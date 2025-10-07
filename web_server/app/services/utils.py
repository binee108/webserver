"""
공통 유틸리티 함수들
"""

from typing import Any
from decimal import Decimal
from app.constants import MarketType, Exchange, OrderType

def to_decimal(value: Any, default: Decimal = Decimal('0')) -> Decimal:
    """값을 Decimal로 안전하게 변환

    Args:
        value: 변환할 값 (int, float, str, Decimal 등)
        default: 변환 실패 시 기본값 (기본값: Decimal('0'))

    Returns:
        Decimal 타입의 값

    Examples:
        >>> to_decimal(100)
        Decimal('100')
        >>> to_decimal('123.45')
        Decimal('123.45')
        >>> to_decimal(None)
        Decimal('0')
        >>> to_decimal('invalid', Decimal('999'))
        Decimal('999')
    """
    if value is None or value == '':
        return default
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (Exception, ValueError, TypeError):
        return default

def decimal_to_float(value: Decimal) -> float:
    """Decimal을 float로 변환 (거래소 API 호출용)"""
    return float(value)


def calculate_is_entry(current_position_qty: Decimal, side: str) -> bool:
    """
    거래가 진입인지 청산인지 판단하는 공통 헬퍼 함수

    Args:
        current_position_qty: 현재 포지션 수량 (양수: 롱, 음수: 숏, 0: 포지션 없음)
        side: 거래 방향 ('BUY', 'SELL')

    Returns:
        bool: True=진입, False=청산
    """
    if current_position_qty == 0:
        # 포지션이 없는 상태에서는 모든 거래가 진입
        return True
    elif current_position_qty > 0:
        # 롱 포지션 보유 중
        if side.upper() == 'BUY':
            # 같은 방향 -> 추가 진입
            return True
        else:  # SELL
            # 반대 방향 -> 청산
            return False
    else:  # current_position_qty < 0
        # 숏 포지션 보유 중
        if side.upper() == 'SELL':
            # 같은 방향 -> 추가 진입
            return True
        else:  # BUY
            # 반대 방향 -> 청산
            return False


def _suggest_symbol_format(symbol_input: str) -> str:
    """
    잘못된 심볼 포맷을 올바른 형식으로 교정 제안

    Args:
        symbol_input: 잘못된 형식의 심볼 (예: BTCUSDT, KRW-BTC)

    Returns:
        교정된 심볼 형식 (예: BTC/USDT, BTC/KRW) 또는 None

    Examples:
        >>> _suggest_symbol_format("BTCUSDT")
        'BTC/USDT'
        >>> _suggest_symbol_format("KRW-BTC")
        'BTC/KRW'
        >>> _suggest_symbol_format("ETHBTC")
        'ETH/BTC'
    """
    symbol_upper = symbol_input.upper()

    # Upbit 형식 감지 (KRW-BTC, USDT-ETH)
    if '-' in symbol_upper:
        parts = symbol_upper.split('-')
        if len(parts) == 2:
            currency, coin = parts
            return f"{coin}/{currency}"  # BTC/KRW

    # Binance 형식 추론 (BTCUSDT, ETHBTC)
    common_currencies = ['USDT', 'BUSD', 'USDC', 'KRW', 'BTC', 'ETH', 'BNB', 'DAI']
    for currency in common_currencies:
        if symbol_upper.endswith(currency):
            coin = symbol_upper[:-len(currency)]
            if coin:  # coin 부분이 비어있지 않은지 확인
                return f"{coin}/{currency}"

    # 추론 실패
    return None

def normalize_webhook_data(webhook_data: dict) -> dict:
    """웹훅 데이터의 필드명을 표준화 (order_type은 정확한 필드명만 허용)"""
    normalized = {}

    # 필드명 매핑 (소문자 키 -> 표준 키)
    # order_type은 제외 (정확한 필드명만 허용)
    field_mapping = {
        'group_name': 'group_name',
        'exchange': 'exchange',
        'platform': 'exchange',  # platform을 exchange로 매핑
        'market_type': 'market_type',
        'currency': 'currency',
        'symbol': 'symbol',
        'side': 'side',
        'price': 'price',
        'stop_price': 'stop_price',  # STOP 주문용 Stop 가격
        'stopprice': 'stop_price',   # 대안 필드명
        'qty_per': 'qty_per',
        'token': 'token',
        'user_token': 'token'
    }

    # 원본 데이터를 소문자 키로 변환하여 매핑
    lower_data = {k.lower(): v for k, v in webhook_data.items()}

    # 표준 필드명으로 변환
    for lower_key, standard_key in field_mapping.items():
        if lower_key in lower_data:
            normalized[standard_key] = lower_data[lower_key]

    # ✅ 심볼 포맷 검증 (BTCUSDT → BTC/USDT 교정 안내)
    if 'symbol' in normalized and isinstance(normalized['symbol'], str):
        from app.utils.symbol_utils import is_standard_format

        symbol_input = normalized['symbol']
        if not is_standard_format(symbol_input):
            # 자동 교정 제안 생성
            suggested_format = _suggest_symbol_format(symbol_input)

            if suggested_format:
                raise ValueError(
                    f"잘못된 심볼 포맷입니다: '{symbol_input}'. "
                    f"올바른 형식: '{suggested_format}' (COIN/CURRENCY 형식 사용)"
                )
            else:
                raise ValueError(
                    f"잘못된 심볼 포맷입니다: '{symbol_input}'. "
                    f"올바른 형식 예시: 'BTC/USDT', 'ETH/KRW' (슬래시(/) 필수)"
                )
    
    # order_type은 정확한 필드명만 허용
    if 'order_type' in webhook_data:
        normalized['order_type'] = webhook_data['order_type']
    
    # 🆕 배치 주문 감지 및 처리
    if 'orders' in webhook_data and isinstance(webhook_data['orders'], list):
        from app.utils.symbol_utils import is_standard_format

        normalized['batch_mode'] = True
        normalized['orders'] = []

        for idx, order in enumerate(webhook_data['orders']):
            if isinstance(order, dict):
                # 개별 주문의 심볼 추출 (주문 레벨 또는 웹훅 레벨)
                order_symbol = order.get('symbol') or webhook_data.get('symbol')

                # ✅ 배치 주문 내 심볼도 검증
                if order_symbol and not is_standard_format(order_symbol):
                    suggested_format = _suggest_symbol_format(order_symbol)
                    if suggested_format:
                        raise ValueError(
                            f"배치 주문 {idx + 1}번째 심볼 포맷 오류: '{order_symbol}'. "
                            f"올바른 형식: '{suggested_format}' (COIN/CURRENCY 형식 사용)"
                        )
                    else:
                        raise ValueError(
                            f"배치 주문 {idx + 1}번째 심볼 포맷 오류: '{order_symbol}'. "
                            f"올바른 형식 예시: 'BTC/USDT', 'ETH/KRW' (슬래시(/) 필수)"
                        )

                # 개별 주문의 모든 필드를 포함 (웹훅 레벨 값 폴백)
                batch_order = {
                    'symbol': order_symbol,
                    'side': order.get('side') or webhook_data.get('side'),
                    'order_type': order.get('order_type') or webhook_data.get('order_type', 'MARKET'),
                    'price': order.get('price'),
                    'qty_per': to_decimal(order.get('qty_per', 100)),
                }
                # STOP 주문 지원
                if 'stop_price' in order:
                    batch_order['stop_price'] = order.get('stop_price')

                normalized['orders'].append(batch_order)

        # 배치 주문이 감지되면 기본 price, qty_per 제거 (혼동 방지)
        normalized.pop('price', None)
        normalized.pop('qty_per', None)
    else:
        normalized['batch_mode'] = False
    
    # 매핑되지 않은 다른 필드들도 그대로 포함 (order_type 관련 및 orders 제외)
    for key, value in webhook_data.items():
        if (key.lower() not in field_mapping and 
            key != 'order_type' and 
            key.lower() not in ['ordertype', 'orderType'] and
            key != 'orders'):
            normalized[key] = value
    
    # 값들을 내부 로직에 맞게 표준화
    if 'order_type' in normalized and isinstance(normalized['order_type'], str):
        normalized['order_type'] = OrderType.normalize(normalized['order_type'])  # 표준화 (MARKET, LIMIT 등)
    
    if 'side' in normalized and isinstance(normalized['side'], str):
        # side를 BUY/SELL로 표준화
        side_lower = normalized['side'].lower()
        if side_lower in ['buy', 'long']:
            normalized['side'] = 'BUY'
        elif side_lower in ['sell', 'short']:
            normalized['side'] = 'SELL'
        else:
            # 이미 대문자인 경우 그대로 사용
            normalized['side'] = normalized['side'].upper()
    
    if 'exchange' in normalized and isinstance(normalized['exchange'], str):
        normalized['exchange'] = Exchange.normalize(normalized['exchange'])  # 표준화 (BINANCE, BYBIT 등)
    
    if 'market_type' in normalized and isinstance(normalized['market_type'], str):
        normalized['market_type'] = MarketType.normalize(normalized['market_type'])  # 표준 형태로 변환
    
    if 'currency' in normalized and isinstance(normalized['currency'], str):
        normalized['currency'] = normalized['currency'].upper()  # 대문자로 표준화 (USDT, KRW 등)
    
    return normalized
