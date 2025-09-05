"""
OpenOrder 레코드 관리 전용 서비스 모듈
OpenOrder의 생성, 업데이트, 삭제를 중앙 집중화하여 일관성 보장
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from decimal import Decimal
from datetime import datetime
from sqlalchemy.orm import Session

from app import db
from app.models import OpenOrder, StrategyAccount, Trade, StrategyPosition
from app.services.utils import to_decimal, decimal_to_float
from app.constants import MarketType, Exchange, OrderType

logger = logging.getLogger(__name__)


class OpenOrderManager:
    """OpenOrder 레코드 관리를 담당하는 클래스"""
    
    def __init__(self, session: Optional[Session] = None):
        # 🔧 기본 세션을 None으로 설정하여 Flask 컨텍스트 의존성 제거
        self.session = session
    
    def create_open_order(self, strategy_account_id: int, exchange_order_id: str,
                         symbol: str, side: str, quantity: Decimal, price: Decimal,
                         market_type: str = None, order_type: str = OrderType.LIMIT, session: Optional[Session] = None) -> OpenOrder:
        """새로운 OpenOrder 레코드 생성"""
        current_session = session or self.session
        
        if current_session is None:
            # 🔧 세션이 전달되지 않은 경우 Flask db.session 사용
            from app import db
            current_session = db.session
        
        try:
            if market_type is None:
                market_type = MarketType.SPOT
            
            open_order = OpenOrder(
                strategy_account_id=strategy_account_id,
                exchange_order_id=exchange_order_id,
                symbol=symbol,
                side=side,  # 이미 BUY/SELL로 표준화되어 전달됨
                quantity=decimal_to_float(quantity),
                price=decimal_to_float(price),
                status='OPEN',
                market_type=market_type
            )
            
            current_session.add(open_order)
            logger.info(f"📋 OpenOrder 레코드 생성 - 주문ID: {exchange_order_id}, "
                       f"심볼: {symbol}, 수량: {quantity}, 가격: {price}")
            
            # ✅ SSE 이벤트는 trading_service에서 중앙화 처리됨
            logger.info(f"📋 {order_type} 주문 생성 완료: {exchange_order_id} (SSE는 중앙 처리)")
            
            return open_order
            
        except Exception as e:
            logger.error(f"OpenOrder 생성 실패 - 주문ID: {exchange_order_id}, 오류: {str(e)}")
            raise
    
    def update_order_status(self, order: OpenOrder, new_status: str, 
                           filled_quantity: Optional[Decimal] = None, 
                           session: Optional[Session] = None) -> bool:
        """OpenOrder 상태 업데이트"""
        current_session = session or self.session
        
        if current_session is None:
            from app import db
            current_session = db.session
        
        try:
            old_status = order.status
            order.status = new_status
            
            if filled_quantity is not None:
                order.filled_quantity = decimal_to_float(filled_quantity)
            
            logger.info(f"주문 상태 변경 - ID: {order.exchange_order_id}, "
                       f"{old_status} → {new_status}")
            
            return True
            
        except Exception as e:
            logger.error(f"주문 상태 업데이트 실패 - ID: {order.exchange_order_id}, 오류: {str(e)}")
            return False
    
    def mark_order_filled(self, order: OpenOrder, filled_quantity: Decimal, 
                         average_price: Decimal, fee_cost: Decimal = Decimal('0'),
                         session: Optional[Session] = None) -> bool:
        """주문을 체결 상태로 마킹하고 관련 레코드 업데이트"""
        current_session = session or self.session
        
        if current_session is None:
            from app import db
            current_session = db.session
        
        try:
            # 1. 상태 업데이트
            self.update_order_status(order, 'FILLED', filled_quantity, current_session)
            
            # 2. Trade 레코드 확인/생성
            self._ensure_trade_record(order, filled_quantity, average_price, fee_cost, current_session)
            
            # 3. 포지션 업데이트
            self._update_position_from_fill(order, filled_quantity, average_price, current_session)
            
            # ✅ SSE 이벤트는 trading_service에서 중앙화 처리됨
            
            logger.info(f"✅ 주문 체결 처리 완료 - ID: {order.exchange_order_id}")
            return True
            
        except Exception as e:
            logger.error(f"주문 체결 처리 실패 - ID: {order.exchange_order_id}, 오류: {str(e)}")
            return False
    
    # ⚠️ SSE 이벤트 발송은 trading_service에서 중앙화됨 - 이 메서드는 더 이상 사용하지 않음
    
    def mark_order_cancelled(self, order: OpenOrder, session: Optional[Session] = None) -> bool:
        """주문을 취소 상태로 마킹"""
        current_session = session or self.session
        
        if current_session is None:
            from app import db
            current_session = db.session
        
        try:
            self.update_order_status(order, 'CANCELLED', session=current_session)
            logger.info(f"✅ 주문 취소 처리 완료 - ID: {order.exchange_order_id}")
            return True
            
        except Exception as e:
            logger.error(f"주문 취소 처리 실패 - ID: {order.exchange_order_id}, 오류: {str(e)}")
            return False
    
    def delete_completed_order(self, order: OpenOrder, reason: str = "completed",
                              session: Optional[Session] = None) -> bool:
        """완료된 주문 레코드 삭제"""
        current_session = session or self.session
        
        if current_session is None:
            from app import db
            current_session = db.session
        
        try:
            if order.status not in ['FILLED', 'CANCELLED']:
                logger.warning(f"완료되지 않은 주문 삭제 시도 - ID: {order.exchange_order_id}, "
                              f"상태: {order.status}")
                return False
            
            order_id = order.exchange_order_id
            current_session.delete(order)
            logger.info(f"🗑️ OpenOrder 레코드 삭제 - ID: {order_id}, 사유: {reason}")
            return True
            
        except Exception as e:
            logger.error(f"주문 레코드 삭제 실패 - ID: {order.exchange_order_id}, 오류: {str(e)}")
            return False
    
    def process_filled_order(self, order: OpenOrder, exchange_order_data: Dict[str, Any],
                            session: Optional[Session] = None) -> bool:
        """체결된 주문 처리 (상태 업데이트 + 레코드 삭제)"""
        current_session = session or self.session
        
        if current_session is None:
            from app import db
            current_session = db.session
        
        try:
            filled_amount = to_decimal(exchange_order_data.get('filled', 0))
            average_price = to_decimal(exchange_order_data.get('average', 0))
            if average_price <= 0:
                average_price = to_decimal(exchange_order_data.get('price', order.price))
            
            fee_info = exchange_order_data.get('fee', {})
            fee_cost = to_decimal(fee_info.get('cost', 0))
            
            # 체결 처리
            if self.mark_order_filled(order, filled_amount, average_price, fee_cost, current_session):
                # 처리 완료 후 레코드 삭제
                return self.delete_completed_order(order, "filled", current_session)
            
            return False
            
        except Exception as e:
            logger.error(f"체결된 주문 처리 실패 - ID: {order.exchange_order_id}, 오류: {str(e)}")
            return False
    
    def process_cancelled_order(self, order: OpenOrder, session: Optional[Session] = None) -> bool:
        """취소된 주문 처리 (상태 업데이트 + 레코드 삭제)"""
        current_session = session or self.session
        
        if current_session is None:
            from app import db
            current_session = db.session
        
        try:
            # 취소 처리
            if self.mark_order_cancelled(order, current_session):
                # 처리 완료 후 레코드 삭제
                return self.delete_completed_order(order, "cancelled", current_session)
            
            return False
            
        except Exception as e:
            logger.error(f"취소된 주문 처리 실패 - ID: {order.exchange_order_id}, 오류: {str(e)}")
            return False
    
    def cleanup_completed_orders(self, session: Optional[Session] = None) -> int:
        """이미 완료된 상태인 주문 레코드들 정리"""
        current_session = session or self.session
        
        if current_session is None:
            from app import db
            current_session = db.session
        
        try:
            completed_orders = current_session.query(OpenOrder).filter(
                OpenOrder.status.in_(['FILLED', 'CANCELLED'])
            ).all()
            
            if not completed_orders:
                logger.debug("정리할 완료된 주문 레코드가 없습니다.")
                return 0
            
            deleted_count = 0
            for order in completed_orders:
                if self.delete_completed_order(order, "cleanup", current_session):
                    deleted_count += 1
            
            logger.info(f"🧹 완료된 주문 레코드 정리 완료 - {deleted_count}개 삭제")
            return deleted_count
            
        except Exception as e:
            logger.error(f"완료된 주문 레코드 정리 실패: {str(e)}")
            return 0
    
    def _ensure_trade_record(self, order: OpenOrder, filled_quantity: Decimal, 
                           average_price: Decimal, fee_cost: Decimal,
                           session: Optional[Session] = None):
        """Trade 레코드 확인/생성"""
        from app.services.utils import calculate_is_entry
        
        current_session = session or self.session
        
        if current_session is None:
            from app import db
            current_session = db.session
        
        # 기존 Trade 레코드 확인
        existing_trade = current_session.query(Trade).filter_by(
            strategy_account_id=order.strategy_account_id,
            exchange_order_id=order.exchange_order_id
        ).first()
        
        if existing_trade and existing_trade.quantity > 0:
            logger.debug(f"Trade 레코드 이미 존재 - 주문ID: {order.exchange_order_id}")
            return
        
        # 포지션 정보 조회 (진입/청산 판단용)
        position = current_session.query(StrategyPosition).filter_by(
            strategy_account_id=order.strategy_account_id,
            symbol=order.symbol
        ).first()
        
        current_position_qty = to_decimal(position.quantity) if position else Decimal('0')
        is_entry = calculate_is_entry(current_position_qty, order.side)
        
        # 실현 손익 계산
        realized_pnl = Decimal('0')
        if position and filled_quantity > 0:
            current_entry_price = to_decimal(position.entry_price)
            
            if order.side == 'SELL' and current_position_qty > 0:
                close_quantity = min(filled_quantity, current_position_qty)
                realized_pnl = close_quantity * (average_price - current_entry_price)
            elif order.side == 'BUY' and current_position_qty < 0:
                close_quantity = min(filled_quantity, abs(current_position_qty))
                realized_pnl = close_quantity * (current_entry_price - average_price)
        
        if existing_trade:
            # 기존 Trade 레코드 업데이트
            existing_trade.quantity = decimal_to_float(filled_quantity)
            existing_trade.order_price = decimal_to_float(to_decimal(order.price))
            existing_trade.price = decimal_to_float(average_price)
            existing_trade.fee = decimal_to_float(fee_cost)
            existing_trade.pnl = decimal_to_float(realized_pnl) if realized_pnl != 0 else None
            existing_trade.is_entry = is_entry
            
            logger.info(f"📝 Trade 레코드 업데이트 - 주문ID: {order.exchange_order_id}")
        else:
            # 새 Trade 레코드 생성
            new_trade = Trade(
                strategy_account_id=order.strategy_account_id,
                exchange_order_id=order.exchange_order_id,
                symbol=order.symbol,
                side=order.side,
                quantity=decimal_to_float(filled_quantity),
                order_price=decimal_to_float(to_decimal(order.price)),
                price=decimal_to_float(average_price),
                order_type=OrderType.LIMIT,  # OpenOrder는 항상 LIMIT 주문
                timestamp=datetime.utcnow(),
                fee=decimal_to_float(fee_cost),
                pnl=decimal_to_float(realized_pnl) if realized_pnl != 0 else None,
                is_entry=is_entry,
                market_type=getattr(order, 'market_type', MarketType.SPOT)
            )
            current_session.add(new_trade)
            logger.info(f"📝 Trade 레코드 생성 - 주문ID: {order.exchange_order_id}")
    
    def _update_position_from_fill(self, order: OpenOrder, filled_quantity: Decimal, 
                                  average_price: Decimal, session: Optional[Session] = None):
        """체결에 따른 포지션 업데이트"""
        from app.services.position_service import position_service
        
        current_session = session or self.session
        
        if current_session is None:
            from app import db
            current_session = db.session
        
        # StrategyAccount 조회
        strategy_account = current_session.query(StrategyAccount).get(order.strategy_account_id)
        if strategy_account:
            position_service.update_position_from_order(
                order, strategy_account, filled_quantity, average_price, current_session
            )


# 전역 인스턴스
open_order_manager = OpenOrderManager() 