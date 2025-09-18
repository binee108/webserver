"""
거래소 API 추상 기본 클래스

모든 거래소 구현이 상속받아야 하는 기본 인터페이스를 정의합니다.
CCXT와 호환되는 메서드 시그니처를 유지하면서 성능을 최적화합니다.
"""

import hmac
import hashlib
import time
import requests
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from urllib.parse import urlencode
from decimal import Decimal, ROUND_DOWN

from .cache import MarketDataCache
from .models import MarketInfo, Balance, Order, Ticker, Position
from .interfaces import AsyncExchangeInterface

logger = logging.getLogger(__name__)


class ExchangeError(Exception):
    """거래소 API 에러"""
    def __init__(self, message: str, code: int = None, response: Dict = None):
        super().__init__(message)
        self.code = code
        self.response = response


class NetworkError(ExchangeError):
    """네트워크 에러"""
    pass


class AuthenticationError(ExchangeError):
    """인증 에러"""
    pass


class InsufficientFunds(ExchangeError):
    """잔액 부족 에러"""
    pass


class InvalidOrder(ExchangeError):
    """잘못된 주문 에러"""
    pass


class BaseExchange(AsyncExchangeInterface):
    """
    거래소 API 추상 기본 클래스
    
    특징:
    - HTTP 세션 재사용으로 연결 최적화
    - 메모리 캐싱으로 무지연 마켓 데이터 액세스
    - 비동기 백그라운드 업데이트
    - 정밀한 Rate Limit 관리
    """
    
    def __init__(self, api_key: str, secret: str, testnet: bool = False):
        self.api_key = api_key
        self.secret = secret
        self.testnet = testnet
        
        # HTTP 세션 (Keep-alive 연결)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'WebServer-Custom-Exchange/1.0',
            'X-MBX-APIKEY': api_key
        })
        
        # 캐싱 시스템
        self.cache = MarketDataCache(self.__class__.__name__)
        
        # Rate Limit 관리
        self._request_times: List[float] = []
        self._weight_used = 0
        self._weight_reset_time = 0
        
        # 통계
        self.stats = {
            'api_calls': 0,
            'cache_hits': 0,
            'errors': 0,
            'last_update': None
        }
        
        logger.info(f"🏛️ {self.__class__.__name__} 초기화 완료 (testnet={testnet})")
    
    @property
    @abstractmethod
    def base_url(self) -> str:
        """거래소 API 기본 URL"""
        pass
    
    @property
    @abstractmethod  
    def market_type(self) -> str:
        """마켓 타입 (SPOT, FUTURES)"""
        pass
    
    def _get_timestamp(self) -> int:
        """현재 타임스탬프 (밀리초)"""
        return int(time.time() * 1000)
    
    def _sign_request(self, params: Dict[str, Any]) -> str:
        """요청 서명 생성"""
        query_string = urlencode(params)
        signature = hmac.new(
            self.secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return f"{query_string}&signature={signature}"
    
    def _check_rate_limit(self, weight: int = 1):
        """Rate Limit 체크 및 대기"""
        current_time = time.time()
        
        # 1분 윈도우 정리
        self._request_times = [t for t in self._request_times if current_time - t < 60]
        
        # Weight 기반 제한 체크
        if current_time > self._weight_reset_time:
            self._weight_used = 0
            self._weight_reset_time = current_time + 60  # 1분 윈도우
        
        # Rate Limit 초과 시 대기
        if len(self._request_times) >= self.get_rate_limit() or self._weight_used + weight > self.get_weight_limit():
            sleep_time = 1.0  # 기본 대기 시간
            logger.warning(f"⏳ Rate Limit 접근, {sleep_time}초 대기")
            time.sleep(sleep_time)
        
        self._request_times.append(current_time)
        self._weight_used += weight
    
    @abstractmethod
    def get_rate_limit(self) -> int:
        """분당 요청 제한"""
        pass
    
    @abstractmethod
    def get_weight_limit(self) -> int:
        """분당 Weight 제한"""
        pass
    
    def _make_request(self, method: str, endpoint: str, params: Dict = None, signed: bool = False, weight: int = 1) -> Dict[str, Any]:
        """HTTP 요청 실행"""
        self._check_rate_limit(weight)
        
        params = params or {}
        url = f"{self.base_url}{endpoint}"
        
        # 서명이 필요한 요청
        if signed:
            params['timestamp'] = self._get_timestamp()
            query_string = self._sign_request(params)
            
            if method.upper() == 'GET':
                url = f"{url}?{query_string}"
                params = None
            else:
                # POST는 body에 데이터 전송
                pass
        
        try:
            self.stats['api_calls'] += 1
            
            if method.upper() == 'GET':
                response = self.session.get(url, params=params, timeout=10)
            elif method.upper() == 'POST':
                if signed:
                    response = self.session.post(url, data=query_string, 
                                                headers={'Content-Type': 'application/x-www-form-urlencoded'})
                else:
                    response = self.session.post(url, json=params)
            elif method.upper() == 'DELETE':
                if signed:
                    response = self.session.delete(url, data=query_string,
                                                  headers={'Content-Type': 'application/x-www-form-urlencoded'})
                else:
                    response = self.session.delete(url, params=params)
            else:
                raise ValueError(f"지원되지 않는 HTTP 메서드: {method}")
            
            # 응답 처리
            if response.status_code == 200:
                return response.json()
            else:
                self._handle_error_response(response)
                
        except requests.exceptions.Timeout:
            raise NetworkError("요청 타임아웃")
        except requests.exceptions.ConnectionError as e:
            raise NetworkError(f"연결 실패: {e}")
        except Exception as e:
            self.stats['errors'] += 1
            logger.error(f"API 요청 실패 {method} {endpoint}: {e}")
            raise
    
    def _handle_error_response(self, response: requests.Response):
        """에러 응답 처리"""
        try:
            error_data = response.json()
            code = error_data.get('code', response.status_code)
            message = error_data.get('msg', 'Unknown error')
            
            # 에러 타입별 분류
            if code in [-1021, -1022]:  # Timestamp errors
                raise AuthenticationError(f"타임스탬프 에러: {message}", code, error_data)
            elif code in [-1100, -1101, -1102]:  # Invalid parameters
                raise InvalidOrder(f"잘못된 파라미터: {message}", code, error_data)
            elif code in [-2010]:  # Insufficient funds
                raise InsufficientFunds(f"잔액 부족: {message}", code, error_data)
            elif code in [-1003, -1015]:  # Rate limit
                raise ExchangeError(f"Rate Limit 초과: {message}", code, error_data)
            else:
                raise ExchangeError(f"API 에러: {message}", code, error_data)
                
        except ValueError:
            # JSON 파싱 실패
            raise ExchangeError(f"HTTP {response.status_code}: {response.text}")
    
    def round_amount(self, symbol: str, amount: float) -> Decimal:
        """수량을 거래소 규칙에 맞게 반올림"""
        market_info = self.cache.get_market(symbol)
        if not market_info:
            logger.warning(f"마켓 정보 없음, 기본 precision 사용: {symbol}")
            return Decimal(str(amount)).quantize(Decimal('0.00000001'), rounding=ROUND_DOWN)
        
        # Step size에 맞춰 반올림
        step_size = market_info.step_size
        if step_size > 0:
            precision = len(str(step_size).split('.')[-1].rstrip('0'))
            quantized = Decimal(str(amount)).quantize(Decimal(f'0.{"0" * precision}'), rounding=ROUND_DOWN)
            
            # 최소 수량 체크
            if quantized < market_info.min_qty:
                raise InvalidOrder(f"최소 주문 수량 미달: {quantized} < {market_info.min_qty}")
            
            return quantized
        
        return Decimal(str(amount))
    
    def round_price(self, symbol: str, price: float) -> Decimal:
        """가격을 거래소 규칙에 맞게 반올림"""
        market_info = self.cache.get_market(symbol)
        if not market_info:
            logger.warning(f"마켓 정보 없음, 기본 precision 사용: {symbol}")
            return Decimal(str(price)).quantize(Decimal('0.00000001'), rounding=ROUND_DOWN)
        
        # Tick size에 맞춰 반올림
        tick_size = market_info.tick_size
        if tick_size > 0:
            precision = len(str(tick_size).split('.')[-1].rstrip('0'))
            return Decimal(str(price)).quantize(Decimal(f'0.{"0" * precision}'), rounding=ROUND_DOWN)
        
        return Decimal(str(price))
    
    # 캐시 관련 메서드 (무지연 액세스)
    def get_market_info(self, symbol: str) -> Optional[MarketInfo]:
        """마켓 정보 조회 (캐시에서 즉시 반환)"""
        return self.cache.get_market(symbol)
    
    def get_precision_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Precision 정보 조회 (캐시에서 즉시 반환)"""
        return self.cache.get_precision(symbol)
    
    # 추상 메서드들 - 각 거래소에서 구현
    @abstractmethod
    async def load_markets(self, reload: bool = False) -> Dict[str, MarketInfo]:
        """마켓 정보 로드 및 캐싱"""
        pass
    
    @abstractmethod
    async def fetch_balance(self) -> Dict[str, Balance]:
        """잔액 조회"""
        pass
    
    @abstractmethod  
    async def fetch_ticker(self, symbol: str) -> Ticker:
        """시세 조회"""
        pass
    
    @abstractmethod
    async def create_order(self, symbol: str, type: str, side: str, amount: float, price: float = None, params: Dict = None) -> Order:
        """주문 생성"""
        pass
    
    @abstractmethod
    async def cancel_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        """주문 취소"""
        pass
    
    @abstractmethod
    async def fetch_order(self, order_id: str, symbol: str) -> Order:
        """주문 조회"""
        pass
    
    @abstractmethod
    async def fetch_open_orders(self, symbol: str = None) -> List[Order]:
        """미체결 주문 조회"""
        pass
    
    def get_stats(self) -> Dict[str, Any]:
        """통계 정보 반환"""
        cache_stats = self.cache.get_stats()
        return {
            **self.stats,
            'cache': cache_stats,
            'rate_limit': {
                'requests_in_window': len(self._request_times),
                'weight_used': self._weight_used
            }
        }
    
    def __del__(self):
        """소멸자 - 리소스 정리"""
        if hasattr(self, 'session'):
            self.session.close()