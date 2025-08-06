"""
공통 유틸리티 함수들
"""

from typing import Any
from decimal import Decimal

def to_decimal(value: Any) -> Decimal:
    """값을 Decimal로 안전하게 변환"""
    if value is None:
        return Decimal('0')
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))

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

def normalize_webhook_data(webhook_data: dict) -> dict:
    """웹훅 데이터의 필드명을 표준화 (대소문자 구별 없이 처리)"""
    normalized = {}
    
    # 필드명 매핑 (소문자 키 -> 표준 키)
    field_mapping = {
        'group_name': 'group_name',
        'exchange': 'exchange',
        'platform': 'exchange',  # platform을 exchange로 매핑
        'market': 'market',
        'currency': 'currency',
        'symbol': 'symbol',
        'ordertype': 'orderType',
        'order_type': 'orderType',
        'side': 'side',
        'price': 'price',
        'qty_per': 'qty_per'
    }
    
    # 원본 데이터를 소문자 키로 변환하여 매핑
    lower_data = {k.lower(): v for k, v in webhook_data.items()}
    
    # 표준 필드명으로 변환
    for lower_key, standard_key in field_mapping.items():
        if lower_key in lower_data:
            normalized[standard_key] = lower_data[lower_key]
    
    # 매핑되지 않은 다른 필드들도 그대로 포함
    for key, value in webhook_data.items():
        if key.lower() not in field_mapping:
            normalized[key] = value
    
    # 값들을 내부 로직에 맞게 표준화
    if 'orderType' in normalized and isinstance(normalized['orderType'], str):
        normalized['orderType'] = normalized['orderType'].upper()  # 대문자로 표준화 (MARKET, LIMIT 등)
    
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
        normalized['exchange'] = normalized['exchange'].upper()  # 대문자로 표준화 (BINANCE, BYBIT 등)
    
    if 'market' in normalized and isinstance(normalized['market'], str):
        normalized['market'] = normalized['market'].upper()  # 대문자로 표준화 (SPOT, FUTURE 등)
    
    if 'currency' in normalized and isinstance(normalized['currency'], str):
        normalized['currency'] = normalized['currency'].upper()  # 대문자로 표준화 (USDT, KRW 등)
    
    return normalized 