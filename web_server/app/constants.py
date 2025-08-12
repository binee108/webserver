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