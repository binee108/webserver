# @FEAT:order-queue @COMP:service @TYPE:core @DEPS:order-tracking,exchange-integration
"""
주문 대기열 관리 모듈

거래소 열린 주문 제한 초과 시 주문을 대기열에 추가하고,
우선순위 기반 동적 재정렬을 통해 최적의 주문 실행을 보장합니다.
"""

from __future__ import annotations

import logging
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional
from datetime import datetime

from app import db
from app.models import OpenOrder, PendingOrder, StrategyAccount, Account
from app.constants import ExchangeLimits, OrderType, ORDER_TYPE_GROUPS, MAX_ORDERS_PER_SYMBOL_TYPE_SIDE
from app.services.utils import to_decimal

logger = logging.getLogger(__name__)


# @FEAT:order-queue @COMP:service @TYPE:core
class OrderQueueManager:
    """주문 대기열 관리자

    핵심 기능:
    1. 대기열에 주문 추가 (enqueue)
    2. 심볼별 동적 재정렬 (rebalance_symbol)
    3. 거래소 주문 ↔ 대기열 주문 간 이동
    4. 성능 메트릭 수집
    """

    MAX_RETRY_COUNT = 5  # 재시도 횟수 제한 상수

    # @FEAT:order-queue @COMP:service @TYPE:core
    def __init__(self, service: Optional[object] = None) -> None:
        """주문 큐 매니저 초기화

        Args:
            service: TradingCore 인스턴스 (거래소 API 호출용)
        """
        self.service = service

        # ✅ v2: 동시성 보호 (조건 4)
        import threading
        self._rebalance_locks = {}  # {(account_id, symbol): Lock}
        self._locks_lock = threading.Lock()

        self.metrics = {
            'total_rebalances': 0,
            'total_cancelled': 0,
            'total_executed': 0,
            'total_duration_ms': 0,
            'avg_duration_ms': 0
        }

    # @FEAT:order-queue @COMP:service @TYPE:core
    def enqueue(
        self,
        strategy_account_id: int,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None,
        market_type: str = 'FUTURES',
        reason: str = 'QUEUE_LIMIT',
        commit: bool = True  # ✅ v2: 트랜잭션 제어 (조건 2)
    ) -> Dict[str, Any]:
        """대기열에 주문 추가 (내부 PendingOrder, SSE 미발송)

        PendingOrder는 거래소 주문 제한 초과 시 내부 대기열 상태로만 유지됩니다.
        사용자 알림은 웹훅 응답 시 order_type별 집계 Batch SSE로 발송됩니다 (Phase 2).

        Args:
            strategy_account_id: 전략 계정 ID
            symbol: 거래 심볼
            side: 주문 방향 (BUY/SELL)
            order_type: 주문 타입 (LIMIT/STOP_LIMIT/STOP_MARKET)
            quantity: 주문 수량
            price: LIMIT 가격 (선택적)
            stop_price: STOP 트리거 가격 (선택적)
            market_type: 마켓 타입 (SPOT/FUTURES)
            reason: 대기열 진입 사유
            commit: 즉시 커밋 여부 (기본값: True)

        Returns:
            dict: {'success': bool, 'pending_order_id': int, 'priority': int, 'sort_price': Decimal, 'message': str}
        """
        try:
            # StrategyAccount 조회
            strategy_account = StrategyAccount.query.get(strategy_account_id)
            if not strategy_account or not strategy_account.account:
                return {
                    'success': False,
                    'error': f'전략 계정을 찾을 수 없습니다 (ID: {strategy_account_id})'
                }

            account = strategy_account.account

            # 우선순위 계산
            priority = OrderType.get_priority(order_type)

            # 정렬용 가격 계산
            sort_price = self._calculate_sort_price(order_type, side, price, stop_price)

            # PendingOrder 레코드 생성
            pending_order = PendingOrder(
                account_id=account.id,
                strategy_account_id=strategy_account_id,
                symbol=symbol,
                side=side.upper(),
                order_type=order_type,
                price=float(price) if price else None,
                stop_price=float(stop_price) if stop_price else None,
                quantity=float(quantity),
                priority=priority,
                sort_price=float(sort_price) if sort_price else None,
                market_type=market_type,
                reason=reason
            )

            db.session.add(pending_order)
            # ✅ v2: 호출자가 commit 제어
            if commit:
                db.session.commit()

            # PendingOrder SSE 발송 제거 - 웹훅 응답 시 Batch SSE로 통합 (Phase 2)
            logger.info(
                f"📥 대기열 추가 완료 - ID: {pending_order.id}, "
                f"심볼: {symbol}, 타입: {order_type}, "
                f"우선순위: {priority}, 정렬가격: {sort_price}"
            )

            return {
                'success': True,
                'pending_order_id': pending_order.id,
                'priority': priority,
                'sort_price': float(sort_price) if sort_price else None,
                'message': f'대기열에 추가되었습니다 (우선순위: {priority})'
            }

        except Exception as e:
            # ✅ v2: commit=True일 때만 롤백 (호출자가 트랜잭션 제어 중일 수 있음)
            if commit:
                db.session.rollback()
            logger.error(f"대기열 추가 실패: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    # @FEAT:order-queue @COMP:service @TYPE:helper
    def _calculate_sort_price(
        self,
        order_type: str,
        side: str,
        price: Optional[Decimal],
        stop_price: Optional[Decimal]
    ) -> Optional[Decimal]:
        """정렬용 가격 계산

        정렬 로직:
        - LIMIT BUY:   sort_price = price          (높을수록 우선 → DESC)
        - LIMIT SELL:  sort_price = -price         (낮을수록 우선 → DESC 변환)
        - STOP BUY:    sort_price = -stop_price    (낮을수록 우선 → DESC 변환)
        - STOP SELL:   sort_price = stop_price     (높을수록 우선 → DESC)
        - MARKET:      sort_price = NULL

        Args:
            order_type: 주문 타입
            side: 주문 방향
            price: LIMIT 가격
            stop_price: STOP 트리거 가격

        Returns:
            Optional[Decimal]: 정렬용 가격 (MARKET은 None)
        """
        side_upper = side.upper()

        # MARKET 주문은 정렬 가격 없음
        if order_type == OrderType.MARKET:
            return None

        # LIMIT 주문
        if order_type == OrderType.LIMIT:
            if price is None:
                logger.warning(f"LIMIT 주문이지만 price가 없음 (side={side})")
                return None

            if side_upper == 'BUY':
                # 높을수록 우선
                return to_decimal(price)
            else:  # SELL
                # 낮을수록 우선 → 음수 변환
                return -to_decimal(price)

        # STOP 주문 (STOP_LIMIT, STOP_MARKET)
        if OrderType.requires_stop_price(order_type):
            if stop_price is None:
                logger.warning(f"{order_type} 주문이지만 stop_price가 없음 (side={side})")
                return None

            if side_upper == 'BUY':
                # 낮을수록 우선 → 음수 변환
                return -to_decimal(stop_price)
            else:  # SELL
                # 높을수록 우선
                return to_decimal(stop_price)

        # 기타 주문 타입
        logger.warning(f"정렬 가격 계산 불가능한 주문 타입: {order_type}")
        return None

    # @FEAT:order-queue @COMP:service @TYPE:core
    def rebalance_symbol(self, account_id: int, symbol: str, commit: bool = True) -> Dict[str, Any]:
        """심볼별 동적 재정렬 (핵심 알고리즘)

        ✅ v2: threading.Lock으로 동시성 보호 (조건 4)
        ✅ v2.2: Side별 분리 정렬 (Phase 2.2)
        ✅ v3: 타입 그룹별 4-way 분리 (Phase 2 - 2025-10-16)

        처리 단계:
        1. 제한 계산 (ExchangeLimits.calculate_symbol_limit)
        2. OpenOrder 조회 (DB) + PendingOrder 조회 (DB)
        3. 타입 그룹별 + Side별 4-way 분리 (LIMIT/STOP × BUY/SELL 독립 버킷)
        4. 각 버킷별 상위 5개 선택 (MAX_ORDERS_PER_SYMBOL_TYPE_SIDE=5)
        5. Sync:
           - 하위로 밀린 거래소 주문 → 취소 + 대기열 이동
           - 상위로 올라온 대기열 주문 → 거래소 실행

        Args:
            account_id: 계정 ID
            symbol: 심볼 (예: 'BTC/USDT')
            commit: 커밋 여부 (기본값: True)

        Returns:
            dict: {
                'success': bool,
                'cancelled': int,
                'executed': int,
                'total_orders': int,
                'active_orders': int,
                'pending_orders': int,
                'duration_ms': float
            }
        """
        # ✅ v2: 심볼별 Lock 획득 (조건 4)
        import threading
        lock_key = (account_id, symbol)
        with self._locks_lock:
            if lock_key not in self._rebalance_locks:
                self._rebalance_locks[lock_key] = threading.Lock()
            lock = self._rebalance_locks[lock_key]

        with lock:
            # 기존 재정렬 로직 (보호됨)
            # 성능 측정 시작
            start_time = time.time()

            # 전체 작업을 트랜잭션으로 감싸기
            try:
                # Step 1: 계정 및 제한 계산
                account = Account.query.get(account_id)
                if not account:
                    return {
                        'success': False,
                        'error': f'계정을 찾을 수 없습니다 (ID: {account_id})'
                    }

                # market_type 결정 (Strategy에서 추론)
                strategy_account = StrategyAccount.query.filter_by(account_id=account_id).first()
                if not strategy_account or not strategy_account.strategy:
                    logger.warning(f"계정 {account_id}에 연결된 전략이 없음, SPOT 기본값 사용")
                    market_type = 'SPOT'
                else:
                    market_type = strategy_account.strategy.market_type or 'SPOT'

                # 거래소별 제한 계산
                limits = ExchangeLimits.calculate_symbol_limit(
                    exchange=account.exchange,
                    market_type=market_type,
                    symbol=symbol
                )

                max_orders = limits['max_orders']
                max_stop_orders = limits['max_stop_orders']

                logger.info(
                    f"🔄 재정렬 시작 - 계정: {account_id}, 심볼: {symbol}, "
                    f"제한: {max_orders}개 (STOP: {max_stop_orders}개)"
                )

                # Step 2: 현재 주문 조회 (DB) - N+1 문제 방지를 위해 joinedload 사용
                from sqlalchemy.orm import joinedload

                active_orders = OpenOrder.query.join(StrategyAccount).filter(
                    StrategyAccount.account_id == account_id,
                    OpenOrder.symbol == symbol
                ).options(
                    joinedload(OpenOrder.strategy_account)  # N+1 방지
                ).all()

                # PendingOrder는 strategy_account 관계를 직접 사용하지 않으므로 joinedload 불필요
                pending_orders = PendingOrder.query.filter_by(
                    account_id=account_id,
                    symbol=symbol
                ).all()

                logger.info(
                    f"📋 현재 상태 - 거래소: {len(active_orders)}개, "
                    f"대기열: {len(pending_orders)}개"
                )

                # 🔍 디버깅: PendingOrder 상세 정보
                if pending_orders:
                    logger.info(f"🔍 PendingOrder 목록:")
                    for po in pending_orders:
                        logger.info(
                            f"  - ID: {po.id}, Price: {po.price}, "
                            f"Priority: {po.priority}, Created: {po.created_at}"
                        )

                # Step 3: 타입 그룹별 + Side별 4-way 분리
                limit_buy_orders = []
                limit_sell_orders = []
                stop_buy_orders = []
                stop_sell_orders = []

                # 타입 그룹 판별 헬퍼
                def get_order_type_group(order_type: str) -> Optional[str]:
                    """주문 타입의 그룹 반환 (LIMIT 또는 STOP)"""
                    for group_name, types in ORDER_TYPE_GROUPS.items():
                        if order_type.upper() in types:
                            return group_name
                    return None  # MARKET 등

                # Active 주문 4-way 분리
                for order in active_orders:
                    order_dict = {
                        'source': 'active',
                        'db_record': order,
                        'priority': OrderType.get_priority(order.order_type),
                        'sort_price': self._get_order_sort_price(order),
                        'created_at': order.created_at,
                    }

                    type_group = get_order_type_group(order.order_type)
                    side = order.side.upper()

                    if type_group == 'LIMIT' and side == 'BUY':
                        limit_buy_orders.append(order_dict)
                    elif type_group == 'LIMIT' and side == 'SELL':
                        limit_sell_orders.append(order_dict)
                    elif type_group == 'STOP' and side == 'BUY':
                        stop_buy_orders.append(order_dict)
                    elif type_group == 'STOP' and side == 'SELL':
                        stop_sell_orders.append(order_dict)
                    # MARKET 등은 무시 (재정렬 대상 아님)

                # Pending 주문 4-way 분리 (동일 로직)
                for order in pending_orders:
                    order_dict = {
                        'source': 'pending',
                        'db_record': order,
                        'priority': order.priority,
                        'sort_price': Decimal(str(order.sort_price)) if order.sort_price else None,
                        'created_at': order.created_at,
                    }

                    type_group = get_order_type_group(order.order_type)
                    side = order.side.upper()

                    if type_group == 'LIMIT' and side == 'BUY':
                        limit_buy_orders.append(order_dict)
                    elif type_group == 'LIMIT' and side == 'SELL':
                        limit_sell_orders.append(order_dict)
                    elif type_group == 'STOP' and side == 'BUY':
                        stop_buy_orders.append(order_dict)
                    elif type_group == 'STOP' and side == 'SELL':
                        stop_sell_orders.append(order_dict)

                logger.info(
                    f"📊 4-way 분리 완료 - "
                    f"LIMIT(buy:{len(limit_buy_orders)}, sell:{len(limit_sell_orders)}), "
                    f"STOP(buy:{len(stop_buy_orders)}, sell:{len(stop_sell_orders)})"
                )

                # Step 4: 각 버킷별 상위 5개 선택 (타입 그룹별 독립 할당)

                # 각 버킷 정렬 (정렬 키: priority ASC, sort_price DESC, created_at ASC)
                limit_buy_orders.sort(key=lambda x: (
                    x['priority'],
                    -(x['sort_price'] if x['sort_price'] else Decimal('-inf')),
                    x['created_at']
                ))
                limit_sell_orders.sort(key=lambda x: (
                    x['priority'],
                    -(x['sort_price'] if x['sort_price'] else Decimal('-inf')),
                    x['created_at']
                ))

                # STOP 주문 정렬 로직:
                # - STOP_BUY: 낮은 stop_price 우선 (121000 → 125000)
                #   → sort_price = -stop_price 저장 (-121000, -125000)
                #   → -(sort_price) ASC 정렬 = 121000, 125000 (낮은 값 먼저)
                # - STOP_SELL: 높은 stop_price 우선 (130000 → 125000)
                #   → sort_price = stop_price 저장 (130000, 125000)
                #   → -(sort_price) ASC 정렬 = -130000, -125000 (높은 절댓값 먼저 = 130000 우선)
                # - LIMIT 주문: priority → price → created_at (Lines 420-429)
                stop_buy_orders.sort(key=lambda x: (
                    -(x['sort_price'] if x['sort_price'] else Decimal('-inf')),  # DESC: -121000 먼저
                    x['created_at']
                ))
                stop_sell_orders.sort(key=lambda x: (
                    -(x['sort_price'] if x['sort_price'] else Decimal('inf')),  # DESC: 130000 먼저
                    x['created_at']
                ))

                # 각 버킷별 상위 5개 선택
                selected_limit_buy = self._select_top_orders_by_priority(
                    limit_buy_orders, MAX_ORDERS_PER_SYMBOL_TYPE_SIDE
                )
                selected_limit_sell = self._select_top_orders_by_priority(
                    limit_sell_orders, MAX_ORDERS_PER_SYMBOL_TYPE_SIDE
                )
                selected_stop_buy = self._select_top_orders_by_priority(
                    stop_buy_orders, MAX_ORDERS_PER_SYMBOL_TYPE_SIDE
                )
                selected_stop_sell = self._select_top_orders_by_priority(
                    stop_sell_orders, MAX_ORDERS_PER_SYMBOL_TYPE_SIDE
                )

                logger.info(
                    f"✅ 선택 완료 - "
                    f"LIMIT(buy:{len(selected_limit_buy)}/{len(limit_buy_orders)}, "
                    f"sell:{len(selected_limit_sell)}/{len(limit_sell_orders)}), "
                    f"STOP(buy:{len(selected_stop_buy)}/{len(stop_buy_orders)}, "
                    f"sell:{len(selected_stop_sell)}/{len(stop_sell_orders)})"
                )

                # STOP 그룹 정렬 기준 검증 (DEBUG)
                if selected_stop_buy or selected_stop_sell:
                    logger.debug(
                        f"🔍 STOP 정렬 - "
                        f"BUY top5 stop_price: {[float(o['db_record'].stop_price) if o['db_record'].stop_price else None for o in selected_stop_buy[:5]]}, "
                        f"SELL top5 stop_price: {[float(o['db_record'].stop_price) if o['db_record'].stop_price else None for o in selected_stop_sell[:5]]}"
                    )

                # 통합 (Step 5에서 사용)
                selected_orders = (selected_limit_buy + selected_limit_sell +
                                   selected_stop_buy + selected_stop_sell)
                all_orders = (limit_buy_orders + limit_sell_orders +
                              stop_buy_orders + stop_sell_orders)

                # Step 5: 액션 결정
                to_cancel = []  # 취소할 거래소 주문
                to_execute = []  # 실행할 대기열 주문

                for order in all_orders:
                    if order in selected_orders:
                        if order['source'] == 'pending':
                            to_execute.append(order['db_record'])
                    else:
                        if order['source'] == 'active':
                            to_cancel.append(order['db_record'])

                logger.info(
                    f"📤 실행 계획 - 취소: {len(to_cancel)}개, "
                    f"실행: {len(to_execute)}개"
                )

                # Step 6: 실제 실행
                cancelled_count = 0
                for open_order in to_cancel:
                    result = self._move_to_pending(open_order)
                    if result:
                        cancelled_count += 1

                # ✅ v2.1: 실패한 주문 수집
                executed_count = 0
                failed_orders = []

                for pending_order in to_execute:
                    result = self._execute_pending_order(pending_order)
                    if result['success']:
                        executed_count += 1
                    else:
                        # 실패 시 분류 정보 추가
                        error_type = self._classify_failure_type(result.get('error', ''))
                        failed_orders.append({
                            'pending_id': result.get('pending_id', pending_order.id),
                            'symbol': pending_order.symbol,
                            'error': result.get('error', 'Unknown error'),
                            'error_type': error_type,
                            'recoverable': self._is_recoverable(error_type)
                        })

                logger.info(
                    f"✅ 재정렬 완료 - 취소: {cancelled_count}개, "
                    f"실행: {executed_count}개, 실패: {len(failed_orders)}개"
                )

                # 호출자가 commit 제어
                if commit:
                    db.session.commit()

                # 성능 메트릭 업데이트
                duration_ms = (time.time() - start_time) * 1000
                self.metrics['total_rebalances'] += 1
                self.metrics['total_cancelled'] += cancelled_count
                self.metrics['total_executed'] += executed_count
                self.metrics['total_duration_ms'] += duration_ms
                self.metrics['avg_duration_ms'] = (
                    self.metrics['total_duration_ms'] / self.metrics['total_rebalances']
                )

                # 느린 재정렬 경고 (500ms 이상)
                if duration_ms > 500:
                    logger.warning(
                        f"⚠️ 느린 재정렬 감지 - {symbol}: {duration_ms:.2f}ms "
                        f"(취소: {cancelled_count}, 실행: {executed_count})"
                    )

                return {
                    'success': True,
                    'cancelled': cancelled_count,
                    'executed': executed_count,
                    'failed_orders': failed_orders,  # ✅ v2.1: 실패한 주문 목록 추가
                    'total_orders': len(all_orders),
                    'active_orders': len(active_orders) - cancelled_count + executed_count,
                    'pending_orders': len(pending_orders) + cancelled_count - executed_count,
                    'duration_ms': duration_ms
                }

            except Exception as e:
                # 호출자가 commit 제어
                if commit:
                    db.session.rollback()
                logger.error(f"❌ 재정렬 실패 (account_id={account_id}, symbol={symbol}): {e}")
                return {
                    'success': False,
                    'error': str(e),
                    'cancelled': 0,
                    'executed': 0
                }

    # @FEAT:order-queue @COMP:service @TYPE:helper
    def _get_order_sort_price(self, order: OpenOrder) -> Optional[Decimal]:
        """OpenOrder의 정렬 가격 계산

        OpenOrder는 sort_price 필드가 없으므로,
        order_type, side, price, stop_price로부터 계산합니다.
        """
        price = Decimal(str(order.price)) if order.price else None
        stop_price = Decimal(str(order.stop_price)) if order.stop_price else None

        return self._calculate_sort_price(
            order_type=order.order_type,
            side=order.side,
            price=price,
            stop_price=stop_price
        )

    # @FEAT:order-queue @COMP:service @TYPE:helper
    def _select_top_orders_by_priority(
        self,
        orders: List[Dict[str, Any]],
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """우선순위 기반 상위 주문 선택 (이미 정렬된 리스트에서 상위 N개)

        Args:
            orders: 이미 정렬된 주문 리스트
            limit: 선택할 주문 수 (기본값: 5)

        Returns:
            상위 N개 주문 리스트
        """
        return orders[:limit]

    # @FEAT:order-queue @COMP:service @TYPE:helper
    def _classify_failure_type(self, error_message: str) -> str:
        """
        거래소 에러 메시지를 분류하여 실패 유형 반환

        Args:
            error_message: 거래소 API 에러 메시지

        Returns:
            str: 'insufficient_balance', 'rate_limit', 'invalid_symbol',
                 'limit_exceeded', 'network_error', 'unknown'
        """
        error_lower = error_message.lower()

        # 잔고 부족
        if any(keyword in error_lower for keyword in ['balance', 'insufficient', 'funds']):
            return 'insufficient_balance'

        # Rate Limit
        if any(keyword in error_lower for keyword in ['rate limit', 'too many', 'throttle']):
            return 'rate_limit'

        # 잘못된 심볼
        if any(keyword in error_lower for keyword in ['invalid symbol', 'unknown symbol']):
            return 'invalid_symbol'

        # 제한 초과 (영구적)
        if 'exceeds' in error_lower or 'limit' in error_lower:
            return 'limit_exceeded'

        # 네트워크 오류
        if any(keyword in error_lower for keyword in ['timeout', 'network', 'connection']):
            return 'network_error'

        return 'unknown'

    # @FEAT:order-queue @COMP:service @TYPE:helper
    def _is_recoverable(self, error_type: str) -> bool:
        """
        실패 유형이 복구 가능한지 판단

        Args:
            error_type: 실패 유형 ('insufficient_balance', 'rate_limit', etc.)

        Returns:
            bool: True (재시도 가능), False (복구 불가능 → 알림)
        """
        # 복구 가능 (일시적 에러 → 스케줄러 재시도)
        recoverable_types = ['rate_limit', 'network_error', 'timeout']

        # 복구 불가능 (영구적 에러 → 알림 + 삭제)
        # non_recoverable_types = ['insufficient_balance', 'invalid_symbol', 'limit_exceeded']

        return error_type in recoverable_types

    # @FEAT:order-queue @COMP:service @TYPE:integration
    def _move_to_pending(self, open_order: OpenOrder) -> bool:
        """거래소 주문 → 대기열 이동

        Args:
            open_order: 취소할 OpenOrder

        Returns:
            bool: 성공 여부
        """
        try:
            # 1. 거래소에서 주문 취소
            cancel_result = self.service.cancel_order(
                order_id=open_order.exchange_order_id,
                symbol=open_order.symbol,
                account_id=open_order.strategy_account.account.id
            )

            if not cancel_result.get('success'):
                logger.error(
                    f"거래소 주문 취소 실패 - order_id: {open_order.exchange_order_id}, "
                    f"error: {cancel_result.get('error')}"
                )
                return False

            # 2. 대기열에 추가
            enqueue_result = self.enqueue(
                strategy_account_id=open_order.strategy_account_id,
                symbol=open_order.symbol,
                side=open_order.side,
                order_type=open_order.order_type,
                quantity=Decimal(str(open_order.quantity)),
                price=Decimal(str(open_order.price)) if open_order.price else None,
                stop_price=Decimal(str(open_order.stop_price)) if open_order.stop_price else None,
                market_type=open_order.market_type,
                reason='REBALANCED_OUT'
            )

            if not enqueue_result.get('success'):
                logger.error(
                    f"대기열 추가 실패 - order_id: {open_order.exchange_order_id}, "
                    f"error: {enqueue_result.get('error')}"
                )
                return False

            logger.info(
                f"🔄 거래소→대기열 이동 완료 - order_id: {open_order.exchange_order_id}"
            )
            return True

        except Exception as e:
            logger.error(f"거래소→대기열 이동 실패: {e}")
            return False

    # @FEAT:order-queue @COMP:service @TYPE:integration
    def _execute_pending_order(self, pending_order: PendingOrder) -> Dict[str, Any]:
        """대기열 주문 → 거래소 실행 (재정렬 시 호출)

        PendingOrder를 거래소에 제출합니다. 성공 시 OpenOrder로 전환되며,
        PendingOrder SSE 발송은 하지 않습니다 (거래소 이벤트는 별도 처리).

        Args:
            pending_order: 실행할 PendingOrder

        Returns:
            dict: {'success': bool, 'order_id': str (성공 시), 'error': str (실패 시)}
        """
        try:
            # TradingCore를 통해 거래소에 주문 실행
            strategy_account = pending_order.strategy_account
            if not strategy_account or not strategy_account.account:
                return {
                    'success': False,
                    'error': f'전략 계정을 찾을 수 없습니다 (ID: {pending_order.strategy_account_id})'
                }

            account = strategy_account.account
            strategy = strategy_account.strategy

            # TradingCore의 execute_trade 호출 (재정렬 경로 플래그 전달)
            result = self.service.execute_trade(
                strategy=strategy,
                symbol=pending_order.symbol,
                side=pending_order.side,
                quantity=Decimal(str(pending_order.quantity)),
                order_type=pending_order.order_type,
                price=Decimal(str(pending_order.price)) if pending_order.price else None,
                stop_price=Decimal(str(pending_order.stop_price)) if pending_order.stop_price else None,
                strategy_account_override=strategy_account,
                schedule_refresh=False,  # 재정렬 중에는 잔고 갱신 스킵
                from_pending_queue=True  # 재정렬 경로임을 명시 (대기열 재진입 방지)
            )

            if result.get('success'):
                # PendingOrder SSE 발송 제거 - 웹훅 응답 시 Batch SSE로 통합 (Phase 2)
                # 성공 시 대기열에서 제거 (커밋은 상위에서)
                db.session.delete(pending_order)

                logger.info(
                    f"✅ 대기열→거래소 실행 완료 - "
                    f"pending_id: {pending_order.id}, "
                    f"order_id: {result.get('order_id')}"
                )

                return {
                    'success': True,
                    'pending_id': pending_order.id,  # ✅ 원본 ID 추적
                    'order_id': result.get('order_id'),
                    'deleted': True  # PendingOrder 삭제 여부
                }
            else:
                # 실패 시 재시도 횟수 확인
                if pending_order.retry_count >= self.MAX_RETRY_COUNT:
                    logger.error(
                        f"❌ 대기열 주문 최대 재시도 초과 - "
                        f"pending_id: {pending_order.id}, "
                        f"재시도: {pending_order.retry_count}회, "
                        f"error: {result.get('error')}"
                    )

                    # ✅ v2.1: 텔레그램 알림 발송 (max retry 실패)
                    try:
                        error_type = self._classify_failure_type(result.get('error', ''))
                        if self.service and hasattr(self.service, 'telegram_service'):
                            self.service.telegram_service.send_order_failure_alert(
                                strategy=strategy,
                                account=account,
                                symbol=pending_order.symbol,
                                error_type=error_type,
                                error_message=f"최대 재시도 초과 ({self.MAX_RETRY_COUNT}회): {result.get('error')}"
                            )
                    except Exception as e:
                        logger.error(f"텔레그램 알림 발송 실패: {e}")

                    # PendingOrder SSE 발송 제거 - 웹훅 응답 시 Batch SSE로 통합 (Phase 2)
                    # 최대 재시도 초과 시 대기열에서 제거
                    db.session.delete(pending_order)

                    return {
                        'success': False,
                        'pending_id': pending_order.id,
                        'error': result.get('error'),
                        'deleted': True  # ✅ 최대 재시도 초과로 삭제
                    }
                else:
                    # 재시도 횟수 증가 (커밋은 상위에서)
                    pending_order.retry_count += 1

                    logger.warning(
                        f"❌ 대기열→거래소 실행 실패 - "
                        f"pending_id: {pending_order.id}, "
                        f"error: {result.get('error')}, "
                        f"재시도: {pending_order.retry_count}회"
                    )

                    return {
                        'success': False,
                        'pending_id': pending_order.id,
                        'error': result.get('error'),
                        'deleted': False  # ✅ 재시도 대기
                    }

        except Exception as e:
            logger.error(f"대기열 주문 실행 실패: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    # @FEAT:order-queue @COMP:service @TYPE:helper
    def get_pending_orders(
        self,
        account_id: Optional[int] = None,
        symbol: Optional[str] = None,
        strategy_account_id: Optional[int] = None
    ) -> List[PendingOrder]:
        """대기열 주문 조회

        Args:
            account_id: 계정 ID (선택적)
            symbol: 심볼 (선택적)
            strategy_account_id: 전략 계정 ID (선택적)

        Returns:
            List[PendingOrder]: 대기열 주문 목록 (우선순위 정렬)
        """
        query = PendingOrder.query

        if account_id:
            query = query.filter_by(account_id=account_id)
        if symbol:
            query = query.filter_by(symbol=symbol)
        if strategy_account_id:
            query = query.filter_by(strategy_account_id=strategy_account_id)

        # 우선순위 정렬
        query = query.order_by(
            PendingOrder.priority.asc(),
            PendingOrder.sort_price.desc(),
            PendingOrder.created_at.asc()
        )

        return query.all()

    # @FEAT:order-queue @COMP:service @TYPE:helper
    def clear_pending_orders(
        self,
        account_id: Optional[int] = None,
        symbol: Optional[str] = None,
        strategy_account_id: Optional[int] = None
    ) -> int:
        """대기열 주문 삭제

        Args:
            account_id: 계정 ID (선택적)
            symbol: 심볼 (선택적)
            strategy_account_id: 전략 계정 ID (선택적)

        Returns:
            int: 삭제된 주문 수
        """
        try:
            query = PendingOrder.query

            if account_id:
                query = query.filter_by(account_id=account_id)
            if symbol:
                query = query.filter_by(symbol=symbol)
            if strategy_account_id:
                query = query.filter_by(strategy_account_id=strategy_account_id)

            count = query.count()
            query.delete()
            db.session.commit()

            logger.info(f"🗑️ 대기열 정리 완료 - {count}개 주문 삭제")
            return count

        except Exception as e:
            db.session.rollback()
            logger.error(f"대기열 정리 실패: {e}")
            return 0

    # @FEAT:order-queue @COMP:service @TYPE:helper
    def get_metrics(self) -> Dict[str, Any]:
        """성능 메트릭 조회

        Returns:
            Dict: {
                'total_rebalances': int,
                'total_cancelled': int,
                'total_executed': int,
                'avg_duration_ms': float
            }
        """
        return self.metrics.copy()

    # @FEAT:order-queue @COMP:service @TYPE:helper
    def reset_metrics(self):
        """메트릭 초기화"""
        self.metrics = {
            'total_rebalances': 0,
            'total_cancelled': 0,
            'total_executed': 0,
            'total_duration_ms': 0,
            'avg_duration_ms': 0
        }
