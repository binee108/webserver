"""
크립토 거래소 어댑터 모듈

지원 거래소:
- Binance (Spot, Futures, Testnet)
- Upbit (Spot)

사용 예시:
    from app.exchanges.crypto import BinanceExchange, CryptoExchangeFactory

    # Factory 사용 (권장)
    exchange = CryptoExchangeFactory.create('binance', api_key, secret, testnet=True)

    # 직접 생성
    binance = BinanceExchange(api_key, secret, testnet=True)
"""

from .base import BaseCryptoExchange
from .factory import CryptoExchangeFactory
from .binance import BinanceExchange
from .upbit import UpbitExchange

__all__ = [
    'BaseCryptoExchange',
    'CryptoExchangeFactory',
    'BinanceExchange',
    'UpbitExchange',
]
