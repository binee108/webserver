# @FEAT:exchange-integration @FEAT:precision-system @COMP:exchange @TYPE:core
"""
크립토 거래소 기본 클래스

BaseExchange를 상속하여 크립토 특화 기능을 추가합니다.
"""

from typing import TYPE_CHECKING

from app.exchanges.base import BaseExchange
from app.exchanges.metadata import get_precision_type, PrecisionType
from app.exchanges.precision_providers import (
    PrecisionProvider,
    ApiBasedPrecisionProvider,
    RuleBasedPrecisionProvider
)

if TYPE_CHECKING:
    from app.exchanges.models import MarketInfo


class BaseCryptoExchange(BaseExchange):
    """
    크립토 거래소 공통 기능

    확장 포인트:
    - 레버리지 설정 (Futures)
    - 포지션 모드 설정 (단방향/양방향)
    - 마진 모드 설정 (격리/교차)
    """

    def __init__(self, api_key: str, secret: str, testnet: bool = False):
        super().__init__()
        self.api_key = api_key
        self.api_secret = secret
        self.testnet = testnet

    # @FEAT:precision-system @COMP:exchange @TYPE:core
    def _create_precision_provider(self, market_info: 'MarketInfo') -> 'PrecisionProvider':
        """
        Factory 메서드: 거래소 타입에 따라 적절한 PrecisionProvider 생성

        Args:
            market_info: 시장 정보 (precision_provider 설정 전 객체)

        Returns:
            PrecisionProvider: API_BASED → ApiBasedPrecisionProvider
                              RULE_BASED → RuleBasedPrecisionProvider

        Note:
            - Phase 1: Interface 생성 (ApiBasedPrecisionProvider는 고정 값 반환)
            - Phase 2: Binance 통합 (load_markets에서 호출)
            - Phase 3: RuleBasedPrecisionProvider 실제 규칙 구현
        """
        # 거래소명 추출
        exchange_name = self.__class__.__name__.replace('CryptoExchange', '').replace('Exchange', '').upper()

        precision_type = get_precision_type(exchange_name)

        # ✅ Phase 1: 실제 Provider 생성 (stub 제거)
        if precision_type == PrecisionType.API_BASED:
            return ApiBasedPrecisionProvider(market_info)
        elif precision_type == PrecisionType.RULE_BASED:
            return RuleBasedPrecisionProvider(market_info, exchange_name)
        else:
            # Unknown type: default to API_BASED (safe fallback)
            return ApiBasedPrecisionProvider(market_info)

    def load_markets(self, market_type: str = 'spot', reload: bool = False, force_cache: bool = False):
        """
        마켓 정보 로드 (래퍼)

        Args:
            market_type: 'spot' or 'futures'
            reload: True면 캐시 무시하고 API 재호출
            force_cache: True면 TTL 무시하고 무조건 캐시 반환
        """
        return self.load_markets_impl(market_type, reload, force_cache)
