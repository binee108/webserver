"""
통합 거래소 서비스

Rate Limit + Precision Cache + Exchange Logic + Adapter Factory 통합
1인 사용자를 위한 단순하고 효율적인 거래소 관리 서비스입니다.
"""

import time
import logging
from typing import Dict, Any, Optional, List, Tuple, Union, TYPE_CHECKING
from decimal import Decimal
from datetime import datetime
from threading import Lock
from collections import defaultdict

from app.models import Account
from app.constants import Exchange, MarketType, OrderType
from app.exchanges.models import PriceQuote

if TYPE_CHECKING:
    from app.exchanges.crypto.base import BaseCryptoExchange
    from app.exchanges.securities.base import BaseSecuritiesExchange

logger = logging.getLogger(__name__)


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

    def acquire_slot(self, exchange: str, endpoint_type: str = 'general') -> None:
        """요청 가능 시점까지 대기한 뒤 슬롯을 확보"""
        exchange = exchange.lower()

        if exchange not in self._limits:
            return

        while True:
            with self._lock:
                current_time = time.time()

                self._request_history[exchange] = [
                    t for t in self._request_history[exchange]
                    if current_time - t < 60
                ]
                self._order_history[exchange] = [
                    t for t in self._order_history[exchange]
                    if current_time - t < 1
                ]

                wait_seconds = 0.0

                limit_per_minute = self._limits[exchange]['requests_per_minute']
                if len(self._request_history[exchange]) >= limit_per_minute:
                    oldest = min(self._request_history[exchange])
                    wait_seconds = max(wait_seconds, oldest + 60 - current_time)

                if endpoint_type == 'order':
                    limit_per_second = self._limits[exchange]['orders_per_second']
                    if len(self._order_history[exchange]) >= limit_per_second:
                        oldest_order = min(self._order_history[exchange])
                        wait_seconds = max(wait_seconds, oldest_order + 1 - current_time)

                if wait_seconds <= 0:
                    self._request_history[exchange].append(current_time)
                    if endpoint_type == 'order':
                        self._order_history[exchange].append(current_time)
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

            balance_map = client.fetch_balance(market_type)
            return {'success': True, 'balance': balance_map}

        except Exception as e:
            logger.error(f"잔액 조회 실패: {e}")
            return {'success': False, 'error': str(e)}

    def cancel_order(self, account: Account, order_id: str, symbol: str,
                    market_type: str = 'spot') -> Dict[str, Any]:
        """주문 취소"""
        try:
            client = self.get_exchange_client(account)
            if not client:
                return {'success': False, 'error': '거래소 클라이언트 없음'}

            self.rate_limiter.acquire_slot(account.exchange, 'order')

            result = client.cancel_order(order_id, symbol, market_type)
            return {'success': True, 'result': result}

        except Exception as e:
            logger.error(f"주문 취소 실패: {e}")
            return {'success': False, 'error': str(e)}

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
                client = self.legacy_factory.create_exchange(exchange_key, api_key='', secret='', testnet=False)
                self._public_exchange_clients[exchange_key] = client
                return client
            except Exception as e:
                logger.error(f"❌ 공용 클라이언트 생성 실패 - exchange={exchange_name}: {e}")
                return None

    def get_price_quotes(self, exchange: str, market_type: str,
                         symbols: Optional[List[str]] = None) -> Dict[str, PriceQuote]:
        """거래소 무관 표준화된 현재가 정보 조회"""
        exchange_name = Exchange.normalize(exchange) if exchange else Exchange.BINANCE
        if not exchange_name or exchange_name not in Exchange.VALID_EXCHANGES:
            exchange_name = Exchange.BINANCE

        normalized_market_type = MarketType.normalize(market_type) if market_type else MarketType.SPOT
        client_market_type = 'futures' if normalized_market_type == MarketType.FUTURES else 'spot'
        symbol_filter = [symbol.upper() for symbol in symbols] if symbols else None

        client = self._get_public_exchange_client(exchange_name)
        if not client:
            return {}

        if not hasattr(client, 'fetch_price_quotes'):
            logger.error(
                "❌ 공용 클라이언트가 가격 조회를 지원하지 않습니다 - exchange=%s",
                exchange_name
            )
            return {}

        try:
            quotes = client.fetch_price_quotes(
                market_type=client_market_type,
                symbols=symbol_filter
            )
        except Exception as e:
            logger.error(
                "❌ 가격 정보 조회 실패 - exchange=%s market_type=%s error=%s",
                exchange_name, client_market_type, e
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
    
    def warm_up_precision_cache(self) -> None:
        """
        Precision 캐시 웜업 (admin.py에서 호출)
        활성 계정의 주요 심볼에 대한 precision 정보를 미리 로드
        """
        try:
            from app.models import Account, StrategyPosition
            
            # 활성 계정 조회
            active_accounts = Account.query.filter_by(is_active=True).all()
            
            for account in active_accounts:
                try:
                    client = self.get_exchange_client(account)
                    if not client:
                        continue
                    
                    # 해당 계정의 최근 포지션에서 심볼 추출
                    # Skip position-based warmup for now
                    recent_positions = []
                    
                    symbols = list(set(pos.symbol for pos in recent_positions if pos.symbol))
                    
                    if not symbols:
                        # 포지션이 없으면 주요 심볼 사용
                        if account.exchange.lower() == 'binance':
                            symbols = ['BTCUSDT', 'ETHUSDT']
                    
                    for symbol in symbols:
                        # Symbol Validator를 사용하여 precision 정보 로드
                        try:
                            from app.services.symbol_validator import symbol_validator
                            market_info = symbol_validator.get_market_info(
                                account.exchange,
                                symbol,
                                'futures' if account.market_type == 'futures' else 'spot'
                            )
                            
                            if market_info:
                                # 캐시에 저장
                                self.precision_cache.set_precision_info(
                                    account.exchange,
                                    symbol,
                                    account.market_type or 'spot',
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
                                logger.info(f"✅ Precision 캐시 웜업: {account.exchange} {symbol}")
                        except Exception as e:
                            logger.warning(f"Symbol {symbol} precision 로드 실패: {e}")
                            
                except Exception as e:
                    logger.error(f"계정 {account.name} precision 웜업 실패: {e}")
            
            logger.info("✅ Precision 캐시 웜업 완료")
            
        except Exception as e:
            logger.error(f"Precision 캐시 웜업 실패: {e}")

    def get_ticker(
        self,
        symbol: str,
        exchange: Optional[str] = None,
        market_type: str = MarketType.SPOT
    ) -> Dict[str, Any]:
        """간단한 시세 조회 (테스트 및 호환성용)"""
        raise NotImplementedError(
            'get_ticker는 외부 거래소 클라이언트가 연결된 환경에서 구현되어야 합니다.'
        )


# 싱글톤 인스턴스
exchange_service = ExchangeService()
