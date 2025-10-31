# @FEAT:exchange-integration @COMP:service @TYPE:orchestrator
"""
통합 거래소 서비스

Rate Limit + Precision Cache + Exchange Logic + Adapter Factory 통합
1인 사용자를 위한 단순하고 효율적인 거래소 관리 서비스입니다.
"""

import time
import logging
import threading
import asyncio
from typing import Dict, Any, Optional, List, Tuple, Union, TYPE_CHECKING
from decimal import Decimal
from datetime import datetime
from threading import Lock
from collections import defaultdict

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
        self._lock = Lock()

    def acquire_slot(self, exchange: str, endpoint_type: str = 'general',
                     account_id: Optional[int] = None) -> None:
        """
        거래소 API Rate Limit 슬롯 획득 (블로킹)

        Args:
            exchange: 거래소 이름 (binance, upbit, bybit 등)
            endpoint_type: 엔드포인트 타입 ('general', 'order')
            account_id: 계좌 ID (제공 시 계좌별 Rate Limit 적용)

        계좌별 Rate Limit:
            - account_id 제공 시: key = f"{exchange}_{account_id}" (예: "binance_1", "binance_2")
            - account_id 없을 시: key = exchange (기존 동작 유지, 예: "binance")
            - 효과: 동일 거래소의 여러 계좌가 독립적으로 Rate Limit 적용됨
        """
        # 계좌별 키 생성 (account_id 제공 시)
        key = f"{exchange.lower()}_{account_id}" if account_id is not None else exchange.lower()

        # Rate Limit 설정 확인 (exchange 이름 기준)
        exchange_lower = exchange.lower()
        if exchange_lower not in self._limits:
            return

        while True:
            with self._lock:
                current_time = time.time()

                self._request_history[key] = [
                    t for t in self._request_history[key]
                    if current_time - t < 60
                ]
                self._order_history[key] = [
                    t for t in self._order_history[key]
                    if current_time - t < 1
                ]

                wait_seconds = 0.0

                limit_per_minute = self._limits[exchange_lower]['requests_per_minute']
                if len(self._request_history[key]) >= limit_per_minute:
                    oldest = min(self._request_history[key])
                    wait_seconds = max(wait_seconds, oldest + 60 - current_time)

                if endpoint_type == 'order':
                    limit_per_second = self._limits[exchange_lower]['orders_per_second']
                    if len(self._order_history[key]) >= limit_per_second:
                        oldest_order = min(self._order_history[key])
                        wait_seconds = max(wait_seconds, oldest_order + 1 - current_time)

                if wait_seconds <= 0:
                    self._request_history[key].append(current_time)
                    if endpoint_type == 'order':
                        self._order_history[key].append(current_time)

                    # 디버깅 로그 추가 (선택적)
                    logger.debug(
                        f"Rate Limit 슬롯 획득: key={key}, endpoint_type={endpoint_type}"
                    )
                    return

            time.sleep(wait_seconds)

    def get_stats(self, exchange: str) -> Dict[str, Any]:
        """Rate Limit 통계"""
        with self._lock:
            current_time = time.time()
            exchange = exchange.lower()

            # 최근 1분간 요청 수
            recent_requests = [
                t for t in self._request_history.get(exchange, [])
                if current_time - t < 60
            ]

            # 최근 1초간 주문 수
            recent_orders = [
                t for t in self._order_history.get(exchange, [])
                if current_time - t < 1
            ]

            return {
                'requests_last_minute': len(recent_requests),
                'orders_last_second': len(recent_orders),
                'limits': self._limits.get(exchange, {})
            }


# @FEAT:exchange-integration @COMP:service @TYPE:helper
class PrecisionCache:
    """Precision 정보 캐싱 (기존 precision_cache_service.py 통합)"""

    def __init__(self):
        self.precision_data = {}
        self.last_update = {}
        self.cache_ttl = 3600  # 1시간
        self._lock = Lock()

    def get_precision_info(self, exchange: str, symbol: str, market_type: str) -> Optional[Dict[str, Any]]:
        """Precision 정보 조회"""
        with self._lock:
            cache_key = f"{exchange}_{symbol}_{market_type}"

            # 캐시 확인
            if cache_key in self.precision_data:
                last_update = self.last_update.get(cache_key, 0)
                if time.time() - last_update < self.cache_ttl:
                    return self.precision_data[cache_key]

            return None

    def set_precision_info(self, exchange: str, symbol: str, market_type: str, precision_info: Dict[str, Any]):
        """Precision 정보 저장"""
        with self._lock:
            cache_key = f"{exchange}_{symbol}_{market_type}"
            self.precision_data[cache_key] = precision_info
            self.last_update[cache_key] = time.time()

    def get_stats(self) -> Dict[str, Any]:
        """캐시 통계"""
        with self._lock:
            return {
                'total_entries': len(self.precision_data),
                'cache_ttl': self.cache_ttl
            }


# @FEAT:exchange-integration @COMP:service @TYPE:orchestrator
class ExchangeService:
    """
    통합 거래소 서비스

    기존 서비스들 통합:
    - exchange_service.py
    - new_exchange_service.py
    - exchange_adapter_factory.py
    - rate_limit_service.py
    - precision_cache_service.py
    - order_execution_service.py (부분)
    """

    def __init__(self):
        self.rate_limiter = RateLimiter()
        self.precision_cache = PrecisionCache()

        # 강화된 클라이언트 캐싱 시스템
        self._exchange_clients = {}  # cache_key -> client
        self._client_timestamps = {}  # cache_key -> (created_time, last_used_time)
        self._client_lock = Lock()
        self._cache_max_size = 100
        self._cache_ttl = 3600  # 1시간

        # Thread-local event loop management
        self._thread_loops: Dict[int, asyncio.AbstractEventLoop] = {}
        self._loop_lock = Lock()

        # 거래소 팩토리 초기화 (UnifiedExchangeFactory는 필요하지 않음 - 직접 생성)
        # UnifiedExchangeFactory는 Account 객체를 직접 받아 처리하므로 팩토리 인스턴스 불필요
        try:
            from app.exchanges.crypto.factory import crypto_factory
            self.legacy_factory = crypto_factory  # 레거시 크립토 전용 팩토리 (공용 클라이언트용)
            logger.info("✅ 통합 거래소 서비스 초기화 완료")
        except ImportError as e:
            logger.error(f"❌ 거래소 팩토리 import 실패: {e}")
            self.legacy_factory = None

        # 공용(비인증) 클라이언트 캐시
        self._public_exchange_clients: Dict[str, Any] = {}

        logger.info("✅ ExchangeService 초기화 완료 (스레드별 이벤트 루프 관리)")

    def _get_or_create_loop(self) -> asyncio.AbstractEventLoop:
        """
        현재 스레드의 이벤트 루프 가져오기 (없으면 생성)

        **왜 필요한가?**
        Flask는 다중 스레드 환경에서 실행되며, 각 요청은 별도 스레드에서 처리됩니다.
        asyncio 이벤트 루프는 스레드 안전하지 않으므로, 각 스레드마다 독립적인
        이벤트 루프를 생성하여 충돌을 방지합니다.

        **동작 원리**:
        1. 현재 스레드 ID 확인
        2. 해당 스레드의 루프가 이미 존재하면 재사용 (성능 최적화)
        3. 없으면 새 루프 생성 후 딕셔너리에 저장

        **스레드 안전성**:
        Fast path는 lock 없이 동작하며, 생성 시에만 lock으로 보호합니다.

        Returns:
            asyncio.AbstractEventLoop: 현재 스레드에 할당된 이벤트 루프
        """
        thread_id = threading.get_ident()

        # Fast path: 루프가 이미 존재하면 즉시 반환 (lock 불필요)
        if thread_id in self._thread_loops:
            return self._thread_loops[thread_id]

        # Slow path: 새 루프 생성 (lock으로 보호)
        with self._loop_lock:
            # Lock 내부에서 재확인 (다른 스레드가 이미 생성했을 수 있음)
            if thread_id not in self._thread_loops:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                self._thread_loops[thread_id] = loop
                logger.info(f"🔄 새 이벤트 루프 생성 (스레드: {thread_id}, 총 루프: {len(self._thread_loops)})")

            return self._thread_loops[thread_id]

    def shutdown(self, timeout: float = 5.0):
        """
        모든 이벤트 루프를 안전하게 종료합니다.

        실행 중인 루프는 건너뛰고 (다른 스레드가 사용 중),
        정지된 루프만 안전하게 정리합니다.

        Args:
            timeout: 각 루프당 태스크 취소 대기 시간 (초)
        """
        logger.info(f"🛑 ExchangeService 종료 시작 (타임아웃: {timeout}s)")

        with self._loop_lock:
            for thread_id, loop in list(self._thread_loops.items()):
                try:
                    # 실행 중인 루프는 다른 스레드에서 사용 중이므로 건너뜀
                    if loop.is_running():
                        logger.warning(
                            f"⚠️ 스레드 {thread_id} 이벤트 루프는 실행 중이므로 종료하지 않음 "
                            f"(다른 스레드에서 사용 중일 가능성)"
                        )
                        continue

                    # 정지된 루프만 정리
                    if not loop.is_closed():
                        # 미완료 태스크 취소
                        try:
                            pending = asyncio.all_tasks(loop)
                            if pending:
                                logger.debug(
                                    f"🧹 스레드 {thread_id}: {len(pending)}개 미완료 태스크 취소 중"
                                )

                                for task in pending:
                                    task.cancel()

                                # 태스크 취소 완료 대기 (타임아웃 적용)
                                loop.run_until_complete(
                                    asyncio.wait(pending, timeout=timeout)
                                )
                        except Exception as e:
                            logger.warning(f"⚠️ 스레드 {thread_id} 태스크 취소 실패: {e}")

                        # 루프 닫기
                        loop.close()
                        logger.info(f"✅ 스레드 {thread_id} 이벤트 루프 종료 완료")

                except Exception as e:
                    logger.error(
                        f"❌ 스레드 {thread_id} 이벤트 루프 종료 실패: {e}",
                        exc_info=True
                    )

            self._thread_loops.clear()
            logger.info(f"✅ ExchangeService 종료 완료 (총 {len(self._thread_loops)}개 루프 정리)")

    # @FEAT:exchange-integration @COMP:service @TYPE:core
    def get_exchange_client(
        self, account: Account
    ) -> Optional[Union['BaseExchange', 'BaseSecuritiesExchange']]:
        """
        거래소 클라이언트 반환 (강화된 캐싱 시스템)

        크립토/증권 통합 지원:
        - UnifiedExchangeFactory를 통한 자동 라우팅
        - 계좌 타입에 따라 BaseExchange 또는 BaseSecuritiesExchange 반환

        Args:
            account: 계정 정보

        Returns:
            Union[BaseExchange, BaseSecuritiesExchange]: 거래소 클라이언트 인스턴스
        """
        from app.exchanges.unified_factory import UnifiedExchangeFactory
        from app.constants import AccountType

        # 캐시 키 생성 (계정 업데이트 시간 포함)
        account_timestamp = account.updated_at.timestamp() if account.updated_at else 0
        cache_key = f"{account.id}_{account.exchange}_{account.account_type}_{account_timestamp}"

        with self._client_lock:
            current_time = time.time()

            # 캐시 정리 (TTL 만료된 항목 제거)
            self._cleanup_expired_clients(current_time)

            # 캐시된 클라이언트 확인
            if cache_key in self._exchange_clients:
                # 마지막 사용 시간 업데이트
                created_time, _ = self._client_timestamps[cache_key]
                self._client_timestamps[cache_key] = (created_time, current_time)
                logger.debug(
                    f"✅ 캐시된 클라이언트 사용 "
                    f"(account_id={account.id}, type={account.account_type})"
                )
                return self._exchange_clients[cache_key]

            # 캐시 크기 제한 (가장 오래된 것 제거)
            if len(self._exchange_clients) >= self._cache_max_size:
                self._evict_oldest_client()

            try:
                # UnifiedExchangeFactory를 통한 클라이언트 생성
                logger.info(
                    f"🔀 거래소 클라이언트 생성 시작 "
                    f"(account_id={account.id}, type={account.account_type}, exchange={account.exchange})"
                )

                client = UnifiedExchangeFactory.create(account)

                if client:
                    self._exchange_clients[cache_key] = client
                    self._client_timestamps[cache_key] = (current_time, current_time)

                    client_type = "증권" if not AccountType.is_crypto(account.account_type) else "크립토"
                    logger.info(
                        f"✅ {client_type} 거래소 클라이언트 생성 완료 "
                        f"(account_id={account.id}, exchange={account.exchange})"
                    )
                    return client
                else:
                    logger.error(
                        f"❌ 거래소 클라이언트 생성 실패: None 반환 "
                        f"(account_id={account.id})"
                    )
                    return None

            except Exception as e:
                logger.error(
                    f"❌ 거래소 클라이언트 생성 중 예외 발생 "
                    f"(account_id={account.id}, type={account.account_type}): {e}"
                )
                return None

    def _cleanup_expired_clients(self, current_time: float) -> None:
        """TTL 만료된 클라이언트 제거"""
        expired_keys = []
        for cache_key, (created_time, last_used_time) in self._client_timestamps.items():
            if current_time - created_time > self._cache_ttl:
                expired_keys.append(cache_key)

        for key in expired_keys:
            self._exchange_clients.pop(key, None)
            self._client_timestamps.pop(key, None)
            logger.debug(f"🧹 만료된 클라이언트 캐시 제거: {key}")

    def _evict_oldest_client(self) -> None:
        """가장 오래된 클라이언트 제거 (LRU)"""
        if not self._client_timestamps:
            return

        # 마지막 사용 시간 기준으로 가장 오래된 것 찾기
        oldest_key = min(
            self._client_timestamps.keys(),
            key=lambda k: self._client_timestamps[k][1]  # last_used_time
        )

        self._exchange_clients.pop(oldest_key, None)
        self._client_timestamps.pop(oldest_key, None)
        logger.debug(f"🧹 LRU 캐시 제거: {oldest_key}")

    def invalidate_account_cache(self, account_id: int) -> int:
        """특정 계정의 모든 캐시 무효화"""
        with self._client_lock:
            removed_count = 0
            keys_to_remove = [
                key for key in self._exchange_clients.keys()
                if key.startswith(f"{account_id}_")
            ]

            for key in keys_to_remove:
                self._exchange_clients.pop(key, None)
                self._client_timestamps.pop(key, None)
                removed_count += 1

            if removed_count > 0:
                logger.info(f"🧹 계정 {account_id} 클라이언트 캐시 {removed_count}개 무효화")

            return removed_count

    def clear_all_cache(self) -> int:
        """모든 클라이언트 캐시 제거"""
        with self._client_lock:
            count = len(self._exchange_clients)
            self._exchange_clients.clear()
            self._client_timestamps.clear()
            if count > 0:
                logger.info(f"🧹 모든 클라이언트 캐시 {count}개 제거")
            return count

    def get_cache_stats(self) -> Dict[str, Any]:
        """클라이언트 캐시 통계"""
        with self._client_lock:
            current_time = time.time()
            active_clients = 0
            expired_clients = 0

            for created_time, last_used_time in self._client_timestamps.values():
                if current_time - created_time <= self._cache_ttl:
                    active_clients += 1
                else:
                    expired_clients += 1

            return {
                'total_cached_clients': len(self._exchange_clients),
                'active_clients': active_clients,
                'expired_clients': expired_clients,
                'cache_max_size': self._cache_max_size,
                'cache_ttl_seconds': self._cache_ttl
            }

    def get_exchange(self, account: Account) -> Optional[Any]:
        """거래소 인스턴스 반환 (호환성 유지)"""
        return self.get_exchange_client(account)

    # @FEAT:exchange-integration @COMP:service @TYPE:core
    def create_order(self, account: Account, symbol: str, side: str,
                    quantity: Decimal, order_type: str, market_type: str = 'spot',
                    price: Optional[Decimal] = None, stop_price: Optional[Decimal] = None) -> Dict[str, Any]:
        """
        주문 생성 (통합된 로직)

        Args:
            account: 계정 정보
            symbol: 거래 심볼
            side: 매수/매도 (BUY/SELL)
            quantity: 수량
            order_type: 주문 유형 (MARKET/LIMIT/STOP_MARKET/STOP_LIMIT)
            market_type: 마켓 유형 (spot/futures)
            price: 지정가 (LIMIT 주문시 필수)
            stop_price: 스탑 가격 (STOP 주문시 필수)

        Returns:
            주문 실행 결과
        """
        try:
            from app.constants import OrderType

            # Rate limit 대응 (필요 시 대기)
            self.rate_limiter.acquire_slot(account.exchange, 'order')

            # OrderType 정규화
            normalized_order_type = OrderType.normalize(order_type)

            # 필수 파라미터 검증
            if OrderType.requires_price(normalized_order_type) and not price:
                return {
                    'success': False,
                    'error': f'{normalized_order_type} 주문 타입은 price 파라미터가 필수입니다',
                    'error_type': 'parameter_error'
                }

            if OrderType.requires_stop_price(normalized_order_type) and not stop_price:
                return {
                    'success': False,
                    'error': f'{normalized_order_type} 주문 타입은 stop_price 파라미터가 필수입니다',
                    'error_type': 'parameter_error'
                }

            # 거래소 클라이언트 가져오기
            client = self.get_exchange_client(account)
            if not client:
                return {
                    'success': False,
                    'error': '거래소 클라이언트 생성 실패',
                    'error_type': 'client_error'
                }

            # Precision 정보 적용
            processed_params = self._apply_precision(
                client, account.exchange, symbol, market_type,
                quantity, price, stop_price
            )

            if not processed_params['success']:
                return processed_params

            # 거래소별 주문 타입 변환
            exchange_order_type = OrderType.to_exchange_format(normalized_order_type, account.exchange)

            # 거래소별 특수 처리는 각 거래소 어댑터에서 담당

            # 실제 주문 실행
            order_params = {
                'symbol': symbol,
                'order_type': exchange_order_type,
                'side': side,
                'amount': processed_params['quantity'],
                'market_type': market_type
            }

            # 조건부 파라미터 추가
            if OrderType.requires_price(normalized_order_type) and processed_params.get('price') is not None:
                order_params['price'] = processed_params['price']

            # STOP 주문에 대한 통합 처리
            if OrderType.requires_stop_price(normalized_order_type) and processed_params.get('stop_price') is not None:
                order_params['stopPrice'] = processed_params['stop_price']

            order_result = client.create_order(**order_params)

            # 통합 상태로 변환
            from app.constants import OrderStatus
            unified_status = OrderStatus.from_exchange(
                order_result.status,
                account.exchange
            )

            # 조정된 체결 정보 계산
            adjusted_filled_quantity = self._calculate_adjusted_filled(
                order_result.filled,
                processed_params['quantity'],
                quantity
            )

            return {
                'success': True,
                'order_id': order_result.id,
                'order_type': order_type,  # 원본 파라미터 유지 (단일 진실 소스)
                'status': unified_status,  # 통합 상태
                'original_status': order_result.status,  # 원본 거래소 상태
                'filled_quantity': order_result.filled,
                'average_price': order_result.price,
                'adjusted_quantity': processed_params['quantity'],  # 조정된 수량
                'adjusted_price': processed_params.get('price'),  # 조정된 가격
                'adjusted_stop_price': processed_params.get('stop_price'),  # 조정된 스톱 가격
                # 조정된 체결 정보 추가
                'adjusted_filled_quantity': adjusted_filled_quantity,
                'adjusted_average_price': processed_params.get('price') or order_result.price,
                'raw_response': order_result
            }

        except Exception as e:
            logger.error(f"주문 생성 실패: {e}")
            return {
                'success': False,
                'error': str(e),
                'error_type': 'execution_error'
            }

    def fetch_order(self, account: Account, symbol: str, order_id: str,
                    market_type: str = 'spot') -> Dict[str, Any]:
        """주문 상세 조회"""
        try:
            client = self.get_exchange_client(account)
            if not client:
                return {
                    'success': False,
                    'error': '거래소 클라이언트 생성 실패',
                    'error_type': 'client_error'
                }

            order = client.fetch_order(symbol=symbol, order_id=order_id, market_type=market_type)

            if not order:
                return {
                    'success': False,
                    'error': '주문을 찾을 수 없습니다',
                    'error_type': 'not_found'
                }

            from app.constants import OrderStatus

            unified_status = OrderStatus.from_exchange(order.status, account.exchange)

            logger.debug(
                "🔍 주문 상세 조회 성공 | account=%s symbol=%s order_id=%s status=%s"
                % (account.id, symbol, order_id, unified_status)
            )

            average_price = order.average if getattr(order, 'average', None) else order.price

            return {
                'success': True,
                'order': order,
                'status': unified_status,
                'original_status': order.status,
                'filled_quantity': order.filled,
                'average_price': average_price,
                'limit_price': getattr(order, 'price', None),
                'amount': order.amount,
                'side': order.side.upper() if order.side else None,
                'order_type': order.type.upper() if order.type else None,
                'timestamp': order.timestamp
            }

        except Exception as e:
            logger.error(f"주문 상세 조회 실패: account={account.id}, order={order_id}, error={e}")
            return {
                'success': False,
                'error': str(e),
                'error_type': 'execution_error'
            }

    def _calculate_adjusted_filled(self, original_filled: Decimal,
                                  adjusted_quantity: Decimal,
                                  original_quantity: Decimal) -> Decimal:
        """체결량을 조정 비율에 따라 계산"""
        if original_quantity == 0:
            return original_filled

        adjustment_ratio = adjusted_quantity / original_quantity
        return original_filled * adjustment_ratio

    # @FEAT:exchange-integration @COMP:service @TYPE:helper
    def _apply_precision(self, client: Any, exchange_name: str, symbol: str,
                        market_type: str, quantity: Decimal,
                        price: Optional[Decimal], stop_price: Optional[Decimal]) -> Dict[str, Any]:
        """수량 및 가격에 정밀도 적용 (Symbol Validator 사용, 네트워크 요청 없음)"""
        try:
            # Symbol Validator를 사용하여 메모리 기반 검증 및 조정
            from app.services.symbol_validator import symbol_validator

            logger.info(f"🔍 Symbol 검증 시작: {exchange_name} {symbol} {market_type} - 수량: {quantity}, 가격: {price}")

            validation_result = symbol_validator.validate_order_params(
                exchange=exchange_name,
                symbol=symbol,
                market_type=market_type,
                quantity=quantity,
                price=price
            )

            if not validation_result['success']:
                logger.error(f"❌ Symbol 검증 실패: {validation_result}")
                # 즉시 실패 반환 (거래 중단)
                return {
                    'success': False,
                    'error': f"Symbol 검증 실패: {validation_result.get('error', 'Unknown error')}",
                    'error_type': validation_result.get('error_type', 'validation_error')
                }

            logger.info(f"✅ Symbol 검증 성공: 조정된 수량={validation_result['adjusted_quantity']}, 조정된 가격={validation_result['adjusted_price']}")

            # 스톱 가격이 있는 경우 별도 조정
            adjusted_stop_price = None
            if stop_price is not None:
                stop_price_result = symbol_validator.validate_order_params(
                    exchange=exchange_name,
                    symbol=symbol,
                    market_type=market_type,
                    quantity=Decimal('1'),  # 더미 수량 (가격 조정만 필요)
                    price=stop_price
                )
                if stop_price_result['success']:
                    adjusted_stop_price = stop_price_result['adjusted_price']
                else:
                    # 스톱 가격 조정 실패 시에도 기본 조정 적용
                    market_info = symbol_validator.get_market_info(exchange_name, symbol, market_type)
                    if market_info:
                        adjusted_stop_price = stop_price.quantize(
                            Decimal('0.1') ** market_info.price_precision,
                            rounding='ROUND_DOWN'
                        )
                    else:
                        adjusted_stop_price = stop_price.quantize(
                            Decimal('0.01'),
                            rounding='ROUND_DOWN'
                        )

            return {
                'success': True,
                'quantity': validation_result['adjusted_quantity'],
                'price': validation_result['adjusted_price'],
                'stop_price': adjusted_stop_price
            }

        except Exception as e:
            logger.error(f"정밀도 적용 실패 (Symbol Validator): {e}")

            # 폴백: 기존 로직 사용 (하지만 네트워크 요청 제거)
            precision_info = self.precision_cache.get_precision_info(
                exchange_name, symbol, market_type
            )

            if not precision_info:
                # 캐시 미스 시 기본값으로 처리 (네트워크 요청 제거)
                logger.warning(f"Precision 정보 없음, 기본값 사용: {exchange_name}_{symbol}_{market_type}")
                precision_info = {'amount': 8, 'price': 8, 'filters': {}}

            # 수량 정밀도 적용
            amount_precision = precision_info.get('amount', 8)
            precision_quantity = quantity.quantize(
                Decimal('0.1') ** amount_precision,
                rounding='ROUND_DOWN'
            )

            # 가격 정밀도 적용
            processed_price = None
            processed_stop_price = None

            if price is not None:
                price_precision = precision_info.get('price', 8)
                processed_price = price.quantize(
                    Decimal('0.1') ** price_precision,
                    rounding='ROUND_DOWN'
                )

            if stop_price is not None:
                price_precision = precision_info.get('price', 8)
                processed_stop_price = stop_price.quantize(
                    Decimal('0.1') ** price_precision,
                    rounding='ROUND_DOWN'
                )

            return {
                'success': True,
                'quantity': precision_quantity,
                'price': processed_price,
                'stop_price': processed_stop_price
            }

        except Exception as e:
            logger.error(f"정밀도 적용 실패: {e}")
            return {
                'success': False,
                'error': f'정밀도 적용 실패: {str(e)}',
                'error_type': 'precision_error'
            }

    def fetch_balance(self, account: Account, market_type: str = 'spot') -> Dict[str, Any]:
        """잔액 조회"""
        try:
            client = self.get_exchange_client(account)
            if not client:
                return {'success': False, 'error': '거래소 클라이언트 없음'}

            # Rate limit 체크
            self.rate_limiter.acquire_slot(account.exchange)

            # Crypto/Securities 모두 동기 메서드 호출 (Phase 1-2에서 비동기 제거 완료)
            balance_map = client.fetch_balance(market_type)

            return {'success': True, 'balance': balance_map}

        except Exception as e:
            logger.error(f"잔액 조회 실패: account_id={account.id}, error={e}")
            return {'success': False, 'error': str(e)}

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
                        'type': 'LIMIT',
                        'amount': Decimal('0.01'),
                        'price': Decimal('95000'),
                        'params': {...}
                    },
                    ...
                ]
            market_type: 'spot' or 'futures'
            account_id: 계좌 ID (Phase 0 Rate Limiting용, Optional - 병렬 처리 시 필수)

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

        Performance:
            스레드별 이벤트 루프 재사용으로 10-15ms 오버헤드 제거
        """
        try:
            # 거래소 클라이언트 가져오기
            client = self.get_exchange_client(account)
            if not client:
                return {
                    'success': False,
                    'error': '거래소 클라이언트 생성 실패',
                    'error_type': 'client_error'
                }

            # Rate limit 체크 (배치 주문도 order 엔드포인트)
            # CRITICAL FIX: account_id 전달하여 Phase 0 계좌별 Rate Limiting 활성화
            self.rate_limiter.acquire_slot(
                account.exchange,
                'order',
                account_id=account_id or account.id  # ✅ 계좌별 Rate Limiting
            )

            # 스레드별 이벤트 루프 재사용
            loop = self._get_or_create_loop()

            # Log for verification
            logger.debug(f"배치 주문 실행 (스레드: {threading.get_ident()}, 이벤트 루프 재사용)")

            # 비동기 메서드를 동기 컨텍스트에서 실행
            result = loop.run_until_complete(
                client.create_batch_orders(orders, market_type)
            )
            return result

        except Exception as e:
            logger.error(f"배치 주문 생성 실패: {e}")
            return {
                'success': False,
                'error': str(e),
                'error_type': 'execution_error'
            }

    # @FEAT:order-tracking @COMP:service @TYPE:integration
    def cancel_order_with_retry(
        self,
        account: Account,
        order_id: str,
        symbol: str,
        market_type: str = 'spot',
        max_retries: int = 3,
        timeout: float = 10.0
    ) -> Dict[str, Any]:
        """주문 취소 (재시도 메커니즘 포함)

        WHY: 일시적 네트워크 오류/타임아웃 극복으로 주문 취소 성공률 향상
        Edge Cases: OrderNotFound (성공 처리), 재시도 불가 오류 (즉시 반환)
        Side Effects: 거래소 API 최대 3회 호출, 재시도 간 1/2/4초 지연
        Performance: 최대 지연 7초 (1+2+4), 성공 시 즉시 반환
        Debugging: 로그에서 재시도 횟수(attempt), 백오프 시간 추적

        Args:
            account: 거래소 계정
            order_id: 주문 ID
            symbol: 심볼 (예: BTC/USDT)
            market_type: 마켓 타입 (spot, future 등)
            max_retries: 최대 재시도 횟수 (기본 3회)
            timeout: 요청 타임아웃 (초, 기본 10초)

        Returns:
            Dict with:
                - success: bool
                - result: dict (성공 시)
                - error: str (실패 시)
                - error_type: str (실패 시)
                - retry_count: int (재시도 횟수)

        Pattern:
        1. 최대 max_retries 회 시도
        2. RequestTimeout/NetworkError → Exponential backoff 재시도
        3. OrderNotFound → 성공 처리 (이미 취소됨)
        4. 기타 예외 → 즉시 반환 (재시도 불가)
        """
        import requests

        retry_count = 0
        last_error = None

        for attempt in range(max_retries):
            try:
                client = self.get_exchange_client(account)
                if not client:
                    return {
                        'success': False,
                        'error': '거래소 클라이언트 없음',
                        'error_type': 'client_error',
                        'retry_count': retry_count
                    }

                self.rate_limiter.acquire_slot(account.exchange, 'order')

                result = client.cancel_order(order_id, symbol, market_type)

                logger.info(
                    f"✅ 주문 취소 성공: {order_id} "
                    f"(attempt={attempt + 1}/{max_retries}, retries={retry_count})"
                )

                return {
                    'success': True,
                    'result': result,
                    'retry_count': retry_count
                }

            except requests.Timeout as e:
                retry_count += 1
                last_error = str(e)

                logger.warning(
                    f"⏱️ 주문 취소 타임아웃: {order_id} "
                    f"(attempt={attempt + 1}/{max_retries}, timeout={timeout}s)"
                )

                if attempt < max_retries - 1:
                    # 지수 백오프: 1초, 2초, 4초
                    backoff_delay = 2 ** attempt
                    logger.info(f"🔄 재시도 대기: {backoff_delay}초")
                    time.sleep(backoff_delay)
                else:
                    logger.error(f"❌ 주문 취소 최종 실패 (타임아웃): {order_id}")
                    return {
                        'success': False,
                        'error': f'Timeout after {max_retries} attempts: {last_error}',
                        'error_type': 'timeout',
                        'retry_count': retry_count
                    }

            except NetworkError as e:
                retry_count += 1
                last_error = str(e)

                logger.warning(
                    f"🌐 주문 취소 네트워크 오류: {order_id} "
                    f"(attempt={attempt + 1}/{max_retries})"
                )

                if attempt < max_retries - 1:
                    backoff_delay = 2 ** attempt
                    logger.info(f"🔄 재시도 대기: {backoff_delay}초")
                    time.sleep(backoff_delay)
                else:
                    logger.error(f"❌ 주문 취소 최종 실패 (네트워크): {order_id}")
                    return {
                        'success': False,
                        'error': f'Network error after {max_retries} attempts: {last_error}',
                        'error_type': 'network',
                        'retry_count': retry_count
                    }

            except OrderNotFound as e:
                # @FEAT:orphan-order-prevention @COMP:service @TYPE:core @PHASE:3a
                # 주문이 이미 취소되었거나 없음 → 성공으로 간주
                logger.warning(
                    f"⚠️ 취소 성공 (already_cancelled) - "
                    f"market_type={market_type}, symbol={symbol}, order_id={order_id}"
                )

                # 🆕 Phase 3a: 방어 로직 - fetch_order()로 1회 재확인
                # WHY: OrderNotFound가 두 가지 경우 발생
                # 1) 주문이 진짜 취소됨 (정상) 2) 잘못된 market_type으로 조회 (오류)
                # fetch_order() 재확인으로 두 경우를 구분하여 고아 주문 방지
                try:
                    verification = self.fetch_order(
                        account=account,
                        symbol=symbol,
                        order_id=order_id,
                        market_type=market_type
                    )

                    if verification and verification.get('success'):
                        # 실제로 주문이 존재함 → market_type 오류 의심
                        logger.warning(
                            f"⚠️ CRITICAL: OrderNotFound이지만 주문 존재 - "
                            f"market_type 오류 의심 - "
                            f"order_id={order_id}, symbol={symbol}, market_type={market_type}"
                        )
                        return {
                            'success': False,
                            'error': 'Order exists but not found in specified market',
                            'error_type': 'market_type_mismatch',
                            'retry_count': retry_count
                        }
                except Exception as verify_error:
                    logger.debug(f"재확인 실패 (예상된 동작): {verify_error}")

                # 재확인 통과 → 진짜 취소됨
                return {
                    'success': True,
                    'result': {'already_cancelled': True},
                    'retry_count': retry_count
                }

            except ExchangeError as e:
                # ExchangeError 내부 메시지 분석으로 fallback 처리
                # TODO: binance.py가 -2011 → OrderNotFound 변환 시 이 블록 제거 가능
                error_msg = str(e).lower()

                # Binance error code -2011: "Unknown order sent"
                if '-2011' in error_msg or 'unknown order' in error_msg or 'order does not exist' in error_msg:
                    logger.info(f"ℹ️ 주문이 이미 취소됨 또는 없음 (ExchangeError fallback): {order_id}")
                    return {
                        'success': True,
                        'result': {'already_cancelled': True},
                        'retry_count': retry_count
                    }

                # 기타 ExchangeError는 재시도 불가능한 오류로 처리
                logger.error(f"❌ 주문 취소 실패 (거래소 오류): {order_id} - {e}")
                return {
                    'success': False,
                    'error': str(e),
                    'error_type': 'exchange_error',
                    'retry_count': retry_count
                }

            except Exception as e:
                # 예상치 못한 오류
                logger.error(f"❌ 주문 취소 실패 (예상치 못한 오류): {order_id} - {type(e).__name__}: {e}")
                return {
                    'success': False,
                    'error': str(e),
                    'error_type': 'unexpected_error',
                    'retry_count': retry_count
                }

        # 모든 재시도 실패 (여기 도달하면 timeout/network 예외 처리에서 return 누락)
        return {
            'success': False,
            'error': last_error or 'All retry attempts failed',
            'error_type': 'retry_exhausted',
            'retry_count': retry_count
        }

    def cancel_order(self, account: Account, order_id: str, symbol: str,
                    market_type: str = 'spot') -> Dict[str, Any]:
        """주문 취소 (레거시 호환성, 재시도 없음)

        레거시 코드 호환성을 위한 래퍼 함수입니다.
        새 코드에서는 cancel_order_with_retry()를 직접 사용하는 것을 권장합니다.
        """
        return self.cancel_order_with_retry(
            account=account,
            order_id=order_id,
            symbol=symbol,
            market_type=market_type,
            max_retries=1,  # 레거시: 재시도 없음
            timeout=10.0
        )

    def get_open_orders(self, account: Account, symbol: Optional[str] = None,
                       market_type: str = 'spot') -> Dict[str, Any]:
        """미체결 주문 조회"""
        try:
            client = self.get_exchange_client(account)
            if not client:
                return {'success': False, 'error': '거래소 클라이언트 없음'}

            self.rate_limiter.acquire_slot(account.exchange)

            orders = client.fetch_open_orders(symbol, market_type)
            return {'success': True, 'orders': orders}

        except Exception as e:
            logger.error(f"미체결 주문 조회 실패: {e}")
            return {'success': False, 'error': str(e)}

    def get_recent_trades(self, account: Account, symbol: Optional[str] = None,
                         market_type: str = 'spot', limit: int = 50) -> Dict[str, Any]:
        """최근 체결 내역 조회

        Args:
            account: 계좌 정보
            symbol: 거래 심볼 (None이면 모든 심볼)
            market_type: 시장 유형 (spot/futures)
            limit: 조회할 체결 내역 수

        Returns:
            성공 시: {'success': True, 'trades': [trade_list]}
            실패 시: {'success': False, 'error': error_message}
        """
        try:
            client = self.get_exchange_client(account)
            if not client:
                return {'success': False, 'error': '거래소 클라이언트 없음'}

            self.rate_limiter.acquire_slot(account.exchange)

            # 거래소별 처리
            if account.exchange.upper() == Exchange.BINANCE:
                trades = self._fetch_binance_trades(client, symbol, market_type, limit)
            elif account.exchange.upper() == Exchange.BYBIT:
                trades = self._fetch_bybit_trades(client, symbol, market_type, limit)
            elif account.exchange.upper() == Exchange.OKX:
                trades = self._fetch_okx_trades(client, symbol, market_type, limit)
            else:
                # 기본 ccxt 메서드 사용
                if hasattr(client, 'fetch_my_trades'):
                    trades = client.fetch_my_trades(symbol, limit=limit)
                else:
                    return {'success': False, 'error': 'Trade history not supported for this exchange'}

            return {'success': True, 'trades': trades}

        except Exception as e:
            logger.error(f"최근 거래 내역 조회 실패: {e}")
            return {'success': False, 'error': str(e)}

    def _fetch_binance_trades(self, client, symbol: Optional[str], market_type: str, limit: int) -> List[Dict]:
        """Binance 거래 내역 조회"""
        try:
            base_url = client._get_base_url(market_type)

            if market_type.lower() == 'futures':
                endpoint = '/fapi/v1/userTrades'
            else:
                endpoint = '/api/v3/myTrades'

            url = f"{base_url}{endpoint}"
            params = {
                'limit': limit
            }

            if symbol:
                params['symbol'] = symbol

            # Binance API 호출
            trades_data = client._request('GET', url, params, signed=True)

            # 표준 포맷으로 변환
            trades = []
            for trade in trades_data:
                trades.append({
                    'id': trade.get('id'),
                    'orderId': trade.get('orderId'),
                    'symbol': trade.get('symbol'),
                    'side': trade.get('side', '').lower(),
                    'price': float(trade.get('price', 0)),
                    'quantity': float(trade.get('qty', 0)),
                    'commission': float(trade.get('commission', 0)),
                    'commissionAsset': trade.get('commissionAsset'),
                    'time': trade.get('time'),
                    'isMaker': trade.get('isMaker', False),
                    'isBuyer': trade.get('isBuyer', False)
                })

            return trades

        except Exception as e:
            logger.error(f"Binance 거래 내역 조회 실패: {e}")
            return []

    def _fetch_bybit_trades(self, client, symbol: Optional[str], market_type: str, limit: int) -> List[Dict]:
        """Bybit 거래 내역 조회"""
        try:
            # Bybit 특화 구현 (필요시 추가)
            if hasattr(client, 'fetch_my_trades'):
                return client.fetch_my_trades(symbol, limit=limit)
            return []
        except Exception as e:
            logger.error(f"Bybit 거래 내역 조회 실패: {e}")
            return []

    def _fetch_okx_trades(self, client, symbol: Optional[str], market_type: str, limit: int) -> List[Dict]:
        """OKX 거래 내역 조회"""
        try:
            # OKX 특화 구현 (필요시 추가)
            if hasattr(client, 'fetch_my_trades'):
                return client.fetch_my_trades(symbol, limit=limit)
            return []
        except Exception as e:
            logger.error(f"OKX 거래 내역 조회 실패: {e}")
            return []


    def get_current_price(self, account_id: int, symbol: str, market_type: str = 'futures') -> Dict[str, Any]:
        """
        특정 심볼의 현재 시장가 조회

        Args:
            account_id: 계좌 ID
            symbol: 거래 심볼 (예: BTCUSDT)
            market_type: 시장 유형 (spot/futures)

        Returns:
            현재가 정보 또는 오류
        """
        try:
            # 계좌 정보 조회
            from app.models import Account
            account = Account.query.get(account_id)
            if not account:
                return {
                    'success': False,
                    'error': f'계좌를 찾을 수 없습니다: {account_id}'
                }

            # 거래소 클라이언트 가져오기
            client = self.get_exchange_client(account)
            if not client:
                return {
                    'success': False,
                    'error': '거래소 클라이언트 생성 실패'
                }

            # Rate limit 체크
            self.rate_limiter.acquire_slot(account.exchange)

            # 거래소별 현재가 조회
            if account.exchange.lower() == 'binance':
                # Binance API 사용
                base_url = client._get_base_url(market_type)
                endpoints = client._get_endpoints(market_type)
                url = f"{base_url}{endpoints.TICKER_PRICE}"
                params = {'symbol': symbol}

                ticker_info = client._request('GET', url, params)
                current_price = Decimal(str(ticker_info['price']))

                logger.debug(f"현재가 조회 성공 - {symbol}: {current_price}")

                return {
                    'success': True,
                    'symbol': symbol,
                    'price': float(current_price),
                    'timestamp': datetime.utcnow().isoformat()
                }
            else:
                # 다른 거래소는 ccxt의 fetch_ticker 사용
                ticker = client.fetch_ticker(symbol)
                current_price = ticker.get('last', 0)

                return {
                    'success': True,
                    'symbol': symbol,
                    'price': float(current_price),
                    'timestamp': datetime.utcnow().isoformat()
                }

        except Exception as e:
            logger.error(f"현재가 조회 실패 - {symbol}: {e}")
            return {
                'success': False,
                'error': str(e),
                'symbol': symbol
            }


    def get_stats(self) -> Dict[str, Any]:
        """서비스 통계"""
        return {
            'rate_limiter': {
                'binance': self.rate_limiter.get_stats('binance'),
                'upbit': self.rate_limiter.get_stats('upbit'),
                'bybit': self.rate_limiter.get_stats('bybit')
            },
            'precision_cache': self.precision_cache.get_stats(),
            'client_cache': self.get_cache_stats()
        }

    def is_available(self) -> bool:
        """서비스 사용 가능 여부"""
        return self.legacy_factory is not None

    def get_supported_exchanges(self) -> List[str]:
        """지원되는 거래소 목록 (크립토 전용)"""
        if self.legacy_factory:
            return self.legacy_factory.get_supported_exchanges()
        return []


    # === 공용 가격 조회 (가격 캐시 등에서 사용) ===

    def get_ticker(
        self,
        exchange: str,
        symbol: str,
        market_type: str = 'futures'
    ) -> Optional[Dict[str, Any]]:
        """거래소 공개 API로 현재 시세 조회 (인증 불필요)

        Args:
            exchange: 거래소 이름 (BINANCE, BYBIT 등)
            symbol: 심볼 (BTC/USDT)
            market_type: 마켓 타입 ('spot', 'futures')

        Returns:
            {
                'symbol': 'BTC/USDT',
                'last': 95000.5,
                'bid': 94999.0,
                'ask': 95001.0,
                'timestamp': 1697123456789
            }
            또는 실패 시 None
        """
        try:
            logger.info(
                "🔍 get_ticker 호출: exchange=%s, symbol=%s, market_type=%s",
                exchange,
                symbol,
                market_type
            )

            # Rate limit 체크 (공개 API도 제한 있음)
            self.rate_limiter.acquire_slot(exchange, 'general')

            # 거래소 정규화
            from app.constants import Exchange
            normalized_exchange = Exchange.normalize(exchange)
            logger.info(
                "✅ 거래소 정규화 완료: %s → %s",
                exchange,
                normalized_exchange
            )

            # get_price_quotes를 활용하여 단일 심볼 조회
            quotes = self.get_price_quotes(
                exchange=normalized_exchange,
                market_type=market_type,
                symbols=[symbol]
            )

            logger.info(
                "📊 get_price_quotes 결과: quotes_count=%d, keys=%s",
                len(quotes) if quotes else 0,
                list(quotes.keys()) if quotes else []
            )

            if not quotes:
                logger.warning(
                    "⚠️ 공개 API 시세 조회 실패: exchange=%s, symbol=%s (quotes 없음)",
                    exchange,
                    symbol
                )
                return None

            # 심볼 정규화 (BTC/USDT, BTCUSDT 모두 대응)
            symbol_upper = symbol.upper().replace('/', '')
            quote = quotes.get(symbol.upper()) or quotes.get(symbol_upper)

            logger.info(
                "🔍 심볼 검색: symbol_original=%s, symbol_upper=%s, symbol_no_slash=%s, found=%s",
                symbol,
                symbol.upper(),
                symbol_upper,
                quote is not None
            )

            if not quote:
                logger.warning(
                    "⚠️ 공개 API 시세 조회 실패: exchange=%s, symbol=%s (quote 없음)",
                    exchange,
                    symbol
                )
                return None

            # ccxt 호환 형식으로 반환
            ticker = {
                'symbol': symbol,
                'last': float(quote.last_price),
                'bid': float(quote.bid_price) if quote.bid_price else None,
                'ask': float(quote.ask_price) if quote.ask_price else None,
                'timestamp': int(datetime.utcnow().timestamp() * 1000)
            }

            logger.info(
                "✅ 공개 API 시세 조회 성공: %s %s = %s",
                exchange,
                symbol,
                ticker['last']
            )

            return ticker

        except Exception as e:
            logger.error(
                "❌ 공개 API 시세 조회 실패: exchange=%s, symbol=%s, error=%s",
                exchange,
                symbol,
                str(e),
                exc_info=True
            )
            return None

    def _get_public_exchange_client(self, exchange_name: str) -> Optional[Any]:
        """인증 불필요한 공용 엔드포인트용 클라이언트 반환 (크립토 전용)"""
        if not self.legacy_factory:
            logger.error("❌ 거래소 팩토리가 초기화되지 않아 공용 클라이언트를 생성할 수 없습니다")
            return None

        exchange_key = exchange_name.lower()

        if not self.legacy_factory.is_supported(exchange_name):
            logger.error(f"❌ 공용 클라이언트를 지원하지 않는 거래소: {exchange_name}")
            return None

        with self._client_lock:
            client = self._public_exchange_clients.get(exchange_key)
            if client:
                return client

            try:
                client = self.legacy_factory.create(exchange_key, api_key='', secret='', testnet=False)
                self._public_exchange_clients[exchange_key] = client
                return client
            except Exception as e:
                logger.error(f"❌ 공용 클라이언트 생성 실패 - exchange={exchange_name}: {e}")
                return None

    def get_price_quotes(self, exchange: str, market_type: str,
                         symbols: Optional[List[str]] = None) -> Dict[str, PriceQuote]:
        """거래소 무관 표준화된 현재가 정보 조회"""
        logger.info(
            "🔍 get_price_quotes 호출: exchange=%s, market_type=%s, symbols=%s",
            exchange,
            market_type,
            symbols
        )

        exchange_name = Exchange.normalize(exchange) if exchange else Exchange.BINANCE
        if not exchange_name or exchange_name not in Exchange.VALID_EXCHANGES:
            exchange_name = Exchange.BINANCE

        normalized_market_type = MarketType.normalize(market_type) if market_type else MarketType.SPOT
        client_market_type = 'futures' if normalized_market_type == MarketType.FUTURES else 'spot'
        symbol_filter = [symbol.upper() for symbol in symbols] if symbols else None

        logger.info(
            "✅ 정규화 완료: exchange_name=%s, market_type=%s→%s, symbol_filter=%s",
            exchange_name,
            market_type,
            client_market_type,
            symbol_filter
        )

        client = self._get_public_exchange_client(exchange_name)
        logger.info("🔍 _get_public_exchange_client 결과: client=%s", client is not None)

        if not client:
            logger.error("❌ 공용 클라이언트 생성 실패 - exchange=%s", exchange_name)
            return {}

        logger.info(
            "✅ 공용 클라이언트 생성 성공, fetch_price_quotes 존재 여부: %s",
            hasattr(client, 'fetch_price_quotes')
        )

        if not hasattr(client, 'fetch_price_quotes'):
            logger.error(
                "❌ 공용 클라이언트가 가격 조회를 지원하지 않습니다 - exchange=%s",
                exchange_name
            )
            return {}

        try:
            logger.info(
                "📡 fetch_price_quotes 호출 시작: market_type=%s, symbols=%s",
                client_market_type,
                symbol_filter
            )

            quotes = client.fetch_price_quotes(
                market_type=client_market_type,
                symbols=symbol_filter
            )

            logger.info(
                "✅ fetch_price_quotes 결과: type=%s, count=%d",
                type(quotes),
                len(quotes) if isinstance(quotes, dict) else 0
            )

        except Exception as e:
            logger.error(
                "❌ 가격 정보 조회 실패 - exchange=%s market_type=%s error=%s",
                exchange_name, client_market_type, e,
                exc_info=True
            )
            return {}

        if not isinstance(quotes, dict):
            logger.error(
                "❌ 가격 정보 포맷이 잘못되었습니다 - exchange=%s type=%s",
                exchange_name, type(quotes)
            )
            return {}

        normalized_quotes: Dict[str, PriceQuote] = {}
        for symbol, quote in quotes.items():
            if not symbol:
                continue

            symbol_upper = symbol.upper()
            if symbol_filter and symbol_upper not in symbol_filter:
                continue

            if isinstance(quote, PriceQuote):
                normalized_quotes[symbol_upper] = quote
                continue

            # 딕셔너리 형태의 응답을 최소 정보로 보정
            if isinstance(quote, dict):
                try:
                    last_value = quote.get('last_price') or quote.get('price') or quote.get('last')
                    if last_value is None:
                        continue

                    normalized_quotes[symbol_upper] = PriceQuote(
                        symbol=symbol_upper,
                        exchange=exchange_name,
                        market_type=normalized_market_type,
                        last_price=Decimal(str(last_value)),
                        bid_price=Decimal(str(quote['bid_price'])) if quote.get('bid_price') is not None else None,
                        ask_price=Decimal(str(quote['ask_price'])) if quote.get('ask_price') is not None else None,
                        volume=Decimal(str(quote['volume'])) if quote.get('volume') is not None else None,
                        raw=quote
                    )
                except Exception as exc:  # pragma: no cover - 방어 코드
                    logger.warning(
                        "가격 정보 표준화 실패 - exchange=%s symbol=%s error=%s",
                        exchange_name, symbol_upper, exc
                    )
                    continue

        return normalized_quotes

    def get_futures_ticker_price(self, symbol: str) -> Optional[Decimal]:
        """Binance Futures 현재가 조회 (공용 엔드포인트)"""
        quotes = self.get_price_quotes(
            exchange=Exchange.BINANCE,
            market_type=MarketType.FUTURES,
            symbols=[symbol]
        )
        quote = quotes.get(symbol.upper())
        return quote.last_price if quote else None

    def get_spot_ticker_price(self, symbol: str) -> Optional[Decimal]:
        """Binance Spot 현재가 조회 (공용 엔드포인트)"""
        quotes = self.get_price_quotes(
            exchange=Exchange.BINANCE,
            market_type=MarketType.SPOT,
            symbols=[symbol]
        )
        quote = quotes.get(symbol.upper())
        return quote.last_price if quote else None

    def get_all_futures_ticker_prices(self) -> Dict[str, Decimal]:
        """Binance Futures 전체 심볼 현재가 조회"""
        quotes = self.get_price_quotes(Exchange.BINANCE, MarketType.FUTURES)
        return {symbol: quote.last_price for symbol, quote in quotes.items()}

    def get_all_spot_ticker_prices(self) -> Dict[str, Decimal]:
        """Binance Spot 전체 심볼 현재가 조회"""
        quotes = self.get_price_quotes(Exchange.BINANCE, MarketType.SPOT)
        return {symbol: quote.last_price for symbol, quote in quotes.items()}


    def get_precision_cache_stats(self) -> Dict[str, Any]:
        """Precision 캐시 통계 반환 (admin.py에서 호출)"""
        with self.precision_cache._lock:
            current_time = time.time()
            active_entries = 0
            expired_entries = 0
            exchange_breakdown = defaultdict(int)

            for cache_key, precision_data in self.precision_cache.precision_data.items():
                last_update = self.precision_cache.last_update.get(cache_key, 0)
                if current_time - last_update < self.precision_cache.cache_ttl:
                    active_entries += 1
                else:
                    expired_entries += 1

                # 거래소별 통계
                exchange_name = cache_key.split('_')[0]
                exchange_breakdown[exchange_name] += 1

            return {
                'total_entries': len(self.precision_cache.precision_data),
                'active_entries': active_entries,
                'expired_entries': expired_entries,
                'cache_ttl_seconds': self.precision_cache.cache_ttl,
                'exchange_breakdown': dict(exchange_breakdown)
            }

    def clear_precision_cache(self, exchange_name: Optional[str] = None) -> None:
        """Precision 캐시 정리 (admin.py에서 호출)"""
        with self.precision_cache._lock:
            if exchange_name:
                # 특정 거래소 캐시만 정리
                exchange_name = exchange_name.lower()
                keys_to_remove = [
                    key for key in self.precision_cache.precision_data.keys()
                    if key.startswith(f"{exchange_name}_")
                ]
                for key in keys_to_remove:
                    self.precision_cache.precision_data.pop(key, None)
                    self.precision_cache.last_update.pop(key, None)
                logger.info(f"✅ {exchange_name} precision 캐시 {len(keys_to_remove)}개 항목 정리")
            else:
                # 전체 캐시 정리
                count = len(self.precision_cache.precision_data)
                self.precision_cache.precision_data.clear()
                self.precision_cache.last_update.clear()
                logger.info(f"✅ 전체 precision 캐시 {count}개 항목 정리")

    # @FEAT:precision-system @COMP:service @TYPE:core
    def warm_up_all_market_info(self) -> Dict[str, Any]:
        """
        서버 시작 시 모든 거래소의 MarketInfo를 선행 로드 (Warmup)

        Returns:
            Dict: {
                'total_exchanges': int,      # 로딩 시도한 거래소 수
                'total_markets': int,         # 로드된 총 마켓 수
                'failed': List[str],          # 실패한 거래소 목록
                'elapsed': float              # 소요 시간 (초)
            }

        Note:
            - ThreadPoolExecutor로 병렬 로딩 (60초 per-exchange, 120초 total)
            - 일부 실패해도 계속 진행 (degraded mode)
            - 첫 주문부터 캐시 히트 보장 (딜레이 제로)
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
        import time

        start_time = time.time()
        logger.info("🔄 MarketInfo Warmup 시작...")

        # 활성 계좌 조회 (거래소별 그룹화)
        active_accounts = Account.query.filter_by(is_active=True).all()
        if not active_accounts:
            logger.warning("⚠️ 활성 계좌 없음 - Warmup 건너뜀")
            return {
                'total_exchanges': 0,
                'total_markets': 0,
                'failed': [],
                'elapsed': time.time() - start_time
            }

        # 거래소별 그룹화 (중복 제거)
        exchange_accounts = {}
        for acc in active_accounts:
            key = f"{acc.exchange}_{acc.account_type}"
            if key not in exchange_accounts:
                exchange_accounts[key] = acc

        # 병렬 로딩 함수
        def load_exchange_markets(exchange_key: str, account: Account) -> Tuple[str, int]:
            """단일 거래소 MarketInfo 로드 (60초 타임아웃)"""
            try:
                adapter = self.get_exchange(account)
                if not adapter:
                    logger.error(f"  ❌ {exchange_key}: 어댑터 생성 실패")
                    return (exchange_key, 0)

                # Spot markets
                spot_count = 0
                try:
                    spot_markets = adapter.load_markets('spot', reload=False)
                    spot_count = len(spot_markets) if spot_markets else 0
                except Exception as e:
                    logger.debug(f"  ℹ️  {exchange_key}: spot 미지원 또는 로드 실패 - {e}")

                # Futures markets (지원하는 경우)
                futures_count = 0
                try:
                    futures_markets = adapter.load_markets('futures', reload=False)
                    futures_count = len(futures_markets) if futures_markets else 0
                except Exception as e:
                    logger.debug(f"  ℹ️  {exchange_key}: futures 미지원 또는 로드 실패 - {e}")

                total_count = spot_count + futures_count
                logger.info(f"  ✅ {exchange_key}: {total_count}개 마켓 로드 (spot: {spot_count}, futures: {futures_count})")
                return (exchange_key, total_count)

            except Exception as e:
                logger.error(f"  ❌ {exchange_key} 로드 실패: {e}")
                return (exchange_key, 0)

        # ThreadPoolExecutor로 병렬 실행
        total_markets = 0
        failed_exchanges = []

        with ThreadPoolExecutor(max_workers=5) as executor:
            # Submit all tasks
            futures = {
                executor.submit(load_exchange_markets, key, acc): key
                for key, acc in exchange_accounts.items()
            }

            # Collect results with 120-second total timeout
            try:
                for future in as_completed(futures, timeout=120):
                    exchange_key = futures[future]
                    try:
                        # 60-second per-exchange timeout
                        exchange_name, count = future.result(timeout=60)
                        if count > 0:
                            total_markets += count
                        else:
                            failed_exchanges.append(exchange_name)

                    except TimeoutError:
                        logger.error(f"  ⏱️ {exchange_key} 타임아웃 (>60초)")
                        failed_exchanges.append(exchange_key)
                    except Exception as e:
                        logger.error(f"  ❌ {exchange_key} 실패: {e}")
                        failed_exchanges.append(exchange_key)

            except TimeoutError:
                logger.error("⏱️ Warmup 전체 타임아웃 (>120초) - 완료된 거래소만 사용")
                # 타임아웃 된 거래소들은 failed로 처리
                for future, key in futures.items():
                    if not future.done():
                        failed_exchanges.append(key)

        elapsed = time.time() - start_time

        # 결과 로깅
        success_count = len(exchange_accounts) - len(failed_exchanges)
        if failed_exchanges:
            logger.warning(
                f"⚠️ MarketInfo Warmup 완료 (일부 실패) - "
                f"성공: {success_count}/{len(exchange_accounts)}, "
                f"마켓: {total_markets}개, "
                f"소요: {elapsed:.1f}초, "
                f"실패: {failed_exchanges}"
            )
        else:
            logger.info(
                f"✅ MarketInfo Warmup 완료 - "
                f"거래소: {len(exchange_accounts)}개, "
                f"마켓: {total_markets}개, "
                f"소요: {elapsed:.1f}초"
            )

        return {
            'total_exchanges': len(exchange_accounts),
            'total_markets': total_markets,
            'failed': failed_exchanges,
            'elapsed': elapsed
        }

    # @FEAT:precision-system @COMP:service @TYPE:core
    def refresh_api_based_market_info(self) -> Dict[str, Any]:
        """
        API 기반 거래소의 MarketInfo 백그라운드 갱신

        - Binance, Bybit 등 API 기반 거래소만 선택적 갱신
        - Upbit, Bithumb 등 고정 규칙 거래소는 건너뜀
        - 5분 17초(317초) 주기로 실행 (소수 시간대)

        Returns:
            Dict: {
                'refreshed_exchanges': List[str],  # 갱신된 거래소 목록
                'total_markets': int,               # 갱신된 총 마켓 수
                'skipped': List[str],               # 건너뛴 거래소 목록
                'elapsed': float                    # 소요 시간 (초)
            }

        Note:
            - DEBUG 로그 레벨 (고빈도 작업, CLAUDE.md 백그라운드 로깅 가이드라인)
            - 갱신 실패 시 기존 캐시 유지 (stale data better than crash)
            - 주문 경로는 영향 없음 (항상 캐시 사용)
        """
        from app.models import Account
        from app.exchanges.metadata import requires_market_refresh
        import time

        logger.debug("🔄 MarketInfo 백그라운드 갱신 시작...")
        start_time = time.time()

        # 활성 계좌 조회
        active_accounts = Account.query.filter_by(is_active=True).all()
        if not active_accounts:
            logger.debug("⚠️ 활성 계좌 없음 - 백그라운드 갱신 건너뜀")
            return {
                'refreshed_exchanges': [],
                'total_markets': 0,
                'skipped': [],
                'elapsed': time.time() - start_time
            }

        # 거래소별 그룹화 (중복 제거)
        exchange_accounts = {}
        for acc in active_accounts:
            key = f"{acc.exchange}_{acc.account_type}"
            if key not in exchange_accounts:
                exchange_accounts[key] = acc

        refreshed = []
        skipped = []
        total_markets = 0

        for exchange_key, account in exchange_accounts.items():
            exchange_name = account.exchange

            # requires_refresh 체크
            if not requires_market_refresh(exchange_name):
                logger.debug(f"  ⏭️ {exchange_name} 건너뛰기 (고정 규칙 기반)")
                skipped.append(exchange_name)
                continue

            try:
                adapter = self.get_exchange(account)

                # Spot 갱신
                spot_markets = adapter.load_markets('spot', reload=True)
                spot_count = len(spot_markets)
                total_markets += spot_count
                logger.debug(f"  ✅ {exchange_name} SPOT 갱신: {spot_count}개")

                # Futures 갱신 (지원하는 경우)
                if hasattr(adapter, 'futures_markets_cache'):
                    futures_markets = adapter.load_markets('futures', reload=True)
                    futures_count = len(futures_markets)
                    total_markets += futures_count
                    logger.debug(f"  ✅ {exchange_name} FUTURES 갱신: {futures_count}개")

                refreshed.append(exchange_name)

            except Exception as e:
                logger.error(f"  ❌ {exchange_name} 갱신 실패: {e}")
                # 실패해도 계속 진행 (기존 캐시 유지)

        elapsed = time.time() - start_time

        # 결과 로깅 (DEBUG 레벨 - 고빈도 작업)
        if refreshed or skipped:
            logger.debug(
                f"🔄 MarketInfo 백그라운드 갱신 완료 - "
                f"갱신: {len(refreshed)}개, 건너뜀: {len(skipped)}개, "
                f"마켓: {total_markets}개, 소요: {elapsed:.1f}초"
            )

        return {
            'refreshed_exchanges': refreshed,
            'total_markets': total_markets,
            'skipped': skipped,
            'elapsed': elapsed
        }

    def warm_up_precision_cache(self) -> None:
        """
        Precision 캐시 웜업 (admin.py에서 호출)
        활성 StrategyAccount의 주요 심볼에 대한 precision 정보를 미리 로드
        """
        try:
            from app.models import StrategyAccount, Account
            from app.constants import AccountType
            from sqlalchemy.orm import contains_eager
            from app import db

            # StrategyAccount 기준으로 웜업 (Account 대신)
            # Eager loading으로 N+1 쿼리 방지
            strategy_accounts = StrategyAccount.query.join(
                StrategyAccount.account
            ).join(
                StrategyAccount.strategy
            ).options(
                contains_eager(StrategyAccount.account),
                contains_eager(StrategyAccount.strategy)
            ).filter(
                StrategyAccount.is_active == True,
                Account.is_active == True
            ).all()

            logger.info(f"🔍 Precision 캐시 웜업 시작 - {len(strategy_accounts)}개 StrategyAccount")

            success_count = 0
            skip_count = 0
            error_count = 0

            for sa in strategy_accounts:
                account = sa.account
                strategy = sa.strategy

                # CRYPTO 계좌만 웜업 (증권은 precision 개념 없음)
                if not AccountType.is_crypto(account.account_type):
                    skip_count += 1
                    logger.debug(f"증권 계좌 웜업 스킵 - Account: {account.name}, Type: {account.account_type}")
                    continue

                try:
                    client = self.get_exchange_client(account)
                    if not client:
                        error_count += 1
                        continue

                    # 주요 심볼 목록 (전략별로 확장 가능)
                    symbols = ['BTCUSDT', 'ETHUSDT']

                    for symbol in symbols:
                        try:
                            from app.services.symbol_validator import symbol_validator

                            # strategy.market_type 사용 (account.market_type 제거)
                            # AttributeError 대비 방어 코드
                            try:
                                market_type = strategy.market_type.lower() if strategy.market_type else 'spot'
                            except AttributeError:
                                logger.warning(
                                    f"Strategy {strategy.id} has no market_type, defaulting to 'spot'. "
                                    f"Account: {account.name}, Exchange: {account.exchange}"
                                )
                                market_type = 'spot'

                            market_info = symbol_validator.get_market_info(
                                account.exchange,
                                symbol,
                                market_type
                            )

                            if market_info:
                                # 캐시에 저장
                                self.precision_cache.set_precision_info(
                                    account.exchange,
                                    symbol,
                                    market_type,
                                    {
                                        'amount': market_info.quantity_precision,
                                        'price': market_info.price_precision,
                                        'filters': {
                                            'min_quantity': float(market_info.min_quantity),
                                            'max_quantity': float(market_info.max_quantity),
                                            'min_price': float(market_info.min_price),
                                            'max_price': float(market_info.max_price),
                                            'min_notional': float(market_info.min_notional)
                                        }
                                    }
                                )
                                success_count += 1
                                logger.debug(
                                    f"✅ Precision 캐시 웜업 성공 - "
                                    f"Exchange: {account.exchange}, Symbol: {symbol}, "
                                    f"Strategy: {strategy.name}, Market: {market_type}"
                                )
                        except Exception as e:
                            error_count += 1
                            logger.debug(
                                f"Symbol {symbol} precision 로드 실패 - "
                                f"Exchange: {account.exchange}, Symbol: {symbol}, "
                                f"Strategy: {strategy.name}, Account: {account.name}, "
                                f"Error: {e}"
                            )

                except Exception as e:
                    error_count += 1
                    logger.error(
                        f"StrategyAccount {sa.id} precision 웜업 실패 - "
                        f"Strategy: {strategy.name}, Account: {account.name}, "
                        f"Error: {e}"
                    )

            logger.info(
                f"✅ Precision 캐시 웜업 완료 - "
                f"성공: {success_count}, 스킵: {skip_count}, 실패: {error_count}"
            )

        except Exception as e:
            logger.error(f"Precision 캐시 웜업 실패: {e}", exc_info=True)


# 싱글톤 인스턴스
exchange_service = ExchangeService()
