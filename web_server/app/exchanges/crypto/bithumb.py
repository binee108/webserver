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

    # ===== Phase 4에서 구현될 메서드들 (Placeholder) =====

    def load_markets_impl(self, market_type: str = 'spot', reload: bool = False) -> Dict[str, MarketInfo]:
        """마켓 정보 로드 (동기) - Phase 4에서 구현"""
        raise NotImplementedError("Phase 4에서 구현 예정")

    def fetch_balance_impl(self, market_type: str = 'spot') -> Dict[str, Balance]:
        """잔액 조회 (동기) - Phase 4에서 구현"""
        raise NotImplementedError("Phase 4에서 구현 예정")

    def create_order_impl(self, symbol: str, order_type: str, side: str,
                         amount: Decimal, price: Optional[Decimal] = None,
                         market_type: str = 'spot', **params) -> Order:
        """주문 생성 (동기) - Phase 4에서 구현"""
        raise NotImplementedError("Phase 4에서 구현 예정")

    def cancel_order_impl(self, order_id: str, symbol: str = None, market_type: str = 'spot') -> Dict[str, Any]:
        """주문 취소 (동기) - Phase 4에서 구현"""
        raise NotImplementedError("Phase 4에서 구현 예정")

    def fetch_open_orders_impl(self, symbol: Optional[str] = None, market_type: str = 'spot') -> List[Order]:
        """미체결 주문 조회 (동기) - Phase 4에서 구현"""
        raise NotImplementedError("Phase 4에서 구현 예정")

    def fetch_order_impl(self, symbol: str = None, order_id: str = None, market_type: str = 'spot') -> Order:
        """단일 주문 상세 조회 (동기) - Phase 4에서 구현"""
        raise NotImplementedError("Phase 4에서 구현 예정")

    def _parse_order(self, order_data: Dict[str, Any]) -> Order:
        """주문 데이터 파싱 - Phase 4에서 구현"""
        raise NotImplementedError("Phase 4에서 구현 예정")

    # ===== 비동기 메서드들 (동기 구현을 래핑) - Phase 4에서 구현 =====

    async def load_markets_async(self, market_type: str = 'spot', reload: bool = False) -> Dict[str, MarketInfo]:
        """마켓 정보 로드 (비동기) - Phase 4에서 구현"""
        raise NotImplementedError("Phase 4에서 구현 예정")

    async def fetch_balance_async(self, market_type: str = 'spot') -> Dict[str, Balance]:
        """잔액 조회 (비동기) - Phase 4에서 구현"""
        raise NotImplementedError("Phase 4에서 구현 예정")

    async def create_order_async(self, symbol: str, order_type: str, side: str,
                          amount: Decimal, price: Optional[Decimal] = None,
                          market_type: str = 'spot', **params) -> Order:
        """주문 생성 (비동기) - Phase 4에서 구현"""
        raise NotImplementedError("Phase 4에서 구현 예정")

    async def cancel_order_async(self, order_id: str, symbol: str = None,
                          market_type: str = 'spot') -> Dict[str, Any]:
        """주문 취소 (비동기) - Phase 4에서 구현"""
        raise NotImplementedError("Phase 4에서 구현 예정")

    async def fetch_order_async(self, symbol: str = None, order_id: str = None, market_type: str = 'spot') -> Order:
        """단일 주문 상세 조회 (비동기) - Phase 4에서 구현"""
        raise NotImplementedError("Phase 4에서 구현 예정")

    async def fetch_open_orders_async(self, symbol: Optional[str] = None,
                               market_type: str = 'spot') -> List[Order]:
        """미체결 주문 조회 (비동기) - Phase 4에서 구현"""
        raise NotImplementedError("Phase 4에서 구현 예정")

    # ===== BaseExchange 필수 메서드 구현 (비동기 버전을 기본으로 사용) - Phase 4에서 구현 =====

    async def load_markets(self, market_type: str = 'spot', reload: bool = False):
        """마켓 정보 로드 - Phase 4에서 구현"""
        raise NotImplementedError("Phase 4에서 구현 예정")

    async def fetch_balance(self, market_type: str = 'spot'):
        """잔액 조회 - Phase 4에서 구현"""
        raise NotImplementedError("Phase 4에서 구현 예정")

    async def create_order(self, symbol: str, order_type: str, side: str,
                          amount: Decimal, price: Optional[Decimal] = None,
                          market_type: str = 'spot', **params):
        """주문 생성 - Phase 4에서 구현"""
        raise NotImplementedError("Phase 4에서 구현 예정")

    async def cancel_order(self, order_id: str, symbol: str = None, market_type: str = 'spot'):
        """주문 취소 - Phase 4에서 구현"""
        raise NotImplementedError("Phase 4에서 구현 예정")

    async def fetch_open_orders(self, symbol: Optional[str] = None, market_type: str = 'spot'):
        """미체결 주문 조회 - Phase 4에서 구현"""
        raise NotImplementedError("Phase 4에서 구현 예정")

    async def fetch_order(self, symbol: str = None, order_id: str = None, market_type: str = 'spot'):
        """단일 주문 조회 - Phase 4에서 구현"""
        raise NotImplementedError("Phase 4에서 구현 예정")

    # ===== 동기 래퍼 메서드들 - Phase 4에서 구현 =====

    def fetch_balance_sync(self, market_type: str = 'spot') -> Dict[str, Balance]:
        """잔액 조회 (동기) - Phase 4에서 구현"""
        raise NotImplementedError("Phase 4에서 구현 예정")

    def create_order_sync(self, symbol: str, order_type: str, side: str,
                         amount: Decimal, price: Optional[Decimal] = None,
                         market_type: str = 'spot', **params) -> Order:
        """주문 생성 (동기) - Phase 4에서 구현"""
        raise NotImplementedError("Phase 4에서 구현 예정")

    def load_markets_sync(self, market_type: str = 'spot', reload: bool = False) -> Dict[str, MarketInfo]:
        """마켓 정보 로드 (동기) - Phase 4에서 구현"""
        raise NotImplementedError("Phase 4에서 구현 예정")

    def cancel_order_sync(self, order_id: str, symbol: str = None, market_type: str = 'spot') -> Dict[str, Any]:
        """주문 취소 (동기) - Phase 4에서 구현"""
        raise NotImplementedError("Phase 4에서 구현 예정")

    def fetch_open_orders_sync(self, symbol: Optional[str] = None, market_type: str = 'spot') -> List[Order]:
        """미체결 주문 조회 (동기) - Phase 4에서 구현"""
        raise NotImplementedError("Phase 4에서 구현 예정")

    def fetch_order_sync(self, symbol: str = None, order_id: str = None, market_type: str = 'spot') -> Order:
        """단일 주문 상세 조회 (동기) - Phase 4에서 구현"""
        raise NotImplementedError("Phase 4에서 구현 예정")
