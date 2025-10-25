# @FEAT:exchange-integration @FEAT:precision-system @COMP:exchange @TYPE:config
"""
크립토 거래소 메타데이터 관리

이 모듈은 거래소별 특성(precision 방식, 지원 기능 등)을 중앙 관리합니다.
"""
from enum import Enum
from typing import Dict, List, Optional
from dataclasses import dataclass


class ExchangeRegion(str, Enum):
    """거래소 지역 분류"""
    DOMESTIC = "domestic"  # 국내 (Upbit, Bithumb, Coinone)
    GLOBAL = "global"      # 해외 (Binance, Bybit, OKX)


class PrecisionType(str, Enum):
    """
    거래소의 precision 방식

    @FEAT:precision-system @COMP:exchange @TYPE:config
    """
    API_BASED = "API_BASED"      # Binance, Bybit: API로 precision 정보 제공
    RULE_BASED = "RULE_BASED"    # Upbit, Bithumb: 고정 가격 단위 규칙


class MarketType(str, Enum):
    """크립토 마켓 타입"""
    SPOT = "spot"           # 현물
    FUTURES = "futures"     # 선물 (분기)
    PERPETUAL = "perpetual" # 무기한 선물
    MARGIN = "margin"       # 마진


@dataclass(frozen=True)
class PrecisionMetadata:
    """
    Precision 방식 메타데이터

    @FEAT:precision-system @COMP:exchange @TYPE:config
    """
    precision_type: PrecisionType
    supports_futures: bool = True
    supports_spot: bool = True


class ExchangeMetadata:
    """크립토 거래소 메타데이터"""

    METADATA: Dict[str, Dict] = {
        # === 해외 거래소 ===
        'binance': {
            'region': ExchangeRegion.GLOBAL,
            'name': 'Binance',
            'country': 'Global',
            'api_version': 'v3',
            'supported_markets': [MarketType.SPOT, MarketType.FUTURES],
            'base_currency': ['USDT', 'BUSD', 'BTC'],
            'auth_type': 'hmac_sha256',
            'testnet_available': True,
            'precision_type': PrecisionType.API_BASED,  # Precision 방식 추가
            'rate_limit': {
                'requests_per_minute': 1200,
                'orders_per_second': 10,
                'weight_limit': 2400
            },
            'features': {
                'leverage': True,
                'position_mode': True,
                'funding_rate': True,
                'websocket': True
            }
        },

        'bybit': {
            'region': ExchangeRegion.GLOBAL,
            'name': 'Bybit',
            'country': 'Global',
            'api_version': 'v5',
            'supported_markets': [MarketType.SPOT, MarketType.PERPETUAL],
            'base_currency': ['USDT', 'USDC'],
            'auth_type': 'hmac_sha256',
            'testnet_available': True,
            'precision_type': PrecisionType.API_BASED,  # Precision 방식 추가
            'rate_limit': {
                'requests_per_minute': 600,
                'orders_per_second': 20,
                'weight_limit': 120
            },
            'features': {
                'leverage': True,
                'position_mode': True,
                'funding_rate': True,
                'websocket': True,
                'unified_account': True  # Bybit Unified Trading
            }
        },

        # === 국내 거래소 ===
        'upbit': {
            'region': ExchangeRegion.DOMESTIC,
            'name': 'Upbit',
            'country': 'South Korea',
            'api_version': 'v1',
            'supported_markets': [MarketType.SPOT],
            'base_currency': ['KRW', 'BTC'],
            'auth_type': 'jwt_sha512',
            'testnet_available': False,
            'precision_type': PrecisionType.RULE_BASED,  # 규칙 기반 precision
            'rate_limit': {
                'requests_per_minute': 600,
                'orders_per_second': 8,
                'weight_limit': None
            },
            'features': {
                'leverage': False,
                'position_mode': False,
                'funding_rate': False,
                'websocket': True
            }
        },

        'bithumb': {
            'region': ExchangeRegion.DOMESTIC,
            'name': 'Bithumb',
            'country': 'South Korea',
            'api_version': 'v1',
            'supported_markets': [MarketType.SPOT],
            'base_currency': ['KRW', 'USDT'],
            'auth_type': 'jwt_hmac_sha256',
            'testnet_available': False,
            'precision_type': PrecisionType.RULE_BASED,  # 규칙 기반 precision
            'rate_limit': {
                'requests_per_minute': 300,
                'orders_per_second': 5,
                'weight_limit': None
            },
            'features': {
                'leverage': False,
                'position_mode': False,
                'funding_rate': False,
                'websocket': True
            }
        },

        # === 향후 추가 예정 (주석 템플릿) ===

        # 'okx': {
        #     'region': ExchangeRegion.GLOBAL,
        #     'name': 'OKX',
        #     'country': 'Global',
        #     'api_version': 'v5',
        #     'supported_markets': [MarketType.SPOT, MarketType.PERPETUAL],
        #     'base_currency': ['USDT', 'USDC'],
        #     'auth_type': 'hmac_sha256',
        #     'testnet_available': True,
        # },
    }

    @classmethod
    def get_metadata(cls, exchange_name: str) -> Dict:
        """거래소 메타데이터 조회"""
        return cls.METADATA.get(exchange_name.lower(), {})

    @classmethod
    def is_domestic(cls, exchange_name: str) -> bool:
        """국내 거래소 여부"""
        meta = cls.get_metadata(exchange_name)
        return meta.get('region') == ExchangeRegion.DOMESTIC

    @classmethod
    def supports_market_type(cls, exchange_name: str, market_type: MarketType) -> bool:
        """특정 마켓 타입 지원 여부"""
        meta = cls.get_metadata(exchange_name)
        supported = meta.get('supported_markets', [])
        return market_type in supported

    @classmethod
    def get_base_currencies(cls, exchange_name: str) -> List[str]:
        """지원 기준 통화 조회"""
        meta = cls.get_metadata(exchange_name)
        return meta.get('base_currency', [])

    @classmethod
    def supports_feature(cls, exchange_name: str, feature: str) -> bool:
        """특정 기능 지원 여부"""
        meta = cls.get_metadata(exchange_name)
        features = meta.get('features', {})
        return features.get(feature, False)

    @classmethod
    def list_exchanges(cls,
                       region: Optional[ExchangeRegion] = None,
                       market_type: Optional[MarketType] = None,
                       feature: Optional[str] = None) -> List[str]:
        """거래소 필터링 조회"""
        exchanges = list(cls.METADATA.keys())

        if region:
            exchanges = [
                ex for ex in exchanges
                if cls.METADATA[ex].get('region') == region
            ]

        if market_type:
            exchanges = [
                ex for ex in exchanges
                if market_type in cls.METADATA[ex].get('supported_markets', [])
            ]

        if feature:
            exchanges = [
                ex for ex in exchanges
                if cls.METADATA[ex].get('features', {}).get(feature, False)
            ]

        return exchanges


# @FEAT:precision-system @COMP:exchange @TYPE:helper
def get_precision_type(exchange_name: str) -> PrecisionType:
    """
    거래소명으로 precision 타입 조회 (Factory 패턴에서 사용)

    Args:
        exchange_name: 거래소 이름 (대문자, 예: BINANCE, UPBIT)

    Returns:
        PrecisionType: API_BASED 또는 RULE_BASED

    Note:
        - 등록되지 않은 거래소는 API_BASED 기본값 반환 (안전한 폴백)
        - 새 거래소 추가 시 ExchangeMetadata.METADATA에 등록하면 자동 동작
    """
    exchange_key = exchange_name.lower()
    metadata = ExchangeMetadata.METADATA.get(exchange_key, {})
    precision_type = metadata.get('precision_type')

    if precision_type is None:
        # 미등록 거래소는 API_BASED 기본값 (대부분 거래소가 API 제공)
        return PrecisionType.API_BASED

    return precision_type


# @FEAT:precision-system @COMP:exchange @TYPE:helper
def requires_market_refresh(exchange_name: str) -> bool:
    """
    거래소의 MarketInfo 갱신 필요 여부

    Args:
        exchange_name: Exchange name (case-insensitive)

    Returns:
        True if exchange requires periodic refresh (API-based)
        False if exchange uses fixed rules (rule-based)

    Note:
        - API-based (Binance, Bybit): filters/precision can change → requires refresh
        - Rule-based (Upbit, Bithumb): fixed price tiers → no refresh needed
    """
    exchange_key = exchange_name.lower()
    metadata = ExchangeMetadata.METADATA.get(exchange_key)

    if metadata is None:
        return True  # Safe default: refresh unknown exchanges

    precision_type = metadata.get('precision_type')
    # API-based exchanges require refresh, rule-based do not
    return precision_type == PrecisionType.API_BASED if precision_type else True


# @FEAT:precision-system @COMP:exchange @TYPE:helper
def get_precision_metadata(exchange_name: str) -> Optional[PrecisionMetadata]:
    """
    거래소의 precision 메타데이터 조회

    Args:
        exchange_name: 거래소 이름 (대문자, 예: BINANCE, UPBIT)

    Returns:
        PrecisionMetadata 또는 None (미등록 거래소)
    """
    exchange_key = exchange_name.lower()
    metadata = ExchangeMetadata.METADATA.get(exchange_key)

    if metadata is None:
        return None

    precision_type = metadata.get('precision_type', PrecisionType.API_BASED)
    supported_markets = metadata.get('supported_markets', [])

    return PrecisionMetadata(
        precision_type=precision_type,
        supports_futures=MarketType.FUTURES in supported_markets or MarketType.PERPETUAL in supported_markets,
        supports_spot=MarketType.SPOT in supported_markets
    )
