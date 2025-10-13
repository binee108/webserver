# @FEAT:exchange-integration @COMP:exchange @TYPE:crypto-implementation
"""
Bithumb 통합 API 구현 (Spot 전용)

국내 2위 거래소 Bithumb API 구현입니다.
Spot 거래만 지원하며, JWT 기반 인증을 사용합니다.
KRW 및 USDT 마켓을 지원합니다.
"""

import hashlib
import json
import logging
import time
import uuid
from decimal import Decimal
from datetime import datetime
from typing import Dict, List, Optional, Any
from urllib.parse import urlencode

import asyncio
import aiohttp
import jwt
import requests

from .base import BaseCryptoExchange
from app.exchanges.base import ExchangeError, InvalidOrder
from app.exchanges.models import MarketInfo, Balance, Order, PriceQuote
from app.utils.symbol_utils import to_bithumb_format, from_bithumb_format, parse_symbol

logger = logging.getLogger(__name__)

# API 기본 URL
BASE_URL = "https://api.bithumb.com"

# API 버전
API_VERSION = "v1"

# Rate Limits (보수적 추정)
RATE_LIMIT_PER_MINUTE = 300  # ESTIMATED
RATE_LIMIT_PER_SECOND = 5    # ESTIMATED

# API 엔드포인트
class BithumbEndpoints:
    # 공개 API (인증 불필요)
    MARKET_ALL = f"/{API_VERSION}/market/all"  # 마켓 코드 조회
    TICKER = f"/{API_VERSION}/ticker"  # 현재가 정보

    # 인증 필요 API
    ACCOUNTS = f"/{API_VERSION}/accounts"  # 전체 계좌 조회
    ORDER = f"/{API_VERSION}/orders"  # 주문하기
    ORDER_INFO = f"/{API_VERSION}/order"  # 개별 주문 조회
    ORDERS_OPEN = f"/{API_VERSION}/orders"  # 미체결 주문 조회 (state=wait)
    ORDER_CANCEL = f"/{API_VERSION}/order"  # 주문 취소


class BithumbExchange(BaseCryptoExchange):
    """
    Bithumb 거래소 클래스 (Spot 전용)

    특징:
    - KRW, USDT 마켓 지원
    - JWT 기반 인증 (HMAC-SHA256)
    - 국내 2위 거래소
    - Testnet 미지원
    """

    def __init__(self, api_key: str, api_secret: str, testnet: bool = False):
        if testnet:
            logger.error("❌ Bithumb testnet 요청 거부 - testnet 미지원")
            raise ValueError("Bithumb does not support testnet")

        # BaseCryptoExchange.__init__이 api_key, secret, testnet 속성을 설정함
        super().__init__(api_key, api_secret, testnet)

        self.base_url = BASE_URL

        # 캐시
        self.markets_cache = {}
        self.cache_time = {}
        self.cache_ttl = 300  # 5분

        # HTTP 세션
        self.session = None

        logger.info("✅ Bithumb 거래소 초기화")

    async def _init_session(self):
        """HTTP 세션 초기화"""
        if self.session is None:
            timeout = aiohttp.ClientTimeout(total=30)
            connector = aiohttp.TCPConnector(limit=100, limit_per_host=30)
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                headers={'User-Agent': 'Bithumb-Native-Client/1.0'}
            )

    async def close(self):
        """세션 정리"""
        if self.session:
            await self.session.close()
            self.session = None

    def _create_jwt_token(self, query_params: Optional[Dict[str, Any]] = None) -> str:
        """
        JWT 토큰 생성 (Bithumb 인증 방식)

        RCE 예방:
        - query_params 타입 검증 (eval/exec 미사용)
        - 서버 타임스탬프 사용 (클라이언트 입력 금지)
        - SHA512 해시를 통한 query_hash 생성
        """
        # 타임스탬프 추가 (밀리초) - 서버에서 직접 생성
        current_ts = int(time.time() * 1000)

        payload = {
            'access_key': self.api_key,
            'nonce': str(uuid.uuid4()),
            'timestamp': current_ts,  # Bithumb은 timestamp 필수
        }

        if query_params:
            # 🔒 RCE 예방: 입력 검증 (타입 검증)
            for key, value in query_params.items():
                if not isinstance(key, str):
                    raise ValueError(f"Invalid query parameter key type: {key} ({type(key)})")
                if not isinstance(value, (str, int, float, Decimal, bool)):
                    raise ValueError(f"Invalid query parameter value type: {key}={type(value)}")

            # 쿼리 파라미터를 SHA512 해시로 변환
            query_string = urlencode(query_params, doseq=True)
            m = hashlib.sha512()
            m.update(query_string.encode('utf-8'))
            query_hash = m.hexdigest()

            payload['query_hash'] = query_hash
            payload['query_hash_alg'] = 'SHA512'

        # JWT 토큰 생성 (HS256 알고리즘)
        return jwt.encode(payload, self.api_secret, algorithm='HS256')

    async def _request_async(self, method: str, endpoint: str, params: Optional[Dict[str, Any]] = None,
                            signed: bool = False) -> Any:
        """HTTP 요청 실행 (비동기)"""
        await self._init_session()

        url = f"{self.base_url}{endpoint}"
        headers = {}

        if signed:
            # JWT 인증 토큰 생성
            token = self._create_jwt_token(params)
            headers['Authorization'] = f'Bearer {token}'

        try:
            response = None
            if method.upper() == 'GET':
                async with self.session.get(url, params=params, headers=headers) as response:
                    data = await response.json()
            elif method.upper() == 'POST':
                headers['Content-Type'] = 'application/json'
                async with self.session.post(url, json=params, headers=headers) as response:
                    data = await response.json()
            elif method.upper() == 'DELETE':
                async with self.session.delete(url, params=params, headers=headers) as response:
                    data = await response.json()
            else:
                raise ValueError(f"지원하지 않는 HTTP 메서드: {method}")

            # Bithumb API 에러 처리
            if isinstance(data, dict) and 'error' in data:
                error_info = data['error']
                raise ExchangeError(f"Bithumb API 오류: {error_info.get('message', 'Unknown error')}")

            return data

        except aiohttp.ClientError as e:
            raise ExchangeError(f"네트워크 오류: {str(e)}")
        except json.JSONDecodeError as e:
            try:
                raw_text = await response.text()
                logger.error(f"Bithumb API 비정상 응답 (상태: {response.status}): {raw_text[:200]}")
            except:
                logger.error(f"Bithumb API 응답 읽기 실패")
            raise ExchangeError(f"Bithumb API 응답 형식 오류: {str(e)}")
        except Exception as e:
            logger.error(f"Bithumb API 요청 실패: {e}")
            raise ExchangeError(f"Bithumb API 오류: {str(e)}")

    def _request(self, method: str, endpoint: str, params: Optional[Dict[str, Any]] = None,
                signed: bool = False) -> Any:
        """HTTP 요청 실행 (동기)"""
        url = f"{self.base_url}{endpoint}"
        headers = {
            'User-Agent': 'Bithumb-Native-Client/1.0'
        }

        if signed:
            # JWT 인증 토큰 생성
            token = self._create_jwt_token(params)
            headers['Authorization'] = f'Bearer {token}'

        try:
            response = None
            if method.upper() == 'GET':
                response = requests.get(url, params=params, headers=headers, timeout=30)
            elif method.upper() == 'POST':
                headers['Content-Type'] = 'application/json'
                response = requests.post(url, json=params, headers=headers, timeout=30)
            elif method.upper() == 'DELETE':
                response = requests.delete(url, params=params, headers=headers, timeout=30)
            else:
                raise ValueError(f"지원하지 않는 HTTP 메서드: {method}")

            # HTTP 에러 처리
            if response.status_code >= 400:
                try:
                    error_data = response.json()
                    error_msg = error_data.get('error', {}).get('message', 'Unknown error')
                    logger.error(f"❌ Bithumb API 에러 [{response.status_code}]: {error_msg}")
                    raise ExchangeError(f"Bithumb API Error [{response.status_code}]: {error_msg}")
                except (ValueError, KeyError):
                    response.raise_for_status()

            data = response.json()

            # Bithumb API 에러 처리
            if isinstance(data, dict) and 'error' in data:
                error_info = data['error']
                raise ExchangeError(f"Bithumb API 오류: {error_info.get('message', 'Unknown error')}")

            return data

        except requests.RequestException as e:
            raise ExchangeError(f"네트워크 오류: {str(e)}")
        except json.JSONDecodeError as e:
            try:
                raw_text = response.text if response else "No response"
                logger.error(f"Bithumb API 비정상 응답 (상태: {response.status_code if response else 'unknown'}): {raw_text[:200]}")
            except:
                logger.error(f"Bithumb API 응답 읽기 실패")
            raise ExchangeError(f"Bithumb API 응답 형식 오류: {str(e)}")
        except Exception as e:
            logger.error(f"Bithumb API 요청 실패: {e}")
            raise ExchangeError(f"Bithumb API 오류: {str(e)}")

    # ===== 핵심 거래 메서드 구현 =====

    def load_markets_impl(self, market_type: str = 'spot', reload: bool = False) -> Dict[str, MarketInfo]:
        """마켓 정보 로드 (동기)"""
        if market_type.lower() != 'spot':
            raise ValueError("Bithumb은 Spot 거래만 지원합니다")

        cache_key = "markets"

        # 캐시 확인
        if not reload and cache_key in self.cache_time:
            if time.time() - self.cache_time[cache_key] < self.cache_ttl:
                return self.markets_cache

        # 마켓 코드 조회 (Public API - 인증 불필요)
        data = self._request('GET', BithumbEndpoints.MARKET_ALL, params={'isDetails': 'true'})

        markets = {}
        for market_info in data:
            market_code = market_info['market']  # 예: KRW-BTC, USDT-BTC

            # KRW 또는 USDT 마켓만 처리
            if not (market_code.startswith('KRW-') or market_code.startswith('USDT-')):
                continue

            # Bithumb 마켓 코드를 표준 형식으로 변환 (KRW-BTC → BTC/KRW)
            standard_symbol = from_bithumb_format(market_code)
            coin, currency = parse_symbol(standard_symbol)

            # USDT 마켓 precision 다르게 설정
            price_precision = 0 if currency == 'KRW' else 2
            quote_precision = 0 if currency == 'KRW' else 2
            min_notional = Decimal('5000') if currency == 'KRW' else Decimal('10')

            markets[standard_symbol] = MarketInfo(
                symbol=standard_symbol,
                base_asset=coin,
                quote_asset=currency,
                status='TRADING',
                active=True,
                amount_precision=8,
                price_precision=price_precision,
                base_precision=8,
                quote_precision=quote_precision,
                min_qty=Decimal('0.00000001'),
                max_qty=Decimal('9999999999'),
                step_size=Decimal('0.00000001'),
                min_price=Decimal('1') if currency == 'KRW' else Decimal('0.01'),
                max_price=Decimal('9999999999'),
                tick_size=Decimal('1') if currency == 'KRW' else Decimal('0.01'),
                min_notional=min_notional,
                market_type='SPOT'
            )

        # 캐시 업데이트
        self.markets_cache = markets
        self.cache_time[cache_key] = time.time()

        logger.info(f"✅ Bithumb 마켓 정보 로드 완료: {len(markets)}개")
        return markets

    def fetch_balance_impl(self, market_type: str = 'spot') -> Dict[str, Balance]:
        """잔액 조회 (동기)"""
        if market_type.lower() != 'spot':
            raise ValueError("Bithumb은 Spot 거래만 지원합니다")

        data = self._request('GET', BithumbEndpoints.ACCOUNTS, signed=True)

        balances = {}
        for account_info in data:
            currency = account_info.get('currency')
            if not currency:
                continue

            balance = Decimal(account_info.get('balance', '0'))
            locked = Decimal(account_info.get('locked', '0'))
            total = balance + locked

            # 0이 아닌 잔액만 포함
            if total > 0:
                balances[currency] = Balance(
                    asset=currency,
                    free=balance,
                    locked=locked,
                    total=total
                )

        logger.info(f"✅ Bithumb 잔액 조회 완료: {len(balances)}개")
        return balances

    def create_order_impl(self, symbol: str, order_type: str, side: str,
                         amount: Decimal, price: Optional[Decimal] = None,
                         market_type: str = 'spot', **params) -> Order:
        """주문 생성 (동기)"""
        if market_type.lower() != 'spot':
            raise ValueError("Bithumb은 Spot 거래만 지원합니다")

        # 심볼 변환: 표준 형식(BTC/KRW) → Bithumb 형식(KRW-BTC)
        market_code = to_bithumb_format(symbol)
        logger.info(f"🔄 심볼 변환: {symbol} → {market_code}")

        # Bithumb 주문 파라미터
        order_params = {
            'market': market_code,
            'side': 'bid' if side.lower() == 'buy' else 'ask',
            'ord_type': 'limit' if order_type.upper() == 'LIMIT' else 'price',
        }

        # 주문 타입별 파라미터 설정
        if order_type.upper() == 'LIMIT':
            if not price:
                raise InvalidOrder("LIMIT 주문은 price 파라미터가 필수입니다")

            # KRW인 경우 정수로 변환
            _, currency = parse_symbol(symbol)
            if currency == 'KRW':
                order_params['price'] = str(int(price))
            else:
                order_params['price'] = str(price)

            order_params['volume'] = str(amount)
        elif order_type.upper() == 'MARKET':
            if side.lower() == 'buy':
                # 매수 시장가: 주문 금액
                if not price:
                    raise InvalidOrder("시장가 매수는 price(주문금액) 파라미터가 필요합니다")
                order_params['price'] = str(int(price * amount))
            else:
                # 매도 시장가: 주문 수량
                order_params['volume'] = str(amount)
        else:
            raise InvalidOrder(f"지원하지 않는 주문 타입: {order_type}")

        logger.info(f"🔍 Bithumb API 호출: {BithumbEndpoints.ORDER}")
        logger.info(f"🔍 주문 파라미터: {order_params}")

        data = self._request('POST', BithumbEndpoints.ORDER, params=order_params, signed=True)
        logger.info(f"🔍 Bithumb API 응답: {data}")

        return self._parse_order(data)

    def cancel_order_impl(self, order_id: str, symbol: str = None, market_type: str = 'spot') -> Dict[str, Any]:
        """주문 취소 (동기)"""
        if market_type.lower() != 'spot':
            raise ValueError("Bithumb은 Spot 거래만 지원합니다")

        params = {'uuid': order_id}
        data = self._request('DELETE', BithumbEndpoints.ORDER_CANCEL, params=params, signed=True)

        return {
            'success': True,
            'order_id': data.get('uuid'),
            'symbol': data.get('market'),
            'status': data.get('state'),
            'message': f"주문 {order_id} 취소 완료"
        }

    def fetch_open_orders_impl(self, symbol: Optional[str] = None, market_type: str = 'spot') -> List[Order]:
        """미체결 주문 조회 (동기)"""
        if market_type.lower() != 'spot':
            raise ValueError("Bithumb은 Spot 거래만 지원합니다")

        params = {'state': 'wait'}  # 미체결 주문 필터
        if symbol:
            # 심볼 변환: 표준 형식(BTC/KRW) → Bithumb 형식(KRW-BTC)
            bithumb_market = to_bithumb_format(symbol)
            params['market'] = bithumb_market

        data = self._request('GET', BithumbEndpoints.ORDERS, params=params, signed=True)
        return [self._parse_order(order_data) for order_data in data]

    def fetch_order_impl(self, symbol: str = None, order_id: str = None, market_type: str = 'spot') -> Order:
        """단일 주문 상세 조회 (동기)"""
        if market_type.lower() != 'spot':
            raise ValueError("Bithumb은 Spot 거래만 지원합니다")

        params = {'uuid': order_id}
        data = self._request('GET', BithumbEndpoints.ORDER_INFO, params=params, signed=True)

        logger.debug(f"🔍 주문 상세 조회 완료: order_id={order_id}")
        return self._parse_order(data)

    def _parse_order(self, order_data: Dict[str, Any]) -> Order:
        """주문 데이터 파싱 - Bithumb 응답을 프로젝트 표준으로 변환"""
        # Bithumb 마켓 코드를 표준 심볼로 변환 (KRW-BTC → BTC/KRW)
        market_code = order_data.get('market', '')
        standard_symbol = from_bithumb_format(market_code)
        logger.debug(f"🔄 응답 심볼 변환: {market_code} → {standard_symbol}")

        # Bithumb 주문 상태 매핑
        state = order_data.get('state', 'wait')
        status_map = {
            'wait': 'NEW',
            'watch': 'NEW',
            'done': 'FILLED',
            'cancel': 'CANCELED'
        }
        status = status_map.get(state, state.upper())

        # Side 변환 (bid → buy, ask → sell)
        side = 'buy' if order_data.get('side') == 'bid' else 'sell'

        # 주문 타입 변환
        ord_type = order_data.get('ord_type', 'limit')
        order_type = 'market' if ord_type == 'price' else 'limit'

        # 수량 및 가격 정보
        volume = Decimal(order_data.get('volume', '0'))
        executed_volume = Decimal(order_data.get('executed_volume', '0'))
        remaining_volume = volume - executed_volume

        price = None
        if order_data.get('price'):
            price = Decimal(str(order_data['price']))

        avg_price = None
        if order_data.get('avg_buy_price'):
            avg_price = Decimal(str(order_data['avg_buy_price']))

        # 총 거래금액
        cost = None
        if executed_volume > 0 and avg_price and avg_price > 0:
            cost = executed_volume * avg_price

        return Order(
            id=order_data.get('uuid'),
            symbol=standard_symbol,  # 표준 형식 심볼 사용
            side=side,
            amount=volume,
            price=price,
            stop_price=None,  # Bithumb은 스탑 주문 미지원
            filled=executed_volume,
            remaining=remaining_volume,
            status=status,
            timestamp=int(datetime.fromisoformat(order_data.get('created_at', '').replace('Z', '+00:00')).timestamp() * 1000) if order_data.get('created_at') else 0,
            type=order_type,
            market_type='SPOT',
            average=avg_price if avg_price and avg_price > 0 else None,
            cost=cost
        )

    # ===== 비동기 메서드들 (동기 구현을 래핑) =====

    async def load_markets_async(self, market_type: str = 'spot', reload: bool = False) -> Dict[str, MarketInfo]:
        """마켓 정보 로드 (비동기)"""
        return self.load_markets_impl(market_type, reload)

    async def fetch_balance_async(self, market_type: str = 'spot') -> Dict[str, Balance]:
        """잔액 조회 (비동기)"""
        return self.fetch_balance_impl(market_type)

    async def create_order_async(self, symbol: str, order_type: str, side: str,
                          amount: Decimal, price: Optional[Decimal] = None,
                          market_type: str = 'spot', **params) -> Order:
        """주문 생성 (비동기)"""
        return self.create_order_impl(symbol, order_type, side, amount, price, market_type, **params)

    async def cancel_order_async(self, order_id: str, symbol: str = None,
                          market_type: str = 'spot') -> Dict[str, Any]:
        """주문 취소 (비동기)"""
        return self.cancel_order_impl(order_id, symbol, market_type)

    async def fetch_order_async(self, symbol: str = None, order_id: str = None, market_type: str = 'spot') -> Order:
        """단일 주문 상세 조회 (비동기)"""
        return self.fetch_order_impl(symbol, order_id, market_type)

    async def fetch_open_orders_async(self, symbol: Optional[str] = None,
                               market_type: str = 'spot') -> List[Order]:
        """미체결 주문 조회 (비동기)"""
        return self.fetch_open_orders_impl(symbol, market_type)

    # ===== BaseExchange 필수 메서드 구현 (동기) =====

    def load_markets(self, market_type: str = 'spot', reload: bool = False):
        """마켓 정보 로드 (동기)"""
        return self.load_markets_impl(market_type, reload)

    def fetch_balance(self, market_type: str = 'spot'):
        """잔액 조회 (동기)"""
        return self.fetch_balance_impl(market_type)

    def create_order(self, symbol: str, order_type: str, side: str,
                     amount: Decimal, price: Optional[Decimal] = None,
                     market_type: str = 'spot', **params):
        """주문 생성 (동기)"""
        return self.create_order_impl(symbol, order_type, side, amount, price, market_type, **params)

    def cancel_order(self, order_id: str, symbol: str = None, market_type: str = 'spot'):
        """주문 취소 (동기)"""
        return self.cancel_order_impl(order_id, symbol, market_type)

    def fetch_open_orders(self, symbol: Optional[str] = None, market_type: str = 'spot'):
        """미체결 주문 조회 (동기)"""
        return self.fetch_open_orders_impl(symbol, market_type)

    def fetch_order(self, symbol: str = None, order_id: str = None, market_type: str = 'spot'):
        """단일 주문 조회 (동기)"""
        return self.fetch_order_impl(symbol, order_id, market_type)

    # ===== 동기 래퍼 메서드들 (하위 호환성) =====

    def fetch_balance_sync(self, market_type: str = 'spot') -> Dict[str, Balance]:
        """잔액 조회 (동기)"""
        return self.fetch_balance_impl(market_type)

    def create_order_sync(self, symbol: str, order_type: str, side: str,
                         amount: Decimal, price: Optional[Decimal] = None,
                         market_type: str = 'spot', **params) -> Order:
        """주문 생성 (동기)"""
        return self.create_order_impl(symbol, order_type, side, amount, price, market_type, **params)

    def load_markets_sync(self, market_type: str = 'spot', reload: bool = False) -> Dict[str, MarketInfo]:
        """마켓 정보 로드 (동기)"""
        return self.load_markets_impl(market_type, reload)

    def cancel_order_sync(self, order_id: str, symbol: str = None, market_type: str = 'spot') -> Dict[str, Any]:
        """주문 취소 (동기)"""
        return self.cancel_order_impl(order_id, symbol, market_type)

    def fetch_open_orders_sync(self, symbol: Optional[str] = None, market_type: str = 'spot') -> List[Order]:
        """미체결 주문 조회 (동기)"""
        return self.fetch_open_orders_impl(symbol, market_type)

    def fetch_order_sync(self, symbol: str = None, order_id: str = None, market_type: str = 'spot') -> Order:
        """단일 주문 상세 조회 (동기)"""
        return self.fetch_order_impl(symbol, order_id, market_type)

    # ===== 배치 주문 기능 =====

    # @FEAT:exchange-integration @FEAT:order-queue @COMP:exchange @TYPE:integration
    def create_batch_orders(self, orders: List[Dict[str, Any]], market_type: str = 'spot') -> Dict[str, Any]:
        """배치 주문 생성 (동기 래퍼)"""
        # 비동기 구현을 동기 컨텍스트에서 실행
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(self.create_batch_orders_async(orders, market_type))

    # @FEAT:exchange-integration @FEAT:order-queue @COMP:exchange @TYPE:integration
    async def create_batch_orders_async(self, orders: List[Dict[str, Any]], market_type: str = 'spot') -> Dict[str, Any]:
        """
        배치 주문 생성 (순차 폴백 - Rate Limit 준수)

        Note:
            - 빗썸은 배치 API를 지원하지 않으므로 순차 처리
            - Rate Limit: 초당 5회, 분당 300회 (추정)
            - asyncio.Lock으로 완전 순차 실행 보장
            - 각 주문 사이에 0.2초 딜레이 (1/5초 = 초당 최대 5회)

        Args:
            orders: 주문 리스트
                [
                    {
                        'symbol': 'BTC/KRW',
                        'side': 'buy',
                        'type': 'LIMIT',
                        'amount': Decimal('0.001'),
                        'price': Decimal('50000000'),
                        'params': {...}
                    },
                    ...
                ]
            market_type: 'spot' (빗썸은 Spot만 지원)

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
                'implementation': 'SEQUENTIAL_FALLBACK'
            }

        Raises:
            ValueError: market_type이 'spot'이 아닌 경우
        """
        # 1. 빈 배치 처리
        if not orders:
            return {
                'success': True,
                'results': [],
                'summary': {'total': 0, 'successful': 0, 'failed': 0},
                'implementation': 'NONE'
            }

        # 2. Spot 전용 검증
        if market_type.lower() != 'spot':
            raise ValueError("Bithumb은 Spot 거래만 지원합니다")

        logger.info(f"📦 Bithumb 배치 주문 시작: {len(orders)}건 (Rate Limit: 초당 5회)")

        # 3. Rate Limiting 설정
        # Lock은 한 번에 1개만 통과시켜 완전한 순차 실행 보장
        _order_lock = asyncio.Lock()
        start_time = time.time()

        async def execute_with_limit(idx: int, order: Dict[str, Any]) -> Dict[str, Any]:
            """Rate limit 제어와 함께 단일 주문 실행 (완전 순차)"""
            async with _order_lock:
                # ⭐ CRITICAL: Rate Limiting - 초당 5회로 제한
                await asyncio.sleep(0.2)  # 1/5초 = 200ms (Upbit 125ms보다 보수적)

                try:
                    # 주문 실행
                    order_obj = await self.create_order_async(
                        symbol=order['symbol'],
                        order_type=order['type'],
                        side=order['side'],
                        amount=order['amount'],
                        price=order.get('price'),
                        market_type=market_type,
                        **order.get('params', {})
                    )

                    logger.info(f"✅ Bithumb 배치 주문 [{idx}] 성공: order_id={order_obj.id}, symbol={order['symbol']}")
                    return {
                        'order_index': idx,
                        'success': True,
                        'order_id': order_obj.id,
                        'order': order_obj.__dict__
                    }

                except Exception as e:
                    logger.error(f"❌ Bithumb 배치 주문 [{idx}] 실패 (symbol={order['symbol']}): {str(e)}")
                    return {
                        'order_index': idx,
                        'success': False,
                        'error': str(e)
                    }

        # 4. 병렬 실행 (Lock으로 동시성 제한)
        tasks = [execute_with_limit(idx, order) for idx, order in enumerate(orders)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 5. 결과 집계
        all_results = []
        successful_count = 0
        failed_count = 0

        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                # asyncio.gather가 예외를 반환한 경우 (이론적으로 발생하지 않아야 함)
                logger.critical(f"🐛 UNEXPECTED: Exception escaped execute_with_limit: {result}")
                all_results.append({
                    'order_index': idx,
                    'success': False,
                    'error': str(result)
                })
                failed_count += 1
            elif isinstance(result, dict):
                all_results.append(result)
                if result.get('success'):
                    successful_count += 1
                else:
                    failed_count += 1
            else:
                # 예상치 못한 결과 타입
                logger.error(f"❌ Bithumb 배치 주문 [{idx}] 예상치 못한 결과 타입: {type(result)}")
                all_results.append({
                    'order_index': idx,
                    'success': False,
                    'error': f"Unexpected result type: {type(result)}"
                })
                failed_count += 1

        # 6. 배치 완료 로깅
        elapsed = time.time() - start_time
        logger.info(
            f"📦 Bithumb 배치 주문 완료: {successful_count}/{len(orders)} 성공, "
            f"소요시간: {elapsed:.2f}초 (평균 {elapsed/len(orders):.3f}초/주문), "
            f"implementation=SEQUENTIAL_FALLBACK"
        )

        return {
            'success': True,  # 전체 프로세스 성공 (개별 주문 실패는 results에 포함)
            'results': all_results,
            'summary': {
                'total': len(orders),
                'successful': successful_count,
                'failed': failed_count
            },
            'implementation': 'SEQUENTIAL_FALLBACK'  # 빗썸은 배치 API 미지원
        }
