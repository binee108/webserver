"""
Binance API 상수 정의

API 엔드포인트, 에러 코드, Rate Limit 등 Binance 관련 상수들을 정의합니다.
"""

# API 기본 URL
SPOT_BASE_URL = "https://api.binance.com"
FUTURES_BASE_URL = "https://fapi.binance.com"

# Testnet URL  
SPOT_TESTNET_URL = "https://testnet.binance.vision"
FUTURES_TESTNET_URL = "https://testnet.binancefuture.com"

# Rate Limits
SPOT_RATE_LIMIT = 1200      # 분당 요청 수
SPOT_WEIGHT_LIMIT = 6000    # 분당 Weight

FUTURES_RATE_LIMIT = 2400   # 분당 요청 수  
FUTURES_WEIGHT_LIMIT = 2400 # 분당 Weight

# API 엔드포인트
class SpotEndpoints:
    """Spot API 엔드포인트"""
    
    # Public endpoints
    EXCHANGE_INFO = "/api/v3/exchangeInfo"
    TICKER_24HR = "/api/v3/ticker/24hr" 
    TICKER_PRICE = "/api/v3/ticker/price"
    ORDER_BOOK = "/api/v3/depth"
    KLINES = "/api/v3/klines"
    
    # Private endpoints
    ACCOUNT = "/api/v3/account"
    ORDER = "/api/v3/order"
    OPEN_ORDERS = "/api/v3/openOrders"
    ALL_ORDERS = "/api/v3/allOrders"


class FuturesEndpoints:
    """Futures API 엔드포인트"""
    
    # Public endpoints  
    EXCHANGE_INFO = "/fapi/v1/exchangeInfo"
    TICKER_24HR = "/fapi/v1/ticker/24hr"
    TICKER_PRICE = "/fapi/v1/ticker/price"
    ORDER_BOOK = "/fapi/v1/depth"
    KLINES = "/fapi/v1/klines"
    
    # Private endpoints
    ACCOUNT = "/fapi/v2/account"
    BALANCE = "/fapi/v2/balance"
    POSITION_RISK = "/fapi/v2/positionRisk"
    ORDER = "/fapi/v1/order"
    OPEN_ORDERS = "/fapi/v1/openOrders"
    ALL_ORDERS = "/fapi/v1/allOrders"


# 주문 타입
class OrderType:
    MARKET = "MARKET"
    LIMIT = "LIMIT" 
    STOP_LOSS = "STOP_LOSS"
    STOP_LOSS_LIMIT = "STOP_LOSS_LIMIT"
    TAKE_PROFIT = "TAKE_PROFIT"
    TAKE_PROFIT_LIMIT = "TAKE_PROFIT_LIMIT"
    LIMIT_MAKER = "LIMIT_MAKER"


# 주문 사이드
class OrderSide:
    BUY = "BUY"
    SELL = "SELL"


# 주문 상태
class OrderStatus:
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED" 
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    PENDING_CANCEL = "PENDING_CANCEL"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


# Time in Force
class TimeInForce:
    GTC = "GTC"  # Good Till Canceled
    IOC = "IOC"  # Immediate or Cancel
    FOK = "FOK"  # Fill or Kill


# 에러 코드
class ErrorCodes:
    """Binance API 에러 코드"""
    
    # 일반 에러
    UNKNOWN = -1000
    DISCONNECTED = -1001
    UNAUTHORIZED = -1002
    TOO_MANY_REQUESTS = -1003
    UNEXPECTED_RESP = -1006
    TIMEOUT = -1007
    
    # 파라미터 에러  
    ILLEGAL_CHARS = -1100
    TOO_MANY_PARAMETERS = -1101
    MANDATORY_PARAM_EMPTY = -1102
    UNKNOWN_PARAM = -1103
    UNREAD_PARAMETERS = -1104
    PARAM_EMPTY = -1105
    PARAM_NOT_REQUIRED = -1106
    
    # 권한 에러
    INVALID_TIMESTAMP = -1021
    INVALID_SIGNATURE = -1022
    
    # 주문 관련 에러
    NEW_ORDER_REJECTED = -2010
    CANCEL_REJECTED = -2011
    NO_SUCH_ORDER = -2013
    BAD_API_ID = -2014
    DUPLICATE_ORDER = -2015
    
    # 잔액 부족
    INSUFFICIENT_BALANCE = -2019
    
    # Rate Limit
    RATE_LIMIT_EXCEEDED = -1015


# Weight 값 (API 호출 비용)
class Weights:
    """API 엔드포인트별 Weight"""
    
    # Spot
    SPOT_ACCOUNT = 10
    SPOT_ORDER = 1
    SPOT_OPEN_ORDERS = 3
    SPOT_CANCEL_ORDER = 1
    SPOT_EXCHANGE_INFO = 10
    SPOT_TICKER_24HR = 1  # 심볼당
    
    # Futures
    FUTURES_ACCOUNT = 5
    FUTURES_ORDER = 1
    FUTURES_OPEN_ORDERS = 1
    FUTURES_CANCEL_ORDER = 1
    FUTURES_EXCHANGE_INFO = 1
    FUTURES_TICKER_24HR = 1  # 심볼당