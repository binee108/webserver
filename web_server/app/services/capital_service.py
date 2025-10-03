"""
자본 배분 서비스 모듈

계좌의 전략별 자본을 재배분하는 로직을 제공합니다.
"""

import logging
from decimal import Decimal
from datetime import datetime
from typing import Dict, Any, List

from app import db
from app.models import Account, StrategyAccount, StrategyCapital, DailyAccountSummary
from app.services.exchange import exchange_service
from app.utils.logging_security import get_secure_logger

logger = get_secure_logger(__name__)


class CapitalAllocationError(Exception):
    """자본 배분 관련 오류"""
    pass


class CapitalAllocationService:
    """자본 배분 서비스 클래스"""

    def __init__(self):
        self.session = db.session

    def recalculate_strategy_capital(self, account_id: int, use_live_balance: bool = False) -> Dict[str, Any]:
        """
        계좌의 전략별 자본을 재배분합니다.

        재배분 공식:
        1. 계좌 총 자산 = DailyAccountSummary.ending_balance (최신) 또는 실시간 잔고
        2. 전략별 가중치 합 = Σ(StrategyAccount.weight)
        3. 전략별 할당 자본 = (총 자산 × 전략 가중치) / 가중치 합

        Args:
            account_id: 계좌 ID
            use_live_balance: 실시간 거래소 API 호출 여부 (기본값: False)

        Returns:
            Dict[str, Any]: 재배분 결과
                - total_capital: 총 자본
                - allocations: 전략별 할당 내역
                - source: 잔고 출처 (db/live)

        Raises:
            CapitalAllocationError: 계좌를 찾을 수 없거나 전략이 없는 경우
        """
        logger.info(f"🔄 자본 재배분 시작 - 계좌: {account_id}, 실시간 조회: {use_live_balance}")

        # 1. 계좌 조회
        account = Account.query.get(account_id)
        if not account:
            raise CapitalAllocationError(f"계좌를 찾을 수 없습니다: {account_id}")

        # 2. 총 자산 계산
        total_capital, balance_source = self._get_total_capital(account, use_live_balance)

        logger.info(f"💰 총 자산: {total_capital} USDT (출처: {balance_source})")

        # 3. 전략 목록 및 가중치 합 계산
        strategy_accounts = StrategyAccount.query.filter_by(
            account_id=account_id,
            is_active=True
        ).all()

        if not strategy_accounts:
            logger.warning(f"⚠️ 계좌 {account_id}에 연결된 활성 전략이 없습니다")
            return {
                'account_id': account_id,
                'total_capital': float(total_capital),
                'allocations': [],
                'source': balance_source,
                'message': '연결된 활성 전략이 없습니다'
            }

        total_weight = sum(sa.weight for sa in strategy_accounts)

        if total_weight == 0:
            raise CapitalAllocationError(f"전략 가중치 합이 0입니다 (계좌: {account_id})")

        logger.info(f"📊 전략 수: {len(strategy_accounts)}, 총 가중치: {total_weight}")

        # 4. 전략별 자본 재배분
        results = []
        for sa in strategy_accounts:
            allocated = (total_capital * Decimal(sa.weight)) / Decimal(total_weight)

            # StrategyCapital 업데이트 또는 생성
            capital = StrategyCapital.query.filter_by(
                strategy_account_id=sa.id
            ).first()

            old_capital = capital.allocated_capital if capital else 0

            if capital:
                capital.allocated_capital = float(allocated)
                capital.last_updated = datetime.utcnow()
            else:
                capital = StrategyCapital(
                    strategy_account_id=sa.id,
                    allocated_capital=float(allocated)
                )
                self.session.add(capital)

            results.append({
                'strategy_account_id': sa.id,
                'strategy_name': sa.strategy.name if sa.strategy else 'Unknown',
                'weight': sa.weight,
                'old_capital': float(old_capital),
                'allocated_capital': float(allocated),
                'change': float(allocated - Decimal(str(old_capital)))
            })

            logger.info(
                f"  ✅ {sa.strategy.name if sa.strategy else 'Unknown'}: "
                f"{old_capital:.2f} → {allocated:.2f} USDT (가중치: {sa.weight})"
            )

        self.session.commit()

        logger.info(f"✅ 자본 재배분 완료 - 계좌: {account_id}, 처리된 전략: {len(results)}개")

        return {
            'account_id': account_id,
            'account_name': account.name,
            'total_capital': float(total_capital),
            'allocations': results,
            'source': balance_source,
            'total_weight': total_weight,
            'timestamp': datetime.utcnow().isoformat()
        }

    def _get_total_capital(self, account: Account, use_live_balance: bool) -> tuple[Decimal, str]:
        """
        계좌의 총 자산을 조회합니다.

        Args:
            account: 계좌 객체
            use_live_balance: 실시간 조회 여부

        Returns:
            tuple: (총 자산, 출처)
        """
        if use_live_balance:
            # 실시간 거래소 API 호출
            try:
                balance = exchange_service.get_balance(
                    account=account,
                    asset='USDT',
                    market_type='futures'
                )
                total = Decimal(str(balance.get('total', 0)))
                logger.info(f"📡 실시간 잔고 조회: {total} USDT")
                return total, 'live'
            except Exception as e:
                logger.warning(f"⚠️ 실시간 잔고 조회 실패: {e}, DB 폴백")

        # DB에서 최신 잔고 조회
        latest_summary = DailyAccountSummary.query.filter_by(
            account_id=account.id
        ).order_by(DailyAccountSummary.date.desc()).first()

        if latest_summary:
            total = Decimal(str(latest_summary.ending_balance))
            logger.info(f"💾 DB 잔고 조회: {total} USDT (날짜: {latest_summary.date})")
            return total, 'db'

        # DB에도 없으면 실시간 조회 시도
        logger.warning(f"⚠️ DB에 잔고 기록이 없습니다, 실시간 조회 시도")
        try:
            balance = exchange_service.get_balance(
                account=account,
                asset='USDT',
                market_type='futures'
            )
            total = Decimal(str(balance.get('total', 0)))
            logger.info(f"📡 실시간 잔고 조회 (폴백): {total} USDT")
            return total, 'live_fallback'
        except Exception as e:
            logger.error(f"❌ 잔고 조회 실패: {e}")
            raise CapitalAllocationError(f"잔고를 조회할 수 없습니다: {e}")


# 싱글톤 인스턴스
capital_allocation_service = CapitalAllocationService()
