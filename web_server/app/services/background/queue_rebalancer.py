"""
주문 대기열 자동 재정렬 백그라운드 작업

APScheduler에서 주기적으로 실행되는 스케줄러 함수를 제공합니다.
모든 활성 계정의 (account_id, symbol) 조합에 대해 대기열 재정렬을 수행합니다.
"""

import logging
from typing import Set, Tuple, List
from sqlalchemy import distinct
from flask import Flask

logger = logging.getLogger(__name__)


def rebalance_all_symbols_with_context(app: Flask) -> None:
    """Flask app context에서 모든 심볼의 대기열 재정렬

    처리 단계:
    1. 활성 계정 조회 (is_active=True)
    2. (account_id, symbol) 조합 추출:
       - OpenOrder 테이블에서 DISTINCT (account_id, symbol)
       - PendingOrder 테이블에서 DISTINCT (account_id, symbol)
       - 두 결과 합집합
    3. 각 (account_id, symbol)별로 rebalance_symbol() 호출
    4. 에러 처리 및 로깅

    Args:
        app: Flask 애플리케이션 인스턴스 (app context 제공)

    Returns:
        None (로그만 기록)

    참고:
        - 스케줄러에서 1초마다 실행
        - max_instances=1로 동시 실행 방지
        - 에러 발생 시에도 스케줄러 중단 방지
    """
    with app.app_context():
        try:
            from app import db
            from app.models import Account, OpenOrder, PendingOrder, StrategyAccount
            from app.services.trading.order_queue_manager import OrderQueueManager

            # Step 1: 활성 계정 조회
            active_accounts = Account.query.filter_by(is_active=True).all()
            active_account_ids = {account.id for account in active_accounts}

            if not active_account_ids:
                # 활성 계정이 없으면 종료 (로그 스팸 방지)
                return

            # Step 2: (account_id, symbol) 조합 추출
            # 2-1. OpenOrder에서 조회 (DB 기반)
            open_order_pairs = db.session.query(
                distinct(StrategyAccount.account_id),
                OpenOrder.symbol
            ).join(
                StrategyAccount,
                OpenOrder.strategy_account_id == StrategyAccount.id
            ).filter(
                StrategyAccount.account_id.in_(active_account_ids)
            ).all()

            # 2-2. PendingOrder에서 조회
            pending_order_pairs = db.session.query(
                distinct(PendingOrder.account_id),
                PendingOrder.symbol
            ).filter(
                PendingOrder.account_id.in_(active_account_ids)
            ).all()

            # 2-3. 합집합 (Set으로 중복 제거)
            all_pairs: Set[Tuple[int, str]] = set(open_order_pairs) | set(pending_order_pairs)

            if not all_pairs:
                # 재정렬할 주문이 없으면 종료 (로그 스팸 방지)
                return

            # Step 3: 각 (account_id, symbol)별 재정렬
            total_cancelled = 0
            total_executed = 0
            total_errors = 0

            # OrderQueueManager 인스턴스 생성 (service는 None으로, rebalance_symbol에서만 사용)
            queue_manager = OrderQueueManager(service=None)

            for account_id, symbol in all_pairs:
                try:
                    result = queue_manager.rebalance_symbol(
                        account_id=account_id,
                        symbol=symbol
                    )

                    if result.get('success'):
                        total_cancelled += result.get('cancelled', 0)
                        total_executed += result.get('executed', 0)
                    else:
                        total_errors += 1
                        logger.warning(
                            f"⚠️  재정렬 실패 - account_id={account_id}, symbol={symbol}, "
                            f"error={result.get('error')}"
                        )

                except Exception as e:
                    total_errors += 1
                    logger.error(
                        f"❌ 재정렬 예외 발생 - account_id={account_id}, symbol={symbol}: {e}",
                        exc_info=True
                    )

            # Step 4: 결과 로깅 (변경사항이 있을 때만)
            if total_cancelled > 0 or total_executed > 0 or total_errors > 0:
                logger.info(
                    f"🔄 대기열 재정렬 완료 - "
                    f"대상: {len(all_pairs)}개 심볼, "
                    f"취소: {total_cancelled}개, "
                    f"실행: {total_executed}개, "
                    f"오류: {total_errors}개"
                )

        except Exception as e:
            # 스케줄러 중단 방지를 위한 최상위 예외 처리
            logger.error(f"❌ 대기열 재정렬 스케줄러 오류: {e}", exc_info=True)

            # Telegram 알림 (다른 스케줄러 패턴과 일치)
            try:
                from app.utils.telegram import send_telegram_message
                send_telegram_message(
                    f"🚨 대기열 재정렬 스케줄러 오류\n\n"
                    f"오류: {str(e)}\n"
                    f"상세 로그를 확인하세요."
                )
            except Exception:
                pass  # 텔레그램 알림 실패는 조용히 무시


def rebalance_specific_symbol_with_context(
    app: Flask,
    account_id: int,
    symbol: str
) -> dict:
    """특정 심볼에 대한 수동 재정렬 (Admin API용)

    Args:
        app: Flask 애플리케이션 인스턴스
        account_id: 계정 ID
        symbol: 거래 심볼

    Returns:
        dict: 재정렬 결과
            {
                'success': bool,
                'cancelled': int,
                'executed': int,
                'total_orders': int,
                'active_orders': int,
                'pending_orders': int
            }
    """
    with app.app_context():
        try:
            from app.services.trading.order_queue_manager import OrderQueueManager

            queue_manager = OrderQueueManager(service=None)
            result = queue_manager.rebalance_symbol(
                account_id=account_id,
                symbol=symbol
            )

            logger.info(
                f"🔧 수동 재정렬 완료 - account_id={account_id}, symbol={symbol}, "
                f"결과={result}"
            )

            return result

        except Exception as e:
            logger.error(
                f"❌ 수동 재정렬 실패 - account_id={account_id}, symbol={symbol}: {e}",
                exc_info=True
            )
            return {
                'success': False,
                'error': str(e),
                'cancelled': 0,
                'executed': 0
            }
