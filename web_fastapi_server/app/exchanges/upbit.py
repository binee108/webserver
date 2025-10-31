"""
Upbit Exchange Adapter

Upbit API 비동기 어댑터 (한국 거래소)
API 문서: https://docs.upbit.com/reference
"""

import uuid
import hashlib
import jwt
import logging
from typing import Optional, List, Dict, Any
from urllib.parse import urlencode, unquote

from app.exchanges.base import BaseExchangeAdapter
from app.exchanges.utils.rate_limiter import RateLimiter
from app.exchanges.exceptions import (
    OrderNotFoundException,
    InsufficientBalanceError,
    ExchangeAuthError
)

logger = logging.getLogger(__name__)


class UpbitAdapter(BaseExchangeAdapter):
    """
    Upbit 거래소 어댑터

    인증: JWT (JSON Web Token)
    Rate Limit: 8 req/s (주문), 30 req/s (일반)
    """

    BASE_URL = "https://api.upbit.com"

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        timeout: float = 30.0,
        max_retries: int = 3,
        requests_per_second: float = 8.0  # 주문 API 기준
    ):
        super().__init__(api_key, api_secret, timeout, max_retries)

        self.exchange_name = "upbit"

        # Rate Limiter (주문 API 기준: 8 req/s)
        self.rate_limiter = RateLimiter(requests_per_second=requests_per_second)

        logger.info(
            f"Upbit adapter initialized: "
            f"API Key={self._mask_api_key(api_key)}"
        )

    def _sign_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, str]:
        """
        Upbit JWT 토큰 생성

        JWT Payload:
        - access_key
        - nonce (UUID v4)
        - query_hash (파라미터가 있는 경우)
        - query_hash_alg (SHA512)

        Args:
            method: HTTP 메서드
            endpoint: API 엔드포인트
            params: 파라미터

        Returns:
            JWT 토큰 헤더
        """
        payload = {
            'access_key': self.api_key,
            'nonce': str(uuid.uuid4())
        }

        # 파라미터가 있는 경우 query_hash 추가
        if params:
            query_string = unquote(urlencode(params, doseq=True))
            m = hashlib.sha512()
            m.update(query_string.encode())
            query_hash = m.hexdigest()

            payload['query_hash'] = query_hash
            payload['query_hash_alg'] = 'SHA512'

        # JWT 토큰 생성
        jwt_token = jwt.encode(payload, self.api_secret, algorithm='HS256')

        # 헤더 생성
        headers = {
            'Authorization': f'Bearer {jwt_token}',
            'Content-Type': 'application/json'
        }

        logger.debug(f"Upbit request signed: {endpoint}")

        return headers

    async def cancel_order(
        self,
        symbol: str,
        order_id: str
    ) -> Dict[str, Any]:
        """주문 취소"""
        await self.rate_limiter.acquire()

        endpoint = "/v1/order"
        params = {
            "uuid": order_id
        }

        # JWT 헤더
        headers = self._sign_request("DELETE", endpoint, params)

        # 요청
        try:
            result = await self.http_client.delete(
                url=f"{self.BASE_URL}{endpoint}",
                headers=headers,
                params=params
            )

            logger.info(f"✅ Upbit order cancelled: {order_id}")

            return self._normalize_order(result)

        except Exception as e:
            # 주문 없음 체크
            if "order_not_found" in str(e).lower() or "invalid_query_payload" in str(e).lower():
                raise OrderNotFoundException(order_id=order_id, exchange="upbit")

            raise

    async def get_order(
        self,
        symbol: str,
        order_id: str
    ) -> Dict[str, Any]:
        """주문 조회"""
        await self.rate_limiter.acquire()

        endpoint = "/v1/order"
        params = {
            "uuid": order_id
        }

        # JWT 헤더
        headers = self._sign_request("GET", endpoint, params)

        # 요청
        try:
            result = await self.http_client.get(
                url=f"{self.BASE_URL}{endpoint}",
                headers=headers,
                params=params
            )

            logger.debug(f"Upbit order retrieved: {order_id}")

            return self._normalize_order(result)

        except Exception as e:
            # 주문 없음 체크
            if "order_not_found" in str(e).lower() or "invalid_query_payload" in str(e).lower():
                raise OrderNotFoundException(order_id=order_id, exchange="upbit")

            raise

    async def create_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: Optional[float] = None
    ) -> Dict[str, Any]:
        """주문 생성"""
        await self.rate_limiter.acquire()

        endpoint = "/v1/orders"
        params = {
            "market": self._normalize_symbol(symbol),
            "side": "bid" if side.lower() == "buy" else "ask",
            "ord_type": "price" if order_type.lower() == "market" else "limit"
        }

        # Market 주문
        if order_type.lower() == "market":
            if side.lower() == "buy":
                # 매수: 금액 지정 (KRW)
                if price is None:
                    raise ValueError("Price (total amount) is required for market buy")
                params["price"] = str(int(price))
            else:
                # 매도: 수량 지정
                params["volume"] = str(quantity)
        else:
            # Limit 주문
            if price is None:
                raise ValueError("Price is required for limit orders")
            params["price"] = str(int(price))
            params["volume"] = str(quantity)

        # JWT 헤더
        headers = self._sign_request("POST", endpoint, params)

        # 요청
        try:
            result = await self.http_client.post(
                url=f"{self.BASE_URL}{endpoint}",
                headers=headers,
                json=params
            )

            logger.info(
                f"✅ Upbit order created: "
                f"{side.upper()} {quantity} {symbol} @ {order_type.upper()}"
            )

            return self._normalize_order(result)

        except Exception as e:
            # 잔고 부족 체크
            if "insufficient" in str(e).lower() or "invalid_funds" in str(e).lower():
                raise InsufficientBalanceError(
                    message=f"Insufficient balance for {symbol}",
                    details={"symbol": symbol, "quantity": quantity}
                )

            # 인증 에러 체크
            if "invalid_access_key" in str(e).lower() or "jwt" in str(e).lower():
                raise ExchangeAuthError(
                    message="Upbit authentication failed",
                    details={"error": str(e)}
                )

            raise

    async def get_open_orders(
        self,
        symbol: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """미체결 주문 조회"""
        await self.rate_limiter.acquire()

        endpoint = "/v1/orders"
        params = {
            "state": "wait"  # wait = 미체결
        }

        if symbol:
            params["market"] = self._normalize_symbol(symbol)

        # JWT 헤더
        headers = self._sign_request("GET", endpoint, params)

        # 요청
        result = await self.http_client.get(
            url=f"{self.BASE_URL}{endpoint}",
            headers=headers,
            params=params
        )

        logger.debug(f"Upbit open orders retrieved: {len(result)} orders")

        # 정규화
        return [self._normalize_order(order) for order in result]

    # === 데이터 정규화 ===

    def _normalize_symbol(self, symbol: str) -> str:
        """
        심볼 정규화: "BTC/KRW" → "KRW-BTC"

        Upbit은 dash 구분이며 순서가 반대
        """
        if "/" in symbol:
            base, quote = symbol.split("/")
            return f"{quote}-{base}"
        return symbol

    def _normalize_order(self, raw_order: Dict[str, Any]) -> Dict[str, Any]:
        """
        Upbit 주문을 공통 형식으로 변환
        """
        # 심볼 변환: "KRW-BTC" → "BTC/KRW"
        market = raw_order.get("market", "")
        if "-" in market:
            quote, base = market.split("-")
            normalized_symbol = f"{base}/{quote}"
        else:
            normalized_symbol = market

        return {
            "exchange": "upbit",
            "order_id": raw_order.get("uuid", ""),
            "symbol": normalized_symbol,
            "side": "buy" if raw_order.get("side") == "bid" else "sell",
            "type": "market" if raw_order.get("ord_type") in ["price", "market"] else "limit",
            "status": self._normalize_status(raw_order.get("state", "")),
            "quantity": float(raw_order.get("volume", 0)),
            "executed_quantity": float(raw_order.get("executed_volume", 0)),
            "price": float(raw_order.get("price", 0)),
            "average_price": float(raw_order.get("avg_price", 0)) if raw_order.get("avg_price") else 0,
            "created_at": self._parse_upbit_timestamp(raw_order.get("created_at", ""))
        }

    def _normalize_status(self, raw_status: str) -> str:
        """
        Upbit 상태 → 공통 상태

        Upbit 상태:
        - wait: 체결 대기
        - watch: 예약 주문 대기
        - done: 전체 체결 완료
        - cancel: 주문 취소
        """
        mapping = {
            "wait": "OPEN",
            "watch": "OPEN",
            "done": "FILLED",
            "cancel": "CANCELLED"
        }

        return mapping.get(raw_status, "UNKNOWN")

    def _parse_upbit_timestamp(self, timestamp_str: str) -> int:
        """
        Upbit 타임스탬프 파싱

        형식: "2023-10-31T12:34:56+09:00"
        반환: 밀리초 Unix timestamp
        """
        if not timestamp_str:
            return 0

        try:
            from datetime import datetime
            # ISO 8601 파싱
            dt = datetime.fromisoformat(timestamp_str)
            return int(dt.timestamp() * 1000)
        except Exception as e:
            logger.warning(f"Failed to parse Upbit timestamp: {timestamp_str} - {e}")
            return 0
