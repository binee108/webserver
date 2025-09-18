"""
동기 래퍼 클래스

Native async 구현을 CCXT처럼 동기적으로 사용할 수 있게 하는 래퍼입니다.
CCXT와의 완벽한 호환성을 유지하면서 Native 구현의 성능 이점을 제공합니다.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from concurrent.futures import ThreadPoolExecutor
import inspect

from .base import BaseExchange

logger = logging.getLogger(__name__)


class SyncExchangeWrapper:
    """
    Native async 구현을 동기적으로 사용할 수 있게 하는 래퍼
    
    특징:
    - CCXT와 동일한 메서드 시그니처
    - async 메서드를 동기적으로 호출
    - 성능 최적화를 위한 이벤트 루프 재사용
    - 스레드 안전성 보장
    """
    
    def __init__(self, async_exchange: BaseExchange):
        """
        Args:
            async_exchange: Native async 구현 인스턴스
        """
        self._async_exchange = async_exchange
        self._loop = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="SyncWrapper")
        
        # 메타데이터 복사
        self._implementation_type = "custom"
        
        # CCXT 호환성을 위한 속성들
        self.id = getattr(async_exchange, 'id', async_exchange.__class__.__name__.lower())
        self.name = getattr(async_exchange, 'name', async_exchange.__class__.__name__)
        self.options = getattr(async_exchange, 'options', {})
        
        logger.info(f"🔄 SyncExchangeWrapper 초기화: {self.name}")
    
    def _run_async(self, coro):
        """
        코루틴을 동기적으로 실행
        
        이벤트 루프 재사용으로 성능 최적화
        """
        try:
            # 기존 이벤트 루프가 있으면 새 스레드에서 실행
            if asyncio.get_running_loop():
                future = self._executor.submit(asyncio.run, coro)
                return future.result()
        except RuntimeError:
            pass
        
        # 새 이벤트 루프에서 실행
        return asyncio.run(coro)
    
    def _get_async_method(self, method_name: str):
        """async 메서드 가져오기"""
        method = getattr(self._async_exchange, method_name, None)
        if method is None:
            raise AttributeError(f"'{self._async_exchange.__class__.__name__}' has no attribute '{method_name}'")
        
        if not inspect.iscoroutinefunction(method):
            # 이미 동기 메서드인 경우 그대로 반환
            return method
            
        # async 메서드를 동기 래퍼로 감싸기
        def sync_wrapper(*args, **kwargs):
            coro = method(*args, **kwargs)
            return self._run_async(coro)
        
        return sync_wrapper
    
    def _get_method_signature(self, method_name: str) -> int:
        """메서드의 파라미터 개수를 반환"""
        method = getattr(self._async_exchange, method_name, None)
        if method is None:
            return 0
        
        sig = inspect.signature(method)
        # self 제외하고 필수 파라미터 개수 계산
        required_params = sum(1 for p in sig.parameters.values() 
                             if p.name != 'self' and p.default == inspect.Parameter.empty)
        return required_params
    
    # ========== 주요 거래 메서드들 ==========
    
    def create_order(self, symbol: str, type: str, side: str, amount: float,
                    price: Optional[float] = None, params: Optional[Dict] = None) -> Dict[str, Any]:
        """주문 생성 (동기)"""
        method = self._get_async_method('create_order')
        result = method(symbol, type, side, amount, price, params)

        # Native 객체를 딕셔너리로 변환
        if hasattr(result, 'to_dict'):
            return result.to_dict()
        return result
    
    def create_market_order(self, symbol: str, side: str, amount: float, 
                           params: Optional[Dict] = None) -> Dict[str, Any]:
        """시장가 주문 생성 (동기)"""
        return self.create_order(symbol, 'market', side, amount, None, params)
    
    def create_limit_order(self, symbol: str, side: str, amount: float, price: float,
                          params: Optional[Dict] = None) -> Dict[str, Any]:
        """지정가 주문 생성 (동기)"""
        return self.create_order(symbol, 'limit', side, amount, price, params)
    
    def cancel_order(self, order_id: str, symbol: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """주문 취소 (동기)"""
        method = self._get_async_method('cancel_order')
        return method(order_id, symbol, params)
    
    def fetch_order(self, order_id: str, symbol: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """주문 조회 (동기)"""
        method = self._get_async_method('fetch_order')

        # Native 메서드 시그니처 확인
        sig = inspect.signature(getattr(self._async_exchange, 'fetch_order'))
        param_names = [p.name for p in sig.parameters.values() if p.name != 'self']

        if len(param_names) == 2:  # (order_id, symbol)
            result = method(order_id, symbol)
        else:  # (order_id, symbol, params)
            result = method(order_id, symbol, params)

        # Native 객체를 딕셔너리로 변환
        if hasattr(result, 'to_dict'):
            return result.to_dict()
        return result
    
    def fetch_open_orders(self, symbol: Optional[str] = None, params: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """미체결 주문 조회 (동기)"""
        method = self._get_async_method('fetch_open_orders')

        # Native 메서드 시그니처 확인
        sig = inspect.signature(getattr(self._async_exchange, 'fetch_open_orders'))
        param_names = [p.name for p in sig.parameters.values() if p.name != 'self']

        if len(param_names) == 0:  # ()
            result = method()
        elif len(param_names) == 1:  # (symbol)
            result = method(symbol)
        else:  # (symbol, params)
            result = method(symbol, params)

        # Native 객체를 딕셔너리로 변환 (리스트의 각 항목)
        if isinstance(result, list):
            return [item.to_dict() if hasattr(item, 'to_dict') else item for item in result]
        return result
    
    def fetch_balance(self, params: Optional[Dict] = None) -> Dict[str, Any]:
        """잔액 조회 (동기)"""
        method = self._get_async_method('fetch_balance')
        return method(params)
    
    def fetch_ticker(self, symbol: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """시세 조회 (동기)"""
        method = self._get_async_method('fetch_ticker')

        # Native 메서드 시그니처 확인
        sig = inspect.signature(getattr(self._async_exchange, 'fetch_ticker'))
        param_names = [p.name for p in sig.parameters.values() if p.name != 'self']

        if len(param_names) == 1:  # (symbol)
            result = method(symbol)
        else:  # (symbol, params)
            result = method(symbol, params)

        # Native 객체를 딕셔너리로 변환
        if hasattr(result, 'to_dict'):
            return result.to_dict()
        return result
    
    def load_markets(self, reload: bool = False) -> Dict[str, Any]:
        """마켓 정보 로드 (동기)"""
        method = self._get_async_method('load_markets')
        return method(reload)
    
    # ========== 속성 및 메타데이터 ==========
    
    @property
    def markets(self) -> Dict[str, Any]:
        """마켓 정보 (CCXT 호환)"""
        if hasattr(self._async_exchange, 'cache') and hasattr(self._async_exchange.cache, 'markets'):
            return self._async_exchange.cache.markets
        return {}
    
    @property
    def symbols(self) -> List[str]:
        """심볼 목록 (CCXT 호환)"""
        return list(self.markets.keys())
    
    def market(self, symbol: str) -> Optional[Dict[str, Any]]:
        """특정 심볼의 마켓 정보 (CCXT 호환)"""
        return self.markets.get(symbol)
    
    def symbol(self, base: str, quote: str) -> str:
        """Base/Quote에서 심볼 생성 (CCXT 호환)"""
        return f"{base}/{quote}"
    
    # ========== 통계 및 메타데이터 ==========
    
    def get_stats(self) -> Dict[str, Any]:
        """통계 정보 조회"""
        if hasattr(self._async_exchange, 'get_stats'):
            return self._async_exchange.get_stats()
        return {}
    
    def __getattr__(self, name: str):
        """
        동적 속성 접근
        
        Native 구현의 모든 속성과 메서드에 접근 가능하게 함
        """
        attr = getattr(self._async_exchange, name, None)
        if attr is None:
            raise AttributeError(f"'{self.__class__.__name__}' has no attribute '{name}'")
        
        # 메서드인 경우 동기 래퍼 적용
        if callable(attr) and inspect.iscoroutinefunction(attr):
            def sync_wrapper(*args, **kwargs):
                coro = attr(*args, **kwargs)
                return self._run_async(coro)
            return sync_wrapper
        
        # 속성인 경우 그대로 반환
        return attr
    
    def __del__(self):
        """리소스 정리"""
        if hasattr(self, '_executor'):
            self._executor.shutdown(wait=False)