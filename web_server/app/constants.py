"""
애플리케이션 전역 상수 정의
"""

from typing import List, Optional

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
    """통합 주문 타입 관리"""
    # 기본 주문 타입
    MARKET = 'MARKET'
    LIMIT = 'LIMIT'
    STOP_MARKET = 'STOP_MARKET'
    STOP_LIMIT = 'STOP_LIMIT'

    # 취소 타입
    CANCEL = 'CANCEL'
    CANCEL_ALL_ORDER = 'CANCEL_ALL_ORDER'

    # 소문자 버전 (API 연동용)
    MARKET_LOWER = 'market'
    LIMIT_LOWER = 'limit'
    STOP_LIMIT_LOWER = 'stop_limit'
    STOP_MARKET_LOWER = 'stop_market'

    # STOP 주문 그룹 (stopPrice 필요)
    STOP_ORDERS = [STOP_MARKET, STOP_LIMIT]

    # LIMIT 주문 그룹 (price 필요)
    LIMIT_ORDERS = [LIMIT, STOP_LIMIT]

    # 유효한 거래 주문 타입
    VALID_TRADING_TYPES = [MARKET, LIMIT, STOP_LIMIT, STOP_MARKET]
    # 모든 유효한 타입 (취소 포함)
    VALID_TYPES = [MARKET, LIMIT, STOP_LIMIT, STOP_MARKET, CANCEL, CANCEL_ALL_ORDER]

    # 주문 우선순위 (낮은 숫자 = 높은 우선순위)
    PRIORITY = {
        MARKET: 1,        # 시장가 주문 최우선
        STOP_MARKET: 2,   # 스탑 시장가
        LIMIT: 3,         # 지정가
        STOP_LIMIT: 4     # 스탑 지정가
    }

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
    def requires_stop_price(cls, order_type):
        """STOP 가격이 필요한 주문 타입 확인"""
        if not order_type:
            return False
        return order_type.upper() in cls.STOP_ORDERS

    @classmethod
    def requires_price(cls, order_type):
        """지정가가 필요한 주문 타입 확인"""
        if not order_type:
            return False
        return order_type.upper() in cls.LIMIT_ORDERS

    @classmethod
    def to_exchange_format(cls, order_type, exchange):
        """거래소별 주문 타입 변환"""
        if not order_type or not exchange:
            return order_type

        # 표준화된 매핑 테이블
        mapping = {
            'binance': {
                cls.STOP_MARKET: 'STOP_MARKET',
                cls.STOP_LIMIT: 'STOP_LIMIT',
                cls.MARKET: 'MARKET',
                cls.LIMIT: 'LIMIT'
            },
            'upbit': {
                cls.STOP_MARKET: 'stop_market',
                cls.STOP_LIMIT: 'stop_limit',
                cls.MARKET: 'market',
                cls.LIMIT: 'limit'
            },
            'bybit': {
                cls.STOP_MARKET: 'Market',
                cls.STOP_LIMIT: 'Limit',
                cls.MARKET: 'Market',
                cls.LIMIT: 'Limit'
            }
        }

        normalized_type = order_type.upper()
        exchange_mapping = mapping.get(exchange.lower(), {})
        return exchange_mapping.get(normalized_type, normalized_type)

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

    @classmethod
    def get_required_params(cls, order_type):
        """주문 타입별 필수 파라미터 반환

        Returns:
            dict: {'price': bool, 'stop_price': bool, 'quantity': bool}
        """
        if not order_type:
            return {'price': False, 'stop_price': False, 'quantity': True}

        normalized_type = order_type.upper()

        return {
            'price': normalized_type in cls.LIMIT_ORDERS,
            'stop_price': normalized_type in cls.STOP_ORDERS,
            'quantity': normalized_type in cls.VALID_TRADING_TYPES
        }

    @classmethod
    def validate_params(cls, order_type, price=None, stop_price=None, quantity=None):
        """주문 타입에 필요한 파라미터가 제공되었는지 검증

        Returns:
            tuple: (is_valid: bool, error_message: str or None)
        """
        if not order_type:
            return False, "order_type이 필요합니다"

        required = cls.get_required_params(order_type)

        if required['price'] and price is None:
            return False, f"{order_type} 주문에는 price가 필수입니다"

        if required['stop_price'] and stop_price is None:
            return False, f"{order_type} 주문에는 stop_price가 필수입니다"

        if required['quantity'] and quantity is None:
            return False, f"{order_type} 주문에는 quantity가 필수입니다"

        return True, None

    @classmethod
    def get_priority(cls, order_type):
        """주문 타입의 우선순위 반환 (낮은 숫자 = 높은 우선순위)

        Args:
            order_type: 주문 타입

        Returns:
            int: 우선순위 (1-4), 알 수 없는 타입은 99
        """
        if not order_type:
            return 99

        normalized_type = order_type.upper()
        return cls.PRIORITY.get(normalized_type, 99)


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


class OrderStatus:
    """통합 주문 상태 (거래소 독립적)"""
    # 기본 상태
    NEW = 'NEW'                      # 신규 주문
    OPEN = 'OPEN'                    # 미체결
    PARTIALLY_FILLED = 'PARTIALLY_FILLED'  # 부분 체결
    FILLED = 'FILLED'                # 완전 체결
    CANCELLED = 'CANCELLED'          # 취소됨
    REJECTED = 'REJECTED'            # 거부됨
    EXPIRED = 'EXPIRED'              # 만료됨

    # 미체결 상태 그룹
    OPEN_STATUSES = [NEW, OPEN, PARTIALLY_FILLED]
    # 완료 상태 그룹
    CLOSED_STATUSES = [FILLED, CANCELLED, REJECTED, EXPIRED]

    @classmethod
    def from_exchange(cls, status: str, exchange: str) -> str:
        """거래소별 상태를 통합 상태로 변환"""
        if not status or not exchange:
            return status

        # 이미 통합 상태인 경우 바로 반환
        if status in [cls.NEW, cls.OPEN, cls.PARTIALLY_FILLED, cls.FILLED, cls.CANCELLED, cls.REJECTED, cls.EXPIRED]:
            return status

        # 소문자 정규화된 상태 처리 (fallback for legacy normalized values)
        normalized_fallback = {
            'open': cls.OPEN,
            'closed': cls.FILLED,
            'canceled': cls.CANCELLED,
            'cancelled': cls.CANCELLED,
            'rejected': cls.REJECTED,
            'expired': cls.EXPIRED,
            'new': cls.NEW
        }

        if status.lower() in normalized_fallback:
            return normalized_fallback[status.lower()]

        # 거래소별 원본 상태 매핑
        mapper = {
            'BINANCE': {
                'NEW': cls.NEW,
                'PARTIALLY_FILLED': cls.PARTIALLY_FILLED,
                'FILLED': cls.FILLED,
                'CANCELED': cls.CANCELLED,  # 바이낸스는 CANCELED 사용
                'CANCELLED': cls.CANCELLED,
                'REJECTED': cls.REJECTED,
                'EXPIRED': cls.EXPIRED
            },
            'BYBIT': {
                'Created': cls.NEW,
                'New': cls.OPEN,
                'PartiallyFilled': cls.PARTIALLY_FILLED,
                'Filled': cls.FILLED,
                'Cancelled': cls.CANCELLED,
                'Canceled': cls.CANCELLED,
                'Rejected': cls.REJECTED
            },
            'UPBIT': {
                'wait': cls.OPEN,
                'done': cls.FILLED,
                'cancel': cls.CANCELLED
            },
            'OKX': {
                'live': cls.OPEN,
                'partially_filled': cls.PARTIALLY_FILLED,
                'filled': cls.FILLED,
                'canceled': cls.CANCELLED
            }
        }

        exchange_upper = exchange.upper()
        if exchange_upper in mapper:
            return mapper[exchange_upper].get(status, status)
        return status

    @classmethod
    def is_open(cls, status: str) -> bool:
        """미체결 상태인지 확인"""
        return status in cls.OPEN_STATUSES

    @classmethod
    def is_closed(cls, status: str) -> bool:
        """완료 상태인지 확인"""
        return status in cls.CLOSED_STATUSES

    @classmethod
    def get_open_statuses(cls) -> list:
        """미체결 상태 목록 반환"""
        return cls.OPEN_STATUSES.copy()

    @classmethod
    def get_closed_statuses(cls) -> list:
        """완료 상태 목록 반환"""
        return cls.CLOSED_STATUSES.copy()


class OrderEventType:
    """주문 이벤트 타입"""
    ORDER_CREATED = 'order_created'     # 주문 생성
    ORDER_UPDATED = 'order_updated'     # 주문 업데이트
    ORDER_FILLED = 'order_filled'       # 주문 체결
    ORDER_CANCELLED = 'order_cancelled' # 주문 취소
    TRADE_EXECUTED = 'trade_executed'   # 거래 실행
    POSITION_UPDATED = 'position_updated' # 포지션 업데이트

    # 유효한 이벤트 타입
    VALID_TYPES = [
        ORDER_CREATED, ORDER_UPDATED, ORDER_FILLED,
        ORDER_CANCELLED, TRADE_EXECUTED, POSITION_UPDATED
    ]

    @classmethod
    def is_valid(cls, event_type: str) -> bool:
        """유효한 이벤트 타입인지 확인"""
        return event_type in cls.VALID_TYPES

    @classmethod
    def get_display_text(cls, event_type: str) -> str:
        """이벤트 타입의 한국어 표시 텍스트 반환"""
        display_map = {
            cls.ORDER_CREATED: '새 주문',
            cls.ORDER_UPDATED: '주문 업데이트',
            cls.ORDER_FILLED: '주문 체결',
            cls.ORDER_CANCELLED: '주문 취소',
            cls.TRADE_EXECUTED: '거래 실행',
            cls.POSITION_UPDATED: '포지션 업데이트'
        }
        return display_map.get(event_type, event_type)
