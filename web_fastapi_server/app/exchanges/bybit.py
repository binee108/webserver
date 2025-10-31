"""
Bybit Exchange Adapter

Bybit V5 API 비동기 어댑터
API 문서: https://bybit-exchange.github.io/docs/v5/intro
"""

import hmac
import hashlib
import time
import logging
from typing import Optional, List, Dict, Any

from app.exchanges.base import BaseExchangeAdapter
from app.exchanges.utils.rate_limiter import RateLimiter
from app.exchanges.exceptions import (
    OrderNotFoundException,
    InsufficientBalanceError,
    ExchangeAuthError
)

logger = logging.getLogger(__name__)


class BybitAdapter(BaseExchangeAdapter):
    """
    Bybit 거래소 어댑터 (V5 API)

    인증: HMAC SHA256 서명 (헤더)
    Rate Limit: 10 req/s (Spot)
    """

    BASE_URL = "https://api.bybit.com"

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        timeout: float = 30.0,
        max_retries: int = 3,
        requests_per_second: float = 10.0
    ):
        super().__init__(api_key, api_secret, timeout, max_retries)

        self.exchange_name = "bybit"

        # Rate Limiter (기본: 10 req/s)
        self.rate_limiter = RateLimiter(requests_per_second=requests_per_second)

        logger.info(
            f"Bybit adapter initialized: "
            f"API Key={self._mask_api_key(api_key)}"
        )

    def _sign_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, str]:
        """
        Bybit V5 요청 서명

        서명 방식:
        1. timestamp + api_key + recv_window + query_string 생성
        2. HMAC SHA256 서명
        3. 헤더에 추가

        Args:
            method: HTTP 메서드
            endpoint: API 엔드포인트
            params: 파라미터

        Returns:
            서명 헤더
        """
        timestamp = str(int(time.time() * 1000))
        recv_window = "5000"  # 5초

        # Query string 생성 (파라미터가 있는 경우)
        if params:
            # JSON 바디인 경우
            if method in ["POST", "PUT"]:
                import json
                param_str = json.dumps(params, separators=(',', ':'))
            else:
                # GET/DELETE는 query string
                from urllib.parse import urlencode
                param_str = urlencode(sorted(params.items()))
        else:
            param_str = ""

        # Signature payload
        # timestamp + api_key + recv_window + param_str
        sign_payload = timestamp + self.api_key + recv_window + param_str

        # HMAC SHA256 서명
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            sign_payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        # 헤더 생성
        headers = {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-SIGN": signature,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": recv_window,
            "Content-Type": "application/json"
        }

        logger.debug(f"Bybit request signed: {endpoint}")

        return headers

    async def cancel_order(
        self,
        symbol: str,
        order_id: str
    ) -> Dict[str, Any]:
        """주문 취소"""
        await self.rate_limiter.acquire()

        endpoint = "/v5/order/cancel"
        params = {
            "category": "spot",
            "symbol": self._normalize_symbol(symbol),
            "orderId": order_id
        }

        # 서명 헤더
        headers = self._sign_request("POST", endpoint, params)

        # 요청
        try:
            result = await self.http_client.post(
                url=f"{self.BASE_URL}{endpoint}",
                headers=headers,
                json=params
            )

            # Bybit V5 응답 구조: {"retCode":0,"retMsg":"OK","result":{...}}
            if result.get("retCode") != 0:
                error_msg = result.get("retMsg", "Unknown error")
                logger.error(f"Bybit cancel error: {error_msg}")
                raise Exception(f"Bybit API error: {error_msg}")

            logger.info(f"✅ Bybit order cancelled: {order_id}")

            return self._normalize_order(result.get("result", {}))

        except Exception as e:
            # 주문 없음 체크
            if "order not found" in str(e).lower() or "110001" in str(e):
                raise OrderNotFoundException(order_id=order_id, exchange="bybit")

            raise

    async def get_order(
        self,
        symbol: str,
        order_id: str
    ) -> Dict[str, Any]:
        """주문 조회"""
        await self.rate_limiter.acquire()

        endpoint = "/v5/order/realtime"
        params = {
            "category": "spot",
            "symbol": self._normalize_symbol(symbol),
            "orderId": order_id
        }

        # 서명 헤더
        headers = self._sign_request("GET", endpoint, params)

        # 요청
        try:
            result = await self.http_client.get(
                url=f"{self.BASE_URL}{endpoint}",
                headers=headers,
                params=params
            )

            if result.get("retCode") != 0:
                error_msg = result.get("retMsg", "Unknown error")
                logger.error(f"Bybit get_order error: {error_msg}")
                raise Exception(f"Bybit API error: {error_msg}")

            # result.list[0]에 주문 정보
            orders = result.get("result", {}).get("list", [])
            if not orders:
                raise OrderNotFoundException(order_id=order_id, exchange="bybit")

            logger.debug(f"Bybit order retrieved: {order_id}")

            return self._normalize_order(orders[0])

        except OrderNotFoundException:
            raise
        except Exception as e:
            # 주문 없음 체크
            if "order not found" in str(e).lower():
                raise OrderNotFoundException(order_id=order_id, exchange="bybit")

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

        endpoint = "/v5/order/create"
        params = {
            "category": "spot",
            "symbol": self._normalize_symbol(symbol),
            "side": side.capitalize(),  # Buy, Sell
            "orderType": order_type.capitalize(),  # Market, Limit
            "qty": str(quantity)
        }

        # Limit 주문 시 가격 필수
        if order_type.lower() == "limit":
            if price is None:
                raise ValueError("Price is required for limit orders")
            params["price"] = str(price)

        # 서명 헤더
        headers = self._sign_request("POST", endpoint, params)

        # 요청
        try:
            result = await self.http_client.post(
                url=f"{self.BASE_URL}{endpoint}",
                headers=headers,
                json=params
            )

            if result.get("retCode") != 0:
                error_msg = result.get("retMsg", "Unknown error")
                logger.error(f"Bybit create_order error: {error_msg}")

                # 잔고 부족 체크
                if "insufficient" in error_msg.lower():
                    raise InsufficientBalanceError(
                        message=f"Insufficient balance for {symbol}",
                        details={"symbol": symbol, "quantity": quantity}
                    )

                raise Exception(f"Bybit API error: {error_msg}")

            logger.info(
                f"✅ Bybit order created: "
                f"{side.upper()} {quantity} {symbol} @ {order_type.upper()}"
            )

            return self._normalize_order(result.get("result", {}))

        except (InsufficientBalanceError, ValueError):
            raise
        except Exception as e:
            # 인증 에러 체크
            if "invalid api_key" in str(e).lower() or "10003" in str(e):
                raise ExchangeAuthError(
                    message="Bybit authentication failed",
                    details={"error": str(e)}
                )

            raise

    async def get_open_orders(
        self,
        symbol: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """미체결 주문 조회"""
        await self.rate_limiter.acquire()

        endpoint = "/v5/order/realtime"
        params = {
            "category": "spot"
        }

        if symbol:
            params["symbol"] = self._normalize_symbol(symbol)

        # 서명 헤더
        headers = self._sign_request("GET", endpoint, params)

        # 요청
        result = await self.http_client.get(
            url=f"{self.BASE_URL}{endpoint}",
            headers=headers,
            params=params
        )

        if result.get("retCode") != 0:
            error_msg = result.get("retMsg", "Unknown error")
            logger.error(f"Bybit get_open_orders error: {error_msg}")
            raise Exception(f"Bybit API error: {error_msg}")

        orders = result.get("result", {}).get("list", [])
        logger.debug(f"Bybit open orders retrieved: {len(orders)} orders")

        # 정규화
        return [self._normalize_order(order) for order in orders]

    # === 데이터 정규화 ===

    def _normalize_symbol(self, symbol: str) -> str:
        """
        심볼 정규화: "BTC/USDT" → "BTCUSDT"
        """
        return symbol.replace("/", "")

    def _normalize_order(self, raw_order: Dict[str, Any]) -> Dict[str, Any]:
        """
        Bybit 주문을 공통 형식으로 변환
        """
        return {
            "exchange": "bybit",
            "order_id": str(raw_order.get("orderId", "")),
            "symbol": raw_order.get("symbol", ""),  # BTCUSDT 형식
            "side": raw_order.get("side", "").lower(),  # buy, sell
            "type": raw_order.get("orderType", "").lower(),  # market, limit
            "status": self._normalize_status(raw_order.get("orderStatus", "")),
            "quantity": float(raw_order.get("qty", 0)),
            "executed_quantity": float(raw_order.get("cumExecQty", 0)),
            "price": float(raw_order.get("price", 0)),
            "average_price": float(raw_order.get("avgPrice", 0)),
            "created_at": int(raw_order.get("createdTime", 0))
        }

    def _normalize_status(self, raw_status: str) -> str:
        """
        Bybit 상태 → 공통 상태

        Bybit 상태:
        - New: 주문 접수
        - PartiallyFilled: 부분 체결
        - Filled: 체결 완료
        - Cancelled: 취소됨
        - Rejected: 거부됨
        """
        mapping = {
            "New": "OPEN",
            "PartiallyFilled": "OPEN",
            "Filled": "FILLED",
            "Cancelled": "CANCELLED",
            "Rejected": "FAILED",
            "Untriggered": "OPEN",  # 조건부 주문
            "Triggered": "OPEN",
            "Deactivated": "CANCELLED"
        }

        return mapping.get(raw_status, "UNKNOWN")
