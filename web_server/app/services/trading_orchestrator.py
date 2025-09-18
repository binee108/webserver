"""
트레이딩 오케스트레이터 서비스
순환 의존성 해결을 위한 중간 레이어
"""

import logging
from typing import Dict, Any, List, Optional
from decimal import Decimal

from app import db
from app.models import Strategy, Account, StrategyAccount, StrategyPosition, Trade

logger = logging.getLogger(__name__)


class TradingOrchestrator:
    """
    트레이딩과 포지션 서비스 간 순환 의존성을 해결하기 위한 오케스트레이터
    두 서비스의 상호작용을 조율하는 역할
    """

    def __init__(self):
        self._trading_service = None
        self._position_service = None

    def set_services(self, trading_service, position_service):
        """서비스 인스턴스 설정 (의존성 주입)"""
        self._trading_service = trading_service
        self._position_service = position_service

    def execute_trade_with_position_update(self,
                                         strategy: Strategy,
                                         symbol: str,
                                         side: str,
                                         quantity: Decimal,
                                         order_type: str,
                                         price: Optional[Decimal] = None,
                                         stop_price: Optional[Decimal] = None) -> Dict[str, Any]:
        """
        거래 실행과 포지션 업데이트를 조율

        Args:
            strategy: 전략 객체
            symbol: 심볼
            side: 매수/매도 방향
            quantity: 수량
            order_type: 주문 유형
            price: 가격 (지정가 주문시)
            stop_price: 스탑 가격 (스탑 주문시)

        Returns:
            거래 실행 결과
        """
        try:
            # 1. 거래 실행
            if not self._trading_service:
                raise RuntimeError("TradingService not set")

            trade_result = self._trading_service._execute_single_trade(
                strategy=strategy,
                symbol=symbol,
                side=side,
                quantity=quantity,
                order_type=order_type,
                price=price,
                stop_price=stop_price
            )

            # 2. 거래 성공시 포지션 업데이트
            if trade_result.get('success', False) and self._position_service:
                try:
                    # 포지션 업데이트를 비동기적으로 처리
                    self._position_service.update_position_after_trade(
                        strategy=strategy,
                        symbol=symbol,
                        side=side,
                        quantity=quantity,
                        price=trade_result.get('average_price', price or Decimal('0')),
                        trade_result=trade_result
                    )
                except Exception as pos_error:
                    logger.error(f"포지션 업데이트 실패: {pos_error}")
                    # 포지션 업데이트 실패가 거래 실행 결과에 영향을 주지 않도록 함

            return trade_result

        except Exception as e:
            logger.error(f"거래 오케스트레이션 실패: {e}")
            return {
                'success': False,
                'error': str(e),
                'error_type': 'orchestration_error'
            }

    def calculate_position_after_trade(self,
                                     position: StrategyPosition,
                                     trade_side: str,
                                     trade_quantity: Decimal,
                                     trade_price: Decimal) -> Dict[str, Decimal]:
        """
        거래 후 포지션 계산 (순수 계산 로직, 의존성 없음)

        Args:
            position: 현재 포지션
            trade_side: 거래 방향
            trade_quantity: 거래 수량
            trade_price: 거래 가격

        Returns:
            새로운 포지션 정보
        """
        current_qty = position.quantity or Decimal('0')
        current_entry = position.entry_price or Decimal('0')

        if trade_side.upper() == 'BUY':
            new_qty = current_qty + trade_quantity
        else:  # SELL
            new_qty = current_qty - trade_quantity

        # 새로운 평균 단가 계산
        if new_qty == 0:
            new_entry_price = Decimal('0')
        elif (current_qty >= 0 and trade_side.upper() == 'BUY') or \
             (current_qty <= 0 and trade_side.upper() == 'SELL'):
            # 같은 방향 진입 (평균 단가 계산)
            if current_qty == 0:
                new_entry_price = trade_price
            else:
                total_cost = (current_qty * current_entry) + (trade_quantity * trade_price)
                new_entry_price = total_cost / new_qty if new_qty != 0 else Decimal('0')
        else:
            # 반대 방향 (기존 진입가 유지 또는 신규 진입가)
            if abs(new_qty) > abs(current_qty):
                # 포지션 방향이 바뀜
                new_entry_price = trade_price
            else:
                # 부분 청산
                new_entry_price = current_entry

        return {
            'quantity': new_qty,
            'entry_price': new_entry_price
        }


# 싱글톤 인스턴스
trading_orchestrator = TradingOrchestrator()