"""
Order ID ↔ 메타데이터 매핑 캐시

WebSocket이 주문 생성보다 먼저 도착하는 레이스를 완화하기 위한
경량 인메모리 캐시. 주문 ID 기준으로 market_type/symbol/account를 복원한다.
"""

import time
import threading
import logging
from typing import Optional, Dict, Any


logger = logging.getLogger(__name__)


class OrderMappingCache:
    def __init__(self, ttl_seconds: int = 600, max_size: int = 1000):
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
        self._lock = threading.Lock()
        self._cache: Dict[str, Dict[str, Any]] = {}

    def _purge(self):
        now = time.time()
        # TTL 기반 정리
        expired_keys = [k for k, v in self._cache.items() if now - v.get("ts", 0) > self.ttl_seconds]
        for key in expired_keys:
            self._cache.pop(key, None)

        # 최대 크기 초과 시 오래된 항목 제거 (단순 정렬)
        if len(self._cache) > self.max_size:
            # ts 기준 오름차순으로 정렬 후 초과분 제거
            sorted_items = sorted(self._cache.items(), key=lambda item: item[1].get("ts", 0))
            for key, _ in sorted_items[: len(self._cache) - self.max_size]:
                self._cache.pop(key, None)

    def register(self, exchange_order_id: str, account_id: int, exchange: str,
                 market_type: str, symbol: str):
        """실거래소 주문 ID와 메타데이터를 매핑해 저장."""
        if not exchange_order_id:
            return

        payload = {
            "account_id": account_id,
            "exchange": (exchange or "").upper(),
            "market_type": (market_type or "").lower() or "spot",
            "symbol": symbol,
            "ts": time.time(),
        }

        with self._lock:
            self._cache[exchange_order_id] = payload
            self._purge()

        logger.debug(
            "🧭 Order mapping 캐시 저장: order_id=%s, exchange=%s, market_type=%s, symbol=%s",
            exchange_order_id, payload["exchange"], payload["market_type"], payload["symbol"]
        )

    def get(self, exchange_order_id: str) -> Optional[Dict[str, Any]]:
        """주문 ID로 메타데이터를 조회. TTL이 지난 항목은 제거 후 None 반환."""
        if not exchange_order_id:
            return None

        with self._lock:
            entry = self._cache.get(exchange_order_id)
            if not entry:
                return None

            if time.time() - entry.get("ts", 0) > self.ttl_seconds:
                # 만료된 항목은 제거 후 miss 처리
                self._cache.pop(exchange_order_id, None)
                return None

            return dict(entry)


# 싱글톤 인스턴스
order_mapping_cache = OrderMappingCache()
