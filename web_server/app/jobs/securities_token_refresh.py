"""
증권 OAuth 토큰 자동 갱신 Job

- 실행 주기: 6시간마다
- 대상: 모든 증권 계좌 (SECURITIES_*)
- 로직: BaseSecuritiesExchange.ensure_token() 위임

관련 문서:
- API 스펙: docs/korea_investment_api_auth.md (Line 78-82)
  * 접근토큰 유효기간: 24시간
  * 갱신 발급 주기: 6시간
  * 6시간 이내 재요청 시 기존 토큰 응답

참고 코드:
- BaseSecuritiesExchange.ensure_token() (app/securities/base.py:95-187)
  * Race Condition 방지: SELECT FOR UPDATE
  * SecuritiesToken.is_expired(): 만료 5분 전 판단
  * SecuritiesToken.needs_refresh(): 마지막 갱신 후 6시간 경과 시 true
"""

import logging
import asyncio
from datetime import datetime
from typing import List, Dict

from flask import Flask

logger = logging.getLogger(__name__)


# @FEAT:securities-token @COMP:job @TYPE:core
class SecuritiesTokenRefreshJob:
    """
    증권 OAuth 토큰 자동 갱신 Job

    특징:
    - 6시간 주기 실행 (토큰 만료 전 갱신)
    - Race Condition 방지 (ensure_token 내부 락)
    - 개별 계좌 실패 시 다음 계좌 처리 계속

    사용 예시:
        # APScheduler 등록
        scheduler.add_job(
            func=lambda: SecuritiesTokenRefreshJob.run(app),
            trigger='interval',
            hours=6,
            id='securities_token_refresh',
            name='증권 OAuth 토큰 자동 갱신'
        )

        # 수동 실행
        result = SecuritiesTokenRefreshJob.run(app)
    """

    # @FEAT:securities-token @COMP:job @TYPE:core
    @staticmethod
    async def run_async(app: Flask = None) -> dict:
        """
        토큰 갱신 Job 실행 (비동기 버전)

        Args:
            app (Flask): Flask 앱 인스턴스 (app context 제공)

        Returns:
            dict: 실행 결과 (성공/실패 계좌 수)

        Note:
            APScheduler에서 호출 시 run() 메서드가 asyncio.run()으로 래핑함
            - 스레드 안전성: 최상위 레벨에서만 asyncio.run() 호출
            - 내부 로직: native await 사용 (중첩 asyncio.run 방지)

        Examples:
            >>> # 비동기 실행 (async 컨텍스트 내에서)
            >>> result = await SecuritiesTokenRefreshJob.run_async(app)
            >>> print(result)
            {
                'success': 3,
                'failed': 1,
                'total': 4,
                'failed_accounts': [...],
                'timestamp': '2025-10-07 12:00:00'
            }
        """
        from app import create_app, db
        from app.models import Account
        from app.exchanges.securities.factory import SecuritiesExchangeFactory

        # Flask app context 생성 (Background Job에서 필수)
        if app is None:
            app = create_app()

        with app.app_context():
            logger.info("🔄 증권 토큰 자동 갱신 Job 시작")

            # 1. 증권 계좌 조회
            securities_accounts = Account.query.filter(
                Account.account_type.like('SECURITIES_%')
            ).all()

            if not securities_accounts:
                logger.info("⚠️ 증권 계좌가 없습니다 (갱신 대상 없음)")
                return {
                    'success': 0,
                    'failed': 0,
                    'total': 0,
                    'failed_accounts': [],
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }

            logger.info(f"📋 증권 계좌 {len(securities_accounts)}개 토큰 갱신 시작")

            # 2. 계좌별 토큰 갱신
            success_count = 0
            failed_accounts = []

            for account in securities_accounts:
                try:
                    # SecuritiesExchangeFactory로 어댑터 생성
                    exchange = SecuritiesExchangeFactory.create(account)

                    # ensure_token()이 자동으로 갱신 필요 여부 판단
                    # - is_expired() 확인: 만료 5분 전이면 재발급
                    # - needs_refresh() 확인: 마지막 갱신 후 6시간 경과 시 갱신
                    # 🆕 Native await 사용 (중첩 asyncio.run 방지)
                    token = await exchange.ensure_token()

                    logger.info(
                        f"✅ 토큰 갱신 성공 "
                        f"(account_id={account.id}, "
                        f"exchange={account.exchange}, "
                        f"token_preview={token[:20] if token else 'N/A'}...)"
                    )
                    success_count += 1

                except Exception as e:
                    logger.error(
                        f"❌ 토큰 갱신 실패 "
                        f"(account_id={account.id}, "
                        f"exchange={account.exchange}): {e}",
                        exc_info=True
                    )
                    failed_accounts.append({
                        'account_id': account.id,
                        'account_name': account.name,
                        'exchange': account.exchange,
                        'error': str(e)
                    })

            # 3. 결과 요약
            result = {
                'success': success_count,
                'failed': len(failed_accounts),
                'total': len(securities_accounts),
                'failed_accounts': failed_accounts,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }

            logger.info(
                f"🏁 증권 토큰 자동 갱신 완료 "
                f"(성공: {success_count}/{len(securities_accounts)}, "
                f"실패: {len(failed_accounts)})"
            )

            return result

    # @FEAT:securities-token @COMP:job @TYPE:core
    @staticmethod
    def run(app: Flask = None) -> dict:
        """
        동기 래퍼 (APScheduler 호환)

        Args:
            app (Flask): Flask 앱 인스턴스

        Returns:
            dict: 실행 결과 (성공/실패 계좌 수)

        Note:
            APScheduler가 호출하는 진입점
            - 내부적으로 asyncio.run()을 사용하여 run_async() 실행
            - 스레드 안전성: 최상위 레벨에서만 asyncio.run() 호출
            - run_async()가 모든 async 로직 처리

        Examples:
            >>> # 동기 실행 (APScheduler에서 호출)
            >>> result = SecuritiesTokenRefreshJob.run(app)
            >>> print(result)
            {
                'success': 3,
                'failed': 1,
                'total': 4,
                'failed_accounts': [...],
                'timestamp': '2025-10-07 12:00:00'
            }
        """
        # 🆕 안전한 asyncio.run() 사용
        # - 최상위 레벨에서만 호출 (스레드 안전)
        # - run_async()가 모든 async 로직 처리
        # - RuntimeError: cannot reuse running loop 방지
        return asyncio.run(SecuritiesTokenRefreshJob.run_async(app))

    # @FEAT:securities-token @COMP:job @TYPE:helper
    @staticmethod
    async def get_accounts_needing_refresh_async(app: Flask = None) -> List['Account']:
        """
        갱신이 필요한 계좌 목록 조회 (비동기 버전)

        Args:
            app (Flask): Flask 앱 인스턴스

        Returns:
            List[Account]: 갱신 필요 계좌 목록

        Note:
            일관성을 위해 비동기 버전 제공
            - 실제로는 DB 쿼리만 수행 (await 불필요)
            - 향후 확장성을 위해 async 패턴 유지

        Examples:
            >>> # 비동기 실행
            >>> accounts = await SecuritiesTokenRefreshJob.get_accounts_needing_refresh_async(app)
            >>> print(f"갱신 필요 계좌: {len(accounts)}개")
        """
        from app import create_app, db
        from app.models import Account, SecuritiesToken
        from datetime import datetime, timedelta

        if app is None:
            app = create_app()

        with app.app_context():
            # 6시간 후 시각
            threshold = datetime.utcnow() + timedelta(hours=6)

            # 토큰이 6시간 이내 만료되는 계좌 조회
            accounts = (
                db.session.query(Account)
                .join(SecuritiesToken, Account.id == SecuritiesToken.account_id)
                .filter(SecuritiesToken.expires_at <= threshold)
                .all()
            )

            return accounts

    # @FEAT:securities-token @COMP:job @TYPE:helper
    @staticmethod
    def get_accounts_needing_refresh(app: Flask = None) -> List['Account']:
        """
        동기 래퍼 - 갱신이 필요한 계좌 목록 조회

        Args:
            app (Flask): Flask 앱 인스턴스

        Returns:
            List[Account]: 갱신 필요 계좌 목록

        Note:
            동기 호출을 위한 래퍼 메서드
            - 내부적으로 asyncio.run() 사용

        Examples:
            >>> # 동기 실행
            >>> accounts = SecuritiesTokenRefreshJob.get_accounts_needing_refresh(app)
            >>> print(f"갱신 필요 계좌: {len(accounts)}개")
        """
        return asyncio.run(SecuritiesTokenRefreshJob.get_accounts_needing_refresh_async(app))
