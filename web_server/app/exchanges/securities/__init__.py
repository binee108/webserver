"""
증권 거래소 어댑터 모듈

지원 증권사:
- 한국투자증권 (KIS) - 국내주식, 해외주식

사용 예시:
    from app.exchanges.securities import SecuritiesExchangeFactory

    # Factory 사용 (권장)
    account = Account.query.get(1)  # 한투 계좌
    exchange = SecuritiesExchangeFactory.create(account)

    # 주문 생성
    order = await exchange.create_stock_order(
        symbol='005930',
        side='buy',
        order_type='LIMIT',
        quantity=10,
        price=Decimal('70000')
    )
"""

from .base import BaseSecuritiesExchange
from .factory import SecuritiesExchangeFactory
from .korea_investment import KoreaInvestmentExchange
from .models import StockOrder, StockBalance, StockPosition, StockQuote
from .exceptions import (
    SecuritiesError,
    TokenExpiredError,
    MarketClosed,
    InsufficientBalance,
)

__all__ = [
    'BaseSecuritiesExchange',
    'SecuritiesExchangeFactory',
    'KoreaInvestmentExchange',
    'StockOrder',
    'StockBalance',
    'StockPosition',
    'StockQuote',
    'SecuritiesError',
    'TokenExpiredError',
    'MarketClosed',
    'InsufficientBalance',
]
