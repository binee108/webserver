"""
심볼 형식 변환 유틸리티

표준 형식: {coin}/{currency} (예: BTC/USDT, ETH/KRW)
거래소별 변환:
- Binance: BTCUSDT
- Upbit: KRW-BTC
"""

from typing import Tuple, Optional
import re
import logging

logger = logging.getLogger(__name__)


class SymbolFormatError(Exception):
    """심볼 형식 오류"""
    pass


def parse_symbol(symbol: str) -> Tuple[str, str]:
    """
    표준 심볼을 coin/currency로 분리

    Args:
        symbol: 표준 형식 심볼 (예: BTC/USDT)

    Returns:
        (coin, currency) 튜플

    Raises:
        SymbolFormatError: 잘못된 형식

    Examples:
        >>> parse_symbol("BTC/USDT")
        ('BTC', 'USDT')
        >>> parse_symbol("ETH/KRW")
        ('ETH', 'KRW')
    """
    if '/' not in symbol:
        raise SymbolFormatError(
            f"Invalid symbol format: {symbol}. Expected format: COIN/CURRENCY (e.g., BTC/USDT)"
        )

    parts = symbol.split('/')
    if len(parts) != 2:
        raise SymbolFormatError(f"Invalid symbol format: {symbol}")

    coin, currency = parts[0].strip().upper(), parts[1].strip().upper()
    if not coin or not currency:
        raise SymbolFormatError(f"Invalid symbol format: {symbol}")

    return coin, currency


def format_symbol(coin: str, currency: str) -> str:
    """
    coin과 currency를 표준 심볼로 결합

    Args:
        coin: 코인 심볼 (예: BTC)
        currency: 기준 통화 (예: USDT)

    Returns:
        표준 형식 심볼 (예: BTC/USDT)

    Examples:
        >>> format_symbol("BTC", "USDT")
        'BTC/USDT'
        >>> format_symbol("eth", "krw")
        'ETH/KRW'
    """
    return f"{coin.upper()}/{currency.upper()}"


def to_binance_format(symbol: str) -> str:
    """
    표준 심볼을 Binance 형식으로 변환

    Args:
        symbol: 표준 형식 심볼 (예: BTC/USDT)

    Returns:
        Binance 형식 심볼 (예: BTCUSDT)

    Examples:
        >>> to_binance_format("BTC/USDT")
        'BTCUSDT'
        >>> to_binance_format("ETH/BTC")
        'ETHBTC'
    """
    coin, currency = parse_symbol(symbol)
    return f"{coin}{currency}"


def to_upbit_format(symbol: str) -> str:
    """
    표준 심볼을 Upbit 형식으로 변환

    Args:
        symbol: 표준 형식 심볼 (예: BTC/KRW)

    Returns:
        Upbit 형식 심볼 (예: KRW-BTC)

    Raises:
        SymbolFormatError: KRW 마켓이 아닌 경우

    Examples:
        >>> to_upbit_format("BTC/KRW")
        'KRW-BTC'
        >>> to_upbit_format("ETH/KRW")
        'KRW-ETH'
    """
    coin, currency = parse_symbol(symbol)
    if currency != 'KRW':
        raise SymbolFormatError(f"Upbit only supports KRW market. Got: {symbol}")
    return f"{currency}-{coin}"


def from_binance_format(binance_symbol: str, default_currency: str = 'USDT') -> str:
    """
    Binance 형식 심볼을 표준 형식으로 변환

    Args:
        binance_symbol: Binance 형식 심볼 (예: BTCUSDT)
        default_currency: 기본 기준 통화 (추론 실패 시 사용)

    Returns:
        표준 형식 심볼 (예: BTC/USDT)

    Examples:
        >>> from_binance_format("BTCUSDT")
        'BTC/USDT'
        >>> from_binance_format("ETHBTC")
        'ETH/BTC'
        >>> from_binance_format("BNBBUSD")
        'BNB/BUSD'
    """
    binance_symbol = binance_symbol.upper()

    # 일반적인 quote currency 목록 (우선순위 순)
    quote_currencies = ['USDT', 'BUSD', 'USDC', 'BTC', 'ETH', 'BNB']

    # quote currency 추론
    detected_currency = None
    for currency in quote_currencies:
        if binance_symbol.endswith(currency):
            detected_currency = currency
            break

    if detected_currency:
        coin = binance_symbol[:-len(detected_currency)]
        return format_symbol(coin, detected_currency)
    else:
        # 추론 실패 시 기본 통화 사용
        logger.warning(
            f"Cannot infer quote currency from {binance_symbol}, using default: {default_currency}"
        )
        coin = binance_symbol[:-len(default_currency)]
        return format_symbol(coin, default_currency)


def from_upbit_format(upbit_symbol: str) -> str:
    """
    Upbit 형식 심볼을 표준 형식으로 변환

    Args:
        upbit_symbol: Upbit 형식 심볼 (예: KRW-BTC)

    Returns:
        표준 형식 심볼 (예: BTC/KRW)

    Raises:
        SymbolFormatError: 잘못된 Upbit 형식

    Examples:
        >>> from_upbit_format("KRW-BTC")
        'BTC/KRW'
        >>> from_upbit_format("KRW-ETH")
        'ETH/KRW'
    """
    parts = upbit_symbol.split('-')
    if len(parts) != 2:
        raise SymbolFormatError(f"Invalid Upbit format: {upbit_symbol}. Expected: CURRENCY-COIN")

    currency, coin = parts
    return format_symbol(coin, currency)


def normalize_symbol_from_db(symbol: str, exchange: str = None) -> str:
    """
    DB에서 읽은 심볼을 표준 형식으로 변환 (하위 호환성)

    Args:
        symbol: DB 심볼 (레거시 또는 표준 형식)
        exchange: 거래소 이름 (추론 힌트)

    Returns:
        표준 형식 심볼

    Examples:
        >>> normalize_symbol_from_db("BTC/USDT")
        'BTC/USDT'
        >>> normalize_symbol_from_db("BTCUSDT", "BINANCE")
        'BTC/USDT'
        >>> normalize_symbol_from_db("KRW-BTC", "UPBIT")
        'BTC/KRW'
    """
    # 이미 표준 형식인 경우
    if '/' in symbol:
        return symbol

    # 레거시 형식 감지 및 변환
    if '-' in symbol:
        # Upbit 형식 (KRW-BTC)
        return from_upbit_format(symbol)
    else:
        # Binance 형식으로 간주 (BTCUSDT)
        return from_binance_format(symbol)


def is_standard_format(symbol: str, market_type: Optional[str] = None) -> bool:
    """
    심볼이 표준 형식인지 확인 (market_type에 따라 검증 방식 변경)

    Args:
        symbol: 확인할 심볼
        market_type: 마켓 타입 (SPOT, FUTURES, DOMESTIC_STOCK, OVERSEAS_STOCK 등)

    Returns:
        표준 형식 여부

    Examples:
        >>> is_standard_format("BTC/USDT", "SPOT")
        True
        >>> is_standard_format("BTCUSDT", "SPOT")
        False
        >>> is_standard_format("005930", "DOMESTIC_STOCK")
        True
        >>> is_standard_format("AAPL", "OVERSEAS_STOCK")
        True
    """
    if not symbol:
        return False

    # market_type이 지정되지 않았거나 crypto 타입인 경우
    if not market_type or market_type in ['SPOT', 'FUTURES']:
        # 크립토 표준 형식: COIN/CURRENCY
        return '/' in symbol and len(symbol.split('/')) == 2

    # 증권 타입인 경우
    elif market_type in ['DOMESTIC_STOCK', 'OVERSEAS_STOCK',
                        'DOMESTIC_FUTUREOPTION', 'OVERSEAS_FUTUREOPTION']:
        # 증권은 다양한 형식 허용
        return _is_valid_securities_symbol(symbol, market_type)

    # 알 수 없는 market_type - crypto 형식으로 검증
    return '/' in symbol and len(symbol.split('/')) == 2


def _is_valid_securities_symbol(symbol: str, market_type: str) -> bool:
    """
    증권 심볼 형식 검증 (Permissive)

    심볼 형식은 각 거래소 API에서 최종 검증하므로, 여기서는 기본적인 안전성만 체크합니다.
    - 길이 제한 (ReDoS 방지)
    - 허용 문자: 영문, 숫자, 마침표(.), 하이픈(-), 언더스코어(_)
    - 특수문자 금지 (SQL Injection, XSS 방지)

    Args:
        symbol: 심볼
        market_type: 증권 마켓 타입

    Returns:
        유효성 여부

    Examples:
        >>> _is_valid_securities_symbol("005930", "DOMESTIC_STOCK")
        True
        >>> _is_valid_securities_symbol("KR005930", "DOMESTIC_STOCK")
        True
        >>> _is_valid_securities_symbol("123456A", "DOMESTIC_STOCK")
        True
        >>> _is_valid_securities_symbol("BRK.A", "OVERSEAS_STOCK")
        True
        >>> _is_valid_securities_symbol("9988", "OVERSEAS_STOCK")
        True
        >>> _is_valid_securities_symbol("'; DROP TABLE--", "DOMESTIC_STOCK")
        False  # SQL Injection attempt blocked
    """
    # 🔒 ReDoS 방지: 길이 제한
    if not symbol or len(symbol) > 30:  # 20 → 30 (longer symbols allowed)
        return False

    # ✅ 허용 문자: 영문, 숫자, 마침표(.), 하이픈(-), 언더스코어(_)
    # 특수문자 금지 (보안: SQL Injection, XSS 방지)
    symbol_upper = symbol.upper()

    # Permissive pattern: alphanumeric + dot + hyphen + underscore
    if not re.match(r'^[A-Z0-9._-]+$', symbol_upper):
        return False

    # 추가 안전성 체크: 순수 특수문자만으로 구성된 심볼 거부
    if re.match(r'^[._-]+$', symbol_upper):
        return False

    return True
