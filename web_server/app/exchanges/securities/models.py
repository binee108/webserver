"""
증권 거래소 공통 데이터 모델

모든 증권사에서 공통으로 사용하는 표준 데이터 구조를 정의합니다.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from datetime import datetime
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


@dataclass
class StockOrder:
    """증권 주문 공통 모델 (증권사 무관)"""
    order_id: str
    symbol: str             # 종목코드 (005930, AAPL 등)
    side: str               # BUY, SELL
    order_type: str         # LIMIT, MARKET
    quantity: int           # 주문 수량
    price: Optional[Decimal] = None
    filled_quantity: int = 0
    remaining_quantity: int = 0
    status: str = 'NEW'     # NEW, PARTIALLY_FILLED, FILLED, CANCELLED
    timestamp: Optional[datetime] = None
    raw_data: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            'order_id': self.order_id,
            'symbol': self.symbol,
            'side': self.side,
            'order_type': self.order_type,
            'quantity': self.quantity,
            'price': float(self.price) if self.price else None,
            'filled_quantity': self.filled_quantity,
            'remaining_quantity': self.remaining_quantity,
            'status': self.status,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }

    @classmethod
    def from_kis_response(
        cls,
        data: Dict[str, Any],
        symbol: str = '',
        side: str = '',
        order_type: str = '',
        quantity: int = 0,
        price: Optional[Decimal] = None
    ) -> 'StockOrder':
        """
        한국투자증권 응답 → 공통 모델 변환

        Args:
            data: 한투 API 응답 (output1 또는 주문 조회 응답)
            symbol: 종목코드 (주문 생성 시 요청값)
            side: 매수/매도 (주문 생성 시 요청값)
            order_type: 주문구분 (주문 생성 시 요청값)
            quantity: 주문수량 (주문 생성 시 요청값)
            price: 주문가격 (주문 생성 시 요청값)

        Returns:
            StockOrder: 증권사 독립적인 주문 모델
        """
        output = data.get('output1', {}) if 'output1' in data else data

        # 주문 생성 응답: symbol, side, order_type 등이 응답에 없으므로 파라미터로 받음
        order_id = output.get('ODNO', '')

        # 주문 조회 응답: PDNO, SLL_BUY_DVSN_CD, ORD_DVSN 등이 있음
        response_symbol = output.get('PDNO', '') or output.get('pdno', '')
        response_side = 'BUY' if output.get('SLL_BUY_DVSN_CD') == '02' or output.get('sll_buy_dvsn_cd') == '02' else 'SELL'
        response_order_type = 'LIMIT' if output.get('ORD_DVSN') == '00' or output.get('ord_dvsn_cd') == '00' else 'MARKET'

        # 주문수량 (조회 응답에서는 ORD_QTY 또는 ord_qty)
        response_qty = int(output.get('ORD_QTY', 0) or output.get('ord_qty', 0))

        # 주문가격 (조회 응답에서는 ORD_UNPR 또는 ord_unpr)
        response_price_str = output.get('ORD_UNPR', '0') or output.get('ord_unpr', '0')
        response_price = Decimal(response_price_str) if response_price_str and response_price_str != '0' else None

        # 체결수량
        filled_qty = int(output.get('TOT_CCLD_QTY', 0) or output.get('tot_ccld_qty', 0))

        # 주문시각 (HHmmss → datetime 변환)
        ord_tmd = output.get('ORD_TMD') or output.get('ord_tmd')
        timestamp = None
        if ord_tmd:
            try:
                # 오늘 날짜 + 시각 조합
                from datetime import datetime
                now = datetime.now()
                hour = int(ord_tmd[:2])
                minute = int(ord_tmd[2:4])
                second = int(ord_tmd[4:6])
                timestamp = now.replace(hour=hour, minute=minute, second=second, microsecond=0)
            except (ValueError, IndexError) as e:
                logger.warning(f"주문시각 파싱 실패: {ord_tmd}, 에러: {e}")
                timestamp = datetime.now()
        else:
            timestamp = datetime.now()

        # 주문상태 (조회 응답에서는 다양한 상태 코드가 있음)
        # Phase 3.4에서 상세 매핑 예정, 현재는 간단히 처리
        status = 'NEW'  # 기본값
        if filled_qty > 0:
            if filled_qty >= response_qty:
                status = 'FILLED'
            else:
                status = 'PARTIALLY_FILLED'
        elif output.get('cncl_yn') == 'Y' or output.get('CNCL_YN') == 'Y':
            status = 'CANCELLED'

        # 응답에 값이 있으면 우선, 없으면 파라미터 사용
        final_symbol = response_symbol or symbol
        final_side = response_side if response_symbol else side  # 조회 응답이면 side 사용
        final_order_type = response_order_type if response_symbol else order_type
        final_quantity = response_qty if response_qty > 0 else quantity
        final_price = response_price if response_price else price

        return cls(
            order_id=order_id,
            symbol=final_symbol,
            side=final_side,
            order_type=final_order_type,
            quantity=final_quantity,
            price=final_price,
            filled_quantity=filled_qty,
            remaining_quantity=final_quantity - filled_qty,
            status=status,
            timestamp=timestamp,
            raw_data=data
        )

    @classmethod
    def from_kiwoom_response(cls, data: Dict[str, Any]) -> 'StockOrder':
        """키움증권 응답 → 공통 모델 변환 (향후 구현)"""
        # TODO: 키움증권 API 응답 구조에 맞게 구현
        raise NotImplementedError("Kiwoom adapter not implemented yet")


@dataclass
class StockBalance:
    """증권 잔고 공통 모델"""
    total_balance: Decimal        # 총 평가금액
    available_balance: Decimal    # 주문가능금액
    total_purchase_amount: Decimal = Decimal('0')  # 총 매입금액
    total_evaluation_amount: Decimal = Decimal('0')  # 총 평가금액
    total_profit_loss: Decimal = Decimal('0')  # 총 손익
    positions: list = field(default_factory=list)  # 보유 종목 리스트

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_balance': float(self.total_balance),
            'available_balance': float(self.available_balance),
            'total_purchase_amount': float(self.total_purchase_amount),
            'total_evaluation_amount': float(self.total_evaluation_amount),
            'total_profit_loss': float(self.total_profit_loss),
            'positions': [p.to_dict() for p in self.positions] if self.positions else []
        }


@dataclass
class StockPosition:
    """주식 포지션 공통 모델"""
    symbol: str
    symbol_name: str
    quantity: int
    avg_price: Decimal
    current_price: Decimal
    purchase_amount: Decimal
    evaluation_amount: Decimal
    unrealized_pnl: Decimal
    profit_loss_rate: Decimal

    def to_dict(self) -> Dict[str, Any]:
        return {
            'symbol': self.symbol,
            'symbol_name': self.symbol_name,
            'quantity': self.quantity,
            'avg_price': float(self.avg_price),
            'current_price': float(self.current_price),
            'purchase_amount': float(self.purchase_amount),
            'evaluation_amount': float(self.evaluation_amount),
            'unrealized_pnl': float(self.unrealized_pnl),
            'profit_loss_rate': float(self.profit_loss_rate)
        }


@dataclass
class StockQuote:
    """주식 시세 공통 모델"""
    symbol: str
    current_price: Decimal
    change_amount: Decimal
    change_rate: Decimal
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    volume: int
    timestamp: datetime
