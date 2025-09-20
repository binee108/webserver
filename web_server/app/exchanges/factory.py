"""
단순화된 거래소 팩토리

1인 사용자를 위한 최소한의 거래소 팩토리입니다.
복잡한 추상화 없이 직접적이고 간단한 구조로 구성되었습니다.
"""

import logging
from typing import Dict, Any, Optional, Union

from .binance import BinanceExchange

logger = logging.getLogger(__name__)


class ExchangeFactory:
    """
    단순화된 거래소 팩토리

    특징:
    - 1인 사용자 최적화
    - 복잡한 추상화 제거
    - Binance 중심 (Native 구현만)
    - 직관적이고 간단한 API
    """

    # 지원하는 거래소 (현재 Binance만)
    SUPPORTED_EXCHANGES = ['binance']

    @classmethod
    def create_exchange(cls, exchange_name: str, api_key: str, secret: str,
                       testnet: bool = False, **kwargs) -> BinanceExchange:
        """
        거래소 인스턴스 생성

        Args:
            exchange_name: 거래소 이름 ('binance')
            api_key: API 키
            secret: API 시크릿
            testnet: 테스트넷 사용 여부

        Returns:
            거래소 인스턴스 (Binance 통합)
        """
        exchange_name = exchange_name.lower()

        if exchange_name not in cls.SUPPORTED_EXCHANGES:
            raise ValueError(f"지원되지 않는 거래소: {exchange_name}")

        if exchange_name == 'binance':
            logger.info(f"✅ Binance 거래소 인스턴스 생성 - Testnet: {testnet}")
            return BinanceExchange(api_key, secret, testnet)
        else:
            raise ValueError(f"지원되지 않는 거래소: {exchange_name}")

    @classmethod
    def create_binance(cls, api_key: str, secret: str, testnet: bool = False) -> BinanceExchange:
        """Binance 인스턴스 생성 (편의 메서드)"""
        return cls.create_exchange('binance', api_key, secret, testnet)

    @classmethod
    def is_supported(cls, exchange_name: str) -> bool:
        """지원되는 거래소인지 확인"""
        return exchange_name.lower() in cls.SUPPORTED_EXCHANGES

    @classmethod
    def get_supported_exchanges(cls) -> list:
        """지원되는 거래소 목록 반환"""
        return cls.SUPPORTED_EXCHANGES.copy()


# 전역 팩토리 인스턴스
exchange_factory = ExchangeFactory()


# 편의 함수들
def create_exchange(exchange_name: str = 'binance', api_key: str = '', secret: str = '',
                   testnet: bool = False) -> BinanceExchange:
    """거래소 인스턴스 생성 (편의 함수)"""
    return exchange_factory.create_exchange(exchange_name, api_key, secret, testnet)


def create_binance(api_key: str, secret: str, testnet: bool = False) -> BinanceExchange:
    """Binance 인스턴스 생성 (편의 함수)"""
    return exchange_factory.create_binance(api_key, secret, testnet)