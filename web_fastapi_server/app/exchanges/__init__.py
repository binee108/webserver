"""
Exchange Adapters

비동기 거래소 API 어댑터
"""

import logging
from typing import Dict, Optional

from app.exchanges.base import BaseExchangeAdapter
from app.exchanges.binance import BinanceAdapter
from app.exchanges.bybit import BybitAdapter
from app.exchanges.upbit import UpbitAdapter

logger = logging.getLogger(__name__)

# 거래소 어댑터 싱글톤 인스턴스
_exchange_instances: Dict[str, BaseExchangeAdapter] = {}


def get_exchange_adapter(
    exchange_name: str,
    api_key: Optional[str] = None,
    api_secret: Optional[str] = None,
    **kwargs
) -> BaseExchangeAdapter:
    """
    거래소 어댑터 팩토리 함수 (싱글톤)

    Args:
        exchange_name: 거래소 이름 ("binance", "bybit", "upbit")
        api_key: API Key (없으면 config에서 로드)
        api_secret: API Secret (없으면 config에서 로드)
        **kwargs: 추가 설정 (timeout, max_retries 등)

    Returns:
        거래소 어댑터 인스턴스

    Raises:
        ValueError: 지원하지 않는 거래소
        ValueError: API Key/Secret 없음

    Example:
        >>> adapter = get_exchange_adapter("binance")
        >>> order = await adapter.cancel_order("BTC/USDT", "12345")
    """
    exchange_name = exchange_name.lower()

    # 싱글톤 체크 (이미 생성된 인스턴스)
    if exchange_name in _exchange_instances:
        logger.debug(f"Returning existing {exchange_name} adapter instance")
        return _exchange_instances[exchange_name]

    # API Key/Secret 로드 (파라미터 or config)
    if not api_key or not api_secret:
        from app.config import settings

        if exchange_name == "binance":
            api_key = api_key or settings.BINANCE_API_KEY
            api_secret = api_secret or settings.BINANCE_API_SECRET
        elif exchange_name == "bybit":
            api_key = api_key or settings.BYBIT_API_KEY
            api_secret = api_secret or settings.BYBIT_API_SECRET
        elif exchange_name == "upbit":
            api_key = api_key or settings.UPBIT_API_KEY
            api_secret = api_secret or settings.UPBIT_API_SECRET
        else:
            raise ValueError(f"Unsupported exchange: {exchange_name}")

        # API Key 검증
        if not api_key or not api_secret:
            logger.warning(
                f"{exchange_name.upper()} API credentials not configured. "
                f"Please set {exchange_name.upper()}_API_KEY and "
                f"{exchange_name.upper()}_API_SECRET in .env"
            )
            raise ValueError(
                f"{exchange_name.upper()} API credentials not configured"
            )

    # 어댑터 생성
    logger.info(f"Creating new {exchange_name} adapter instance")

    if exchange_name == "binance":
        adapter = BinanceAdapter(
            api_key=api_key,
            api_secret=api_secret,
            **kwargs
        )
    elif exchange_name == "bybit":
        adapter = BybitAdapter(
            api_key=api_key,
            api_secret=api_secret,
            **kwargs
        )
    elif exchange_name == "upbit":
        adapter = UpbitAdapter(
            api_key=api_key,
            api_secret=api_secret,
            **kwargs
        )
    else:
        raise ValueError(f"Unsupported exchange: {exchange_name}")

    # 싱글톤 저장
    _exchange_instances[exchange_name] = adapter

    return adapter


def clear_exchange_instances():
    """
    모든 거래소 어댑터 인스턴스 정리

    앱 종료 시 호출
    """
    global _exchange_instances

    logger.info("Clearing exchange adapter instances")

    for exchange_name, adapter in _exchange_instances.items():
        logger.debug(f"Closing {exchange_name} adapter")
        # Note: 비동기 close()는 별도로 호출 필요

    _exchange_instances.clear()


__all__ = [
    "BaseExchangeAdapter",
    "BinanceAdapter",
    "BybitAdapter",
    "UpbitAdapter",
    "get_exchange_adapter",
    "clear_exchange_instances"
]
