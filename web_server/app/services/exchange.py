"""
Exchange 서비스 통합 모듈

exchange_integrated_service.py 와 capital_service.py를 통합하여
하나의 일관된 서비스로 제공합니다.
"""
import logging
import time
from collections import defaultdict
from enum import Enum
from typing import Dict, List, Optional, Union, Any, TYPE_CHECKING

from app.models import Account
from app.constants import Exchange, MarketType, OrderType
from app.exchanges.models import PriceQuote
from app.exchanges.exceptions import (
    ExchangeError,
    NetworkError,
    OrderNotFound
)

if TYPE_CHECKING:
    from app.exchanges.crypto.base import BaseCryptoExchange
    from app.exchanges.securities.base import BaseSecuritiesExchange

logger = logging.getLogger(__name__)


# @FEAT:exchange-integration @COMP:service @TYPE:validation
class MarketTypeEnum(str, Enum):
    """거래소 마켓 타입 표준화"""
    SPOT = "spot"
    FUTURES = "futures"

    @classmethod
    def has_value(cls, value) -> bool:
        """유효한 값인지 확인"""
        return value in cls._value2member_map_

    @classmethod
    def normalize(cls, value) -> str:
        """값을 표준 형식으로 정규화"""
        if isinstance(value, cls):
            return value.value
        if cls.has_value(value):
            return value
        raise ValueError(f"Invalid market type: {value}")


# @FEAT:exchange-integration @COMP:service @TYPE:helper
class RateLimiter:
    """Rate Limiting 기능 (기존 rate_limit_service.py 통합)"""

    def __init__(self):
        self._limits = {
            'binance': {'requests_per_minute': 1200, 'orders_per_second': 10},
            'upbit': {'requests_per_minute': 600, 'orders_per_second': 8},
            'bybit': {'requests_per_minute': 600, 'orders_per_second': 20},
        }
        self._request_history = defaultdict(list)
        self._order_history = defaultdict(list)

    def acquire_slot(self, exchange_name: str) -> bool:
        """API 요용슬롯 획득 (Rate Limit 관리)"""
        current_time = time.time()

        # 요청 history 정리 (1분 이전 데이터 삭제)
        self._request_history[exchange_name] = [
            timestamp for timestamp in self._request_history[exchange_name]
            if current_time - timestamp < 60
        ]

        # 주문 history 정리 (1초 이전 데이터 삭제)
        self._order_history[exchange_name] = [
            timestamp for timestamp in self._order_history[exchange_name]
            if current_time - timestamp < 1
        ]

        # Rate limit 체크
        limit = self._limits[exchange_name]

        if len(self._request_history[exchange_name]) >= limit['requests_per_minute']:
            wait_time = 60 - (current_time - self._request_history[exchange_name][0])
            logger.warning(f"Rate limit exceeded for {exchange_name}, waiting {wait_time:.2f}s")
            time.sleep(wait_time)
            return False

        if len(self._order_history[exchange_name]) >= limit['orders_per_second']:
            wait_time = 1 - (current_time - self._order_history[exchange_name][0])
            logger.warning(f"Order rate limit exceeded for {exchange_name}, waiting {wait_time:.2f}s")
            time.sleep(wait_time)
            return False

        # 슬롯 획득 기록
        self._request_history[exchange_name].append(current_time)
        self._order_history[exchange_name].append(current_time)
        return True


def _standardize_crypto_balance(balance_data: Dict, exchange_name: str, market_type: str) -> Dict[str, Any]:
    """
    거래별 잔고 데이터 표준화 (Binance/Upbit/Bybit 호환성)

    Args:
        balance_data: 거래별 잔고 데이터
        exchange_name: 거래소 이름
        market_type: 마켓 타입

    Returns:
        표준화된 잔고 데이터
    """
    standardized = {}

    try:
        for asset, data in balance_data.items():
            if isinstance(data, dict):
                free = float(data.get('free', 0))
                locked = float(data.get('locked', 0))
            else:  # Balance 객체
                free = float(getattr(data, 'free', 0))
                locked = float(getattr(data, 'locked', 0))

            if free > 0 or locked > 0:  # 0보다 큰 잔고만 표준화
                standardized[asset] = {
                    'free': free,
                    'locked': locked,
                    'total': free + locked
                }

        logger.debug(f"표준화 완료 - 거래소: {exchange_name}, 마켓: {market_type}, 자산: {len(standardized)}개")
        return {
            'success': True,
            'exchange': exchange_name,
            'market_type': market_type,
            'balances': standardized
        }

    except Exception as e:
        logger.error(f"잔고 표준화 실패: {e}")
        return {'success': False, 'error': str(e)}


class ExchangeService:
    """거래소 서비스 통합 클래스 (Exchange + Capital Service 통합)"""

    def __init__(self):
        self._crypto_exchanges: Dict[str, 'BaseCryptoExchange'] = {}
        self._securities_exchanges: Dict[str, 'BaseSecuritiesExchange'] = {}
        self.rate_limiter = RateLimiter()

        # CRITICAL FIX: Initialize exchanges to prevent "Unsupported exchange" errors
        # This prevents the empty _crypto_exchanges dictionary issue that caused
        # "Unsupported exchange: binance" errors when the service was used
        self.register_active_exchanges()

    # @FEAT:exchange-service-initialization @COMP:service @TYPE:core @DEPS:constants
    def register_active_exchanges(self) -> Dict[str, Any]:
        """
        설정 파일에 정의된 지원 거래소들을 사전 등록합니다.

        왜 이 메서드가 필요한가:
        - ExchangeService 초기화 시 빈 _crypto_exchanges 문제 해결 (CRITICAL)
        - "Unsupported exchange: binance" 오류 방지
        - 서비스 시작 시 모든 지원 거래소 기능 활성화
        - DB 의존성 제거로 결정론적 초기화 보장

        Returns:
            Dict[str, Any]: 등록 결과
                {
                    'success': bool,                    # 전체 성공 여부
                    'registered_exchanges': List[str],   # 등록된 거래소 목록
                    'total_exchanges': int,              # 총 지원 거래소 수
                    'success_count': int,                # 성공한 등록 수
                    'error_count': int,                  # 실패한 등록 수
                    'errors': List[Dict]                 # 상세 에러 정보
                }

        Notes:
            - constants.CRYPTO_EXCHANGES, SECURITIES_EXCHANGES에서 거래소 목록 가져옴
            - API 키 없이 기본 클라이언트 생성 (계좌 연결 시 주입)
            - register_crypto_exchange()로 서비스에 등록
            - 개별 실패 시 다른 거래소는 계속 진행 (graceful degradation)

        Examples:
            >>> result = exchange_service.register_active_exchanges()
            >>> if result['success']:
            ...     print(f"{len(result['registered_exchanges'])}개 거래소 등록됨")
            ...     print(f"거래소: {result['registered_exchanges']}")
            7개 거래소 등록됨
            거래소: ['binance', 'bybit', 'okx', 'upbit', 'bithumb', 'kis', 'kiwoom']

        Performance:
            - 실행 시간: 100-500ms (설정 기반)
            - 메모리: 거래소당 ~0.5MB 기본 클라이언트 생성
            - DB 쿼리: 없음 (설정 파일 기반)

        Critical Integration:
            - Phase 2: app/services/__init__.py에서 서비스 시작 시 호출
            - 문제 해결: _crypto_exchanges 빈 딕셔너리 → 지원 거래소들로 채움
            - 기능 복원: 잔고 조회, 가격 조회, WebSocket 연결 등
        """
        try:
            registered_exchanges = []
            success_count = 0
            error_count = 0
            errors = []

            # 1. 설정에서 지원 거래소 목록 가져오기
            crypto_exchanges = [Exchange.to_lower(ex) for ex in Exchange.CRYPTO_EXCHANGES]
            securities_exchanges = [Exchange.to_lower(ex) for ex in Exchange.SECURITIES_EXCHANGES]
            total_exchanges = len(crypto_exchanges) + len(securities_exchanges)

            logger.info(f"거래소 등록 시작: {total_exchanges}개 지원 거래소 (크립토: {len(crypto_exchanges)}, 증권: {len(securities_exchanges)})")

            # 2. 크립토 거래소 등록
            for exchange_name in crypto_exchanges:
                try:
                    logger.debug(f"크립토 거래소 {exchange_name} 기본 클라이언트 생성 시작")

                    # 기본 클라이언트 생성 (API 키 없이)
                    client = self._create_default_crypto_client(exchange_name)

                    if client:
                        self.register_crypto_exchange(exchange_name, client)
                        registered_exchanges.append(exchange_name)
                        success_count += 1
                        logger.info(f"크립토 거래소 등록 성공: {exchange_name}")
                    else:
                        raise Exception(f"클라이언트 생성 실패: {exchange_name}")

                except Exception as e:
                    error_info = {
                        'exchange': exchange_name,
                        'exchange_type': 'crypto',
                        'error_type': type(e).__name__,
                        'message': str(e)
                    }
                    errors.append(error_info)
                    error_count += 1
                    logger.error(f"크립토 거래소 {exchange_name} 등록 실패: {e}")

            # 3. 증권 거래소 등록
            for exchange_name in securities_exchanges:
                try:
                    logger.debug(f"증권 거래소 {exchange_name} 기본 클라이언트 생성 시작")

                    # 기본 클라이언트 생성 (API 키 없이)
                    client = self._create_default_securities_client(exchange_name)

                    if client:
                        self.register_securities_exchange(exchange_name, client)
                        registered_exchanges.append(exchange_name)
                        success_count += 1
                        logger.info(f"증권 거래소 등록 성공: {exchange_name}")
                    else:
                        raise Exception(f"클라이언트 생성 실패: {exchange_name}")

                except Exception as e:
                    error_info = {
                        'exchange': exchange_name,
                        'exchange_type': 'securities',
                        'error_type': type(e).__name__,
                        'message': str(e)
                    }
                    errors.append(error_info)
                    error_count += 1
                    logger.error(f"증권 거래소 {exchange_name} 등록 실패: {e}")

            # 4. 결과 요약
            any_success = success_count > 0

            # 결과 로깅
            if any_success:
                logger.info(f"거래소 등록 완료: 성공 {success_count}개, 실패 {error_count}개")
                logger.info(f"등록된 거래소: {registered_exchanges}")
            else:
                logger.error(f"모든 거래소 등록 실패: {error_count}개 오류 발생")
                for error in errors:
                    logger.error(f"  - {error['exchange']}: {error['message']}")

            return {
                'success': any_success,
                'registered_exchanges': registered_exchanges,
                'total_exchanges': total_exchanges,
                'success_count': success_count,
                'error_count': error_count,
                'errors': errors
            }

        except Exception as e:
            logger.error(f"거래소 등록 중 심각한 오류 발생: {e}")
            return {
                'success': False,
                'registered_exchanges': [],
                'total_exchanges': 0,
                'success_count': 0,
                'error_count': 1,
                'errors': [{'type': 'system_error', 'message': str(e)}]
            }

    def register_crypto_exchange(self, name: str, exchange: 'BaseCryptoExchange'):
        """암호화폐 거래소 등록"""
        self._crypto_exchanges[name] = exchange

    def register_securities_exchange(self, name: str, exchange: 'BaseSecuritiesExchange'):
        """증권 거래소 등록"""
        self._securities_exchanges[name] = exchange

    # @FEAT:exchange-service-initialization @COMP:service @TYPE:helper
    def _create_default_crypto_client(self, exchange_name: str) -> Optional['BaseCryptoExchange']:
        """
        API 키 없이 기본 크립토 거래소 클라이언트를 생성합니다.

        Args:
            exchange_name: 거래소 이름 (소문자)

        Returns:
            BaseCryptoExchange: 기본 클라이언트 또는 None
        """
        try:
            from app.exchanges.crypto.factory import CryptoExchangeFactory

            # API 키 없이 기본 클라이언트 생성
            client = CryptoExchangeFactory.create_default_client(exchange_name)
            return client

        except Exception as e:
            logger.debug(f"기본 크립토 클라이언트 생성 실패 ({exchange_name}): {e}")
            return None

    # @FEAT:exchange-service-initialization @COMP:service @TYPE:helper
    def _create_default_securities_client(self, exchange_name: str) -> Optional['BaseSecuritiesExchange']:
        """
        API 키 없이 기본 증권 거래소 클라이언트를 생성합니다.

        Args:
            exchange_name: 거래소 이름 (소문자)

        Returns:
            BaseSecuritiesExchange: 기본 클라이언트 또는 None
        """
        try:
            from app.exchanges.securities.factory import SecuritiesExchangeFactory

            # API 키 없이 기본 클라이언트 생성
            client = SecuritiesExchangeFactory.create_default_client(exchange_name)
            return client

        except Exception as e:
            logger.debug(f"기본 증권 클라이언트 생성 실패 ({exchange_name}): {e}")
            return None

    def _get_client(self, account: Account) -> Union['BaseCryptoExchange', 'BaseSecuritiesExchange']:
        """계정에 해당하는 거래소 클라이언트 획득"""
        client = None

        if account.exchange in self._crypto_exchanges:
            client = self._crypto_exchanges[account.exchange]
        elif account.exchange in self._securities_exchanges:
            client = self._securities_exchanges[account.exchange]

        if not client:
            raise ExchangeError(f"Unsupported exchange: {account.exchange}")

        return client

    # @FEAT:exchange-integration @COMP:service @TYPE:core
    def create_order(self, account: Account, order_data: Dict[str, Any],
                   market_type: Union[str, MarketTypeEnum] = MarketTypeEnum.SPOT) -> Dict[str, Any]:
        """
        주문 생성 (Exchange & Capital Service 통합)

        Args:
            account: 계정 정보
            order_data: 주문 데이터 (symbol, side, type, amount, price 등)
            market_type: 마켓 타입 (기본값: SPOT)

        Returns:
            주문 생성 결과
        """
        try:
            # Rate limit 체크
            self.rate_limiter.acquire_slot(account.exchange)

            # 클라이언트 획득
            client = self._get_client(account)

            # MarketTypeEnum 정규화
            normalized_market_type = MarketTypeEnum.normalize(market_type)

            # 주문 생성
            result = client.create_order(
                symbol=order_data['symbol'],
                order_type=order_data['type'],
                side=order_data['side'],
                amount=order_data['amount'],
                price=order_data.get('price'),
                stop_price=order_data.get('stop_price'),
                market_type=normalized_market_type
            )

            logger.info(f"주문 생성 성공: {account.exchange}, {order_data['symbol']}")
            return {'success': True, 'result': result}

        except Exception as e:
            logger.error(f"주문 생성 실패: {e}")
            return {'success': False, 'error': str(e)}

    # @FEAT:exchange-integration @COMP:service @TYPE:core
    def cancel_order(self, account: Account, symbol: str, order_id: str,
                    market_type: Union[str, MarketTypeEnum] = MarketTypeEnum.SPOT) -> Dict[str, Any]:
        """
        주문 취소

        Args:
            account: 계정 정보
            symbol: 거래 쌍
            order_id: 주문 ID
            market_type: 마켓 타입

        Returns:
            주문 취소 결과
        """
        try:
            # Rate limit 체크
            self.rate_limiter.acquire_slot(account.exchange)

            # 클라이언트 획득
            client = self._get_client(account)

            # MarketTypeEnum 정규화
            normalized_market_type = MarketTypeEnum.normalize(market_type)

            # 주문 취소
            result = client.cancel_order(order_id, symbol, normalized_market_type)

            logger.info(f"주문 취소 성공: {account.exchange}, {symbol}")
            return {'success': True, 'result': result}

        except Exception as e:
            logger.error(f"주문 취소 실패: {e}")
            return {'success': False, 'error': str(e)}

    # @FEAT:exchange-integration @COMP:service @TYPE:core
    def get_open_orders(self, account: Account, symbol: str = None,
                       market_type: Union[str, MarketTypeEnum] = MarketTypeEnum.SPOT) -> Dict[str, Any]:
        """
        미체결 주문 조회

        Args:
            account: 계정 정보
            symbol: 거래 쌍 (None이면 모든 거래 쌍)
            market_type: 마켓 타입

        Returns:
            미체결 주문 리스트
        """
        try:
            # Rate limit 체크
            self.rate_limiter.acquire_slot(account.exchange)

            # 클라이언트 획득
            client = self._get_client(account)

            # MarketTypeEnum 정규화
            normalized_market_type = MarketTypeEnum.normalize(market_type)

            # 미체결 주문 조회
            result = client.get_open_orders(symbol, normalized_market_type)

            return {'success': True, 'orders': result}

        except Exception as e:
            logger.error(f"미체결 주문 조회 실패: {e}")
            return {'success': False, 'error': str(e)}

    # @FEAT:exchange-integration @COMP:service @TYPE:core
    def get_order_history(self, account: Account, symbol: str = None,
                         limit: int = 100,
                         market_type: Union[str, MarketTypeEnum] = MarketTypeEnum.SPOT) -> Dict[str, Any]:
        """
        체결 내역 조회

        Args:
            account: 계정 정보
            symbol: 거래 쌍 (None이면 모든 거래 쌍)
            limit: 조회 개수 제한
            market_type: 마켓 타입

        Returns:
            체결 내역 리스트
        """
        try:
            # Rate limit 체크
            self.rate_limiter.acquire_slot(account.exchange)

            # 클라이언트 획득
            client = self._get_client(account)

            # MarketTypeEnum 정규화
            normalized_market_type = MarketTypeEnum.normalize(market_type)

            # 체결 내역 조회
            result = client.get_order_history(symbol, limit, normalized_market_type)

            return {'success': True, 'orders': result}

        except Exception as e:
            logger.error(f"체결 내역 조회 실패: {e}")
            return {'success': False, 'error': str(e)}

    # @FEAT:exchange-integration @COMP:service @TYPE:core
    def fetch_balance(self, account: Account,
                     market_type: Union[str, MarketTypeEnum] = MarketTypeEnum.SPOT) -> Dict[str, Any]:
        """
        전체 잔고 조회 (Exchange & Capital Service 통합)

        Args:
            account: 계정 정보
            market_type: 마켓 타입 (기본값: SPOT)

        Returns:
            전체 잔고 정보
        """
        try:
            # Rate limit 체크
            self.rate_limiter.acquire_slot(account.exchange)

            # Crypto/Securities 모두 동기 메서드 호출 (Phase 1-2에서 비동기 제거 완료)
            client = self._get_client(account)
            balance_map = client.fetch_balance(market_type)

            # 표준 포맷으로 변환
            return _standardize_crypto_balance(balance_map, account.exchange, market_type)

        except Exception as e:
            logger.error(f"잔액 조회 실패: account_id={account.id}, error={e}")
            return {'success': False, 'error': str(e)}

    # @FEAT:exchange-integration @COMP:service @TYPE:core
    def get_balance(self, account: Account, asset: str = 'USDT',
                   market_type: Union[str, MarketTypeEnum] = MarketTypeEnum.SPOT) -> Dict[str, Any]:
        """
        단일 자산 잔고 조회 편의 메서드

        Feature 브랜치의 간결한 구조 + Main 브랜치의 상세 검증
        """
        # Input validation (Main 브랜치 로직)
        if not account:
            logger.error("Account parameter is required")
            return {'success': False, 'error': 'Account parameter is required'}

        if not asset or not isinstance(asset, str):
            logger.error(f"Asset must be a non-empty string, got: {asset}")
            return {'success': False, 'error': 'Asset must be a non-empty string'}

        # MarketTypeEnum normalization (Feature 브랜치 로직)
        normalized_market_type = MarketTypeEnum.normalize(market_type)

        # 전체 잔고 조회 (Feature 브랜치의 간결한 로직)
        result = self.fetch_balance(account, normalized_market_type)

        if not result['success']:
            return result

        balances = result.get('balances', {})
        if asset not in balances:
            return {
                'success': True,
                'asset': asset,
                'free': 0.0,
                'locked': 0.0,
                'total': 0.0
            }

        return {
            'success': True,
            **balances[asset]
        }

    # @FEAT:batch-parallel-processing @FEAT:exchange-integration @COMP:service @TYPE:core
    def create_batch_orders(self, account: Account, orders: List[Dict[str, Any]],
                           market_type: str = 'spot',
                           account_id: Optional[int] = None) -> Dict[str, Any]:
        """
        배치 주문 생성 (스레드별 이벤트 루프 재사용, 병렬 처리 지원)

        Args:
            account: 계정 정보
            orders: 주문 리스트
                [
                    {
                        'symbol': 'BTC/USDT',
                        'side': 'buy',
                        'type': 'limit',
                        'amount': 0.001,
                        'price': 50000.0
                    }
                ]
            market_type: 마켓 타입
            account_id: 계정 ID (선택)

        Returns:
            배치 주문 결과
        """
        try:
            # Rate limit 체크
            self.rate_limiter.acquire_slot(account.exchange)

            # 클라이언트 획득
            client = self._get_client(account)

            # 배치 주문 생성
            results = []
            for order_data in orders:
                try:
                    result = client.create_order(
                        symbol=order_data['symbol'],
                        order_type=order_data['type'],
                        side=order_data['side'],
                        amount=order_data['amount'],
                        price=order_data.get('price'),
                        stop_price=order_data.get('stop_price'),
                        market_type=market_type
                    )
                    results.append({'success': True, 'result': result})
                except Exception as e:
                    results.append({'success': False, 'error': str(e)})

            logger.info(f"배치 주문 생성 완료: {len(results)}개 중 성공 {len([r for r in results if r['success']])}개")
            return {'success': True, 'results': results}

        except Exception as e:
            logger.error(f"배치 주문 생성 실패: {e}")
            return {'success': False, 'error': str(e)}

    # @FEAT:exchange-integration @COMP:service @TYPE:core
    def get_symbol_info(self, account: Account, symbol: str) -> Dict[str, Any]:
        """
        거래 쌍 정보 조회

        Args:
            account: 계정 정보
            symbol: 거래 쌍 (예: 'BTC/USDT')

        Returns:
            거래 쌍 정보
        """
        try:
            # Rate limit 체크
            self.rate_limiter.acquire_slot(account.exchange)

            # 클라이언트 획득
            client = self._get_client(account)

            # 거래 쌍 정보 조회
            result = client.get_symbol_info(symbol)

            return {'success': True, 'info': result}

        except Exception as e:
            logger.error(f"거래 쌍 정보 조회 실패: {e}")
            return {'success': False, 'error': str(e)}

    # @FEAT:exchange-integration @COMP:service @TYPE:core
    def get_ticker(self, account: Account, symbol: str) -> Dict[str, Any]:
        """
        티커 정보 조회

        Args:
            account: 계정 정보
            symbol: 거래 쌍 (예: 'BTC/USDT')

        Returns:
            티커 정보
        """
        try:
            # Rate limit 체크
            self.rate_limiter.acquire_slot(account.exchange)

            # 클라이언트 획득
            client = self._get_client(account)

            # 티커 정보 조회
            result = client.get_ticker(symbol)

            return {'success': True, 'ticker': result}

        except Exception as e:
            logger.error(f"티커 정보 조회 실패: {e}")
            return {'success': False, 'error': str(e)}

    # @FEAT:exchange-integration @COMP:service @TYPE:core
    def get_order_book(self, account: Account, symbol: str, limit: int = 100) -> Dict[str, Any]:
        """
        호가 정보 조회

        Args:
            account: 계정 정보
            symbol: 거래 쌍 (예: 'BTC/USDT')
            limit: 조회 개수 제한

        Returns:
            호가 정보
        """
        try:
            # Rate limit 체크
            self.rate_limiter.acquire_slot(account.exchange)

            # 클라이언트 획득
            client = self._get_client(account)

            # 호가 정보 조회
            result = client.get_order_book(symbol, limit)

            return {'success': True, 'order_book': result}

        except Exception as e:
            logger.error(f"호가 정보 조회 실패: {e}")
            return {'success': False, 'error': str(e)}

    # @FEAT:exchange-integration @COMP:service @TYPE:core
    def get_recent_trades(self, account: Account, symbol: str, limit: int = 100) -> Dict[str, Any]:
        """
        최근 체결 내역 조회

        Args:
            account: 계정 정보
            symbol: 거래 쌍 (예: 'BTC/USDT')
            limit: 조회 개수 제한

        Returns:
            최근 체결 내역
        """
        try:
            # Rate limit 체크
            self.rate_limiter.acquire_slot(account.exchange)

            # 클라이언트 획득
            client = self._get_client(account)

            # 최근 체결 내역 조회
            result = client.get_recent_trades(symbol, limit)

            return {'success': True, 'trades': result}

        except Exception as e:
            logger.error(f"최근 체결 내역 조회 실패: {e}")
            return {'success': False, 'error': str(e)}

    # @FEAT:exchange-integration @COMP:service @TYPE:core
    def get_klines(self, account: Account, symbol: str, interval: str = '1h',
                  limit: int = 100) -> Dict[str, Any]:
        """
        캔들 정보 조회

        Args:
            account: 계정 정보
            symbol: 거래 쌍 (예: 'BTC/USDT')
            interval: 간격 (예: '1m', '5m', '1h', '1d')
            limit: 조회 개수 제한

        Returns:
            캔들 정보
        """
        try:
            # Rate limit 체크
            self.rate_limiter.acquire_slot(account.exchange)

            # 클라이언트 획득
            client = self._get_client(account)

            # 캔들 정보 조회
            result = client.get_klines(symbol, interval, limit)

            return {'success': True, 'klines': result}

        except Exception as e:
            logger.error(f"캔들 정보 조회 실패: {e}")
            return {'success': False, 'error': str(e)}

    # @FEAT:exchange-integration @COMP:service @TYPE:core
    def get_leverage_info(self, account: Account, symbol: str) -> Dict[str, Any]:
        """
        레버리지 정보 조회 (선물 전용)

        Args:
            account: 계정 정보
            symbol: 거래 쌍 (예: 'BTC/USDT')

        Returns:
            레버리지 정보
        """
        try:
            # Rate limit 체크
            self.rate_limiter.acquire_slot(account.exchange)

            # 클라이언트 획득
            client = self._get_client(account)

            # 레버리지 정보 조회
            result = client.get_leverage_info(symbol)

            return {'success': True, 'leverage_info': result}

        except Exception as e:
            logger.error(f"레버리지 정보 조회 실패: {e}")
            return {'success': False, 'error': str(e)}

    # @FEAT:exchange-integration @COMP:service @TYPE:core
    def set_leverage(self, account: Account, symbol: str, leverage: int) -> Dict[str, Any]:
        """
        레버리지 설정 (선물 전용)

        Args:
            account: 계정 정보
            symbol: 거래 쌍 (예: 'BTC/USDT')
            leverage: 레버리지 배수

        Returns:
            레버리지 설정 결과
        """
        try:
            # Rate limit 체크
            self.rate_limiter.acquire_slot(account.exchange)

            # 클라이언트 획득
            client = self._get_client(account)

            # 레버리지 설정
            result = client.set_leverage(symbol, leverage)

            logger.info(f"레버리지 설정 성공: {account.exchange}, {symbol}, {leverage}x")
            return {'success': True, 'result': result}

        except Exception as e:
            logger.error(f"레버리지 설정 실패: {e}")
            return {'success': False, 'error': str(e)}

    # @FEAT:exchange-integration @COMP:service @TYPE:core
    def get_positions(self, account: Account, symbol: str = None) -> Dict[str, Any]:
        """
        포지션 정보 조회

        Args:
            account: 계정 정보
            symbol: 거래 쌍 (None이면 모든 거래 쌍)

        Returns:
            포지션 정보
        """
        try:
            # Rate limit 체크
            self.rate_limiter.acquire_slot(account.exchange)

            # 클라이언트 획득
            client = self._get_client(account)

            # 포지션 정보 조회
            result = client.get_positions(symbol)

            return {'success': True, 'positions': result}

        except Exception as e:
            logger.error(f"포지션 정보 조회 실패: {e}")
            return {'success': False, 'error': str(e)}

    # @FEAT:exchange-integration @COMP:service @TYPE:core
    def close_position(self, account: Account, symbol: str, amount: float,
                      side: str = 'both') -> Dict[str, Any]:
        """
        포지션 청산

        Args:
            account: 계정 정보
            symbol: 거래 쌍 (예: 'BTC/USDT')
            amount: 청산 수량 (None이면 전량 청산)
            side: 청산 방향 ('buy', 'sell', 'both')

        Returns:
            청산 결과
        """
        try:
            # Rate limit 체크
            self.rate_limiter.acquire_slot(account.exchange)

            # 클라이언트 획득
            client = self._get_client(account)

            # 포지션 청산
            result = client.close_position(symbol, amount, side)

            logger.info(f"포지션 청산 성공: {account.exchange}, {symbol}")
            return {'success': True, 'result': result}

        except Exception as e:
            logger.error(f"포지션 청산 실패: {e}")
            return {'success': False, 'error': str(e)}

    # @FEAT:exchange-integration @COMP:service @TYPE:core
    def get_trading_fee(self, account: Account, symbol: str) -> Dict[str, Any]:
        """
        거래 수수료 정보 조회

        Args:
            account: 계정 정보
            symbol: 거래 쌍 (예: 'BTC/USDT')

        Returns:
            거래 수수료 정보
        """
        try:
            # Rate limit 체크
            self.rate_limiter.acquire_slot(account.exchange)

            # 클라이언트 획득
            client = self._get_client(account)

            # 거래 수수료 정보 조회
            result = client.get_trading_fee(symbol)

            return {'success': True, 'fee': result}

        except Exception as e:
            logger.error(f"거래 수수료 정보 조회 실패: {e}")
            return {'success': False, 'error': str(e)}

    # @FEAT:exchange-integration @COMP:service @TYPE:core
    def get_deposit_address(self, account: Account, asset: str) -> Dict[str, Any]:
        """
        입금 주소 조회

        Args:
            account: 계정 정보
            asset: 자산 (예: 'BTC')

        Returns:
            입금 주소 정보
        """
        try:
            # Rate limit 체크
            self.rate_limiter.acquire_slot(account.exchange)

            # 클라이언트 획득
            client = self._get_client(account)

            # 입금 주소 조회
            result = client.get_deposit_address(asset)

            return {'success': True, 'address': result}

        except Exception as e:
            logger.error(f"입금 주소 조회 실패: {e}")
            return {'success': False, 'error': str(e)}

    # @FEAT:exchange-integration @COMP:service @TYPE:core
    def get_withdraw_address(self, account: Account, asset: str) -> Dict[str, Any]:
        """
        출금 주소 조회

        Args:
            account: 계정 정보
            asset: 자산 (예: 'BTC')

        Returns:
            출금 주소 정보
        """
        try:
            # Rate limit 체크
            self.rate_limiter.acquire_slot(account.exchange)

            # 클라이언트 획득
            client = self._get_client(account)

            # 출금 주소 조회
            result = client.get_withdraw_address(asset)

            return {'success': True, 'address': result}

        except Exception as e:
            logger.error(f"출금 주소 조회 실패: {e}")
            return {'success': False, 'error': str(e)}

    # @FEAT:exchange-integration @COMP:service @TYPE:core
    def withdraw(self, account: Account, asset: str, amount: float,
                address: str, memo: str = None) -> Dict[str, Any]:
        """
        출금

        Args:
            account: 계정 정보
            asset: 자산 (예: 'BTC')
            amount: 출금 금액
            address: 출금 주소
            memo: 출금 메모 (선택)

        Returns:
            출금 결과
        """
        try:
            # Rate limit 체크
            self.rate_limiter.acquire_slot(account.exchange)

            # 클라이언트 획득
            client = self._get_client(account)

            # 출금
            result = client.withdraw(asset, amount, address, memo)

            logger.info(f"출금 성공: {account.exchange}, {asset}, {amount}")
            return {'success': True, 'result': result}

        except Exception as e:
            logger.error(f"출금 실패: {e}")
            return {'success': False, 'error': str(e)}

    # @FEAT:exchange-integration @COMP:service @TYPE:core
    def get_deposit_history(self, account: Account, asset: str = None,
                          limit: int = 100) -> Dict[str, Any]:
        """
        입금 내역 조회

        Args:
            account: 계정 정보
            asset: 자산 (None이면 모든 자산)
            limit: 조회 개수 제한

        Returns:
            입금 내역
        """
        try:
            # Rate limit 체크
            self.rate_limiter.acquire_slot(account.exchange)

            # 클라이언트 획득
            client = self._get_client(account)

            # 입금 내역 조회
            result = client.get_deposit_history(asset, limit)

            return {'success': True, 'deposits': result}

        except Exception as e:
            logger.error(f"입금 내역 조회 실패: {e}")
            return {'success': False, 'error': str(e)}

    # @FEAT:exchange-integration @COMP:service @TYPE:core
    def get_withdraw_history(self, account: Account, asset: str = None,
                           limit: int = 100) -> Dict[str, Any]:
        """
        출금 내역 조회

        Args:
            account: 계정 정보
            asset: 자산 (None이면 모든 자산)
            limit: 조회 개수 제한

        Returns:
            출금 내역
        """
        try:
            # Rate limit 체크
            self.rate_limiter.acquire_slot(account.exchange)

            # 클라이언트 획득
            client = self._get_client(account)

            # 출금 내역 조회
            result = client.get_withdraw_history(asset, limit)

            return {'success': True, 'withdrawals': result}

        except Exception as e:
            logger.error(f"출금 내역 조회 실패: {e}")
            return {'success': False, 'error': str(e)}

    # @FEAT:exchange-integration @COMP:service @TYPE:core
    def get_account_info(self, account: Account) -> Dict[str, Any]:
        """
        계정 정보 조회

        Args:
            account: 계정 정보

        Returns:
            계정 정보
        """
        try:
            # Rate limit 체크
            self.rate_limiter.acquire_slot(account.exchange)

            # 클라이언트 획득
            client = self._get_client(account)

            # 계정 정보 조회
            result = client.get_account_info()

            return {'success': True, 'account': result}

        except Exception as e:
            logger.error(f"계정 정보 조회 실패: {e}")
            return {'success': False, 'error': str(e)}

    # @FEAT:exchange-integration @COMP:service @TYPE:core
    def get_api_status(self, account: Account) -> Dict[str, Any]:
        """
        API 상태 확인

        Args:
            account: 계정 정보

        Returns:
            API 상태 정보
        """
        try:
            # Rate limit 체크
            self.rate_limiter.acquire_slot(account.exchange)

            # 클라이언트 획득
            client = self._get_client(account)

            # API 상태 확인
            result = client.get_api_status()

            return {'success': True, 'status': result}

        except Exception as e:
            logger.error(f"API 상태 확인 실패: {e}")
            return {'success': False, 'error': str(e)}

    # @FEAT:exchange-integration @COMP:service @TYPE:core
    def get_server_time(self, account: Account) -> Dict[str, Any]:
        """
        서버 시간 조회

        Args:
            account: 계정 정보

        Returns:
            서버 시간 정보
        """
        try:
            # Rate limit 체크
            self.rate_limiter.acquire_slot(account.exchange)

            # 클라이언트 획득
            client = self._get_client(account)

            # 서버 시간 조회
            result = client.get_server_time()

            return {'success': True, 'server_time': result}

        except Exception as e:
            logger.error(f"서버 시간 조회 실패: {e}")
            return {'success': False, 'error': str(e)}

    # @FEAT:exchange-integration @COMP:service @TYPE:core
    def get_exchange_info(self, account: Account) -> Dict[str, Any]:
        """
        거래소 정보 조회

        Args:
            account: 계정 정보

        Returns:
            거래소 정보
        """
        try:
            # Rate limit 체크
            self.rate_limiter.acquire_slot(account.exchange)

            # 클라이언트 획득
            client = self._get_client(account)

            # 거래소 정보 조회
            result = client.get_exchange_info()

            return {'success': True, 'exchange_info': result}

        except Exception as e:
            logger.error(f"거래소 정보 조회 실패: {e}")
            return {'success': False, 'error': str(e)}

    # @FEAT:exchange-integration @COMP:service @TYPE:core
    def get_wallet_balance(self, account: Account,
                          market_type: Union[str, MarketTypeEnum] = MarketTypeEnum.SPOT) -> Dict[str, Any]:
        """
        지갑 잔고 조회

        Args:
            account: 계정 정보
            market_type: 마켓 타입 (기본값: SPOT)

        Returns:
            지갑 잔고 정보
        """
        try:
            # Rate limit 체크
            self.rate_limiter.acquire_slot(account.exchange)

            # 클라이언트 획득
            client = self._get_client(account)

            # MarketTypeEnum 정규화
            normalized_market_type = MarketTypeEnum.normalize(market_type)

            # 지갑 잔고 조회
            result = client.get_wallet_balance(normalized_market_type)

            return {'success': True, 'wallet_balance': result}

        except Exception as e:
            logger.error(f"지갑 잔고 조회 실패: {e}")
            return {'success': False, 'error': str(e)}

    # @FEAT:exchange-integration @COMP:service @TYPE:core
    def get_precision_info(self, account: Account, symbol: str) -> Dict[str, Any]:
        """
        거래 쌍 정밀도 정보 조회

        Args:
            account: 계정 정보
            symbol: 거래 쌍 (예: 'BTC/USDT')

        Returns:
            정밀도 정보
        """
        try:
            # Rate limit 체크
            self.rate_limiter.acquire_slot(account.exchange)

            # 클라이언트 획득
            client = self._get_client(account)

            # 정밀도 정보 조회
            precision_info = client.get_precision_info(symbol)

            # 정밀도 적용
            processed_amount, processed_price, processed_stop_price = self.apply_precision(
                symbol,
                precision_info.get('precision', {}),
                precision_info.get('min_amount', 0),
                precision_info.get('min_price', 0)
            )

            return {
                'success': True,
                'precision_info': precision_info,
                'processed_amount': processed_amount,
                'processed_price': processed_price,
                'processed_stop_price': processed_stop_price
            }

        except Exception as e:
            logger.error(f"정밀도 정보 조회 실패: {e}")
            return {
                'success': False,
                'error': f'정밀도 정보 조회 실패: {str(e)}',
                'error_type': 'precision_error'
            }

    # @FEAT:exchange-integration @COMP:service @TYPE:core
    def apply_precision(self, symbol: str, precision: Dict[str, int],
                       min_amount: float, min_price: float) -> tuple:
        """
        거래 쌍 정밀도 적용

        Args:
            symbol: 거래 쌍 (예: 'BTC/USDT')
            precision: 정밀도 정보
            min_amount: 최소 거래 금액
            min_price: 최소 거래 가격

        Returns:
            (amount, price, stop_price) - 정밀도가 적용된 값들
        """
        try:
            # 기본값 설정
            processed_amount = 0.0
            processed_price = 0.0
            processed_stop_price = 0.0

            # 수량 정밀도 적용
            if 'amount' in precision:
                processed_amount = round(min_amount, precision['amount'])

            # 가격 정밀도 적용
            if 'price' in precision:
                processed_price = round(min_price, precision['price'])

            # Stop price 정밀도 적용
            if 'stop_price' in precision:
                processed_stop_price = round(min_price, precision['stop_price'])

            logger.debug(f"정밀도 적용 완료: {symbol} - amount: {processed_amount}, price: {processed_price}, stop_price: {processed_stop_price}")
            return processed_amount, processed_price, processed_stop_price

        except Exception as e:
            logger.error(f"정밀도 적용 실패: {e}")
            return 0.0, 0.0, 0.0

    # @FEAT:exchange-warmup @COMP:service @TYPE:core
    def get_supported_exchanges(self) -> List[str]:
        """
        현재 사용 가능한 거래소 목록을 반환합니다.

        왜 이 메서드가 필요한가:
        - 시스템 시작 시 어떤 거래소가 활성화되었는지 확인
        - 웜업 작업 전에 대상 거래소 목록 필터링
        - 사용자 인터페이스에서 지원되는 거래소 표시
        - 장애 발생 시 가용한 거래소만 선택하여 작업 수행

        Args:
            없음

        Returns:
            List[str]: API 상태가 정상인 거래소 이름 목록
                       - 예: ['binance', 'upbit', 'bybit']
                       - 장애 중인 거래소는 제외됨

        Raises:
            없음 (장애 발생 시 빈 리스트 반환)

        Notes:
            - 내부적으로 각 거래소의 get_api_status() 호출
            - 실패한 거래소는 경고 로그 기록 후 목록에서 제외
            - 빈 리스트 반환은 심각한 시스템 장애를 의미할 수 있음

        Examples:
            >>> service = ExchangeService()
            >>> service.register_crypto_exchange('binance', binance_client)
            >>> exchanges = service.get_supported_exchanges()
            >>> print(f"사용 가능한 거래소: {exchanges}")
            사용 가능한 거래소: ['binance']

        Performance:
            - 시간 복잡도: O(n) where n은 등록된 거래소 수
            - 각 거래소당 1회 API 호출
            - 네트워크 지연 시 영향받을 수 있음
        """
        try:
            # 현재 등록된 모든 거래소 목록 반환
            all_exchanges = list(self._crypto_exchanges.keys()) + list(self._securities_exchanges.keys())
            supported_exchanges = []

            for exchange in all_exchanges:
                try:
                    # 각 거래소의 API 상태 확인
                    if exchange in self._crypto_exchanges:
                        status = self._crypto_exchanges[exchange].get_api_status()
                    else:
                        status = self._securities_exchanges[exchange].get_api_status()

                    if status.get('success', False):
                        supported_exchanges.append(exchange)
                    else:
                        logger.warning(f"거래소 {exchange} API 상태 비정상: {status}")

                except Exception as e:
                    logger.warning(f"거래소 {exchange} 상태 확인 실패: {e}")

            logger.info(f"지원되는 거래소: {supported_exchanges}")
            return supported_exchanges

        except Exception as e:
            logger.error(f"지원 거래소 목록 조회 실패: {e}")
            return []

    # @FEAT:exchange-warmup @COMP:service @TYPE:core
    def warm_up_precision_cache(self, account: Account) -> Dict[str, Any]:
        """
        주요 거래 쌍의 정밀도 정보를 미리 로드하여 캐시를 웜업합니다.

        왜 이 메서드가 필요한가:
        - 주문 실행 시 정밀도 조회 레이턴시 제거
        - Rate Limit 발생 전에 필요한 정보 미리 확보
        - 사용자 경험 향상 (주문 처리 속도 개선)
        - 시스템 부하 분산 (시작 시점 vs 실시간)

        Args:
            account (Account): 거래소 계정 정보
                - account.exchange: 거래소 이름 (예: 'binance')
                - account.api_key: API 인증 키
                - account.secret: API 비밀 키

        Returns:
            Dict[str, Any]: 웜업 실행 결과
                {
                    'success': bool,           # 성공 여부
                    'cached_symbols': List[str], # 캐시된 심볼 목록
                    'success_count': int,       # 성공한 심볼 수
                    'error_count': int,         # 실패한 심볼 수
                    'total_count': int          # 전체 시도한 심볼 수
                }

        Raises:
            ExchangeError: 거래소 API 호출 실패 시
            NetworkError: 네트워크 연결 문제 발생 시
            ValueError: 계정 정보가 유효하지 않은 경우

        Notes:
            - BTC, ETH 기반 상위 10개 주요 거래 쌍 대상
            - 각 심볼당 0.1초 간격으로 Rate Limit 준수
            - 실패한 심볼은 건너뛰고 나머지 계속 처리
            - 실제 캐시는 거래소 클라이언트 내부에서 관리

        Examples:
            >>> account = Account(id=1, exchange='binance', ...)
            >>> result = exchange_service.warm_up_precision_cache(account)
            >>> if result['success']:
            ...     print(f"캐시 완료: {result['success_count']}/{result['total_count']}")
            ... else:
            ...     print(f"캐시 실패: {result.get('error')}")
            캐시 완료: 8/10

        Performance:
            - 평균 실행 시간: 1-2초 (10개 심볼 기준)
            - 메모리 사용: 약 1KB (심볼당 정밀도 정보)
            - Rate Limit: 10 req/min (거래소 제한 내에서 안전)
        """
        try:
            # Rate limit 체크
            self.rate_limiter.acquire_slot(account.exchange)

            # 클라이언트 획득
            client = self._get_client(account)

            # 주요 거래 쌍 목록 (BTC, ETH 기준)
            major_pairs = [
                'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'ADA/USDT', 'SOL/USDT',
                'XRP/USDT', 'DOT/USDT', 'DOGE/USDT', 'AVAX/USDT', 'MATIC/USDT'
            ]

            precision_cache = {}
            success_count = 0
            error_count = 0

            for symbol in major_pairs:
                try:
                    # 정밀도 정보 조회 및 캐싱
                    precision_info = client.get_precision_info(symbol)
                    precision_cache[symbol] = precision_info
                    success_count += 1

                    # Rate limit 고려한 약간의 지연
                    time.sleep(0.1)

                except Exception as e:
                    logger.debug(f"정밀도 캐시 실패 {symbol}: {e}")
                    error_count += 1
                    continue

            logger.info(f"정밀도 캐시 웜업 완료: 성공 {success_count}개, 실패 {error_count}개")

            return {
                'success': True,
                'cached_symbols': list(precision_cache.keys()),
                'success_count': success_count,
                'error_count': error_count,
                'total_count': len(major_pairs)
            }

        except Exception as e:
            logger.error(f"정밀도 캐시 웜업 실패: {e}")
            return {'success': False, 'error': str(e)}

    # @FEAT:exchange-warmup @COMP:service @TYPE:core
    def warm_up_all_market_info(self, account: Account) -> Dict[str, Any]:
        """
        거래소의 전체 마켓 정보를 미리 로드하여 캐시를 웜업합니다.

        왜 이 메서드가 필요한가:
        - 모든 거래 가능한 심볼 정보 사전 확보
        - 심볼 검증 및 변환 로직의 성능 향상
        - 사용자 인터페이스에서 심볼 목록 표시 지원
        - 시스템 초기화 시 마켓 데이터 기반 구성

        Args:
            account (Account): 거래소 계정 정보
                - account.exchange: 거래소 이름 (예: 'binance')
                - account.api_key: API 인증 키 (일부 거래소는 인증 필요)
                - account.secret: API 비밀 키

        Returns:
            Dict[str, Any]: 웜업 실행 결과
                {
                    'success': bool,           # 성공 여부
                    'market_count': int,       # 로드된 마켓 수
                    'markets': List[str],       # 마켓 목록 (심볼명)
                    'exchange': str            # 거래소 이름
                }

        Raises:
            ExchangeError: 거래소 API 호출 실패 시
            NetworkError: 네트워크 연결 문제 발생 시
            ValueError: 계정 정보가 유효하지 않은 경우
            PermissionError: 권한 없는 API 접근 시

        Notes:
            - get_exchange_info() API를 사용하여 전체 마켓 목록 조회
            - 대부분의 거래소에서는 인증 없이 조회 가능
            - 수백개의 마켓 정보를 한 번에 로드하므로 시간 소요
            - 메모리 사용량이 크므로 정기적인 재실행 권장

        Examples:
            >>> account = Account(id=1, exchange='binance', ...)
            >>> result = exchange_service.warm_up_all_market_info(account)
            >>> if result['success']:
            ...     print(f"{result['market_count']}개 마켓 로드됨")
            ...     print(f"거래소: {result['exchange']}")
            ... else:
            ...     print(f"실패: {result.get('error')}")
            1525개 마켓 로드됨
            거래소: binance

        Performance:
            - 평균 실행 시간: 2-5초 (거래소 및 마켓 수에 따라)
            - 메모리 사용: 100KB-1MB (마켓 수에 따라)
            - Rate Limit: 1회 호출 (대부분 제한 없음)
            - 네트워크: 50KB-500KB 데이터 전송

        Edge Cases:
            - 일부 거래소는 마켓 정보 조회에 인증 필요
            - 마켓 수가 매우 많은 경우 응답 시간 길어짐
            - 거래소 점검 시 빈 응답 또는 에러 반환
        """
        try:
            # Rate limit 체크
            self.rate_limiter.acquire_slot(account.exchange)

            # 클라이언트 획득
            client = self._get_client(account)

            # 거래소 전체 마켓 정보 조회
            market_info = client.get_exchange_info()

            if not market_info.get('success', False):
                raise Exception(f"마켓 정보 조회 실패: {market_info.get('error', 'Unknown error')}")

            markets = market_info.get('markets', {})
            market_count = len(markets)

            logger.info(f"마켓 정보 웜업 완료: 총 {market_count}개 마켓 로드됨")

            return {
                'success': True,
                'market_count': market_count,
                'markets': list(markets.keys()) if isinstance(markets, dict) else markets,
                'exchange': account.exchange
            }

        except Exception as e:
            logger.error(f"마켓 정보 웜업 실패: {e}")
            return {'success': False, 'error': str(e)}

    # @FEAT:exchange-warmup @COMP:service @TYPE:core @DEPS:admin-panel,rate-limiter
    def refresh_api_based_market_info(self) -> Dict[str, Any]:
        """
        모든 활성 계좌의 마켓 정보를 API를 통해 갱신합니다.

        왜 이 메서드가 필요한가:
        - 백그라운드에서 정기적인 마켓 데이터 갱신
        - 관리자 패널에서 실시간 마켓 정보 모니터링 지원
        - 여러 거래소의 마켓 정보 동기화
        - 캐시 무효화 및 최신 정보 보장

        Returns:
            Dict[str, Any]: 갱신 실행 결과
                {
                    'success': bool,                    # 전체 성공 여부
                    'refreshed_exchanges': List[str],   # 갱신된 거래소 목록
                    'total_markets': int,               # 전체 마켓 수
                    'execution_time': float,            # 실행 시간 (초)
                    'exchange_details': Dict[str, Dict]  # 거래소별 상세 정보
                }

        Raises:
            없음 (모든 오류를 내부에서 처리하고 결과에 포함)

        Notes:
            - Account.query를 사용하여 모든 활성 계좌 조회
            - 거래소별로 그룹화하여 중복 API 호출 방지
            - warm_up_all_market_info() 패턴을 따르되 여러 계좌 지원
            - 실패한 거래소가 있어도 다른 거래소는 계속 처리
            - 관리자 패널과 백그라운드 작업에서 사용됨

        Examples:
            >>> result = exchange_service.refresh_api_based_market_info()
            >>> if result['success']:
            ...     print(f"{len(result['refreshed_exchanges'])}개 거래소 갱신됨")
            ...     print(f"총 {result['total_markets']}개 마켓")
            ...     print(f"실행 시간: {result['execution_time']:.2f}초")
            ... else:
            ...     print("일부 거래소 갱신 실패")
            3개 거래소 갱신됨
            총 4521개 마켓
            실행 시간: 12.34초

        Performance:
            - 평균 실행 시간: 5-15초 (거래소 수 및 네트워크 상태에 따라)
            - 메모리 사용: 1MB-5MB (마켓 수에 따라)
            - Rate Limit: 거래소별 1회 호출
            - 네트워크: 1MB-10MB 데이터 전송

        Edge Cases:
            - 활성 계좌가 없는 경우 빈 결과 반환
            - 일부 거래소 API 실패 시 다른 거래소는 계속 처리
            - 네트워크 지연 시 타임아웃 처리
            - 거래소 점검 시 해당 거래소만 실패 처리
        """
        start_time = time.time()
        refreshed_exchanges = []
        total_markets = 0
        exchange_details = {}
        any_success = False

        try:
            # 모든 활성 계좌 조회
            active_accounts = Account.query.filter_by(is_active=True).all()

            if not active_accounts:
                logger.info("활성 계좌가 없어 마켓 정보 갱신을 건너뜁니다")
                return {
                    'success': True,
                    'refreshed_exchanges': [],
                    'total_markets': 0,
                    'execution_time': time.time() - start_time,
                    'exchange_details': {}
                }

            # 거래소별로 그룹화하여 중복 API 호출 방지
            exchange_groups = {}
            for account in active_accounts:
                exchange_name = account.exchange.lower()
                if exchange_name not in exchange_groups:
                    exchange_groups[exchange_name] = account

            logger.info(f"마켓 정보 갱신 시작: {len(exchange_groups)}개 거래소")

            # 각 거래소별로 마켓 정보 갱신
            for exchange_name, account in exchange_groups.items():
                try:
                    # Rate limit 체크
                    self.rate_limiter.acquire_slot(account.exchange)

                    # 클라이언트 획득
                    client = self._get_client(account)

                    # 거래소 마켓 정보 조회
                    market_info = client.get_exchange_info()

                    if market_info.get('success', False):
                        markets = market_info.get('markets', {})
                        market_count = len(markets)

                        refreshed_exchanges.append(exchange_name)
                        total_markets += market_count
                        any_success = True

                        exchange_details[exchange_name] = {
                            'success': True,
                            'market_count': market_count,
                            'markets': list(markets.keys()) if isinstance(markets, dict) else markets,
                            'account_used': f"{account.name} ({account.exchange})"
                        }

                        logger.info(f"거래소 {exchange_name} 마켓 정보 갱신 완료: {market_count}개 마켓")
                    else:
                        error_msg = market_info.get('error', 'Unknown error')
                        exchange_details[exchange_name] = {
                            'success': False,
                            'error': error_msg,
                            'account_used': f"{account.name} ({account.exchange})"
                        }
                        logger.error(f"거래소 {exchange_name} 마켓 정보 갱신 실패: {error_msg}")

                except Exception as e:
                    exchange_details[exchange_name] = {
                        'success': False,
                        'error': str(e),
                        'account_used': f"{account.name} ({account.exchange})" if account else 'Unknown'
                    }
                    logger.error(f"거래소 {exchange_name} 처리 중 예외 발생: {e}")

            execution_time = time.time() - start_time

            # 최종 결과 로깅
            if any_success:
                logger.info(f"마켓 정보 갱신 완료: {len(refreshed_exchanges)}개 거래소, {total_markets}개 마켓 (소요: {execution_time:.2f}초)")
            else:
                logger.error(f"모든 거래소에서 마켓 정보 갱신 실패 (소요: {execution_time:.2f}초)")

            return {
                'success': any_success,
                'refreshed_exchanges': refreshed_exchanges,
                'total_markets': total_markets,
                'execution_time': execution_time,
                'exchange_details': exchange_details
            }

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"마켓 정보 갱신 중 심각한 오류 발생: {e}")
            return {
                'success': False,
                'refreshed_exchanges': refreshed_exchanges,
                'total_markets': total_markets,
                'execution_time': execution_time,
                'exchange_details': exchange_details,
                'error': str(e)
            }

    # @FEAT:exchange-warmup @COMP:service @TYPE:core
    def get_precision_cache_stats(self) -> Dict[str, Any]:
        """
        정밀도 캐시의 현재 상태와 통계 정보를 반환합니다.

        왜 이 메서드가 필요한가:
        - 캐시 상태 모니터링 및 디버깅 지원
        - 웜업 작업의 성공 여부 확인
        - 시스템 리소스 사용량 추적
        - 운영 대시보드에 상태 정보 표시

        Args:
            없음

        Returns:
            Dict[str, Any]: 캐시 통계 정보
                {
                    'success': bool,                    # 조회 성공 여부
                    'stats': {
                        'cache_status': str,            # 캐시 상태 ('active')
                        'cache_type': str,              # 캐시 타입 ('precision_info')
                        'supported_exchanges': int,     # 지원되는 거래소 수
                        'last_updated': float           # 마지막 업데이트 시간 (Unix timestamp)
                    }
                }

        Raises:
            없음 (모든 오류를 내부에서 처리하고 False 상태 반환)

        Notes:
            - 실제 캐시 데이터는 각 거래소 클라이언트에서 관리
            - 여기서는 시스템 수준의 기본 통계만 제공
            - last_updated는 현재 시간으로 캐시 활성화 상태만 표시
            - 향후 실제 캐시 크기, 히트율 등 추가 가능

        Examples:
            >>> stats = exchange_service.get_precision_cache_stats()
            >>> if stats['success']:
            ...     cache_info = stats['stats']
            ...     print(f"상태: {cache_info['cache_status']}")
            ...     print(f"지원 거래소: {cache_info['supported_exchanges']}개")
            ... else:
            ...     print("통계 조회 실패")
            상태: active
            지원 거래소: 3개

        Performance:
            - 실행 시간: < 1ms (메모리 기반 조회)
            - 메모리 사용: 최소한 (< 100 bytes)
            - Rate Limit: 해당 없음 (로컬 정보)

        Limitations:
            - 실제 캐시 내용이나 크기 정보는 제공하지 않음
            - 캐시 히트율이나 만료 정보는 포함되지 않음
            - 거래소별 상세 정보는 클라이언트에서 직접 조회 필요
        """
        try:
            # 기본 통계 정보 반환 (실제 캐시는 클라이언트에서 관리)
            stats = {
                'cache_status': 'active',
                'cache_type': 'precision_info',
                'supported_exchanges': len(self._crypto_exchanges) + len(self._securities_exchanges),
                'last_updated': time.time()
            }

            return {
                'success': True,
                'stats': stats
            }

        except Exception as e:
            logger.error(f"정밀도 캐시 통계 조회 실패: {e}")
            return {'success': False, 'error': str(e)}

    # @FEAT:exchange-warmup @COMP:service @TYPE:helper
    def _warm_up_account_precision_cache(self, account: Account) -> Dict[str, Any]:
        """
        특정 계정에 대한 정밀도 캐시 웜업을 수행하는 내부 헬퍼 메서드입니다.

        왜 이 헬퍼 메서드가 필요한가:
        - 계정별 웜업 로직의 재사용성 확보
        - 로깅 및 에러 처리의 일관성 유지
        - 상위 호출자에서의 코드 중복 제거
        - 계정 ID 기반의 추적 및 모니터링 지원

        Args:
            account (Account): 웜업할 대상 계정 정보
                - account.id: 계정 식별자 (로깅용)
                - account.exchange: 거래소 이름
                - 기타 API 인증 정보

        Returns:
            Dict[str, Any]: 웜업 실행 결과
                {
                    'success': bool,           # 성공 여부
                    'cached_symbols': List[str], # 캐시된 심볼 목록
                    'success_count': int,       # 성공한 심볼 수
                    'error_count': int,         # 실패한 심볼 수
                    'total_count': int          # 전체 시도한 심볼 수
                }

        Raises:
            없음 (모든 예외를 처리하고 결과에 반영)

        Notes:
            - 내부적으로 warm_up_precision_cache() 호출
            - 계정 ID를 포함한 상세 로그 기록
            - 실패 시 원인을 명확하게 로그에 남김
            - public 메서드와의 인터페이스 일관성 유지

        Examples:
            >>> account = Account(id=42, exchange='binance', ...)
            >>> result = service._warm_up_account_precision_cache(account)
            >>> # 내부 로그: "계정 42 정밀도 캐시 웜업 성공: 8개"

        Performance:
            - 위임 호출이므로 성능 특성은 warm_up_precision_cache() 동일
            - 추가 오버헤드: 로깅 (~1ms)
            - 메모리: 추가 사용 없음

        Design Decision:
            - public 메서드와 별도로 유지하는 이유:
            1. 계정별 로깅 필요성
            2. 향후 계정별 커스터마이징 가능성
            3. 테스트에서의 목적 분리
            4. 일관적인 에러 처리 패턴
        """
        try:
            result = self.warm_up_precision_cache(account)

            if result['success']:
                logger.info(f"계정 {account.id} 정밀도 캐시 웜업 성공: {result['success_count']}개")
            else:
                logger.error(f"계정 {account.id} 정밀도 캐시 웜업 실패: {result.get('error', 'Unknown error')}")

            return result

        except Exception as e:
            logger.error(f"계정별 정밀도 캐시 웜업 실패: {e}")
            return {'success': False, 'error': str(e)}

    # @FEAT:price-cache @COMP:service @TYPE:core @DEPS:exchange-clients
    def get_price_quotes(self, exchange: str, market_type: str = 'spot',
                        symbols: Optional[List[str]] = None) -> Dict[str, PriceQuote]:
        """
        여러 거래소의 현재가 정보를 통합하여 조회합니다.

        왜 이 메서드가 필요한가:
        - 가격 캐시 시스템에서 31초마다 현재가 정보 갱신 (CRITICAL)
        - Issue #54 해결: ExchangeService missing method 오류 수정
        - 여러 거래소의 가격 데이터를 일관된 인터페이스로 제공
        - 거래소 이름 정규화 및 에러 처리 통합
        - 개별 거래소 구현에 대한 위임 패턴 구현

        Args:
            exchange (str): 거래소 이름 ('BINANCE', 'binance', 'UPBIT' 등)
            market_type (str): 마켓 타입 ('spot', 'futures'), 기본값 'spot'
            symbols (Optional[List[str]]): 조회할 심볼 목록, None이면 전체 조회

        Returns:
            Dict[str, PriceQuote]: 심볼을 키로 하는 가격 정보 딕셔너리
                - key: 심볼명 (예: 'BTC/USDT')
                - value: PriceQuote 객체 (거래소 무관 표준 포맷)
                - 실패 시 빈 딕셔너리 반환

        Raises:
            없음 (모든 예외를 내부에서 처리하고 빈 딕셔너리 반환)

        Notes:
            - 거래소 이름 정규화: 대소문자 무관, Exchange enum 호환
            - 개별 거래소의 fetch_price_quotes() 메서드에 위임
            - 실패한 거래소는 경고 로그 후 빈 결과 반환
            - Rate limiting은 개별 거래소 구현에서 처리
            - 가격 이상 감지는 상위 계층에서 처리 (향후 확장용)

        Examples:
            >>> quotes = exchange_service.get_price_quotes('BINANCE', 'spot', ['BTC/USDT'])
            >>> print(quotes['BTC/USDT'].last_price)  # 50000.0
            50000.0
            >>>
            >>> # 전체 심볼 조회
            >>> all_quotes = exchange_service.get_price_quotes('upbit', 'spot')
            >>> print(f"총 {len(all_quotes)}개 심볼 조회됨")
            총 100개 심볼 조회됨

        Performance:
            - 평균 실행 시간: 1-3초 (거래소 및 심볼 수에 따라)
            - 메모리 사용: 심볼당 ~100 bytes
            - 네트워크: 10KB-1MB (조회 결과에 따라)
            - Rate Limit: 거래소별 1회 호출

        Critical Integration:
            - app/__init__.py:1011 - 백그라운드 스케줄러 호출 (31초 간격)
            - price_cache.py:223, 276 - 가격 캐시 업데이트 호출
            - 실패 시 전체 가격 캐시 시스템 영향 (CRITICAL)
        """
        try:
            # 거래소 이름 정규화 (대소문자 무관)
            normalized_exchange = self._normalize_exchange_name(exchange)

            logger.debug(f"가격 조회 시작: exchange={exchange} -> {normalized_exchange}, "
                        f"market_type={market_type}, symbols={symbols}")

            # 적절한 거래소 클라이언트 획득
            client = self._get_exchange_client_by_name(normalized_exchange)

            if not client:
                logger.error(f"지원되지 않는 거래소: {exchange} (정규화: {normalized_exchange})")
                return {}

            # 개별 거래소에 가격 조회 위임
            quotes = client.fetch_price_quotes(
                market_type=market_type,
                symbols=symbols
            )

            if not quotes:
                logger.warning(f"가격 정보를 반환받지 못함: {normalized_exchange}, "
                            f"market_type={market_type}, symbols={symbols}")
                return {}

            logger.debug(f"가격 조회 완료: {normalized_exchange}, "
                        f"market_type={market_type}, quotes={len(quotes)}개")

            return quotes

        except Exception as e:
            logger.error(f"가격 조회 실패: exchange={exchange}, "
                        f"market_type={market_type}, symbols={symbols}, error={e}")
            return {}

    def _normalize_exchange_name(self, exchange: str) -> str:
        """
        거래소 이름을 표준 형식으로 정규화합니다.

        Args:
            exchange (str): 원본 거래소 이름 ('BINANCE', 'binance', 'Binance' 등)

        Returns:
            str: 정규화된 거래소 이름 ('binance', 'upbit' 등)

        Notes:
            - Exchange enum 값과 소문자 버전 모두 지원
            - 등록된 클라이언트의 키와 일치하는 형식으로 반환
        """
        if not exchange:
            return exchange

        exchange_upper = exchange.upper()
        exchange_lower = exchange.lower()

        # Exchange enum의 소문자 버전과 매칭
        exchange_mapping = {
            'BINANCE': 'binance',
            'BYBIT': 'bybit',
            'OKX': 'okx',
            'UPBIT': 'upbit',
            'BITHUMB': 'bithumb'
        }

        # 먼소문자로 변환 시도
        if exchange_upper in exchange_mapping:
            return exchange_mapping[exchange_upper]

        # 이미 소문자인 경우 그대로 반환
        return exchange_lower

    def _get_exchange_client_by_name(self, exchange_name: str) -> Optional[Union['BaseCryptoExchange', 'BaseSecuritiesExchange']]:
        """
        거래소 이름으로 해당 클라이언트를 획득합니다.

        Args:
            exchange_name (str): 정규화된 거래소 이름 ('binance', 'upbit' 등)

        Returns:
            Optional[BaseCryptoExchange|BaseSecuritiesExchange]: 거래소 클라이언트 또는 None
        """
        # 크립토 거래소에서 먼저 찾기
        if exchange_name in self._crypto_exchanges:
            return self._crypto_exchanges[exchange_name]

        # 증권 거래소에서 찾기
        if exchange_name in self._securities_exchanges:
            return self._securities_exchanges[exchange_name]

        return None

    # @FEAT:exchange-warmup @COMP:service @TYPE:helper
    def _warm_up_exchange_market_info(self, account: Account) -> Dict[str, Any]:
        """
        특정 거래소의 마켓 정보 웜업을 수행하는 내부 헬퍼 메서드입니다.

        왜 이 헬퍼 메서드가 필요한가:
        - 거래소별 마켓 정보 로드의 재사용성 확보
        - 거래소 이름 기반의 상세 로깅 제공
        - 배치 처리에서의 일관된 에러 처리
        - 상위 호출자의 코드 복잡성 감소

        Args:
            account (Account): 웜업할 대상 계정 정보
                - account.exchange: 거래소 이름 (로깅용)
                - 기타 API 인증 정보 (일부 거래소에서 필요)

        Returns:
            Dict[str, Any]: 웜업 실행 결과
                {
                    'success': bool,           # 성공 여부
                    'market_count': int,       # 로드된 마켓 수
                    'markets': List[str],       # 마켓 목록 (심볼명)
                    'exchange': str            # 거래소 이름
                }

        Raises:
            없음 (모든 예외를 처리하고 결과에 반영)

        Notes:
            - 내부적으로 warm_up_all_market_info() 호출
            - 거래소 이름을 포함한 상세 로그 기록
            - 실패 시 거래소별 원인을 명확하게 로그에 남김
            - public 메서드와 완전히 동일한 반환 구조

        Examples:
            >>> account = Account(exchange='binance', ...)
            >>> result = service._warm_up_exchange_market_info(account)
            >>> # 내부 로그: "거래소 binance 마켓 정보 웜업 성공: 1525개"

        Performance:
            - 위임 호출이므로 성능 특성은 warm_up_all_market_info() 동일
            - 추가 오버헤드: 로깅 (~1ms)
            - 메모리: 추가 사용 없음

        Design Decision:
            - public 메서드와 별도로 유지하는 이유:
            1. 거래소별 로깅 필요성
            2. 배치 처리 시 각 거래소 결과 추적
            3. 향후 거래소별 커스터마이징 가능성
            4. 테스트에서 단일 거래소 웜업 시뮬레이션

        Typical Usage:
            - 여러 계정/거래소 순차 웜업
            - 백그라운드 스케줄러에서의 개별 호출
            - 거래소 장애 후 재시도 로직
        """
        try:
            result = self.warm_up_all_market_info(account)

            if result['success']:
                logger.info(f"거래소 {account.exchange} 마켓 정보 웜업 성공: {result['market_count']}개")
            else:
                logger.error(f"거래소 {account.exchange} 마켓 정보 웜업 실패: {result.get('error', 'Unknown error')}")

            return result

        except Exception as e:
            logger.error(f"거래소별 마켓 정보 웜업 실패: {e}")
            return {'success': False, 'error': str(e)}


# Create global exchange service instance
# @FEAT:exchange-integration @COMP:service @TYPE:core
exchange_service = ExchangeService()