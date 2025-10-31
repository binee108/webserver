
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

    # @FEAT:order-tracking @COMP:service @TYPE:core
    # @DATA:OrderStatus.CANCELLING - DB-first 패턴 (Phase 2: 2025-10-30)
    def cancel_order(self, order_id: str, symbol: str, account_id: int) -> Dict[str, Any]:
        """주문 취소 (DB-First 패턴)

        WHY: 타임아웃 시 orphan order 방지. DB 상태를 먼저 변경하여 백그라운드 정리 가능.
        Edge Cases: 중복 취소(already_cancelling), 주문 없음(order_not_found), race condition(재조회)
        Side Effects: DB commit (CANCELLING 상태), SSE 이벤트, 거래소 API 호출
        Performance: 정상 1×commit, 실패/예외 2×commit, 재조회 최대 2회
        Debugging: 로그에서 🔄→✅/⚠️/❌ 이모지로 경로 추적

        Pattern:
        1. DB 상태를 CANCELLING으로 먼저 변경
        2. 거래소 API 호출 (타임아웃/재시도는 Phase 3)
        3. 성공 시: CANCELLING → CANCELLED (DB 삭제)
        4. 실패 시: CANCELLING → OPEN (원래 상태 복원)
        5. 예외 시: 하이브리드 처리 (1회 재확인 + 백그라운드)

        Args:
            order_id: 거래소 주문 ID
            symbol: 심볼
            account_id: 계정 ID

        Returns:
            Dict with success, error, error_type
        """
        try:
            # ============================================================
            # STEP 0: Validation
            # ============================================================
            account = Account.query.get(account_id)
            if not account:
                return {
                    'success': False,
                    'error': '계정을 찾을 수 없습니다',
                    'error_type': 'account_error'
                }

            # 계정의 전략을 통해 market_type 확인
            strategy_account = StrategyAccount.query.filter_by(
                account_id=account_id
            ).first()

            market_type = 'spot'  # 기본값
            if strategy_account and strategy_account.strategy:
                market_type = strategy_account.strategy.market_type.lower()

            # OpenOrder 조회
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

                    open_order.status = old_status
                    open_order.error_message = error_msg
                    db.session.commit()

                    logger.warning(
                        f"⚠️ 거래소 취소 실패 → {old_status} 복원: {order_id} "
                        f"(error: {error_msg[:50]}...)"
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

                    elif verification_result == 'active':
                        # 거래소에서 여전히 활성 상태 → OPEN 복원
                        error_msg = sanitize_error_message(str(e))
                        open_order.status = old_status
                        open_order.error_message = error_msg
                        db.session.commit()

                        logger.warning(
                            f"⚠️ 재확인: 거래소에서 활성 확인 → {old_status} 복원: {order_id}"
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
        Edge Cases: 네트워크 오류 → 'unknown', FILLED 상태 → 'unknown'
        Side Effects: 거래소 API 1회 호출 (fetch_order)
        Performance: 거래소 API 응답 시간 (보통 100-500ms)
        Debugging: 로그 "⚠️ 주문 상태 조회 실패" 또는 "⚠️ 예상치 못한 주문 상태"

        Phase 2 (cancel_order 예외 처리) + Phase 4 (백그라운드 정리)에서 재사용.

        Args:
            account: 거래소 계정
            order_id: 주문 ID
            symbol: 심볼
            market_type: 마켓 타입 ('spot', 'futures' 등)

        Returns:
            'cancelled': 거래소에서 취소됨 확인
            'active': 거래소에서 여전히 활성 상태
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

            # 기타 (예: FILLED)
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

            # 기존 cancel_order 메서드 재사용
            result = self.service.cancel_order(
                order_id=order_id,
                symbol=open_order.symbol,
                account_id=open_order.strategy_account.account.id
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
                                  timing_context: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """사용자 권한 기준의 미체결 주문 일괄 취소 (Phase 5 이후)

        @FEAT:order-cancel @COMP:service @TYPE:core

        ⚠️ Race Condition 방지: 심볼별 Lock 획득 후 OpenOrder 취소 (Issue #9)
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        모든 영향받는 (account_id, symbol) 조합의 Lock을 Deadlock 방지 순서로 획득하여
        OpenOrder를 취소하고 거래소 API를 호출합니다.
        Phase 5 이후 OpenOrder만 처리하며 PendingOrder 로직은 제거되었습니다.

        권한 모델 (Permission Models)
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        - User-Scoped (포지션 페이지): user_id=current_user.id (현재 유저만)
        - Strategy-Scoped (웹훅): user_id=account.user_id (각 구독자별 루프 호출)

        Args:
            user_id: 사용자 ID (포지션: current_user.id, 웹훅: account.user_id)
            strategy_id: 전략 ID
            account_id: 계좌 ID 필터 (None=모든 계좌, 지정=해당 계좌만)
            symbol: 심볼 필터 (None=전체, "BTC/USDT"=특정 심볼)
            side: 주문 방향 필터 (None=전체, "BUY"/"SELL"=특정 방향, 대소문자 무관)
            timing_context: 웹훅 타이밍 정보 (웹훅: {'webhook_received_at': timestamp})

        Returns:
            Dict[str, Any]: {
                'success': bool,
                'cancelled_orders': List[Dict],  # OpenOrder 취소 목록 (PendingOrder 없음)
                'failed_orders': List[Dict],      # 실패 목록
                'total_processed': int,
                'filter_conditions': List[str],
                'message': str
            }

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
                    cancel_result = self.service.cancel_order(
                        order_id=open_order.exchange_order_id,
                        symbol=open_order.symbol,
                        account_id=account.id
                    )

                    order_summary = {
                        'order_id': open_order.exchange_order_id,
                        'symbol': open_order.symbol,
                        'account_id': account.id,
                        'strategy_id': strategy_account.strategy.id if strategy_account and strategy_account.strategy else None
                    }

                    if cancel_result.get('success'):
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

        Infinite Loop Fix (2025-10-26):
            - webhook_received_at 파라미터 추가로 원본 웹훅 수신 시각 보존
            - PendingOrder → OpenOrder 전환 시 타임스탬프 손실 방지
            - 정렬 순서 안정성 보장을 위한 필수 필드
            - See Migration: 20251026_add_webhook_received_at
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

    # @FEAT:webhook-order @COMP:job @TYPE:core
    # @DATA:OrderStatus.PENDING - PENDING 주문 정리 (Phase 2: 2025-10-30)
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

    # @FEAT:order-tracking @COMP:service @TYPE:helper
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

    # @FEAT:order-tracking @COMP:job @TYPE:core
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
                                # 거래소에 없음 → 이미 체결/취소됨 → 삭제
                                logger.info(
                                    f"🗑️ OpenOrder 삭제 (거래소에 없음): "
                                    f"order_id={locked_order.exchange_order_id}, "
                                    f"symbol={locked_order.symbol}"
                                )
                                db.session.delete(locked_order)
                                total_deleted += 1
                            else:
                                # 상태 확인
                                status = exchange_order.get('status', '').upper()

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

            # Step 5: PENDING 주문 정리 (Phase 2)
            self._cleanup_stuck_pending_orders()

            # Step 6: CANCELLING 주문 정리 (Phase 4: 2025-10-30)
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

            fill_summary = trading_service.position_manager.process_order_fill(
                strategy_account=locked_order.strategy_account,
                order_id=locked_order.exchange_order_id,
                symbol=locked_order.symbol,
                side=locked_order.side,
                order_type=locked_order.order_type,
                order_result=order_result,
                market_type=locked_order.strategy_account.strategy.market_type
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
