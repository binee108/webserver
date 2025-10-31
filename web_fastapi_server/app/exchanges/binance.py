"""
Binance Exchange Adapter

Binance Spot API 비동기 어댑터
API 문서: https://binance-docs.github.io/apidocs/spot/en/
"""

import hmac
import hashlib
import time
import logging
from typing import Optional, List, Dict, Any
from urllib.parse import urlencode

from app.exchanges.base import BaseExchangeAdapter
from app.exchanges.utils.rate_limiter import RateLimiter
from app.exchanges.exceptions import (
    OrderNotFoundException,
    InsufficientBalanceError,
    ExchangeAuthError
)

logger = logging.getLogger(__name__)


class BinanceAdapter(BaseExchangeAdapter):
    """
    Binance 거래소 어댑터

    인증: HMAC SHA256 서명
    Rate Limit: 1200 requests/minute (weight 기반)
    """

    BASE_URL = "https://api.binance.com"

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        timeout: float = 30.0,
        max_retries: int = 3,
        requests_per_second: float = 10.0
    ):
        super().__init__(api_key, api_secret, timeout, max_retries)

        self.exchange_name = "binance"

        # Rate Limiter (기본: 10 req/s)
        self.rate_limiter = RateLimiter(requests_per_second=requests_per_second)

        logger.info(
            f"Binance adapter initialized: "
            f"API Key={self._mask_api_key(api_key)}"
        )

    def _sign_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Binance 요청 서명

        서명 방식:
        1. timestamp 추가
        2. query string 생성
        3. HMAC SHA256 서명
        4. signature 추가

        Args:
            method: HTTP 메서드
            endpoint: API 엔드포인트
            params: 파라미터

        Returns:
            서명된 파라미터
        """
        if params is None:
            params = {}

        # Timestamp 추가 (밀리초)
        params['timestamp'] = int(time.time() * 1000)

        # Query string 생성
        query_string = urlencode(params)

        # HMAC SHA256 서명
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        # Signature 추가
        params['signature'] = signature

        logger.debug(f"Binance request signed: {endpoint}")

        return params

    async def cancel_order(
        self,
        symbol: str,
        order_id: str
    ) -> Dict[str, Any]:
        """주문 취소"""
        await self.rate_limiter.acquire()

        endpoint = "/api/v3/order"
        params = {
            "symbol": self._normalize_symbol(symbol),
            "orderId": order_id
        }

        # 서명
        signed_params = self._sign_request("DELETE", endpoint, params)

        # 헤더
        headers = {
            "X-MBX-APIKEY": self.api_key
        }

        # 요청
        try:
            result = await self.http_client.delete(
                url=f"{self.BASE_URL}{endpoint}",
                headers=headers,
                params=signed_params
            )

            logger.info(f"✅ Binance order cancelled: {order_id}")

            return self._normalize_order(result)

        except Exception as e:
            # 주문 없음 체크
            if "Unknown order" in str(e) or "Order does not exist" in str(e):
                raise OrderNotFoundException(order_id=order_id, exchange="binance")

            raise

    async def get_order(
        self,
        symbol: str,
        order_id: str
    ) -> Dict[str, Any]:
        """주문 조회"""
        await self.rate_limiter.acquire()

        endpoint = "/api/v3/order"
        params = {
            "symbol": self._normalize_symbol(symbol),
            "orderId": order_id
        }

        # 서명
        signed_params = self._sign_request("GET", endpoint, params)

        # 헤더
        headers = {
            "X-MBX-APIKEY": self.api_key
        }

        # 요청
        try:
            result = await self.http_client.get(
                url=f"{self.BASE_URL}{endpoint}",
                headers=headers,
                params=signed_params
            )

            logger.debug(f"Binance order retrieved: {order_id}")

            return self._normalize_order(result)

        except Exception as e:
            # 주문 없음 체크
            if "Unknown order" in str(e) or "Order does not exist" in str(e):
                raise OrderNotFoundException(order_id=order_id, exchange="binance")

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

        endpoint = "/api/v3/order"
        params = {
            "symbol": self._normalize_symbol(symbol),
            "side": side.upper(),  # BUY, SELL
            "type": order_type.upper(),  # MARKET, LIMIT
            "quantity": quantity
        }

        # Limit 주문 시 가격 필수
        if order_type.lower() == "limit":
            if price is None:
                raise ValueError("Price is required for limit orders")
            params["price"] = price
            params["timeInForce"] = "GTC"  # Good Till Cancel

        # 서명
        signed_params = self._sign_request("POST", endpoint, params)

        # 헤더
        headers = {
            "X-MBX-APIKEY": self.api_key
        }

        # 요청
        try:
            result = await self.http_client.post(
                url=f"{self.BASE_URL}{endpoint}",
                headers=headers,
                params=signed_params
            )

            logger.info(
                f"✅ Binance order created: "
                f"{side.upper()} {quantity} {symbol} @ {order_type.upper()}"
            )

            return self._normalize_order(result)

        except Exception as e:
            # 잔고 부족 체크
            if "insufficient balance" in str(e).lower():
                raise InsufficientBalanceError(
                    message=f"Insufficient balance for {symbol}",
                    details={"symbol": symbol, "quantity": quantity}
                )

            # 인증 에러 체크
            if "API-key format invalid" in str(e) or "Signature for this request" in str(e):
                raise ExchangeAuthError(
                    message="Binance authentication failed",
                    details={"error": str(e)}
                )

            raise

    async def get_open_orders(
        self,
        symbol: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """미체결 주문 조회"""
        await self.rate_limiter.acquire()

        endpoint = "/api/v3/openOrders"
        params = {}

        if symbol:
            params["symbol"] = self._normalize_symbol(symbol)

        # 서명
        signed_params = self._sign_request("GET", endpoint, params)

        # 헤더
        headers = {
            "X-MBX-APIKEY": self.api_key
        }

        # 요청
        result = await self.http_client.get(
            url=f"{self.BASE_URL}{endpoint}",
            headers=headers,
            params=signed_params
        )

        logger.debug(f"Binance open orders retrieved: {len(result)} orders")

        # 정규화
        return [self._normalize_order(order) for order in result]

    # === 데이터 정규화 ===

    def _normalize_symbol(self, symbol: str) -> str:
        """
        심볼 정규화: "BTC/USDT" → "BTCUSDT"
        """
        return symbol.replace("/", "")

    def _normalize_order(self, raw_order: Dict[str, Any]) -> Dict[str, Any]:
        """
        Binance 주문을 공통 형식으로 변환
        """
        return {
            "exchange": "binance",
            "order_id": str(raw_order["orderId"]),
            "symbol": raw_order["symbol"],  # BTCUSDT 형식
            "side": raw_order["side"].lower(),  # buy, sell
            "type": raw_order["type"].lower(),  # market, limit
            "status": self._normalize_status(raw_order["status"]),
            "quantity": float(raw_order["origQty"]),
            "executed_quantity": float(raw_order["executedQty"]),
            "price": float(raw_order.get("price", 0)),
            "average_price": float(raw_order.get("avgPrice", 0)) if raw_order.get("avgPrice") else 0,
            "created_at": raw_order["time"]
        }

    def _normalize_status(self, raw_status: str) -> str:
        """
        Binance 상태 → 공통 상태

        Binance 상태:
        - NEW: 주문 접수
        - PARTIALLY_FILLED: 부분 체결
        - FILLED: 체결 완료
        - CANCELED: 취소됨
        - PENDING_CANCEL: 취소 중
        - REJECTED: 거부됨
        - EXPIRED: 만료됨
        """
        mapping = {
            "NEW": "OPEN",
            "PARTIALLY_FILLED": "OPEN",
            "FILLED": "FILLED",
            "CANCELED": "CANCELLED",
            "PENDING_CANCEL": "OPEN",  # 취소 처리 중
            "REJECTED": "FAILED",
            "EXPIRED": "EXPIRED"
        }

        return mapping.get(raw_status, "UNKNOWN")
