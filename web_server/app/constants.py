# @FEAT:framework @COMP:config @TYPE:boilerplate
"""
애플리케이션 전역 상수 정의
"""

from typing import List, Optional
import math

class AccountType:
    """계좌 타입"""
    CRYPTO = 'CRYPTO'
    STOCK = 'STOCK'  # 증권 통합 타입

    VALID_TYPES = [CRYPTO, STOCK]

    @classmethod
    def is_crypto(cls, account_type):
        """크립토 계좌 타입인지 확인

        Args:
            account_type (str): 계좌 타입 (CRYPTO 또는 STOCK)

        Returns:
            bool: 크립토 계좌 타입이면 True

        Examples:
            >>> AccountType.is_crypto('CRYPTO')
            True
            >>> AccountType.is_crypto('STOCK')
            False
        """
        return account_type == cls.CRYPTO

    @classmethod
    def is_securities(cls, account_type):
        """증권 계좌 타입인지 확인

        Args:
            account_type (str): 계좌 타입 (CRYPTO 또는 STOCK)

        Returns:
            bool: 증권 계좌 타입이면 True

        Examples:
            >>> AccountType.is_securities('STOCK')
            True
            >>> AccountType.is_securities('CRYPTO')
            False
        """
        return account_type == cls.STOCK

    @classmethod
    def normalize(cls, value):
        """값을 표준 AccountType 상수로 변환"""
        if not value:
            return cls.CRYPTO  # 기본값

        upper_value = value.upper()
        if upper_value in ['STOCK', 'SECURITIES', 'EQUITY']:
            return cls.STOCK
        elif upper_value in ['CRYPTO', 'CRYPTOCURRENCY']:
            return cls.CRYPTO

        return cls.CRYPTO  # 기본값


class SecuritiesMarketType:
    """증권 마켓 타입"""
    DOMESTIC_STOCK = 'DOMESTIC_STOCK'      # 국내주식
    OVERSEAS_STOCK = 'OVERSEAS_STOCK'      # 해외주식
    DOMESTIC_FUTURES = 'DOMESTIC_FUTURES'  # 국내선물옵션
    OVERSEAS_FUTURES = 'OVERSEAS_FUTURES'  # 해외선물옵션

    VALID_TYPES = [DOMESTIC_STOCK, OVERSEAS_STOCK, DOMESTIC_FUTURES, OVERSEAS_FUTURES]


class MarketType:
    """마켓 타입 상수 (크립토 + 증권 통합)"""
    # 크립토 마켓
    SPOT = 'SPOT'
    FUTURES = 'FUTURES'

    # 증권 마켓
    DOMESTIC_STOCK = 'DOMESTIC_STOCK'            # 국내주식
    OVERSEAS_STOCK = 'OVERSEAS_STOCK'            # 해외주식
    DOMESTIC_FUTUREOPTION = 'DOMESTIC_FUTUREOPTION'  # 국내선물옵션
    OVERSEAS_FUTUREOPTION = 'OVERSEAS_FUTUREOPTION'  # 해외선물옵션

    # 소문자 버전 (JavaScript 연동, 레거시 지원용)
    SPOT_LOWER = 'spot'
    FUTURES_LOWER = 'futures'

    # 유효한 값 목록
    CRYPTO_TYPES = [SPOT, FUTURES]
    SECURITIES_TYPES = [DOMESTIC_STOCK, OVERSEAS_STOCK, DOMESTIC_FUTUREOPTION, OVERSEAS_FUTUREOPTION]
    VALID_TYPES = CRYPTO_TYPES + SECURITIES_TYPES
    VALID_TYPES_LOWER = [SPOT_LOWER, FUTURES_LOWER]

    @classmethod
    def is_valid(cls, value):
        """값이 유효한 market_type인지 확인"""
        if not value:
            return False
        return value.upper() in cls.VALID_TYPES

    @classmethod
    def is_crypto(cls, value):
        """크립토 마켓 타입인지 확인"""
        if not value:
            return False
        return value.upper() in cls.CRYPTO_TYPES

    @classmethod
    def is_securities(cls, value):
        """증권 마켓 타입인지 확인"""
        if not value:
            return False
        return value.upper() in cls.SECURITIES_TYPES

    @classmethod
    def get_all_crypto(cls):
        """모든 크립토 마켓 타입 반환"""
        return cls.CRYPTO_TYPES.copy()

    @classmethod
    def get_all_securities(cls):
        """모든 증권 마켓 타입 반환"""
        return cls.SECURITIES_TYPES.copy()

    @classmethod
    def normalize(cls, value):
        """값을 표준 MarketType 상수로 변환 (모든 변형 지원)

        Args:
            value (str): 변환할 마켓 타입 값 (SPOT, FUTURES, 대소문자 무관)

        Returns:
            str: 표준 MarketType 상수 (SPOT, FUTURES, 또는 증권 타입)

        Examples:
            >>> MarketType.normalize('future')
            'FUTURES'
            >>> MarketType.normalize('SPOT')
            'SPOT'
            >>> MarketType.normalize('DOMESTIC_STOCK')
            'DOMESTIC_STOCK'
        """
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
            # 증권 타입들 (정확한 매칭)
            elif upper_value in cls.SECURITIES_TYPES:
                return upper_value

        # 이미 올바른 상수인 경우
        if value in cls.VALID_TYPES:
            return value

        # 알 수 없는 값은 기본값
        return cls.SPOT

    @classmethod
    def to_exchange_type(cls, market_type, exchange_name):
        """MarketType 상수를 거래소별 API 형식으로 변환

        Args:
            market_type (str): 마켓 타입 (SPOT, FUTURES)
            exchange_name (str): 거래소 이름 (binance, bybit, okx 등)

        Returns:
            str: 거래소 API 형식의 마켓 타입 (spot, future, linear, swap 등)

        Examples:
            >>> MarketType.to_exchange_type('FUTURES', 'binance')
            'future'
            >>> MarketType.to_exchange_type('FUTURES', 'bybit')
            'linear'
            >>> MarketType.to_exchange_type('SPOT', 'binance')
            'spot'
        """
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
        """기본값 반환

        Returns:
            str: 기본 마켓 타입 (SPOT)

        Examples:
            >>> MarketType.get_default()
            'SPOT'
        """
        return cls.SPOT


class Exchange:
    """거래소 상수"""
    # 크립토 거래소
    BINANCE = 'BINANCE'
    BYBIT = 'BYBIT'
    OKX = 'OKX'
    UPBIT = 'UPBIT'
    BITHUMB = 'BITHUMB'

    # 증권 거래소
    KIS = 'KIS'           # 한국투자증권
    KIWOOM = 'KIWOOM'     # 키움증권
    LS = 'LS'             # LS증권
    EBEST = 'EBEST'       # 이베스트투자증권

    # 소문자 버전 (API 연동용)
    BINANCE_LOWER = 'binance'
    BYBIT_LOWER = 'bybit'
    OKX_LOWER = 'okx'
    UPBIT_LOWER = 'upbit'
    BITHUMB_LOWER = 'bithumb'

    # 유효한 값 목록
    VALID_EXCHANGES = [BINANCE, BYBIT, OKX, UPBIT, BITHUMB, KIS, KIWOOM, LS, EBEST]
    VALID_EXCHANGES_LOWER = [x.lower() for x in VALID_EXCHANGES]

    CRYPTO_EXCHANGES = [BINANCE, BYBIT, OKX, UPBIT, BITHUMB]
    SECURITIES_EXCHANGES = [KIS, KIWOOM, LS, EBEST]

    @classmethod
    def is_valid(cls, value):
        """값이 유효한 거래소인지 확인

        Args:
            value (str): 확인할 거래소 이름

        Returns:
            bool: 유효한 거래소이면 True

        Examples:
            >>> Exchange.is_valid('BINANCE')
            True
            >>> Exchange.is_valid('binance')
            True
            >>> Exchange.is_valid('INVALID')
            False
        """
        if not value:
            return False
        return value.upper() in cls.VALID_EXCHANGES

    @classmethod
    def is_securities(cls, exchange):
        """증권 거래소 여부 확인

        Args:
            exchange (str): 거래소 이름

        Returns:
            bool: 증권 거래소이면 True

        Examples:
            >>> Exchange.is_securities('KIS')
            True
            >>> Exchange.is_securities('BINANCE')
            False
        """
        if not exchange:
            return False
        return exchange.upper() in cls.SECURITIES_EXCHANGES

    @classmethod
    def is_crypto(cls, exchange):
        """크립토 거래소 여부 확인

        Args:
            exchange (str): 거래소 이름

        Returns:
            bool: 크립토 거래소이면 True

        Examples:
            >>> Exchange.is_crypto('BINANCE')
            True
            >>> Exchange.is_crypto('KIS')
            False
        """
        if not exchange:
            return False
        return exchange.upper() in cls.CRYPTO_EXCHANGES

    @classmethod
    def normalize(cls, value):
        """값을 표준 대문자 형태로 변환

        Args:
            value (str): 거래소 이름

        Returns:
            str: 대문자로 변환된 거래소 이름 (유효하지 않으면 원본 반환)

        Examples:
            >>> Exchange.normalize('binance')
            'BINANCE'
            >>> Exchange.normalize('BINANCE')
            'BINANCE'
        """
        if value and isinstance(value, str):
            upper_value = value.upper()
            if upper_value in cls.VALID_EXCHANGES:
                return upper_value
        return value

    @classmethod
    def to_lower(cls, value):
        """값을 소문자로 변환

        Args:
            value (str): 거래소 이름

        Returns:
            str: 소문자로 변환된 거래소 이름

        Examples:
            >>> Exchange.to_lower('BINANCE')
            'binance'
        """
        if value and isinstance(value, str):
            return value.lower()
        return value


class OrderType:
    """통합 주문 타입 관리 (크립토 + 증권)"""
    # 기본 주문 타입 (크립토 + 증권 공통)
    MARKET = 'MARKET'
    LIMIT = 'LIMIT'
    STOP_MARKET = 'STOP_MARKET'
    STOP_LIMIT = 'STOP_LIMIT'

    # 증권 전용 주문 타입
    CONDITIONAL_LIMIT = 'CONDITIONAL_LIMIT'  # 조건부 지정가
    BEST_LIMIT = 'BEST_LIMIT'                # 최유리 지정가
    PRE_MARKET = 'PRE_MARKET'                # 시간외 단일가
    AFTER_MARKET = 'AFTER_MARKET'            # 시간외 종가

    # 취소 타입
    CANCEL = 'CANCEL'
    CANCEL_ALL_ORDER = 'CANCEL_ALL_ORDER'

    # 소문자 버전 (API 연동용)
    MARKET_LOWER = 'market'
    LIMIT_LOWER = 'limit'
    STOP_LIMIT_LOWER = 'stop_limit'
    STOP_MARKET_LOWER = 'stop_market'

    # STOP 주문 그룹 (stopPrice 필요)
    STOP_ORDERS = [STOP_MARKET, STOP_LIMIT, CONDITIONAL_LIMIT]

    # LIMIT 주문 그룹 (price 필요)
    LIMIT_ORDERS = [LIMIT, STOP_LIMIT, CONDITIONAL_LIMIT, PRE_MARKET, AFTER_MARKET]

    # 유효한 거래 주문 타입
    VALID_TRADING_TYPES = [MARKET, LIMIT, STOP_LIMIT, STOP_MARKET, CONDITIONAL_LIMIT, BEST_LIMIT, PRE_MARKET, AFTER_MARKET]
    # 모든 유효한 타입 (취소 포함)
    VALID_TYPES = VALID_TRADING_TYPES + [CANCEL, CANCEL_ALL_ORDER]

    # 주문 우선순위 (낮은 숫자 = 높은 우선순위)
    # 배치 주문 처리 순서: MARKET(1) > CANCEL(2) > LIMIT(3) ≈ STOP(4-5)
    #
    # 설계 원칙:
    # - MARKET 주문이 최우선 (즉시 체결)
    # - CANCEL이 2순위 (기존 주문 제거)
    # - LIMIT/STOP은 비슷한 우선순위 범위 (3-6)
    #   → 같은 레벨에서 price/stop_price로 2차 정렬
    # - STOP_MARKET(4) < STOP_LIMIT(5): stop_price 동일 시 STOP_MARKET 우선
    PRIORITY = {
        MARKET: 1,             # 시장가 주문 최우선
        CANCEL: 2,             # 주문 취소
        CANCEL_ALL_ORDER: 2,   # 전체 주문 취소 (CANCEL과 동일)
        LIMIT: 3,              # 지정가
        STOP_MARKET: 4,        # 스탑 시장가 (stop_price 동일 시 LIMIT보다 우선)
        STOP_LIMIT: 5,         # 스탑 지정가
        CONDITIONAL_LIMIT: 6,  # 조건부 지정가
        BEST_LIMIT: 3,         # 최유리 지정가 (LIMIT과 동일)
        PRE_MARKET: 3,         # 시간외 단일가 (LIMIT과 동일)
        AFTER_MARKET: 3        # 시간외 종가 (LIMIT과 동일)
    }

    @classmethod
    def is_valid(cls, value):
        """값이 유효한 order_type인지 확인

        Args:
            value (str): 확인할 주문 타입

        Returns:
            bool: 유효한 주문 타입이면 True

        Examples:
            >>> OrderType.is_valid('MARKET')
            True
            >>> OrderType.is_valid('LIMIT')
            True
            >>> OrderType.is_valid('INVALID')
            False
        """
        if not value:
            return False
        return value.upper() in cls.VALID_TYPES

    @classmethod
    def is_trading_type(cls, value):
        """값이 거래 주문 타입인지 확인 (취소 타입 제외)

        Args:
            value (str): 확인할 주문 타입

        Returns:
            bool: 거래 주문 타입이면 True (CANCEL 제외)

        Examples:
            >>> OrderType.is_trading_type('MARKET')
            True
            >>> OrderType.is_trading_type('CANCEL')
            False
        """
        if not value:
            return False
        return value.upper() in cls.VALID_TRADING_TYPES

    @classmethod
    def requires_stop_price(cls, order_type):
        """STOP 가격이 필요한 주문 타입 확인

        Args:
            order_type (str): 주문 타입

        Returns:
            bool: stop_price가 필요하면 True (STOP_MARKET, STOP_LIMIT 등)

        Examples:
            >>> OrderType.requires_stop_price('STOP_LIMIT')
            True
            >>> OrderType.requires_stop_price('MARKET')
            False
        """
        if not order_type:
            return False
        return order_type.upper() in cls.STOP_ORDERS

    @classmethod
    def requires_price(cls, order_type):
        """지정가가 필요한 주문 타입 확인

        Args:
            order_type (str): 주문 타입

        Returns:
            bool: price가 필요하면 True (LIMIT, STOP_LIMIT 등)

        Examples:
            >>> OrderType.requires_price('LIMIT')
            True
            >>> OrderType.requires_price('MARKET')
            False
        """
        if not order_type:
            return False
        return order_type.upper() in cls.LIMIT_ORDERS

    @classmethod
    def to_exchange_format(cls, order_type, exchange):
        """거래소별 주문 타입 변환

        Args:
            order_type (str): 표준 주문 타입 (MARKET, LIMIT 등)
            exchange (str): 거래소 이름

        Returns:
            str: 거래소 API 형식의 주문 타입

        Examples:
            >>> OrderType.to_exchange_format('MARKET', 'binance')
            'MARKET'
            >>> OrderType.to_exchange_format('STOP_MARKET', 'upbit')
            'stop_market'
        """
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
        """값을 표준 대문자 형태로 변환

        Args:
            value (str): 주문 타입 값

        Returns:
            str: 표준 대문자 형태의 주문 타입 (유효하지 않으면 원본 반환)

        Examples:
            >>> OrderType.normalize('market')
            'MARKET'
            >>> OrderType.normalize('stop-limit')
            'STOP_LIMIT'
        """
        if value and isinstance(value, str):
            upper_value = value.upper()
            # 공백과 하이픈 처리
            upper_value = upper_value.replace('-', '_').replace(' ', '_')
            if upper_value in cls.VALID_TYPES:
                return upper_value
        return value

    @classmethod
    def to_lower(cls, value):
        """값을 소문자로 변환 (API 호출용)

        Args:
            value (str): 주문 타입

        Returns:
            str: 소문자로 변환된 주문 타입

        Examples:
            >>> OrderType.to_lower('MARKET')
            'market'
        """
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

        # BEST_LIMIT은 price 불필요 (최유리 가격 자동 적용)
        requires_price = normalized_type in cls.LIMIT_ORDERS and normalized_type != cls.BEST_LIMIT

        return {
            'price': requires_price,
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

    # Bithumb (KRW 기준)
    BITHUMB_SPOT = 5000      # 현물 5000 KRW (ESTIMATED - 업비트와 유사)

    # 조정 배수 (안전 마진 2배)
    ADJUSTMENT_MULTIPLIER = 2.0

    @classmethod
    def get_min_amount(cls, exchange: str, market_type: str, currency: str = 'USDT') -> float:
        """거래소와 마켓타입에 따른 최소 금액 반환

        Args:
            exchange (str): 거래소 이름 (BINANCE, BYBIT, OKX, UPBIT)
            market_type (str): 마켓 타입 (SPOT, FUTURES)
            currency (str): 통화 (USDT, KRW 등), 기본값 'USDT'

        Returns:
            float: 최소 거래 금액 (USDT 또는 해당 통화 기준)

        Examples:
            >>> MinOrderAmount.get_min_amount('BINANCE', 'SPOT')
            10.0
            >>> MinOrderAmount.get_min_amount('BINANCE', 'FUTURES')
            20.0
            >>> MinOrderAmount.get_min_amount('BYBIT', 'SPOT')
            1.0
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
            },
            'BITHUMB': {
                'SPOT': cls.BITHUMB_SPOT
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
        """거래소별 상태를 통합 상태로 변환

        Args:
            status (str): 거래소 원본 주문 상태
            exchange (str): 거래소 이름

        Returns:
            str: 통합 주문 상태 (NEW, OPEN, FILLED, CANCELLED 등)

        Examples:
            >>> OrderStatus.from_exchange('NEW', 'BINANCE')
            'NEW'
            >>> OrderStatus.from_exchange('PartiallyFilled', 'BYBIT')
            'PARTIALLY_FILLED'
            >>> OrderStatus.from_exchange('wait', 'UPBIT')
            'OPEN'
        """
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
        """미체결 상태인지 확인

        Args:
            status (str): 주문 상태

        Returns:
            bool: 미체결 상태이면 True (NEW, OPEN, PARTIALLY_FILLED)

        Examples:
            >>> OrderStatus.is_open('OPEN')
            True
            >>> OrderStatus.is_open('FILLED')
            False
        """
        return status in cls.OPEN_STATUSES

    @classmethod
    def is_closed(cls, status: str) -> bool:
        """완료 상태인지 확인

        Args:
            status (str): 주문 상태

        Returns:
            bool: 완료 상태이면 True (FILLED, CANCELLED, REJECTED, EXPIRED)

        Examples:
            >>> OrderStatus.is_closed('FILLED')
            True
            >>> OrderStatus.is_closed('OPEN')
            False
        """
        return status in cls.CLOSED_STATUSES

    @classmethod
    def get_open_statuses(cls) -> list:
        """미체결 상태 목록 반환

        Returns:
            list: 미체결 상태 목록 [NEW, OPEN, PARTIALLY_FILLED]

        Examples:
            >>> OrderStatus.get_open_statuses()
            ['NEW', 'OPEN', 'PARTIALLY_FILLED']
        """
        return cls.OPEN_STATUSES.copy()

    @classmethod
    def get_closed_statuses(cls) -> list:
        """완료 상태 목록 반환

        Returns:
            list: 완료 상태 목록 [FILLED, CANCELLED, REJECTED, EXPIRED]

        Examples:
            >>> OrderStatus.get_closed_statuses()
            ['FILLED', 'CANCELLED', 'REJECTED', 'EXPIRED']
        """
        return cls.CLOSED_STATUSES.copy()


# @FEAT:order-limits @COMP:validation @TYPE:config
# 주문 제한 관련 상수
MAX_ORDERS_PER_SYMBOL_SIDE = 10  # 심볼당 side별 전체 제한 (LIMIT + STOP 합계)
MAX_ORDERS_PER_SYMBOL_TYPE_SIDE = 5  # 심볼당 타입 그룹별 side별 제한

# 주문 타입 그룹 분류
# Purpose: 심볼당 타입 그룹별 주문 제한 관리 (MAX_ORDERS_PER_SYMBOL_TYPE_SIDE 적용)
# - LIMIT 그룹: 일반 지정가 주문 (심볼당 side별 최대 5개)
# - STOP 그룹: 스톱 주문 (심볼당 side별 최대 5개)
# 예시: BTC/USDT buy 방향 - LIMIT 5개 + STOP 5개 = 총 10개 허용
ORDER_TYPE_GROUPS = {
    "LIMIT": ["LIMIT", "LIMIT_MAKER"],
    "STOP": ["STOP", "STOP_LIMIT", "STOP_MARKET"]
}


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
        """유효한 이벤트 타입인지 확인

        Args:
            event_type (str): 확인할 이벤트 타입

        Returns:
            bool: 유효한 이벤트 타입이면 True

        Examples:
            >>> OrderEventType.is_valid('order_created')
            True
            >>> OrderEventType.is_valid('invalid_event')
            False
        """
        return event_type in cls.VALID_TYPES

    @classmethod
    def get_display_text(cls, event_type: str) -> str:
        """이벤트 타입의 한국어 표시 텍스트 반환

        Args:
            event_type (str): 이벤트 타입

        Returns:
            str: 한국어 표시 텍스트

        Examples:
            >>> OrderEventType.get_display_text('order_created')
            '새 주문'
            >>> OrderEventType.get_display_text('order_filled')
            '주문 체결'
        """
        display_map = {
            cls.ORDER_CREATED: '새 주문',
            cls.ORDER_UPDATED: '주문 업데이트',
            cls.ORDER_FILLED: '주문 체결',
            cls.ORDER_CANCELLED: '주문 취소',
            cls.TRADE_EXECUTED: '거래 실행',
            cls.POSITION_UPDATED: '포지션 업데이트'
        }
        return display_map.get(event_type, event_type)


class KISOrderType:
    """한국투자증권 주문 타입 매핑

    Generic OrderType을 한국투자증권 API 주문 코드로 변환
    """
    # 국내주식 주문 구분 코드
    DOMESTIC_LIMIT = '00'           # 지정가
    DOMESTIC_MARKET = '01'          # 시장가
    DOMESTIC_CONDITIONAL = '02'     # 조건부지정가
    DOMESTIC_BEST = '03'            # 최유리지정가
    DOMESTIC_PRE_MARKET = '05'      # 시간외단일가
    DOMESTIC_AFTER_MARKET = '06'    # 시간외종가

    # 해외주식 주문 구분 코드 (단순)
    OVERSEAS_LIMIT = '00'           # 지정가
    OVERSEAS_MARKET = '01'          # 시장가

    # 선물옵션 주문 구분 코드
    FUTURES_LIMIT = '1'             # 지정가
    FUTURES_MARKET = '2'            # 시장가
    FUTURES_CONDITION = '3'         # 조건부지정가

    @classmethod
    def to_domestic_code(cls, order_type: str) -> str:
        """Generic OrderType을 국내주식 주문 코드로 변환

        Args:
            order_type: 표준 OrderType 상수 (MARKET, LIMIT 등)

        Returns:
            str: KIS API 주문 구분 코드 ('00', '01' 등)

        Raises:
            ValueError: 지원하지 않는 주문 타입인 경우
        """
        mapping = {
            OrderType.LIMIT: cls.DOMESTIC_LIMIT,
            OrderType.MARKET: cls.DOMESTIC_MARKET,
            OrderType.CONDITIONAL_LIMIT: cls.DOMESTIC_CONDITIONAL,
            OrderType.BEST_LIMIT: cls.DOMESTIC_BEST,
            OrderType.PRE_MARKET: cls.DOMESTIC_PRE_MARKET,
            OrderType.AFTER_MARKET: cls.DOMESTIC_AFTER_MARKET,
        }
        code = mapping.get(order_type.upper() if isinstance(order_type, str) else order_type)
        if code is None:
            raise ValueError(f"국내주식에서 지원하지 않는 주문 타입입니다: {order_type}")
        return code

    @classmethod
    def to_overseas_code(cls, order_type: str) -> str:
        """Generic OrderType을 해외주식 주문 코드로 변환

        Args:
            order_type: 표준 OrderType 상수 (MARKET, LIMIT)

        Returns:
            str: KIS API 주문 구분 코드 ('00', '01')

        Raises:
            ValueError: 지원하지 않는 주문 타입인 경우
        """
        mapping = {
            OrderType.LIMIT: cls.OVERSEAS_LIMIT,
            OrderType.MARKET: cls.OVERSEAS_MARKET,
        }
        code = mapping.get(order_type.upper() if isinstance(order_type, str) else order_type)
        if code is None:
            raise ValueError(f"해외주식에서 지원하지 않는 주문 타입입니다: {order_type}")
        return code

    @classmethod
    def to_futures_code(cls, order_type: str) -> str:
        """Generic OrderType을 선물옵션 주문 코드로 변환

        Args:
            order_type: 표준 OrderType 상수

        Returns:
            str: KIS API 주문 구분 코드 ('1', '2', '3')

        Raises:
            ValueError: 지원하지 않는 주문 타입인 경우
        """
        mapping = {
            OrderType.LIMIT: cls.FUTURES_LIMIT,
            OrderType.MARKET: cls.FUTURES_MARKET,
            OrderType.CONDITIONAL_LIMIT: cls.FUTURES_CONDITION,
        }
        code = mapping.get(order_type.upper() if isinstance(order_type, str) else order_type)
        if code is None:
            raise ValueError(f"선물옵션에서 지원하지 않는 주문 타입입니다: {order_type}")
        return code

    @classmethod
    def from_domestic_code(cls, code: str) -> str:
        """국내주식 주문 코드를 Generic OrderType으로 역변환

        Args:
            code: KIS API 주문 구분 코드

        Returns:
            str: 표준 OrderType 상수
        """
        reverse_mapping = {
            cls.DOMESTIC_LIMIT: OrderType.LIMIT,
            cls.DOMESTIC_MARKET: OrderType.MARKET,
            cls.DOMESTIC_CONDITIONAL: OrderType.CONDITIONAL_LIMIT,
            cls.DOMESTIC_BEST: OrderType.BEST_LIMIT,
            cls.DOMESTIC_PRE_MARKET: OrderType.PRE_MARKET,
            cls.DOMESTIC_AFTER_MARKET: OrderType.AFTER_MARKET,
        }
        return reverse_mapping.get(code, OrderType.LIMIT)  # 기본값: LIMIT

    @classmethod
    def from_overseas_code(cls, code: str) -> str:
        """해외주식 주문 코드를 Generic OrderType으로 역변환

        Args:
            code: KIS API 주문 구분 코드

        Returns:
            str: 표준 OrderType 상수
        """
        reverse_mapping = {
            cls.OVERSEAS_LIMIT: OrderType.LIMIT,
            cls.OVERSEAS_MARKET: OrderType.MARKET,
        }
        return reverse_mapping.get(code, OrderType.LIMIT)  # 기본값: LIMIT

    @classmethod
    def from_futures_code(cls, code: str) -> str:
        """선물옵션 주문 코드를 Generic OrderType으로 역변환

        Args:
            code: KIS API 주문 구분 코드

        Returns:
            str: 표준 OrderType 상수
        """
        reverse_mapping = {
            cls.FUTURES_LIMIT: OrderType.LIMIT,
            cls.FUTURES_MARKET: OrderType.MARKET,
            cls.FUTURES_CONDITION: OrderType.CONDITIONAL_LIMIT,
        }
        return reverse_mapping.get(code, OrderType.LIMIT)  # 기본값: LIMIT


# @FEAT:order-queue @COMP:config @TYPE:core
class ExchangeLimits:
    """거래소별 열린 주문 제한 관리

    거래소별 심볼당/계정당 열린 주문 제한을 정의하고,
    대기열 시스템에서 사용할 동적 제한을 계산합니다.
    """

    # 거래소별 제한 상수 (거래소 공식 문서 기준)
    LIMITS = {
        'BINANCE': {
            MarketType.FUTURES: {
                'per_symbol': 200,      # 심볼당 열린 주문 제한
                'per_account': 10000,   # 계정당 총 열린 주문 제한
                'conditional': 10       # 조건부 주문 제한 (STOP)
            },
            MarketType.SPOT: {
                'per_symbol': 25,
                'per_account': 1000,
                'conditional': 5
            }
        },
        'BYBIT': {
            MarketType.FUTURES: {
                'per_symbol': 500,
                'per_account': None,    # 제한 없음
                'conditional': 10
            },
            MarketType.SPOT: {
                'per_symbol': None,
                'per_account': 500,
                'conditional': 30
            }
        },
        'OKX': {
            MarketType.FUTURES: {
                'per_symbol': 500,
                'per_account': 4000,
                'conditional': None     # 별도 제한 없음
            },
            MarketType.SPOT: {
                'per_symbol': 500,
                'per_account': 4000,
                'conditional': None
            }
        },
        'UPBIT': {
            MarketType.SPOT: {
                'per_symbol': None,
                'per_account': None,
                'conditional': 20       # 조건부 주문만 제한
            }
        },
        'BITHUMB': {
            MarketType.SPOT: {
                'per_symbol': None,     # 공식 문서 없음 - 보수적 기본값 사용
                'per_account': None,
                'conditional': 20       # ESTIMATED - 업비트와 유사 (공식 문서 없음)
            }
        }
    }

    # 기본 제한값
    DEFAULT_MAX_ORDERS = 20         # 제한이 없을 때 기본값
    MAX_CAP = 20                     # 계산된 제한의 최대 캡
    MIN_LIMIT = 1                    # 최소 제한
    DEFAULT_STOP_LIMIT = 5          # STOP 주문 기본 제한


    # @FEAT:order-queue @COMP:config @TYPE:core
    @classmethod
    def calculate_symbol_limit(cls, exchange: str, market_type: str, symbol: str = None) -> dict:
        """심볼당 열린 주문 제한 계산

        계산 로직:
        1. 심볼당 제한의 10% (존재 시)
        2. 계정당 제한의 10% (심볼당 없을 시)
        3. 기본값 20개 (모두 없을 시)

        제약 조건:
        - 최대 캡: 20개
        - 최소: 1개
        - STOP 주문: 별도 제한 (기본 5개)

        BREAKING CHANGE (Side-based separation v2.0):
        - max_orders: 이제 총 허용량을 나타냄 (Buy + Sell 합계)
        - max_orders_per_side: 각 side(Buy/Sell)의 독립적인 제한
        - max_stop_orders: 이제 총 STOP 허용량을 나타냄 (Buy + Sell 합계)
        - max_stop_orders_per_side: 각 side(Buy/Sell)의 독립적인 STOP 제한
        - 기존 동작: 심볼당 10개 제한
        - 신규 동작: 각 side당 10개 제한 (총 최대 20개)

        STOP 주문 할당 정책 (v2.4 - 2025-10-16):
        - STOP 주문은 전체 주문의 50%로 고정 할당하여 예측 가능성 향상
        - 계산식: max_stop_per_side = max_orders_per_side // 2 (정수 나눗셈)
        - 엣지 케이스: max_orders_per_side=1 시 STOP=1, LIMIT=0 (STOP 우선 정책)
        - 예: BINANCE FUTURES (20개/side) → STOP 10개, LIMIT 10개
        - 예: BINANCE SPOT (2개/side) → STOP 1개, LIMIT 1개
        - 거래소 조건부 제한(conditional) 우선 적용

        Args:
            exchange: 거래소 이름 (BINANCE, BYBIT, OKX, UPBIT)
            market_type: 마켓 타입 (SPOT, FUTURES)
            symbol: 심볼 (현재는 사용하지 않음, 향후 심볼별 커스텀 제한용)

        Returns:
            dict: {
                'max_orders': int,                # 총 허용량 (Buy + Sell 합계)
                'max_orders_per_side': int,       # 각 side별 제한 (Buy 또는 Sell)
                'max_stop_orders': int,           # 총 STOP 허용량 (Buy + Sell 합계)
                'max_stop_orders_per_side': int,  # 각 side별 STOP 제한
                'per_symbol_limit': int,          # 거래소 심볼당 원본 제한
                'per_account_limit': int,         # 거래소 계정당 원본 제한
                'calculation_method': str         # 계산 방법 (per_symbol, per_account, default)
            }

        Examples:
            >>> ExchangeLimits.calculate_symbol_limit('BINANCE', 'FUTURES')
            {'max_orders': 40, 'max_orders_per_side': 20, 'max_stop_orders': 20, 'max_stop_orders_per_side': 10, ...}

            >>> ExchangeLimits.calculate_symbol_limit('BINANCE', 'SPOT')
            {'max_orders': 4, 'max_orders_per_side': 2, 'max_stop_orders': 2, 'max_stop_orders_per_side': 1, ...}
        """
        exchange_upper = exchange.upper()
        market_type_normalized = MarketType.normalize(market_type)

        # 거래소별 제한 조회
        exchange_limits = cls.LIMITS.get(exchange_upper, {})
        market_limits = exchange_limits.get(market_type_normalized, {})

        per_symbol = market_limits.get('per_symbol')
        per_account = market_limits.get('per_account')
        conditional_limit = market_limits.get('conditional', cls.DEFAULT_STOP_LIMIT)

        # 제한 계산 로직
        calculated_limit = None
        calculation_method = 'default'

        if per_symbol is not None:
            # 1순위: 심볼당 제한의 10%
            calculated_limit = int(per_symbol * 0.1)
            calculation_method = 'per_symbol'
        elif per_account is not None:
            # 2순위: 계정당 제한의 10%
            calculated_limit = int(per_account * 0.1)
            calculation_method = 'per_account'
        else:
            # 3순위: 기본값
            calculated_limit = cls.DEFAULT_MAX_ORDERS
            calculation_method = 'default'

        # 제약 조건 적용
        max_orders_per_side = max(cls.MIN_LIMIT, min(calculated_limit, cls.MAX_CAP))

        # STOP 주문 제한 (고정 50:50 할당)
        # 엣지 케이스 보호: max_orders_per_side=1 시 STOP 우선 정책
        if max_orders_per_side == 1:
            max_stop_orders_per_side = 1  # STOP 우선 (LIMIT은 0개)
        else:
            # 50:50 분할: STOP = 절반, LIMIT = 나머지
            max_stop_orders_per_side = max_orders_per_side // 2

            # 거래소 조건부 제한 적용
            if conditional_limit is not None:
                max_stop_orders_per_side = min(max_stop_orders_per_side, conditional_limit)

        # Side별 제한을 총 허용량으로 변환 (Buy + Sell)
        max_orders = max_orders_per_side * 2
        max_stop_orders = max_stop_orders_per_side * 2

        return {
            'max_orders': max_orders,
            'max_orders_per_side': max_orders_per_side,
            'max_stop_orders': max_stop_orders,
            'max_stop_orders_per_side': max_stop_orders_per_side,
            # max_limit는 호출자가 계산: max_orders_per_side - max_stop_orders_per_side
            'per_symbol_limit': per_symbol,
            'per_account_limit': per_account,
            'calculation_method': calculation_method,
            'exchange': exchange_upper,
            'market_type': market_type_normalized
        }

    @classmethod
    def get_raw_limits(cls, exchange: str, market_type: str) -> dict:
        """거래소의 원본 제한값 반환 (계산하지 않음)

        Args:
            exchange: 거래소 이름
            market_type: 마켓 타입

        Returns:
            dict: {
                'per_symbol': int or None,
                'per_account': int or None,
                'conditional': int or None
            }
        """
        exchange_upper = exchange.upper()
        market_type_normalized = MarketType.normalize(market_type)

        exchange_limits = cls.LIMITS.get(exchange_upper, {})
        return exchange_limits.get(market_type_normalized, {
            'per_symbol': None,
            'per_account': None,
            'conditional': None
        })
