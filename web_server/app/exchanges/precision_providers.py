# @FEAT:precision-system @COMP:exchange @TYPE:core
"""
PrecisionProvider interface and implementations.

이 모듈은 거래소별 가격/수량 정밀도 계산을 담당합니다.
- ApiBasedPrecisionProvider: Binance, Bybit 등 API에서 precision 제공
- RuleBasedPrecisionProvider: Upbit, Bithumb 등 고정 가격 단위 규칙 사용
"""

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.exchanges.models import MarketInfo


class PrecisionProvider(ABC):
    """
    거래소 precision 정보 제공 인터페이스 (Strategy Pattern)

    모든 거래소는 이 인터페이스를 구현하여 tick_size, step_size를 제공합니다.
    - API 기반 거래소: 고정 값 반환 (ApiBasedPrecisionProvider)
    - 규칙 기반 거래소: 가격대별 동적 계산 (RuleBasedPrecisionProvider)
    """

    def __init__(self, market_info: 'MarketInfo'):
        """
        Args:
            market_info: 시장 정보 (symbol, tick_size, step_size 등 포함)
        """
        self.market_info = market_info

    @abstractmethod
    def get_tick_size(self, price: Decimal) -> Decimal:
        """
        주어진 가격에 대한 tick_size 반환

        Args:
            price: 주문 가격

        Returns:
            Decimal: 가격 단위 (예: 0.01, 1, 1000 등)

        Note:
            - API 기반: 고정 값 반환 (price 무시)
            - 규칙 기반: 가격대별 동적 계산
        """
        pass

    @abstractmethod
    def get_step_size(self) -> Decimal:
        """
        수량 단위 반환

        Returns:
            Decimal: 수량 단위 (예: 0.001, 0.01 등)

        Note:
            - 대부분 거래소는 고정 값 (가격과 무관)
        """
        pass


class ApiBasedPrecisionProvider(PrecisionProvider):
    """
    API 기반 거래소용 PrecisionProvider (Binance, Bybit 등)

    거래소 API가 제공하는 고정 tick_size, step_size를 사용합니다.
    가격대와 무관하게 항상 동일한 값을 반환합니다.
    """

    def get_tick_size(self, price: Decimal) -> Decimal:
        """
        고정 tick_size 반환 (가격 무관)

        Args:
            price: 주문 가격 (사용하지 않음)

        Returns:
            Decimal: MarketInfo.tick_size (API에서 제공한 고정 값)
        """
        return self.market_info.tick_size

    def get_step_size(self) -> Decimal:
        """
        고정 step_size 반환

        Returns:
            Decimal: MarketInfo.step_size (API에서 제공한 고정 값)
        """
        return self.market_info.step_size


class RuleBasedPrecisionProvider(PrecisionProvider):
    """
    규칙 기반 거래소용 PrecisionProvider (Upbit, Bithumb 등)

    가격대에 따라 동적으로 tick_size를 계산합니다.

    예시 (Upbit KRW 마켓):
    - 2,000,000원 이상: 1,000원 단위
    - 1,000,000원 ~ 2,000,000원: 500원 단위
    - 100,000원 ~ 1,000,000원: 100원 단위
    - ... (총 16개 구간)

    Note:
        - Phase 1에서는 스텁 구현 (Phase 3에서 실제 규칙 추가)
        - 현재는 market_info.tick_size를 그대로 반환 (기존 동작 유지)
    """

    def __init__(self, market_info: 'MarketInfo', exchange_name: str):
        """
        Args:
            market_info: 시장 정보
            exchange_name: 거래소 이름 (예: UPBIT, BITHUMB)
        """
        super().__init__(market_info)
        self.exchange_name = exchange_name.upper()
        # Phase 3에서 거래소별 규칙 로드 예정
        # self.rules = self._load_price_rules()

    def get_tick_size(self, price: Decimal) -> Decimal:
        """
        가격대별 tick_size 반환 (Phase 3에서 구현)

        Args:
            price: 주문 가격

        Returns:
            Decimal: 가격대에 맞는 tick_size

        Note:
            Phase 1 스텁: market_info.tick_size 반환 (기존 동작 유지)
            Phase 3: 실제 가격대별 규칙 적용
        """
        # Phase 1: 스텁 구현 (기존 tick_size 반환)
        # Phase 3: 아래 로직 활성화 예정
        # return self._calculate_tick_size_by_price(price)
        return self.market_info.tick_size

    def get_step_size(self) -> Decimal:
        """
        수량 단위 반환

        Returns:
            Decimal: market_info.step_size (고정 값)
        """
        return self.market_info.step_size

    # Phase 3에서 구현 예정
    # def _load_price_rules(self) -> List[PriceRule]:
    #     """거래소별 가격 규칙 로드"""
    #     pass
    #
    # def _calculate_tick_size_by_price(self, price: Decimal) -> Decimal:
    #     """가격대에 맞는 tick_size 계산"""
    #     pass
