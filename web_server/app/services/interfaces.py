"""
서비스 인터페이스 정의
의존성 주입을 위한 추상화 레이어
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from decimal import Decimal
from app.models import Account
from app.constants import MarketType


class IExchangeService(ABC):
    """거래소 서비스 인터페이스"""

    @abstractmethod
    def get_exchange(self, account: Account) -> Optional[Any]:
        """거래소 인스턴스 반환"""
        pass

    @abstractmethod
    def create_order(self, account: Account, symbol: str, side: str,
                    quantity: Decimal, order_type: str,
                    market_type: str = MarketType.SPOT,
                    price: Optional[Decimal] = None,
                    stop_price: Optional[Decimal] = None) -> Dict[str, Any]:
        """주문 생성"""
        pass

    @abstractmethod
    def cancel_order(self, account: Account, order_id: str, symbol: str) -> Dict[str, Any]:
        """주문 취소"""
        pass

    @abstractmethod
    def fetch_balance(self, account: Account) -> Dict[str, Any]:
        """잔고 조회"""
        pass


class ITradingService(ABC):
    """트레이딩 서비스 인터페이스"""

    @abstractmethod
    def execute_trade(self, strategy, account, symbol: str, side: str,
                     quantity: Decimal, order_type: str, **kwargs) -> Dict[str, Any]:
        """거래 실행"""
        pass

    @abstractmethod
    def set_orchestrator(self, orchestrator):
        """오케스트레이터 설정"""
        pass


class IPositionService(ABC):
    """포지션 서비스 인터페이스"""

    @abstractmethod
    def update_position(self, position, side: str, quantity: Decimal, price: Decimal):
        """포지션 업데이트"""
        pass

    @abstractmethod
    def calculate_unrealized_pnl(self):
        """미실현 손익 계산"""
        pass


class IOrderService(ABC):
    """주문 서비스 인터페이스"""

    @abstractmethod
    def create_open_order(self, strategy_account_id: int, exchange_order_id: str,
                         symbol: str, side: str, quantity: Decimal, **kwargs):
        """미체결 주문 생성"""
        pass

    @abstractmethod
    def update_open_orders_status(self) -> Dict[str, Any]:
        """주문 상태 업데이트"""
        pass

    @abstractmethod
    def cancel_order(self, open_order) -> Dict[str, Any]:
        """주문 취소"""
        pass


class IConnectionService(ABC):
    """연결 서비스 인터페이스"""

    @abstractmethod
    def get_exchange_instance(self, account: Account) -> Optional[Any]:
        """거래소 인스턴스 반환"""
        pass

    @abstractmethod
    def test_connection(self, account: Account) -> bool:
        """연결 테스트"""
        pass


class IPrecisionCacheService(ABC):
    """정밀도 캐시 서비스 인터페이스"""

    @abstractmethod
    def get_precision_info(self, exchange_name: str, symbol: str, market_type: str) -> Optional[Dict[str, Any]]:
        """정밀도 정보 조회"""
        pass

    @abstractmethod
    def warm_up_cache(self, exchange_service_instance):
        """캐시 웜업"""
        pass


class IRateLimitService(ABC):
    """Rate Limit 서비스 인터페이스"""

    @abstractmethod
    def wait_if_needed(self, exchange_name: str) -> float:
        """필요시 대기"""
        pass

    @abstractmethod
    def check_rate_limit(self, exchange_name: str) -> Dict[str, Any]:
        """Rate limit 체크"""
        pass


class IWebhookService(ABC):
    """웹훅 서비스 인터페이스"""

    @abstractmethod
    def process_webhook(self, token: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """웹훅 처리"""
        pass