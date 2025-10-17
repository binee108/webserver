
"""Order management logic extracted from the legacy trading service."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import joinedload

from app import db
from app.models import Account, OpenOrder, Strategy, StrategyAccount
from app.services.exchange import exchange_service
from app.constants import OrderType

logger = logging.getLogger(__name__)


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

    def cancel_order(self, order_id: str, symbol: str, account_id: int) -> Dict[str, Any]:
        """주문 취소"""
        try:
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

            logger.info(f"주문 취소 - order_id: {order_id}, symbol: {symbol}, market_type: {market_type}")

            # 거래소에서 주문 취소
            result = exchange_service.cancel_order(
                account=account,
                order_id=order_id,
                symbol=symbol,
                market_type=market_type
            )

            if result['success']:
                # OpenOrder 기록 업데이트
                open_order = OpenOrder.query.filter_by(
                    exchange_order_id=order_id
                ).first()

                if open_order:
                    # 주문 정보 로그 (삭제 전)
                    logger.info(f"🗑️ OpenOrder 정리: {order_id} (취소 처리)")

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
                        logger.info(f"📊 심볼 구독 해제 - 계정: {account_id}, 심볼: {symbol} (마지막 주문)")
                    else:
                        logger.debug(f"📊 심볼 구독 유지 - 계정: {account_id}, 심볼: {symbol} (남은 주문: {remaining_orders}개)")

                    logger.info(f"✅ 취소된 주문이 정리되었습니다: {order_id}")

            return result

        except Exception as e:
            logger.error(f"주문 취소 실패: {e}")
            return {
                'success': False,
                'error': str(e),
                'error_type': 'cancel_error'
            }

    def cancel_order_by_user(self, order_id: str, user_id: int) -> Dict[str, Any]:
        """사용자 권한 기준 주문 취소"""
        try:
            from app.constants import OrderStatus

            # 주문 조회 및 사용자 권한 확인
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

            # 기존 cancel_order 메서드를 재사용
            result = self.service.cancel_order(
                order_id=order_id,
                symbol=open_order.symbol,
                account_id=open_order.strategy_account.account.id
            )

            if result['success']:
                result['symbol'] = open_order.symbol

            return result

        except Exception as e:
            logger.error(f"사용자 주문 취소 실패: {e}")
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
        """사용자 권한 기준의 미체결 주문 일괄 취소 (OpenOrder + PendingOrder)

        ⚠️  단일 소스 (Single Source of Truth)
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        모든 주문 취소 로직은 이 메서드를 거칩니다. 수정 시 영향받는 기능:
        1. 포지션 페이지 - 모든 주문 취소 버튼 (positions.py)
        2. 웹훅 - CANCEL_ALL_ORDER 메시지 처리 (webhook_service.py)
        3. SSE 실시간 이벤트 발송 (포지션 페이지 UI 업데이트)
        4. Race Condition 방지 (WebSocket 체결 이벤트 간섭 차단)
        5. 대기열 시스템 (rebalance_symbol과의 동기화)

        ⚠️  Race Condition 방지: 순서 변경 금지!
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        Phase 1: PendingOrder 삭제 → commit (먼저 커밋)
        Phase 2: OpenOrder 취소 (거래소 API 호출)

        이유: OpenOrder 취소 시 WebSocket 이벤트가 rebalance_symbol()을 트리거하여
        PendingOrder를 거래소로 전송할 수 있음. Phase 1에서 먼저 삭제하여 방지.

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
                'cancelled_orders': List[Dict],  # OpenOrder 취소 목록
                'failed_orders': List[Dict],      # 실패 목록
                'pending_deleted': int,           # PendingOrder 삭제 수
                'total_processed': int,
                'filter_conditions': List[str],
                'message': str
            }
        """
        try:
            from app.constants import OrderStatus
            from app.models import PendingOrder

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
            # Step 1: PendingOrder 삭제 (경쟁 조건 방지 - 먼저 삭제)
            # ============================================================
            pending_query = (
                PendingOrder.query
                .join(StrategyAccount)
                .join(Account)
                .options(
                    joinedload(PendingOrder.strategy_account)
                    .joinedload(StrategyAccount.account)
                )
                .filter(
                    Account.user_id == user_id,
                    Account.is_active == True,
                    StrategyAccount.strategy_id == strategy_id
                )
            )

            if account_id:
                pending_query = pending_query.filter(Account.id == account_id)
                if f"account_id={account_id}" not in filter_conditions:
                    filter_conditions.append(f"account_id={account_id}")

            if symbol:
                pending_query = pending_query.filter(PendingOrder.symbol == symbol)
                if f"symbol={symbol}" not in filter_conditions:
                    filter_conditions.append(f"symbol={symbol}")

            # 🆕 side 필터링 추가
            if side:
                pending_query = pending_query.filter(PendingOrder.side == side.upper())
                if f"side={side.upper()}" not in filter_conditions:
                    filter_conditions.append(f"side={side.upper()}")

            pending_orders = pending_query.all()
            pending_deleted_count = len(pending_orders)

            logger.info(
                f"🗑️ PendingOrder 삭제 시작 - 사용자: {user_id}, {pending_deleted_count}개"
                + (f" ({', '.join(filter_conditions)})" if filter_conditions else '')
            )

            # PendingOrder 삭제 + SSE 이벤트 발송
            for pending_order in pending_orders:
                try:
                    # SSE 이벤트 발송 (삭제 전)
                    strategy_account = pending_order.strategy_account
                    if strategy_account and strategy_account.strategy:
                        self.service.event_emitter.emit_pending_order_event(
                            event_type='order_cancelled',
                            pending_order=pending_order,
                            user_id=user_id
                        )
                except Exception as sse_error:
                    logger.warning(f"PendingOrder SSE 이벤트 발송 실패: {sse_error}")

                # DB에서 삭제
                db.session.delete(pending_order)

            # PendingOrder 삭제 커밋 (OpenOrder 취소 전에 완료)
            db.session.commit()

            if pending_deleted_count > 0:
                logger.info(f"✅ PendingOrder {pending_deleted_count}개 삭제 완료")

            # ============================================================
            # Step 2: OpenOrder 취소
            # ============================================================
            query = (
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
                query = query.filter(Account.id == account_id)

            if symbol:
                query = query.filter(OpenOrder.symbol == symbol)

            # 🆕 side 필터링 추가
            if side:
                query = query.filter(OpenOrder.side == side.upper())

            target_orders = query.all()

            if not target_orders and pending_deleted_count == 0:
                logger.info(
                    f"No orders to cancel for user {user_id}"
                    + (f" ({', '.join(filter_conditions)})" if filter_conditions else '')
                )
                return {
                    'success': True,
                    'cancelled_orders': [],
                    'failed_orders': [],
                    'pending_deleted': 0,
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
            total_processed = total_cancelled + total_failed + pending_deleted_count

            logger.info(
                f"✅ 일괄 취소 완료 - 사용자: {user_id}, "
                f"OpenOrder 취소: {total_cancelled}개, 실패: {total_failed}개, "
                f"PendingOrder 삭제: {pending_deleted_count}개"
            )

            response = {
                'cancelled_orders': cancelled_orders,
                'failed_orders': failed_orders,
                'pending_deleted': pending_deleted_count,
                'total_processed': total_processed,
                'filter_conditions': filter_conditions
            }

            if total_cancelled > 0 and total_failed == 0:
                if pending_deleted_count > 0:
                    response['success'] = True
                    response['message'] = f'{total_cancelled}개 주문 취소 및 {pending_deleted_count}개 대기열 주문 삭제 완료'
                else:
                    response['success'] = True
                    response['message'] = f'{total_cancelled}개 주문을 취소했습니다.'
            elif total_cancelled > 0 and total_failed > 0:
                response['success'] = True
                response['partial_success'] = True
                if pending_deleted_count > 0:
                    response['message'] = (
                        f'일부 주문만 취소되었습니다. '
                        f'OpenOrder: 성공 {total_cancelled}개, 실패 {total_failed}개, '
                        f'PendingOrder: {pending_deleted_count}개 삭제'
                    )
                else:
                    response['message'] = (
                        f'일부 주문만 취소되었습니다. 성공 {total_cancelled}개, 실패 {total_failed}개'
                    )
            elif total_cancelled == 0 and pending_deleted_count > 0:
                # OpenOrder는 없고 PendingOrder만 삭제된 경우
                response['success'] = True
                response['message'] = f'{pending_deleted_count}개 대기열 주문을 삭제했습니다.'
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
                'pending_deleted': 0,
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
    ) -> Dict[str, Any]:
        """Persist an open order if the exchange reports it as outstanding."""
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

    # @FEAT:order-tracking @COMP:job @TYPE:core
    def update_open_orders_status(self) -> None:
        """백그라운드 작업: 모든 미체결 주문의 상태를 거래소와 동기화 (Phase 3: 배치 쿼리 최적화)

        개선사항:
        - 개별 API 호출 → 계좌별 배치 쿼리
        - 100개 주문: 100번 호출 → 5번 호출 (20배 개선)
        - 처리 시간: 20초 → 1초

        실행 주기: 29초마다
        """
        from app.constants import OrderStatus
        from datetime import datetime

        try:
            # Step 1: 처리 중이 아닌 미체결 주문 조회 (Phase 2 낙관적 잠금)
            open_orders = (
                OpenOrder.query
                .options(
                    joinedload(OpenOrder.strategy_account)
                    .joinedload(StrategyAccount.account),
                    joinedload(OpenOrder.strategy_account)
                    .joinedload(StrategyAccount.strategy)
                )
                .filter(
                    OpenOrder.status.in_(OrderStatus.get_open_statuses()),
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

            # Step 3: 계좌별 배치 처리
            total_processed = 0
            total_updated = 0
            total_deleted = 0
            total_failed = 0

            for account_id, db_orders in grouped_by_account.items():
                try:
                    # Step 3-1: 계좌 조회
                    account = Account.query.get(account_id)
                    if not account:
                        logger.error(f"❌ 계정을 찾을 수 없음: account_id={account_id}")
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

                                # ✅ Phase 2: 체결 처리 추가 (FILLED/PARTIALLY_FILLED)
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

                except Exception as e:
                    db.session.rollback()
                    logger.error(
                        f"❌ 계좌 배치 처리 실패: account_id={account_id}, error={e}",
                        exc_info=True
                    )
                    total_failed += len(db_orders)

            # Step 4: 최종 보고
            logger.info(
                f"✅ 미체결 주문 상태 업데이트 완료: "
                f"처리={total_processed}, 업데이트={total_updated}, "
                f"삭제={total_deleted}, 실패={total_failed}"
            )

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
