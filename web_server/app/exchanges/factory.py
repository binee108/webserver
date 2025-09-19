"""
거래소 팩토리 및 어댑터 레이어

CCXT와 호환되는 인터페이스를 제공하면서 새로운 고성능 구현으로 점진적 전환을 지원합니다.
"""

import os
import asyncio
import logging
from typing import Dict, Any, Optional, Union
from abc import ABC, abstractmethod

from .base import BaseExchange
from .binance.spot import BinanceSpot
from .binance.futures import BinanceFutures

# CCXT는 더 이상 사용하지 않음 - Native 구현만 사용
CCXT_AVAILABLE = False

logger = logging.getLogger(__name__)


class ExchangeFactory:
    """
    거래소 인스턴스 팩토리 (Native 구현만 지원)

    지원되는 거래소들의 Native 구현체를 생성합니다.
    CCXT는 더 이상 사용하지 않으며, 모든 거래소는 Native API로 구현됩니다.
    """
    
    SUPPORTED_EXCHANGES = {
        'binance': {
            'spot_class': BinanceSpot,
            'futures_class': BinanceFutures
        }
    }
    
    @classmethod
    def create_exchange(cls, exchange_name: str, market_type: str, api_key: str, secret: str,
                       testnet: bool = False, **kwargs) -> BaseExchange:
        """
        거래소 Native 인스턴스 생성

        Args:
            exchange_name: 거래소 이름 ('binance')
            market_type: 마켓 타입 ('SPOT', 'FUTURES')
            api_key: API 키
            secret: API 시크릿
            testnet: 테스트넷 사용 여부
            **kwargs: 추가 파라미터

        Returns:
            Native 거래소 인스턴스
        """
        exchange_name = exchange_name.lower()
        market_type = market_type.upper()

        if exchange_name in cls.SUPPORTED_EXCHANGES:
            logger.info(f"🚀 {exchange_name} {market_type} Native API 사용")
            return cls._create_native_exchange(exchange_name, market_type, api_key, secret, testnet, **kwargs)
        else:
            raise ValueError(f"지원되지 않는 거래소: {exchange_name}")
    
    @classmethod
    def _create_native_exchange(cls, exchange_name: str, market_type: str, api_key: str, secret: str,
                               testnet: bool = False, **kwargs) -> BaseExchange:
        """Native 거래소 인스턴스 생성"""
        config = cls.SUPPORTED_EXCHANGES.get(exchange_name)
        if not config:
            raise ValueError(f"지원되지 않는 거래소: {exchange_name}")
        
        if market_type == "FUTURES":
            exchange_class = config['futures_class']
        else:
            exchange_class = config['spot_class']
        
        try:
            instance = exchange_class(api_key, secret, testnet)
            
            # 마켓 정보 백그라운드 로딩
            if hasattr(instance, 'load_markets'):
                asyncio.create_task(instance.load_markets())
            
            logger.info(f"✅ {exchange_class.__name__} 인스턴스 생성 완료")
            return instance
            
        except Exception as e:
            logger.error(f"Native 거래소 인스턴스 생성 실패: {e}")
            raise
    
    
    @classmethod
    def is_supported(cls, exchange_name: str) -> bool:
        """지원되는 거래소인지 확인"""
        return exchange_name.lower() in cls.SUPPORTED_EXCHANGES
    
    @classmethod
    def get_supported_exchanges(cls) -> list:
        """지원되는 거래소 목록 반환"""
        return list(cls.SUPPORTED_EXCHANGES.keys())


# ExchangeAdapter 클래스는 CCXT 호환용이므로 제거됨
# Native 구현만 사용하므로 직접 ExchangeFactory.create_exchange() 사용