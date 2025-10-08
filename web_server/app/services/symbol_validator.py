"""
Symbol 제한사항 검증 서비스

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

        logger.info("✅ Symbol Validator 초기화 완료")

    def refresh_symbols_with_context(self, app):
        """Flask app context와 함께 Symbol 정보 갱신 (APScheduler용)"""
        with app.app_context():
            self._refresh_all_symbols()

    def load_initial_symbols(self):
        """서비스 시작 시 모든 거래소 심볼 정보 필수 로드 (Public API 사용)"""
        try:
            logger.info("🔄 거래소 심볼 정보 로드 시작 (Public API)")

            # 로드 전 캐시 상태 확인
            logger.info(f"📊 로드 전 캐시 상태: {len(self.market_info_cache)}개 심볼")

            # Binance public API로 심볼 정보 로드
            success_count = self._load_binance_public_symbols()

            # 추후 다른 거래소 추가
            # success_count += self._load_bybit_public_symbols()
            # success_count += self._load_okx_public_symbols()

            # 로드 후 캐시 상태 확인
            logger.info(f"📊 로드 후 캐시 상태: {len(self.market_info_cache)}개 심볼")

            # 중요한 심볼 확인 (BTCUSDT FUTURES)
            btc_futures_key = "BINANCE_BTCUSDT_FUTURES"
            if btc_futures_key in self.market_info_cache:
                market_info = self.market_info_cache[btc_futures_key]
                logger.info(f"🔍 BTCUSDT FUTURES 정보 확인: min_qty={market_info.min_qty}, step_size={market_info.step_size}, min_notional={market_info.min_notional}")
            else:
                logger.warning(f"⚠️ BTCUSDT FUTURES 정보를 찾을 수 없음: {btc_futures_key}")

            if not self.market_info_cache:
                error_msg = "심볼 정보를 로드할 수 없습니다 - 거래 불가"
                logger.error(f"❌ {error_msg}")
                raise Exception(error_msg)

            # 초기화 완료 플래그 설정
            self.is_initialized = True
            logger.info(f"✅ 거래소 심볼 정보 로드 완료: {success_count}개 (초기화 플래그 설정됨)")

        except Exception as e:
            logger.error(f"❌ 거래소 심볼 로드 실패: {e}")
            raise Exception(f"거래소 심볼 정보를 로드할 수 없어 서비스를 시작할 수 없습니다: {e}")

    def _load_binance_public_symbols(self) -> int:
        """Binance public API로 심볼 정보 로드 (계정 불필요)"""
        try:
            from app.exchanges.crypto.binance import BinanceExchange

            # API 키 없이 public 엔드포인트 사용
            exchange = BinanceExchange(
                api_key='',  # public API는 키 불필요
                api_secret='',
                testnet=False
            )

            loaded_count = 0

            # Spot과 Futures 모두 로드
            for market_type in ['spot', 'futures']:
                try:
                    logger.info(f"🔄 Binance {market_type.upper()} 심볼 정보 로드 중...")
                    markets = exchange.load_markets(market_type, reload=True)

                    with self.cache_lock:
                        for symbol, market_info in markets.items():
                            cache_key = f"BINANCE_{symbol}_{market_type.upper()}"
                            self.market_info_cache[cache_key] = market_info
                            self.cache_last_updated[cache_key] = time.time()
                            loaded_count += 1

                    logger.info(f"✅ Binance {market_type.upper()} 심볼 로드: {len(markets)}개")

                except Exception as e:
                    logger.error(f"❌ Binance {market_type.upper()} 심볼 로드 실패: {e}")

            return loaded_count

        except Exception as e:
            logger.error(f"❌ Binance Symbol 로드 실패: {e}")
            return 0

    def _load_binance_symbols(self, account: Account) -> int:
        """Binance Symbol 정보 로드"""
        try:
            from app.exchanges.crypto.binance import BinanceExchange

            exchange = BinanceExchange(
                api_key=account.api_key,
                api_secret=account.api_secret,
                testnet=account.is_testnet
            )

            loaded_count = 0

            # Spot과 Futures 모두 로드
            for market_type in ['spot', 'futures']:
                try:
                    markets = exchange.load_markets(market_type, reload=True)

                    with self.cache_lock:
                        for symbol, market_info in markets.items():
                            cache_key = f"BINANCE_{symbol}_{market_type.upper()}"
                            self.market_info_cache[cache_key] = market_info
                            self.cache_last_updated[cache_key] = time.time()
                            loaded_count += 1

                    logger.info(f"Binance {market_type} Symbol 로드: {len(markets)}개")

                except Exception as e:
                    logger.error(f"Binance {market_type} Symbol 로드 실패: {e}")

            return loaded_count

        except Exception as e:
            logger.error(f"Binance Symbol 로드 실패: {e}")
            return 0


    def _refresh_all_symbols(self):
        """모든 Symbol 정보 갱신 (백그라운드 작업)"""
        try:
            logger.info("🔄 백그라운드 Symbol 정보 갱신 시작")
            refresh_start_time = time.time()

            from app.models import Account
            accounts = Account.query.filter_by(is_active=True).all()

            total_refreshed = 0

            for account in accounts:
                if account.exchange == 'BINANCE':
                    refreshed = self._load_binance_symbols(account)
                    total_refreshed += refreshed
                # 추후 다른 거래소 추가

            refresh_duration = time.time() - refresh_start_time

            logger.info(f"✅ 백그라운드 Symbol 갱신 완료: {total_refreshed}개, "
                       f"소요시간: {refresh_duration:.2f}초")

        except Exception as e:
            logger.error(f"백그라운드 Symbol 갱신 실패: {e}")

    def get_market_info(self, exchange: str, symbol: str, market_type: str) -> Optional[MarketInfo]:
        """메모리에서 MarketInfo 조회 (네트워크 요청 없음)"""
        cache_key = f"{exchange.upper()}_{symbol.upper()}_{market_type.upper()}"

        with self.cache_lock:
            return self.market_info_cache.get(cache_key)

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
            logger.debug(f"🔍 주문 파라미터 검증 시작: {cache_key}, 수량={quantity}, 가격={price}")

            market_info = self.get_market_info(exchange, symbol, market_type)

            if not market_info:
                # 심볼 정보가 없으면 거래 불가
                error_msg = f'심볼 정보를 찾을 수 없습니다: {cache_key}'
                logger.error(f"❌ {error_msg}")

                # 디버그: 현재 캐시 상태 출력
                logger.error(f"📊 현재 캐시 상태: 총 {len(self.market_info_cache)}개 심볼")
                logger.error(f"📊 캐시 키 샘플 (처음 5개): {list(self.market_info_cache.keys())[:5]}")
                logger.error(f"📊 초기화 상태: {self.is_initialized}")

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
