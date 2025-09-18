"""
통합 주문 서비스
기존 4개 주문 서비스를 하나로 통합
"""

import logging
from typing import Dict, Any, List, Optional
from decimal import Decimal
from datetime import datetime
from sqlalchemy.orm import Session, joinedload
from collections import defaultdict

from app import db
from app.models import OpenOrder, StrategyAccount, Account, Strategy, Trade, StrategyPosition
from app.services.utils import to_decimal, decimal_to_float
from app.constants import MarketType, Exchange, OrderType

logger = logging.getLogger(__name__)


class UnifiedOrderService:
    """통합 주문 서비스 - 모든 주문 관련 기능을 한 곳에서 관리"""

    def __init__(self):
        self.session = db.session
        # 나중에 의존성 주입으로 설정될 서비스들
        self._exchange_service = None

    def set_exchange_service(self, exchange_service):
        """거래소 서비스 설정 (의존성 주입)"""
        self._exchange_service = exchange_service

    # === 주문 생성 관련 ===

    def create_open_order(self,
                         strategy_account_id: int,
                         exchange_order_id: str,
                         symbol: str,
                         side: str,
                         quantity: Decimal,
                         price: Optional[Decimal] = None,
                         market_type: str = None,
                         order_type: str = OrderType.LIMIT,
                         stop_price: Optional[Decimal] = None,
                         session: Optional[Session] = None) -> OpenOrder:
        """새로운 OpenOrder 레코드 생성"""
        current_session = session or self.session

        try:
            if market_type is None:
                market_type = MarketType.SPOT

            open_order = OpenOrder(
                strategy_account_id=strategy_account_id,
                exchange_order_id=exchange_order_id,
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=decimal_to_float(quantity),
                price=decimal_to_float(price) if price is not None else None,
                stop_price=decimal_to_float(stop_price) if stop_price is not None else None,
                market_type=market_type,
                status='OPEN',
                created_at=datetime.utcnow(),
                last_checked=datetime.utcnow()
            )

            current_session.add(open_order)
            current_session.flush()  # ID 생성을 위해 flush

            logger.info(f"✅ OpenOrder 생성: ID={open_order.id}, 거래소주문ID={exchange_order_id}, "
                       f"심볼={symbol}, 사이드={side}, 수량={quantity}, 타입={order_type}")

            return open_order

        except Exception as e:
            logger.error(f"❌ OpenOrder 생성 실패: {e}")
            current_session.rollback()
            raise

    def update_open_order(self,
                         open_order: OpenOrder,
                         update_data: Dict[str, Any],
                         session: Optional[Session] = None) -> bool:
        """OpenOrder 업데이트"""
        current_session = session or self.session

        try:
            # 업데이트 가능한 필드들
            allowed_fields = [
                'status', 'filled_quantity', 'remaining_quantity',
                'average_price', 'fee_amount', 'fee_currency',
                'last_checked', 'filled_at'
            ]

            updated = False
            for field, value in update_data.items():
                if field in allowed_fields and hasattr(open_order, field):
                    if field in ['filled_quantity', 'remaining_quantity', 'average_price', 'fee_amount']:
                        # Decimal 필드는 float로 변환
                        value = decimal_to_float(value) if value is not None else None

                    old_value = getattr(open_order, field)
                    if old_value != value:
                        setattr(open_order, field, value)
                        updated = True
                        logger.debug(f"📝 OpenOrder 업데이트: {field} {old_value} → {value}")

            if updated:
                open_order.last_checked = datetime.utcnow()
                current_session.flush()

            return updated

        except Exception as e:
            logger.error(f"❌ OpenOrder 업데이트 실패: {e}")
            current_session.rollback()
            raise

    def delete_open_order(self, open_order: OpenOrder, session: Optional[Session] = None) -> bool:
        """OpenOrder 삭제"""
        current_session = session or self.session

        try:
            current_session.delete(open_order)
            current_session.flush()

            logger.info(f"🗑️ OpenOrder 삭제: ID={open_order.id}, 거래소주문ID={open_order.exchange_order_id}")
            return True

        except Exception as e:
            logger.error(f"❌ OpenOrder 삭제 실패: {e}")
            current_session.rollback()
            return False

    # === 주문 조회 관련 ===

    def get_open_orders_by_user(self, user_id: int) -> List[OpenOrder]:
        """사용자별 미체결 주문 조회"""
        try:
            return self.session.query(OpenOrder).join(
                StrategyAccount, OpenOrder.strategy_account_id == StrategyAccount.id
            ).join(
                Account, StrategyAccount.account_id == Account.id
            ).filter(
                Account.user_id == user_id,
                OpenOrder.status == 'OPEN'
            ).order_by(OpenOrder.created_at.desc()).all()

        except Exception as e:
            logger.error(f"사용자별 미체결 주문 조회 실패: {e}")
            return []

    def get_open_orders_by_strategy(self, strategy_id: int) -> List[OpenOrder]:
        """전략별 미체결 주문 조회"""
        try:
            return self.session.query(OpenOrder).join(
                StrategyAccount, OpenOrder.strategy_account_id == StrategyAccount.id
            ).filter(
                StrategyAccount.strategy_id == strategy_id,
                OpenOrder.status == 'OPEN'
            ).order_by(OpenOrder.created_at.desc()).all()

        except Exception as e:
            logger.error(f"전략별 미체결 주문 조회 실패: {e}")
            return []

    def get_active_open_orders(self) -> List[OpenOrder]:
        """모든 활성 미체결 주문 조회"""
        try:
            return self.session.query(OpenOrder).options(
                joinedload(OpenOrder.strategy_account).joinedload(StrategyAccount.account),
                joinedload(OpenOrder.strategy_account).joinedload(StrategyAccount.strategy)
            ).filter(
                OpenOrder.status == 'OPEN'
            ).order_by(OpenOrder.created_at.desc()).all()

        except Exception as e:
            logger.error(f"활성 미체결 주문 조회 실패: {e}")
            return []

    # === 주문 취소 관련 ===

    def cancel_order(self, open_order: OpenOrder) -> Dict[str, Any]:
        """주문 취소"""
        try:
            if not self._exchange_service:
                return {
                    'success': False,
                    'error': 'Exchange service not available',
                    'error_type': 'service_error'
                }

            # 계정 정보 가져오기
            strategy_account = open_order.strategy_account
            account = strategy_account.account

            # 거래소에서 주문 취소
            cancel_result = self._exchange_service.cancel_order(
                account=account,
                order_id=open_order.exchange_order_id,
                symbol=open_order.symbol
            )

            if cancel_result.get('success', False):
                # 로컬 레코드 업데이트
                self.update_open_order(open_order, {
                    'status': 'CANCELED',
                    'last_checked': datetime.utcnow()
                })

                # 이벤트 발송
                self._emit_order_cancelled_event(open_order, account, strategy_account.strategy)

                logger.info(f"✅ 주문 취소 완료: {open_order.exchange_order_id}")
                return {
                    'success': True,
                    'message': '주문이 성공적으로 취소되었습니다.'
                }
            else:
                logger.error(f"❌ 거래소 주문 취소 실패: {cancel_result.get('error', 'Unknown error')}")
                return cancel_result

        except Exception as e:
            logger.error(f"주문 취소 중 오류: {e}")
            return {
                'success': False,
                'error': str(e),
                'error_type': 'cancel_error'
            }

    def cancel_orders_bulk(self, order_ids: List[int]) -> Dict[str, Any]:
        """여러 주문 일괄 취소"""
        try:
            results = {
                'success_count': 0,
                'failed_count': 0,
                'errors': []
            }

            for order_id in order_ids:
                open_order = self.session.query(OpenOrder).get(order_id)
                if not open_order:
                    results['failed_count'] += 1
                    results['errors'].append(f"주문 ID {order_id}를 찾을 수 없습니다.")
                    continue

                cancel_result = self.cancel_order(open_order)
                if cancel_result.get('success', False):
                    results['success_count'] += 1
                else:
                    results['failed_count'] += 1
                    results['errors'].append(f"주문 ID {order_id} 취소 실패: {cancel_result.get('error', 'Unknown')}")

            return {
                'success': True,
                'results': results
            }

        except Exception as e:
            logger.error(f"일괄 주문 취소 실패: {e}")
            return {
                'success': False,
                'error': str(e),
                'error_type': 'bulk_cancel_error'
            }

    # === 주문 상태 업데이트 관련 ===

    def update_open_orders_status(self) -> Dict[str, Any]:
        """모든 미체결 주문 상태 업데이트 (백그라운드 작업용)"""
        try:
            # 완료된 주문 정리
            cleanup_count = self.cleanup_completed_orders()

            # 활성 미체결 주문 조회
            open_orders = self.get_active_open_orders()
            if not open_orders:
                return self._create_summary_result(cleanup_count, 0, 0, 0, 0)

            # 계좌별 그룹화
            orders_by_account = self._group_orders_by_account(open_orders)
            if not orders_by_account:
                return self._create_summary_result(cleanup_count, len(open_orders), 0, 0, 0)

            # 계좌별 주문 처리
            processing_stats = self._process_orders_by_account(orders_by_account)

            # 결과 반환
            self.session.commit()
            return self._create_summary_result(
                cleanup_count,
                len(open_orders),
                processing_stats['updated_count'],
                processing_stats['filled_count'],
                processing_stats['error_count']
            )

        except Exception as e:
            logger.error(f"주문 상태 업데이트 실패: {e}")
            self.session.rollback()
            return {
                'success': False,
                'error': str(e),
                'error_type': 'status_update_error'
            }

    def cleanup_completed_orders(self, session: Optional[Session] = None) -> int:
        """완료된 주문 정리"""
        current_session = session or self.session

        try:
            # FILLED 또는 CANCELED 상태의 오래된 주문들 삭제 (7일 이상)
            from datetime import timedelta
            cutoff_date = datetime.utcnow() - timedelta(days=7)

            deleted_count = current_session.query(OpenOrder).filter(
                OpenOrder.status.in_(['FILLED', 'CANCELED']),
                OpenOrder.last_checked < cutoff_date
            ).delete()

            if deleted_count > 0:
                logger.info(f"🗑️ 완료된 주문 {deleted_count}개 정리 완료")

            return deleted_count

        except Exception as e:
            logger.error(f"완료된 주문 정리 실패: {e}")
            return 0

    # === Private 메서드들 ===

    def _group_orders_by_account(self, open_orders: List[OpenOrder]) -> Dict[Account, List[OpenOrder]]:
        """주문을 계좌별로 그룹화"""
        orders_by_account = defaultdict(list)

        for order in open_orders:
            try:
                account = order.strategy_account.account
                if account and account.is_active:
                    orders_by_account[account].append(order)
            except Exception as e:
                logger.warning(f"주문 그룹화 중 오류 (주문 ID: {order.id}): {e}")

        return dict(orders_by_account)

    def _process_orders_by_account(self, orders_by_account: Dict[Account, List[OpenOrder]]) -> Dict[str, int]:
        """계좌별 주문 처리"""
        stats = {
            'updated_count': 0,
            'filled_count': 0,
            'error_count': 0
        }

        for account, orders in orders_by_account.items():
            try:
                account_stats = self._process_account_orders(account, orders)
                stats['updated_count'] += account_stats['updated_count']
                stats['filled_count'] += account_stats['filled_count']
                stats['error_count'] += account_stats['error_count']

            except Exception as e:
                logger.error(f"계좌 {account.id} 주문 처리 실패: {e}")
                stats['error_count'] += len(orders)

        return stats

    def _process_account_orders(self, account: Account, orders: List[OpenOrder]) -> Dict[str, int]:
        """특정 계좌의 주문들 처리"""
        stats = {
            'updated_count': 0,
            'filled_count': 0,
            'error_count': 0
        }

        if not self._exchange_service:
            logger.warning("Exchange service not available for order processing")
            stats['error_count'] = len(orders)
            return stats

        for order in orders:
            try:
                # 거래소에서 주문 상태 조회
                order_result = self._exchange_service.fetch_order(
                    account=account,
                    order_id=order.exchange_order_id,
                    symbol=order.symbol
                )

                if order_result.get('success', False):
                    order_data = order_result['order']

                    # 주문 상태 업데이트
                    if self._update_order_from_exchange_data(order, order_data):
                        stats['updated_count'] += 1

                        # 체결 완료 확인
                        if order.status == 'FILLED':
                            stats['filled_count'] += 1

                else:
                    logger.warning(f"주문 조회 실패: {order.exchange_order_id} - {order_result.get('error', 'Unknown')}")
                    stats['error_count'] += 1

            except Exception as e:
                logger.error(f"주문 {order.exchange_order_id} 처리 실패: {e}")
                stats['error_count'] += 1

        return stats

    def _update_order_from_exchange_data(self, order: OpenOrder, exchange_data: Dict[str, Any]) -> bool:
        """거래소 데이터로 주문 업데이트"""
        try:
            update_data = {}

            # 상태 업데이트
            exchange_status = exchange_data.get('status', '').upper()
            if exchange_status in ['CLOSED', 'FILLED']:
                update_data['status'] = 'FILLED'
                update_data['filled_at'] = datetime.utcnow()
            elif exchange_status in ['CANCELED', 'CANCELLED']:
                update_data['status'] = 'CANCELED'

            # 체결 수량 및 평균 가격
            filled_amount = exchange_data.get('filled', 0)
            if filled_amount:
                update_data['filled_quantity'] = Decimal(str(filled_amount))

            average_price = exchange_data.get('average')
            if average_price:
                update_data['average_price'] = Decimal(str(average_price))

            # 수수료 정보
            fee_info = exchange_data.get('fee', {})
            if fee_info:
                fee_cost = fee_info.get('cost')
                if fee_cost:
                    update_data['fee_amount'] = Decimal(str(fee_cost))
                    update_data['fee_currency'] = fee_info.get('currency', '')

            update_data['last_checked'] = datetime.utcnow()

            return self.update_open_order(order, update_data)

        except Exception as e:
            logger.error(f"거래소 데이터로 주문 업데이트 실패: {e}")
            return False

    def _emit_order_cancelled_event(self, open_order: OpenOrder, account: Account, strategy: Strategy):
        """주문 취소 이벤트 발송"""
        try:
            from app.services.event_service import event_service, OrderEvent

            account_info = {
                'id': account.id,
                'name': account.name,
                'exchange': account.exchange
            }

            order_event = OrderEvent(
                event_type='order_cancelled',
                order_id=open_order.exchange_order_id,
                symbol=open_order.symbol,
                strategy_id=strategy.id,
                user_id=account.user_id,
                timestamp=datetime.utcnow(),
                data={
                    'side': open_order.side,
                    'quantity': open_order.quantity,
                    'price': open_order.price,
                    'order_type': open_order.order_type,
                    'account': account_info
                }
            )

            event_service.publish(order_event)

        except Exception as e:
            logger.error(f"주문 취소 이벤트 발송 실패: {e}")

    def _create_summary_result(self, cleanup_count: int, total_orders: int,
                              updated_count: int, filled_count: int, error_count: int) -> Dict[str, Any]:
        """결과 요약 생성"""
        return {
            'success': True,
            'cleanup_count': cleanup_count,
            'total_orders': total_orders,
            'updated_count': updated_count,
            'filled_count': filled_count,
            'error_count': error_count,
            'processed_at': datetime.utcnow().isoformat()
        }


# 싱글톤 인스턴스
unified_order_service = UnifiedOrderService()