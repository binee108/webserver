"""
애플리케이션 전역 상수 정의
"""

class MarketType:
    """마켓 타입 상수"""
    SPOT = 'SPOT'
    FUTURES = 'FUTURES'
    
    # 소문자 버전 (JavaScript 연동, 레거시 지원용)
    SPOT_LOWER = 'spot'
    FUTURES_LOWER = 'futures'
    
    # 유효한 값 목록
    VALID_TYPES = [SPOT, FUTURES]
    VALID_TYPES_LOWER = [SPOT_LOWER, FUTURES_LOWER]
    
    @classmethod
    def is_valid(cls, value):
        """값이 유효한 market_type인지 확인"""
        if not value:
            return False
        return value.upper() in cls.VALID_TYPES
    
    @classmethod
    def normalize(cls, value):
        """값을 표준 MarketType 상수로 변환 (모든 변형 지원)"""
        if not value:
            return cls.SPOT  # 기본값
        
        if isinstance(value, str):
            upper_value = value.upper()
            # FUTURES 변형들
            if upper_value in ['FUTURE', 'FUTURES', 'DERIVATIVE', 'DERIVATIVES']:
                return cls.FUTURES
            # SPOT 변형들  
            elif upper_value in ['SPOT', 'CASH']:
                return cls.SPOT
        
        # 이미 올바른 상수인 경우
        if value in [cls.SPOT, cls.FUTURES]:
            return value
            
        # 알 수 없는 값은 기본값
        return cls.SPOT
    
    @classmethod
    def to_exchange_type(cls, market_type, exchange_name):
        """MarketType 상수를 거래소별 API 형식으로 변환"""
        # 정규화된 MarketType 상수인지 확인
        normalized_type = cls.normalize(market_type)
        
        if normalized_type == cls.FUTURES:
            # 거래소별 선물 거래 설정값
            if exchange_name in ['binance', 'BINANCE']:
                return 'future'
            elif exchange_name in ['bybit', 'BYBIT']:
                return 'linear'  # USDT 선물
            elif exchange_name in ['okx', 'OKX']:
                return 'swap'
            else:
                return 'future'  # 기본값
        else:  # SPOT
            return 'spot'
    
    @classmethod
    def get_default(cls):
        """기본값 반환"""
        return cls.SPOT


class Exchange:
    """거래소 상수"""
    BINANCE = 'BINANCE'
    BYBIT = 'BYBIT'
    OKX = 'OKX'
    UPBIT = 'UPBIT'
    
    # 소문자 버전 (API 연동용)
    BINANCE_LOWER = 'binance'
    BYBIT_LOWER = 'bybit'
    OKX_LOWER = 'okx'
    UPBIT_LOWER = 'upbit'
    
    # 유효한 값 목록
    VALID_EXCHANGES = [BINANCE, BYBIT, OKX, UPBIT]
    VALID_EXCHANGES_LOWER = [BINANCE_LOWER, BYBIT_LOWER, OKX_LOWER, UPBIT_LOWER]
    
    @classmethod
    def is_valid(cls, value):
        """값이 유효한 거래소인지 확인"""
        if not value:
            return False
        return value.upper() in cls.VALID_EXCHANGES
    
    @classmethod
    def normalize(cls, value):
        """값을 표준 대문자 형태로 변환"""
        if value and isinstance(value, str):
            upper_value = value.upper()
            if upper_value in cls.VALID_EXCHANGES:
                return upper_value
        return value
    
    @classmethod
    def to_lower(cls, value):
        """값을 소문자로 변환"""
        if value and isinstance(value, str):
            return value.lower()
        return value


class OrderType:
    """주문 타입 상수"""
    MARKET = 'MARKET'
    LIMIT = 'LIMIT'
    STOP_LIMIT = 'STOP_LIMIT'
    CANCEL_ALL_ORDER = 'CANCEL_ALL_ORDER'
    
    # 소문자 버전 (API 연동용)
    MARKET_LOWER = 'market'
    LIMIT_LOWER = 'limit'
    STOP_LIMIT_LOWER = 'stop_limit'
    
    # 유효한 거래 주문 타입
    VALID_TRADING_TYPES = [MARKET, LIMIT, STOP_LIMIT]
    # 모든 유효한 타입 (취소 포함)
    VALID_TYPES = [MARKET, LIMIT, STOP_LIMIT, CANCEL_ALL_ORDER]
    
    @classmethod
    def is_valid(cls, value):
        """값이 유효한 order_type인지 확인"""
        if not value:
            return False
        return value.upper() in cls.VALID_TYPES
    
    @classmethod
    def is_trading_type(cls, value):
        """값이 거래 주문 타입인지 확인"""
        if not value:
            return False
        return value.upper() in cls.VALID_TRADING_TYPES
    
    @classmethod
    def normalize(cls, value):
        """값을 표준 대문자 형태로 변환"""
        if value and isinstance(value, str):
            upper_value = value.upper()
            # 공백과 하이픈 처리
            upper_value = upper_value.replace('-', '_').replace(' ', '_')
            if upper_value in cls.VALID_TYPES:
                return upper_value
        return value
    
    @classmethod
    def to_lower(cls, value):
        """값을 소문자로 변환 (API 호출용)"""
        if value and isinstance(value, str):
            return value.lower()
        return value


class MinOrderAmount:
    """거래소별 마켓타입별 최소 거래 금액 (USDT 기준)"""
    
    # Binance - 공식 문서 기준
    BINANCE_SPOT = 10.0      # 현물 10 USDT
    BINANCE_FUTURES = 20.0   # 선물 20 USDT (바이낸스 선물 최소 notional)
    
    # Bybit - 공식 문서 기준
    BYBIT_SPOT = 1.0         # 현물 1 USDT
    BYBIT_FUTURES = 5.0      # 선물 5 USDT
    
    # OKX - 공식 문서 기준
    OKX_SPOT = 1.0           # 현물 1 USDT
    OKX_FUTURES = 5.0        # 선물 5 USDT
    
    # Upbit (KRW 기준)
    UPBIT_SPOT = 5000        # 현물 5000 KRW
    
    # 조정 배수 (안전 마진 2배)
    ADJUSTMENT_MULTIPLIER = 2.0
    
    @classmethod
    def get_min_amount(cls, exchange: str, market_type: str, currency: str = 'USDT') -> float:
        """거래소와 마켓타입에 따른 최소 금액 반환
        
        Args:
            exchange: 거래소 이름 (BINANCE, BYBIT, OKX, UPBIT)
            market_type: 마켓 타입 (SPOT, FUTURES)
            currency: 통화 (USDT, KRW 등)
            
        Returns:
            최소 거래 금액
        """
        exchange_upper = exchange.upper()
        market_type_upper = market_type.upper()
        
        # FUTURES는 모든 변형 처리
        if market_type_upper in ['FUTURE', 'FUTURES', 'SWAP', 'LINEAR']:
            market_type_upper = 'FUTURES'
        
        # 거래소별 최소 금액 매핑
        min_amounts = {
            'BINANCE': {
                'SPOT': cls.BINANCE_SPOT,
                'FUTURES': cls.BINANCE_FUTURES
            },
            'BYBIT': {
                'SPOT': cls.BYBIT_SPOT,
                'FUTURES': cls.BYBIT_FUTURES
            },
            'OKX': {
                'SPOT': cls.OKX_SPOT,
                'FUTURES': cls.OKX_FUTURES
            },
            'UPBIT': {
                'SPOT': cls.UPBIT_SPOT
            }
        }
        
        # 거래소와 마켓타입에 해당하는 최소 금액 반환
        if exchange_upper in min_amounts:
            market_amounts = min_amounts[exchange_upper]
            if market_type_upper in market_amounts:
                return market_amounts[market_type_upper]
        
        # 기본값 (찾을 수 없는 경우)
        if market_type_upper == 'FUTURES':
            return 5.0  # 선물 기본값
        return 10.0  # 현물 기본값