"""
거래소 연동 서비스 모듈
CCXT를 사용하여 다중 거래소 지원
"""

import ccxt
import time
import logging
from typing import Dict, Any, Optional, List
from functools import wraps
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from app.models import Account
from app.constants import MarketType, Exchange, OrderType
from threading import Lock  # 🆕 스레드 안전한 캐싱을 위한 import 추가
import json  # 🆕 precision 데이터 직렬화용
from app.services.universal_exchange import UniversalExchange, universal_exchange_manager  # 🆕 UniversalExchange 추가

logger = logging.getLogger(__name__)

class ExchangeError(Exception):
    """거래소 관련 오류"""
    pass

# 🆕 Precision 정보 전용 캐시 클래스
class PrecisionCache:
    """Precision 정보 전용 고성능 캐시 시스템"""
    
    def __init__(self):
        self.precision_data = {}  # {exchange_symbol: precision_info}
        self.last_update = {}     # {exchange: timestamp}
        self.cache_duration = 86400  # 24시간 (precision은 자주 변하지 않음)
        self.lock = Lock()
        self.api_call_stats = {
            'cache_hits': 0,
            'cache_misses': 0,
            'api_calls_saved': 0
        }
    
    def get_precision_info(self, exchange_name: str, symbol: str, market_type: str) -> Optional[Dict[str, Any]]:
        """precision 정보 조회 (MarketType 상수 기반 캐시)"""
        from app.constants import MarketType
        
        # market_type 정규화 (필수)
        normalized_market_type = MarketType.normalize(market_type)
        
        with self.lock:
            # MarketType 상수 기반 캐시 키 생성
            cache_key = f"{exchange_name.lower()}_{normalized_market_type}_{symbol}"
            
            if cache_key in self.precision_data:
                precision_info, timestamp = self.precision_data[cache_key]
                if time.time() - timestamp < self.cache_duration:
                    self.api_call_stats['cache_hits'] += 1
                    logger.debug(f"📈 Precision 캐시 히트 (MarketType 기반) - {cache_key}")
                    return precision_info
                else:
                    # 만료된 캐시 제거
                    del self.precision_data[cache_key]
                    logger.debug(f"⏰ Precision 캐시 만료 - {cache_key}")
            
            # 레거시 캐시 키 확인 (점진적 마이그레이션)
            legacy_keys = [
                f"{exchange_name.lower()}_{symbol}",  # 기존 형식
                f"{exchange_name.lower()}_{market_type.lower()}_{symbol}",  # 이전 비정규화 형식
            ]
            
            for legacy_key in legacy_keys:
                if legacy_key in self.precision_data:
                    precision_info, timestamp = self.precision_data[legacy_key]
                    if time.time() - timestamp < self.cache_duration:
                        logger.info(f"📊 레거시 캐시 발견, 새 형식으로 마이그레이션 - {legacy_key} → {cache_key}")
                        # 새 형식으로 저장 후 기존 키 제거
                        self.precision_data[cache_key] = (precision_info, timestamp)
                        del self.precision_data[legacy_key]
                        self.api_call_stats['cache_hits'] += 1
                        return precision_info
                    else:
                        # 만료된 레거시 캐시 제거
                        del self.precision_data[legacy_key]
            
            self.api_call_stats['cache_misses'] += 1
            return None
    
    def set_precision_info(self, exchange_name: str, symbol: str, precision_info: Dict[str, Any], market_type: str):
        """precision 정보 캐싱 (MarketType 상수 기반)"""
        from app.constants import MarketType
        
        # market_type 정규화 (필수)
        normalized_market_type = MarketType.normalize(market_type)
        
        with self.lock:
            # MarketType 상수 기반 캐시 키로만 저장
            cache_key = f"{exchange_name.lower()}_{normalized_market_type}_{symbol}"
            self.precision_data[cache_key] = (precision_info, time.time())
            logger.debug(f"💾 Precision 정보 캐싱 완료 (MarketType 기반) - {cache_key}")
    
    def update_exchange_precision_cache(self, exchange_name: str, exchange_instance) -> int:
        """특정 거래소의 모든 precision 정보 업데이트 (MarketType 상수 기반)"""
        from app.constants import MarketType
        
        try:
            logger.debug(f"{exchange_name} precision 캐시 업데이트 시작 (MarketType 기반)")
            
            # markets 로딩 (백그라운드에서 한 번만)
            if not exchange_instance.markets:
                exchange_instance.load_markets()
            
            updated_count = 0
            current_time = time.time()
            
            with self.lock:
                for symbol, market in exchange_instance.markets.items():
                    precision_info = {
                        'amount': market.get('precision', {}).get('amount'),
                        'price': market.get('precision', {}).get('price'),
                        'limits': market.get('limits', {}),
                        'active': market.get('active', True),
                        'type': market.get('type', 'spot')
                    }
                    
                    # 거래소 API의 market type을 MarketType 상수로 정규화
                    api_market_type = market.get('type', 'spot')
                    normalized_market_type = MarketType.normalize(api_market_type)
                    
                    # MarketType 상수 기반 캐시 키로 저장
                    cache_key = f"{exchange_name.lower()}_{normalized_market_type}_{symbol}"
                    self.precision_data[cache_key] = (precision_info, current_time)
                    
                    updated_count += 1
                
                self.last_update[exchange_name.lower()] = current_time
            
            logger.debug(f"{exchange_name} precision 캐시 업데이트 완료 - {updated_count}개 심볼 (MarketType 기반)")
            return updated_count
            
        except Exception as e:
            logger.error(f"❌ {exchange_name} precision 캐시 업데이트 실패: {str(e)}")
            return 0
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """캐시 성능 통계"""
        with self.lock:
            total_requests = self.api_call_stats['cache_hits'] + self.api_call_stats['cache_misses']
            hit_rate = (self.api_call_stats['cache_hits'] / total_requests * 100) if total_requests > 0 else 0
            
            return {
                'total_cached_symbols': len(self.precision_data),
                'cache_hits': self.api_call_stats['cache_hits'],
                'cache_misses': self.api_call_stats['cache_misses'],
                'hit_rate_percent': round(hit_rate, 2),
                'api_calls_saved': self.api_call_stats['api_calls_saved'],
                'last_updates': self.last_update.copy()
            }
    
    def clear_cache(self, exchange_name: str = None):
        """캐시 정리"""
        with self.lock:
            if exchange_name:
                # 특정 거래소 캐시만 정리
                keys_to_remove = [k for k in self.precision_data.keys() if k.startswith(f"{exchange_name.lower()}_")]
                for key in keys_to_remove:
                    del self.precision_data[key]
                if exchange_name.lower() in self.last_update:
                    del self.last_update[exchange_name.lower()]
                logger.debug(f"{exchange_name} precision 캐시 정리 완료")
            else:
                # 전체 캐시 정리
                self.precision_data.clear()
                self.last_update.clear()
                logger.debug("전체 precision 캐시 정리 완료")
    
    def clear_symbol_cache(self, exchange_name: str, symbol: str):
        """특정 심볼의 precision 캐시 삭제 (잘못된 precision 데이터 제거용)"""
        with self.lock:
            keys_to_remove = [key for key in self.precision_data.keys() 
                            if key.startswith(f"{exchange_name.lower()}_") and key.endswith(f"_{symbol}")]
            
            for key in keys_to_remove:
                del self.precision_data[key]
                
            logger.info(f"🗑️ {exchange_name} {symbol} precision 캐시 삭제됨 ({len(keys_to_remove)}개 키)")
            return len(keys_to_remove)

# 🆕 Rate Limit 관리 클래스
class RateLimitManager:
    """거래소별 Rate Limit 관리"""
    
    # 거래소별 Rate Limit 설정
    EXCHANGE_LIMITS = {
        'binance': {
            'orders_per_second': 10,       # 초당 주문 수
            'orders_per_minute': 1200,     # 분당 주문 수
            'weight_per_minute': 6000,     # 분당 Weight
            'burst_allowance': 5           # 순간적 버스트 허용
        },
        'bybit': {
            'orders_per_second': 10,
            'orders_per_minute': 100,
            'burst_allowance': 3
        },
        'okx': {
            'orders_per_second': 60,       # OKX는 상대적으로 관대
            'orders_per_minute': 2400,
            'burst_allowance': 10
        }
    }
    
    def __init__(self):
        self.request_history = {}  # {exchange: [timestamps]}
        self.locks = {}            # {exchange: Lock}
    
    def _get_exchange_lock(self, exchange: str) -> Lock:
        """거래소별 Lock 반환"""
        if exchange not in self.locks:
            self.locks[exchange] = Lock()
        return self.locks[exchange]
    
    def get_delay_for_orders(self, exchange: str, order_count: int) -> float:
        """배치 주문에 필요한 지연 시간 계산"""
        exchange_lower = exchange.lower()
        limits = self.EXCHANGE_LIMITS.get(exchange_lower, {})
        
        # 기본값 설정 (보수적으로)
        orders_per_second = limits.get('orders_per_second', 5)
        burst_allowance = limits.get('burst_allowance', 2)
        
        if order_count <= burst_allowance:
            # 버스트 허용량 이하면 최소 지연
            return 0.1
        else:
            # 초당 주문 제한에 맞춰 지연 시간 계산 (20% 여유)
            return (1.0 / orders_per_second) * 1.2
    
    def calculate_batch_delays(self, exchange: str, order_count: int) -> List[float]:
        """배치 주문들 간의 지연 시간 리스트 계산"""
        base_delay = self.get_delay_for_orders(exchange, order_count)
        delays = []
        
        exchange_lower = exchange.lower()
        limits = self.EXCHANGE_LIMITS.get(exchange_lower, {})
        burst_allowance = limits.get('burst_allowance', 2)
        
        for i in range(order_count):
            if i == 0:
                # 첫 번째 주문은 지연 없음
                delays.append(0.0)
            elif i < burst_allowance:
                # 버스트 허용량 내에서는 짧은 지연
                delays.append(0.1)
            else:
                # 이후는 계산된 지연 시간 적용
                delays.append(base_delay)
        
        return delays
    
    def wait_if_needed(self, exchange: str, weight: int = 1):
        """필요시 대기하여 rate limit 준수"""
        exchange_lower = exchange.lower()
        limits = self.EXCHANGE_LIMITS.get(exchange_lower, {})
        
        if not limits:
            # 알려지지 않은 거래소는 보수적으로 대기
            time.sleep(0.2)
            return
        
        lock = self._get_exchange_lock(exchange_lower)
        
        with lock:
            current_time = time.time()
            
            # 요청 히스토리 초기화
            if exchange_lower not in self.request_history:
                self.request_history[exchange_lower] = []
            
            history = self.request_history[exchange_lower]
            
            # 1분 이전 요청들 제거
            history[:] = [t for t in history if current_time - t < 60]
            
            # 분당 요청 수 체크
            orders_per_minute = limits.get('orders_per_minute', 100)
            if len(history) >= orders_per_minute:
                # 가장 오래된 요청 시간 기준으로 대기 시간 계산
                oldest_request = min(history)
                wait_time = 60 - (current_time - oldest_request) + 0.1  # 여유시간 0.1초
                if wait_time > 0:
                    logger.info(f"Rate limit 대기: {exchange} - {wait_time:.2f}초")
                    time.sleep(wait_time)
            
            # 현재 요청 시간 기록
            self.request_history[exchange_lower].append(current_time)

def retry_on_failure(max_retries: int = 3, delay: float = 0.25):
    """지수 백오프 재시도 데코레이터"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    error_msg = str(e).lower()
                    
                    # 재시도하지 않아야 할 에러들
                    no_retry_patterns = [
                        'must be greater than minimum',  # 최소 수량 에러
                        'insufficient balance',           # 잔고 부족
                        'invalid api key',                # API 키 오류
                        'permission denied',              # 권한 오류
                        'amount too small',               # 수량 너무 작음
                        'minimum amount',                 # 최소 수량
                        'precision',                      # precision 에러
                        'invalid symbol',                 # 잘못된 심볼
                        'notional must be no smaller',   # 최소 주문 금액 에러
                        'Order would immediately trigger', # STOP 주문 즉시 실행 에러
                    ]
                    
                    # 재시도하지 않을 에러인 경우 즉시 예외 발생
                    if any(pattern in error_msg for pattern in no_retry_patterns):
                        logger.error(f"재시도 불가 에러: {func.__name__}, 오류: {str(e)}")
                        raise ExchangeError(f"주문 생성 실패: {str(e)}")
                    
                    if attempt == max_retries - 1:
                        logger.error(f"최대 재시도 횟수 초과: {func.__name__}, 오류: {str(e)}")
                        raise ExchangeError(f"거래소 API 호출 실패: {str(e)}")
                    
                    wait_time = delay * (2 ** attempt)
                    logger.warning(f"재시도 {attempt + 1}/{max_retries}: {func.__name__}, 대기시간: {wait_time}초")
                    time.sleep(wait_time)
            
            return None
        return wrapper
    return decorator

class ExchangeService:
    """거래소 서비스 클래스"""
    
    # 지원하는 거래소 목록
    SUPPORTED_EXCHANGES = {
        'binance': ccxt.binance,
        'bybit': ccxt.bybit,
        'okx': ccxt.okx
    }
    
    def __init__(self):
        self._exchanges: Dict[str, ccxt.Exchange] = {}
        self._market_cache: Dict[str, tuple] = {}  # 🆕 market 정보 캐시 추가
        self._cache_duration = 3600  # 🆕 캐시 유지 시간 (1시간)
        # 🆕 ticker 정보 캐싱을 위한 딕셔너리 및 락 추가
        self.ticker_cache = {}  # {symbol: {'data': ticker_data, 'timestamp': time, 'account_id': account_id}}
        self.ticker_cache_lock = Lock()  # 스레드 안전한 접근을 위한 락
        self.ticker_cache_ttl = 3  # 3초 TTL (실시간성과 성능의 균형)
        
        # 🆕 Precision 전용 고성능 캐시 시스템
        self.precision_cache = PrecisionCache()
        
        # 🆕 UniversalExchange 매니저 (새로운 거래소 시스템)
        self.universal_manager = universal_exchange_manager
        
        logger.info("🚀 ExchangeService 초기화 완료 - PrecisionCache + UniversalExchange 시스템 활성화")
    
    def get_exchange(self, account: Account, market_type: str = None) -> ccxt.Exchange:
        """계좌 정보로 거래소 인스턴스 생성/반환
        
        Args:
            account: 계좌 정보
            market_type: 마켓 타입 (MarketType.SPOT 또는 MarketType.FUTURES)
                        None인 경우 기존 방식(SPOT) 유지 (하위 호환성)
        
        Returns:
            거래소 인스턴스
        """
        # market_type이 지정된 경우 UniversalExchange 사용
        if market_type is not None:
            try:
                # API 인증 정보 구성
                api_credentials = {
                    'apiKey': account.public_api,
                    'secret': account.secret_api,
                }
                
                # OKX passphrase 처리 (필요시)
                if account.exchange == 'okx' and hasattr(account, 'passphrase') and account.passphrase:
                    api_credentials['password'] = account.passphrase
                
                # UniversalExchange 인스턴스 가져오기
                universal = self.universal_manager.get_exchange(account.exchange, api_credentials)
                
                # 지정된 market_type에 맞는 인스턴스 반환
                instance = universal.get_instance(market_type)
                
                logger.debug(f"🔧 UniversalExchange 사용: {account.exchange} {market_type} (계좌 ID: {account.id})")
                return instance
                
            except ValueError as e:
                # UniversalExchange에서 지원하지 않는 거래소인 경우 기존 방식 사용
                logger.warning(f"⚠️ UniversalExchange 미지원 거래소, 기존 방식 사용: {account.exchange} - {e}")
                # 기존 방식으로 fallback
            except Exception as e:
                logger.error(f"❌ UniversalExchange 실패, 기존 방식 사용: {account.exchange} - {e}")
                # 기존 방식으로 fallback
        
        # 기존 방식 (하위 호환성 유지)
        cache_key = f"{account.exchange}_{account.id}"
        
        if cache_key not in self._exchanges:
            if account.exchange not in self.SUPPORTED_EXCHANGES:
                raise ExchangeError(f"지원하지 않는 거래소: {account.exchange}")
            
            exchange_class = self.SUPPORTED_EXCHANGES[account.exchange]
            
            # 거래소별 설정
            config = {
                'apiKey': account.public_api,
                'secret': account.secret_api,
                'sandbox': False,
                'enableRateLimit': True,
                'timeout': 30000,
            }
            
            # Bybit의 경우 추가 설정
            if account.exchange == Exchange.BYBIT_LOWER:
                config['options'] = {'defaultType': 'linear'}
            
            # Binance의 경우 추가 설정
            if account.exchange == Exchange.BINANCE_LOWER:
                config['options'] = {
                    'warnOnFetchOpenOrdersWithoutSymbol': False,
                    'defaultType': 'spot'
                }
            
            try:
                exchange = exchange_class(config)
                self._exchanges[cache_key] = exchange
                logger.info(f"거래소 인스턴스 생성 (기존 방식): {account.exchange} (계좌 ID: {account.id})")
            except Exception as e:
                raise ExchangeError(f"거래소 연결 실패: {str(e)}")
        
        return self._exchanges[cache_key]
    
    @retry_on_failure(max_retries=10)
    def test_connection(self, account: Account) -> Dict[str, Any]:
        """거래소 연결 테스트"""
        try:
            exchange = self.get_exchange(account)
            balance = exchange.fetch_balance()
            
            return {
                'success': True,
                'message': '연결 성공',
                'total_balance': balance.get('total', {}),
                'exchange_info': {
                    'name': exchange.name,
                    'version': exchange.version,
                    'has_futures': exchange.has.get('fetchPositions', False)
                }
            }
        except Exception as e:
            logger.error(f"연결 테스트 실패 - 계좌 ID: {account.id}, 오류: {str(e)}")
            return {
                'success': False,
                'message': f'연결 실패: {str(e)}'
            }
    
    @retry_on_failure(max_retries=10)
    def test_connection_simple(self, exchange_name: str, public_api: str, secret_api: str, passphrase: str = None) -> Dict[str, Any]:
        """간단한 거래소 연결 테스트 (계좌 생성 시 사용)"""
        try:
            if exchange_name not in self.SUPPORTED_EXCHANGES:
                raise ExchangeError(f"지원하지 않는 거래소: {exchange_name}")
            
            exchange_class = self.SUPPORTED_EXCHANGES[exchange_name]
            
            # 거래소별 설정
            config = {
                'apiKey': public_api,
                'secret': secret_api,
                'sandbox': False,  # 기본적으로 실제 환경에서 테스트
                'enableRateLimit': True,
                'timeout': 30000,
            }
            
            # Bybit의 경우 추가 설정
            if exchange_name == Exchange.BYBIT_LOWER:
                config['options'] = {'defaultType': 'linear'}  # USDT 선물
            
            # OKX의 경우 passphrase 필요
            if exchange_name == 'okx' and passphrase:
                config['password'] = passphrase
            
            exchange = exchange_class(config)
            balance = exchange.fetch_balance()
            
            return {
                'success': True,
                'message': '연결 성공',
                'total_balance': balance.get('total', {}),
                'exchange_info': {
                    'name': exchange.name,
                    'version': exchange.version,
                    'has_futures': exchange.has.get('fetchPositions', False)
                }
            }
        except Exception as e:
            logger.error(f"연결 테스트 실패 - 거래소: {exchange_name}, 오류: {str(e)}")
            return {
                'success': False,
                'message': f'연결 실패: {str(e)}'
            }
    
    @retry_on_failure(max_retries=10)
    def get_balance(self, account: Account, currency: str = None, market_type: str = MarketType.SPOT) -> Dict[str, Any]:
        """잔고 조회 (마켓 타입별 분리)"""
        exchange = self.get_exchange(account)
        
        try:
            # 마켓 타입에 따라 다른 방식으로 잔고 조회 (대소문자 구분 없이)
            market_type_upper = market_type.upper() if market_type else 'SPOT'
            if market_type_upper in ['FUTURES', 'FUTURE']:
                # 선물 잔고 조회
                if hasattr(exchange, 'fetch_balance') and exchange.has.get('fetchBalance'):
                    # 거래소별 선물 잔고 조회 방식
                    if account.exchange == Exchange.BINANCE_LOWER:
                        # Binance 선물 잔고
                        exchange.options['defaultType'] = 'future'
                        balance = exchange.fetch_balance()
                    elif account.exchange == Exchange.BYBIT_LOWER:
                        # Bybit 선물 잔고 (이미 linear로 설정됨)
                        balance = exchange.fetch_balance()
                    elif account.exchange == 'okx':
                        # OKX 선물 잔고
                        exchange.options['defaultType'] = 'swap'
                        balance = exchange.fetch_balance()
                    else:
                        # 기본 선물 잔고 조회
                        balance = exchange.fetch_balance()
                else:
                    raise ExchangeError(f"거래소 {account.exchange}에서 선물 잔고 조회를 지원하지 않습니다")
            else:
                # 현물 잔고 조회 (기본값)
                if account.exchange == Exchange.BINANCE_LOWER:
                    exchange.options['defaultType'] = 'spot'
                elif account.exchange == Exchange.BYBIT_LOWER:
                    exchange.options['defaultType'] = 'spot'
                elif account.exchange == 'okx':
                    exchange.options['defaultType'] = 'spot'
                
                balance = exchange.fetch_balance()
            
            if currency:
                # Debug logging for balance structure
                logger.debug(f"Balance fetched for {account.exchange} {market_type}: keys={list(balance.keys())[:10]}")
                if currency in balance:
                    logger.debug(f"Currency {currency} balance: {balance.get(currency)}")
                
                currency_balance = balance.get(currency, {})
                result = {
                    'free': currency_balance.get('free', 0) if isinstance(currency_balance, dict) else 0,
                    'used': currency_balance.get('used', 0) if isinstance(currency_balance, dict) else 0,
                    'total': currency_balance.get('total', 0) if isinstance(currency_balance, dict) else 0
                }
                
                # If total is 0, try to get it from the root balance object
                if result['total'] == 0 and 'total' in balance:
                    total_balance = balance.get('total', {})
                    if isinstance(total_balance, dict) and currency in total_balance:
                        result['total'] = total_balance[currency]
                
                logger.debug(f"Returning balance for {currency}: {result}")
                return result
            
            return balance
            
        except Exception as e:
            logger.error(f"잔고 조회 실패 - 계좌: {account.id}, 마켓: {market_type}, 오류: {str(e)}")
            raise ExchangeError(f"잔고 조회 실패: {str(e)}")
    
    @retry_on_failure(max_retries=10)
    def get_balance_by_market_type(self, account: Account, market_type: str, currency: str = 'USDT') -> float:
        """마켓 타입별 특정 통화 잔고 조회 (자본 할당용)"""
        try:
            balance_info = self.get_balance(account, currency, market_type)
            return balance_info.get('total', 0)
        except Exception as e:
            logger.error(f"마켓별 잔고 조회 실패 - 계좌: {account.id}, 마켓: {market_type}, 통화: {currency}, 오류: {str(e)}")
            return 0.0
    
    @retry_on_failure(max_retries=10)
    def create_order(self, account: Account, symbol: str, order_type: str, 
                    side: str, amount: float, price: float = None, stop_price: float = None, market_type: str = MarketType.SPOT) -> Dict[str, Any]:
        """주문 생성"""
        exchange = self.get_exchange(account)
        
        try:
            # 마켓 타입에 따라 거래소 설정 (대소문자 구분 없이)
            market_type_upper = market_type.upper() if market_type else 'SPOT'
            if market_type_upper in ['FUTURES', 'FUTURE']:
                # 선물 거래 설정
                if account.exchange == Exchange.BINANCE_LOWER:
                    exchange.options['defaultType'] = 'future'
                elif account.exchange == Exchange.BYBIT_LOWER:
                    exchange.options['defaultType'] = 'linear'  # USDT 선물
                elif account.exchange == 'okx':
                    exchange.options['defaultType'] = 'swap'
            else:
                # 현물 거래 설정 (기본값)
                if account.exchange == Exchange.BINANCE_LOWER:
                    exchange.options['defaultType'] = 'spot'
                elif account.exchange == Exchange.BYBIT_LOWER:
                    exchange.options['defaultType'] = 'spot'
                elif account.exchange == 'okx':
                    exchange.options['defaultType'] = 'spot'
            
            # side를 거래소 API 형식으로 변환 (BUY/SELL -> buy/sell)
            api_side = side.lower() if isinstance(side, str) else side
            
            if order_type.lower() == 'market':
                order = exchange.create_market_order(symbol, api_side, amount)
            elif order_type.lower() == 'limit':
                if price is None:
                    raise ExchangeError("지정가 주문에는 가격이 필요합니다")
                order = exchange.create_limit_order(symbol, api_side, amount, price)
            elif order_type.lower() == 'stop_limit':
                if stop_price is None:
                    raise ExchangeError("STOP_LIMIT 주문에는 stop_price가 필요합니다")
                if price is None:
                    raise ExchangeError("STOP_LIMIT 주문에는 limit price가 필요합니다")
                # STOP_LIMIT 주문: stop_price에서 트리거되어 price로 지정가 주문 실행
                params = {
                    'stopPrice': stop_price,
                    'type': 'STOP_LOSS_LIMIT' if account.exchange == 'binance' else 'StopLimit'
                }
                order = exchange.create_order(symbol, 'limit', api_side, amount, price, params)
            elif order_type.lower() == 'stop_market':
                if stop_price is None:
                    raise ExchangeError("STOP_MARKET 주문에는 stop_price가 필요합니다")
                # STOP_MARKET 주문: stop_price에서 트리거되어 시장가 주문 실행
                params = {
                    'stopPrice': stop_price,
                    'type': 'STOP_LOSS' if account.exchange == 'binance' else 'StopMarket'
                }
                order = exchange.create_order(symbol, 'market', api_side, amount, None, params)
            else:
                raise ExchangeError(f"지원하지 않는 주문 타입: {order_type}")
            
            logger.info(f"주문 생성 성공 - 계좌: {account.id}, 심볼: {symbol}, "
                       f"타입: {order_type}, 사이드: {side}, 수량: {amount}, 마켓: {market_type}")
            
            return order
            
        except Exception as e:
            logger.error(f"주문 생성 실패 - 계좌: {account.id}, 오류: {str(e)}")
            raise ExchangeError(f"주문 생성 실패: {str(e)}")
    
    @retry_on_failure(max_retries=10)
    def cancel_order(self, account: Account, order_id: str, symbol: str, market_type: str = MarketType.SPOT) -> Dict[str, Any]:
        """주문 취소"""
        exchange = self.get_exchange(account)
        
        try:
            # 🆕 market_type에 따라 거래소 설정
            market_type_upper = market_type.upper() if market_type else 'SPOT'
            if market_type_upper in ['FUTURES', 'FUTURE']:
                # 선물 거래 설정
                if account.exchange == Exchange.BINANCE_LOWER:
                    exchange.options['defaultType'] = 'future'
                elif account.exchange == Exchange.BYBIT_LOWER:
                    exchange.options['defaultType'] = 'linear'  # USDT 선물
                elif account.exchange == 'okx':
                    exchange.options['defaultType'] = 'swap'
            else:
                # 현물 거래 설정 (기본값)
                if account.exchange == Exchange.BINANCE_LOWER:
                    exchange.options['defaultType'] = 'spot'
                elif account.exchange == Exchange.BYBIT_LOWER:
                    exchange.options['defaultType'] = 'spot'
                elif account.exchange == 'okx':
                    exchange.options['defaultType'] = 'spot'
            
            result = exchange.cancel_order(order_id, symbol)
            logger.info(f"주문 취소 성공 - 계좌: {account.id}, 주문 ID: {order_id}, 마켓: {market_type}")
            return result
        except Exception as e:
            logger.error(f"주문 취소 실패 - 계좌: {account.id}, 주문 ID: {order_id}, 마켓: {market_type}, 오류: {str(e)}")
            raise ExchangeError(f"주문 취소 실패: {str(e)}")
    
    @retry_on_failure(max_retries=10)
    def cancel_all_orders(self, account: Account, symbol: str = None, market_type: str = MarketType.SPOT) -> List[Dict[str, Any]]:
        """모든 주문 취소"""
        exchange = self.get_exchange(account)
        
        try:
            # 🆕 market_type에 따라 거래소 설정
            market_type_upper = market_type.upper() if market_type else 'SPOT'
            if market_type_upper in ['FUTURES', 'FUTURE']:
                # 선물 거래 설정
                if account.exchange == Exchange.BINANCE_LOWER:
                    exchange.options['defaultType'] = 'future'
                elif account.exchange == Exchange.BYBIT_LOWER:
                    exchange.options['defaultType'] = 'linear'  # USDT 선물
                elif account.exchange == 'okx':
                    exchange.options['defaultType'] = 'swap'
            else:
                # 현물 거래 설정 (기본값)
                if account.exchange == Exchange.BINANCE_LOWER:
                    exchange.options['defaultType'] = 'spot'
                elif account.exchange == Exchange.BYBIT_LOWER:
                    exchange.options['defaultType'] = 'spot'
                elif account.exchange == 'okx':
                    exchange.options['defaultType'] = 'spot'
            
            if symbol:
                # 특정 심볼의 주문만 취소
                results = exchange.cancel_all_orders(symbol)
            else:
                # 모든 주문 취소
                results = exchange.cancel_all_orders()
            
            logger.info(f"주문 취소 성공 - 계좌: {account.id}, 심볼: {symbol or 'ALL'}, 마켓: {market_type}, 취소된 주문 수: {len(results) if results else 0}")
            return results if results else []
            
        except Exception as e:
            logger.error(f"주문 취소 실패 - 계좌: {account.id}, 심볼: {symbol or 'ALL'}, 마켓: {market_type}, 오류: {str(e)}")
            raise ExchangeError(f"주문 취소 실패: {str(e)}")
    
    @retry_on_failure(max_retries=10)
    def get_order_status(self, account: Account, order_id: str, symbol: str, market_type: str = MarketType.SPOT) -> Dict[str, Any]:
        """주문 상태 조회"""
        exchange = self.get_exchange(account)
        
        try:
            # 🆕 market_type에 따라 거래소 설정
            market_type_upper = market_type.upper() if market_type else 'SPOT'
            if market_type_upper in ['FUTURES', 'FUTURE']:
                # 선물 거래 설정
                if account.exchange == Exchange.BINANCE_LOWER:
                    exchange.options['defaultType'] = 'future'
                elif account.exchange == Exchange.BYBIT_LOWER:
                    exchange.options['defaultType'] = 'linear'  # USDT 선물
                elif account.exchange == 'okx':
                    exchange.options['defaultType'] = 'swap'
            else:
                # 현물 거래 설정 (기본값)
                if account.exchange == Exchange.BINANCE_LOWER:
                    exchange.options['defaultType'] = 'spot'
                elif account.exchange == Exchange.BYBIT_LOWER:
                    exchange.options['defaultType'] = 'spot'
                elif account.exchange == 'okx':
                    exchange.options['defaultType'] = 'spot'
            
            order = exchange.fetch_order(order_id, symbol)
            return order
        except Exception as e:
            logger.error(f"주문 상태 조회 실패 - 계좌: {account.id}, 주문 ID: {order_id}, 마켓: {market_type}, 오류: {str(e)}")
            raise ExchangeError(f"주문 상태 조회 실패: {str(e)}")
    
    @retry_on_failure(max_retries=10)
    def get_order_fills(self, account: Account, order_id: str, symbol: str) -> List[Dict[str, Any]]:
        """주문 체결 내역 조회"""
        exchange = self.get_exchange(account)
        
        try:
            # 주문 정보 조회
            order = exchange.fetch_order(order_id, symbol)
            
            # 체결 내역이 있는 경우 반환
            fills = []
            if order.get('status') == 'closed' and order.get('filled', 0) > 0:
                # 일부 거래소는 trades 정보를 제공
                if 'trades' in order and order['trades']:
                    fills = order['trades']
                else:
                    # trades 정보가 없으면 주문 정보로 체결 내역 생성
                    fills = [{
                        'id': order.get('id'),
                        'order': order.get('id'),
                        'amount': order.get('filled', 0),
                        'price': order.get('average', order.get('price', 0)),
                        'cost': order.get('cost', 0),
                        'fee': order.get('fee', {}),
                        'timestamp': order.get('timestamp'),
                        'datetime': order.get('datetime'),
                        'symbol': symbol,
                        'side': order.get('side'),
                        'type': order.get('type')
                    }]
            
            return fills
            
        except Exception as e:
            logger.error(f"주문 체결 내역 조회 실패 - 계좌: {account.id}, 주문 ID: {order_id}, 오류: {str(e)}")
            raise ExchangeError(f"주문 체결 내역 조회 실패: {str(e)}")
    
    @retry_on_failure(max_retries=10)
    def wait_for_order_fill(self, account: Account, order_id: str, symbol: str, timeout: int = 30) -> Dict[str, Any]:
        """주문 체결 대기 (시장가 주문용)"""
        exchange = self.get_exchange(account)
        
        import time
        start_time = time.time()
        
        try:
            while time.time() - start_time < timeout:
                order = exchange.fetch_order(order_id, symbol)
                
                if order.get('status') in ['closed', 'canceled', 'cancelled']:
                    return order
                
                time.sleep(0.5)  # 0.5초 대기
            
            # 타임아웃 시 마지막 상태 반환
            return exchange.fetch_order(order_id, symbol)
            
        except Exception as e:
            logger.error(f"주문 체결 대기 실패 - 계좌: {account.id}, 주문 ID: {order_id}, 오류: {str(e)}")
            raise ExchangeError(f"주문 체결 대기 실패: {str(e)}")
    
    @retry_on_failure(max_retries=10)
    def get_ticker(self, account: Account, symbol: str) -> Dict[str, Any]:
        """현재가 정보 조회 (캐싱 적용)"""
        try:
            # 🆕 캐시된 데이터 먼저 확인
            cached_ticker = self._get_cached_ticker(account, symbol)
            if cached_ticker:
                return cached_ticker
            
            # 캐시 미스 시 API 호출
            logger.debug(f"Ticker API 호출 - 계좌: {account.id}, 심볼: {symbol}")
            
            exchange = self.get_exchange(account)
            
            # 🆕 기존 방식대로 직접 fetch_ticker 호출 (심볼 변환 불필요)
            ticker = exchange.fetch_ticker(symbol)
            
            # 🆕 결과 캐싱
            self._cache_ticker(account, symbol, ticker)
            
            logger.debug(f"Ticker 조회 완료 - 계좌: {account.id}, 심볼: {symbol}, 가격: {ticker.get('last')}")
            
            return ticker
            
        except Exception as e:
            logger.error(f"Ticker 조회 실패 - 계좌: {account.id}, 심볼: {symbol}, 오류: {str(e)}")
            raise ExchangeError(f"Ticker 조회 실패: {str(e)}")
    
    @retry_on_failure(max_retries=10)
    def fetch_open_orders(self, account: Account, symbol: str = None, market_type: str = MarketType.SPOT) -> List[Dict[str, Any]]:
        """열린 주문 리스트 조회 (한 번에 모든 주문 가져오기)"""
        exchange = self.get_exchange(account)
        
        try:
            # 🆕 market_type에 따라 거래소 설정
            market_type_upper = market_type.upper() if market_type else 'SPOT'
            if market_type_upper in ['FUTURES', 'FUTURE']:
                # 선물 거래 설정
                if account.exchange == Exchange.BINANCE_LOWER:
                    exchange.options['defaultType'] = 'future'
                elif account.exchange == Exchange.BYBIT_LOWER:
                    exchange.options['defaultType'] = 'linear'  # USDT 선물
                elif account.exchange == 'okx':
                    exchange.options['defaultType'] = 'swap'
            else:
                # 현물 거래 설정 (기본값)
                if account.exchange == Exchange.BINANCE_LOWER:
                    exchange.options['defaultType'] = 'spot'
                elif account.exchange == Exchange.BYBIT_LOWER:
                    exchange.options['defaultType'] = 'spot'
                elif account.exchange == 'okx':
                    exchange.options['defaultType'] = 'spot'
            
            # 🆕 바이낸스의 경우 특별 처리
            if account.exchange == 'binance' and symbol is None:
                # 바이낸스는 심볼 없는 조회 시 rate limit이 매우 엄격하므로
                # 경고를 무시하고 조회하되, 실패 시 빈 리스트 반환
                try:
                    open_orders = exchange.fetch_open_orders(symbol)
                    logger.debug(f"미체결 주문 조회 완료 - 계좌: {account.id}, 마켓: {market_type}, 주문 수: {len(open_orders)}")
                    return open_orders
                except Exception as binance_error:
                    error_msg = str(binance_error).lower()
                    if 'rate' in error_msg or 'limit' in error_msg or 'warning' in error_msg:
                        logger.warning(f"바이낸스 rate limit으로 인한 조회 실패, 빈 리스트 반환 - 계좌 ID: {account.id}, 마켓: {market_type}")
                        return []  # rate limit 오류 시 빈 리스트 반환
                    else:
                        raise  # 다른 오류는 재발생
            else:
                # 다른 거래소는 기존 방식 사용
                open_orders = exchange.fetch_open_orders(symbol)
                logger.debug(f"미체결 주문 조회 완료 - 계좌: {account.id}, 마켓: {market_type}, 주문 수: {len(open_orders)}")
                return open_orders
                
        except Exception as e:
            logger.error(f"열린 주문 조회 실패 - 계좌 ID: {account.id}, 심볼: {symbol}, 마켓: {market_type}, 오류: {str(e)}")
            raise ExchangeError(f"열린 주문 조회 실패: {str(e)}")
    
    @retry_on_failure(max_retries=10)
    def fetch_open_orders_by_symbols(self, account: Account, symbols: List[str], market_type: str = MarketType.SPOT) -> List[Dict[str, Any]]:
        """심볼별로 열린 주문 조회 (바이낸스 rate limit 회피용)"""
        exchange = self.get_exchange(account)
        all_orders = []
        
        try:
            # 🆕 market_type에 따라 거래소 설정
            market_type_upper = market_type.upper() if market_type else 'SPOT'
            if market_type_upper in ['FUTURES', 'FUTURE']:
                # 선물 거래 설정
                if account.exchange == Exchange.BINANCE_LOWER:
                    exchange.options['defaultType'] = 'future'
                elif account.exchange == Exchange.BYBIT_LOWER:
                    exchange.options['defaultType'] = 'linear'  # USDT 선물
                elif account.exchange == 'okx':
                    exchange.options['defaultType'] = 'swap'
            else:
                # 현물 거래 설정 (기본값)
                if account.exchange == Exchange.BINANCE_LOWER:
                    exchange.options['defaultType'] = 'spot'
                elif account.exchange == Exchange.BYBIT_LOWER:
                    exchange.options['defaultType'] = 'spot'
                elif account.exchange == 'okx':
                    exchange.options['defaultType'] = 'spot'
            
            for symbol in symbols:
                try:
                    symbol_orders = exchange.fetch_open_orders(symbol)
                    all_orders.extend(symbol_orders)
                    logger.debug(f"심볼 {symbol}: {len(symbol_orders)}개 열린 주문 조회 (마켓: {market_type})")
                except Exception as symbol_error:
                    logger.warning(f"심볼 {symbol} 열린 주문 조회 실패 (마켓: {market_type}): {symbol_error}")
                    continue
            
            logger.info(f"계좌 {account.name}: 총 {len(all_orders)}개 열린 주문 조회 완료 (심볼별 조회, 마켓: {market_type})")
            return all_orders
            
        except Exception as e:
            logger.error(f"심볼별 열린 주문 조회 실패 (마켓: {market_type}): {e}")
            return []
    
    def clear_cache(self, account_id: int = None):
        """거래소 인스턴스 캐시 정리"""
        if account_id:
            # 특정 계좌의 캐시만 정리
            keys_to_remove = [key for key in self._exchanges.keys() if key.endswith(f"_{account_id}")]
            for key in keys_to_remove:
                del self._exchanges[key]
        else:
            # 모든 캐시 정리
            self._exchanges.clear()
        
        logger.info(f"거래소 캐시 정리 완료 - 계좌 ID: {account_id or 'ALL'}")
    
    def clear_market_cache(self, exchange_name: str = None, symbol: str = None):
        """🆕 Market 정보 캐시 정리"""
        if exchange_name and symbol:
            # 특정 거래소의 특정 심볼 캐시만 정리
            cache_key = f"{exchange_name}_{symbol}"
            if cache_key in self._market_cache:
                del self._market_cache[cache_key]
                logger.info(f"Market 캐시 정리: {cache_key}")
        elif exchange_name:
            # 특정 거래소의 모든 심볼 캐시 정리
            keys_to_remove = [key for key in self._market_cache.keys() if key.startswith(f"{exchange_name}_")]
            for key in keys_to_remove:
                del self._market_cache[key]
            logger.info(f"Market 캐시 정리: {exchange_name} 전체")
        else:
            # 모든 market 캐시 정리
            self._market_cache.clear()
            logger.info("Market 캐시 전체 정리 완료")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """🆕 캐시 통계 정보 반환"""
        current_time = time.time()
        
        # 만료된 캐시 개수 계산
        expired_market_cache = 0
        for cache_key, (market, timestamp) in self._market_cache.items():
            if current_time - timestamp >= self._cache_duration:
                expired_market_cache += 1
        
        return {
            'exchange_cache_count': len(self._exchanges),
            'market_cache_count': len(self._market_cache),
            'expired_market_cache': expired_market_cache,
            'cache_duration_hours': self._cache_duration / 3600
        }

    @retry_on_failure(max_retries=10)
    def get_market_info(self, account: Account, symbol: str) -> Dict[str, Any]:
        """심볼의 market 정보 조회 및 캐싱"""
        cache_key = f"{account.exchange}_{symbol}"
        
        # 캐시 확인
        if cache_key in self._market_cache:
            cached_market, timestamp = self._market_cache[cache_key]
            if time.time() - timestamp < self._cache_duration:
                logger.debug(f"Market 정보 캐시 사용: {symbol}")
                return cached_market
        
        try:
            exchange = self.get_exchange(account)
            
            # 🆕 exchange.markets가 None이거나 비어있는지 확인
            if not exchange.markets or symbol not in exchange.markets:
                logger.info(f"Market 정보 로딩 - 계좌: {account.id}, 심볼: {symbol}, defaultType: {exchange.options.get('defaultType', 'unknown')}")
                
                # 🆕 선물 마켓인 경우 추가 처리
                if exchange.options.get('defaultType') in ['future', 'linear', 'swap']:
                    logger.info(f"선물 마켓 강제 로딩 - 거래소: {account.exchange}")
                    try:
                        exchange.load_markets(True)  # reload=True로 강제 새로고침
                    except Exception as reload_error:
                        logger.warning(f"선물 마켓 강제 로딩 실패, 일반 로딩 시도: {reload_error}")
                        exchange.load_markets()
                else:
                    exchange.load_markets()  # markets 정보가 없거나 심볼이 없으면 로드
            
            # 🆕 로드 후에도 심볼이 없는 경우 심볼 형식 변환 시도
            if symbol not in exchange.markets:
                logger.info(f"심볼 변환 시도: {symbol}")
                converted_symbol = self._convert_symbol_format(symbol, exchange)
                
                if converted_symbol != symbol and converted_symbol in exchange.markets:
                    symbol = converted_symbol
                else:
                    # 변환 실패 시 상세 정보 제공
                    quote_currencies = self._get_common_quote_currencies(exchange)
                    logger.warning(f"심볼 변환 실패. 지원하는 quote currencies: {quote_currencies}")
                    
                    # 유사한 심볼 찾기 시도
                    if '/' not in symbol and len(symbol) >= 6:
                        base, quote = self._extract_base_quote_from_symbol(symbol, quote_currencies)
                        if base:
                            similar_symbols = [s for s in exchange.markets.keys() if s.startswith(base) and '/' in s][:5]
                            if similar_symbols:
                                logger.info(f"유사한 심볼들: {similar_symbols}")
            
            # 🆕 여전히 심볼을 찾을 수 없는 경우 에러 처리
            if symbol not in exchange.markets:
                available_symbols = list(exchange.markets.keys())[:10]  # 처음 10개만 로깅
                market_type = exchange.options.get('defaultType', 'unknown')
                total_symbols = len(exchange.markets)
                
                logger.error(f"심볼 {symbol}을 찾을 수 없습니다 (마켓타입: {market_type}, 총 {total_symbols}개 심볼)")
                logger.error(f"사용 가능한 심볼 예시: {available_symbols}")
                
                # 거래소별 추가 정보 제공
                if account.exchange == Exchange.BINANCE_LOWER:
                    if market_type_upper in ['FUTURES', 'FUTURE']:
                        logger.error(f"Binance 선물에서는 'SOL/USDT' 형식을 사용합니다.")
                    else:
                        logger.error(f"Binance 현물에서는 'SOL/USDT' 형식을 사용합니다.")
                
                raise ExchangeError(f"심볼 {symbol}을 찾을 수 없습니다 (마켓타입: {market_type})")
            
            market = exchange.market(symbol)
            
            # 캐시에 저장 (변환된 심볼로)
            cache_key = f"{account.exchange}_{symbol}"
            self._market_cache[cache_key] = (market, time.time())
            logger.info(f"Market 정보 조회 및 캐싱: {symbol} - precision: {market.get('precision', {})}")
            
            return market
            
        except Exception as e:
            logger.error(f"Market 정보 조회 실패 - 계좌: {account.id}, 심볼: {symbol}, 오류: {str(e)}")
            raise ExchangeError(f"Market 정보 조회 실패: {str(e)}")
    
    def _get_common_quote_currencies(self, exchange) -> List[str]:
        """거래소에서 지원하는 일반적인 quote currency 목록 반환 (우선순위 순)"""
        # 거래소별 일반적인 quote currency (우선순위 순)
        common_quotes = {
            'binance': ['USDT', 'BUSD', 'BTC', 'ETH', 'BNB', 'USDC', 'TUSD', 'FDUSD'],
            'bybit': ['USDT', 'BTC', 'ETH', 'USDC'],
            'okx': ['USDT', 'BTC', 'ETH', 'USDC', 'OKB']
        }
        
        exchange_name = exchange.id.lower()
        default_quotes = ['USDT', 'BTC', 'ETH', 'USDC']  # 기본값
        
        return common_quotes.get(exchange_name, default_quotes)
    
    def _extract_base_quote_from_symbol(self, symbol: str, quote_currencies: List[str]) -> tuple:
        """심볼에서 base와 quote를 추출 (quote currency 우선순위 기반)"""
        symbol_upper = symbol.upper()
        
        # quote currency를 우선순위 순으로 확인
        for quote in quote_currencies:
            if symbol_upper.endswith(quote) and len(symbol_upper) > len(quote):
                base = symbol_upper[:-len(quote)]
                return base, quote
        
        return None, None
    
    def _convert_symbol_format(self, symbol: str, exchange, target_format: str = 'auto') -> str:
        """효율적인 심볼 형식 변환"""
        original_symbol = symbol
        
        # 거래소의 일반적인 quote currency 목록 가져오기
        quote_currencies = self._get_common_quote_currencies(exchange)
        
        # 현재 심볼이 markets에 있으면 변환 불필요
        if symbol in exchange.markets:
            return symbol
        
        # 1. 슬래시 없는 형식 -> 슬래시 있는 형식 (SOLUSDT -> SOL/USDT)
        if '/' not in symbol:
            base, quote = self._extract_base_quote_from_symbol(symbol, quote_currencies)
            if base and quote:
                slash_format = f"{base}/{quote}"
                if slash_format in exchange.markets:
                    logger.info(f"심볼 형식 변환 성공: {original_symbol} -> {slash_format}")
                    return slash_format
        
        # 2. 슬래시 있는 형식 -> 슬래시 없는 형식 (SOL/USDT -> SOLUSDT)
        elif '/' in symbol:
            no_slash_format = symbol.replace('/', '')
            if no_slash_format in exchange.markets:
                logger.info(f"심볼 형식 변환 성공: {original_symbol} -> {no_slash_format}")
                return no_slash_format
        
        # 3. 추가 변환 시도 (다른 quote currency들로)
        if '/' not in symbol:
            base, detected_quote = self._extract_base_quote_from_symbol(symbol, quote_currencies)
            if base:
                # 검출된 quote가 잘못된 경우, 다른 quote currency들 시도
                for alternative_quote in quote_currencies:
                    if alternative_quote != detected_quote:
                        alternative_symbol = f"{base}/{alternative_quote}"
                        if alternative_symbol in exchange.markets:
                            logger.info(f"심볼 형식 변환 성공 (대체 quote): {original_symbol} -> {alternative_symbol}")
                            return alternative_symbol
        
        # 변환 실패
        logger.warning(f"심볼 형식 변환 실패: {original_symbol}")
        return symbol
    
    def preprocess_order_params(self, account: Account, symbol: str, amount: float, price: float = None, market_type: str = MarketType.SPOT) -> tuple:
        """주문 파라미터 전처리 (CCXT 내부 로직과 동일하게 조정) - Decimal 기반 정밀 연산"""
        try:
            # 🆕 입력값을 즉시 Decimal로 변환하여 정밀도 보장
            from app.services.utils import to_decimal, decimal_to_float
            
            amount_decimal = to_decimal(amount)
            price_decimal = to_decimal(price) if price is not None else None
            
            # 🆕 전처리 시작 로깅
            logger.info(f"주문 파라미터 전처리 시작 - 계좌: {account.id}({account.name}), "
                       f"심볼: {symbol}, 마켓타입: {market_type}, 수량: {amount_decimal}")
            
            exchange = self.get_exchange(account)
            
            # 🆕 market_type에 따라 거래소 설정 (get_market_info 호출 전에 설정)
            market_type_lower = market_type.lower()
            if market_type_lower in ['future', 'futures']:
                # 선물 거래 설정
                logger.info(f"선물 거래 모드 설정 - 거래소: {account.exchange}")
                if account.exchange == Exchange.BINANCE_LOWER:
                    exchange.options['defaultType'] = 'future'
                elif account.exchange == Exchange.BYBIT_LOWER:
                    exchange.options['defaultType'] = 'linear'  # USDT 선물
                elif account.exchange == 'okx':
                    exchange.options['defaultType'] = 'swap'
            else:
                # 현물 거래 설정 (기본값)
                logger.info(f"현물 거래 모드 설정 - 거래소: {account.exchange}")
                if account.exchange == Exchange.BINANCE_LOWER:
                    exchange.options['defaultType'] = 'spot'
                elif account.exchange == Exchange.BYBIT_LOWER:
                    exchange.options['defaultType'] = 'spot'
                elif account.exchange == 'okx':
                    exchange.options['defaultType'] = 'spot'
            
            # 🆕 거래소 설정 후 로깅
            logger.info(f"거래소 설정 완료 - 현재 defaultType: {exchange.options.get('defaultType', 'unknown')}")
            
            market = self.get_market_info(account, symbol)
            
            # 원본 값 저장 (로깅용)
            original_amount = amount_decimal
            original_price = price_decimal
            
            # 수량 전처리 (내림 처리) - Decimal 기반
            adjusted_amount = self._adjust_amount(market, amount_decimal)
            
            # 가격 전처리 (지정가 주문인 경우, 내림 처리) - Decimal 기반
            adjusted_price = None
            if price_decimal is not None:
                adjusted_price = self._adjust_price(market, price_decimal)
            
            # 🆕 최소 주문 수량 검증 - Decimal 기반 비교
            limits = market.get('limits', {})
            min_amount = to_decimal(limits.get('amount', {}).get('min', 0))
            if min_amount > 0 and adjusted_amount < min_amount:
                raise ExchangeError(f"주문 수량이 최소값보다 작습니다: {adjusted_amount} < {min_amount}")
            
            # 🆕 최소 주문 금액 검증 - Decimal 기반 연산
            if adjusted_price:
                cost = adjusted_amount * adjusted_price
                min_cost = to_decimal(limits.get('cost', {}).get('min', 0))
                if min_cost > 0 and cost < min_cost:
                    raise ExchangeError(f"주문 금액이 최소값보다 작습니다: {cost} < {min_cost}")
            
            # 조정 여부 로깅 - Decimal 기반 비교
            amount_adjusted = abs(adjusted_amount - original_amount) > Decimal('0.00000001')
            price_adjusted = adjusted_price and original_price and abs(adjusted_price - original_price) > Decimal('0.00000001')
            
            if amount_adjusted or price_adjusted:
                logger.info(f"주문 파라미터 전처리 - 심볼: {symbol}, 마켓: {market_type}")
                if amount_adjusted:
                    logger.info(f"  수량 조정: {original_amount} → {adjusted_amount}")
                if price_adjusted:
                    logger.info(f"  가격 조정: {original_price} → {adjusted_price}")
            
            # 🆕 반환값을 float로 변환 (CCXT 호환성)
            return (
                decimal_to_float(adjusted_amount),
                decimal_to_float(adjusted_price) if adjusted_price else None
            )
            
        except Exception as e:
            logger.warning(f"주문 파라미터 전처리 실패, 원본 값 사용 - 심볼: {symbol}, 마켓: {market_type}, 오류: {str(e)}")
            raise  # 🆕 예외를 다시 발생시켜서 상위에서 처리하도록 함
    
    def _adjust_amount(self, market: Dict[str, Any], amount: Decimal) -> Decimal:
        """수량 조정 (precision과 limits 적용, 내림 처리) - Decimal 기반 정밀 연산"""
        from app.services.utils import to_decimal
        
        # precision 적용 (내림 처리) - Decimal 기반
        precision = market.get('precision', {})
        amount_precision = precision.get('amount')
        
        if amount_precision is not None:
            if isinstance(amount_precision, int):
                # 소수점 자리수로 지정된 경우 - Decimal.quantize 사용하여 내림 처리
                if amount_precision >= 0:
                    # 양수: 소수점 자리수
                    quantize_exp = Decimal('0.1') ** amount_precision
                    adjusted_amount = amount.quantize(quantize_exp, rounding=ROUND_DOWN)
                else:
                    # 음수: 정수 자리수 (예: -1이면 10의 자리에서 반올림)
                    quantize_exp = Decimal('10') ** (-amount_precision)
                    adjusted_amount = amount.quantize(quantize_exp, rounding=ROUND_DOWN)
            else:
                # step size로 지정된 경우 (일부 거래소) - Decimal 기반 내림 처리
                step_size = to_decimal(amount_precision)
                if step_size > 0:
                    # amount를 step_size로 나눈 몫을 구하고 다시 곱함 (내림 효과)
                    steps = (amount / step_size).quantize(Decimal('1'), rounding=ROUND_DOWN)
                    adjusted_amount = steps * step_size
                else:
                    adjusted_amount = amount
        else:
            adjusted_amount = amount
        
        # limits 적용 - Decimal 기반 비교
        limits = market.get('limits', {}).get('amount', {})
        min_amount = to_decimal(limits.get('min', 0))
        max_amount = to_decimal(limits.get('max', float('inf')))
        
        if adjusted_amount < min_amount:
            adjusted_amount = min_amount
        elif adjusted_amount > max_amount:
            adjusted_amount = max_amount
        
        return adjusted_amount
    
    def _adjust_price(self, market: Dict[str, Any], price: Decimal) -> Decimal:
        """가격 조정 (precision과 limits 적용, 내림 처리) - Decimal 기반 정밀 연산"""
        from app.services.utils import to_decimal
        
        # precision 적용 (내림 처리) - Decimal 기반
        precision = market.get('precision', {})
        price_precision = precision.get('price')
        
        if price_precision is not None:
            if isinstance(price_precision, int):
                # 소수점 자리수로 지정된 경우 - Decimal.quantize 사용하여 내림 처리
                if price_precision >= 0:
                    # 양수: 소수점 자리수
                    quantize_exp = Decimal('0.1') ** price_precision
                    adjusted_price = price.quantize(quantize_exp, rounding=ROUND_DOWN)
                else:
                    # 음수: 정수 자리수 (예: -1이면 10의 자리에서 반올림)
                    quantize_exp = Decimal('10') ** (-price_precision)
                    adjusted_price = price.quantize(quantize_exp, rounding=ROUND_DOWN)
            else:
                # step size로 지정된 경우 (일부 거래소) - Decimal 기반 내림 처리
                step_size = to_decimal(price_precision)
                if step_size > 0:
                    # price를 step_size로 나눈 몫을 구하고 다시 곱함 (내림 효과)
                    steps = (price / step_size).quantize(Decimal('1'), rounding=ROUND_DOWN)
                    adjusted_price = steps * step_size
                else:
                    adjusted_price = price
        else:
            adjusted_price = price
        
        # limits 적용 - Decimal 기반 비교
        limits = market.get('limits', {}).get('price', {})
        min_price = to_decimal(limits.get('min', 0))
        max_price = to_decimal(limits.get('max', float('inf')))
        
        if adjusted_price < min_price:
            adjusted_price = min_price
        elif adjusted_price > max_price:
            adjusted_price = max_price
        
        return adjusted_price

    def _get_cached_ticker(self, account: Account, symbol: str) -> Optional[Dict[str, Any]]:
        """🆕 캐시된 ticker 정보 조회"""
        with self.ticker_cache_lock:
            cache_key = f"{account.exchange.lower()}_{symbol}"
            cached_data = self.ticker_cache.get(cache_key)
            
            if cached_data:
                # TTL 체크
                if time.time() - cached_data['timestamp'] < self.ticker_cache_ttl:
                    logger.debug(f"Ticker 캐시 히트 - 계좌: {account.id}, 심볼: {symbol}, "
                               f"캐시 생성: {cached_data['timestamp']:.1f}초 전")
                    return cached_data['data']
                else:
                    # TTL 만료된 캐시 제거
                    del self.ticker_cache[cache_key]
                    logger.debug(f"Ticker 캐시 만료 - 계좌: {account.id}, 심볼: {symbol}")
            
            return None
    
    def _cache_ticker(self, account: Account, symbol: str, ticker_data: Dict[str, Any]):
        """🆕 ticker 정보 캐싱"""
        with self.ticker_cache_lock:
            cache_key = f"{account.exchange.lower()}_{symbol}"
            self.ticker_cache[cache_key] = {
                'data': ticker_data,
                'timestamp': time.time(),
                'account_id': account.id
            }
            logger.debug(f"Ticker 정보 캐싱 - 계좌: {account.id}, 심볼: {symbol}")

    @retry_on_failure(max_retries=10)
    def get_precision_info_optimized(self, account: Account, symbol: str, market_type: str = None) -> Dict[str, Any]:
        """🆕 Precision 정보 최적화 조회 (MarketType 상수 기반)"""
        from app.constants import MarketType
        
        exchange_name = account.exchange.lower()
        
        # market_type 정규화 (필수)
        normalized_market_type = MarketType.normalize(market_type)
        
        # 1단계: Precision 캐시에서 먼저 조회 (MarketType 상수 기반)
        precision_info = self.precision_cache.get_precision_info(exchange_name, symbol, normalized_market_type)
        if precision_info:
            logger.debug(f"⚡ Precision 최적화 조회 성공 (캐시, {normalized_market_type}) - {symbol}")
            return precision_info
        
        # 2단계: UniversalExchange를 사용하여 정확한 precision 조회
        try:
            # API 인증 정보 구성
            api_credentials = {
                'apiKey': account.public_api,
                'secret': account.secret_api,
            }
            
            # OKX passphrase 처리 (필요시)
            if account.exchange == 'okx' and hasattr(account, 'passphrase') and account.passphrase:
                api_credentials['password'] = account.passphrase
            
            # UniversalExchange를 통한 정확한 precision 조회
            try:
                universal = self.universal_manager.get_exchange(account.exchange, api_credentials)
                precision_result = universal.get_precision(symbol, normalized_market_type)
                
                if precision_result:
                    # UniversalExchange 결과를 기존 형식으로 변환
                    precision_info = {
                        'amount': precision_result['amount_precision'],
                        'price': precision_result['price_precision'],
                        'limits': precision_result['limits'],
                        'active': precision_result['market_info']['active'],
                        'type': precision_result['market_type'],
                        'symbol': precision_result['symbol'],  # 실제 사용된 심볼
                        'original_symbol': precision_result['original_symbol'],
                        'exchange_info': {
                            'api_class': precision_result['api_class'],
                            'has_separate_api': precision_result['has_separate_api']
                        }
                    }
                    
                    # 🎯 BTCUSDT FUTURES precision 특별 로깅 (문제 해결 확인)
                    if symbol.upper() == 'BTCUSDT' and normalized_market_type == MarketType.FUTURES:
                        logger.info(f"🎉 BTCUSDT FUTURES precision UniversalExchange 조회 성공!")
                        logger.info(f"   Original Symbol: {symbol}")
                        logger.info(f"   Used Symbol: {precision_result['symbol']}")
                        logger.info(f"   Amount Precision: {precision_result['amount_precision']} ← 정확한 FUTURES precision!")
                        logger.info(f"   API Class: {precision_result['api_class']}")
                        logger.info(f"   Market Type: {precision_result['market_type']}")
                        logger.info(f"   0.002 문제 해결: {precision_result['amount_precision'] == 3}")
                    
                    # 캐시에 저장
                    self.precision_cache.set_precision_info(exchange_name, symbol, precision_info, normalized_market_type)
                    
                    logger.info(f"✅ UniversalExchange precision 조회 성공 - {symbol} ({normalized_market_type}): "
                              f"amount={precision_info['amount']}, API={precision_result['api_class']}")
                    
                    return precision_info
                
                else:
                    # UniversalExchange에서 심볼을 찾지 못한 경우
                    logger.warning(f"⚠️ UniversalExchange에서 심볼 찾지 못함: {symbol} ({normalized_market_type})")
                    
            except ValueError as e:
                # 지원하지 않는 거래소인 경우
                logger.warning(f"⚠️ UniversalExchange 미지원 거래소: {account.exchange} - {e}")
                
            except Exception as e:
                # UniversalExchange 오류 발생 시
                logger.error(f"❌ UniversalExchange 오류: {account.exchange} - {e}")
            
            # 3단계: fallback - 기존 방식으로 조회
            logger.info(f"🔄 기존 방식으로 fallback precision 조회: {symbol} ({normalized_market_type})")
            
            exchange = self.get_exchange(account)  # market_type 없이 호출 (기존 방식)
            
            # MarketType 상수 기반 거래소 설정
            exchange_api_type = MarketType.to_exchange_type(normalized_market_type, account.exchange)
            previous_type = exchange.options.get('defaultType')
            exchange.options['defaultType'] = exchange_api_type
            
            # defaultType 변경 시 markets 리로드
            if previous_type != exchange_api_type:
                logger.info(f"🔄 {exchange_name} fallback markets 리로딩 - {previous_type} → {exchange_api_type}")
                exchange.load_markets(reload=True)
            elif not exchange.markets:
                exchange.load_markets()
            
            # 심볼 찾기
            if symbol in exchange.markets:
                market = exchange.markets[symbol]
            else:
                # 심볼 변환 시도
                converted_symbol = self._convert_symbol_format(symbol, exchange)
                if converted_symbol != symbol and converted_symbol in exchange.markets:
                    symbol = converted_symbol
                    market = exchange.markets[symbol]
                else:
                    raise ExchangeError(f"심볼 {symbol}을 찾을 수 없습니다")
            
            # precision 정보 추출
            precision_info = {
                'amount': market.get('precision', {}).get('amount'),
                'price': market.get('precision', {}).get('price'),
                'limits': market.get('limits', {}),
                'active': market.get('active', True),
                'type': market.get('type', 'spot'),
                'symbol': symbol,
                'fallback_method': 'legacy'  # fallback 방식 표시
            }
            
            # 캐시에 저장
            self.precision_cache.set_precision_info(exchange_name, symbol, precision_info, normalized_market_type)
            
            logger.info(f"💾 Fallback precision 조회 완료 - {symbol} ({normalized_market_type}): amount={precision_info['amount']}")
            return precision_info
            
        except Exception as e:
            logger.error(f"❌ Precision 정보 조회 완전 실패 - {symbol}: {str(e)}")
            raise ExchangeError(f"Precision 정보 조회 실패: {str(e)}")
    
    def preprocess_order_params_optimized(self, account: Account, symbol: str, amount: float, price: float = None, market_type: str = None) -> tuple:
        """🆕 주문 파라미터 전처리 최적화 (MarketType 상수 기반) - 95% 성능 향상"""
        try:
            # 🆕 입력값을 즉시 Decimal로 변환하여 정밀도 보장
            from app.services.utils import to_decimal, decimal_to_float
            from app.constants import MinOrderAmount, MarketType
            
            # market_type 정규화 (필수)
            normalized_market_type = MarketType.normalize(market_type)
            
            amount_decimal = to_decimal(amount)
            price_decimal = to_decimal(price) if price is not None else None
            
            # 🆕 전처리 시작 로깅
            logger.debug(f"🚀 주문 파라미터 최적화 전처리 시작 - 계좌: {account.id}({account.name}), "
                       f"심볼: {symbol}, 마켓타입: {normalized_market_type}")
            
            # 🆕 UniversalExchange 사용 (market_type 지정)
            exchange = self.get_exchange(account, normalized_market_type)
            
            logger.debug(f"거래소 설정 완료 (전처리) - {account.exchange}: {normalized_market_type} (UniversalExchange 사용)")
            
            # 🆕 최적화된 precision 정보 조회 (MarketType 상수 기반)
            precision_info = self.get_precision_info_optimized(account, symbol, normalized_market_type)
            
            # 원본 값 저장 (로깅용)
            original_amount = amount_decimal
            original_price = price_decimal
            
            # 수량 전처리 (내림 처리) - Decimal 기반
            adjusted_amount = self._adjust_amount_optimized(precision_info, amount_decimal)
            
            # 가격 전처리 (지정가 주문인 경우, 내림 처리) - Decimal 기반
            adjusted_price = None
            if price_decimal is not None:
                adjusted_price = self._adjust_price_optimized(precision_info, price_decimal)
            
            # 🆕 최소 주문 수량/금액 자동 조정 로직
            limits = precision_info.get('limits', {})
            min_amount = to_decimal(limits.get('amount', {}).get('min', 0))
            min_cost = to_decimal(limits.get('cost', {}).get('min', 0))
            
            # 조정 정보 초기화
            adjustment_info = None
            
            # 현재 가격 결정 (지정가면 지정가, 시장가면 최근 시장가 필요)
            effective_price = adjusted_price if adjusted_price else price_decimal
            if not effective_price:
                # 시장가 주문인 경우 현재가 조회 필요 (ticker 정보 사용)
                ticker = self.get_ticker(account, symbol)
                if ticker and 'last' in ticker:
                    effective_price = to_decimal(ticker['last'])
                else:
                    effective_price = Decimal('1')  # fallback
            
            # 현재 주문 금액 계산
            current_cost = adjusted_amount * effective_price
            
            # 최소 요구사항 체크 및 자동 조정
            needs_adjustment = False
            required_amount = adjusted_amount
            adjustment_reason = ""
            
            # 1. 최소 수량 체크
            if min_amount > 0 and adjusted_amount < min_amount:
                required_amount_by_min = min_amount * Decimal(str(MinOrderAmount.ADJUSTMENT_MULTIPLIER))
                required_amount = max(required_amount, required_amount_by_min)
                needs_adjustment = True
                adjustment_reason = f"최소 수량({min_amount:.8f}) 미달"
            
            # 2. 최소 금액 체크
            if min_cost > 0 and current_cost < min_cost:
                required_cost = min_cost * Decimal(str(MinOrderAmount.ADJUSTMENT_MULTIPLIER))
                required_amount_by_cost = required_cost / effective_price
                if required_amount_by_cost > required_amount:
                    required_amount = required_amount_by_cost
                    adjustment_reason = f"최소 금액({min_cost:.2f} USDT) 미달"
                needs_adjustment = True
            
            # 3. 거래소별 하드코딩된 최소 금액 체크
            exchange_min_cost = Decimal(str(MinOrderAmount.get_min_amount(
                account.exchange.upper(), 
                normalized_market_type
            )))
            if current_cost < exchange_min_cost:
                required_cost = exchange_min_cost * Decimal(str(MinOrderAmount.ADJUSTMENT_MULTIPLIER))
                required_amount_by_exchange = required_cost / effective_price
                if required_amount_by_exchange > required_amount:
                    required_amount = required_amount_by_exchange
                    adjustment_reason = f"거래소 최소 금액({exchange_min_cost:.2f} USDT) 미달"
                needs_adjustment = True
            
            # 자동 조정 적용
            if needs_adjustment:
                # precision 적용하여 조정된 수량 계산
                final_adjusted_amount = self._adjust_amount_optimized(precision_info, required_amount)
                final_adjusted_cost = final_adjusted_amount * effective_price
                
                # 조정 정보 기록
                adjustment_info = {
                    'was_adjusted': True,
                    'original_amount': decimal_to_float(original_amount),
                    'original_cost': decimal_to_float(original_amount * effective_price),
                    'adjusted_amount': decimal_to_float(final_adjusted_amount),
                    'adjusted_cost': decimal_to_float(final_adjusted_cost),
                    'min_amount': decimal_to_float(min_amount) if min_amount else 0,
                    'min_cost': decimal_to_float(min_cost) if min_cost else 0,
                    'exchange_min_cost': decimal_to_float(exchange_min_cost),
                    'reason': f"{adjustment_reason}, 안전 마진 2배 적용",
                    'symbol': symbol,
                    'exchange': account.exchange.upper(),
                    'market_type': normalized_market_type
                }
                
                logger.info(f"📊 주문 수량 자동 조정 - 심볼: {symbol}")
                logger.info(f"  원래: {original_amount:.8f} ({original_amount * effective_price:.2f} USDT)")
                logger.info(f"  조정: {final_adjusted_amount:.8f} ({final_adjusted_cost:.2f} USDT)")
                logger.info(f"  사유: {adjustment_info['reason']}")
                
                adjusted_amount = final_adjusted_amount
            
            # 조정 여부 로깅 - Decimal 기반 비교
            amount_adjusted = abs(adjusted_amount - original_amount) > Decimal('0.00000001')
            price_adjusted = adjusted_price and original_price and abs(adjusted_price - original_price) > Decimal('0.00000001')
            
            if amount_adjusted or price_adjusted:
                logger.debug(f"📊 주문 파라미터 최적화 전처리 완료 - 심볼: {symbol}")
                if amount_adjusted:
                    logger.debug(f"  수량 조정: {original_amount} → {adjusted_amount}")
                if price_adjusted:
                    logger.debug(f"  가격 조정: {original_price} → {adjusted_price}")
            
            # 🆕 반환값을 float로 변환 (CCXT 호환성), 조정 정보 포함
            return (
                decimal_to_float(adjusted_amount),
                decimal_to_float(adjusted_price) if adjusted_price else None,
                adjustment_info  # 조정 정보 추가
            )
            
        except Exception as e:
            logger.warning(f"주문 파라미터 최적화 전처리 실패, 기존 방식으로 fallback - 심볼: {symbol}, 오류: {str(e)}")
            # 🆕 실패 시 기존 방식으로 fallback
            return self.preprocess_order_params(account, symbol, amount, price, normalized_market_type)
    
    def _adjust_amount_optimized(self, precision_info: Dict[str, Any], amount: Decimal) -> Decimal:
        """🆕 수량 조정 최적화 (precision_info 직접 사용)"""
        from app.services.utils import to_decimal
        
        # precision 적용 (내림 처리) - Decimal 기반
        amount_precision = precision_info.get('amount')
        
        if amount_precision is not None:
            if isinstance(amount_precision, int):
                # 소수점 자리수로 지정된 경우
                if amount_precision >= 0:
                    quantize_exp = Decimal('0.1') ** amount_precision
                    adjusted_amount = amount.quantize(quantize_exp, rounding=ROUND_DOWN)
                else:
                    quantize_exp = Decimal('10') ** (-amount_precision)
                    adjusted_amount = amount.quantize(quantize_exp, rounding=ROUND_DOWN)
            else:
                # step size로 지정된 경우
                step_size = to_decimal(amount_precision)
                if step_size > 0:
                    # amount를 step_size로 나눈 몫을 구하고 다시 곱함 (내림 효과)
                    steps = (amount / step_size).quantize(Decimal('1'), rounding=ROUND_DOWN)
                    adjusted_amount = steps * step_size
                else:
                    adjusted_amount = amount
        else:
            adjusted_amount = amount
        
        # limits 적용 - Decimal 기반 비교
        limits = precision_info.get('limits', {}).get('amount', {})
        min_amount = to_decimal(limits.get('min', 0))
        max_amount = to_decimal(limits.get('max', float('inf')))
        
        if adjusted_amount < min_amount:
            adjusted_amount = min_amount
        elif adjusted_amount > max_amount:
            adjusted_amount = max_amount
        
        return adjusted_amount
    
    def _adjust_price_optimized(self, precision_info: Dict[str, Any], price: Decimal) -> Decimal:
        """🆕 가격 조정 최적화 (precision_info 직접 사용)"""
        from app.services.utils import to_decimal
        
        # precision 적용 (내림 처리) - Decimal 기반
        price_precision = precision_info.get('price')
        
        if price_precision is not None:
            if isinstance(price_precision, int):
                # 소수점 자리수로 지정된 경우
                if price_precision >= 0:
                    quantize_exp = Decimal('0.1') ** price_precision
                    adjusted_price = price.quantize(quantize_exp, rounding=ROUND_DOWN)
                else:
                    quantize_exp = Decimal('10') ** (-price_precision)
                    adjusted_price = price.quantize(quantize_exp, rounding=ROUND_DOWN)
            else:
                # step size로 지정된 경우
                step_size = to_decimal(price_precision)
                if step_size > 0:
                    # price를 step_size로 나눈 몫을 구하고 다시 곱함 (내림 효과)
                    steps = (price / step_size).quantize(Decimal('1'), rounding=ROUND_DOWN)
                    adjusted_price = steps * step_size
                else:
                    adjusted_price = price
        else:
            adjusted_price = price
        
        # limits 적용 - Decimal 기반 비교
        limits = precision_info.get('limits', {}).get('price', {})
        min_price = to_decimal(limits.get('min', 0))
        max_price = to_decimal(limits.get('max', float('inf')))
        
        if adjusted_price < min_price:
            adjusted_price = min_price
        elif adjusted_price > max_price:
            adjusted_price = max_price
        
        return adjusted_price
    
    def warm_up_precision_cache(self, account_list: List[Account] = None):
        """🆕 Precision 캐시 웜업 (애플리케이션 시작 시 또는 백그라운드 실행)"""
        if not account_list:
            # 모든 활성 계좌 조회
            account_list = Account.query.filter_by(is_active=True).all()
        
        logger.debug(f"Precision 캐시 웜업 시작 - {len(account_list)}개 계좌")
        
        exchange_processed = set()
        total_updated = 0
        
        for account in account_list:
            exchange_name = account.exchange.lower()
            
            # 거래소별로 한 번씩만 처리
            if exchange_name in exchange_processed:
                continue
            
            try:
                exchange = self.get_exchange(account)
                updated_count = self.precision_cache.update_exchange_precision_cache(exchange_name, exchange)
                total_updated += updated_count
                exchange_processed.add(exchange_name)
                
            except Exception as e:
                logger.error(f"❌ {exchange_name} precision 캐시 웜업 실패: {str(e)}")
                continue
        
        logger.debug(f"Precision 캐시 웜업 완료 - {len(exchange_processed)}개 거래소, {total_updated}개 심볼")
        
        # 캐시 통계 로깅 (DEBUG 레벨)
        stats = self.precision_cache.get_cache_stats()
        logger.debug(f"Precision 캐시 통계: {stats}")
    
    def get_precision_cache_stats(self) -> Dict[str, Any]:
        """🆕 Precision 캐시 성능 통계 조회"""
        return self.precision_cache.get_cache_stats()
    
    def clear_precision_cache(self, exchange_name: str = None):
        """🆕 Precision 캐시 정리"""
        self.precision_cache.clear_cache(exchange_name)

# 전역 인스턴스
exchange_service = ExchangeService() 