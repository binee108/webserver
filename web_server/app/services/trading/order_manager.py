
"""Order management logic extracted from the legacy trading service."""

from __future__ import annotations

import logging
import time
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

                # 취소 이벤트 발송
                self.service.event_emitter.emit_order_cancelled_event(order_id, symbol, account_id)

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

    def update_open_orders_status(self) -> None:
        """백그라운드 작업: 모든 미체결 주문의 상태를 거래소와 동기화"""
        from app.constants import OrderStatus

        try:
            # DB에서 미체결 상태인 모든 주문 조회
            open_orders = (
                OpenOrder.query
                .options(
                    joinedload(OpenOrder.strategy_account)
                    .joinedload(StrategyAccount.account),
                    joinedload(OpenOrder.strategy_account)
                    .joinedload(StrategyAccount.strategy)
                )
                .filter(OpenOrder.status.in_(OrderStatus.get_open_statuses()))
                .all()
            )

            if not open_orders:
                return

            logger.info(f"미체결 주문 상태 동기화 시작: {len(open_orders)}개 주문")

            updated_count = 0
            closed_count = 0
            error_count = 0

            for open_order in open_orders:
                try:
                    strategy_account = open_order.strategy_account
                    if not strategy_account or not strategy_account.account or not strategy_account.strategy:
                        logger.warning(f"전략 계정 정보 없음 - order_id: {open_order.exchange_order_id}")
                        continue

                    account = strategy_account.account
                    strategy = strategy_account.strategy

                    # 거래소에서 주문 상태 조회
                    from app.services.exchange import exchange_service
                    market_type = strategy.market_type.lower() if strategy.market_type else 'spot'

                    order_info = exchange_service.fetch_order(
                        account=account,
                        order_id=open_order.exchange_order_id,
                        symbol=open_order.symbol,
                        market_type=market_type
                    )

                    if not order_info.get('success'):
                        error_count += 1
                        continue

                    order_status = order_info.get('status', '')

                    # 상태 업데이트
                    if OrderStatus.is_closed(order_status):
                        # 완료된 주문은 DB에서 제거
                        db.session.delete(open_order)
                        closed_count += 1
                        logger.debug(f"완료된 주문 제거: {open_order.exchange_order_id}")
                    else:
                        # 미체결 상태 업데이트
                        open_order.status = order_status
                        open_order.filled_quantity = float(order_info.get('filled_quantity', 0))
                        updated_count += 1

                except Exception as e:
                    error_count += 1
                    logger.error(f"주문 상태 업데이트 실패 - order_id: {open_order.exchange_order_id}, error: {e}")
                    continue

            # 일괄 커밋
            db.session.commit()

            logger.info(
                f"미체결 주문 상태 동기화 완료 - 업데이트: {updated_count}, 완료: {closed_count}, 오류: {error_count}"
            )

        except Exception as e:
            db.session.rollback()
            logger.error(f"미체결 주문 상태 동기화 실패: {e}")
