# @FEAT:webhook-order @COMP:util @TYPE:helper
"""
공통 유틸리티 함수들
"""

import logging
from typing import Any
from decimal import Decimal
from app.constants import MarketType, Exchange, OrderType
from app.utils.symbol_utils import is_standard_format

logger = logging.getLogger(__name__)

# 🔁 DRY: 증권 심볼 에러 메시지 (단일 소스)
_SECURITIES_SYMBOL_ERROR_MESSAGES = {
    'DOMESTIC_STOCK': "국내주식 심볼 형식이 올바르지 않습니다 (예: 005930, KR005930, 123456A). 영문, 숫자, 마침표(.), 하이픈(-), 언더스코어(_)만 사용 가능합니다.",
    'OVERSEAS_STOCK': "해외주식 심볼 형식이 올바르지 않습니다 (예: AAPL, BRK.A, 9988). 영문, 숫자, 마침표(.), 하이픈(-), 언더스코어(_)만 사용 가능합니다.",
    'DOMESTIC_FUTUREOPTION': "국내선물옵션 심볼 형식이 올바르지 않습니다 (예: 101TC000, KR4101C3000). 영문, 숫자, 마침표(.), 하이픈(-), 언더스코어(_)만 사용 가능합니다.",
    'OVERSEAS_FUTUREOPTION': "해외선물옵션 심볼 형식이 올바르지 않습니다 (예: ESZ4, NQH5, CL-DEC24). 영문, 숫자, 마침표(.), 하이픈(-), 언더스코어(_)만 사용 가능합니다.",
}

# @FEAT:trading @COMP:util @TYPE:helper
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

# @FEAT:trading @COMP:util @TYPE:helper
def decimal_to_float(value: Decimal) -> float:
    """Decimal을 float로 변환 (거래소 API 호출용)"""
    return float(value)


# @FEAT:position-tracking @COMP:util @TYPE:helper
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


# @FEAT:webhook-order @COMP:util @TYPE:helper
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

# @FEAT:webhook-order @COMP:validation @TYPE:validation
# @REFACTOR:2025-11-03 - Removed batch_mode field assignment (Phase 2)
def normalize_webhook_data(webhook_data: dict) -> dict:
    """
    웹훅 데이터의 필드명을 표준화합니다 (order_type은 정확한 필드명만 허용).

    배치 모드 감지:
        'orders' 필드 존재 여부로 배치 모드를 판단합니다.
        @PRINCIPLE: batch_mode 파생 필드를 생성하지 않습니다 (단일 소스 원칙)
        @REFACTOR:2025-11-03 - batch_mode 필드 할당 제거 (Phase 2)

    Args:
        webhook_data: 웹훅 입력 데이터

    Returns:
        정규화된 데이터 (batch_mode 파생 필드 없음, 'orders' 필드로만 배치 감지)
    """
    normalized = {}

    # 필드명 매핑 (소문자 키 -> 표준 키)
    # order_type은 제외 (정확한 필드명만 허용)
    field_mapping = {
        'group_name': 'group_name',
        # 'exchange': 'exchange',  # ❌ 제거: Account.exchange에서 자동 결정
        # 'platform': 'exchange',  # ❌ 제거: Account.exchange에서 자동 결정
        # 'market_type': 'market_type',  # ❌ 제거: Strategy.market_type에서 자동 결정
        'currency': 'currency',
        'symbol': 'symbol',
        'side': 'side',
        'price': 'price',
        'stop_price': 'stop_price',  # STOP 주문용 Stop 가격
        'stopprice': 'stop_price',   # 대안 필드명
        'qty_per': 'qty_per',
        'qty': 'qty',                # 🆕 절대 수량 (qty_per 대안)
        'token': 'token',
        'user_token': 'token',
        'params': 'params'           # 🆕 증권/선물옵션용 추가 파라미터
    }

    # 원본 데이터를 소문자 키로 변환하여 매핑
    lower_data = {k.lower(): v for k, v in webhook_data.items()}

    # 표준 필드명으로 변환
    for lower_key, standard_key in field_mapping.items():
        if lower_key in lower_data:
            normalized[standard_key] = lower_data[lower_key]

    # ✅ 심볼 포맷 검증 (market_type에 따라 다른 검증 방식 적용)
    if 'symbol' in normalized and isinstance(normalized['symbol'], str):
        symbol_input = normalized['symbol']
        # market_type 추론 (아직 정규화되지 않은 상태에서)
        detected_market_type = normalized.get('market_type')

        if not is_standard_format(symbol_input, detected_market_type):
            # 크립토 마켓인 경우 자동 교정 제안
            if not detected_market_type or detected_market_type in ['SPOT', 'FUTURES']:
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
            else:
                # 증권 마켓인 경우 market_type별 안내
                error_msg = _SECURITIES_SYMBOL_ERROR_MESSAGES.get(
                    detected_market_type,
                    f"잘못된 심볼 포맷입니다: '{symbol_input}'"
                )
                raise ValueError(error_msg)

    # order_type은 정확한 필드명만 허용
    if 'order_type' in webhook_data:
        normalized['order_type'] = webhook_data['order_type']

    # ✅ CANCEL_ALL_ORDER 필수 필드 검증 (symbol 필수, side 선택적)
    if normalized.get('order_type') == 'CANCEL_ALL_ORDER':
        if not normalized.get('symbol'):
            raise ValueError("CANCEL_ALL_ORDER에는 symbol이 필수입니다")
        # side는 선택적 (BUY/SELL 방향 필터, 없으면 모든 주문 취소)
        # 필터링: strategy_account_id (전략 격리) + symbol (필수) + side (선택적)

    # 🆕 배치 주문 감지 및 처리 (새로운 포맷)
    # @REFACTOR:2025-11-03 - Batch mode detected via 'orders' field only (no batch_mode assignment)
    if 'orders' in webhook_data and isinstance(webhook_data['orders'], list):
        normalized['orders'] = []

        # 상위 레벨 공통 필드 (폴백 지원): symbol만
        # 나머지 필드(side, price, stop_price, qty_per)는 각 주문에 명시 필수
        common_symbol = webhook_data.get('symbol')

        # 폴백 정책 변경 감지 (기존 사용자 경고)
        deprecated_fallback_fields = []
        for field in ['side', 'price', 'stop_price', 'qty_per']:
            if field in webhook_data:
                deprecated_fallback_fields.append(field)

        if deprecated_fallback_fields:
            logger.warning(
                f"⚠️ 배치 주문 폴백 정책 변경 (2025-10-08): "
                f"상위 레벨 {', '.join(deprecated_fallback_fields)} 필드는 더 이상 폴백되지 않습니다. "
                f"각 주문에 명시해야 합니다."
            )

        for idx, order in enumerate(webhook_data['orders']):
            if isinstance(order, dict):
                # 개별 주문의 심볼 (order 레벨 우선, 없으면 상위 레벨 사용)
                order_symbol = order.get('symbol') or common_symbol

                # ✅ 배치 주문 내 심볼도 검증 (market_type 인식)
                detected_market_type = normalized.get('market_type')
                if order_symbol and not is_standard_format(order_symbol, detected_market_type):
                    if not detected_market_type or detected_market_type in ['SPOT', 'FUTURES']:
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
                    else:
                        error_msg = _SECURITIES_SYMBOL_ERROR_MESSAGES.get(
                            detected_market_type,
                            f"배치 주문 {idx + 1}번째 심볼 포맷 오류: '{order_symbol}'"
                        )
                        raise ValueError(error_msg)

                # 개별 주문 데이터 구성 (order 레벨에서만 가져옴, 폴백 없음)
                batch_order = {
                    'symbol': order_symbol,
                    'order_type': order.get('order_type'),  # 필수 (order 레벨에서만)
                }

                # side, price, stop_price, qty_per는 각 주문에서만 가져옴 (폴백 없음)
                if 'side' in order:
                    batch_order['side'] = order['side']

                if 'price' in order:
                    batch_order['price'] = order['price']

                if 'stop_price' in order:
                    batch_order['stop_price'] = order['stop_price']

                if 'qty_per' in order:
                    batch_order['qty_per'] = to_decimal(order['qty_per'])

                # 🆕 qty 지원 (절대 수량)
                if 'qty' in order:
                    batch_order['qty'] = to_decimal(order['qty'])

                # params 지원 (확장 파라미터)
                if 'params' in order:
                    batch_order['params'] = order['params']

                # order_type 검증 (필수)
                if not batch_order.get('order_type'):
                    raise ValueError(
                        f"배치 주문 {idx + 1}번째에 order_type이 필요합니다. "
                        f"사용 가능한 타입: MARKET, LIMIT, STOP_MARKET, STOP_LIMIT, CANCEL_ALL_ORDER"
                    )

                # side 검증 (CANCEL_ALL_ORDER 제외 필수)
                order_type = batch_order.get('order_type')
                if order_type not in ['CANCEL_ALL_ORDER', 'CANCEL'] and not batch_order.get('side'):
                    raise ValueError(
                        f"배치 주문 {idx + 1}번째에 side가 필요합니다. "
                        f"폴백 정책 변경 (2025-10-08): side는 각 주문에 명시해야 합니다."
                    )

                # 🆕 qty 또는 qty_per 검증 (CANCEL_ALL_ORDER, CANCEL 제외 필수)
                if order_type not in ['CANCEL_ALL_ORDER', 'CANCEL'] and not batch_order.get('qty_per') and not batch_order.get('qty'):
                    raise ValueError(
                        f"배치 주문 {idx + 1}번째에 qty 또는 qty_per 중 하나가 필요합니다. "
                        f"폴백 정책 변경 (2025-10-08): 각 주문에 명시해야 합니다."
                    )

                normalized['orders'].append(batch_order)

        # 배치 주문이 감지되면 기본 price, qty_per, side 제거 (혼동 방지)
        normalized.pop('price', None)
        normalized.pop('qty_per', None)
        normalized.pop('side', None)

    # 매핑되지 않은 다른 필드들도 그대로 포함 (order_type 관련 및 orders 제외)
    for key, value in webhook_data.items():
        if (key.lower() not in field_mapping and
            key != 'order_type' and
            key.lower() not in ['ordertype', 'orderType'] and
            key != 'orders'):
            normalized[key] = value

    # @REFACTOR:2025-11-03 - Batch mode field assignment removed (Phase 2)
    # Detection is now exclusively via 'orders' field presence (single source of truth)

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

    # ❌ 제거: exchange와 market_type은 더 이상 웹훅에서 받지 않음
    # if 'exchange' in normalized and isinstance(normalized['exchange'], str):
    #     normalized['exchange'] = Exchange.normalize(normalized['exchange'])
    # if 'market_type' in normalized and isinstance(normalized['market_type'], str):
    #     normalized['market_type'] = MarketType.normalize(normalized['market_type'])

    if 'currency' in normalized and isinstance(normalized['currency'], str):
        normalized['currency'] = normalized['currency'].upper()  # 대문자로 표준화 (USDT, KRW 등)

    return normalized
