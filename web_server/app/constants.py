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

    # @FEAT:account-management @FEAT:exchange-integration @COMP:config @TYPE:core
    DOMESTIC_EXCHANGES = [UPBIT, BITHUMB]  # KRW 기준 국내 거래소 (잔고 USDT 변환 시 사용)

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

    # @FEAT:account-management @FEAT:exchange-integration @COMP:config @TYPE:core
    @classmethod
    def is_domestic(cls, exchange: str) -> bool:
        """
        국내 거래소 여부를 확인합니다.

        KRW 기준으로 거래하는 국내 거래소(UPBIT, BITHUMB)인지 확인합니다.
        이 메서드는 국내 거래소 KRW 잔고를 USDT로 변환할 때 사용됩니다.

        Args:
            exchange: 거래소 이름 (대소문자 무관)

        Returns:
            bool: 국내 거래소이면 True, 해외 거래소이면 False

        Examples:
            >>> Exchange.is_domestic('UPBIT')
            True
            >>> Exchange.is_domestic('upbit')  # 소문자도 처리
            True
            >>> Exchange.is_domestic('BITHUMB')
            True
            >>> Exchange.is_domestic('BINANCE')
            False
            >>> Exchange.is_domestic(None)
            False
            >>> Exchange.is_domestic('')
            False

        Note:
            국내 거래소 추가 시 DOMESTIC_EXCHANGES 리스트에 추가 필요
            (예: COINONE 추가 시 DOMESTIC_EXCHANGES = [UPBIT, BITHUMB, COINONE])
        """
        if not exchange:
            return False

        exchange_normalized = cls.normalize(exchange)
        return exchange_normalized in cls.DOMESTIC_EXCHANGES

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

    # @FEAT:webhook-batch-queue @COMP:config @TYPE:core
    # Individual Commit Pattern routing groups (Phase 1)
    QUEUED_TYPES = ['LIMIT', 'STOP_LIMIT', 'STOP_MARKET']  # Route to PendingOrder queue
    DIRECT_TYPES = ['MARKET', 'CANCEL_ALL_ORDER']  # Execute immediately on exchange

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

    @staticmethod
    def classify_priority(order_type: str) -> str:
        """배치주문 우선순위 분류

        @FEAT:immediate-order-execution @COMP:config @TYPE:core

        배치 주문 처리 시 즉시 실행 여부를 결정하는 우선순위를 반환합니다.

        비즈니스 로직:
        - 'high' (즉시 실행): CANCEL(취소), MARKET(시장가), STOP_MARKET(손절매)
          → 시장 상황에 민감하며 지연 시 손실 가능성 높음
        - 'low' (지연 실행 가능): LIMIT(지정가), STOP_LIMIT(조건부지정가)
          → 대기 가능하며 배치 처리로 효율성 제고

        Args:
            order_type (str): 주문 타입 (CANCEL, MARKET, LIMIT, STOP_LIMIT, STOP_MARKET 등)

        Returns:
            str: 'high' (즉시 실행 우선) 또는 'low' (지연 실행 가능)

        Examples:
            >>> OrderType.classify_priority('MARKET')
            'high'
            >>> OrderType.classify_priority('CANCEL')
            'high'
            >>> OrderType.classify_priority('STOP_MARKET')
            'high'
            >>> OrderType.classify_priority('LIMIT')
            'low'
            >>> OrderType.classify_priority('STOP_LIMIT')
            'low'

        Notes:
            - None 또는 빈 문자열 입력: 'low' 반환 (안전한 기본값)
            - 유효하지 않은 order_type: 'low' 반환 (조용히 처리, 로그 없음)
            - Phase 2: webhook 우선순위 큐 분류에 활용 예정
        """
        if not order_type:
            return 'low'

        high_priority = {OrderType.CANCEL, OrderType.MARKET, OrderType.STOP_MARKET}
        normalized_type = order_type.upper()
        return 'high' if normalized_type in high_priority else 'low'


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
    PENDING = 'PENDING'              # @DATA:OrderStatus.PENDING - DB-first 패턴 (Phase 2: 2025-10-30)
    CANCELLING = 'CANCELLING'        # @FEAT:cancel-order-db-first @COMP:constant @TYPE:core
                                     # @DATA:OrderStatus.CANCELLING - Pre-exchange API call state (order cancellation)
    NEW = 'NEW'                      # 신규 주문
    OPEN = 'OPEN'                    # 미체결
    PARTIALLY_FILLED = 'PARTIALLY_FILLED'  # 부분 체결
    FILLED = 'FILLED'                # 완전 체결
    CANCELLED = 'CANCELLED'          # 취소됨
    REJECTED = 'REJECTED'            # 거부됨
    EXPIRED = 'EXPIRED'              # 만료됨
    FAILED = 'FAILED'                # @DATA:OrderStatus.FAILED - 거래소 API 실패 (Phase 2: 2025-10-30)

    # 미체결 상태 그룹 (백그라운드 작업 처리용)
    # Note: PENDING은 get_active_statuses()에서 별도 추가됨
    OPEN_STATUSES = [NEW, OPEN, PARTIALLY_FILLED, CANCELLING]  # @FEAT:cancel-order-db-first
    # 완료 상태 그룹
    CLOSED_STATUSES = [FILLED, CANCELLED, REJECTED, EXPIRED, FAILED]

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
            bool: 미체결 상태이면 True (NEW, OPEN, PARTIALLY_FILLED, CANCELLING)

        Examples:
            >>> OrderStatus.is_open('OPEN')
            True
            >>> OrderStatus.is_open('CANCELLING')
            True
            >>> OrderStatus.is_open('FILLED')
            False

        Notes:
            - CANCELLING: DB-first 주문 취소 패턴의 임시 상태 (백그라운드 작업 대상)
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
            list: 미체결 상태 목록 [NEW, OPEN, PARTIALLY_FILLED, CANCELLING]

        Examples:
            >>> OrderStatus.get_open_statuses()
            ['NEW', 'OPEN', 'PARTIALLY_FILLED', 'CANCELLING']

        Notes:
            - 백그라운드 작업용 활성 미체결 상태
            - PENDING은 get_active_statuses()에서 별도 추가됨
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

    @classmethod
    def get_active_statuses(cls) -> list:
        """백그라운드 작업용 활성 상태 목록 반환 (PENDING 포함)

        활성 상태: 정리, 모니터링, 강제 상태 전환이 필요한 상태
        - PENDING: DB-first 패턴 (거래소 API 호출 대기 중)
        - OPEN, PARTIALLY_FILLED: 미체결 주문

        Returns:
            list: 활성 상태 목록 [PENDING, NEW, OPEN, PARTIALLY_FILLED]

        Examples:
            >>> OrderStatus.get_active_statuses()
            ['PENDING', 'NEW', 'OPEN', 'PARTIALLY_FILLED']

        Notes:
            - PENDING: 120초 초과 시 cleanup job에서 FAILED로 변환
            - 배경 작업 쿼리: OpenOrder.status.in_(OrderStatus.get_active_statuses())
        """
        return [cls.PENDING] + cls.OPEN_STATUSES.copy()

    @classmethod
    def get_open_statuses_for_ui(cls) -> list:
        """UI 표시용 미체결 상태 목록 반환 (PENDING, CANCELLING 제외)

        사용자에게 표시되는 상태: NEW, OPEN, PARTIALLY_FILLED만 표시
        PENDING과 CANCELLING은 임시 상태이므로 사용자에게 숨김

        Returns:
            list: UI용 미체결 상태 목록 [NEW, OPEN, PARTIALLY_FILLED]

        Examples:
            >>> OrderStatus.get_open_statuses_for_ui()
            ['NEW', 'OPEN', 'PARTIALLY_FILLED']

        Notes:
            - API 응답 필터링: orders = OpenOrder.query.filter(status.in_(get_open_statuses_for_ui()))
            - 대시보드: PENDING, CANCELLING 상태 주문은 필터링됨
        """
        return [cls.NEW, cls.OPEN, cls.PARTIALLY_FILLED]


# @FEAT:order-limits @COMP:validation @TYPE:config
# 주문 제한 관련 상수
MAX_ORDERS_PER_SYMBOL_SIDE = 10  # 심볼당 side별 전체 제한 (LIMIT + STOP 합계)
MAX_ORDERS_PER_SYMBOL_TYPE_SIDE = 2  # 심볼당 타입 그룹별 side별 제한

# 주문 타입 그룹 분류
# Purpose: 심볼당 타입 그룹별 주문 제한 관리 (MAX_ORDERS_PER_SYMBOL_TYPE_SIDE 적용)
# - LIMIT 그룹: 일반 지정가 주문 (심볼당 side별 최대 2개)
# - STOP 그룹: 스톱 주문 (심볼당 side별 최대 2개)
# 예시: BTC/USDT buy 방향 - LIMIT 2개 + STOP 2개 = 총 4개 허용
ORDER_TYPE_GROUPS = {
    "LIMIT": ["LIMIT", "LIMIT_MAKER"],
    "STOP": ["STOP", "STOP_LIMIT", "STOP_MARKET"]
}


class BackgroundJobTag:
    """백그라운드 작업 태그 (로그 구분용)

    @FEAT:background-log-tagging @COMP:config @TYPE:core

    각 백그라운드 작업의 로그를 구분하기 위한 태그 상수입니다.
    Format: [TAG_NAME] (대괄호로 감싼 대문자)
    Usage: admin/system 페이지에서 작업별 로그 필터링 용도

    네이밍 규칙:
    - 최대 15자 (괄호 제외)
    - 명확하고 축약된 이름 사용
    - 작업의 핵심 기능을 즉시 알 수 있도록 구성
    """
    PRECISION_CACHE = "[PRECISION_CACHE]"    # Precision 캐시 업데이트 (30초 주기)
    SYMBOL_VALID = "[SYMBOL_VALID]"          # Symbol Validator 갱신 (30초 주기)
    MARKET_INFO = "[MARKET_INFO]"            # MarketInfo 백그라운드 갱신 (30초 주기)
    PRICE_CACHE = "[PRICE_CACHE]"            # 가격 캐시 업데이트 (5초 주기)
    ORDER_UPDATE = "[ORDER_UPDATE]"          # 미체결 주문 상태 업데이트 (29초 주기)
    PNL_CALC = "[PNL_CALC]"                  # 미실현 손익 계산 (29초 주기)
    DAILY_SUMMARY = "[DAILY_SUMMARY]"        # 일일 요약 전송 (매일 09:00)
    PERF_CALC = "[PERF_CALC]"                # 일일 성과 계산 (매일 09:05)
    AUTO_REBAL = "[AUTO_REBAL]"              # 자동 리밸런싱 (매시 17분)
    BALANCE_SYNC = "[BALANCE_SYNC]"          # 계좌 잔고 자동 동기화 (59초 주기)
    TOKEN_REFRESH = "[TOKEN_REFRESH]"        # 증권 OAuth 토큰 갱신 (매시 정각)
    QUEUE_REBAL = "[QUEUE_REBAL]"            # 대기열 재정렬 (1초 주기)
    LOCK_RELEASE = "[LOCK_RELEASE]"          # 오래된 처리 잠금 해제 (5분 주기)
    WS_HEALTH = "[WS_HEALTH]"                # WebSocket 연결 상태 모니터링 (30초 주기)

# @FEAT:background-log-tagging @COMP:config @TYPE:core
# Job ID → Tag 매핑 (admin 페이지 로그 파싱용)
# Purpose: admin/system에서 job_id 파라미터로 로그 필터링 시 사용
# Usage: JOB_TAG_MAP.get(job_id) → BackgroundJobTag or None
# IMPORTANT: 키는 APScheduler Job ID와 정확히 일치해야 함 (app/__init__.py 참조)
# Example: scheduler.add_job(..., id='precision_cache_update', ...) → 키는 'precision_cache_update'
# Validation: grep "id='" app/__init__.py | grep scheduler.add_job
JOB_TAG_MAP = {
    # Infrastructure Services
    'precision_cache_update': BackgroundJobTag.PRECISION_CACHE,       # Line 542 (app/__init__.py)
    'symbol_validator_refresh': BackgroundJobTag.SYMBOL_VALID,        # Line 555
    'refresh_market_info': BackgroundJobTag.MARKET_INFO,              # Line 574
    'update_price_cache': BackgroundJobTag.PRICE_CACHE,               # Line 587

    # Trading Operations
    'update_open_orders': BackgroundJobTag.ORDER_UPDATE,              # Line 598
    'calculate_unrealized_pnl': BackgroundJobTag.PNL_CALC,            # Line 610
    'auto_rebalance_accounts': BackgroundJobTag.AUTO_REBAL,           # Line 654
    'rebalance_order_queue': BackgroundJobTag.QUEUE_REBAL,            # Line 681
    'release_stale_order_locks': BackgroundJobTag.LOCK_RELEASE,       # Line 693

    # Monitoring & Reporting
    'check_websocket_health': BackgroundJobTag.WS_HEALTH,             # Line 705
    'send_daily_summary': BackgroundJobTag.DAILY_SUMMARY,             # Line 623
    'calculate_daily_performance': BackgroundJobTag.PERF_CALC,        # Line 637
    'securities_token_refresh': BackgroundJobTag.TOKEN_REFRESH,       # Line 668
    'sync_account_balances': BackgroundJobTag.BALANCE_SYNC,              # Line 819 (app/__init__.py)
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


# @FEAT:order-status-standardization @COMP:transformer @TYPE:standardization
class StandardOrderStatus:
    """거래소 중립적 표준 주문 상태 상수

    모든 거래소에서 공통으로 사용하는 표준 주문 상태를 정의합니다.
    각 거래소별 상태는 OrderStatusTransformer를 통해 표준 상태로 변환됩니다.

    상태 분류:
    - 활성 상태: PENDING, NEW, OPEN, PARTIALLY_FILLED
    - 최종 상태: FILLED, CANCELLED, REJECTED, EXPIRED, FAILED
    """

    # 활성 상태 (Active Statuses)
    PENDING = 'PENDING'              # 거래소 전송 대기 중
    NEW = 'NEW'                      # 새 주문 (거래소 수신 완료)
    OPEN = 'OPEN'                    # 미체결 상태
    PARTIALLY_FILLED = 'PARTIALLY_FILLED'  # 부분 체결

    # 최종 상태 (Terminal Statuses)
    FILLED = 'FILLED'                # 완전 체결
    CANCELLED = 'CANCELLED'          # 취소됨
    CANCELED = 'CANCELLED'           # 호환성용 (CANCELLED와 동일)
    REJECTED = 'REJECTED'            # 거부됨
    EXPIRED = 'EXPIRED'              # 만료됨
    FAILED = 'FAILED'                # 실패

    # 유효한 모든 상태 목록
    VALID_STATUSES = [
        PENDING, NEW, OPEN, PARTIALLY_FILLED,
        FILLED, CANCELLED, CANCELED, REJECTED, EXPIRED, FAILED
    ]

    # 최종 상태 목록 (더 이상 변하지 않는 상태)
    TERMINAL_STATUSES = [
        FILLED, CANCELLED, REJECTED, EXPIRED, FAILED
    ]

    # 활성 상태 목록 (변경 가능한 상태)
    ACTIVE_STATUSES = [
        PENDING, NEW, OPEN, PARTIALLY_FILLED
    ]

    @classmethod
    def get_all_valid_statuses(cls):
        """유효한 모든 상태 목록 반환

        Returns:
            list: 유효한 상태 문자열 목록
        """
        return cls.VALID_STATUSES.copy()

    @classmethod
    def is_valid(cls, status):
        """유효한 상태인지 확인

        Args:
            status (str): 확인할 상태

        Returns:
            bool: 유효한 상태이면 True

        Examples:
            >>> StandardOrderStatus.is_valid('CANCELLED')
            True
            >>> StandardOrderStatus.is_valid('CANCELED')  # 호환성
            True
            >>> StandardOrderStatus.is_valid('INVALID')
            False
        """
        if not status:
            return False

        # normalize 메서드를 재사용하여 유효성 확인
        return cls.normalize(status) is not None

    @classmethod
    def normalize(cls, status):
        """상태 값을 표준 형식으로 정규화

        Args:
            status (str): 정규화할 상태 값

        Returns:
            str or None: 표준 상태 값, 유효하지 않으면 None

        Examples:
            >>> StandardOrderStatus.normalize('canceled')
            'CANCELLED'
            >>> StandardOrderStatus.normalize('partially-filled')
            'PARTIALLY_FILLED'
            >>> StandardOrderStatus.normalize('INVALID')
            None
        """
        if not status:
            return None

        # 대소문자 정규화 및 공백 제거
        normalized = status.upper().strip()

        # 호환성 매핑 (CANCELED -> CANCELLED)
        compatibility_mapping = {
            'CANCELED': cls.CANCELLED
        }

        # 호환성 처리
        if normalized in compatibility_mapping:
            return compatibility_mapping[normalized]

        # 구분자 정규화 (하이픈 -> 언더스코어)
        normalized = normalized.replace('-', '_')

        # 유효한 상태인지 확인
        return normalized if normalized in cls.VALID_STATUSES else None

    @classmethod
    def get_terminal_statuses(cls):
        """최종 상태 목록 반환

        Returns:
            list: 최종 상태 문자열 목록
        """
        return cls.TERMINAL_STATUSES.copy()

    @classmethod
    def is_terminal(cls, status):
        """최종 상태인지 확인

        Args:
            status (str): 확인할 상태

        Returns:
            bool: 최종 상태이면 True
        """
        if not status:
            return False
        return status in cls.TERMINAL_STATUSES

    @classmethod
    def get_active_statuses(cls):
        """활성 상태 목록 반환

        Returns:
            list: 활성 상태 문자열 목록
        """
        return cls.ACTIVE_STATUSES.copy()

    @classmethod
    def is_active(cls, status):
        """활성 상태인지 확인

        Args:
            status (str): 확인할 상태

        Returns:
            bool: 활성 상태이면 True
        """
        if not status:
            return False
        return status in cls.ACTIVE_STATUSES
