# @FEAT:exchange-integration @COMP:exchange @TYPE:config
"""
크립토 거래소 팩토리 (메타데이터 기반)

플러그인 구조로 새 거래소 추가가 용이합니다.
"""

import logging
import inspect
from typing import List, Optional

from .binance import BinanceExchange
from .upbit import UpbitExchange
from .bithumb import BithumbExchange
from app.exchanges.metadata import ExchangeMetadata, ExchangeRegion, MarketType

logger = logging.getLogger(__name__)


class CryptoExchangeFactory:
    """
    크립토 거래소 팩토리 (플러그인 구조)

    특징:
    - 메타데이터 기반 거래소 관리
    - 플러그인 구조 (새 거래소 추가 용이)
    - features 기반 필터링
    """

    # 거래소 클래스 매핑 (확장 시 여기에만 추가)
    _EXCHANGE_CLASSES = {
        'binance': BinanceExchange,
        'upbit': UpbitExchange,
        'bithumb': BithumbExchange,
        # 향후 추가 예시:
        # 'bybit': BybitExchange,
    }

    # 지원하는 거래소 목록
    SUPPORTED_EXCHANGES = list(_EXCHANGE_CLASSES.keys())

    @classmethod
    def create(cls, exchange_name: str, api_key: str, secret: str,
                       testnet: bool = False, **kwargs):
        """
        크립토 거래소 인스턴스 생성

        Args:
            exchange_name: 거래소 이름 (소문자)
            api_key: API 키
            secret: Secret 키
            testnet: 테스트넷 사용 여부

        Returns:
            BaseExchange 인스턴스
        """
        exchange_name = exchange_name.lower()

        # 1. 지원 거래소 검증
        if exchange_name not in cls._EXCHANGE_CLASSES:
            raise ValueError(
                f"지원되지 않는 거래소: {exchange_name}. "
                f"지원 목록: {list(cls._EXCHANGE_CLASSES.keys())}"
            )

        # 2. 메타데이터 검증
        metadata = ExchangeMetadata.get_metadata(exchange_name)
        if not metadata:
            logger.warning(f"메타데이터 없음: {exchange_name}")

        # 3. Testnet 검증 (국내 거래소는 대부분 미지원)
        if testnet and metadata and not metadata.get('testnet_available', False):
            raise ValueError(f"{metadata.get('name')} does not support testnet")

        # 4. 인스턴스 생성
        exchange_class = cls._EXCHANGE_CLASSES[exchange_name]
        logger.info(f"✅ {exchange_name} 거래소 인스턴스 생성 - Testnet: {testnet}")
        return exchange_class(api_key, secret, testnet, **kwargs)

    @classmethod
    def list_exchanges(cls,
                       region: Optional[ExchangeRegion] = None,
                       market_type: Optional[MarketType] = None,
                       feature: Optional[str] = None) -> List[str]:
        """
        지원 거래소 목록 조회 (다중 필터링)

        Examples:
            >>> list_exchanges(region=ExchangeRegion.DOMESTIC)
            []  # 현재 국내 거래소 미지원

            >>> list_exchanges(market_type=MarketType.FUTURES)
            ['binance']

            >>> list_exchanges(feature='leverage')
            ['binance']
        """
        return ExchangeMetadata.list_exchanges(region, market_type, feature)

    @classmethod
    def create_binance(cls, api_key: str, secret: str, testnet: bool = False) -> BinanceExchange:
        """Binance 인스턴스 생성 (편의 메서드)"""
        return cls.create('binance', api_key, secret, testnet)

    @classmethod
    def create_upbit(cls, api_key: str, secret: str) -> UpbitExchange:
        """Upbit 인스턴스 생성 (편의 메서드)"""
        return cls.create('upbit', api_key, secret, testnet=False)

    @classmethod
    def create_bithumb(cls, api_key: str, secret: str) -> 'BithumbExchange':
        """Bithumb 인스턴스 생성 (편의 메서드)"""
        return cls.create('bithumb', api_key, secret, testnet=False)

    @classmethod
    def is_supported(cls, exchange_name: str) -> bool:
        """지원되는 거래소인지 확인"""
        return exchange_name.lower() in cls.SUPPORTED_EXCHANGES

    @classmethod
    def get_supported_exchanges(cls) -> list:
        """지원되는 거래소 목록 반환"""
        return cls.SUPPORTED_EXCHANGES.copy()

    @classmethod
    def create_default_client(cls, exchange_name: str) -> Optional['BaseCryptoExchange']:
        """
        API 키 없이 기본 클라이언트를 생성합니다.

        Args:
            exchange_name: 거래소 이름 (소문자)

        Returns:
            BaseCryptoExchange: 기본 클라이언트 또는 None
        """
        try:
            exchange_name = exchange_name.lower()

            # 지원 거래소 검증
            if exchange_name not in cls._EXCHANGE_CLASSES:
                logger.warning(f"지원되지 않는 거래소: {exchange_name}")
                return None

            exchange_class = cls._EXCHANGE_CLASSES[exchange_name]

            # Constructor 시그니처를 기반으로 안전한 기본 인자 구성
            init_signature = inspect.signature(exchange_class.__init__)
            kwargs = {}

            if 'api_key' in init_signature.parameters:
                kwargs['api_key'] = ""

            # FIXED: Check 'secret' FIRST (base class parameter)
            if 'secret' in init_signature.parameters:
                kwargs['secret'] = ""
            elif 'api_secret' in init_signature.parameters:  # THEN fallback to api_secret
                kwargs['api_secret'] = ""

            # FIXED: Add explicit return for missing parameters
            if not kwargs.get('secret') and not kwargs.get('api_secret'):
                logger.error(f"❌ Both 'secret' and 'api_secret' missing for {exchange_name}")
                return None

            if 'testnet' in init_signature.parameters:
                kwargs['testnet'] = False

            # Log parameter detection for debugging
            logger.debug(f"🔍 {exchange_name} constructor signature: {init_signature}")
            logger.debug(f"🔧 {exchange_name} final kwargs: {list(kwargs.keys())}")

            client = exchange_class(**kwargs)

            logger.info(f"✅ {exchange_name} client created successfully with parameters: {list(kwargs.keys())}")
            return client

        except Exception as e:
            logger.warning(f"❌ {exchange_name} client creation failed: {e}")
            return None


# 전역 팩토리 (클래스 - 모든 메서드가 @classmethod)
crypto_factory = CryptoExchangeFactory


# 편의 함수들
def create_exchange(exchange_name: str = 'binance', api_key: str = '', secret: str = '',
                   testnet: bool = False) -> BinanceExchange:
    """거래소 인스턴스 생성 (편의 함수)"""
    return crypto_factory.create(exchange_name, api_key, secret, testnet)


def create_binance(api_key: str, secret: str, testnet: bool = False) -> BinanceExchange:
    """Binance 인스턴스 생성 (편의 함수)"""
    return crypto_factory.create_binance(api_key, secret, testnet)


def create_upbit(api_key: str, secret: str) -> UpbitExchange:
    """Upbit 인스턴스 생성 (편의 함수)"""
    return crypto_factory.create_upbit(api_key, secret)


def create_bithumb(api_key: str, secret: str) -> 'BithumbExchange':
    """Bithumb 인스턴스 생성 (편의 함수)"""
    return crypto_factory.create_bithumb(api_key, secret)
