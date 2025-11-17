"""
Symbol 제한사항 검증 서비스

@FEAT:symbol-validation @COMP:service @TYPE:core

거래소별 Symbol 제한사항(LOT_SIZE, PRICE_FILTER, MIN_NOTIONAL 등)을
메모리에 캐싱하고 고속으로 검증하는 서비스입니다.

주요 기능:
- 백그라운드에서 주기적으로 Symbol 정보 갱신 (매시 15분)
- 메모리 기반 고속 검증 (네트워크 요청 없음)
- 자동 소수점 조정 및 제한사항 검증
- 여러 거래소 확장 가능한 구조
"""

import logging
import time
import threading
from typing import Dict, Any, Optional, Tuple
from decimal import Decimal, ROUND_DOWN
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

from app.models import Account
from app.exchanges.models import MarketInfo
from app.constants import Exchange

logger = logging.getLogger(__name__)


class SymbolValidationError(Exception):
    """Symbol 검증 관련 오류"""
    pass


# @FEAT:exchange-service-initialization @FEAT:symbol-validation @COMP:service @TYPE:core
class SymbolValidator:
    """
    Symbol 제한사항 검증 서비스

    특징:
    - 메모리 기반 고속 검증 (네트워크 병목 없음)
    - 백그라운드 주기적 갱신 (매시 15분)
    - 자동 소수점 조정 및 제한사항 검증
    - 여러 거래소 지원 구조
    """

    def __init__(self):
        self.market_info_cache: Dict[str, MarketInfo] = {}
        self.cache_last_updated: Dict[str, float] = {}
        self.cache_lock = threading.RLock()
        self.is_initialized = False

        logger.info("Symbol Validator initialized successfully")

    # @FEAT:symbol-validation @FEAT:background-scheduler @COMP:service @TYPE:integration
    def refresh_symbols(self):
        """Flask app context와 함께 Symbol 정보 갱신 (APScheduler용)"""
        from app import get_flask_app
        app = get_flask_app()
        with app.app_context():
            self._refresh_all_symbols()

    # @FEAT:symbol-validation @FEAT:exchange-integration @COMP:service @TYPE:core
    def load_initial_symbols(self):
        """
        서비스 시작 시 모든 거래소 심볼 정보 필수 로드 (Public API)

        WHY CryptoExchangeFactory 기반 동적 로딩:
        - 하드코딩 제거: 새 거래소 추가 시 코드 수정 불필요
        - 메타데이터 활용: ExchangeMetadata의 supported_markets로 market_type 자동 필터링
        - 확장성: 모든 거래소를 동일한 방식으로 처리

        변경 내역 (2025-10-13):
        - 기존: _load_binance_public_symbols() 하드코딩
        - 현재: crypto_factory.SUPPORTED_EXCHANGES 순회 + metadata 기반 필터링
        """
        try:
            from app.exchanges.crypto.factory import crypto_factory
            from app.exchanges.metadata import ExchangeMetadata

            logger.info("Loading exchange symbol information (Public API)")

            # 로드 전 캐시 상태 확인
            logger.info(f"Pre-load cache status: {len(self.market_info_cache)} symbols")

            success_count = 0

            # ⭐ 기존 CryptoExchangeFactory 활용하여 모든 거래소 순회
            for exchange_name in crypto_factory.SUPPORTED_EXCHANGES:
                metadata = ExchangeMetadata.get_metadata(exchange_name)
                supported_markets = metadata.get('supported_markets', [])

                if not supported_markets:
                    logger.warning(f"{exchange_name}: No supported market types (skipping)")
                    continue

                try:
                    # Public API 사용 (API 키 불필요)
                    exchange = crypto_factory.create(exchange_name, '', '', testnet=False)

                    for market_type in supported_markets:
                        try:
                            logger.info(f"Loading {exchange_name.upper()} {market_type.value.upper()} symbol information...")
                            markets = exchange.load_markets_impl(market_type.value, reload=True)

                            with self.cache_lock:
                                for symbol, market_info in markets.items():
                                    cache_key = f"{exchange_name.upper()}_{symbol}_{market_type.value.upper()}"
                                    self.market_info_cache[cache_key] = market_info
                                    self.cache_last_updated[cache_key] = time.time()
                                    success_count += 1

                            logger.info(f"Loaded {exchange_name.upper()} {market_type.value.upper()} symbols: {len(markets)}")

                        except Exception as e:
                            logger.error(f"Failed to load {exchange_name.upper()} {market_type.value.upper()} symbols: {e}")

                except Exception as e:
                    logger.error(f"Failed to create {exchange_name} exchange instance: {e}")

            # 로드 후 캐시 상태 확인
            logger.info(f"Post-load cache status: {len(self.market_info_cache)} symbols")

            if not self.market_info_cache:
                error_msg = "Unable to load symbol information - trading disabled"
                logger.error(error_msg)
                raise Exception(error_msg)

            # 초기화 완료 플래그 설정
            self.is_initialized = True
            logger.info(f"Exchange symbol information loaded: {success_count} symbols (initialization flag set)")

        except Exception as e:
            logger.error(f"Failed to load exchange symbols: {e}")
            raise Exception(f"Cannot start service due to failure loading exchange symbol information: {e}")

    # @FEAT:symbol-validation @FEAT:background-scheduler @COMP:service @TYPE:helper
    def _refresh_all_symbols(self):
        """
        모든 Symbol 정보 갱신 (백그라운드 작업)

        WHY 메타데이터 기반 필터링:
        - 거래소별 지원 market_type 자동 감지
        - Upbit SPOT 전용, Binance SPOT/FUTURES 모두 지원
        - "Upbit은 Futures 지원하지 않음" 에러 제거

        변경 내역 (2025-10-13):
        - 기존: 하드코딩된 market_type 순회
        - 현재: ExchangeMetadata.supported_markets 기반 필터링
        """
        try:
            from app.exchanges.crypto.factory import crypto_factory
            from app.exchanges.metadata import ExchangeMetadata
            from app.models import Account

            logger.info("Starting background symbol information refresh")
            refresh_start_time = time.time()

            accounts = Account.query.filter_by(is_active=True).all()

            # 거래소별 계좌 그룹화 (첫 번째 활성 계좌만 사용)
            exchange_accounts = {}
            for account in accounts:
                exchange_name = account.exchange.lower()
                if exchange_name not in exchange_accounts and exchange_name in crypto_factory.SUPPORTED_EXCHANGES:
                    exchange_accounts[exchange_name] = account

            total_refreshed = 0

            # ⭐ 기존 CryptoExchangeFactory 활용
            for exchange_name, account in exchange_accounts.items():
                metadata = ExchangeMetadata.get_metadata(exchange_name)
                supported_markets = metadata.get('supported_markets', [])

                try:
                    exchange = crypto_factory.create(
                        exchange_name,
                        account.api_key,
                        account.api_secret,
                        account.is_testnet
                    )

                    for market_type in supported_markets:
                        try:
                            markets = exchange.load_markets_impl(market_type.value, reload=True)

                            with self.cache_lock:
                                for symbol, market_info in markets.items():
                                    cache_key = f"{exchange_name.upper()}_{symbol}_{market_type.value.upper()}"
                                    self.market_info_cache[cache_key] = market_info
                                    self.cache_last_updated[cache_key] = time.time()
                                    total_refreshed += 1

                            logger.info(f"{exchange_name.upper()} {market_type.value} Symbol 로드: {len(markets)}개")

                        except Exception as e:
                            logger.error(f"{exchange_name.upper()} {market_type.value} Symbol 로드 실패: {e}")

                except Exception as e:
                    logger.error(f"{exchange_name} Symbol 갱신 실패: {e}")

            refresh_duration = time.time() - refresh_start_time

            logger.info(f"Background symbol refresh completed: {total_refreshed} symbols, "
                       f"duration: {refresh_duration:.2f}s")

        except Exception as e:
            logger.error(f"Background symbol refresh failed: {e}")

    # @FEAT:symbol-validation @COMP:service @TYPE:helper
    def get_market_info(self, exchange: str, symbol: str, market_type: str) -> Optional[MarketInfo]:
        """메모리에서 MarketInfo 조회 (네트워크 요청 없음)"""
        cache_key = f"{exchange.upper()}_{symbol.upper()}_{market_type.upper()}"

        with self.cache_lock:
            return self.market_info_cache.get(cache_key)

    # @FEAT:symbol-validation @COMP:service @TYPE:validation
    def validate_order_params(self, exchange: str, symbol: str, market_type: str,
                            quantity: Decimal, price: Optional[Decimal] = None) -> Dict[str, Any]:
        """
        주문 파라미터 검증 (메모리 기반, 네트워크 요청 없음)

        Returns:
            {
                'success': bool,
                'adjusted_quantity': Decimal,
                'adjusted_price': Optional[Decimal],
                'error': str (실패 시)
            }
        """
        try:
            cache_key = f"{exchange.upper()}_{symbol.upper()}_{market_type.upper()}"
            logger.debug(f"Starting order parameter validation: {cache_key}, quantity={quantity}, price={price}")

            market_info = self.get_market_info(exchange, symbol, market_type)

            if not market_info:
                # 심볼 정보가 없으면 거래 불가
                error_msg = f'Symbol information not found: {cache_key}'
                logger.error(error_msg)

                # 디버그: 현재 캐시 상태 출력
                logger.error(f"Current cache status: total {len(self.market_info_cache)} symbols")
                logger.error(f"Cache key samples (first 5): {list(self.market_info_cache.keys())[:5]}")
                logger.error(f"Initialization status: {self.is_initialized}")

                return {
                    'success': False,
                    'error': error_msg,
                    'error_type': 'symbol_not_found'
                }

            # 수량 검증 및 조정
            quantity_result = self._validate_and_adjust_quantity(market_info, quantity)
            if not quantity_result['success']:
                return quantity_result

            # 가격 검증 및 조정
            price_result = self._validate_and_adjust_price(market_info, price)
            if not price_result['success']:
                return price_result

            adjusted_quantity = quantity_result['adjusted_quantity']
            adjusted_price = price_result['adjusted_price']

            # 최소 거래금액(MIN_NOTIONAL) 검증
            if adjusted_price and adjusted_quantity:
                total_value = adjusted_quantity * adjusted_price
                if total_value < market_info.min_notional:
                    return {
                        'success': False,
                        'error': f'최소 거래금액 미달: {total_value} < {market_info.min_notional}',
                        'error_type': 'min_notional_error',
                        'min_notional': market_info.min_notional,
                        'min_quantity': quantity_result.get('min_quantity'),
                        'step_size': quantity_result.get('step_size')
                    }

            return {
                'success': True,
                'adjusted_quantity': adjusted_quantity,
                'adjusted_price': adjusted_price,
                'min_quantity': quantity_result.get('min_quantity'),
                'step_size': quantity_result.get('step_size'),
                'min_notional': market_info.min_notional
            }

        except Exception as e:
            logger.error(f"주문 파라미터 검증 실패: {e}")
            return {
                'success': False,
                'error': str(e),
                'error_type': 'validation_error'
            }

    # @FEAT:symbol-validation @COMP:service @TYPE:validation
    def _validate_and_adjust_quantity(self, market_info: MarketInfo, quantity: Decimal) -> Dict[str, Any]:
        """수량 검증 및 조정"""
        try:
            # 최소/최대 수량 검증
            if quantity < market_info.min_qty:
                return {
                    'success': False,
                    'error': f'최소 수량 미달: {quantity} < {market_info.min_qty}',
                    'error_type': 'min_quantity_error',
                    'min_quantity': market_info.min_qty,
                    'step_size': market_info.step_size,
                    'min_notional': market_info.min_notional
                }

            if market_info.max_qty > 0 and quantity > market_info.max_qty:
                return {
                    'success': False,
                    'error': f'최대 수량 초과: {quantity} > {market_info.max_qty}',
                    'error_type': 'max_quantity_error'
                }

            # 소수점 자리수 조정 (내림)
            step_size = market_info.step_size
            if step_size > 0:
                # step_size의 소수점 자리수에 맞춰 조정
                precision = abs(step_size.as_tuple().exponent)
                adjusted_quantity = quantity.quantize(
                    Decimal('0.1') ** precision,
                    rounding=ROUND_DOWN
                )
            else:
                # 기본 precision 사용
                adjusted_quantity = quantity.quantize(
                    Decimal('0.1') ** market_info.amount_precision,
                    rounding=ROUND_DOWN
                )

            return {
                'success': True,
                'adjusted_quantity': adjusted_quantity,
                'min_quantity': market_info.min_qty,
                'step_size': step_size if step_size and step_size > 0 else Decimal('0.1') ** market_info.amount_precision,
                'min_notional': market_info.min_notional
            }

        except Exception as e:
            return {
                'success': False,
                'error': f'수량 조정 실패: {str(e)}',
                'error_type': 'quantity_adjustment_error'
            }

    # @FEAT:symbol-validation @COMP:service @TYPE:validation
    def _validate_and_adjust_price(self, market_info: MarketInfo, price: Optional[Decimal]) -> Dict[str, Any]:
        """가격 검증 및 조정"""
        try:
            if price is None:
                return {'success': True, 'adjusted_price': None}

            # 최소/최대 가격 검증
            if price < market_info.min_price:
                return {
                    'success': False,
                    'error': f'최소 가격 미달: {price} < {market_info.min_price}',
                    'error_type': 'min_price_error'
                }

            if market_info.max_price > 0 and price > market_info.max_price:
                return {
                    'success': False,
                    'error': f'최대 가격 초과: {price} > {market_info.max_price}',
                    'error_type': 'max_price_error'
                }

            # 소수점 자리수 조정 (내림)
            tick_size = market_info.tick_size
            if tick_size > 0:
                # tick_size의 소수점 자리수에 맞춰 조정
                precision = abs(tick_size.as_tuple().exponent)
                adjusted_price = price.quantize(
                    Decimal('0.1') ** precision,
                    rounding=ROUND_DOWN
                )
            else:
                # 기본 precision 사용
                adjusted_price = price.quantize(
                    Decimal('0.1') ** market_info.price_precision,
                    rounding=ROUND_DOWN
                )

            return {
                'success': True,
                'adjusted_price': adjusted_price
            }

        except Exception as e:
            return {
                'success': False,
                'error': f'가격 조정 실패: {str(e)}',
                'error_type': 'price_adjustment_error'
            }


    # @FEAT:symbol-validation @COMP:service @TYPE:helper
    def get_cache_stats(self) -> Dict[str, Any]:
        """캐시 통계 조회"""
        with self.cache_lock:
            return {
                'total_symbols': len(self.market_info_cache),
                'is_initialized': self.is_initialized,
                'cache_keys': list(self.market_info_cache.keys())[:10]  # 처음 10개만
            }


# 전역 인스턴스
symbol_validator = SymbolValidator()
