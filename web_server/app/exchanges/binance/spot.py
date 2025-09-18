"""
Binance Spot API 직접 구현

CCXT보다 빠른 성능과 메모리 기반 캐싱으로 무지연 주문 처리를 제공합니다.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any
from decimal import Decimal

from ..base import BaseExchange, ExchangeError, InvalidOrder, InsufficientFunds
from app.services.exchange_service import OrderParsingError
from ..models import MarketInfo, Balance, Order, Ticker
from .constants import (
    SPOT_BASE_URL, SPOT_TESTNET_URL, SPOT_RATE_LIMIT, SPOT_WEIGHT_LIMIT,
    SpotEndpoints, OrderType, OrderSide, OrderStatus, TimeInForce, Weights
)

logger = logging.getLogger(__name__)


class BinanceSpot(BaseExchange):
    """
    Binance Spot API 구현
    
    특징:
    - 메모리 캐싱으로 마켓 정보 무지연 액세스
    - HTTP 세션 재사용으로 연결 최적화  
    - 백그라운드에서 비동기 캐시 업데이트
    - Weight 기반 정밀 Rate Limit 관리
    """
    
    def __init__(self, api_key: str, secret: str, testnet: bool = False):
        super().__init__(api_key, secret, testnet)
        
        # 마켓 초기화 상태
        self._markets_loaded = False
        self._loading_markets = False
        
        logger.info(f"🟡 Binance Spot API 초기화 완료 (testnet={testnet})")
    
    @property
    def base_url(self) -> str:
        return SPOT_TESTNET_URL if self.testnet else SPOT_BASE_URL
    
    @property  
    def market_type(self) -> str:
        return "SPOT"
    
    def get_rate_limit(self) -> int:
        return SPOT_RATE_LIMIT
    
    def get_weight_limit(self) -> int:
        return SPOT_WEIGHT_LIMIT
    
    async def load_markets(self, reload: bool = False) -> Dict[str, MarketInfo]:
        """
        마켓 정보 로드 및 캐싱
        
        캐시 전략:
        1. 첫 호출 시 API에서 로드 후 캐시
        2. 이후 호출은 캐시에서 즉시 반환
        3. 백그라운드에서 주기적 업데이트
        """
        if self._markets_loaded and not reload:
            # 캐시에서 즉시 반환 (무지연)
            cached_markets = {}
            for symbol in self.cache.markets.keys():
                market_info = self.cache.get_market(symbol)
                if market_info:
                    cached_markets[symbol] = market_info
            
            if cached_markets:
                logger.debug(f"📈 마켓 정보 캐시 히트: {len(cached_markets)}개")
                return cached_markets
        
        # 중복 로딩 방지
        if self._loading_markets:
            await asyncio.sleep(0.1)
            return await self.load_markets(reload=False)
        
        self._loading_markets = True
        
        try:
            logger.info("🔄 Binance Spot 마켓 정보 로딩 시작")
            
            # API 호출
            response = self._make_request('GET', SpotEndpoints.EXCHANGE_INFO, weight=Weights.SPOT_EXCHANGE_INFO)
            symbols_data = response.get('symbols', [])
            
            # 캐시 업데이트
            updated_count = self.cache.update_markets_batch(symbols_data, "SPOT")
            
            # 결과 구성
            markets = {}
            for data in symbols_data:
                if data['status'] == 'TRADING':
                    market_info = MarketInfo.from_binance_spot(data)
                    markets[data['symbol']] = market_info
            
            self._markets_loaded = True
            self.stats['last_update'] = self._get_timestamp()
            
            logger.info(f"✅ Binance Spot 마켓 정보 로딩 완료: {updated_count}개 심볼")
            
            # 백그라운드 업데이트 스케줄링 (최초 1회만)
            if not hasattr(self, '_background_scheduled'):
                self.cache.schedule_background_update(
                    lambda: asyncio.run(self.load_markets(reload=True)),
                    interval=3600  # 1시간마다
                )
                self._background_scheduled = True
                logger.info("⏰ 백그라운드 마켓 업데이트 스케줄링 완료")
            
            return markets
            
        except Exception as e:
            logger.error(f"마켓 정보 로딩 실패: {e}")
            raise ExchangeError(f"마켓 정보 로딩 실패: {e}")
        finally:
            self._loading_markets = False
    
    async def fetch_balance(self) -> Dict[str, Balance]:
        """계정 잔액 조회"""
        try:
            response = self._make_request('GET', SpotEndpoints.ACCOUNT, signed=True, weight=Weights.SPOT_ACCOUNT)
            
            balances = {}
            for item in response.get('balances', []):
                asset = item['asset']
                free = Decimal(item['free'])
                locked = Decimal(item['locked'])
                
                if free > 0 or locked > 0:  # 0이 아닌 잔액만
                    balances[asset] = Balance(
                        asset=asset,
                        free=free,
                        locked=locked,
                        total=free + locked
                    )
            
            logger.debug(f"💰 잔액 조회 완료: {len(balances)}개 자산")
            return balances
            
        except Exception as e:
            logger.error(f"잔액 조회 실패: {e}")
            raise ExchangeError(f"잔액 조회 실패: {e}")
    
    async def fetch_ticker(self, symbol: str, params: Optional[Dict] = None) -> Ticker:
        """시세 조회 (캐시 우선, 실패 시 API)"""
        # 캐시에서 먼저 조회
        cached_ticker = self.cache.get_ticker(symbol)
        if cached_ticker:
            self.stats['cache_hits'] += 1
            return cached_ticker
        
        try:
            params = {'symbol': symbol}
            response = self._make_request('GET', SpotEndpoints.TICKER_24HR, params, weight=Weights.SPOT_TICKER_24HR)
            
            ticker = Ticker.from_binance(response)
            
            # 캐시 업데이트
            self.cache.set_ticker(symbol, ticker)
            
            logger.debug(f"📊 시세 조회: {symbol} = ${ticker.last}")
            return ticker
            
        except Exception as e:
            logger.error(f"시세 조회 실패 {symbol}: {e}")
            raise ExchangeError(f"시세 조회 실패: {e}")
    
    async def create_order(self, symbol: str, type: str, side: str, amount: float, price: float = None, params: Dict = None) -> Order:
        """
        주문 생성
        
        무지연 처리 과정:
        1. 캐시된 마켓 정보로 즉시 validation
        2. API 주문 실행
        3. 백그라운드에서 캐시 업데이트
        """
        params = params or {}
        
        # 캐시된 마켓 정보로 즉시 검증 (무지연)
        if not self.get_market_info(symbol):
            logger.warning(f"마켓 정보 없음, API에서 로드: {symbol}")
            await self.load_markets()
        
        # 수량/가격 정규화
        rounded_amount = self.round_amount(symbol, amount)
        rounded_price = self.round_price(symbol, price) if price else None
        
        # 주문 파라미터 구성
        order_params = {
            'symbol': symbol,
            'side': side.upper(),
            'type': type.upper(),
            'quantity': str(rounded_amount)
        }
        
        # 가격 설정
        if type.upper() == OrderType.LIMIT:
            if not rounded_price:
                raise InvalidOrder("LIMIT 주문은 가격이 필요합니다")
            order_params['price'] = str(rounded_price)
            order_params['timeInForce'] = params.get('timeInForce', TimeInForce.GTC)
        
        # STOP 주문 파라미터
        if 'stopPrice' in params:
            order_params['stopPrice'] = str(self.round_price(symbol, float(params['stopPrice'])))
        
        # 추가 파라미터
        order_params.update(params)
        
        try:
            logger.info(f"📤 주문 생성: {side} {rounded_amount} {symbol} @ {rounded_price or 'MARKET'}")

            response = self._make_request('POST', SpotEndpoints.ORDER, order_params, signed=True, weight=Weights.SPOT_ORDER)

            try:
                order = Order.from_binance(response)
            except Exception as parse_error:
                # 주문은 생성됐지만 파싱 실패
                logger.error(f"주문 응답 파싱 실패: {parse_error}, 원본 응답: {response}")
                raise OrderParsingError(f"주문 ID {response.get('orderId', 'unknown')} 파싱 실패") from parse_error

            # 백그라운드에서 마켓 캐시 업데이트 (비동기)
            self.cache._executor.submit(self._update_market_cache_async, symbol)

            logger.info(f"✅ 주문 생성 완료: {order.id} ({order.status})")
            return order

        except OrderParsingError:
            raise  # 재시도 하지 않음
        except Exception as e:
            logger.error(f"주문 생성 실패: {e}")
            
            # 에러 타입별 처리
            if hasattr(e, 'code'):
                if e.code == -2010:  # NEW_ORDER_REJECTED
                    raise InvalidOrder(f"주문 거부: {e}")
                elif e.code == -2019:  # INSUFFICIENT_BALANCE  
                    raise InsufficientFunds(f"잔액 부족: {e}")
            
            raise ExchangeError(f"주문 생성 실패: {e}")
    
    async def cancel_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        """주문 취소"""
        params = {
            'symbol': symbol,
            'orderId': order_id
        }
        
        try:
            logger.info(f"🗑️ 주문 취소: {order_id}")
            
            response = self._make_request('DELETE', SpotEndpoints.ORDER, params, signed=True, weight=Weights.SPOT_CANCEL_ORDER)
            
            logger.info(f"✅ 주문 취소 완료: {order_id}")
            return response
            
        except Exception as e:
            logger.error(f"주문 취소 실패: {e}")
            raise ExchangeError(f"주문 취소 실패: {e}")
    
    async def fetch_order(self, order_id: str, symbol: str, params: Optional[Dict] = None) -> Order:
        """주문 상태 조회"""
        request_params = {
            'symbol': symbol,
            'orderId': order_id
        }
        
        try:
            response = self._make_request('GET', SpotEndpoints.ORDER, request_params, signed=True, weight=Weights.SPOT_ORDER)
            order = Order.from_binance(response)
            
            logger.debug(f"📋 주문 조회: {order_id} ({order.status})")
            return order
            
        except Exception as e:
            logger.error(f"주문 조회 실패: {e}")
            raise ExchangeError(f"주문 조회 실패: {e}")
    
    async def fetch_open_orders(self, symbol: Optional[str] = None, params: Optional[Dict] = None) -> List[Order]:
        """미체결 주문 조회"""
        request_params = {}
        if symbol:
            request_params['symbol'] = symbol
        
        try:
            response = self._make_request('GET', SpotEndpoints.OPEN_ORDERS, request_params, signed=True, weight=Weights.SPOT_OPEN_ORDERS)
            
            orders = []
            for item in response:
                order = Order.from_binance(item)
                orders.append(order)
            
            logger.debug(f"📊 미체결 주문: {len(orders)}개")
            return orders
            
        except Exception as e:
            logger.error(f"미체결 주문 조회 실패: {e}")
            raise ExchangeError(f"미체결 주문 조회 실패: {e}")
    
    async def fetch_my_trades(self, symbol: str, since: int = None, limit: int = 500, params: Dict = None) -> List[Dict[str, Any]]:
        """거래 내역 조회"""
        request_params = {'symbol': symbol}
        
        if since:
            request_params['startTime'] = since
        if limit:
            request_params['limit'] = min(limit, 1000)  # 최대 1000개로 제한
        
        if params:
            request_params.update(params)
        
        try:
            response = self._make_request('GET', '/api/v3/myTrades', request_params, signed=True, weight=10)
            
            logger.debug(f"💼 거래 내역 조회: {symbol} ({len(response)}개)")
            return response
            
        except Exception as e:
            logger.error(f"거래 내역 조회 실패: {e}")
            raise ExchangeError(f"거래 내역 조회 실패: {e}")
    
    def _update_market_cache_async(self, symbol: str):
        """특정 심볼의 마켓 캐시 비동기 업데이트"""
        try:
            # 전체 마켓 정보 중 해당 심볼만 업데이트
            response = self._make_request('GET', SpotEndpoints.EXCHANGE_INFO, weight=Weights.SPOT_EXCHANGE_INFO)
            
            for data in response.get('symbols', []):
                if data['symbol'] == symbol:
                    market_info = MarketInfo.from_binance_spot(data)
                    self.cache.set_market(symbol, market_info)
                    logger.debug(f"🔄 마켓 캐시 업데이트: {symbol}")
                    break
                    
        except Exception as e:
            logger.error(f"마켓 캐시 업데이트 실패 {symbol}: {e}")
    
    def create_market_order(self, symbol: str, side: str, amount: float, params: Dict = None) -> Order:
        """시장가 주문 (동기 래퍼)"""
        return asyncio.run(self.create_order(symbol, OrderType.MARKET, side, amount, params=params))
    
    def create_limit_order(self, symbol: str, side: str, amount: float, price: float, params: Dict = None) -> Order:
        """지정가 주문 (동기 래퍼)"""
        return asyncio.run(self.create_order(symbol, OrderType.LIMIT, side, amount, price, params))
    
    # CCXT 호환 메서드들 (동기)
    def fetch_balance_sync(self) -> Dict[str, Balance]:
        """잔액 조회 (동기)"""
        return asyncio.run(self.fetch_balance())
    
    def fetch_ticker_sync(self, symbol: str) -> Ticker:
        """시세 조회 (동기)"""
        return asyncio.run(self.fetch_ticker(symbol))
    
    def fetch_open_orders_sync(self, symbol: str = None) -> List[Order]:
        """미체결 주문 조회 (동기)"""
        return asyncio.run(self.fetch_open_orders(symbol))
    
    def load_markets_sync(self, reload: bool = False) -> Dict[str, MarketInfo]:
        """마켓 정보 로드 (동기)"""
        return asyncio.run(self.load_markets(reload))
    
    # CCXT 호환성을 위한 별명
    async def fetch_markets(self, reload: bool = False) -> Dict[str, MarketInfo]:
        """마켓 정보 조회 (load_markets 별명)"""
        return await self.load_markets(reload)
    
    def fetch_markets_sync(self, reload: bool = False) -> Dict[str, MarketInfo]:
        """마켓 정보 조회 (동기)"""
        return asyncio.run(self.fetch_markets(reload))