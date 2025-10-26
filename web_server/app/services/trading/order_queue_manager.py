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
from app.constants import OrderType, ORDER_TYPE_GROUPS, MAX_ORDERS_PER_SYMBOL_TYPE_SIDE
from app.services.utils import to_decimal
from app.services.exchange import exchange_service

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
        commit: bool = True,  # ✅ v2: 트랜잭션 제어 (조건 2)
        webhook_received_at: Optional[datetime] = None  # ✅ Infinite Loop Fix: 웹훅 수신 시각 보존
    ) -> Dict[str, Any]:
        """대기열에 주문 추가 (Order List SSE 발송, Toast SSE는 Batch 통합)

        PendingOrder 생성 시 Order List SSE를 발송하여 열린 주문 테이블을 실시간 업데이트합니다.
        Toast 알림은 웹훅 응답 시 order_type별 집계 Batch SSE로 발송됩니다.

        Infinite Loop Fix (2025-10-26):
            - webhook_received_at 파라미터 추가로 원본 웹훅 수신 시각 보존
            - PendingOrder → OpenOrder 전환 시 타임스탬프 손실 방지
            - 동일 시각 주문의 정렬 순서 안정성 보장
            - See Migration: 20251026_add_webhook_received_at

        **Transaction Safety**:
        - SSE는 DB 커밋 완료 후에만 발송됩니다 (commit=True 시).
        - commit=False 사용 시 호출자가 명시적으로 커밋하고 SSE 발송을 별도 처리해야 합니다.

        **SSE Emission**:
        - Event Type: 'order_created'
        - Condition: strategy 정보가 있고, event_emitter가 사용 가능할 때만 발송
        - Failure: SSE 발송 실패는 비치명적 (경고 로그, 주문 생성은 계속)

        Args:
            strategy_account_id: 전략 계정 ID
            symbol: 거래 심볼
            side: 주문 방향 (buy/sell)
            order_type: 주문 타입 (LIMIT/STOP_LIMIT/STOP_MARKET)
            quantity: 주문 수량
            price: LIMIT 가격 (선택적)
            stop_price: STOP 트리거 가격 (선택적)
            market_type: 마켓 타입 (SPOT/FUTURES)
            reason: 대기열 진입 사유
            commit: 즉시 DB 커밋 여부 (기본값: True, DB 커밋 + SSE 발송)

        Returns:
            dict: 작업 결과

            성공 시:
                {
                    'success': True,
                    'pending_order_id': int - 생성된 PendingOrder ID,
                    'priority': int - 주문 우선순위 (낮을수록 먼저 실행),
                    'sort_price': float - 정렬용 가격,
                    'message': str - 성공 메시지
                }

            실패 시:
                {
                    'success': False,
                    'error': str - 오류 메시지
                }

        Raises:
            None (모든 오류는 dict 반환값으로 처리)
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

            # @FEAT:pending-order-sse @COMP:service @TYPE:helper
            # 📡 SSE 발송용 user_id 사전 추출
            # - 커밋 전 추출: SQLAlchemy 세션 만료 방지
            # - None 체크: strategy 관계 누락 시 SSE 스킵 (주문 생성은 계속)
            user_id_for_sse = None
            if strategy_account.strategy:
                user_id_for_sse = strategy_account.strategy.user_id
                logger.debug(f"✅ user_id 추출 성공: {user_id_for_sse}")
            else:
                logger.warning(
                    f"⚠️ PendingOrder SSE 발송 스킵: strategy 정보 없음 "
                    f"(strategy_account_id: {strategy_account_id})"
                )

            # 우선순위 계산
            priority = OrderType.get_priority(order_type)

            # 정렬용 가격 계산
            sort_price = self._calculate_sort_price(order_type, side, price, stop_price)

            # @FEAT:order-tracking @COMP:service @TYPE:core
            # PendingOrder 레코드 생성 (webhook_received_at 포함)
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
                reason=reason,
                webhook_received_at=webhook_received_at or datetime.utcnow()  # ✅ 웹훅 수신 시각
            )

            db.session.add(pending_order)

            # commit=False일 때도 ID 할당 (배치 SSE 발송용)
            # flush()는 ID를 할당하지만 트랜잭션은 열린 상태 유지
            if not commit:
                db.session.flush()

            # 트랜잭션 안전성: SSE 발송은 DB 커밋 완료 후 (commit=True 시)
            if commit:
                db.session.commit()

                # @FEAT:pending-order-sse @COMP:service @TYPE:core @DEPS:event-emitter
                # 📡 Order List SSE 발송 (DB 커밋 완료 후, 실시간 UI 업데이트)
                # ⚠️ Toast SSE는 웹훅 응답에서 order_type별 집계 Batch로 발송 (core.py)
                logger.debug(
                    f"🔍 SSE 발송 조건 확인: "
                    f"self.service={self.service is not None}, "
                    f"has_event_emitter={hasattr(self.service, 'event_emitter') if self.service else 'N/A'}, "
                    f"user_id_for_sse={user_id_for_sse}"
                )

                if self.service and hasattr(self.service, 'event_emitter') and user_id_for_sse:
                    logger.debug("✅ SSE 발송 조건 충족 - emit_pending_order_event 호출 시작")
                    try:
                        self.service.event_emitter.emit_pending_order_event(
                            event_type='order_created',
                            pending_order=pending_order,
                            user_id=user_id_for_sse
                        )
                        logger.debug(
                            f"📡 [SSE] PendingOrder 생성 → Order List 업데이트: "
                            f"ID={pending_order.id}, user_id={user_id_for_sse}, symbol={symbol}"
                        )
                    except Exception as e:
                        logger.warning(
                            f"⚠️ PendingOrder Order List SSE 발송 실패 (비치명적): {e}"
                        )
                else:
                    logger.warning(
                        f"⚠️ SSE 발송 조건 미충족 - 스킵: "
                        f"service={self.service is not None}, "
                        f"event_emitter={hasattr(self.service, 'event_emitter') if self.service else False}, "
                        f"user_id={user_id_for_sse is not None}"
                    )

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
        ✅ v4: webhook_received_at 정렬 키 사용 (Infinite Loop Fix - 2025-10-26)

        Infinite Loop Fix (2025-10-26):
            - 정렬 키 변경: created_at → webhook_received_at (+ DB ID tie-breaker)
            - PendingOrder ↔ OpenOrder 전환 시 타임스탬프 안정성 보장
            - 동일 시각 주문의 정렬 순서 결정성 확보
            - See Migration: 20251026_add_webhook_received_at

        처리 단계:
        1. OpenOrder 조회 (DB) + PendingOrder 조회 (DB)
        2. 타입 그룹별 + Side별 4-way 분리 (LIMIT/STOP × BUY/SELL 독립 버킷)
        3. 각 버킷별 상위 2개 선택 (MAX_ORDERS_PER_SYMBOL_TYPE_SIDE=2)
        4. Sync:
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

                # 단일 상수 기반 제한 (거래소 구분 없음)
                max_orders_per_type_side = MAX_ORDERS_PER_SYMBOL_TYPE_SIDE  # 2개

                logger.info(
                    f"🔄 재정렬 시작 - 계정: {account_id}, 심볼: {symbol}, "
                    f"타입별 Side당 제한: {max_orders_per_type_side}개 "
                    f"(LIMIT BUY/SELL 각 2개, STOP BUY/SELL 각 2개)"
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

                # @FEAT:order-tracking @COMP:service @TYPE:core
                # Active 주문 4-way 분리 (webhook_received_at 포함)
                for order in active_orders:
                    order_dict = {
                        'source': 'active',
                        'db_record': order,
                        'priority': OrderType.get_priority(order.order_type),
                        'sort_price': self._get_order_sort_price(order),
                        'created_at': order.created_at,
                        'webhook_received_at': order.webhook_received_at  # ✅ 웹훅 수신 시각
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

                # @FEAT:order-tracking @COMP:service @TYPE:core
                # Pending 주문 4-way 분리 (webhook_received_at 포함)
                for order in pending_orders:
                    order_dict = {
                        'source': 'pending',
                        'db_record': order,
                        'priority': order.priority,
                        'sort_price': Decimal(str(order.sort_price)) if order.sort_price else None,
                        'created_at': order.created_at,
                        'webhook_received_at': order.webhook_received_at  # ✅ 웹훅 수신 시각
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

                # Step 4: 각 버킷별 상위 2개 선택 (타입 그룹별 독립 할당)

                # @FEAT:order-tracking @COMP:service @TYPE:core
                # 각 버킷 정렬 (정렬 키: priority ASC, sort_price DESC, webhook_received_at ASC, DB ID ASC)
                limit_buy_orders.sort(key=lambda x: (
                    x['priority'],
                    -(x['sort_price'] if x['sort_price'] else Decimal('-inf')),
                    x['webhook_received_at'] or x['created_at'],  # ✅ 웹훅 수신 시각 우선
                    x['db_record'].id  # ✅ Tie-breaker
                ))
                limit_sell_orders.sort(key=lambda x: (
                    x['priority'],
                    -(x['sort_price'] if x['sort_price'] else Decimal('-inf')),
                    x['webhook_received_at'] or x['created_at'],  # ✅ 웹훅 수신 시각 우선
                    x['db_record'].id  # ✅ Tie-breaker
                ))

                # @FEAT:order-tracking @COMP:service @TYPE:core
                # STOP 주문 정렬 로직:
                # - STOP_BUY: 낮은 stop_price 우선 (121000 → 125000)
                #   → sort_price = -stop_price 저장 (-121000, -125000)
                #   → -(sort_price) ASC 정렬 = 121000, 125000 (낮은 값 먼저)
                # - STOP_SELL: 높은 stop_price 우선 (130000 → 125000)
                #   → sort_price = stop_price 저장 (130000, 125000)
                #   → -(sort_price) ASC 정렬 = -130000, -125000 (높은 절댓값 먼저 = 130000 우선)
                # - LIMIT 주문: priority → price → webhook_received_at → id
                stop_buy_orders.sort(key=lambda x: (
                    -(x['sort_price'] if x['sort_price'] else Decimal('-inf')),  # DESC: -121000 먼저
                    x['webhook_received_at'] or x['created_at'],  # ✅ 웹훅 수신 시각 우선
                    x['db_record'].id  # ✅ Tie-breaker
                ))
                stop_sell_orders.sort(key=lambda x: (
                    -(x['sort_price'] if x['sort_price'] else Decimal('inf')),  # DESC: 130000 먼저
                    x['webhook_received_at'] or x['created_at'],  # ✅ 웹훅 수신 시각 우선
                    x['db_record'].id  # ✅ Tie-breaker
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
                        f"BUY top2 stop_price: {[float(o['db_record'].stop_price) if o['db_record'].stop_price else None for o in selected_stop_buy[:2]]}, "
                        f"SELL top2 stop_price: {[float(o['db_record'].stop_price) if o['db_record'].stop_price else None for o in selected_stop_sell[:2]]}"
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

                # Phase 2: Execute pending orders via batch API
                if to_execute:
                    batch_result = self._process_pending_batch(
                        pending_orders=to_execute
                    )

                    executed_count = batch_result['executed']
                    failed_count = batch_result['failed']

                    logger.info(
                        f"🎯 재정렬 완료 (배치) - "
                        f"취소: {cancelled_count}개, "
                        f"성공: {executed_count}개, "
                        f"실패: {failed_count}개"
                    )
                else:
                    executed_count = 0
                    failed_count = 0

                    logger.info(
                        f"✅ 재정렬 완료 - 취소: {cancelled_count}개 "
                        f"(실행 대상 없음)"
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
                    'failed': failed_count if to_execute else 0,  # Phase 2: Batch result
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

    # @FEAT:webhook-batch-queue @COMP:service @TYPE:core
    def _process_pending_batch(
        self,
        pending_orders: List[PendingOrder]
    ) -> Dict[str, Any]:
        """
        Process pending orders via exchange batch API (80% API call reduction)

        @FEAT:webhook-batch-queue @COMP:service @TYPE:core
        Phase 2: Rebalancer integration with multi-account support

        Infinite Loop Fix (2025-10-26):
            - PendingOrder의 webhook_received_at을 OpenOrder로 전달
            - create_open_order_record 호출 시 webhook_received_at 파라미터 추가
            - 타임스탬프 손실 없이 주문 상태 전환 보장
            - See Migration: 20251026_add_webhook_received_at

        Architecture:
            1. Group by account_id → independent processing (exception isolation)
            2. Batch in chunks of 5 (Binance limit; Bybit supports 10 but unified)
            3. Index-based result mapping (result[i] ↔ pending_order[i])
            4. Per-order error classification (permanent → delete, temporary → retry)
            5. Caller controls commit (transaction boundary)

        Args:
            pending_orders (List[PendingOrder]): Orders to execute via batch API

        Returns:
            Dict[str, Any]:
                - 'success': bool (overall status)
                - 'executed': int (successfully created OpenOrders)
                - 'failed': int (retry or deleted after MAX_RETRY_COUNT=5)

        Performance: N orders = ceil(N/5) API calls (vs N individual calls)

        Error Isolation:
            - Account failure doesn't block other accounts
            - Batch failure: all orders in batch marked for retry
            - Retry exhaustion: delete after 5 attempts (see MAX_RETRY_COUNT)

        Phase 1 Consistency: Reuses _classify_failure_type(), MAX_RETRY_COUNT
        See Also: _execute_pending_order() (deprecated), _emit_pending_order_sse()
        """

        if not pending_orders:
            return {'success': True, 'executed': 0, 'failed': 0}

        # Step 1: Group orders by account_id (multi-account support)
        from collections import defaultdict
        orders_by_account = defaultdict(list)

        # Fix: 카운터 변수 초기화 누락 수정 (NameError 방지)
        success_count = 0
        failed_count = 0

        for pending_order in pending_orders:
            # Bug Fix: Prevent AttributeError if strategy_account is None
            if not pending_order.strategy_account:
                logger.error(
                    f"[_process_pending_batch] PendingOrder {pending_order.id} has no strategy_account, skipping"
                )
                failed_count += 1  # Include skipped orders in failed count for accurate metrics
                continue

            account_id = pending_order.strategy_account.account_id
            orders_by_account[account_id].append(pending_order)

        logger.info(f"📦 배치 처리 시작 - {len(orders_by_account)}개 계좌, {len(pending_orders)}개 주문")

        # Step 2: Process each account independently (exception isolation)
        for account_id, account_orders in orders_by_account.items():
            try:
                # Get account info
                first_order = account_orders[0]
                strategy_account = first_order.strategy_account
                account = strategy_account.account
                symbol = first_order.symbol
                market_type = first_order.market_type

                logger.info(f"  🔄 Account {account_id} ({account.name}): {len(account_orders)}개 주문 처리 중...")

                # Batch size 5: Binance limit (Bybit=10, but unified to 5 for cross-exchange consistency)
                for i in range(0, len(account_orders), 5):
                    batch = account_orders[i:i+5]

                    logger.debug(f"    ⚙️  배치 {i//5 + 1}: {len(batch)}개 주문")

                    # Step 1: Convert to CCXT format
                    # Why: Exchange API requires lowercase side, float types, stopPrice in params
                    # Transforms: PendingOrder (Decimal, 'BUY') → CCXT (float, 'buy')
                    exchange_orders = []
                    for pending_order in batch:
                        order_dict = {
                            'symbol': pending_order.symbol,
                            'side': pending_order.side.lower(),
                            'type': pending_order.order_type,
                            'amount': float(pending_order.quantity),
                        }

                        # Add price if LIMIT order
                        if pending_order.price:
                            order_dict['price'] = float(pending_order.price)

                        # Add stop_price if STOP order
                        if pending_order.stop_price:
                            order_dict['params'] = {'stopPrice': float(pending_order.stop_price)}

                        exchange_orders.append(order_dict)

                    # Step 2: Execute batch API (1 call for 5 orders = 80% reduction)
                    # Why batch size 5: Binance limit (Bybit supports 10 but we unify to 5)
                    # Upbit fallback: No batch API, uses individual execution
                    # @FIX: Issue #3 - Use global singleton exchange_service (matches core.py:19 pattern)
                    # Fixed AttributeError: 'TradingCore' object has no attribute 'exchange_service'
                    try:
                        batch_result = exchange_service.create_batch_orders(
                            account=account,
                            orders=exchange_orders,  # All 5 orders at once
                            market_type=market_type.lower(),
                            account_id=account.id
                        )

                        logger.info(f"    ✅ 배치 API 호출 성공: {len(exchange_orders)}개 주문")

                    except Exception as batch_error:
                        # Batch API call failed - mark all as failed
                        logger.error(f"    ❌ 배치 API 호출 실패: {batch_error}")

                        for pending_order in batch:
                            # Classify failure type
                            failure_type = self._classify_failure_type(str(batch_error))

                            if failure_type == "permanent":
                                db.session.delete(pending_order)
                                logger.warning(f"    🗑️  영구 실패 - 삭제: PendingOrder {pending_order.id}")
                            elif failure_type == "temporary":
                                pending_order.retry_count += 1
                                # Bug Fix: Changed > to >= for correct retry count (5 retries: 0→1→2→3→4→5)
                                # MAX_RETRY_COUNT=5 means "delete after 5 retries"
                                if pending_order.retry_count >= self.MAX_RETRY_COUNT:
                                    db.session.delete(pending_order)
                                    logger.warning(
                                        f"    🗑️  재시도 한계 초과 - 삭제: PendingOrder {pending_order.id} "
                                        f"(retry_count={pending_order.retry_count}, max={self.MAX_RETRY_COUNT})"
                                    )
                                    self._emit_pending_order_sse(account_id, symbol)
                                else:
                                    logger.warning(
                                        f"    ⏳ 재시도 예약: PendingOrder {pending_order.id} "
                                        f"({pending_order.retry_count}/{self.MAX_RETRY_COUNT})"
                                    )

                        failed_count += len(batch)
                        continue  # Skip to next batch

                    # Step 3: Parse results via index mapping (result[i] ↔ pending_order[i])
                    # Why index-based: Exchange preserves request order, simpler than ID matching
                    # Error detection: 'code' (Binance), 'error_code' (Upbit), 'status'=='error' (generic)
                    # Success: OpenOrder → SSE → Delete | Failure: Classify → Retry or Delete
                    batch_results = batch_result.get('results', [])

                    # Index-based mapping: Simpler than order ID matching, exchange preserves request order
                    for idx, result_item in enumerate(batch_results):
                        if idx >= len(batch):
                            logger.warning(f"    ⚠️  결과 인덱스 초과: {idx} >= {len(batch)}")
                            break

                        pending_order = batch[idx]

                        # Multi-exchange error detection (plan requirement)
                        is_exchange_error = (
                            'code' in result_item or          # Binance
                            'error_code' in result_item or     # Upbit
                            result_item.get('status') == 'error'  # Generic
                        )

                        if is_exchange_error:
                            # FAILURE PATH
                            error_msg = result_item.get('msg') or result_item.get('message', 'Unknown error')
                            logger.error(f"    ❌ 주문 실패: PendingOrder {pending_order.id}, 사유: {error_msg}")

                            # Classify failure type
                            failure_type = self._classify_failure_type(error_msg)

                            if failure_type == "permanent":
                                db.session.delete(pending_order)
                                logger.warning(f"    🗑️  영구 실패 - 삭제: PendingOrder {pending_order.id}")
                            elif failure_type == "temporary":
                                pending_order.retry_count += 1
                                # Bug Fix: Changed > to >= for correct retry count (5 retries: 0→1→2→3→4→5)
                                # MAX_RETRY_COUNT=5 means "delete after 5 retries"
                                if pending_order.retry_count >= self.MAX_RETRY_COUNT:
                                    db.session.delete(pending_order)
                                    logger.warning(
                                        f"    🗑️  재시도 한계 초과 - 삭제: PendingOrder {pending_order.id} "
                                        f"(retry_count={pending_order.retry_count}, max={self.MAX_RETRY_COUNT})"
                                    )
                                    self._emit_pending_order_sse(account_id, symbol)
                                else:
                                    logger.warning(
                                        f"    ⏳ 재시도 예약: PendingOrder {pending_order.id} "
                                        f"({pending_order.retry_count}/{self.MAX_RETRY_COUNT})"
                                    )

                            failed_count += 1
                        else:
                            # SUCCESS PATH
                            # Extract 'order' field from batch result (batch API wraps order data)
                            order_data = result_item.get('order', result_item)

                            # Normalize field name: Batch API uses 'id' internally, but we need 'order_id'
                            if 'order_id' not in order_data:
                                if 'id' in order_data:
                                    order_data['order_id'] = order_data['id']
                                else:
                                    logger.error(f"    ❌ Batch API response missing both 'id' and 'order_id': {result_item}")
                                    failed_count += 1
                                    continue

                            logger.info(f"    ✅ 주문 성공: PendingOrder {pending_order.id} → OpenOrder")
                            logger.debug(f"    🔍 order_data: order_id={order_data.get('order_id')}, status={order_data.get('status')}, order_type={order_data.get('order_type')}")

                            # @FEAT:order-tracking @COMP:service @TYPE:core
                            # Create OpenOrder record (PendingOrder의 webhook_received_at 전달)
                            create_result = self.service.order_manager.create_open_order_record(
                                strategy_account=strategy_account,
                                order_result=order_data,
                                symbol=pending_order.symbol,
                                side=pending_order.side,
                                order_type=pending_order.order_type,
                                quantity=pending_order.quantity,
                                price=pending_order.price,
                                stop_price=pending_order.stop_price,
                                webhook_received_at=pending_order.webhook_received_at  # ✅ 웹훅 수신 시각 전달
                            )
                            logger.debug(f"    🔍 create_open_order_record 결과: {create_result}")

                            # Emit OpenOrder created SSE event (if order was saved to DB)
                            if create_result.get('success') and pending_order.strategy_account:
                                strategy = pending_order.strategy_account.strategy
                                if strategy and self.service and hasattr(self.service, 'event_emitter'):
                                    try:
                                        # Ensure account_id is in order_data for SSE emission
                                        if 'account_id' not in order_data:
                                            order_data['account_id'] = account.id

                                        self.service.event_emitter.emit_order_events_smart(
                                            strategy=strategy,
                                            symbol=pending_order.symbol,
                                            side=pending_order.side,
                                            quantity=pending_order.quantity,
                                            order_result=order_data
                                        )
                                        logger.info(f"    📡 OpenOrder SSE 이벤트 발송 완료: {pending_order.symbol}")
                                    except Exception as sse_error:
                                        logger.warning(f"    ⚠️ OpenOrder SSE 발송 실패 (비치명적): {sse_error}")

                            # @FEAT:webhook-order @FEAT:event-sse @COMP:service @TYPE:helper
                            # 배치 실행 성공 후 PendingOrder 삭제 + SSE 발송
                            # PendingOrder 삭제 SSE 이벤트 발송 (배치 실행 성공 - 삭제 전)
                            if pending_order.strategy_account and pending_order.strategy_account.strategy:
                                user_id = pending_order.strategy_account.strategy.user_id
                                if self.service and hasattr(self.service, 'event_emitter'):
                                    try:
                                        self.service.event_emitter.emit_pending_order_event(
                                            event_type='order_cancelled',
                                            pending_order=pending_order,
                                            user_id=user_id
                                        )
                                    except Exception as sse_error:
                                        logger.warning(f"⚠️ SSE 발송 실패 (비치명적): {sse_error}")

                            # Delete PendingOrder
                            db.session.delete(pending_order)

                            success_count += 1

                logger.info(f"  ✅ Account {account_id} 완료 - 성공: {success_count}, 실패: {failed_count}")

            except Exception as account_error:
                # Account-level exception: log and continue with other accounts
                logger.error(f"  ❌ Account {account_id} 전체 실패: {account_error}")
                failed_count += len(account_orders)
                continue  # ✅ Exception Isolation: Other accounts continue processing

        # NO internal commit - caller controls transaction boundary (rebalance_symbol commits atomically)
        return {
            'success': True,
            'executed': success_count,
            'failed': failed_count
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
            str: 'permanent' or 'temporary'
                - permanent: 영구 실패 (삭제 필요) - 잔고 부족, 잘못된 심볼, 제한 초과
                - temporary: 일시적 실패 (재시도 가능) - Rate Limit, 네트워크 오류
        """
        error_lower = error_message.lower()

        # 일시적 오류 (재시도 가능)
        temporary_keywords = ['rate limit', 'too many', 'throttle', 'timeout', 'network', 'connection']
        if any(keyword in error_lower for keyword in temporary_keywords):
            return 'temporary'

        # 영구적 오류 (재시도 불가)
        permanent_keywords = ['balance', 'insufficient', 'funds', 'invalid symbol', 'unknown symbol', 'exceeds']
        if any(keyword in error_lower for keyword in permanent_keywords):
            return 'permanent'

        # 기본값: 일시적 오류로 분류 (재시도 기회 부여)
        return 'temporary'

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

    # @FEAT:webhook-batch-queue @COMP:service @TYPE:helper
    def _emit_pending_order_sse(self, account_id: int, symbol: str):
        """
        Emit SSE event for PendingOrder changes (DRY helper)

        @FEAT:webhook-batch-queue @COMP:service @TYPE:helper
        Reduces SSE emission code duplication (20 lines → 1 method call)

        Args:
            account_id (int): Account ID for event filtering
            symbol (str): Trading pair symbol (e.g., 'BTC/USDT')

        Behavior:
            - Emits 'order_list_update' SSE event
            - Frontend updates Order List table in real-time
            - Gracefully handles emission failures (warning log only)

        Usage:
            Called after PendingOrder deletion (success, retry exhaustion, permanent failure)

        Example:
            # After successful batch execution
            self._emit_pending_order_sse(account_id=1, symbol='BTC/USDT')
            # Frontend receives: {'type': 'order_list_update', 'account_id': 1, 'symbol': 'BTC/USDT'}
        """
        try:
            # Import SSE emitter
            from web_server.app.services.sse.emitter import emit_order_list_update

            # Emit order list update event
            emit_order_list_update(
                account_id=account_id,
                symbol=symbol,
                event_type='pending_order_cancelled'
            )

        except Exception as e:
            logger.warning(f"⚠️  SSE 발송 실패 (account_id={account_id}, symbol={symbol}): {e}")

    # @FEAT:order-queue @COMP:service @TYPE:integration
    def _move_to_pending(self, open_order: OpenOrder) -> bool:
        """거래소 주문 → 대기열 이동

        Infinite Loop Fix (2025-10-26):
            - OpenOrder의 webhook_received_at 보존하여 PendingOrder로 전달
            - 재정렬 시 타임스탬프 손실 방지
            - See Migration: 20251026_add_webhook_received_at

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

            # @FEAT:order-tracking @COMP:service @TYPE:core
            # 2. 대기열에 추가 (OpenOrder의 webhook_received_at 보존)
            webhook_received_at = open_order.webhook_received_at or open_order.created_at

            enqueue_result = self.enqueue(
                strategy_account_id=open_order.strategy_account_id,
                symbol=open_order.symbol,
                side=open_order.side,
                order_type=open_order.order_type,
                quantity=Decimal(str(open_order.quantity)),
                price=Decimal(str(open_order.price)) if open_order.price else None,
                stop_price=Decimal(str(open_order.stop_price)) if open_order.stop_price else None,
                market_type=open_order.market_type,
                reason='REBALANCED_OUT',
                webhook_received_at=webhook_received_at,  # ✅ 웹훅 수신 시각 보존
                commit=False  # 트랜잭션 제어
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
        """대기열 주문 → 거래소 실행 및 Order List SSE 발송 (재정렬 시 호출)

        PendingOrder를 거래소에 제출합니다. 성공 시 OpenOrder로 전환되고,
        Order List SSE를 발송하여 열린 주문 테이블을 실시간 업데이트합니다.

        **SSE 발송 정책** (재정렬 성공 또는 최대 재시도 초과 시):
        - Event Type: 'order_cancelled' (대기열 → 거래소 전환)
        - 조건: strategy 정보가 있고, event_emitter가 사용 가능할 때
        - 타이밍: db.session.delete() **전**에 발송 (객체 접근 보장)
        - 실패 처리: SSE 발송 실패는 비치명적 (경고 로그 후 삭제 계속)

        Args:
            pending_order: 실행할 PendingOrder

        Returns:
            dict: 재정렬 결과

            성공 시:
                {
                    'success': True,
                    'pending_id': int - 삭제된 PendingOrder ID (추적용),
                    'order_id': str - 생성된 거래소 주문 ID,
                    'deleted': True - PendingOrder 삭제 여부
                }

            실패 시:
                {
                    'success': False,
                    'error': str - 오류 메시지,
                    'retry_count': int - 현재 재시도 횟수 (최대 5회)
                }
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
                # 재정렬 성공 - 거래소 주문 생성됨
                logger.info(
                    f"✅ 재정렬 성공: PendingOrder {pending_order.id}번 → OpenOrder {result.get('order_id')}"
                )

                # 📡 Order List SSE 발송 (삭제 전, Toast SSE는 웹훅 응답 시 Batch 통합)
                # @FEAT:pending-order-sse @COMP:service @TYPE:core @DEPS:event-emitter
                user_id_for_sse = None
                if pending_order.strategy_account and pending_order.strategy_account.strategy:
                    user_id_for_sse = pending_order.strategy_account.strategy.user_id
                else:
                    logger.warning(
                        f"⚠️ PendingOrder 삭제 SSE 발송 스킵: strategy 정보 없음 "
                        f"(pending_order_id={pending_order.id})"
                    )

                if self.service and hasattr(self.service, 'event_emitter') and user_id_for_sse:
                    try:
                        self.service.event_emitter.emit_pending_order_event(
                            event_type='order_cancelled',
                            pending_order=pending_order,
                            user_id=user_id_for_sse
                        )
                        logger.debug(
                            f"📡 [SSE] PendingOrder 삭제 (재정렬 성공) → Order List 업데이트: "
                            f"ID={pending_order.id}, user_id={user_id_for_sse}, symbol={pending_order.symbol}"
                        )
                    except Exception as e:
                        logger.warning(
                            f"⚠️ PendingOrder Order List SSE 발송 실패 (비치명적): "
                            f"ID={pending_order.id}, error={e}"
                        )

                # DB에서 제거 (커밋은 상위에서)
                db.session.delete(pending_order)

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

                    # 📡 Order List SSE 발송 (최대 재시도 초과 → 삭제 전)
                    # @FEAT:pending-order-sse @COMP:service @TYPE:core @DEPS:event-emitter
                    user_id_for_sse = None
                    if pending_order.strategy_account and pending_order.strategy_account.strategy:
                        user_id_for_sse = pending_order.strategy_account.strategy.user_id
                    else:
                        logger.warning(
                            f"⚠️ PendingOrder 삭제 SSE 발송 스킵: strategy 정보 없음 "
                            f"(pending_order_id={pending_order.id})"
                        )

                    if self.service and hasattr(self.service, 'event_emitter') and user_id_for_sse:
                        try:
                            self.service.event_emitter.emit_pending_order_event(
                                event_type='order_cancelled',
                                pending_order=pending_order,
                                user_id=user_id_for_sse
                            )
                            logger.debug(
                                f"📡 [SSE] PendingOrder 삭제 (최대 재시도 초과) → Order List 업데이트: "
                                f"ID={pending_order.id}, user_id={user_id_for_sse}, symbol={pending_order.symbol}"
                            )
                        except Exception as e:
                            logger.warning(
                                f"⚠️ PendingOrder Order List SSE 발송 실패 (비치명적): "
                                f"ID={pending_order.id}, error={e}"
                            )

                    # PendingOrder 삭제 (최대 재시도 초과)
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
