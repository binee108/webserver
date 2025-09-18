"""
Exchange Interfaces

거래소 구현체가 따라야 하는 인터페이스 정의
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any


class ExchangeInterface(ABC):
    """CCXT 호환 동기 거래소 구현체 인터페이스"""
    
    @abstractmethod
    def load_markets(self) -> Dict[str, Any]:
        """시장 정보 로드"""
        pass
    
    @abstractmethod
    def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """티커 정보 조회"""
        pass
    
    @abstractmethod
    def fetch_balance(self) -> Dict[str, Any]:
        """잔액 정보 조회"""
        pass
    
    @abstractmethod
    def create_order(self, symbol: str, order_type: str, side: str, 
                    amount: float, price: Optional[float] = None, 
                    params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """주문 생성"""
        pass
    
    @abstractmethod
    def cancel_order(self, order_id: str, symbol: str, 
                    params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """주문 취소"""
        pass
    
    @abstractmethod
    def fetch_order(self, order_id: str, symbol: str, 
                   params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """주문 정보 조회"""
        pass


class AsyncExchangeInterface(ABC):
    """Native 비동기 거래소 구현체 인터페이스"""
    
    @abstractmethod
    async def load_markets(self) -> Dict[str, Any]:
        """시장 정보 로드"""
        pass
    
    @abstractmethod
    async def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """티커 정보 조회"""
        pass
    
    @abstractmethod
    async def fetch_balance(self) -> Dict[str, Any]:
        """잔액 정보 조회"""
        pass
    
    @abstractmethod
    async def create_order(self, symbol: str, order_type: str, side: str, 
                          amount: float, price: Optional[float] = None, 
                          params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """주문 생성"""
        pass
    
    @abstractmethod
    async def cancel_order(self, order_id: str, symbol: str, 
                          params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """주문 취소"""
        pass
    
    @abstractmethod
    async def fetch_order(self, order_id: str, symbol: str, 
                         params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """주문 정보 조회"""
        pass