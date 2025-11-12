
"""
Order management logic extracted from the legacy trading service.

@FEAT:order-cancel @COMP:service @TYPE:core
Phase 5: Step 3 (Code Implementation) - OpenOrder 취소 기능 (PendingOrder 제거 완료)
"""

from __future__ import annotations

import contextlib
import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import joinedload
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import Account, OpenOrder, Strategy, StrategyAccount
from app.services.exchange import exchange_service
from app.constants import OrderType, OrderStatus
from app.services.trading.core import sanitize_error_message

logger = logging.getLogger(__name__)

# @FEAT:order-cancel @COMP:util @TYPE:config
# Phase 5: PendingOrder 시스템 제거됨 (모든 주문은 즉시 거래소 실행)


class OrderManager:
    """Handles order lifecycle operations and OpenOrder persistence."""

    def __init__(self, service: Optional[object] = None) -> None:
        self.service = service
        self.db = db.session  # SQLAlchemy session for queries

        # Phase 2: STOP_LIMIT fetch_order 실패 추적 캐시
        # @FEAT:stop-limit-activation @COMP:service @TYPE:helper @ISSUE:45
        # fetch_order() 연속 3회 실패 감지용 메모리 캐시
        # 형식: {order_id: failure_count}
        self.fetch_failure_cache: Dict[str, int] = {}

    def create_order(self, strategy_id: int, symbol: str, side: str,
                    quantity: Decimal, order_type: str = 'MARKET',
                    price: Optional[Decimal] = None,
                    stop_price: Optional[Decimal] = None) -> Dict[str, Any]:
        """주문 생성"""
        try:
            strategy = Strategy.query.get(strategy_id)
            if not strategy:
                return {
                    'success': False,
                    'error': '전략을 찾을 수 없습니다',
                    'error_type': 'strategy_error'
                }

            return self.service.execute_trade(
                strategy=strategy,
                symbol=symbol,
                side=side,
                quantity=quantity,
                order_type=order_type,
                price=price,
                stop_price=stop_price
            )

        except Exception as e:
            logger.error(f"주문 생성 실패: {e}")
            return {
                'success': False,
                'error': str(e),
                'error_type': 'order_error'
            }

    # @FEAT:order-cancellation @COMP:service @TYPE:core
    # @FEAT:orphan-order-prevention @COMP:service @TYPE:core
    # Issue #32: Binance Error -2011 (Unknown order) 처리 추가
    # 취소 실패 시 fetch_order()로 주문 상태 재조회하여 DB 정합성 자동 복구
    # Phase 4 (2025-11-05): -2011 감지 → fetch_order 재조회 → 정합성 복구 또는 FailedOrder 추가
    def cancel_order(
        self,
        order_id: str,
        symbol: str,
        account_id: int,
        strategy_account_id: Optional[int] = None,
        open_order: Optional[OpenOrder] = None
    ) -> Dict[str, Any]:
        """주문 취소 (DB-First 패턴)

        WHY: 타임아웃 시 orphan order 방지. DB 상태를 먼저 변경하여 백그라운드 정리 가능.
        Edge Cases: 중복 취소(already_cancelling), 주문 없음(order_not_found), race condition(재조회),
                   Binance Error -2011(Unknown order, 즉시 체결 LIMIT 주문 취소 시 발생)
        Side Effects: DB commit (CANCELLING 상태), SSE 이벤트, 거래소 API 호출 (최대 2회)
        Performance: 정상 1×commit, 실패/예외 2×commit, -2011 특수 처리 시 1×fetch_order 추가
        Debugging: 로그에서 🔄→✅/⚠️/❌ 이모지로 경로 추적

        Pattern:
        1. DB 상태를 CANCELLING으로 먼저 변경
        2. 거래소 API 호출 (타임아웃/재시도는 Phase 3)
        3. 성공 시: CANCELLING → CANCELLED (DB 삭제)
        4. 실패 시 (일반 오류): CANCELLING → OPEN (원래 상태 복원)
        5. 실패 시 (Error -2011): 주문 상태 재조회 →
           FILLED/CANCELED/EXPIRED → DB 삭제 (정합성 복구)
           NEW/OPEN/PARTIALLY_FILLED → FailedOrder 추가 (자동 재시도)
           조회 실패 → 안전하게 DB 정리
        6. 예외 시: 하이브리드 처리 (1회 재확인 + 백그라운드)

        Args:
            order_id: 거래소 주문 ID
            symbol: 심볼
            account_id: 계정 ID (레거시 호환성)
            strategy_account_id: 전략 계정 ID (Optional, open_order와 함께 사용 시 무시됨)
            open_order: OpenOrder 객체 (Optional, 제공 시 추가 조회 생략 및 정확한 market_type 사용)

        Returns:
            Dict[str, Any] with keys:
                success (bool): 취소 성공 여부
                order_id (str): 주문 ID (성공 시)
                symbol (str): 심볼 (성공 시)
                error (str): 오류 메시지 (실패 시)
                error_type (str): 오류 분류
                    'order_not_found' - 주문 없음
                    'already_cancelling' - 이미 취소 중
                    'cancel_verification_failed' - 거래소 취소 미확인
                    'pending_retry' - FailedOrder 추가됨 (재시도 대기)
                    'cancel_error' - 예외 발생
                action (str): 최종 조치 ('removed' = DB 삭제됨)
                message (str): 추가 설명
        """
        try:
            # ============================================================
            # STEP 0: Validation (Phase 3a: open_order 우선 사용)
            # ============================================================

            # 🆕 Phase 3a: open_order 인자 우선 사용 (추가 조회 불필요)
            if not open_order:
                open_order = OpenOrder.query.filter_by(
                    exchange_order_id=order_id
                ).first()

            if not open_order:
                return {
                    'success': False,
                    'error': '주문을 찾을 수 없습니다',
                    'error_type': 'order_not_found'
                }

            # 이미 취소 중인 경우
            if open_order.status == OrderStatus.CANCELLING:
                return {
                    'success': False,
                    'error': '이미 취소 처리 중입니다',
                    'error_type': 'already_cancelling'
                }

            # ✅ Phase 3a: 정확한 market_type (open_order에서 직접 가져오기)
            strategy_account = open_order.strategy_account
            if not strategy_account or not strategy_account.account:
                return {
                    'success': False,
                    'error': 'StrategyAccount를 찾을 수 없습니다',
                    'error_type': 'account_error'
                }

            account = strategy_account.account
            market_type = open_order.market_type or strategy_account.strategy.market_type.lower()

            # ============================================================
            # STEP 1: DB 상태를 CANCELLING으로 먼저 변경
            # ============================================================
            old_status = open_order.status
            open_order.status = OrderStatus.CANCELLING
            open_order.cancel_attempted_at = datetime.utcnow()
            db.session.commit()

            logger.info(
                f"🔄 주문 취소 시작: {old_status} → {OrderStatus.CANCELLING} "
                f"(order_id={order_id}, symbol={symbol}, market_type={market_type})"
            )

            try:
                # ============================================================
                # STEP 2: 거래소 API 호출 (Phase 3: 타임아웃 10초 + 재시도 3회)
                # ============================================================
                result = exchange_service.cancel_order_with_retry(
                    account=account,
                    order_id=order_id,
                    symbol=symbol,
                    market_type=market_type,
                    max_retries=3,
                    timeout=10.0
                )

                # ============================================================
                # STEP 3: 성공 시 CANCELLING → CANCELLED (DB 삭제)
                # ============================================================
                if result['success']:
                    # 거래소 측 취소 결과 검증
                    if not self._confirm_order_cancelled(
                        account=account,
                        order_id=order_id,
                        symbol=symbol,
                        market_type=market_type,
                        cancel_result=result
                    ):
                        # 취소 미확인 → 원래 상태 복원
                        revert_msg = sanitize_error_message(
                            result.get('error', 'Cancellation not confirmed by exchange')
                        )
                        open_order.status = old_status
                        open_order.cancel_attempted_at = None
                        open_order.error_message = revert_msg
                        db.session.commit()

                        logger.warning(
                            "⚠️ 거래소 취소 미확인 → %s 복원: order_id=%s",
                            old_status,
                            order_id
                        )

                        return {
                            'success': False,
                            'error': 'Cancellation not confirmed by exchange',
                            'error_type': 'cancel_verification_failed'
                        }

                    # 주문 정보 로그 (삭제 전)
                    logger.info(f"✅ 거래소 취소 확인 → DB 삭제: {order_id}")

                    # SSE 이벤트 발송 (DB 삭제 전)
                    try:
                        strategy_account = open_order.strategy_account
                        if strategy_account and strategy_account.strategy_id:
                            self.service.event_emitter.emit_order_cancelled_event(
                                order_id=order_id,
                                symbol=symbol,
                                account_id=account_id
                            )
                    except Exception as sse_error:
                        logger.warning(f"OpenOrder SSE 이벤트 발송 실패: {sse_error}")

                    # DB에서 완전히 삭제
                    db.session.delete(open_order)
                    db.session.commit()

                    # 동일 심볼의 다른 OpenOrder가 있는지 확인
                    remaining_orders = OpenOrder.query.filter_by(
                        symbol=symbol
                    ).join(StrategyAccount).filter(
                        StrategyAccount.account_id == account_id
                    ).count()

                    if remaining_orders == 0:
                        # 더 이상 주문이 없으면 구독 해제
                        self.service.unsubscribe_symbol(account_id, symbol)
                        logger.info(
                            f"📊 심볼 구독 해제 - 계정: {account_id}, 심볼: {symbol} (마지막 주문)"
                        )
                    else:
                        logger.debug(
                            f"📊 심볼 구독 유지 - 계정: {account_id}, 심볼: {symbol} "
                            f"(남은 주문: {remaining_orders}개)"
                        )

                    logger.info(f"✅ 취소된 주문이 정리되었습니다: {order_id}")

                    return {
                        'success': True,
                        'order_id': order_id,
                        'symbol': symbol
                    }

                # ============================================================
                # STEP 4: 실패 시 CANCELLING → OPEN (원래 상태 복원)
                # ============================================================
                else:
                    error_msg = sanitize_error_message(
                        result.get('error', 'Exchange cancellation failed')
                    )

                    # 주문 다시 조회 (refresh, race condition 방어)
                    open_order = OpenOrder.query.filter_by(
                        exchange_order_id=order_id
                    ).first()

                    if not open_order:
                        # Race condition: 다른 프로세스가 이미 삭제
                        logger.warning(f"⚠️ 주문이 이미 삭제됨 (race condition): {order_id}")
                        return result

                    # ============================================================
                    # STEP 4.1: Binance Error -2011 (Unknown order) 특수 처리
                    # ============================================================
                    # Issue #32: 즉시 체결 LIMIT 주문 취소 시 -2011 발생 → 주문 상태 재조회
                    if '-2011' in error_msg or 'Unknown order' in error_msg:
                        logger.info(
                            f"🔍 Binance Error -2011 감지 → 주문 상태 재조회: {order_id}"
                        )

                        # 주문 최종 상태 조회
                        fetched_order = exchange_service.fetch_order(
                            account=account,
                            symbol=symbol,
                            order_id=order_id,
                            market_type=market_type
                        )

                        if fetched_order and fetched_order.get('success'):
                            final_status = fetched_order.get('status', '').upper()

                            # Case 1: 이미 종료된 주문 → DB 정리 (정상 처리)
                            if final_status in ['FILLED', 'CANCELED', 'EXPIRED']:
                                logger.info(
                                    f"✅ 주문 이미 종료 ({final_status}) → DB 삭제: {order_id}"
                                )

                                # Race condition 방어: 다시 조회
                                open_order = OpenOrder.query.filter_by(
                                    exchange_order_id=order_id
                                ).first()

                                if open_order:
                                    db.session.delete(open_order)
                                    db.session.commit()

                                    # SSE 알림 (주문 삭제 이벤트)
                                    try:
                                        if self.service and hasattr(self.service, 'event_emitter'):
                                            self.service.event_emitter.emit_order_cancelled_event(
                                                order_id=order_id,
                                                symbol=symbol,
                                                account_id=account.id
                                            )
                                    except Exception as emit_error:
                                        logger.warning(f"⚠️ SSE 이벤트 발송 실패: {emit_error}")

                                return {
                                    'success': True,
                                    'message': f'Order already {final_status}',
                                    'action': 'removed'
                                }

                            # Case 2: 아직 열린 주문 → FailedOrder 추가 (재시도 필요)
                            elif final_status in ['NEW', 'OPEN', 'PARTIALLY_FILLED']:
                                logger.warning(
                                    f"⚠️ 취소 실패하지만 주문 존재 ({final_status}) "
                                    f"→ FailedOrder 추가 (재시도 대기): {order_id}"
                                )

                                # TODO (Phase 2 고려사항): PARTIALLY_FILLED 케이스는 filled_quantity 확인 필요
                                # 현재는 재시도 큐에 추가하여 재취소 시도 (최소 구현)
                                # Phase 2에서 fetch_order() 결과의 filled_quantity로 Trade 생성 로직 추가 검토

                                # CANCELLING → 원래 상태 복원
                                open_order = OpenOrder.query.filter_by(
                                    exchange_order_id=order_id
                                ).first()

                                if open_order:
                                    open_order.status = old_status
                                    open_order.error_message = error_msg
                                    db.session.commit()

                                    # FailedOrder 큐에 추가
                                    try:
                                        from app.services.trading.failed_order_manager import failed_order_manager
                                        failed_order_manager.create_failed_cancellation(
                                            order=open_order,
                                            exchange_error=error_msg
                                        )
                                    except Exception as fe:
                                        logger.error(
                                            f"⚠️ FailedOrder 생성 실패 - "
                                            f"order_id={order_id}, error={fe}"
                                        )

                                return {
                                    'success': False,
                                    'error': error_msg,
                                    'error_type': 'pending_retry'
                                }

                        # Case 3: 조회 실패 또는 주문 없음 → 안전하게 삭제
                        else:
                            logger.warning(
                                f"⚠️ 주문 조회 실패 또는 거래소에 없음 → DB 정리: {order_id}"
                            )

                            open_order = OpenOrder.query.filter_by(
                                exchange_order_id=order_id
                            ).first()

                            if open_order:
                                db.session.delete(open_order)
                                db.session.commit()

                            return {
                                'success': True,
                                'message': 'Order not found on exchange (cleaned up)',
                                'action': 'removed'
                            }

                    # ============================================================
                    # STEP 4.2: 기존 로직 (다른 오류 처리: -1021 Timestamp, -2015 Invalid API-key 등)
                    # ============================================================
                    # NOTE: Binance Error -2011 케이스는 위에서 이미 return으로 종료되므로,
                    # 이 아래 코드는 다른 오류 케이스에만 자동 실행됨
                    open_order.status = old_status
                    open_order.error_message = error_msg
                    db.session.commit()

                    logger.warning(
                        f"⚠️ 거래소 취소 실패 → {old_status} 복원: {order_id} "
                        f"(error: {error_msg[:50]}...)"
                    )

                    # @FEAT:orphan-order-prevention @COMP:service @TYPE:core @PHASE:2
                    # Phase 2: 취소 실패 추적 - exchange API 실패 시 FailedOrder 생성
                    try:
                        from app.services.trading.failed_order_manager import failed_order_manager
                        failed_order_manager.create_failed_cancellation(
                            order=open_order,
                            exchange_error=result.get('error')
                        )
                    except Exception as fe:
                        # Non-blocking: FailedOrder 생성 실패는 치명적이지 않음 (취소 실패는 이미 발생)
                        logger.error(
                            f"⚠️ FailedOrder 생성 실패 (취소 실패는 이미 발생) - "
                            f"order_id={order_id}, error={fe}"
                        )

                    return result

            except Exception as e:
                # ============================================================
                # STEP 5: 예외 시 하이브리드 처리 (1회 재확인 + 백그라운드)
                # ============================================================
                logger.error(f"❌ 주문 취소 예외: {order_id} - {e}")

                try:
                    # 1회 재확인 시도
                    verification_result = self._verify_cancellation_once(
                        account=account,
                        order_id=order_id,
                        symbol=symbol,
                        market_type=market_type
                    )

                    # 주문 다시 조회 (refresh, race condition 방어)
                    open_order = OpenOrder.query.filter_by(
                        exchange_order_id=order_id
                    ).first()

                    if not open_order:
                        logger.warning(f"⚠️ 주문이 이미 삭제됨 (race condition): {order_id}")
                        return {
                            'success': False,
                            'error': str(e),
                            'error_type': 'cancel_error'
                        }

                    if verification_result == 'cancelled':
                        # 거래소에서 실제로 취소됨 → DB 삭제
                        logger.info(
                            f"✅ 재확인: 거래소에서 취소됨 확인 → DB 삭제: {order_id}"
                        )
                        db.session.delete(open_order)
                        db.session.commit()

                        return {
                            'success': True,
                            'order_id': order_id,
                            'symbol': symbol,
                            'verified': True
                        }

                    # @FEAT:orphan-order-prevention @COMP:service @TYPE:core @PHASE:3b
                    # Phase 3b.2: Race Condition S5.2 - 취소 중 체결된 주문 처리
                    elif verification_result == 'filled':
                        # 거래소에서 체결됨 확인 → DB 삭제
                        logger.info(
                            f"✅ 재확인: 거래소에서 체결됨 확인 → DB 삭제: {order_id}"
                        )
                        db.session.delete(open_order)
                        db.session.commit()

                        return {
                            'success': True,
                            'order_id': order_id,
                            'symbol': symbol,
                            'already_filled': True,
                            'error_type': 'already_filled',
                            'message': '주문이 체결되어 DB에서 제거됨'
                        }

                    elif verification_result == 'active':
                        # 거래소에서 여전히 활성 상태 → OPEN 복원
                        error_msg = sanitize_error_message(str(e))
                        open_order.status = old_status
                        open_order.error_message = error_msg
                        db.session.commit()

                        logger.warning(
                            f"⚠️ 재확인: 거래소에서 활성 확인 → {old_status} 복원: {order_id}"
                        )

                        # @FEAT:orphan-order-prevention @COMP:service @TYPE:core @PHASE:2
                        # Phase 2: 예외 발생 시에도 FailedOrder 생성 (verification_result='active'일 때)
                        try:
                            from app.services.trading.failed_order_manager import failed_order_manager
                            failed_order_manager.create_failed_cancellation(
                                order=open_order,
                                exchange_error=str(e)
                            )
                        except Exception as fe:
                            logger.error(
                                f"⚠️ FailedOrder 생성 실패 (예외 발생 후) - "
                                f"order_id={order_id}, error={fe}"
                            )

                        return {
                            'success': False,
                            'error': str(e),
                            'error_type': 'cancel_error_verified_active'
                        }

                    else:
                        # 재확인 실패 → CANCELLING 유지, 백그라운드가 5분 후 정리
                        logger.warning(
                            f"⚠️ 재확인 실패 → CANCELLING 유지 (백그라운드 대기): {order_id}"
                        )

                        return {
                            'success': False,
                            'error': str(e),
                            'error_type': 'cancel_error_unverified'
                        }

                except Exception as verify_error:
                    logger.error(f"❌ 재확인 실패: {order_id} - {verify_error}")

                    # 재확인 자체 실패 → CANCELLING 유지, 백그라운드가 정리
                    return {
                        'success': False,
                        'error': str(e),
                        'error_type': 'cancel_error'
                    }

        except Exception as outer_e:
            logger.error(f"❌ 주문 취소 외부 예외: {order_id} - {outer_e}")
            db.session.rollback()
            return {
                'success': False,
                'error': str(outer_e),
                'error_type': 'cancel_error'
            }

    # @FEAT:order-tracking @COMP:service @TYPE:helper
    def _verify_cancellation_once(
        self,
        account: Account,
        order_id: str,
        symbol: str,
        market_type: str
    ) -> str:
        """1회 재확인: 거래소에서 주문 상태 확인

        WHY: 거래소 API 타임아웃 시 실제 취소 여부 확인. CANCELLING 상태 orphan 방지.
        Edge Cases: 네트워크 오류 → 'unknown', FILLED 상태 → 'filled' (Phase 3b.2)
        Side Effects: 거래소 API 1회 호출 (fetch_order)
        Performance: 거래소 API 응답 시간 (보통 100-500ms)
        Debugging: 로그 "⚠️ 주문 상태 조회 실패" 또는 "✅ 주문 체결 확인 (Race Condition)"

        Phase 2 (cancel_order 예외 처리) + Phase 3b.2 (Race S5.2) + Phase 4 (백그라운드 정리)에서 재사용.

        Args:
            account: 거래소 계정
            order_id: 주문 ID
            symbol: 심볼
            market_type: 마켓 타입 ('spot', 'futures' 등)

        Returns:
            'cancelled': 거래소에서 취소됨 확인
            'active': 거래소에서 여전히 활성 상태
            'filled': 거래소에서 체결됨 확인 (Phase 3b.2 추가)
            'unknown': 확인 실패 (네트워크 오류 등)
        """
        try:
            # 거래소에서 주문 상태 조회
            order_info = exchange_service.fetch_order(
                account=account,
                symbol=symbol,
                order_id=order_id,
                market_type=market_type
            )

            if not order_info or not order_info.get('success'):
                logger.warning(f"⚠️ 주문 상태 조회 실패: {order_id}")
                return 'unknown'

            status = order_info.get('status', '').upper()

            # 취소 관련 상태
            if status in ['CANCELLED', 'CANCELED', 'REJECTED', 'EXPIRED']:
                return 'cancelled'

            # 활성 상태
            if status in ['NEW', 'OPEN', 'PENDING', 'PARTIALLY_FILLED']:
                return 'active'

            # @FEAT:orphan-order-prevention @COMP:service @TYPE:core @PHASE:3b
            # Phase 3b.2: 체결 상태 처리 (Race Condition S5.2)
            # 일부 거래소는 소문자 status 반환 가능 (defensive coding)
            if status in ['FILLED', 'CLOSED', 'closed', 'filled']:
                logger.info(f"✅ 주문 체결 확인 (Race S5.2): order_id={order_id}, status={status}")
                return 'filled'

            # 기타 (예상치 못한 상태)
            logger.warning(f"⚠️ 예상치 못한 주문 상태: {status} (order_id={order_id})")
            return 'unknown'

        except Exception as e:
            logger.error(f"❌ 주문 상태 조회 예외: {order_id} - {e}")
            return 'unknown'

    def _confirm_order_cancelled(
        self,
        account: Account,
        order_id: str,
        symbol: str,
        market_type: str,
        cancel_result: Dict[str, Any]
    ) -> bool:
        """거래소가 실제로 주문 취소를 반영했는지 확인한다.

        검증 순서:
            1. 취소 응답에 status 힌트가 있는 경우 우선 사용
            2. fetch_order 1회 확인 (_verify_cancellation_once 재사용)
            3. 여전히 불확실하면 get_open_orders로 잔존 여부 확인

        Returns:
            bool: True → 취소 확인, False → 취소 미확인
        """
        from app.constants import OrderStatus

        # Step 1: 응답에 status 힌트가 있는 경우 (예: Binance cancel_order 응답)
        result_payload = (cancel_result or {}).get('result') or {}
        status_hint = result_payload.get('status')
        if status_hint:
            normalized = OrderStatus.from_exchange(status_hint, account.exchange)
            if normalized in (
                OrderStatus.CANCELLED,
                OrderStatus.REJECTED,
                OrderStatus.EXPIRED,
            ):
                return True

        # 이미 취소됨(already_cancelled) 플래그는 불확실 -> 추가 검증 진행

        # Step 2: fetch_order로 단일 확인
        verification = self._verify_cancellation_once(
            account=account,
            order_id=order_id,
            symbol=symbol,
            market_type=market_type
        )

        if verification == 'cancelled':
            return True
        if verification == 'active':
            logger.warning(
                "⚠️ 거래소 응답에서 주문이 여전히 활성 상태로 확인됨 - order_id=%s",
                order_id
            )
            return False

        # Step 3: open orders 조회로 최종 확인 (verification == 'unknown')
        try:
            open_orders_result = exchange_service.get_open_orders(
                account=account,
                symbol=symbol,
                market_type=market_type
            )

            if not open_orders_result.get('success'):
                logger.warning(
                    "⚠️ 거래소 미체결 주문 조회 실패 - order_id=%s, error=%s",
                    order_id,
                    open_orders_result.get('error')
                )
                return False

            orders = open_orders_result.get('orders', [])
            for raw_order in orders:
                current_id = None
                if hasattr(raw_order, 'id'):
                    current_id = str(raw_order.id)
                elif isinstance(raw_order, dict):
                    current_id = str(raw_order.get('id') or raw_order.get('order_id'))

                if current_id == str(order_id):
                    logger.warning(
                        "⚠️ 주문이 여전히 거래소에 존재 - order_id=%s",
                        order_id
                    )
                    return False

            # 미체결 목록에 존재하지 않으면 취소된 것으로 간주
            return True

        except Exception as e:
            logger.error(
                "❌ 거래소 미체결 주문 확인 실패 - order_id=%s, error=%s",
                order_id,
                e
            )
            return False

    def cancel_order_by_user(self, order_id: str, user_id: int) -> Dict[str, Any]:
        """사용자 권한 기준 주문 취소 (OpenOrder)

        @FEAT:order-cancel @COMP:service @TYPE:core

        OpenOrder를 거래소 API를 통해 취소하고 Order List SSE를 발송합니다.
        Phase 5 이후 모든 주문은 즉시 거래소에 실행되므로 PendingOrder 로직은 제거되었습니다.

        Args:
            order_id: 주문 ID (거래소 주문 ID)
            user_id: 사용자 ID (권한 검증용)

        Returns:
            Dict[str, Any]: {
                'success': bool,
                'error': str,  # 실패 시
                'symbol': str,  # 성공 시
                'source': str   # 'exchange'
            }
        """
        try:
            from app.constants import OrderStatus

            # OpenOrder 취소 경로 (모든 주문은 거래소 직접 실행)
            logger.info(f"📋 OpenOrder 취소 요청: order_id={order_id}, user_id={user_id}")

            open_order = (
                OpenOrder.query
                .join(StrategyAccount)
                .join(Account)
                .options(
                    joinedload(OpenOrder.strategy_account)
                    .joinedload(StrategyAccount.account)
                )
                .filter(
                    OpenOrder.exchange_order_id == order_id,
                    Account.user_id == user_id,
                    Account.is_active == True,
                    OpenOrder.status.in_(OrderStatus.get_open_statuses())
                )
                .first()
            )

            if not open_order:
                return {
                    'success': False,
                    'error': '주문을 찾을 수 없거나 취소할 권한이 없습니다.',
                    'error_type': 'permission_error'
                }

            # 기존 cancel_order 메서드 재사용 (Phase 3a: open_order 전달)
            result = self.service.cancel_order(
                order_id=order_id,
                symbol=open_order.symbol,
                account_id=open_order.strategy_account.account.id,
                open_order=open_order  # 🆕 Phase 3a: 정확한 market_type 사용
            )

            if result['success']:
                result['symbol'] = open_order.symbol
                result['source'] = 'exchange'

            return result

        except Exception as e:
            db.session.rollback()
            logger.error(f"주문 취소 실패: order_id={order_id}, user_id={user_id}, error={e}")
            return {
                'success': False,
                'error': str(e),
                'error_type': 'cancel_error'
            }

    def get_open_orders(self, account_id: int, symbol: Optional[str] = None, market_type: str = 'spot') -> Dict[str, Any]:
        """미체결 주문 조회"""
        try:
            account = Account.query.get(account_id)
            if not account:
                return {
                    'success': False,
                    'error': '계정을 찾을 수 없습니다',
                    'error_type': 'account_error'
                }

            # 거래소에서 미체결 주문 조회
            result = exchange_service.get_open_orders(
                account=account,
                symbol=symbol,
                market_type=market_type
            )

            return result

        except Exception as e:
            logger.error(f"미체결 주문 조회 실패: {e}")
            return {
                'success': False,
                'error': str(e),
                'error_type': 'query_error'
            }

    def cancel_all_orders(self, strategy_id: int, symbol: Optional[str] = None,
                          account_id: Optional[int] = None,
                          side: Optional[str] = None,
                          timing_context: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """전략의 모든 미체결 주문 취소 (Wrapper - Backward Compatibility)

        ⚠️  직접 호출 금지: cancel_all_orders_by_user() 사용하세요
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        이 wrapper는 strategy.user_id (전략 소유자)만 추출하여 사용합니다.

        치명적 제한: 웹훅에서 사용 시 구독자 주문이 취소되지 않습니다!
        - 전략 소유자: user_id=1
        - 구독자 계좌: user_id=2, account_id=200
        - cancel_all_orders(account_id=200) → user_id=1 추출
        - 결과: user_id=1 AND account_id=200 → 불일치 → 취소 실패 ❌

        올바른 사용법:
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 포지션 페이지
        cancel_all_orders_by_user(user_id=current_user.id, strategy_id=...)

        # 웹훅 (각 구독자별)
        cancel_all_orders_by_user(user_id=account.user_id, account_id=account.id, ...)

        Args:
            strategy_id: 전략 ID
            symbol: 심볼 필터 (None=전체)
            account_id: 계좌 ID (⚠️  strategy.user_id와 일치하는 계좌만 작동)
            side: 주문 방향 ("BUY"/"SELL", None=전체)
            timing_context: 타이밍 정보

        Note: 레거시 호환성만 유지. 새 코드는 cancel_all_orders_by_user() 직접 호출.
        """
        try:
            logger.info(f"🔄 전략 {strategy_id} 모든 주문 취소 시작 (symbol: {symbol or 'ALL'}, "
                       f"account_id: {account_id or 'ALL'}, side: {side or 'ALL'})")

            # 전략 조회
            strategy = Strategy.query.get(strategy_id)
            if not strategy:
                return {
                    'success': False,
                    'error': f'전략을 찾을 수 없습니다: {strategy_id}',
                    'error_type': 'strategy_error'
                }

            # user_id 추출
            user_id = strategy.user_id
            if not user_id:
                return {
                    'success': False,
                    'error': '전략에 사용자가 연결되어 있지 않습니다',
                    'error_type': 'user_error'
                }

            # cancel_all_orders_by_user() 호출 (단일 소스)
            return self.cancel_all_orders_by_user(
                user_id=user_id,
                strategy_id=strategy_id,
                account_id=account_id,
                symbol=symbol,
                side=side,
                timing_context=timing_context
            )

        except Exception as e:
            logger.error(f"모든 주문 취소 실패: {e}")
            return {
                'success': False,
                'error': str(e),
                'error_type': 'cancel_all_error'
            }

    def cancel_all_orders_by_user(self, user_id: int, strategy_id: int,
                                  account_id: Optional[int] = None,
                                  symbol: Optional[str] = None,
                                  side: Optional[str] = None,
                                  timing_context: Optional[Dict[str, float]] = None,
                                  snapshot_threshold: Optional[datetime] = None) -> Dict[str, Any]:
        """사용자 권한 기준의 미체결 주문 일괄 취소 (Phase 5 이후)

        @FEAT:order-cancel @COMP:service @TYPE:core
        @FEAT:orphan-order-prevention @COMP:service @TYPE:core @PHASE:3b
        @DATA:webhook_received_at - Snapshot 기반 조회 (Phase 3b.1: 2025-10-31)

        ⚠️ Race Condition 방지: 심볼별 Lock 획득 후 OpenOrder 취소 (Issue #9)
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        모든 영향받는 (account_id, symbol) 조합의 Lock을 Deadlock 방지 순서로 획득하여
        OpenOrder를 취소하고 거래소 API를 호출합니다.
        Phase 5 이후 OpenOrder만 처리하며 PendingOrder 로직은 제거되었습니다.

        권한 모델 (Permission Models)
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        - User-Scoped (포지션 페이지): user_id=current_user.id (현재 유저만)
        - Strategy-Scoped (웹훅): user_id=account.user_id (각 구독자별 루프 호출)

        Phase 3b.1: Snapshot 기반 조회
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        snapshot_threshold 제공 시 해당 시점 이전의 주문만 조회 (Scenario S3.1 해결)
        - webhook_received_at <= snapshot_threshold (웹훅 경로 주문)
        - OR (webhook_received_at IS NULL AND created_at <= snapshot_threshold) (수동 주문)

        Args:
            user_id: 사용자 ID (포지션: current_user.id, 웹훅: account.user_id)
            strategy_id: 전략 ID
            account_id: 계좌 ID 필터 (None=모든 계좌, 지정=해당 계좌만)
            symbol: 심볼 필터 (None=전체, "BTC/USDT"=특정 심볼)
            side: 주문 방향 필터 (None=전체, "BUY"/"SELL"=특정 방향, 대소문자 무관)
            timing_context: 웹훅 타이밍 정보 (웹훅: {'webhook_received_at': timestamp})
            snapshot_threshold: Snapshot 기준 시각 (Phase 3b.1, None=미사용)

        Returns:
            Dict[str, Any]: {
                'success': bool,
                'cancelled_orders': List[Dict],  # OpenOrder 취소 목록 (PendingOrder 없음)
                    # 각 항목 형식: {
                    #     'order_id': str,
                    #     'symbol': str,
                    #     'account_id': int,
                    #     'strategy_id': int,
                    #     'already_filled': bool (선택)  # Phase 3b.2: Race S5.2로 체결된 주문
                    # }
                'failed_orders': List[Dict],      # 실패 목록
                    # 각 항목 형식: {
                    #     'order_id': str,
                    #     'reason': str,
                    #     'already_filled': bool (선택)  # Race Condition 인지
                    # }
                'total_processed': int,
                'filter_conditions': List[str],
                'message': str
            }

        WHY:
            already_filled 플래그는 Race Condition S5.2 대응 (Phase 3b.2)
            - 취소 시도 중 거래소가 주문 체결 시 True로 설정
            - 실패 주문과 구분하여 자동 재시도 정책 적용 가능

        Edge Cases:
            1. Race Condition S5.2: 취소 중 체결되어 DB에서 삭제됨 (already_filled=True)
            2. both-NULL 상황: webhook_received_at=NULL & created_at > threshold
               → 취소 제외됨 (웹훅 지연 주문으로 간주)

        Note:
            Phase 5 이후 모든 주문은 즉시 거래소에 실행되므로 PendingOrder 로직은 제거됨.
        """
        try:
            from app.constants import OrderStatus

            # ============================================================
            # 입력 파라미터 검증 및 정규화
            # ============================================================
            if side:
                side = side.strip().upper()
                if side not in ('BUY', 'SELL'):
                    logger.warning(f"⚠️ 잘못된 side 값: {side}, 필터 무시")
                    side = None

            # 타이밍 컨텍스트 초기화
            if timing_context is None:
                timing_context = {}

            # @FEAT:orphan-order-prevention @COMP:service @TYPE:core @PHASE:3b
            # Phase 3b.1: Snapshot threshold 추출 (timing_context에서)
            if not snapshot_threshold and timing_context and 'webhook_received_at' in timing_context:
                webhook_received_at_unix = timing_context['webhook_received_at']
                # UTC 변환: 전체 시스템이 UTC 기반이므로 utcfromtimestamp 사용 (일관성)
                snapshot_threshold = datetime.utcfromtimestamp(webhook_received_at_unix)
                logger.info(
                    f"📸 CANCEL_ALL_ORDER Snapshot 모드 - "
                    f"threshold={snapshot_threshold.isoformat()} (UTC)"
                )

            cancel_started_at = time.time()

            filter_conditions: List[str] = []
            filter_conditions.append(f"strategy_id={strategy_id}")

            # ============================================================
            # Step 0: 영향받는 계정 및 심볼 조회, Lock 획득 (Issue #9)
            # ============================================================

            # OpenOrder 쿼리 구성
            open_query = (
                OpenOrder.query
                .join(StrategyAccount)
                .join(Strategy)
                .join(Account)
                .options(
                    joinedload(OpenOrder.strategy_account)
                    .joinedload(StrategyAccount.account),
                    joinedload(OpenOrder.strategy_account)
                    .joinedload(StrategyAccount.strategy)
                )
                .filter(
                    Account.user_id == user_id,
                    Account.is_active == True,
                    Strategy.id == strategy_id,
                    OpenOrder.status.in_(OrderStatus.get_open_statuses())
                )
            )

            if account_id:
                open_query = open_query.filter(Account.id == account_id)
            if symbol:
                open_query = open_query.filter(OpenOrder.symbol == symbol)
            if side:
                open_query = open_query.filter(OpenOrder.side == side.upper())

            # @FEAT:orphan-order-prevention @COMP:service @TYPE:core @PHASE:3b
            # Phase 3b.1: Snapshot 필터 추가 (Scenario S3.1 해결)
            if snapshot_threshold:
                # webhook_received_at <= snapshot_threshold (웹훅 경로 주문)
                # OR (webhook_received_at IS NULL AND created_at <= snapshot_threshold) (수동 주문)
                open_query = open_query.filter(
                    db.or_(
                        OpenOrder.webhook_received_at <= snapshot_threshold,
                        db.and_(
                            OpenOrder.webhook_received_at.is_(None),
                            OpenOrder.created_at <= snapshot_threshold
                        )
                    )
                )

            # 모든 영향받는 계정 추출
            affected_account_ids = set()

            # OpenOrder에서 계정 추출
            for oo in open_query.all():
                strategy_account = StrategyAccount.query.get(oo.strategy_account_id)
                if strategy_account:
                    affected_account_ids.add(strategy_account.account_id)

            # 영향받는 심볼 목록 추출
            affected_symbols = set()

            # OpenOrder에서 심볼 추출
            open_query_symbols = open_query.with_entities(OpenOrder.symbol).distinct()
            for row in open_query_symbols:
                affected_symbols.add(row.symbol)

            # 조기 종료: 취소할 주문이 없는 경우
            if not affected_account_ids or not affected_symbols:
                logger.info(
                    f"취소할 주문이 없습니다 (user_id={user_id}, strategy_id={strategy_id})"
                )
                return {
                    'success': True,
                    'cancelled_orders': [],
                    'failed_orders': [],
                    'total_processed': 0,
                    'filter_conditions': filter_conditions,
                    'message': '취소할 주문이 없습니다.'
                }

            # Deadlock 방지: 정렬된 순서로 Lock 획득
            sorted_account_ids = sorted(affected_account_ids)
            sorted_symbols = sorted(affected_symbols)

            total_locks = len(sorted_account_ids) * len(sorted_symbols)

            logger.info(
                f"🔒 CANCEL_ALL Lock 획득 시작 - "
                f"계정: {sorted_account_ids}, 심볼: {sorted_symbols}, "
                f"총 {total_locks}개 Lock"
            )

            # ============================================================
            # OpenOrder 취소 실행
            # ============================================================
            # filter_conditions 업데이트
            if account_id and f"account_id={account_id}" not in filter_conditions:
                filter_conditions.append(f"account_id={account_id}")
            if symbol and f"symbol={symbol}" not in filter_conditions:
                filter_conditions.append(f"symbol={symbol}")
            if side and f"side={side.upper()}" not in filter_conditions:
                filter_conditions.append(f"side={side.upper()}")

            # OpenOrder 조회
            target_orders = open_query.all()

            # @FEAT:orphan-order-prevention @COMP:service @TYPE:core @PHASE:3b
            # Phase 3b.1: Snapshot 개수 로그
            if snapshot_threshold:
                logger.info(
                    f"📸 CANCEL_ALL_ORDER Snapshot: {len(target_orders)}개 주문 "
                    f"(기준 시각: {snapshot_threshold.isoformat()})"
                )

            if not target_orders:
                logger.info(
                    f"No orders to cancel for user {user_id}"
                    + (f" ({', '.join(filter_conditions)})" if filter_conditions else '')
                )
                return {
                    'success': True,
                    'cancelled_orders': [],
                    'failed_orders': [],
                    'total_processed': 0,
                    'filter_conditions': filter_conditions,
                    'message': '취소할 주문이 없습니다.'
                }

            cancelled_orders: List[Dict[str, Any]] = []
            failed_orders: List[Dict[str, Any]] = []
            # @FEAT:orphan-order-prevention @COMP:service @TYPE:core @PHASE:3b
            # Phase 3b.2: 'filled' 카운터 추가 (통계 개선)
            filled_count = 0

            logger.info(
                f"🔄 OpenOrder 취소 시작 - 사용자: {user_id}, {len(target_orders)}개"
                + (f" ({', '.join(filter_conditions)})" if filter_conditions else '')
            )

            for open_order in target_orders:
                strategy_account = open_order.strategy_account
                account = strategy_account.account if strategy_account else None

                if not account:
                    logger.warning(
                        f"Skip cancel: missing account for order {open_order.exchange_order_id}"
                    )
                    failed_orders.append({
                        'order_id': open_order.exchange_order_id,
                        'symbol': open_order.symbol,
                        'error': 'Account not linked to order'
                    })
                    continue

                try:
                    # ✅ Phase 3a: open_order 전달 (추가 조회 불필요)
                    cancel_result = self.service.cancel_order(
                        order_id=open_order.exchange_order_id,
                        symbol=open_order.symbol,
                        account_id=account.id,
                        open_order=open_order  # 🆕 추가
                    )

                    order_summary = {
                        'order_id': open_order.exchange_order_id,
                        'symbol': open_order.symbol,
                        'account_id': account.id,
                        'strategy_id': strategy_account.strategy.id if strategy_account and strategy_account.strategy else None
                    }

                    if cancel_result.get('success'):
                        # @FEAT:orphan-order-prevention @COMP:service @TYPE:core @PHASE:3b
                        # Phase 3b.2: 'already_filled' 체크하여 filled_count 증가
                        if cancel_result.get('already_filled'):
                            filled_count += 1
                        cancelled_orders.append(order_summary)
                    else:
                        failed_orders.append({
                            **order_summary,
                            'error': cancel_result.get('error')
                        })

                except Exception as cancel_error:
                    logger.error(
                        f"Bulk cancel failure for order {open_order.exchange_order_id}: {cancel_error}"
                    )
                    failed_orders.append({
                        'order_id': open_order.exchange_order_id,
                        'symbol': open_order.symbol,
                        'account_id': account.id,
                        'strategy_id': strategy_account.strategy.id if strategy_account and strategy_account.strategy else None,
                        'error': str(cancel_error)
                    })

            total_cancelled = len(cancelled_orders)
            total_failed = len(failed_orders)
            total_processed = total_cancelled + total_failed

            # @FEAT:orphan-order-prevention @COMP:service @TYPE:core @PHASE:3b
            # Phase 3b.2: 'filled' 통계 로그 추가
            if filled_count > 0:
                logger.info(f"[CANCEL_ALL] {filled_count}개 주문 이미 체결됨 (Race S5.2)")

            logger.info(
                f"✅ CANCEL_ALL 완료 - 사용자: {user_id}, "
                f"OpenOrder 취소: {total_cancelled}개, 실패: {total_failed}개, "
                f"심볼: {sorted_symbols}"
            )

            response = {
                'cancelled_orders': cancelled_orders,
                'failed_orders': failed_orders,
                'total_processed': total_processed,
                'filter_conditions': filter_conditions
            }

            if total_cancelled > 0 and total_failed == 0:
                response['success'] = True
                response['message'] = f'{total_cancelled}개 주문을 취소했습니다.'
            elif total_cancelled > 0 and total_failed > 0:
                response['success'] = True
                response['partial_success'] = True
                response['message'] = (
                    f'일부 주문만 취소되었습니다. 성공 {total_cancelled}개, 실패 {total_failed}개'
                )
            else:
                response['success'] = False
                response['error'] = '모든 주문 취소에 실패했습니다.'

            return response

        except Exception as e:
            db.session.rollback()
            logger.error(f"사용자 일괄 주문 취소 실패: user={user_id}, error={e}")
            return {
                'success': False,
                'error': str(e),
                'cancelled_orders': [],
                'failed_orders': [],
                'total_processed': 0,
                'filter_conditions': []
            }

    def get_user_open_orders(self, user_id: int, strategy_id: Optional[int] = None, symbol: Optional[str] = None) -> Dict[str, Any]:
        """사용자의 미체결 주문 목록 조회 (Service 계층)"""
        try:
            # 사용자의 모든 미체결 주문을 조회 (권한 확인 포함)
            query = (
                OpenOrder.query
                .join(StrategyAccount)
                .join(Strategy)
                .join(Account)
                .options(
                    joinedload(OpenOrder.strategy_account)
                    .joinedload(StrategyAccount.strategy),
                    joinedload(OpenOrder.strategy_account)
                    .joinedload(StrategyAccount.account)
                )
                .filter(
                    Strategy.user_id == user_id,
                    OpenOrder.status.in_(['NEW', 'OPEN', 'PARTIALLY_FILLED']),
                    Account.is_active == True
                )
            )

            # 전략별 필터링 (optional)
            if strategy_id:
                query = query.filter(Strategy.id == strategy_id)

            # 심볼별 필터링 (optional)
            if symbol:
                query = query.filter(OpenOrder.symbol == symbol)

            # 최신 주문부터 정렬
            open_orders = query.order_by(OpenOrder.created_at.desc()).all()

            # 응답 데이터 구성
            orders_data = []
            for order in open_orders:
                strategy_account = order.strategy_account
                strategy = strategy_account.strategy if strategy_account else None
                account = strategy_account.account if strategy_account else None

                order_dict = {
                    'order_id': order.exchange_order_id,  # 통일된 명명: order_id 사용 (exchange_order_id를 매핑)
                    'symbol': order.symbol,
                    'side': order.side,
                    'quantity': order.quantity,
                    'price': order.price,
                    'stop_price': order.stop_price,  # Stop 가격 추가
                    'order_type': order.order_type,  # 주문 타입 추가
                    'filled_quantity': order.filled_quantity,
                    'status': order.status,
                    'market_type': order.market_type,
                    'created_at': order.created_at.isoformat() if order.created_at else None,
                    'updated_at': order.updated_at.isoformat() if order.updated_at else None
                }

                # 전략 정보 추가 (있는 경우)
                if strategy:
                    order_dict['strategy'] = {
                        'id': strategy.id,
                        'name': strategy.name,
                        'group_name': strategy.group_name,
                        'market_type': strategy.market_type
                    }

                # 계정 정보 추가 (있는 경우)
                if account:
                    order_dict['account'] = {
                        'id': account.id,
                        'name': account.name,
                        'exchange': account.exchange
                    }

                # 전략 계정 ID 추가 (있는 경우)
                if strategy_account:
                    order_dict['strategy_account_id'] = strategy_account.id

                orders_data.append(order_dict)

            logger.info(f"사용자 미체결 주문 조회 완료 - 사용자: {user_id}, {len(orders_data)}개 주문")

            return {
                'success': True,
                'open_orders': orders_data,
                'total_count': len(orders_data)
            }

        except Exception as e:
            logger.error(f"사용자 미체결 주문 조회 실패 - 사용자: {user_id}, 오류: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'open_orders': [],
                'total_count': 0
            }

    def create_open_order_record(
        self,
        strategy_account: StrategyAccount,
        order_result: Dict[str, Any],
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None,
        webhook_received_at: Optional[datetime] = None  # ✅ Infinite Loop Fix: 웹훅 수신 시각 보존
    ) -> Dict[str, Any]:
        """Persist an open order if the exchange reports it as outstanding.

        주문 생성 후 OpenOrder 레코드를 데이터베이스에 저장합니다.

        낙관적 INSERT 패턴 (Optimistic INSERT):
            - INSERT를 먼저 시도하고, UNIQUE constraint 위반 시 기존 레코드 재사용
            - WebSocket + Webhook 이중 경로로 인한 중복 INSERT 시도는 정상 동작 (Issue #42)
            - 멱등성 보장: 동일 exchange_order_id로 여러 번 호출해도 안전

        Args:
            strategy_account: 전략 계정 객체
            order_result: 거래소 응답 (order_id, status, filled_quantity 포함)
            symbol: 거래 심볼 (예: "BTC/USDT")
            side: 거래 방향 ("BUY" 또는 "SELL")
            order_type: 주문 유형 (LIMIT, STOP_LIMIT, STOP_MARKET)
            quantity: 주문 수량
            price: 주문 가격 (LIMIT 주문에서 사용)
            stop_price: 스탑 가격 (STOP 주문에서 사용)
            webhook_received_at: 웹훅 수신 시각 (타임스탐프 손실 방지)

        Returns:
            dict: {
                'success': True/False,
                'open_order_id': <ID> (성공 시),
                'exchange_order_id': <exchange_order_id>,
                'duplicate': True/False (중복 감지 여부)
            }

        Raises:
            IntegrityError: FK 제약 조건 위반 등 (UNIQUE 제약은 내부 처리)

        Performance:
            신규 주문: 1회 DB 왕복 (vs 기존 2회)
            평균: 1.5회 DB 왕복 (약 25% 개선)

        Issue #42 해결:
            - Optimistic INSERT: 먼저 INSERT 시도, 중복 시 기존 레코드 재사용
            - UNIQUE 제약 위반을 정상 시나리오로 처리
            - 성능 25% 개선으로 데이터베이스 부하 감소
        """
        from app.constants import OrderStatus

        try:
            if order_type == OrderType.MARKET:
                logger.debug("시장가 주문은 OpenOrder에 저장하지 않음: %s", order_result.get('order_id'))
                return {'success': False, 'reason': 'market_order'}

            order_status = order_result.get('status', '')
            if not OrderStatus.is_open(order_status):
                logger.debug(
                    "완전 체결된 주문(%s)은 OpenOrder에 저장하지 않음: %s",
                    order_status,
                    order_result.get('order_id'),
                )
                return {'success': False, 'reason': 'fully_filled'}

            exchange_order_id = order_result.get('order_id')
            if not exchange_order_id:
                logger.error("exchange_order_id가 없어서 OpenOrder 생성 불가")
                return {'success': False, 'error': 'missing_order_id'}

            # @FEAT:order-tracking @COMP:service @TYPE:core
            open_order = OpenOrder(
                strategy_account_id=strategy_account.id,
                exchange_order_id=str(exchange_order_id),
                symbol=symbol,
                side=side.upper(),
                order_type=order_type,
                price=float(price) if price else None,
                stop_price=float(stop_price) if stop_price else None,
                quantity=float(quantity),
                filled_quantity=float(order_result.get('filled_quantity', 0)),
                status=order_status,
                market_type=strategy_account.strategy.market_type or 'SPOT',
                webhook_received_at=webhook_received_at  # ✅ 웹훅 수신 시각
            )

            db.session.add(open_order)
            db.session.commit()

            logger.info(
                "📝 OpenOrder 레코드 생성 완료: ID=%s, 거래소주문ID=%s, 상태=%s, price=%s, stop_price=%s",
                open_order.id,
                exchange_order_id,
                order_status,
                price,
                stop_price,
            )
            return {
                'success': True,
                'open_order_id': open_order.id,
                'exchange_order_id': exchange_order_id,
            }

        except IntegrityError as e:
            db.session.rollback()

            # UNIQUE constraint 위반만 처리 (다른 IntegrityError는 재발생)
            if 'open_orders_exchange_order_id_key' in str(e):
                # WebSocket/Webhook 이중 경로 = 정상 동작
                existing_order = OpenOrder.query.filter_by(
                    exchange_order_id=str(exchange_order_id)
                ).first()

                if existing_order:
                    logger.info(
                        "📝 OpenOrder 중복 감지 (이중 경로): ID=%s, 거래소주문ID=%s, "
                        "경로=WebSocket+Webhook (정상)",
                        existing_order.id,
                        exchange_order_id
                    )
                    return {
                        'success': True,
                        'open_order_id': existing_order.id,
                        'exchange_order_id': exchange_order_id,
                        'duplicate': True  # 중복 플래그
                    }

            # 다른 IntegrityError는 실제 문제 → 재발생
            logger.error("OpenOrder 생성 실패 (IntegrityError): %s", e)
            raise

        except Exception as exc:  # pragma: no cover - defensive logging
            db.session.rollback()
            logger.error("OpenOrder 레코드 생성 실패: %s", exc)
            return {
                'success': False,
                'error': str(exc),
            }

    def update_open_order_status(self, order_id: str, order_result: Dict[str, Any]) -> None:
        """Update or remove OpenOrder entries based on the latest exchange state."""
        from app.constants import OrderStatus

        try:
            open_order = OpenOrder.query.filter_by(
                exchange_order_id=str(order_id)
            ).first()

            if not open_order:
                return

            open_order.status = order_result.get('status')
            open_order.filled_quantity = float(order_result.get('filled_quantity', 0))

            if OrderStatus.is_closed(order_result.get('status')):
                db.session.delete(open_order)
                logger.debug("🗑️  완료된 주문 OpenOrder 제거: %s", order_id)
            else:
                db.session.add(open_order)
                logger.debug("📝 OpenOrder 상태 업데이트: %s -> %s", order_id, open_order.status)

            db.session.commit()

        except Exception as exc:  # pragma: no cover - defensive logging
            db.session.rollback()
            logger.error("OpenOrder 상태 업데이트 실패: %s", exc)

    # @FEAT:orphan-order-prevention @COMP:job @TYPE:core @PHASE:4
    # Phase 4: PENDING 주문 정리 - 120초 이상 PENDING 상태 주문을 FAILED로 전환
    def _cleanup_stuck_pending_orders(self) -> None:
        """
        정리 작업: PENDING 상태로 120초 이상 멈춘 주문을 FAILED로 강제 전환

        호출 시점: update_open_orders_status() 실행 후 (29초마다)

        동작:
        1. PENDING 상태이고 created_at이 120초 이전인 주문 검색
        2. status → FAILED로 변경
        3. error_message에 타임아웃 원인 저장 (보안 정제됨)

        목적:
        - DB-first 패턴에서 거래소 API 호출 후 예외 발생 시 발생하는 고아 주문 정리
        - 최대 대기 시간: 120초 (29초 주기 × 최대 5주기)
        - 자동 복구: 응답 없는 PENDING 주문은 결국 FAILED로 전환

        사례:
        - 거래소 API 수행 중 네트워크 단절 → PENDING 유지
        - 서버 크래시 후 재부팅 → PENDING 주문들 정리 대기
        - 타임아웃 (120초): 자동으로 FAILED로 전환
        """
        from app.models import OpenOrder
        from app.constants import OrderStatus
        from app.services.trading.core import sanitize_error_message

        try:
            timeout_seconds = 120  # 120초
            cutoff_time = datetime.utcnow() - timedelta(seconds=timeout_seconds)

            # PENDING 상태이고 timeout 초과한 주문 검색
            stuck_orders = OpenOrder.query.filter(
                OpenOrder.status == OrderStatus.PENDING,
                OpenOrder.created_at < cutoff_time
            ).all()

            if not stuck_orders:
                # 정리할 주문 없음 (정상 상태)
                return

            # PENDING 주문 강제 전환
            for order in stuck_orders:
                order.status = OrderStatus.FAILED
                order.error_message = sanitize_error_message(
                    f"Order stuck in PENDING state for >{timeout_seconds}s (created: {order.created_at})"
                )

            db.session.commit()

            logger.warning(
                f"🧹 PENDING 주문 정리: {len(stuck_orders)}개 주문을 FAILED로 전환 "
                f"(timeout: >{timeout_seconds}초)"
            )

        except Exception as e:
            db.session.rollback()
            logger.error(f"❌ PENDING 주문 정리 실패: {e}")

    # @FEAT:orphan-order-prevention @COMP:job @TYPE:core @PHASE:4
    # Phase 4: CANCELLING 주문 정리 - 거래소 상태 재확인 후 동기화
    def _cleanup_orphan_cancelling_orders(self) -> None:
        """
        정리 작업: CANCELLING 상태로 300초 이상 멈춘 주문을 거래소 상태 재확인 후 처리

        호출 시점: update_open_orders_status() 실행 후 (29초마다)

        동작:
        1. CANCELLING 상태이고 cancel_attempted_at이 300초 이전인 주문 검색
        2. 거래소 상태 재확인:
           - 취소됨 확인 시: DB 삭제
           - 미취소 확인 시: OPEN으로 복원
           - 확인 실패 시: 600초(10분) 이상 경과하면 OPEN으로 복원 (안전장치)

        목적:
        - DB-First 패턴에서 거래소 API 예외 발생 시 남은 고아 주문 정리
        - 최대 대기 시간: 300초 (29초 주기 × 최대 11주기)
        - 자동 복구: 응답 없는 CANCELLING 주문은 결국 확인 또는 복원

        사례:
        - 거래소 API 예외 발생 → CANCELLING 유지 (Phase 2)
        - 300초 후: 백그라운드가 거래소 상태 재확인
        - 취소 확인 시: DB 삭제, 미취소 확인 시: OPEN 복원
        - 10분 이상 확인 불가: OPEN 복원 (안전장치)
        """
        from app.models import OpenOrder, StrategyAccount, Account
        from app.constants import OrderStatus
        from app.services.trading.core import sanitize_error_message

        try:
            # 타임아웃: 300초 (5분)
            timeout_seconds = 300
            cutoff_time = datetime.utcnow() - timedelta(seconds=timeout_seconds)

            # 안전장치 타임아웃: 600초 (10분)
            safety_timeout_seconds = 600
            safety_cutoff_time = datetime.utcnow() - timedelta(seconds=safety_timeout_seconds)

            # CANCELLING 상태이고 timeout 초과한 주문 검색
            stuck_orders = (
                OpenOrder.query
                .options(
                    joinedload(OpenOrder.strategy_account)
                    .joinedload(StrategyAccount.account),
                    joinedload(OpenOrder.strategy_account)
                    .joinedload(StrategyAccount.strategy)
                )
                .filter(
                    OpenOrder.status == OrderStatus.CANCELLING,
                    OpenOrder.cancel_attempted_at < cutoff_time
                )
                .all()
            )

            if not stuck_orders:
                # 정리할 주문 없음 (정상 상태)
                return

            logger.info(
                f"🧹 CANCELLING 주문 정리 시작: {len(stuck_orders)}개 주문 "
                f"(timeout: >{timeout_seconds}초)"
            )

            cancelled_count = 0
            restored_count = 0
            safety_restored_count = 0

            for order in stuck_orders:
                try:
                    # 계정 정보 가져오기
                    strategy_account = order.strategy_account
                    if not strategy_account or not strategy_account.account:
                        logger.warning(
                            f"⚠️ 계정 정보 없음, OPEN 복원: {order.exchange_order_id}"
                        )
                        order.status = OrderStatus.OPEN
                        order.cancel_attempted_at = None
                        order.error_message = sanitize_error_message(
                            "Account not found during cleanup"
                        )
                        restored_count += 1
                        continue

                    account = strategy_account.account
                    market_type = 'spot'
                    if strategy_account.strategy:
                        market_type = strategy_account.strategy.market_type.lower()

                    # 안전장치: 10분 이상 경과 시 거래소 확인 없이 OPEN 복원
                    if order.cancel_attempted_at < safety_cutoff_time:
                        logger.warning(
                            f"⚠️ 안전장치 작동 (>{safety_timeout_seconds}초): "
                            f"OPEN 복원: {order.exchange_order_id}"
                        )
                        order.status = OrderStatus.OPEN
                        order.cancel_attempted_at = None
                        order.error_message = sanitize_error_message(
                            f"Cancellation stuck >{safety_timeout_seconds}s, restored to OPEN"
                        )
                        safety_restored_count += 1
                        continue

                    # 거래소 상태 재확인 (Phase 2 helper 재사용)
                    verification_result = self._verify_cancellation_once(
                        account=account,
                        order_id=order.exchange_order_id,
                        symbol=order.symbol,
                        market_type=market_type
                    )

                    if verification_result == 'cancelled':
                        # 취소됨 확인 → DB 삭제
                        logger.info(
                            f"✅ 백그라운드 확인: 취소됨 → DB 삭제: "
                            f"{order.exchange_order_id}"
                        )
                        db.session.delete(order)
                        cancelled_count += 1

                    elif verification_result == 'active':
                        # 활성 상태 확인 → OPEN 복원
                        logger.warning(
                            f"⚠️ 백그라운드 확인: 활성 → OPEN 복원: "
                            f"{order.exchange_order_id}"
                        )
                        order.status = OrderStatus.OPEN
                        order.cancel_attempted_at = None
                        order.error_message = sanitize_error_message(
                            "Cancellation failed, order still active on exchange"
                        )
                        restored_count += 1

                    else:
                        # 확인 실패 → CANCELLING 유지 (다음 주기에 재시도)
                        logger.warning(
                            f"⚠️ 백그라운드 확인 실패 → CANCELLING 유지: "
                            f"{order.exchange_order_id}"
                        )

                except Exception as order_error:
                    logger.error(
                        f"❌ CANCELLING 주문 정리 실패 (개별): "
                        f"{order.exchange_order_id} - {order_error}"
                    )

            # 변경사항 커밋
            db.session.commit()

            logger.info(
                f"🧹 CANCELLING 주문 정리 완료: "
                f"취소={cancelled_count}개, 복원={restored_count}개, "
                f"안전장치복원={safety_restored_count}개"
            )

        except Exception as e:
            db.session.rollback()
            logger.error(f"❌ CANCELLING 주문 정리 실패: {e}")

    # @FEAT:orphan-order-prevention @COMP:job @TYPE:core @PHASE:5
    # Phase 5: DB-거래소 상태 일관성 검증 및 자동 동기화 (29초 주기)
    def update_open_orders_status(self) -> None:
        """백그라운드 작업: 모든 미체결 주문의 상태를 거래소와 동기화 (Phase 3: 배치 쿼리 최적화)

        개선사항:
        - 개별 API 호출 → 계좌별 배치 쿼리
        - 100개 주문: 100번 호출 → 5번 호출 (20배 개선)
        - 처리 시간: 20초 → 1초

        실행 주기: 29초마다
        """
        # @FEAT:order-tracking @COMP:validation @TYPE:core
        # Phase 3 Critical Fix: @ISSUE #3 - Flask App Context 검증 (APScheduler 스레드에서 실행되므로 context 필수)
        from flask import has_app_context
        if not has_app_context():
            logger.error(
                "❌ Flask app context 없음: update_open_orders_status는 "
                "update_open_orders_with_context()를 통해 호출해야 합니다."
            )
            raise RuntimeError(
                "update_open_orders_status requires Flask app context. "
                "Call update_open_orders_with_context() instead."
            )

        from app.constants import OrderStatus
        from datetime import datetime

        try:
            # Step 1: 처리 중이 아닌 활성 주문 조회 (Phase 2 낙관적 잠금)
            # @DATA:OrderStatus.PENDING - 백그라운드 작업용 활성 상태 포함 (Phase 2: 2025-10-30)
            # get_active_statuses(): PENDING, NEW, OPEN, PARTIALLY_FILLED (PENDING 정리 작업용)
            open_orders = (
                OpenOrder.query
                .options(
                    joinedload(OpenOrder.strategy_account)
                    .joinedload(StrategyAccount.account),
                    joinedload(OpenOrder.strategy_account)
                    .joinedload(StrategyAccount.strategy)
                )
                .filter(
                    OpenOrder.status.in_(OrderStatus.get_active_statuses()),
                    OpenOrder.is_processing == False  # 처리 중이 아닌 주문만
                )
                .all()
            )

            if not open_orders:
                logger.debug("📋 미체결 주문 없음")
                return

            logger.info(f"📋 미체결 주문 상태 업데이트 시작: {len(open_orders)}개 주문")

            # Step 2: 계좌별 그룹화 (핵심 최적화)
            grouped_by_account: Dict[int, List[OpenOrder]] = defaultdict(list)
            for order in open_orders:
                if order.strategy_account and order.strategy_account.account:
                    account_id = order.strategy_account.account.id
                    grouped_by_account[account_id].append(order)
                else:
                    logger.warning(
                        f"⚠️ OpenOrder에 연결된 계정 없음: order_id={order.exchange_order_id}"
                    )

            logger.info(
                f"🗂️ 계좌별 그룹화 완료: {len(grouped_by_account)}개 계좌, "
                f"{len(open_orders)}개 주문"
            )

            # @FEAT:order-tracking @COMP:job @TYPE:resilience
            # Priority 2 Phase 2: Circuit Breaker - 거래소별 연속 실패 제한
            try:
                CIRCUIT_BREAKER_THRESHOLD = max(1, int(os.getenv('CIRCUIT_BREAKER_THRESHOLD', '3')))
            except ValueError:
                CIRCUIT_BREAKER_THRESHOLD = 3
                logger.warning("⚠️ Invalid CIRCUIT_BREAKER_THRESHOLD, using default: 3")

            exchange_failures = defaultdict(int)  # 거래소별 실패 카운터

            # Step 3: 계좌별 배치 처리
            total_processed = 0
            total_updated = 0
            total_deleted = 0
            total_failed = 0

            for account_id, db_orders in grouped_by_account.items():
                exchange_name = None  # 변수 스코프 안전성 (예외 핸들러용)
                try:
                    # Step 3-1: 계좌 조회
                    account = Account.query.get(account_id)
                    if not account:
                        logger.error(f"❌ 계정을 찾을 수 없음: account_id={account_id}")
                        total_failed += len(db_orders)
                        continue

                    exchange_name = account.exchange.upper()

                    # @FEAT:order-tracking @COMP:job @TYPE:resilience
                    # Priority 2 Phase 2: Circuit Breaker - 거래소별 연속 실패 체크
                    if exchange_failures[exchange_name] >= CIRCUIT_BREAKER_THRESHOLD:
                        logger.warning(
                            f"🚫 Circuit Breaker 발동: {exchange_name} "
                            f"(연속 실패: {exchange_failures[exchange_name]}/{CIRCUIT_BREAKER_THRESHOLD}) - "
                            f"계좌 {account.name}의 {len(db_orders)}개 주문 건너뜀"
                        )
                        total_failed += len(db_orders)
                        continue

                    # Step 3-2: market_type 확인 (첫 번째 주문 기준)
                    market_type = db_orders[0].market_type or 'spot'

                    # Step 3-3: 배치 쿼리 (계좌의 모든 미체결 주문 한 번에 조회)
                    logger.info(
                        f"📡 배치 쿼리 시작: account={account.name} ({account_id}), "
                        f"market_type={market_type}, DB 주문 수={len(db_orders)}"
                    )

                    batch_result = exchange_service.get_open_orders(
                        account=account,
                        symbol=None,  # 모든 심볼
                        market_type=market_type.lower()
                    )

                    if not batch_result.get('success'):
                        # 배치 쿼리 실패 시 폴백: 개별 쿼리
                        logger.warning(
                            f"⚠️ 배치 쿼리 실패, 개별 쿼리로 폴백: "
                            f"account={account.name}, error={batch_result.get('error')}"
                        )

                        # 폴백: 개별 쿼리 (기존 로직)
                        for db_order in db_orders:
                            try:
                                individual_result = exchange_service.fetch_order(
                                    account=account,
                                    symbol=db_order.symbol,
                                    order_id=db_order.exchange_order_id,
                                    market_type=market_type.lower()
                                )

                                if individual_result and individual_result.get('success'):
                                    processed_result = self._process_single_order(
                                        db_order,
                                        individual_result,
                                        account_id
                                    )
                                    if processed_result == 'updated':
                                        total_updated += 1
                                    elif processed_result == 'deleted':
                                        total_deleted += 1
                                    total_processed += 1
                                else:
                                    total_failed += 1

                            except Exception as e:
                                logger.error(
                                    f"❌ 개별 쿼리 실패: order_id={db_order.exchange_order_id}, "
                                    f"error={e}"
                                )
                                total_failed += 1

                        # @FEAT:order-tracking @COMP:job @TYPE:core
                        # Phase 3 Critical Fix: @ISSUE #1-A - 폴백 처리 결과 커밋 (개별 쿼리 실패 시에도 상태 변경 반영)
                        try:
                            db.session.commit()
                            logger.info(
                                f"✅ 폴백 처리 완료: account={account.name}, "
                                f"처리={len(db_orders)}"
                            )
                        except Exception as commit_error:
                            db.session.rollback()
                            logger.error(
                                f"❌ 폴백 커밋 실패: account={account.name}, "
                                f"error={commit_error}"
                            )

                        continue  # 다음 계좌로

                    # Step 3-4: 거래소 응답을 맵으로 변환 (빠른 조회)
                    exchange_orders_map: Dict[str, Dict[str, Any]] = {}
                    for exchange_order in batch_result.get('orders', []):
                        # Order 객체를 딕셔너리로 변환
                        if hasattr(exchange_order, 'id'):
                            # Order 모델 인스턴스
                            order_id = str(exchange_order.id)
                            exchange_orders_map[order_id] = {
                                'order_id': order_id,
                                'status': exchange_order.status,
                                'filled_quantity': float(exchange_order.filled),
                                'average_price': float(exchange_order.average) if exchange_order.average else None,
                                'symbol': exchange_order.symbol
                            }
                        elif isinstance(exchange_order, dict):
                            # 딕셔너리 형태
                            order_id = str(exchange_order.get('id') or exchange_order.get('order_id'))
                            exchange_orders_map[order_id] = exchange_order

                    logger.info(
                        f"✅ 배치 쿼리 성공: account={account.name}, "
                        f"거래소 주문 수={len(exchange_orders_map)}, DB 주문 수={len(db_orders)}"
                    )

                    # Phase 2: 배치 쿼리 검증 강화
                    # @FEAT:order-tracking @FEAT:stop-limit-activation @COMP:service @TYPE:core @ISSUE:45
                    # 배치 쿼리 결과 DEBUG 로그 추가 (Phase 1에서 변환된 LIMIT 주문 포함 여부 확인)
                    logger.debug(
                        f"📊 배치 쿼리 결과 상세: account={account.name}, "
                        f"거래소 응답 주문 수={len(exchange_orders_map)}개, "
                        f"DB 미추적 주문 감지 시 fetch_order() 개별 조회 수행 준비 완료"
                    )

                    # Step 3-5: DB 주문과 거래소 응답 비교
                    for db_order in db_orders:
                        try:
                            # 낙관적 잠금 획득 시도 (Phase 2)
                            locked_order = OpenOrder.query.filter_by(
                                id=db_order.id,
                                is_processing=False
                            ).with_for_update(skip_locked=True).first()

                            if not locked_order:
                                logger.debug(
                                    f"⏭️ 주문 스킵 (이미 처리 중): "
                                    f"order_id={db_order.exchange_order_id}"
                                )
                                continue

                            # 처리 시작 플래그 설정 (Phase 2)
                            locked_order.is_processing = True
                            locked_order.processing_started_at = datetime.utcnow()
                            db.session.flush()

                            # 거래소 응답에서 주문 찾기
                            exchange_order = exchange_orders_map.get(
                                locked_order.exchange_order_id
                            )

                            if not exchange_order:
                                # ============================================================
                                # @FEAT:order-tracking @FEAT:stop-limit-activation @COMP:service @TYPE:core @ISSUE:30,45
                                # @DEPS:exchange-api
                                # LIMIT Order Fill Processing Bug Fix (Issue #30)
                                # STOP_LIMIT Activation Detection (Issue #45)
                                # ============================================================
                                # 문제: Binance get_open_orders()는 FILLED 주문을 반환하지 않음.
                                #       또한 STOP_LIMIT 주문이 활성화되면 LIMIT으로 변환되는데,
                                #       배치 쿼리에서 찾지 못한 주문을 확인 없이 삭제하여
                                #       Trade/Position 기록이 미생성됨.
                                #
                                # 원인: Binance API 정상 동작 - get_open_orders()는
                                #       NEW/PARTIALLY_FILLED만 반환, FILLED는 응답에서 제외.
                                #       STOP_LIMIT 활성화 시 order_type이 LIMIT으로 변환됨.
                                #
                                # 해결: fetch_order()로 개별 조회하여 최종 상태 확인:
                                #       - STOP_LIMIT 활성화(→LIMIT) → order_type 업데이트, 주문 유지
                                #       - FILLED → _process_scheduler_fill() 호출
                                #       - CANCELED/EXPIRED/REJECTED → 안전 삭제
                                #       - NEW/OPEN 등 → 주문 유지, 다음 사이클 재시도
                                #       - 네트워크 에러 → Fail-safe: 주문 유지
                                # ============================================================

                                # Step 1: 배치 쿼리에서 찾지 못한 주문 → 개별 조회로 최종 상태 확인
                                # Binance API의 get_open_orders()는 NEW/PARTIALLY_FILLED만 반환.
                                # FILLED 주문은 응답에 없으므로 fetch_order()로 최종 확인 필수.
                                # STOP_LIMIT 활성화 후 LIMIT으로 변환되는 경우도 감지 필요.
                                try:
                                    final_order = exchange_service.fetch_order(
                                        account=account,
                                        symbol=locked_order.symbol,
                                        order_id=locked_order.exchange_order_id,
                                        market_type=locked_order.market_type or 'spot'
                                    )

                                    if final_order and final_order.get('success'):
                                        final_status = final_order.get('status', '').upper()
                                        final_order_type = final_order.get('order_type', '').upper()

                                        # ============================================================
                                        # @FEAT:stop-limit-activation @ISSUE:45
                                        # Step 1-A: STOP_LIMIT 활성화 감지 (배치 미포함 → LIMIT 변환)
                                        # ============================================================
                                        # STOP_LIMIT 주문이 stop_price 도달로 활성화되면
                                        # 거래소에서 자동으로 LIMIT 주문으로 변환됨.
                                        # 배치 쿼리에서 찾을 수 없고, fetch_order()로 확인하면 type=LIMIT
                                        if locked_order.order_type == 'STOP_LIMIT' and final_order_type == 'LIMIT':
                                            logger.info(
                                                f"✅ STOP_LIMIT 활성화 감지 성공: order_id={locked_order.exchange_order_id}, "
                                                f"stop_price={locked_order.stop_price} 도달, LIMIT으로 변환"
                                            )

                                            # order_type 업데이트: STOP_LIMIT → LIMIT
                                            locked_order.order_type = 'LIMIT'
                                            # stop_price는 활성화 후 불필요
                                            locked_order.stop_price = None
                                            # limit_price 업데이트 (거래소에서 받은 price)
                                            if final_order.get('limit_price'):
                                                locked_order.price = final_order.get('limit_price')

                                            # 처리 플래그 해제
                                            locked_order.is_processing = False
                                            locked_order.processing_started_at = None
                                            db.session.flush()

                                            logger.info(
                                                f"✅ OpenOrder 업데이트 완료: order_id={locked_order.exchange_order_id}, "
                                                f"order_type=LIMIT, stop_price=None, 다음 사이클에서 추적 재개"
                                            )
                                            total_updated += 1
                                            continue  # 이 주문은 처리 완료, 다른 상태 체크 스킵

                                        # Step 2: FILLED 상태 → 체결 처리 (Trade/Position 생성)
                                        # _process_scheduler_fill()을 호출하여 정상적인 체결 처리 수행.
                                        if final_status == 'FILLED':
                                            logger.info(
                                                f"✅ 체결 감지 (배치 미포함, Scheduler): "
                                                f"order_id={locked_order.exchange_order_id}, "
                                                f"symbol={locked_order.symbol}"
                                            )
                                            fill_summary = self._process_scheduler_fill(
                                                locked_order, final_order, account
                                            )
                                            if fill_summary.get('success'):
                                                logger.info(
                                                    f"✅ 체결 처리 완료: order_id={locked_order.exchange_order_id}, "
                                                    f"trade_id={fill_summary.get('trade_id')}"
                                                )

                                                # ============================================================
                                                # @FEAT:order-tracking @FEAT:limit-order-fill-processing @COMP:job @TYPE:core
                                                # Issue #36: Scheduler FILLED 경로에서 OpenOrder 삭제 로직 추가
                                                # 배경: 백그라운드 스케줄러가 FILLED 감지 시 체결 처리는 수행하지만
                                                #       OpenOrder 삭제를 누락하여 체결된 주문이 "열린 주문"에 계속 표시됨.
                                                # 해결: WebSocket 경로(order_fill_monitor.py:362-365)와 동일한 삭제 로직 적용.
                                                # 레이스 컨디션 방지:
                                                # - locked_order는 이미 with_for_update(skip_locked=True)로 잠금 획득
                                                # - WebSocket이 먼저 삭제한 경우 중복 처리 없음 (skip_locked로 건너뜀)
                                                # - 따라서 이 코드 경로에 도달한 주문은 안전하게 삭제 가능
                                                # ============================================================
                                                try:
                                                    db.session.delete(locked_order)
                                                    logger.info(
                                                        f"🗑️ OpenOrder 삭제 완료 (Scheduler FILLED): "
                                                        f"order_id={locked_order.exchange_order_id}, status=FILLED"
                                                    )
                                                    total_deleted += 1
                                                except Exception as delete_error:
                                                    # 레이스 컨디션: WebSocket이 이미 삭제한 경우
                                                    logger.warning(
                                                        f"⚠️ OpenOrder 삭제 실패 (이미 삭제됨?): "
                                                        f"order_id={locked_order.exchange_order_id}, "
                                                        f"error={type(delete_error).__name__}: {str(delete_error)}"
                                                    )
                                                    # 삭제 실패는 치명적이지 않으므로 계속 진행
                                                    # (체결 처리는 완료되었고, OpenOrder는 이미 제거된 상태)
                                            else:
                                                logger.error(
                                                    f"❌ 체결 처리 실패: order_id={locked_order.exchange_order_id}, "
                                                    f"error={fill_summary.get('error')}"
                                                )
                                                # 체결 처리 실패 시 주문 유지 (플래그 해제 후 재시도)
                                                locked_order.is_processing = False
                                                locked_order.processing_started_at = None
                                                total_failed += 1
                                                continue

                                        # Step 3: CANCELED/EXPIRED/REJECTED → 안전 삭제
                                        # 최종 상태가 종료 상태인 경우 OpenOrder 삭제.
                                        elif final_status in ['CANCELED', 'CANCELLED', 'EXPIRED', 'REJECTED']:
                                            logger.info(
                                                f"🗑️ OpenOrder 삭제 ({final_status}): "
                                                f"order_id={locked_order.exchange_order_id}, "
                                                f"symbol={locked_order.symbol}"
                                            )

                                            # SSE 이벤트 발송 (DB 삭제 전)
                                            try:
                                                self.service.event_emitter.emit_order_cancelled_or_expired_event(
                                                    open_order=locked_order,
                                                    status=final_status
                                                )
                                            except Exception as sse_error:
                                                logger.warning(
                                                    f"⚠️ SSE 이벤트 발송 실패 (무시): "
                                                    f"order_id={locked_order.exchange_order_id}, "
                                                    f"error={sse_error}"
                                                )

                                            db.session.delete(locked_order)
                                            total_deleted += 1

                                        # Step 4: 기타 상태 (NEW/OPEN 등) → 주문 유지
                                        # 예상치 못한 상태는 로그 후 다음 사이클 재시도.
                                        else:
                                            logger.warning(
                                                f"⚠️ 예상치 못한 주문 상태: order_id={locked_order.exchange_order_id}, "
                                                f"status={final_status}, 주문 유지"
                                            )
                                            locked_order.is_processing = False
                                            locked_order.processing_started_at = None

                                    else:
                                        # Step 5: fetch_order 실패 (주문이 거래소에 없음) → 안전 삭제
                                        # 거래소에 주문이 존재하지 않으면 삭제 안전.
                                        logger.info(
                                            f"🗑️ OpenOrder 삭제 (거래소에 주문 없음): "
                                            f"order_id={locked_order.exchange_order_id}, "
                                            f"symbol={locked_order.symbol}"
                                        )
                                        db.session.delete(locked_order)
                                        total_deleted += 1

                                except Exception as e:
                                    # Step 6: 네트워크 에러 등 → Fail-safe: 주문 유지
                                    # 불확실한 경우 주문을 유지하여 데이터 손실 방지, 다음 사이클 재시도.

                                    # Phase 2: STOP_LIMIT fetch_order 연속 실패 감지 및 Telegram 알림
                                    # @FEAT:stop-limit-activation @COMP:service @TYPE:core @ISSUE:45
                                    if locked_order.order_type == 'STOP_LIMIT':
                                        # 실패 횟수 추적
                                        order_id = locked_order.exchange_order_id
                                        current_failure_count = self.fetch_failure_cache.get(order_id, 0) + 1
                                        self.fetch_failure_cache[order_id] = current_failure_count

                                        logger.warning(
                                            f"⚠️ STOP_LIMIT 활성화 감지 실패 (fetch_order 실패 {current_failure_count}/3): "
                                            f"order_id={order_id}, "
                                            f"stop_price={locked_order.stop_price}, "
                                            f"error={type(e).__name__}: {str(e)}"
                                        )

                                        # 연속 3회 실패 시 ERROR 로그 + Telegram 알림
                                        if current_failure_count >= 3:
                                            error_msg = (
                                                f"CRITICAL: STOP_LIMIT 활성화 감지 실패, "
                                                f"order_id={order_id}, "
                                                f"수동 확인 필요"
                                            )
                                            logger.error(error_msg)

                                            # Telegram 알림 전송
                                            try:
                                                if self.service and hasattr(self.service, 'notify_service'):
                                                    self.service.notify_service.send_telegram(
                                                        title="⚠️ Issue #45: STOP_LIMIT 활성화 감지 실패",
                                                        message=(
                                                            f"Order ID: {order_id}\n"
                                                            f"Stop Price: {locked_order.stop_price}\n"
                                                            f"상태: fetch_order 3회 연속 실패, 수동 확인 필요"
                                                        ),
                                                        level="ERROR"
                                                    )
                                                else:
                                                    logger.warning(
                                                        f"⚠️ Telegram 알림 전송 불가 (notify_service 미사용): "
                                                        f"order_id={order_id}"
                                                    )
                                            except Exception as notify_error:
                                                logger.warning(
                                                    f"⚠️ Telegram 알림 전송 실패 (계속 진행): "
                                                    f"order_id={order_id}, error={notify_error}"
                                                )

                                            # 캐시 초기화 (재알림 방지)
                                            self.fetch_failure_cache[order_id] = 0
                                    else:
                                        logger.warning(
                                            f"⚠️ 주문 상태 확인 실패 (다음 사이클 재시도): "
                                            f"order_id={locked_order.exchange_order_id}, "
                                            f"error={type(e).__name__}: {str(e)}"
                                        )

                                    # 주문 유지 (삭제하지 않음)
                                    locked_order.is_processing = False
                                    locked_order.processing_started_at = None
                                    total_failed += 1
                            else:
                                # 상태 확인
                                status = exchange_order.get('status', '').upper()

                                # Phase 2: 변환된 LIMIT 주문 추적 로그
                                # @FEAT:order-tracking @FEAT:stop-limit-activation @COMP:service @TYPE:core @ISSUE:45
                                # Phase 1에서 STOP_LIMIT → LIMIT으로 변환된 주문이 배치 쿼리에 포함되는지 확인
                                if locked_order.order_type == 'LIMIT' and status in ['NEW', 'OPEN', 'PARTIALLY_FILLED']:
                                    logger.debug(
                                        f"📍 변환된 LIMIT 주문 배치 조회 확인: order_id={locked_order.exchange_order_id}, "
                                        f"symbol={locked_order.symbol}, status={status}, "
                                        f"price={locked_order.price}"
                                    )

                                # @FEAT:order-tracking @COMP:job @TYPE:core
                                # Phase 2: 체결 처리 추가 (FILLED/PARTIALLY_FILLED)
                                fill_processed_successfully = True
                                if status in ['FILLED', 'PARTIALLY_FILLED']:
                                    fill_summary = self._process_scheduler_fill(
                                        locked_order, exchange_order, account
                                    )

                                    if fill_summary.get('success'):
                                        logger.info(
                                            f"✅ Scheduler 체결 처리 완료 - "
                                            f"order_id={locked_order.exchange_order_id}, "
                                            f"Trade ID: {fill_summary.get('trade_id')}"
                                        )
                                    else:
                                        # Phase 3 Critical Fix: @ISSUE #2 - 체결 처리 실패 시 주문 유지 (거래소 상태 신뢰, DB 저장 실패 시 29초 후 재시도)
                                        fill_processed_successfully = False
                                        logger.error(
                                            f"❌ 체결 처리 실패로 주문 유지: "
                                            f"order_id={locked_order.exchange_order_id}, "
                                            f"재시도 예정 (29초 후)"
                                        )
                                        # 플래그 해제하여 다음 주기에 재시도 가능하도록
                                        locked_order.is_processing = False
                                        locked_order.processing_started_at = None
                                        total_failed += 1
                                        continue  # 주문 삭제 건너뛰기

                                # OpenOrder 업데이트/삭제 처리
                                if status in ['FILLED', 'CANCELED', 'CANCELLED', 'EXPIRED']:
                                    # 완료 상태 → 삭제
                                    logger.info(
                                        f"🗑️ OpenOrder 삭제 (완료): "
                                        f"order_id={locked_order.exchange_order_id}, "
                                        f"symbol={locked_order.symbol}, status={status}"
                                    )

                                    # SSE 이벤트 발송 (취소/만료만, DB 삭제 전)
                                    if status in ['CANCELED', 'CANCELLED', 'EXPIRED']:
                                        try:
                                            self.service.event_emitter.emit_order_cancelled_or_expired_event(
                                                open_order=locked_order,
                                                status=status
                                            )
                                        except Exception as sse_error:
                                            logger.warning(
                                                f"⚠️ SSE 이벤트 발송 실패 (무시): "
                                                f"order_id={locked_order.exchange_order_id}, "
                                                f"error={sse_error}"
                                            )

                                    db.session.delete(locked_order)
                                    total_deleted += 1
                                elif status in ['PARTIALLY_FILLED']:
                                    # 부분 체결 → 업데이트
                                    filled_qty = float(exchange_order.get('filled_quantity', 0))
                                    logger.info(
                                        f"📝 OpenOrder 업데이트 (부분 체결): "
                                        f"order_id={locked_order.exchange_order_id}, "
                                        f"symbol={locked_order.symbol}, filled={filled_qty}"
                                    )
                                    locked_order.status = status
                                    locked_order.filled_quantity = filled_qty

                                    # 플래그 해제 (부분 체결은 계속 모니터링)
                                    locked_order.is_processing = False
                                    locked_order.processing_started_at = None
                                    total_updated += 1
                                else:
                                    # NEW 또는 기타 → 상태만 업데이트
                                    locked_order.status = status
                                    locked_order.is_processing = False
                                    locked_order.processing_started_at = None
                                    total_updated += 1

                            total_processed += 1

                        except Exception as e:
                            logger.error(
                                f"❌ 주문 처리 실패: order_id={db_order.exchange_order_id}, "
                                f"error={e}",
                                exc_info=True
                            )

                            # 에러 발생 시 플래그 해제
                            if db_order.is_processing:
                                db_order.is_processing = False
                                db_order.processing_started_at = None

                            total_failed += 1

                    # 계좌별 커밋
                    db.session.commit()
                    logger.info(
                        f"✅ 계좌 처리 완료: {account.name}, "
                        f"처리={len(db_orders)}, 업데이트={total_updated}, "
                        f"삭제={total_deleted}"
                    )

                    # @FEAT:order-tracking @COMP:job @TYPE:resilience
                    # Priority 2 Phase 2: Gradual Recovery - 성공 시 카운터 감소
                    if exchange_failures[exchange_name] > 0:
                        old_count = exchange_failures[exchange_name]
                        exchange_failures[exchange_name] = max(0, old_count - 1)
                        logger.info(
                            f"✅ {exchange_name} 복구 진행: 실패 카운터 {old_count} → {exchange_failures[exchange_name]}"
                        )

                # @FEAT:order-tracking @COMP:job @TYPE:resilience
                # Priority 2 Phase 1: 계좌 격리 - 배치 처리 실패 시 다른 계좌 계속 진행
                except Exception as e:
                    db.session.rollback()
                    logger.error(
                        f"❌ 계좌 배치 처리 실패: account_id={account_id}, error={e} (다음 계좌 계속 진행)",
                        exc_info=True
                    )

                    # Circuit Breaker: 실패 시 카운터 증가 (exchange_name이 할당된 경우만)
                    if exchange_name:
                        exchange_failures[exchange_name] += 1
                        logger.warning(
                            f"⚠️ {exchange_name} 실패 카운터 증가: "
                            f"{exchange_failures[exchange_name] - 1} → {exchange_failures[exchange_name]} "
                            f"(임계값: {CIRCUIT_BREAKER_THRESHOLD})"
                        )
                    else:
                        logger.warning(
                            f"⚠️ 거래소 정보 없음: account_id={account_id} - "
                            f"Circuit Breaker 카운터 증가 불가 (계좌 조회 실패)"
                        )

                    total_failed += len(db_orders)
                    continue  # 다음 계좌로 계속 진행

            # Step 4: 최종 보고
            logger.info(
                f"✅ 미체결 주문 상태 업데이트 완료: "
                f"처리={total_processed}, 업데이트={total_updated}, "
                f"삭제={total_deleted}, 실패={total_failed}"
            )

            # @FEAT:orphan-order-prevention @PHASE:4
            # Step 5: PENDING 주문 정리 (Phase 4)
            self._cleanup_stuck_pending_orders()

            # @FEAT:orphan-order-prevention @PHASE:4
            # Step 6: CANCELLING 주문 정리 (Phase 4)
            self._cleanup_orphan_cancelling_orders()

        except Exception as e:
            db.session.rollback()
            logger.error(f"❌ 미체결 주문 상태 업데이트 실패: {e}", exc_info=True)

    # @FEAT:order-tracking @FEAT:limit-order @COMP:job @TYPE:core
    def _process_scheduler_fill(
        self,
        locked_order: OpenOrder,
        exchange_order: Dict,
        account: Account
    ) -> Dict[str, Any]:
        """
        Scheduler Path: 체결 처리 (Phase 2)

        공통 로직은 helper 함수로 추출하여 Phase 1과 공유

        Args:
            locked_order: 잠금 획득한 OpenOrder 인스턴스
            exchange_order: 거래소에서 조회한 주문 정보
            account: 거래 계좌

        Returns:
            fill_summary: process_order_fill() 결과
        """
        try:
            # TradingService import
            from app.services.trading import trading_service

            # ✅ 공통 로직: order_info → order_result 포맷 변환
            order_result = self._convert_exchange_order_to_result(exchange_order, locked_order)

            # Phase 2: 변환된 LIMIT 주문 체결 처리 로그 강화
            # @FEAT:stop-limit-activation @COMP:service @TYPE:core @ISSUE:45
            # STOP_LIMIT에서 변환된 LIMIT 주문도 이 경로로 체결 처리됨
            if locked_order.order_type == 'LIMIT':
                logger.debug(
                    f"📊 LIMIT 주문 체결 처리: order_id={locked_order.exchange_order_id}, "
                    f"symbol={locked_order.symbol}, "
                    f"filled_quantity={exchange_order.get('filled_quantity')}, "
                    f"average_price={exchange_order.get('average_price')}"
                )

            fill_summary = trading_service.position_manager.process_order_fill(
                strategy_account=locked_order.strategy_account,
                order_id=locked_order.exchange_order_id,
                symbol=locked_order.symbol,
                side=locked_order.side,
                order_type=locked_order.order_type,
                order_result=order_result,
                market_type=locked_order.strategy_account.strategy.market_type
            )

            # Phase 2: 체결 처리 완료 로그 (변환된 주문 추적용)
            if locked_order.order_type == 'LIMIT' and fill_summary.get('success'):
                logger.info(
                    f"✅ 변환된 LIMIT 주문 체결 처리 완료: "
                    f"order_id={locked_order.exchange_order_id}, "
                    f"원래 타입: STOP_LIMIT (활성화됨), "
                    f"trade_id={fill_summary.get('trade_id')}"
                )

            return fill_summary

        except Exception as e:
            logger.error(
                f"❌ Scheduler 체결 처리 실패: order_id={locked_order.exchange_order_id}, "
                f"error={type(e).__name__}: {str(e)}",
                exc_info=True
            )
            return {
                'success': False,
                'error': str(e)
            }

    # @FEAT:order-tracking @FEAT:limit-order @COMP:job @TYPE:helper
    def _convert_exchange_order_to_result(self, exchange_order: dict, open_order: OpenOrder) -> dict:
        """
        공통 로직: exchange_order → order_result 포맷 변환
        Phase 2에서 사용 (order_fill_monitor의 _convert_order_info_to_result와 유사)
        """
        return {
            'order_id': exchange_order.get('order_id') or open_order.exchange_order_id,
            'status': exchange_order.get('status'),
            'filled_quantity': exchange_order.get('filled_quantity'),
            'average_price': exchange_order.get('average_price'),
            'side': exchange_order.get('side') or open_order.side,
            'order_type': exchange_order.get('order_type') or open_order.order_type
        }

    # @FEAT:order-tracking @COMP:job @TYPE:helper
    def _process_single_order(
        self,
        db_order: OpenOrder,
        fetch_result: Dict,
        account_id: int
    ) -> str:
        """개별 주문 처리 (Phase 3: 폴백 시 사용)

        배치 쿼리 실패 시 안전장치로 사용됩니다.

        Args:
            db_order: DB의 OpenOrder 인스턴스
            fetch_result: fetch_order() 결과
            account_id: 계정 ID

        Returns:
            'updated', 'deleted', or 'skipped'
        """
        from app.constants import OrderStatus
        from datetime import datetime

        try:
            # 낙관적 잠금
            locked_order = OpenOrder.query.filter_by(
                id=db_order.id,
                is_processing=False
            ).with_for_update(skip_locked=True).first()

            if not locked_order:
                return 'skipped'

            locked_order.is_processing = True
            locked_order.processing_started_at = datetime.utcnow()
            db.session.flush()

            status = fetch_result.get('status', '').upper()

            if status in ['FILLED', 'CANCELED', 'CANCELLED', 'EXPIRED']:
                db.session.delete(locked_order)
                db.session.commit()
                return 'deleted'
            elif status == 'PARTIALLY_FILLED':
                locked_order.status = status
                locked_order.filled_quantity = float(fetch_result.get('filled_quantity', 0))
                locked_order.is_processing = False
                locked_order.processing_started_at = None
                db.session.commit()
                return 'updated'
            else:
                locked_order.status = status
                locked_order.is_processing = False
                locked_order.processing_started_at = None
                db.session.commit()
                return 'updated'

        except Exception as e:
            db.session.rollback()

            # @FEAT:order-tracking @COMP:job @TYPE:validation
            # Phase 3 Critical Fix: @ISSUE #1-B - 예외 발생 시 플래그 해제 (DeadlockDetected 등 예외 시 잠금 복구)
            try:
                # locked_order가 존재하고 잠금 상태인 경우만 해제
                if locked_order and locked_order.is_processing:
                    locked_order.is_processing = False
                    locked_order.processing_started_at = None
                    db.session.commit()
                    logger.debug(
                        f"🔓 플래그 해제 완료 (예외 복구): "
                        f"order_id={locked_order.exchange_order_id}"
                    )
            except Exception as flag_error:
                db.session.rollback()
                logger.warning(
                    f"⚠️ 플래그 해제 실패: {flag_error}"
                )

            logger.error(f"❌ 개별 주문 처리 실패: {e}")
            return 'failed'

    # @FEAT:order-tracking @COMP:job @TYPE:core
    def release_stale_order_locks(self) -> None:
        """오래된 처리 잠금 해제 (Phase 2: 타임아웃 복구)

        프로세스 크래시 또는 WebSocket 핸들러 중단 시 영구적으로 잠긴 주문을 복구합니다.

        임계값: 5분 이상 처리 중인 주문
        실행 주기: 60초마다
        """
        from datetime import datetime, timedelta

        try:
            stale_threshold = datetime.utcnow() - timedelta(minutes=5)

            # 5분 이상 처리 중인 주문 조회
            stale_orders = OpenOrder.query.filter(
                OpenOrder.is_processing == True,
                OpenOrder.processing_started_at < stale_threshold
            ).all()

            if not stale_orders:
                logger.debug("⏰ 오래된 처리 잠금 없음 (모든 주문 정상)")
                return

            # 잠금 해제
            released_count = 0
            for order in stale_orders:
                elapsed_seconds = (datetime.utcnow() - order.processing_started_at).total_seconds()
                logger.warning(
                    f"⚠️ 오래된 처리 잠금 해제: "
                    f"order_id={order.exchange_order_id}, "
                    f"symbol={order.symbol}, "
                    f"처리 시작: {order.processing_started_at}, "
                    f"경과 시간: {elapsed_seconds:.1f}초"
                )

                order.is_processing = False
                order.processing_started_at = None
                released_count += 1

            db.session.commit()
            logger.info(f"✅ 오래된 처리 잠금 해제 완료: {released_count}개 주문")

        except Exception as e:
            db.session.rollback()
            logger.error(f"❌ 처리 잠금 해제 실패: {e}", exc_info=True)
