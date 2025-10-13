# @FEAT:order-queue @FEAT:background-scheduler @COMP:job @TYPE:core @DEPS:order-tracking,telegram-notification
"""
주문 대기열 자동 재정렬 백그라운드 작업

APScheduler에서 주기적으로 실행되는 스케줄러 함수를 제공합니다.
모든 활성 계정의 (account_id, symbol) 조합에 대해 대기열 재정렬을 수행합니다.
"""

import logging
import time
from typing import Set, Tuple, List
from sqlalchemy import distinct
from flask import Flask

logger = logging.getLogger(__name__)

# 모듈 레벨 변수 (메모리 체크용)
_last_memory_check = 0
_psutil_warning_shown = False


# @FEAT:order-queue @FEAT:background-scheduler @COMP:job @TYPE:core
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
    5. 대기열 적체 모니터링 및 알림

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

            global _last_memory_check, _psutil_warning_shown

            # 메모리 사용량 체크 (5분마다 1회)
            current_time = time.time()
            if current_time - _last_memory_check > 300:  # 5분
                try:
                    import psutil
                    import os

                    process = psutil.Process(os.getpid())
                    memory_info = process.memory_info()
                    memory_mb = memory_info.rss / 1024 / 1024

                    logger.info(f"📊 메모리 사용량: {memory_mb:.2f} MB")

                    # 메모리 경고
                    if memory_mb > 500:
                        logger.warning(f"⚠️ 높은 메모리 사용량 감지: {memory_mb:.2f} MB")

                        if memory_mb > 1024:
                            try:
                                from app.services.telegram import telegram_service
                                if telegram_service.is_enabled():
                                    telegram_service.send_error_alert(
                                        "메모리 사용량 경고",
                                        f"메모리 사용량: {memory_mb:.2f} MB"
                                    )
                            except Exception as e:
                                logger.debug(f"텔레그램 알림 실패 (메모리 경고): {e}")

                    _last_memory_check = current_time

                except ImportError:
                    if not _psutil_warning_shown:
                        logger.warning("⚠️ psutil 패키지가 설치되지 않아 메모리 모니터링을 건너뜁니다")
                        _psutil_warning_shown = True
                except Exception as e:
                    logger.error(f"❌ 메모리 체크 실패: {e}")

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

            # 🔍 디버깅: 중복 검증
            logger.info(
                f"🔍 재정렬 대상 조합 - "
                f"OpenOrder: {len(open_order_pairs)}개, "
                f"PendingOrder: {len(pending_order_pairs)}개, "
                f"합집합: {len(all_pairs)}개"
            )

            if all_pairs:
                logger.info(f"🔍 재정렬 대상 상세:")
                for idx, (account_id, symbol) in enumerate(sorted(all_pairs), 1):
                    logger.info(f"  [{idx}] Account {account_id}: {symbol}")

            if not all_pairs:
                # 재정렬할 주문이 없으면 종료 (로그 스팸 방지)
                return

            # Step 3: 대기열 적체 모니터링 (재정렬 전 체크)
            large_queues = []
            for account_id, symbol in all_pairs:
                pending_count = PendingOrder.query.filter_by(
                    account_id=account_id,
                    symbol=symbol
                ).count()

                # 대기열이 20개 이상이면 경고
                if pending_count >= 20:
                    large_queues.append({
                        'account_id': account_id,
                        'symbol': symbol,
                        'pending_count': pending_count
                    })

            # 대기열 적체 알림
            if large_queues:
                logger.warning(f"⚠️ 대기열 적체 감지 - {len(large_queues)}개 심볼")

                # Telegram 알림 (10개 이상 적체 시)
                if len(large_queues) >= 10:
                    try:
                        from app.services.telegram import telegram_service
                        if telegram_service.is_enabled():
                            message = "대기열 적체 경고\n\n"
                            for item in large_queues[:5]:  # 상위 5개만
                                message += f"계정 {item['account_id']} - {item['symbol']}: {item['pending_count']}개\n"
                            if len(large_queues) > 5:
                                message += f"\n외 {len(large_queues) - 5}개 심볼"

                            telegram_service.send_error_alert(
                                "대기열 적체 경고",
                                message
                            )
                    except Exception as e:
                        logger.debug(f"텔레그램 알림 실패 (대기열 적체): {e}")

            # Step 4: 각 (account_id, symbol)별 재정렬
            total_cancelled = 0
            total_executed = 0
            total_errors = 0

            # OrderQueueManager 인스턴스 재사용 (trading_service에서 기존 인스턴스 가져오기)
            from app.services.trading import trading_service
            queue_manager = trading_service.order_queue_manager

            # 🔍 디버깅: 처리 순서 추적
            processed_pairs = []

            for account_id, symbol in all_pairs:
                try:
                    # 🔍 디버깅: 처리 시작
                    logger.info(f"🔍 재정렬 처리 시작 - Account {account_id}, Symbol: {symbol}")
                    processed_pairs.append((account_id, symbol))

                    result = queue_manager.rebalance_symbol(
                        account_id=account_id,
                        symbol=symbol
                    )

                    # 🔍 디버깅: 처리 완료
                    logger.info(
                        f"🔍 재정렬 처리 완료 - Account {account_id}, Symbol: {symbol}, "
                        f"결과: {result.get('success')}, 취소: {result.get('cancelled')}, 실행: {result.get('executed')}"
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

            # Step 5: 재정렬 후 적체 재확인
            still_large_queues = []
            for account_id, symbol in all_pairs:
                pending_count = PendingOrder.query.filter_by(
                    account_id=account_id,
                    symbol=symbol
                ).count()

                if pending_count >= 20:
                    still_large_queues.append({
                        'account_id': account_id,
                        'symbol': symbol,
                        'pending_count': pending_count
                    })

            # 적체가 해소되지 않았을 때만 알림
            resolved_count = len(large_queues) - len(still_large_queues)
            if resolved_count > 0:
                logger.info(f"✅ 대기열 적체 해소 - {resolved_count}개 심볼")

            # 여전히 적체 중이고 10개 이상이면 Telegram 알림
            if still_large_queues and len(still_large_queues) >= 10:
                try:
                    from app.services.telegram import telegram_service
                    if telegram_service.is_enabled():
                        message = "⚠️ 재정렬 후에도 대기열 적체 지속\n\n"
                        for item in still_large_queues[:5]:
                            message += f"계정 {item['account_id']} - {item['symbol']}: {item['pending_count']}개\n"
                        if len(still_large_queues) > 5:
                            message += f"\n외 {len(still_large_queues) - 5}개 심볼"

                        telegram_service.send_error_alert(
                            "대기열 적체 경고",
                            message
                        )
                except Exception as e:
                    logger.debug(f"텔레그램 알림 실패 (대기열 적체): {e}")
            elif still_large_queues:
                logger.warning(f"⚠️ 대기열 적체 지속 - {len(still_large_queues)}개 심볼 (10개 미만이므로 텔레그램 알림 생략)")

            # Step 6: 결과 로깅 (변경사항이 있을 때만)
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
            except Exception as e:
                logger.debug(f"텔레그램 알림 실패 (스케줄러 오류): {e}")


# @FEAT:order-queue @FEAT:background-scheduler @COMP:job @TYPE:helper
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
            from app.services.trading import trading_service

            queue_manager = trading_service.order_queue_manager
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
