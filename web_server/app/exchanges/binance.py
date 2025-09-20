"""
Binance 통합 API 구현 (Spot + Futures)

1인 사용자를 위한 단순화된 Binance API 구현입니다.
Spot과 Futures를 하나의 클래스로 통합하여 관리를 단순화합니다.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import time
from decimal import Decimal
from typing import Dict, List, Optional, Any, Union
from urllib.parse import urlencode

import aiohttp

from .base import BaseExchange, ExchangeError, InvalidOrder, InsufficientFunds
from .models import MarketInfo, Balance, Order, Ticker, Position

logger = logging.getLogger(__name__)

# API 기본 URL
SPOT_BASE_URL = "https://api.binance.com"
FUTURES_BASE_URL = "https://fapi.binance.com"
SPOT_TESTNET_URL = "https://testnet.binance.vision"
FUTURES_TESTNET_URL = "https://testnet.binancefuture.com"

# Rate Limits
SPOT_RATE_LIMIT = 1200
FUTURES_RATE_LIMIT = 2400

# API 엔드포인트
class SpotEndpoints:
    EXCHANGE_INFO = "/api/v3/exchangeInfo"
    TICKER_24HR = "/api/v3/ticker/24hr"
    TICKER_PRICE = "/api/v3/ticker/price"
    ORDER_BOOK = "/api/v3/depth"
    ACCOUNT = "/api/v3/account"
    ORDER = "/api/v3/order"
    OPEN_ORDERS = "/api/v3/openOrders"

class FuturesEndpoints:
    EXCHANGE_INFO = "/fapi/v1/exchangeInfo"
    TICKER_24HR = "/fapi/v1/ticker/24hr"
    TICKER_PRICE = "/fapi/v1/ticker/price"
    ORDER_BOOK = "/fapi/v1/depth"
    ACCOUNT = "/fapi/v2/account"
    POSITION_RISK = "/fapi/v2/positionRisk"
    ORDER = "/fapi/v1/order"
    OPEN_ORDERS = "/fapi/v1/openOrders"

# 주문 관련 상수
class OrderType:
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"
    STOP_LOSS_LIMIT = "STOP_LOSS_LIMIT"

class OrderSide:
    BUY = "BUY"
    SELL = "SELL"

class OrderStatus:
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class BinanceExchange(BaseExchange):
    """
    Binance 통합 거래소 클래스 (Spot + Futures)

    특징:
    - Spot과 Futures를 하나의 클래스로 통합
    - market_type 파라미터로 Spot/Futures 구분
    - 메모리 캐싱으로 성능 최적화
    - 1인 사용자에 최적화된 단순한 구조
    """

    def __init__(self, api_key: str, api_secret: str, testnet: bool = False):
        super().__init__()

        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet

        # URL 설정
        if testnet:
            self.spot_base_url = SPOT_TESTNET_URL
            self.futures_base_url = FUTURES_TESTNET_URL
        else:
            self.spot_base_url = SPOT_BASE_URL
            self.futures_base_url = FUTURES_BASE_URL

        # 캐시
        self.spot_markets_cache = {}
        self.futures_markets_cache = {}
        self.cache_time = {}
        self.cache_ttl = 300  # 5분

        # HTTP 세션
        self.session = None

        logger.info(f"✅ Binance 통합 거래소 초기화 - Testnet: {testnet}")

    async def _init_session(self):
        """HTTP 세션 초기화"""
        if self.session is None:
            timeout = aiohttp.ClientTimeout(total=30)
            connector = aiohttp.TCPConnector(limit=100, limit_per_host=30)
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                headers={'User-Agent': 'Binance-Native-Client/1.0'}
            )

    async def close(self):
        """세션 정리"""
        if self.session:
            await self.session.close()
            self.session = None

    def _get_base_url(self, market_type: str) -> str:
        """마켓 타입에 따른 기본 URL 반환"""
        if market_type.lower() == 'futures':
            return self.futures_base_url
        else:
            return self.spot_base_url

    def _get_endpoints(self, market_type: str):
        """마켓 타입에 따른 엔드포인트 클래스 반환"""
        if market_type.lower() == 'futures':
            return FuturesEndpoints
        else:
            return SpotEndpoints

    def _create_signature(self, params: Dict[str, Any]) -> str:
        """API 서명 생성"""
        query_string = urlencode(params)
        return hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    async def _request(self, method: str, url: str, params: Dict[str, Any] = None,
                      signed: bool = False) -> Dict[str, Any]:
        """HTTP 요청 실행"""
        await self._init_session()

        if params is None:
            params = {}

        headers = {}
        if self.api_key:
            headers['X-MBX-APIKEY'] = self.api_key

        if signed:
            params['timestamp'] = int(time.time() * 1000)
            params['signature'] = self._create_signature(params)

        try:
            if method.upper() == 'GET':
                async with self.session.get(url, params=params, headers=headers) as response:
                    data = await response.json()
            elif method.upper() == 'POST':
                async with self.session.post(url, data=params, headers=headers) as response:
                    data = await response.json()
            elif method.upper() == 'DELETE':
                async with self.session.delete(url, params=params, headers=headers) as response:
                    data = await response.json()
            else:
                raise ValueError(f"지원하지 않는 HTTP 메서드: {method}")

            if 'code' in data and data['code'] != 200:
                raise ExchangeError(f"Binance API 오류: {data.get('msg', 'Unknown error')}")

            return data

        except aiohttp.ClientError as e:
            raise ExchangeError(f"네트워크 오류: {str(e)}")
        except json.JSONDecodeError as e:
            raise ExchangeError(f"JSON 파싱 오류: {str(e)}")

    async def load_markets(self, market_type: str = 'spot', reload: bool = False) -> Dict[str, MarketInfo]:
        """마켓 정보 로드"""
        cache_key = f"{market_type}_markets"

        # 캐시 확인
        if not reload and cache_key in self.cache_time:
            if time.time() - self.cache_time[cache_key] < self.cache_ttl:
                return getattr(self, f"{market_type}_markets_cache", {})

        base_url = self._get_base_url(market_type)
        endpoints = self._get_endpoints(market_type)

        url = f"{base_url}{endpoints.EXCHANGE_INFO}"
        data = await self._request('GET', url)

        markets = {}
        for symbol_info in data.get('symbols', []):
            if symbol_info['status'] != 'TRADING':
                continue

            symbol = symbol_info['symbol']
            markets[symbol] = MarketInfo(
                id=symbol,
                symbol=symbol,
                base=symbol_info['baseAsset'],
                quote=symbol_info['quoteAsset'],
                active=True,
                amount_precision=symbol_info.get('baseAssetPrecision', 8),
                price_precision=symbol_info.get('quotePrecision', 8),
                market_type=market_type.upper()
            )

        # 캐시 업데이트
        if market_type == 'spot':
            self.spot_markets_cache = markets
        else:
            self.futures_markets_cache = markets

        self.cache_time[cache_key] = time.time()

        logger.info(f"✅ {market_type.title()} 마켓 정보 로드 완료: {len(markets)}개")
        return markets

    async def fetch_balance(self, market_type: str = 'spot') -> Dict[str, Balance]:
        """잔액 조회"""
        base_url = self._get_base_url(market_type)
        endpoints = self._get_endpoints(market_type)

        url = f"{base_url}{endpoints.ACCOUNT}"
        data = await self._request('GET', url, signed=True)

        balances = {}
        balance_key = 'balances' if market_type == 'spot' else 'assets'

        for balance_info in data.get(balance_key, []):
            asset = balance_info['asset']
            free = Decimal(balance_info['free'])
            locked = Decimal(balance_info.get('locked', '0'))

            if free > 0 or locked > 0:
                balances[asset] = Balance(
                    currency=asset,
                    free=free,
                    used=locked,
                    total=free + locked
                )

        return balances

    async def fetch_positions(self) -> List[Position]:
        """포지션 조회 (Futures 전용)"""
        base_url = self._get_base_url('futures')

        url = f"{base_url}{FuturesEndpoints.POSITION_RISK}"
        data = await self._request('GET', url, signed=True)

        positions = []
        for pos_info in data:
            size = Decimal(pos_info['positionAmt'])
            if size != 0:  # 포지션이 있는 경우만
                positions.append(Position(
                    symbol=pos_info['symbol'],
                    side='long' if size > 0 else 'short',
                    size=abs(size),
                    entry_price=Decimal(pos_info['entryPrice']),
                    unrealized_pnl=Decimal(pos_info['unRealizedProfit']),
                    percentage=Decimal(pos_info['percentage'])
                ))

        return positions

    async def create_order(self, symbol: str, order_type: str, side: str,
                          amount: Decimal, price: Optional[Decimal] = None,
                          market_type: str = 'spot', **params) -> Order:
        """주문 생성"""
        base_url = self._get_base_url(market_type)
        endpoints = self._get_endpoints(market_type)

        order_params = {
            'symbol': symbol,
            'side': side.upper(),
            'type': order_type.upper(),
        }

        # 수량 설정 (Spot: quantity, Futures: quantity)
        order_params['quantity'] = str(amount)

        # 가격 설정 (LIMIT 주문의 경우)
        if order_type.upper() == 'LIMIT' and price:
            order_params['price'] = str(price)
            order_params['timeInForce'] = 'GTC'  # Good Till Canceled

        # 추가 파라미터
        order_params.update(params)

        url = f"{base_url}{endpoints.ORDER}"
        data = await self._request('POST', url, order_params, signed=True)

        return self._parse_order(data, market_type)

    async def cancel_order(self, order_id: str, symbol: str,
                          market_type: str = 'spot') -> Dict[str, Any]:
        """주문 취소"""
        base_url = self._get_base_url(market_type)
        endpoints = self._get_endpoints(market_type)

        params = {
            'symbol': symbol,
            'orderId': order_id
        }

        url = f"{base_url}{endpoints.ORDER}"
        return await self._request('DELETE', url, params, signed=True)

    async def fetch_open_orders(self, symbol: Optional[str] = None,
                               market_type: str = 'spot') -> List[Order]:
        """미체결 주문 조회"""
        base_url = self._get_base_url(market_type)
        endpoints = self._get_endpoints(market_type)

        params = {}
        if symbol:
            params['symbol'] = symbol

        url = f"{base_url}{endpoints.OPEN_ORDERS}"
        data = await self._request('GET', url, params, signed=True)

        return [self._parse_order(order_data, market_type) for order_data in data]

    def _parse_order(self, order_data: Dict[str, Any], market_type: str) -> Order:
        """주문 데이터 파싱"""
        return Order(
            id=str(order_data['orderId']),
            symbol=order_data['symbol'],
            side=order_data['side'].lower(),
            amount=Decimal(order_data['origQty']),
            price=Decimal(order_data['price']) if order_data['price'] != '0' else None,
            filled=Decimal(order_data['executedQty']),
            remaining=Decimal(order_data['origQty']) - Decimal(order_data['executedQty']),
            status=self._normalize_order_status(order_data['status']),
            timestamp=order_data['time'],
            type=order_data['type'].lower(),
            market_type=market_type.upper()
        )

    def _normalize_order_status(self, status: str) -> str:
        """주문 상태 정규화"""
        status_map = {
            'NEW': 'open',
            'PARTIALLY_FILLED': 'open',
            'FILLED': 'closed',
            'CANCELED': 'canceled',
            'REJECTED': 'rejected',
            'EXPIRED': 'expired'
        }
        return status_map.get(status, status.lower())

    # CCXT 호환 메서드들 (동기)
    def fetch_balance_sync(self, market_type: str = 'spot') -> Dict[str, Balance]:
        """잔액 조회 (동기)"""
        return asyncio.run(self.fetch_balance(market_type))

    def create_market_order(self, symbol: str, side: str, amount: float,
                           market_type: str = 'spot') -> Order:
        """시장가 주문 (동기 래퍼)"""
        return asyncio.run(self.create_order(
            symbol, OrderType.MARKET, side, Decimal(str(amount)),
            market_type=market_type
        ))

    def create_limit_order(self, symbol: str, side: str, amount: float,
                          price: float, market_type: str = 'spot') -> Order:
        """지정가 주문 (동기 래퍼)"""
        return asyncio.run(self.create_order(
            symbol, OrderType.LIMIT, side, Decimal(str(amount)),
            Decimal(str(price)), market_type=market_type
        ))

    def load_markets_sync(self, market_type: str = 'spot', reload: bool = False) -> Dict[str, MarketInfo]:
        """마켓 정보 로드 (동기)"""
        return asyncio.run(self.load_markets(market_type, reload))

    # 심볼 정보 조회 (precision 서비스용)
    def get_symbol_info(self, symbol: str, market_type: str = 'spot') -> Optional[Dict[str, Any]]:
        """심볼 정보 조회"""
        try:
            markets = self.load_markets_sync(market_type)
            if symbol in markets:
                market_info = markets[symbol]
                return {
                    'baseAssetPrecision': market_info.amount_precision,
                    'quotePrecision': market_info.price_precision,
                    'filters': {}  # 간단한 구현
                }
        except Exception as e:
            logger.warning(f"심볼 정보 조회 실패 {symbol}: {e}")

        return None


# 편의를 위한 별칭
BinanceSpot = BinanceExchange
BinanceFutures = BinanceExchange