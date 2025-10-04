"""
크립토 거래소 메타데이터 관리
"""
from enum import Enum
from typing import Dict, List, Optional


class ExchangeRegion(str, Enum):
    """거래소 지역 분류"""
    DOMESTIC = "domestic"  # 국내 (Upbit, Bithumb, Coinone)
    GLOBAL = "global"      # 해외 (Binance, Bybit, OKX)


class MarketType(str, Enum):
    """크립토 마켓 타입"""
    SPOT = "spot"           # 현물
    FUTURES = "futures"     # 선물 (분기)
    PERPETUAL = "perpetual" # 무기한 선물
    MARGIN = "margin"       # 마진


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

        # === 향후 추가 예정 (주석 템플릿) ===
        # 'bithumb': {
        #     'region': ExchangeRegion.DOMESTIC,
        #     'name': 'Bithumb',
        #     'country': 'South Korea',
        #     'api_version': 'v1',
        #     'supported_markets': [MarketType.SPOT],
        #     'base_currency': ['KRW'],
        #     'auth_type': 'hmac_sha512',
        #     'testnet_available': False,
        # },

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
