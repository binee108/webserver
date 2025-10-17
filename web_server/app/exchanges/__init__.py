"""
통합 거래소 모듈

# @FEAT:exchange-integration @COMP:exchange @TYPE:core

사용법:
    # 권장 방식 (신규 코드)
    from app.exchanges.crypto import BinanceExchange, CryptoExchangeFactory
    from app.exchanges.securities import KoreaInvestmentExchange, SecuritiesExchangeFactory
    from app.exchanges import UnifiedExchangeFactory

    # 하위 호환 (기존 코드, Deprecated)
    from app.exchanges import BinanceExchange  # ⚠️ Deprecated
"""

# === 공통 클래스 ===
from .base import BaseExchange
from .models import MarketInfo, Balance, Order, Ticker, Position
from .unified_factory import UnifiedExchangeFactory

# 예외 클래스 (base.py에 있으면 그대로 사용, 없으면 exceptions.py에서 import)
try:
    from .base import (
        ExchangeError,
        NetworkError,
        AuthenticationError,
        InsufficientFunds,
        InvalidOrder,
    )
except ImportError:
    from .exceptions import (
        ExchangeError,
        NetworkError,
        AuthenticationError,
        InsufficientFunds,
        InvalidOrder,
        OrderNotFound,
    )

# === 하위 호환성 유지 (Deprecated) ===
# 기존 코드 호환을 위해 재export
from .crypto import (
    BinanceExchange,
    UpbitExchange,
    CryptoExchangeFactory,
)
from .securities import (
    KoreaInvestmentExchange,
    SecuritiesExchangeFactory,
    StockOrder,
    StockBalance,
)

__all__ = [
    # 공통
    'BaseExchange',
    'UnifiedExchangeFactory',
    'MarketInfo',
    'Balance',
    'Order',
    'Ticker',
    'Position',
    'ExchangeError',
    'NetworkError',
    'AuthenticationError',
    'InsufficientFunds',
    'InvalidOrder',

    # Crypto (Deprecated - 하위 호환용)
    'BinanceExchange',
    'UpbitExchange',
    'CryptoExchangeFactory',

    # Securities (Deprecated - 하위 호환용)
    'KoreaInvestmentExchange',
    'SecuritiesExchangeFactory',
    'StockOrder',
    'StockBalance',
]
