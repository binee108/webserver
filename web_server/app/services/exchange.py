"""
Exchange 서비스 통합 모듈

exchange_integrated_service.py 와 capital_service.py를 통합하여
하나의 일관된 서비스로 제공합니다.
"""
import logging
from typing import Dict, List, Optional, Union, TYPE_CHECKING

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

    def register_crypto_exchange(self, name: str, exchange: 'BaseCryptoExchange'):
        """암호화폐 거래소 등록"""
        self._crypto_exchanges[name] = exchange

    def register_securities_exchange(self, name: str, exchange: 'BaseSecuritiesExchange'):
        """증권 거래소 등록"""
        self._securities_exchanges[name] = exchange

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
                side=order_data['side'],
                order_type=order_data['type'],
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
                        side=order_data['side'],
                        order_type=order_data['type'],
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