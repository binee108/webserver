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
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, InvalidOperation
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from urllib.parse import urlencode

import aiohttp
import requests

from .base import BaseCryptoExchange
from app.constants import OrderType
from app.exchanges.base import ExchangeError, InvalidOrder, InsufficientFunds
from app.exchanges.models import MarketInfo, Balance, Order, Ticker, Position, PriceQuote
from app.utils.symbol_utils import to_binance_format, from_binance_format

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
    BATCH_ORDERS = "/fapi/v1/batchOrders"  # 배치 주문 엔드포인트


class BinanceExchange(BaseCryptoExchange):
    """
    Binance 통합 거래소 클래스 (Spot + Futures)

    특징:
    - Spot과 Futures를 하나의 클래스로 통합
    - market_type 파라미터로 Spot/Futures 구분
    - 메모리 캐싱으로 성능 최적화
    - 1인 사용자에 최적화된 단순한 구조
    """

    def __init__(self, api_key: str, api_secret: str, testnet: bool = False):
        # BaseCryptoExchange.__init__이 api_key, secret, testnet 속성을 설정함
        super().__init__(api_key, api_secret, testnet)

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

        # 주문 타입 매핑 추적 (거래소 특수성 캡슐화)
        self.order_type_mappings = {}  # order_id -> original_order_type

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

    def _convert_to_binance_format(self, order_type: str, side: str) -> str:
        """프로젝트 주문 타입을 Binance API 형식으로 변환"""
        if order_type.upper() == 'STOP_LIMIT':
            # Binance Futures에서 STOP_LIMIT는 STOP 타입으로 구현 (트리거 후 지정가 주문)
            logger.info(f"🔄 주문 타입 변환: STOP_LIMIT → STOP")
            return 'STOP'
        return order_type

    def _convert_from_binance_format(self, binance_type: str, order_id: str = None) -> str:
        """Binance 타입을 프로젝트 표준으로 변환"""
        # 로컬 메모리에서 원본 타입 조회
        if order_id and order_id in self.order_type_mappings:
            original_type = self.order_type_mappings[order_id]
            logger.debug(f"🔄 타입 복원: {binance_type} → {original_type} (order_id: {order_id})")
            return original_type

        # 일반적인 변환
        if binance_type == 'STOP':
            return 'STOP_LIMIT'
        return binance_type.lower()

    def _store_order_mapping(self, order_id: str, original_type: str):
        """주문 타입 매핑을 로컬 메모리에 저장"""
        self.order_type_mappings[order_id] = original_type
        logger.debug(f"💾 주문 매핑 저장: {order_id} → {original_type}")

    def _cleanup_order_mapping(self, order_id: str):
        """완료된 주문의 매핑 정보 정리"""
        if order_id in self.order_type_mappings:
            del self.order_type_mappings[order_id]
            logger.debug(f"🗑️ 주문 매핑 정리: {order_id}")

    def _create_signature(self, params: Dict[str, Any]) -> str:
        """API 서명 생성"""
        query_string = urlencode(params)
        return hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    async def _request_async(self, method: str, url: str, params: Dict[str, Any] = None,
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
            params['recvWindow'] = 5000  # 5초 허용 시간차 (시간 동기화 문제 해결)
            params['signature'] = self._create_signature(params)

        try:
            response = None
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
            # 응답이 JSON이 아닌 경우 (HTML 오류 페이지 등)
            try:
                raw_text = await response.text()
                logger.error(f"Binance API 비정상 응답 (상태: {response.status}): {raw_text[:200]}")
            except:
                logger.error(f"Binance API 응답 읽기 실패 (상태: {getattr(response, 'status', 'unknown')})")
            raise ExchangeError(f"Binance API 응답 형식 오류: {str(e)}")
        except Exception as e:
            # 모든 기타 오류를 포착하여 상세 정보 제공
            error_details = {
                'error': str(e),
                'error_type': type(e).__name__,
                'url': url,
                'method': method,
                'signed': signed
            }

            if 'response' in locals() and response:
                error_details['response_status'] = response.status

            if 'data' in locals():
                error_details['response_data'] = data

            logger.error(f"Binance API 요청 실패: {error_details}")
            raise ExchangeError(f"Binance API 오류: {str(e)}")

    def _request(self, method: str, url: str, params: Dict[str, Any] = None,
                signed: bool = False) -> Dict[str, Any]:
        """HTTP 요청 실행 (동기 버전)"""
        if params is None:
            params = {}

        headers = {
            'User-Agent': 'Binance-Native-Client/1.0',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        if self.api_key:
            headers['X-MBX-APIKEY'] = self.api_key

        if signed:
            params['timestamp'] = int(time.time() * 1000)
            params['recvWindow'] = 5000  # 5초 허용 시간차 (시간 동기화 문제 해결)
            params['signature'] = self._create_signature(params)

        try:
            response = None
            if method.upper() == 'GET':
                response = requests.get(url, params=params, headers=headers, timeout=30)
            elif method.upper() == 'POST':
                response = requests.post(url, data=params, headers=headers, timeout=30)
            elif method.upper() == 'DELETE':
                response = requests.delete(url, params=params, headers=headers, timeout=30)
            else:
                raise ValueError(f"지원하지 않는 HTTP 메서드: {method}")

            # HTTP 400 에러의 경우 Binance 에러 메시지 먼저 읽기
            if response.status_code >= 400:
                try:
                    error_data = response.json()
                    error_msg = error_data.get('msg', 'Unknown error')
                    error_code = error_data.get('code', response.status_code)
                    logger.error(f"❌ Binance API 에러 [{error_code}]: {error_msg}")
                    raise ExchangeError(f"Binance API Error [{error_code}]: {error_msg}")
                except (ValueError, KeyError):
                    # JSON 파싱 실패시 기본 에러 처리
                    response.raise_for_status()

            data = response.json()

            if 'code' in data and data['code'] != 200:
                raise ExchangeError(f"Binance API 오류: {data.get('msg', 'Unknown error')}")

            return data

        except requests.RequestException as e:
            raise ExchangeError(f"네트워크 오류: {str(e)}")
        except json.JSONDecodeError as e:
            # 응답이 JSON이 아닌 경우 (HTML 오류 페이지 등)
            try:
                raw_text = response.text if response else "No response"
                logger.error(f"Binance API 비정상 응답 (상태: {response.status_code if response else 'unknown'}): {raw_text[:200]}")
            except:
                logger.error(f"Binance API 응답 읽기 실패")
            raise ExchangeError(f"Binance API 응답 형식 오류: {str(e)}")
        except Exception as e:
            # 모든 기타 오류를 포착하여 상세 정보 제공
            error_details = {
                'error': str(e),
                'error_type': type(e).__name__,
                'url': url,
                'method': method,
                'signed': signed
            }

            if response:
                error_details['response_status'] = response.status_code

            logger.error(f"Binance API 요청 실패: {error_details}")
            raise ExchangeError(f"Binance API 오류: {str(e)}")

    def load_markets_impl(self, market_type: str = 'spot', reload: bool = False) -> Dict[str, MarketInfo]:
        """마켓 정보 로드 (동기 구현)"""
        cache_key = f"{market_type}_markets"

        # 캐시 확인
        if not reload and cache_key in self.cache_time:
            if time.time() - self.cache_time[cache_key] < self.cache_ttl:
                return getattr(self, f"{market_type}_markets_cache", {})

        base_url = self._get_base_url(market_type)
        endpoints = self._get_endpoints(market_type)

        url = f"{base_url}{endpoints.EXCHANGE_INFO}"
        data = self._request('GET', url)

        markets = {}
        for symbol_info in data.get('symbols', []):
            if symbol_info['status'] != 'TRADING':
                continue

            binance_symbol = symbol_info['symbol']
            # Binance 형식(BTCUSDT) → 표준 형식(BTC/USDT)
            standard_symbol = from_binance_format(binance_symbol)

            # MarketInfo.from_binance_* 메서드를 사용하여 filters 정보 완전 파싱
            if market_type.lower() == 'spot':
                markets[standard_symbol] = MarketInfo.from_binance_spot(symbol_info)
            else:  # futures
                markets[standard_symbol] = MarketInfo.from_binance_futures(symbol_info)

        # 캐시 업데이트
        if market_type == 'spot':
            self.spot_markets_cache = markets
        else:
            self.futures_markets_cache = markets

        self.cache_time[cache_key] = time.time()

        logger.info(f"✅ {market_type.title()} 마켓 정보 로드 완료: {len(markets)}개")
        return markets

    def fetch_price_quotes(self, market_type: str = 'spot',
                           symbols: Optional[List[str]] = None) -> Dict[str, PriceQuote]:
        """표준화된 현재가 정보 조회"""
        market_type_lower = (market_type or 'spot').lower()
        base_url = self._get_base_url(market_type_lower)
        endpoints = self._get_endpoints(market_type_lower)
        url = f"{base_url}{endpoints.TICKER_PRICE}"

        try:
            response = self._request('GET', url)
        except Exception as e:
            logger.error(f"Binance 가격 조회 실패: market_type={market_type_lower} error={e}")
            return {}

        if isinstance(response, dict):
            data_items = [response]
        else:
            data_items = response or []

        symbol_filter = {s.upper() for s in symbols} if symbols else None
        timestamp = datetime.utcnow()
        standard_market_type = 'FUTURES' if market_type_lower == 'futures' else 'SPOT'

        quotes: Dict[str, PriceQuote] = {}
        for item in data_items:
            symbol = item.get('symbol')
            price = item.get('price')
            if not symbol or price is None:
                continue

            symbol_upper = symbol.upper()
            if symbol_filter and symbol_upper not in symbol_filter:
                continue

            last_price = Decimal(str(price))
            bid_value = item.get('bidPrice', price)
            ask_value = item.get('askPrice', price)
            volume_value = item.get('volume')

            quotes[symbol_upper] = PriceQuote(
                symbol=symbol_upper,
                exchange='BINANCE',
                market_type=standard_market_type,
                last_price=last_price,
                bid_price=Decimal(str(bid_value)) if bid_value is not None else None,
                ask_price=Decimal(str(ask_value)) if ask_value is not None else None,
                volume=Decimal(str(volume_value)) if volume_value is not None else None,
                timestamp=timestamp,
                raw=item
            )

        return quotes

    def fetch_balance_impl(self, market_type: str = 'spot') -> Dict[str, Balance]:
        """잔액 조회 (동기 구현)"""
        base_url = self._get_base_url(market_type)
        endpoints = self._get_endpoints(market_type)

        url = f"{base_url}{endpoints.ACCOUNT}"
        data = self._request('GET', url, signed=True)

        balances = {}
        balance_key = 'balances' if market_type == 'spot' else 'assets'

        for balance_info in data.get(balance_key, []):
            asset = balance_info.get('asset') or balance_info.get('currency')
            if not asset:
                continue

            if market_type.lower() == 'futures':
                wallet_balance = Decimal(balance_info.get('walletBalance', '0'))
                available_balance = Decimal(balance_info.get('availableBalance', '0'))
                initial_margin = Decimal(balance_info.get('initialMargin', '0'))
                maint_margin = Decimal(balance_info.get('maintMargin', '0'))

                free = available_balance
                locked = initial_margin + maint_margin
                total = wallet_balance
            else:
                # Spot API 필드 매핑
                free = Decimal(balance_info.get('free', '0'))
                locked = Decimal(balance_info.get('locked', '0'))
                total = free + locked

            # 0이 아닌 잔액만 포함
            if total > 0:
                balances[asset] = Balance(
                    asset=asset,
                    free=free,
                    locked=locked,
                    total=total
                )

        logger.info(f"✅ {market_type.title()} 잔액 조회 완료: {len(balances)}개")
        return balances

    def _prepare_order_params(self, original_order_type: str, binance_symbol: str,
                             side: str, binance_order_type: str, amount: Decimal,
                             price: Optional[Decimal], params: Dict[str, Any]) -> Dict[str, Any]:
        """
        주문 파라미터 준비 (DRY - 동기/비동기 공통 로직)

        Args:
            original_order_type (str): 원본 주문 타입 (MARKET, LIMIT, STOP_MARKET, STOP_LIMIT)
            binance_symbol (str): Binance 형식 심볼 (BTCUSDT)
            side (str): 주문 방향 (buy, sell)
            binance_order_type (str): Binance API 형식 주문 타입
            amount (Decimal): 주문 수량
            price (Optional[Decimal]): 주문 가격 (LIMIT 타입인 경우 필수)
            params (Dict[str, Any]): 추가 파라미터 (stopPrice 등)

        Returns:
            Dict[str, Any]: Binance API 호출용 주문 파라미터

        Raises:
            InvalidOrder: 필수 파라미터 누락 또는 지원하지 않는 주문 타입

        Examples:
            >>> params = self._prepare_order_params(
            ...     'LIMIT', 'BTCUSDT', 'buy', 'LIMIT', Decimal('0.001'),
            ...     Decimal('50000'), {}
            ... )
            >>> params['type']
            'LIMIT'
            >>> params['timeInForce']
            'GTC'
        """
        order_params = {
            'symbol': binance_symbol,
            'side': side.upper(),
            'type': binance_order_type.upper(),
            'quantity': str(amount)
        }

        # OrderType별 파라미터 설정 - 체계적인 timeInForce 처리
        if original_order_type.upper() == OrderType.MARKET:
            # MARKET: timeInForce 불필요, price 불필요
            logger.info("🔄 MARKET 주문: timeInForce, price 파라미터 제외")

        elif original_order_type.upper() == OrderType.LIMIT:
            # LIMIT: price 필수, timeInForce = GTC
            if not price:
                raise InvalidOrder(f"LIMIT 주문은 price 파라미터가 필수입니다. price={price}")
            order_params['price'] = str(price)
            order_params['timeInForce'] = 'GTC'
            logger.info(f"🔄 LIMIT 주문: price={price}, timeInForce=GTC")

        elif original_order_type.upper() == OrderType.STOP_MARKET:
            # STOP_MARKET: stopPrice 필수, price 불필요, timeInForce 불필요
            if not params.get('stopPrice'):
                raise InvalidOrder(f"STOP_MARKET 주문은 stopPrice 파라미터가 필수입니다.")
            order_params['stopPrice'] = str(params['stopPrice'])
            logger.info(f"🔄 STOP_MARKET 주문: stopPrice={params['stopPrice']}, timeInForce 제외")

        elif original_order_type.upper() == OrderType.STOP_LIMIT:
            # STOP_LIMIT: price, stopPrice 모두 필수, timeInForce = GTC
            if not price:
                raise InvalidOrder(f"STOP_LIMIT 주문은 price 파라미터가 필수입니다. price={price}")
            if not params.get('stopPrice'):
                raise InvalidOrder(f"STOP_LIMIT 주문은 stopPrice 파라미터가 필수입니다.")
            order_params['price'] = str(price)
            order_params['stopPrice'] = str(params['stopPrice'])
            order_params['timeInForce'] = 'GTC'
            logger.info(f"🔄 STOP_LIMIT 주문: price={price}, stopPrice={params['stopPrice']}, timeInForce=GTC")

        else:
            raise InvalidOrder(f"지원하지 않는 주문 타입: {original_order_type}")

        # 추가 파라미터 처리 (이미 처리된 것들 제외)
        processed_keys = {'stopPrice'}
        remaining_params = {k: v for k, v in params.items() if k not in processed_keys}
        order_params.update(remaining_params)

        return order_params

    def create_order_impl(self, symbol: str, order_type: str, side: str,
                         amount: Decimal, price: Optional[Decimal] = None,
                         market_type: str = 'spot', **params) -> Order:
        """주문 생성 (동기 구현)"""
        base_url = self._get_base_url(market_type)
        endpoints = self._get_endpoints(market_type)

        # 0. 심볼 변환: 표준 형식(BTC/USDT) → Binance 형식(BTCUSDT)
        binance_symbol = to_binance_format(symbol)
        logger.info(f"🔄 심볼 변환: {symbol} → {binance_symbol}")

        # 1. 입력 변환 및 파라미터 준비 (DRY - 공통 로직)
        original_order_type = order_type
        binance_order_type = self._convert_to_binance_format(order_type, side)
        order_params = self._prepare_order_params(
            original_order_type, binance_symbol, side,
            binance_order_type, amount, price, params
        )

        url = f"{base_url}{endpoints.ORDER}"
        logger.debug(f"🔍 바이낸스 API 호출: {url}")
        logger.debug(f"🔍 주문 파라미터: {order_params}")
        data = self._request('POST', url, order_params, signed=True)
        logger.debug(f"🔍 바이낸스 API 응답: {data}")

        # 시장가 주문의 경우 즉시 주문 상태 재조회 (체결 정보 확인)
        if order_type.upper() == 'MARKET' and data.get('status') == 'NEW':
            logger.info(f"🔄 시장가 주문 상태 재조회: {data.get('orderId')}")
            try:
                # 잠시 대기 후 주문 상태 조회
                import time
                time.sleep(0.1)  # 100ms 대기

                order_status_url = f"{base_url}{endpoints.ORDER}"
                status_params = {
                    'symbol': binance_symbol,  # 변환된 심볼 사용
                    'orderId': data.get('orderId')
                }

                updated_data = self._request('GET', order_status_url, status_params, signed=True)
                logger.info(f"🔍 재조회된 주문 상태: {updated_data}")

                # 체결량이 있으면 업데이트된 데이터 사용
                if float(updated_data.get('executedQty', '0')) > 0:
                    data = updated_data
                    logger.info(f"✅ 시장가 주문 체결 확인: 체결량={updated_data.get('executedQty')}")

            except Exception as e:
                logger.warning(f"⚠️ 주문 상태 재조회 실패: {e}")

        # 2. 주문 매핑 저장 (로컬 메모리)
        order_id = str(data.get('orderId'))
        if order_id and original_order_type != binance_order_type:
            self._store_order_mapping(order_id, original_order_type)

        # 3. 응답 변환: Binance 응답 → 프로젝트 표준 형식
        return self._parse_order(data, market_type, original_order_type)

    def cancel_order_impl(self, order_id: str, symbol: str, market_type: str = 'spot') -> Dict[str, Any]:
        """주문 취소 (동기 구현)"""
        base_url = self._get_base_url(market_type)
        endpoints = self._get_endpoints(market_type)

        # 심볼 변환: 표준 형식 → Binance 형식
        binance_symbol = to_binance_format(symbol)

        params = {
            'symbol': binance_symbol,
            'orderId': order_id
        }

        url = f"{base_url}{endpoints.ORDER}"
        data = self._request('DELETE', url, params, signed=True)

        return {
            'success': True,
            'order_id': str(data.get('orderId')),
            'symbol': data.get('symbol'),
            'status': data.get('status'),
            'message': f"주문 {order_id} 취소 완료"
        }

    def fetch_positions_impl(self) -> List[Position]:
        """포지션 조회 (Futures 전용, 동기 구현)"""
        base_url = self._get_base_url('futures')

        url = f"{base_url}{FuturesEndpoints.POSITION_RISK}"
        data = self._request('GET', url, signed=True)

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
                    mark_price=Decimal(pos_info.get('markPrice', '0')),
                    margin=Decimal(pos_info.get('initialMargin', '0'))
                ))

        return positions

    def fetch_open_orders_impl(self, symbol: Optional[str] = None, market_type: str = 'spot') -> List[Order]:
        """미체결 주문 조회 (동기 구현)"""
        base_url = self._get_base_url(market_type)
        endpoints = self._get_endpoints(market_type)

        params = {}
        if symbol:
            # 심볼 변환: 표준 형식 → Binance 형식
            binance_symbol = to_binance_format(symbol)
            params['symbol'] = binance_symbol

        url = f"{base_url}{endpoints.OPEN_ORDERS}"
        data = self._request('GET', url, params, signed=True)

        return [self._parse_order(order_data, market_type) for order_data in data]

    def fetch_order_impl(self, symbol: str, order_id: str, market_type: str = 'spot') -> Order:
        """단일 주문 상세 조회 (동기 구현)"""
        base_url = self._get_base_url(market_type)
        endpoints = self._get_endpoints(market_type)

        # 심볼 변환: 표준 형식 → Binance 형식
        binance_symbol = to_binance_format(symbol)

        params = {
            'symbol': binance_symbol,
            'orderId': order_id
        }

        url = f"{base_url}{endpoints.ORDER}"
        data = self._request('GET', url, params, signed=True)

        logger.debug(f"🔍 주문 상세 조회 완료: order_id={order_id}, market_type={market_type}")
        return self._parse_order(data, market_type)

    async def load_markets_async(self, market_type: str = 'spot', reload: bool = False) -> Dict[str, MarketInfo]:
        """마켓 정보 로드"""
        cache_key = f"{market_type}_markets"

        # 캐시 확인
        if not reload and cache_key in self.cache_time:
            if time.time() - self.cache_time[cache_key] < self.cache_ttl:
                return getattr(self, f"{market_type}_markets_cache", {})

        base_url = self._get_base_url(market_type)
        endpoints = self._get_endpoints(market_type)

        url = f"{base_url}{endpoints.EXCHANGE_INFO}"
        data = await self._request_async('GET', url)

        markets = {}
        for symbol_info in data.get('symbols', []):
            if symbol_info['status'] != 'TRADING':
                continue

            binance_symbol = symbol_info['symbol']
            # Binance 형식(BTCUSDT) → 표준 형식(BTC/USDT)
            standard_symbol = from_binance_format(binance_symbol)

            # MarketInfo.from_binance_* 메서드를 사용하여 filters 정보 완전 파싱
            if market_type.lower() == 'spot':
                markets[standard_symbol] = MarketInfo.from_binance_spot(symbol_info)
            else:  # futures
                markets[standard_symbol] = MarketInfo.from_binance_futures(symbol_info)

        # 캐시 업데이트
        if market_type == 'spot':
            self.spot_markets_cache = markets
        else:
            self.futures_markets_cache = markets

        self.cache_time[cache_key] = time.time()

        logger.info(f"✅ {market_type.title()} 마켓 정보 로드 완료: {len(markets)}개")
        return markets

    async def fetch_balance_async(self, market_type: str = 'spot') -> Dict[str, Balance]:
        """잔액 조회"""
        base_url = self._get_base_url(market_type)
        endpoints = self._get_endpoints(market_type)

        url = f"{base_url}{endpoints.ACCOUNT}"
        data = await self._request_async('GET', url, signed=True)

        # 디버깅을 위해 API 응답 로깅 (DEBUG 레벨)
        logger.debug(f"🔍 Balance API Response ({market_type}): {json.dumps(data, indent=2, default=str)}")

        balances = {}
        balance_key = 'balances' if market_type == 'spot' else 'assets'

        for balance_info in data.get(balance_key, []):
            asset = balance_info.get('asset') or balance_info.get('currency')
            if not asset:
                continue

            # 디버깅을 위해 개별 자산 정보 로깅 (DEBUG 레벨)
            logger.debug(f"🔍 Processing asset {asset}: {json.dumps(balance_info, indent=2, default=str)}")

            if market_type.lower() == 'futures':
                # Binance Futures API 필드 매핑 (/fapi/v2/account)
                # availableBalance: 사용 가능한 잔고
                # walletBalance: 전체 지갑 잔고
                # marginBalance: 마진 잔고 (unrealizedProfit 포함)
                # initialMargin: 사용 중인 초기 마진
                
                wallet_balance = Decimal(balance_info.get('walletBalance', '0'))
                available_balance = Decimal(balance_info.get('availableBalance', '0'))
                initial_margin = Decimal(balance_info.get('initialMargin', '0'))
                maint_margin = Decimal(balance_info.get('maintMargin', '0'))
                
                # Futures에서는 walletBalance가 total, availableBalance가 free
                free = available_balance
                locked = initial_margin + maint_margin
                total = wallet_balance
                
                logger.info(f"🔍 Futures balance for {asset}: wallet={wallet_balance}, available={available_balance}, "
                           f"initial_margin={initial_margin}, maint_margin={maint_margin}")
                logger.info(f"🔍 Calculated: free={free}, locked={locked}, total={total}")
                
            else:
                # Spot API 필드 매핑 (/api/v3/account)
                free = Decimal(balance_info.get('free', '0'))
                locked = Decimal(balance_info.get('locked', '0'))
                total = free + locked

            # 0이 아닌 잔고만 포함 (total 기준으로 판단)
            if total > 0:
                balances[asset] = Balance(
                    asset=asset,
                    free=free,
                    locked=locked,
                    total=total
                )
                logger.info(f"✅ Added {asset} balance: free={free}, locked={locked}, total={total}")
            else:
                logger.debug(f"⏭️ Skipped {asset} (total=0): free={free}, locked={locked}")

        logger.info(f"✅ Total balances found ({market_type}): {len(balances)}")
        return balances

    async def fetch_positions_async(self) -> List[Position]:
        """포지션 조회 (Futures 전용)"""
        base_url = self._get_base_url('futures')

        url = f"{base_url}{FuturesEndpoints.POSITION_RISK}"
        data = await self._request_async('GET', url, signed=True)

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
                    mark_price=Decimal(pos_info.get('markPrice', '0')),
                    margin=Decimal(pos_info.get('initialMargin', '0'))
                ))

        return positions

    async def create_order_async(self, symbol: str, order_type: str, side: str,
                          amount: Decimal, price: Optional[Decimal] = None,
                          market_type: str = 'spot', **params) -> Order:
        """주문 생성"""
        base_url = self._get_base_url(market_type)
        endpoints = self._get_endpoints(market_type)

        # 0. 심볼 변환: 표준 형식(BTC/USDT) → Binance 형식(BTCUSDT)
        binance_symbol = to_binance_format(symbol)
        logger.info(f"🔄 심볼 변환 (비동기): {symbol} → {binance_symbol}")

        # 1. 입력 변환 및 파라미터 준비 (DRY - 공통 로직)
        original_order_type = order_type
        binance_order_type = self._convert_to_binance_format(order_type, side)
        order_params = self._prepare_order_params(
            original_order_type, binance_symbol, side,
            binance_order_type, amount, price, params
        )


        url = f"{base_url}{endpoints.ORDER}"
        data = await self._request_async('POST', url, order_params, signed=True)

        # 주문 매핑 저장 (동기 버전과 동일)
        order_id = str(data.get('orderId'))
        if order_id and original_order_type != binance_order_type:
            self._store_order_mapping(order_id, original_order_type)

        return self._parse_order(data, market_type, original_order_type)

    async def cancel_order_async(self, order_id: str, symbol: str,
                          market_type: str = 'spot') -> Dict[str, Any]:
        """주문 취소"""
        base_url = self._get_base_url(market_type)
        endpoints = self._get_endpoints(market_type)

        # 심볼 변환: 표준 형식 → Binance 형식
        binance_symbol = to_binance_format(symbol)

        params = {
            'symbol': binance_symbol,
            'orderId': order_id
        }

        url = f"{base_url}{endpoints.ORDER}"
        return await self._request_async('DELETE', url, params, signed=True)

    async def fetch_open_orders_async(self, symbol: Optional[str] = None,
                               market_type: str = 'spot') -> List[Order]:
        """미체결 주문 조회"""
        base_url = self._get_base_url(market_type)
        endpoints = self._get_endpoints(market_type)

        params = {}
        if symbol:
            # 심볼 변환: 표준 형식 → Binance 형식
            binance_symbol = to_binance_format(symbol)
            params['symbol'] = binance_symbol

        url = f"{base_url}{endpoints.OPEN_ORDERS}"
        data = await self._request_async('GET', url, params, signed=True)

        return [self._parse_order(order_data, market_type) for order_data in data]

    def _parse_order(self, order_data: Dict[str, Any], market_type: str, original_type: str = None) -> Order:
        """주문 데이터 파싱 - Binance 응답을 프로젝트 표준으로 변환"""
        # 0. 심볼 변환: Binance 형식(BTCUSDT) → 표준 형식(BTC/USDT)
        binance_symbol = order_data['symbol']
        standard_symbol = from_binance_format(binance_symbol)
        logger.debug(f"🔄 응답 심볼 변환: {binance_symbol} → {standard_symbol}")

        # timestamp 필드 처리 - 다양한 필드명 지원
        timestamp = order_data.get('time') or order_data.get('updateTime') or order_data.get('transactTime', 0)

        # 주문 타입 변환: Binance → 프로젝트 표준
        order_id = str(order_data['orderId'])
        binance_type = order_data['type']

        if original_type:
            # 주문 생성시 전달받은 원본 타입 사용
            converted_type = original_type.lower()
        else:
            # 일반 변환 (조회 등에서 사용)
            converted_type = self._convert_from_binance_format(binance_type, order_id)

        # 시장가 주문의 경우 평균 체결가 계산
        executed_qty = Decimal(order_data.get('executedQty', '0'))
        cumulative_quote = Decimal(order_data.get('cummulativeQuoteQty', '0'))
        avg_price = None

        avg_price_field = order_data.get('avgPrice')
        if avg_price_field:
            try:
                avg_price = Decimal(avg_price_field)
            except (InvalidOperation, TypeError):
                avg_price = None

        if (avg_price is None or avg_price <= 0) and cumulative_quote > 0 and executed_qty > 0:
            avg_price = cumulative_quote / executed_qty
            logger.debug(
                "📊 평균가 계산 (누적 체결 기반): %s / %s = %s",
                cumulative_quote,
                executed_qty,
                avg_price
            )

        limit_price = None
        if order_data.get('price') and order_data['price'] != '0':
            try:
                limit_price = Decimal(order_data['price'])
            except (InvalidOperation, TypeError):
                limit_price = None

        return Order(
            id=order_id,
            symbol=standard_symbol,  # 표준 형식 심볼 사용
            side=order_data['side'].lower(),
            amount=Decimal(order_data['origQty']),
            price=limit_price,
            stop_price=Decimal(order_data['stopPrice']) if order_data.get('stopPrice') else None,
            filled=executed_qty,
            remaining=Decimal(order_data['origQty']) - executed_qty,
            status=order_data['status'],  # 원본 거래소 상태 유지
            timestamp=timestamp,
            type=converted_type,  # 변환된 타입 사용
            market_type=market_type.upper(),
            average=avg_price if avg_price and avg_price > 0 else None,
            cost=cumulative_quote if cumulative_quote > 0 else None
        )


    # CCXT 호환 메서드들 (동기)
    def fetch_balance(self, market_type: str = 'spot') -> Dict[str, Balance]:
        """잔액 조회 (동기)"""
        return self.fetch_balance_impl(market_type)

    def create_market_order(self, symbol: str, side: str, amount: float,
                           market_type: str = 'spot') -> Order:
        """시장가 주문 (동기 래퍼)"""
        return self.create_order_impl(
            symbol, OrderType.MARKET, side, Decimal(str(amount)),
            market_type=market_type
        )

    def create_limit_order(self, symbol: str, side: str, amount: float,
                          price: float, market_type: str = 'spot') -> Order:
        """지정가 주문 (동기 래퍼)"""
        return self.create_order_impl(
            symbol, OrderType.LIMIT, side, Decimal(str(amount)),
            Decimal(str(price)), market_type=market_type
        )


    def create_order(self, symbol: str, order_type: str, side: str,
                         amount: Decimal, price: Optional[Decimal] = None,
                         market_type: str = 'spot', **params) -> Order:
        """주문 생성 (동기 래퍼)"""
        return self.create_order_impl(symbol, order_type, side, amount, price, market_type, **params)

    def load_markets(self, market_type: str = 'spot', reload: bool = False) -> Dict[str, MarketInfo]:
        """마켓 정보 로드 (동기)"""
        return self.load_markets_impl(market_type, reload)


    def cancel_order(self, order_id: str, symbol: str, market_type: str = 'spot') -> Dict[str, Any]:
        """주문 취소 (동기)"""
        return self.cancel_order_impl(order_id, symbol, market_type)

    def fetch_open_orders(self, symbol: Optional[str] = None, market_type: str = 'spot') -> List[Order]:
        """미체결 주문 조회 (동기)"""
        return self.fetch_open_orders_impl(symbol, market_type)

    def fetch_order(self, symbol: str, order_id: str, market_type: str = 'spot') -> Order:
        """단일 주문 상세 조회 (동기)"""
        return self.fetch_order_impl(symbol, order_id, market_type)

    def fetch_positions(self) -> List[Position]:
        """포지션 조회 (동기)"""
        return self.fetch_positions_impl()
    # 심볼 정보 조회 (precision 서비스용)
    def get_symbol_info(self, symbol: str, market_type: str = 'spot') -> Optional[Dict[str, Any]]:
        """심볼 정보 조회"""
        try:
            markets = self.load_markets(market_type)
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

    # ===== 배치 주문 기능 =====

    def create_batch_orders(self, orders: List[Dict[str, Any]], market_type: str = 'spot') -> Dict[str, Any]:
        """배치 주문 생성 (동기 래퍼)"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.create_batch_orders_async(orders, market_type))
        finally:
            loop.close()
            asyncio.set_event_loop(None)

    async def create_batch_orders_async(self, orders: List[Dict[str, Any]], market_type: str = 'spot') -> Dict[str, Any]:
        """
        배치 주문 생성 (BaseExchange 추상 메서드 구현)

        Args:
            orders: 주문 리스트
                [
                    {
                        'symbol': 'BTC/USDT',
                        'side': 'buy',
                        'type': 'LIMIT',
                        'amount': Decimal('0.01'),
                        'price': Decimal('95000'),
                        'params': {...}  # stopPrice 등
                    },
                    ...
                ]
            market_type: 'spot' or 'futures'

        Returns:
            {
                'success': True,
                'results': [
                    {'order_index': 0, 'success': True, 'order_id': '...', 'order': {...}},
                    {'order_index': 1, 'success': False, 'error': '...'},
                    ...
                ],
                'summary': {
                    'total': 5,
                    'successful': 4,
                    'failed': 1
                },
                'implementation': 'NATIVE_BATCH' | 'SEQUENTIAL_FALLBACK'
            }
        """
        if not orders:
            return {
                'success': True,
                'results': [],
                'summary': {'total': 0, 'successful': 0, 'failed': 0},
                'implementation': 'NONE'
            }

        logger.info(f"📦 배치 주문 시작: {len(orders)}건, market_type={market_type}")

        # market_type에 따라 분기
        if market_type.lower() == 'futures':
            return await self._create_batch_orders_futures(orders)
        else:
            return await self._create_batch_orders_sequential(orders, market_type)

    async def _create_batch_orders_futures(self, orders: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Binance Futures 네이티브 배치 API 사용

        Binance Futures Batch Orders API:
        - 엔드포인트: POST /fapi/v1/batchOrders
        - 최대 5건/요청
        - batchOrders 파라미터로 JSON 문자열 전송
        """
        base_url = self._get_base_url('futures')
        endpoints = self._get_endpoints('futures')

        all_results = []
        total_orders = len(orders)
        successful_count = 0
        failed_count = 0

        # 5건씩 청크로 분할
        chunk_size = 5
        for chunk_idx in range(0, total_orders, chunk_size):
            chunk = orders[chunk_idx:chunk_idx + chunk_size]
            chunk_start_idx = chunk_idx

            logger.info(f"📦 청크 {chunk_idx // chunk_size + 1} 처리: {len(chunk)}건 (인덱스 {chunk_start_idx}~{chunk_start_idx + len(chunk) - 1})")

            try:
                # Binance 배치 주문 형식으로 변환
                batch_orders_payload = []
                for order_idx, order in enumerate(chunk):
                    global_idx = chunk_start_idx + order_idx

                    # 심볼 변환: 표준 형식(BTC/USDT) → Binance 형식(BTCUSDT)
                    binance_symbol = to_binance_format(order['symbol'])

                    # 주문 타입 변환
                    original_type = order['type']
                    binance_type = self._convert_to_binance_format(original_type, order['side'])

                    # 기본 파라미터
                    order_params = {
                        'symbol': binance_symbol,
                        'side': order['side'].upper(),
                        'type': binance_type.upper(),
                        'quantity': str(order['amount'])
                    }

                    # 주문 타입별 파라미터 추가
                    price = order.get('price')
                    params = order.get('params', {})

                    if original_type.upper() == OrderType.MARKET:
                        # MARKET: price, timeInForce 불필요
                        pass

                    elif original_type.upper() == OrderType.LIMIT:
                        # LIMIT: price 필수, timeInForce = GTC
                        if not price:
                            raise InvalidOrder(f"LIMIT 주문은 price가 필수입니다 (order_index={global_idx})")
                        order_params['price'] = str(price)
                        order_params['timeInForce'] = 'GTC'

                    elif original_type.upper() == OrderType.STOP_MARKET:
                        # STOP_MARKET: stopPrice 필수
                        if not params.get('stopPrice'):
                            raise InvalidOrder(f"STOP_MARKET 주문은 stopPrice가 필수입니다 (order_index={global_idx})")
                        order_params['stopPrice'] = str(params['stopPrice'])

                    elif original_type.upper() == OrderType.STOP_LIMIT:
                        # STOP_LIMIT: price, stopPrice 모두 필수, timeInForce = GTC
                        if not price:
                            raise InvalidOrder(f"STOP_LIMIT 주문은 price가 필수입니다 (order_index={global_idx})")
                        if not params.get('stopPrice'):
                            raise InvalidOrder(f"STOP_LIMIT 주문은 stopPrice가 필수입니다 (order_index={global_idx})")
                        order_params['price'] = str(price)
                        order_params['stopPrice'] = str(params['stopPrice'])
                        order_params['timeInForce'] = 'GTC'

                    batch_orders_payload.append(order_params)

                # API 호출
                url = f"{base_url}{endpoints.BATCH_ORDERS}"
                api_params = {
                    'batchOrders': json.dumps(batch_orders_payload)
                }

                logger.debug(f"🔍 배치 주문 API 호출: {url}")
                logger.debug(f"🔍 페이로드: {batch_orders_payload}")

                response = await self._request_async('POST', url, api_params, signed=True)

                logger.debug(f"🔍 배치 주문 응답: {response}")

                # 응답 파싱 (응답 순서 = 요청 순서 보장)
                for order_idx, order_response in enumerate(response):
                    global_idx = chunk_start_idx + order_idx
                    original_order = chunk[order_idx]

                    # 실패 체크 (code 필드 존재 시 실패)
                    if 'code' in order_response:
                        error_msg = order_response.get('msg', 'Unknown error')
                        logger.warning(f"⚠️ 주문 {global_idx} 실패: {error_msg}")
                        all_results.append({
                            'order_index': global_idx,
                            'success': False,
                            'error': error_msg
                        })
                        failed_count += 1
                    else:
                        # 성공
                        order_obj = self._parse_order(order_response, 'futures', original_order['type'])

                        # 주문 매핑 저장
                        if original_order['type'] != self._convert_to_binance_format(original_order['type'], original_order['side']):
                            self._store_order_mapping(order_obj.id, original_order['type'])

                        logger.info(f"✅ 주문 {global_idx} 성공: order_id={order_obj.id}")
                        all_results.append({
                            'order_index': global_idx,
                            'success': True,
                            'order_id': order_obj.id,
                            'order': order_obj.__dict__
                        })
                        successful_count += 1

            except Exception as e:
                # 청크 전체 실패
                logger.error(f"❌ 청크 {chunk_idx // chunk_size + 1} 실패: {e}")
                for order_idx in range(len(chunk)):
                    global_idx = chunk_start_idx + order_idx
                    all_results.append({
                        'order_index': global_idx,
                        'success': False,
                        'error': str(e)
                    })
                    failed_count += 1

        # 배치 완료 로깅
        num_chunks = (total_orders + chunk_size - 1) // chunk_size  # 올림 계산
        logger.info(
            f"📦 Futures 배치 주문 완료: {successful_count}/{total_orders} 성공, "
            f"implementation=NATIVE_BATCH, chunks={num_chunks}"
        )

        return {
            'success': True,
            'results': all_results,
            'summary': {
                'total': total_orders,
                'successful': successful_count,
                'failed': failed_count
            },
            'implementation': 'NATIVE_BATCH'
        }

    async def _create_batch_orders_sequential(self, orders: List[Dict[str, Any]], market_type: str) -> Dict[str, Any]:
        """
        Spot 폴백: 병렬 순차 처리 (asyncio.gather 사용)

        Note:
            - Spot은 배치 API 미지원 → 개별 주문을 병렬로 실행
            - 각 주문의 성공/실패를 독립적으로 처리
            - Rate limit 방지를 위해 동시 실행 수 제한 (Semaphore)
        """
        logger.info(f"📦 병렬 순차 처리 시작: {len(orders)}건")

        # Rate limit 방지: 동시 최대 10개 요청으로 제한
        MAX_CONCURRENT = 10
        semaphore = asyncio.Semaphore(MAX_CONCURRENT)

        async def execute_with_limit(idx: int, order: Dict[str, Any]) -> Dict[str, Any]:
            """Rate limit 제어와 함께 단일 주문 실행"""
            async with semaphore:
                return await self._execute_single_order(idx, order, market_type)

        # 태스크 생성
        tasks = [
            execute_with_limit(idx, order)
            for idx, order in enumerate(orders)
        ]

        # 병렬 실행 (예외를 결과로 반환)
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 결과 집계
        all_results = []
        successful_count = 0
        failed_count = 0

        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                # 예외 발생
                logger.warning(f"⚠️ 주문 {idx} 실패 (예외): {result}")
                all_results.append({
                    'order_index': idx,
                    'success': False,
                    'error': str(result)
                })
                failed_count += 1
            elif result.get('success'):
                all_results.append(result)
                successful_count += 1
            else:
                all_results.append(result)
                failed_count += 1

        # 배치 완료 로깅
        logger.info(
            f"📦 Spot 순차 배치 완료: {successful_count}/{len(orders)} 성공, "
            f"implementation=SEQUENTIAL_FALLBACK"
        )

        return {
            'success': True,
            'results': all_results,
            'summary': {
                'total': len(orders),
                'successful': successful_count,
                'failed': failed_count
            },
            'implementation': 'SEQUENTIAL_FALLBACK'
        }

    async def _execute_single_order(self, order_index: int, order: Dict[str, Any], market_type: str) -> Dict[str, Any]:
        """
        단일 주문 실행 헬퍼 (병렬 순차 처리용)

        Args:
            order_index: 주문 인덱스
            order: 주문 정보
            market_type: 마켓 타입

        Returns:
            성공: {'order_index': idx, 'success': True, 'order_id': '...', 'order': {...}}
            실패: {'order_index': idx, 'success': False, 'error': '...'}
        """
        try:
            # create_order_async 호출
            order_obj = await self.create_order_async(
                symbol=order['symbol'],
                order_type=order['type'],
                side=order['side'],
                amount=order['amount'],
                price=order.get('price'),
                market_type=market_type,
                **order.get('params', {})
            )

            logger.info(f"✅ 주문 {order_index} 성공: order_id={order_obj.id}")
            return {
                'order_index': order_index,
                'success': True,
                'order_id': order_obj.id,
                'order': order_obj.__dict__
            }

        except Exception as e:
            logger.warning(f"⚠️ 주문 {order_index} 실패: {e}")
            return {
                'order_index': order_index,
                'success': False,
                'error': str(e)
            }



# 편의를 위한 별칭
BinanceSpot = BinanceExchange
BinanceFutures = BinanceExchange
