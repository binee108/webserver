"""
거래소 API 공통 데이터 모델

@FEAT:framework @FEAT:exchange-integration @COMP:model @TYPE:boilerplate
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Sequence
from decimal import Decimal
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def extract_timestamp_ms(data: Dict[str, Any], keys: Sequence[str],
                         context: str = "") -> Optional[int]:
    """
    여러 후보 키에서 타임스탬프 추출

    Args:
        data: API 응답 데이터
        keys: 우선순위 순으로 정렬된 키 목록
        context: 로깅용 컨텍스트 정보

    Returns:
        밀리초 단위 타임스탬프 또는 None
    """
    for key in keys:
        if key in data and data[key] is not None:
            try:
                return int(data[key])
            except (TypeError, ValueError):
                logger.warning(f"타임스탬프 변환 실패 - {context}: {key}={data[key]}")
                continue

    logger.warning(f"타임스탬프 누락 - {context}: 시도한 키={keys}, 사용 가능한 키={list(data.keys())}")
    return None


@dataclass
class MarketInfo:
    """마켓 정보 모델"""
    symbol: str
    base_asset: str
    quote_asset: str
    status: str
    active: bool

    # Precision 정보
    price_precision: int
    amount_precision: int
    base_precision: int
    quote_precision: int

    # Limits (내부 사용)
    min_qty: Decimal
    max_qty: Decimal
    step_size: Decimal

    min_price: Decimal
    max_price: Decimal
    tick_size: Decimal

    min_notional: Decimal

    # Market type
    market_type: str = "SPOT"  # SPOT, FUTURES

    # CCXT 호환성 속성들
    @property
    def min_quantity(self) -> Decimal:
        """CCXT 호환성: limits.amount.min"""
        return self.min_qty

    @property
    def max_quantity(self) -> Decimal:
        """CCXT 호환성: limits.amount.max"""
        return self.max_qty

    @property
    def limits(self) -> Dict[str, Dict[str, Any]]:
        """CCXT 호환성: limits 구조"""
        return {
            'amount': {
                'min': float(self.min_qty),
                'max': float(self.max_qty) if self.max_qty > 0 else None
            },
            'price': {
                'min': float(self.min_price),
                'max': float(self.max_price) if self.max_price > 0 else None
            },
            'cost': {
                'min': float(self.min_notional),
                'max': None
            }
        }

    @property
    def precision(self) -> Dict[str, int]:
        """CCXT 호환성: precision 구조"""
        return {
            'amount': self.amount_precision,
            'price': self.price_precision,
            'base': self.base_precision,
            'quote': self.quote_precision
        }

    @classmethod
    def from_binance_spot(cls, data: Dict[str, Any]) -> 'MarketInfo':
        """Binance Spot API 데이터에서 생성"""
        filters = {f['filterType']: f for f in data.get('filters', [])}

        lot_size = filters.get('LOT_SIZE', {})
        price_filter = filters.get('PRICE_FILTER', {})
        notional = filters.get('NOTIONAL', {}) or filters.get('MIN_NOTIONAL', {})

        return cls(
            symbol=data['symbol'],
            base_asset=data['baseAsset'],
            quote_asset=data['quoteAsset'],
            status=data['status'],
            active=data['status'] == 'TRADING',

            price_precision=data.get('quotePrecision', 8),
            amount_precision=data.get('baseAssetPrecision', 8),
            base_precision=data.get('baseAssetPrecision', 8),
            quote_precision=data.get('quotePrecision', 8),

            min_qty=Decimal(lot_size.get('minQty', '0')),
            max_qty=Decimal(lot_size.get('maxQty', '0')),
            step_size=Decimal(lot_size.get('stepSize', '0')),

            min_price=Decimal(price_filter.get('minPrice', '0')),
            max_price=Decimal(price_filter.get('maxPrice', '0')),
            tick_size=Decimal(price_filter.get('tickSize', '0')),

            min_notional=Decimal(notional.get('minNotional', '0')),
            market_type="SPOT"
        )

    @classmethod
    def from_binance_futures(cls, data: Dict[str, Any]) -> 'MarketInfo':
        """Binance Futures API 데이터에서 생성"""
        filters = {f['filterType']: f for f in data.get('filters', [])}

        lot_size = filters.get('LOT_SIZE', {})
        price_filter = filters.get('PRICE_FILTER', {})
        notional = filters.get('MIN_NOTIONAL', {})

        return cls(
            symbol=data['symbol'],
            base_asset=data['baseAsset'],
            quote_asset=data['quoteAsset'],
            status=data['status'],
            active=data['status'] == 'TRADING',

            price_precision=data.get('pricePrecision', 8),
            amount_precision=data.get('quantityPrecision', 8),
            base_precision=data.get('baseAssetPrecision', 8),
            quote_precision=data.get('quotePrecision', 8),

            min_qty=Decimal(lot_size.get('minQty', '0')),
            max_qty=Decimal(lot_size.get('maxQty', '0')),
            step_size=Decimal(lot_size.get('stepSize', '0')),

            min_price=Decimal(price_filter.get('minPrice', '0')),
            max_price=Decimal(price_filter.get('maxPrice', '0')),
            tick_size=Decimal(price_filter.get('tickSize', '0')),

            min_notional=Decimal(notional.get('notional', '0')),
            market_type="FUTURES"
        )


@dataclass
class Balance:
    """잔액 정보 모델"""
    asset: str
    free: Decimal
    locked: Decimal
    total: Decimal = None

    def __post_init__(self):
        """total이 없으면 free + locked로 계산"""
        if self.total is None:
            self.total = self.free + self.locked


@dataclass
class Position:
    """포지션 정보 모델 (선물)"""
    symbol: str
    size: Decimal
    side: str  # LONG, SHORT
    unrealized_pnl: Decimal
    entry_price: Decimal
    mark_price: Decimal
    margin: Decimal


@dataclass
class Order:
    """주문 정보 모델"""
    # 필수 필드 (기본값 없음)
    id: str
    symbol: str
    side: str
    type: str
    status: str
    amount: Decimal
    filled: Decimal
    remaining: Decimal
    timestamp: datetime

    # 선택 필드 (기본값 있음)
    price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None  # STOP 주문의 트리거 가격
    market_type: Optional[str] = None
    client_order_id: Optional[str] = None
    average: Optional[Decimal] = None
    cost: Optional[Decimal] = None
    fee: Optional[Decimal] = None
    last_trade_timestamp: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """CCXT 호환 딕셔너리로 변환"""
        return {
            'id': self.id,
            'clientOrderId': self.client_order_id,
            'datetime': self.timestamp.isoformat() if self.timestamp else None,
            'timestamp': int(self.timestamp.timestamp() * 1000) if self.timestamp else None,
            'lastTradeTimestamp': int(self.last_trade_timestamp.timestamp() * 1000) if self.last_trade_timestamp else None,
            'symbol': self.symbol,
            'type': self.type.lower(),
            'timeInForce': None,
            'amount': float(self.amount),
            'price': float(self.price) if self.price else None,
            'stopPrice': float(self.stop_price) if self.stop_price else None,
            'average': float(self.average) if self.average else None,
            'filled': float(self.filled),
            'remaining': float(self.remaining),
            'cost': float(self.cost),
            'trades': None,
            'fee': {
                'currency': None,
                'cost': float(self.fee),
                'rate': None
            },
            'info': {},
            'status': self.status.lower(),
            'side': self.side.lower()
        }

    @classmethod
    def from_binance(cls, data: Dict[str, Any]) -> 'Order':
        """Binance API 데이터에서 생성"""
        # 타임스탬프 안전 추출
        timestamp_ms = extract_timestamp_ms(
            data,
            ['time', 'transactTime', 'updateTime', 'timestamp'],
            f"Order({data.get('orderId', 'unknown')})"
        )

        update_ms = extract_timestamp_ms(
            data,
            ['updateTime', 'time'],
            f"Order({data.get('orderId', 'unknown')}) update"
        )

        return cls(
            id=str(data['orderId']),
            client_order_id=data.get('clientOrderId', ''),
            symbol=data['symbol'],
            side=data['side'],
            type=data['type'],
            status=data['status'],
            amount=Decimal(data['origQty']),
            filled=Decimal(data['executedQty']),
            remaining=Decimal(data['origQty']) - Decimal(data['executedQty']),
            price=Decimal(data['price']) if data.get('price') else None,
            stop_price=Decimal(data['stopPrice']) if data.get('stopPrice') else None,
            average=Decimal(data.get('avgPrice', '0')) if data.get('avgPrice') else None,
            cost=Decimal(data.get('cummulativeQuoteQty', '0')),
            fee=Decimal('0'),  # 별도 조회 필요
            timestamp=datetime.fromtimestamp(timestamp_ms / 1000) if timestamp_ms else None,
            last_trade_timestamp=datetime.fromtimestamp(update_ms / 1000) if update_ms else None
        )


@dataclass
class Ticker:
    """시세 정보 모델"""
    symbol: str
    last: Decimal
    bid: Decimal
    ask: Decimal
    high: Decimal
    low: Decimal
    volume: Decimal
    change: Decimal
    change_percent: Decimal
    timestamp: datetime

    def to_dict(self) -> Dict[str, Any]:
        """CCXT 호환 딕셔너리로 변환"""
        return {
            'symbol': self.symbol,
            'last': float(self.last),
            'bid': float(self.bid),
            'ask': float(self.ask),
            'high': float(self.high),
            'low': float(self.low),
            'volume': float(self.volume),
            'change': float(self.change),
            'percentage': float(self.change_percent),
            'datetime': self.timestamp.isoformat() if self.timestamp else None,
            'timestamp': int(self.timestamp.timestamp() * 1000) if self.timestamp else None,
            'baseVolume': float(self.volume),
            'quoteVolume': None,
            'info': {}
        }

    @classmethod
    def from_binance(cls, data: Dict[str, Any]) -> 'Ticker':
        """Binance API 데이터에서 생성"""
        return cls(
            symbol=data['symbol'],
            last=Decimal(data['lastPrice']),
            bid=Decimal(data.get('bidPrice', data['lastPrice'])),  # Futures에서는 bidPrice가 없을 수 있음
            ask=Decimal(data.get('askPrice', data['lastPrice'])),  # Futures에서는 askPrice가 없을 수 있음
            high=Decimal(data['highPrice']),
            low=Decimal(data['lowPrice']),
            volume=Decimal(data['volume']),
            change=Decimal(data['priceChange']),
            change_percent=Decimal(data['priceChangePercent']),
            timestamp=datetime.now()
        )


@dataclass
class PriceQuote:
    """표준화된 현재가 정보 (거래소 무관 공통 포맷)"""
    symbol: str
    exchange: str
    market_type: str
    last_price: Decimal
    bid_price: Optional[Decimal] = None
    ask_price: Optional[Decimal] = None
    volume: Optional[Decimal] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    raw: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """사전 포맷으로 변환"""
        return {
            'symbol': self.symbol,
            'exchange': self.exchange,
            'market_type': self.market_type,
            'last_price': float(self.last_price),
            'bid_price': float(self.bid_price) if self.bid_price is not None else None,
            'ask_price': float(self.ask_price) if self.ask_price is not None else None,
            'volume': float(self.volume) if self.volume is not None else None,
            'timestamp': self.timestamp.isoformat(),
            'raw': self.raw
        }


# Enhanced Exchange Service에서 사용하는 추가 모델들
@dataclass
class TickerInfo:
    """티커 정보 (Enhanced Exchange용)"""
    symbol: str
    timestamp: datetime
    bid_price: Decimal
    ask_price: Decimal
    last_price: Decimal
    open_price: Decimal
    close_price: Decimal
    high_price: Decimal
    low_price: Decimal
    volume: Decimal
    quote_volume: Decimal
    change_24h: Decimal
    change_percent_24h: Decimal
    raw_data: Dict[str, Any]

@dataclass
class BalanceInfo:
    """잔액 정보 (Enhanced Exchange용)"""
    asset: str
    free: Decimal
    locked: Decimal
    total: Decimal
    raw_data: Optional[Dict[str, Any]] = None

@dataclass
class OrderInfo:
    """주문 정보 (Enhanced Exchange용)"""
    order_id: str
    client_order_id: str
    symbol: str
    side: str
    order_type: str
    quantity: Decimal
    price: Optional[Decimal]
    filled_quantity: Decimal
    remaining_quantity: Decimal
    status: str
    timestamp: datetime
    avg_price: Optional[Decimal] = None
    commission: Optional[Decimal] = None
    raw_data: Optional[Dict[str, Any]] = None

@dataclass
class PositionInfo:
    """포지션 정보 (Enhanced Exchange용)"""
    symbol: str
    side: str  # LONG, SHORT
    size: Decimal
    entry_price: Decimal
    mark_price: Decimal
    pnl: Decimal
    unrealized_pnl: Decimal
    margin: Decimal
    timestamp: datetime
    raw_data: Optional[Dict[str, Any]] = None
