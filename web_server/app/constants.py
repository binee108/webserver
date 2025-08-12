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
        """값을 표준 형태로 변환"""
        if value and isinstance(value, str):
            upper_value = value.upper()
            if upper_value in ['FUTURE', 'FUTURES']:
                return cls.FUTURES
            elif upper_value == 'SPOT':
                return cls.SPOT
        return value
    
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