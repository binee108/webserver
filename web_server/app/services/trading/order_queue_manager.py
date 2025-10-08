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
from app.constants import ExchangeLimits, OrderType
from app.services.utils import to_decimal

logger = logging.getLogger(__name__)


class OrderQueueManager:
    """주문 대기열 관리자

    핵심 기능:
    1. 대기열에 주문 추가 (enqueue)
    2. 심볼별 동적 재정렬 (rebalance_symbol)
    3. 거래소 주문 ↔ 대기열 주문 간 이동
    4. 성능 메트릭 수집
    """

    MAX_RETRY_COUNT = 5  # 재시도 횟수 제한 상수

    def __init__(self, service: Optional[object] = None) -> None:
        self.service = service
        self.metrics = {
            'total_rebalances': 0,
            'total_cancelled': 0,
            'total_executed': 0,
            'total_duration_ms': 0,
            'avg_duration_ms': 0
        }

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
        reason: str = 'QUEUE_LIMIT'
    ) -> Dict[str, Any]:
        """대기열에 주문 추가

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

        Returns:
            dict: {
                'success': bool,
                'pending_order_id': int,
                'priority': int,
                'sort_price': Decimal,
                'message': str
            }
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
            db.session.commit()

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
            db.session.rollback()
            logger.error(f"대기열 추가 실패: {e}")
            return {
                'success': False,
                'error': str(e)
            }

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

    def rebalance_symbol(self, account_id: int, symbol: str, commit: bool = True) -> Dict[str, Any]:
        """심볼별 동적 재정렬 (핵심 알고리즘)

        처리 단계:
        1. 제한 계산 (ExchangeLimits.calculate_symbol_limit)
        2. OpenOrder 조회 (DB) + PendingOrder 조회 (DB)
        3. 전체 통합 정렬 (priority, sort_price, created_at)
        4. 상위 N개 선택 (STOP 이중 제한 적용)
        5. Sync:
           - 하위로 밀린 거래소 주문 → 취소 + 대기열 이동
           - 상위로 올라온 대기열 주문 → 거래소 실행

        Args:
            account_id: 계정 ID
            symbol: 거래 심볼
            commit: 트랜잭션 커밋 여부 (기본값: True)

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

            # Step 3: 통합 정렬
            all_orders = []

            for order in active_orders:
                all_orders.append({
                    'source': 'active',
                    'db_record': order,
                    'priority': OrderType.get_priority(order.order_type),
                    'sort_price': self._get_order_sort_price(order),
                    'created_at': order.created_at,
                    'is_stop': OrderType.requires_stop_price(order.order_type)
                })

            for order in pending_orders:
                all_orders.append({
                    'source': 'pending',
                    'db_record': order,
                    'priority': order.priority,
                    'sort_price': Decimal(str(order.sort_price)) if order.sort_price else None,
                    'created_at': order.created_at,
                    'is_stop': OrderType.requires_stop_price(order.order_type)
                })

            # 정렬 키: (priority ASC, sort_price DESC, created_at ASC)
            all_orders.sort(key=lambda x: (
                x['priority'],
                -(x['sort_price'] if x['sort_price'] else Decimal('-inf')),
                x['created_at']
            ))

            logger.debug(f"📊 정렬 완료 - 총 {len(all_orders)}개 주문")

            # Step 4: 상위 N개 선택 (이중 제한)
            selected_orders = []
            stop_count = 0

            for order in all_orders:
                if len(selected_orders) >= max_orders:
                    break  # 전체 제한 도달

                if order['is_stop']:
                    if stop_count >= max_stop_orders:
                        continue  # STOP 제한 초과 → 건너뛰기
                    stop_count += 1

                selected_orders.append(order)

            logger.info(
                f"✅ 선택 완료 - {len(selected_orders)}개 주문 "
                f"(STOP: {stop_count}개)"
            )

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

            executed_count = 0
            for pending_order in to_execute:
                result = self._execute_pending_order(pending_order)
                if result['success']:
                    executed_count += 1

            logger.info(
                f"✅ 재정렬 완료 - 취소: {cancelled_count}개, "
                f"실행: {executed_count}개"
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

    def _execute_pending_order(self, pending_order: PendingOrder) -> Dict[str, Any]:
        """대기열 주문 → 거래소 실행

        Args:
            pending_order: 실행할 PendingOrder

        Returns:
            dict: {
                'success': bool,
                'order_id': str (성공 시),
                'error': str (실패 시)
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

            # TradingCore의 execute_trade 호출
            result = self.service.execute_trade(
                strategy=strategy,
                symbol=pending_order.symbol,
                side=pending_order.side,
                quantity=Decimal(str(pending_order.quantity)),
                order_type=pending_order.order_type,
                price=Decimal(str(pending_order.price)) if pending_order.price else None,
                stop_price=Decimal(str(pending_order.stop_price)) if pending_order.stop_price else None,
                strategy_account_override=strategy_account,
                schedule_refresh=False  # 재정렬 중에는 잔고 갱신 스킵
            )

            if result.get('success'):
                # 성공 시 대기열에서 제거 (커밋은 상위에서)
                db.session.delete(pending_order)

                logger.info(
                    f"✅ 대기열→거래소 실행 완료 - "
                    f"pending_id: {pending_order.id}, "
                    f"order_id: {result.get('order_id')}"
                )

                return {
                    'success': True,
                    'order_id': result.get('order_id')
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
                    # 최대 재시도 초과 시 대기열에서 제거
                    db.session.delete(pending_order)
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
                    'error': result.get('error')
                }

        except Exception as e:
            logger.error(f"대기열 주문 실행 실패: {e}")
            return {
                'success': False,
                'error': str(e)
            }

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

    def reset_metrics(self):
        """메트릭 초기화"""
        self.metrics = {
            'total_rebalances': 0,
            'total_cancelled': 0,
            'total_executed': 0,
            'total_duration_ms': 0,
            'avg_duration_ms': 0
        }
