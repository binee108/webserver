"""
Binance Futures API 직접 구현

선물 거래를 위한 고성능 API 구현으로 포지션 관리와 레버리지 거래를 지원합니다.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any
from decimal import Decimal

from ..base import BaseExchange, ExchangeError, InvalidOrder, InsufficientFunds
from app.services.exchange_service import OrderParsingError
from ..models import MarketInfo, Balance, Order, Ticker, Position
from .constants import (
    FUTURES_BASE_URL, FUTURES_TESTNET_URL, FUTURES_RATE_LIMIT, FUTURES_WEIGHT_LIMIT,
    FuturesEndpoints, OrderType, OrderSide, OrderStatus, TimeInForce, Weights
)

logger = logging.getLogger(__name__)


class BinanceFutures(BaseExchange):
    """
    Binance Futures API 구현
    
    특징:
    - 포지션 기반 거래 지원
    - 레버리지 관리
    - 마진 및 자금 조달료 처리
    - 고성능 캐싱 시스템
    """
    
    def __init__(self, api_key: str, secret: str, testnet: bool = False):
        super().__init__(api_key, secret, testnet)
        
        # 선물 거래 특화 설정
        self._positions_cache = {}
        self._margin_cache = {}
        self._leverage_cache = {}
        
        # 마켓 초기화 상태
        self._markets_loaded = False
        self._loading_markets = False
        
        logger.info(f"🚀 Binance Futures API 초기화 완료 (testnet={testnet})")
    
    @property
    def base_url(self) -> str:
        # 테스트넷의 경우 /fapi 경로 포함하여 전체 URL 구성
        if self.testnet:
            return FUTURES_TESTNET_URL
        return FUTURES_BASE_URL
    
    @property  
    def market_type(self) -> str:
        return "FUTURES"
    
    def get_rate_limit(self) -> int:
        return FUTURES_RATE_LIMIT
    
    def get_weight_limit(self) -> int:
        return FUTURES_WEIGHT_LIMIT
    
    async def load_markets(self, reload: bool = False) -> Dict[str, MarketInfo]:
        """선물 마켓 정보 로드 및 캐싱"""
        if self._markets_loaded and not reload:
            # 캐시에서 즉시 반환 (무지연)
            cached_markets = {}
            for symbol in self.cache.markets.keys():
                market_info = self.cache.get_market(symbol)
                if market_info:
                    cached_markets[symbol] = market_info
            
            if cached_markets:
                logger.debug(f"📈 선물 마켓 캐시 히트: {len(cached_markets)}개")
                return cached_markets
        
        # 중복 로딩 방지
        if self._loading_markets:
            await asyncio.sleep(0.1)
            return await self.load_markets(reload=False)
        
        self._loading_markets = True
        
        try:
            logger.info("🔄 Binance Futures 마켓 정보 로딩 시작")
            
            # API 호출
            response = self._make_request('GET', FuturesEndpoints.EXCHANGE_INFO, weight=Weights.FUTURES_EXCHANGE_INFO)
            symbols_data = response.get('symbols', [])
            
            # 캐시 업데이트
            updated_count = self.cache.update_markets_batch(symbols_data, "FUTURES")
            
            # 결과 구성
            markets = {}
            for data in symbols_data:
                if data['status'] == 'TRADING':
                    market_info = MarketInfo.from_binance_futures(data)
                    markets[data['symbol']] = market_info
            
            self._markets_loaded = True
            self.stats['last_update'] = self._get_timestamp()
            
            logger.info(f"✅ Binance Futures 마켓 정보 로딩 완료: {updated_count}개 심볼")
            
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
            logger.error(f"선물 마켓 정보 로딩 실패: {e}")
            raise ExchangeError(f"선물 마켓 정보 로딩 실패: {e}")
        finally:
            self._loading_markets = False
    
    async def fetch_balance(self) -> Dict[str, Balance]:
        """선물 계정 잔액 조회"""
        try:
            response = self._make_request('GET', FuturesEndpoints.ACCOUNT, signed=True, weight=Weights.FUTURES_ACCOUNT)
            
            balances = {}
            for item in response.get('assets', []):
                asset = item['asset']
                wallet_balance = Decimal(item['walletBalance'])
                unrealized_pnl = Decimal(item['unrealizedProfit'])
                margin_balance = Decimal(item['marginBalance'])
                
                if wallet_balance > 0 or margin_balance > 0:
                    balances[asset] = Balance(
                        asset=asset,
                        free=margin_balance,  # 사용 가능한 마진
                        locked=Decimal('0'),  # 선물에서는 locked 개념이 다름
                        total=wallet_balance
                    )
            
            logger.debug(f"💰 선물 잔액 조회 완료: {len(balances)}개 자산")
            return balances
            
        except Exception as e:
            logger.error(f"선물 잔액 조회 실패: {e}")
            raise ExchangeError(f"선물 잔액 조회 실패: {e}")
    
    async def fetch_positions(self) -> List[Position]:
        """포지션 조회"""
        try:
            response = self._make_request('GET', FuturesEndpoints.POSITION_RISK, signed=True, weight=2)
            
            positions = []
            for item in response:
                position_size = Decimal(item['positionAmt'])
                
                # 0이 아닌 포지션만 반환
                if position_size != 0:
                    position = Position(
                        symbol=item['symbol'],
                        size=abs(position_size),
                        side='LONG' if position_size > 0 else 'SHORT',
                        unrealized_pnl=Decimal(item['unRealizedProfit']),
                        entry_price=Decimal(item['entryPrice']),
                        mark_price=Decimal(item['markPrice']),
                        margin=Decimal(item['isolatedMargin']) if item.get('isolatedMargin') else Decimal('0')
                    )
                    positions.append(position)
            
            logger.debug(f"📊 포지션 조회: {len(positions)}개")
            return positions
            
        except Exception as e:
            logger.error(f"포지션 조회 실패: {e}")
            raise ExchangeError(f"포지션 조회 실패: {e}")
    
    async def fetch_ticker(self, symbol: str, params: Optional[Dict] = None) -> Ticker:
        """선물 시세 조회"""
        # 캐시에서 먼저 조회
        cached_ticker = self.cache.get_ticker(symbol)
        if cached_ticker:
            self.stats['cache_hits'] += 1
            return cached_ticker
        
        try:
            params = {'symbol': symbol}
            response = self._make_request('GET', FuturesEndpoints.TICKER_24HR, params, weight=Weights.FUTURES_TICKER_24HR)
            
            ticker = Ticker.from_binance(response)
            
            # 캐시 업데이트
            self.cache.set_ticker(symbol, ticker)
            
            logger.debug(f"📊 선물 시세 조회: {symbol} = ${ticker.last}")
            return ticker
            
        except Exception as e:
            logger.error(f"선물 시세 조회 실패 {symbol}: {e}")
            raise ExchangeError(f"선물 시세 조회 실패: {e}")
    
    async def create_order(self, symbol: str, type: str, side: str, amount: float, price: float = None, params: Dict = None) -> Order:
        """선물 주문 생성"""
        params = params or {}
        
        # 캐시된 마켓 정보로 즉시 검증 (무지연)
        if not self.get_market_info(symbol):
            logger.warning(f"선물 마켓 정보 없음, API에서 로드: {symbol}")
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
        
        # 선물 특화 파라미터
        if 'stopPrice' in params:
            order_params['stopPrice'] = str(self.round_price(symbol, float(params['stopPrice'])))
        
        if 'reduceOnly' in params:
            order_params['reduceOnly'] = str(params['reduceOnly']).lower()
        
        if 'closePosition' in params:
            order_params['closePosition'] = str(params['closePosition']).lower()
        
        # 추가 파라미터
        for key, value in params.items():
            if key not in ['timeInForce', 'stopPrice', 'reduceOnly', 'closePosition']:
                order_params[key] = value
        
        try:
            logger.info(f"📤 선물 주문 생성: {side} {rounded_amount} {symbol} @ {rounded_price or 'MARKET'}")

            response = self._make_request('POST', FuturesEndpoints.ORDER, order_params, signed=True, weight=Weights.FUTURES_ORDER)

            try:
                order = Order.from_binance(response)
            except Exception as parse_error:
                # 주문은 생성됐지만 파싱 실패
                logger.error(f"주문 응답 파싱 실패: {parse_error}, 원본 응답: {response}")
                raise OrderParsingError(f"주문 ID {response.get('orderId', 'unknown')} 파싱 실패") from parse_error

            # 백그라운드에서 마켓 캐시 업데이트 (비동기)
            self.cache._executor.submit(self._update_market_cache_async, symbol)

            logger.info(f"✅ 선물 주문 생성 완료: {order.id} ({order.status})")
            return order

        except OrderParsingError:
            raise  # 재시도 하지 않음
        except Exception as e:
            logger.error(f"선물 주문 생성 실패: {e}")
            
            # 에러 타입별 처리
            if hasattr(e, 'code'):
                if e.code == -2010:  # NEW_ORDER_REJECTED
                    raise InvalidOrder(f"주문 거부: {e}")
                elif e.code == -2019:  # INSUFFICIENT_BALANCE  
                    raise InsufficientFunds(f"마진 부족: {e}")
            
            raise ExchangeError(f"선물 주문 생성 실패: {e}")
    
    async def cancel_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        """선물 주문 취소"""
        params = {
            'symbol': symbol,
            'orderId': order_id
        }
        
        try:
            logger.info(f"🗑️ 선물 주문 취소: {order_id}")
            
            response = self._make_request('DELETE', FuturesEndpoints.ORDER, params, signed=True, weight=Weights.FUTURES_CANCEL_ORDER)
            
            logger.info(f"✅ 선물 주문 취소 완료: {order_id}")
            return response
            
        except Exception as e:
            logger.error(f"선물 주문 취소 실패: {e}")
            raise ExchangeError(f"선물 주문 취소 실패: {e}")
    
    async def fetch_order(self, order_id: str, symbol: str, params: Optional[Dict] = None) -> Order:
        """선물 주문 상태 조회"""
        request_params = {
            'symbol': symbol,
            'orderId': order_id
        }
        
        try:
            response = self._make_request('GET', FuturesEndpoints.ORDER, request_params, signed=True, weight=Weights.FUTURES_ORDER)
            order = Order.from_binance(response)
            
            logger.debug(f"📋 선물 주문 조회: {order_id} ({order.status})")
            return order
            
        except Exception as e:
            logger.error(f"선물 주문 조회 실패: {e}")
            raise ExchangeError(f"선물 주문 조회 실패: {e}")
    
    async def fetch_open_orders(self, symbol: Optional[str] = None, params: Optional[Dict] = None) -> List[Order]:
        """선물 미체결 주문 조회"""
        request_params = {}
        if symbol:
            request_params['symbol'] = symbol
        
        try:
            response = self._make_request('GET', FuturesEndpoints.OPEN_ORDERS, request_params, signed=True, weight=Weights.FUTURES_OPEN_ORDERS)
            
            orders = []
            for item in response:
                order = Order.from_binance(item)
                orders.append(order)
            
            logger.debug(f"📊 선물 미체결 주문: {len(orders)}개")
            return orders
            
        except Exception as e:
            logger.error(f"선물 미체결 주문 조회 실패: {e}")
            raise ExchangeError(f"선물 미체결 주문 조회 실패: {e}")
    
    async def set_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        """레버리지 설정"""
        params = {
            'symbol': symbol,
            'leverage': leverage
        }
        
        try:
            logger.info(f"⚖️ 레버리지 설정: {symbol} = {leverage}x")
            
            response = self._make_request('POST', '/fapi/v1/leverage', params, signed=True, weight=1)
            
            # 캐시 업데이트
            self._leverage_cache[symbol] = leverage
            
            logger.info(f"✅ 레버리지 설정 완료: {symbol} = {leverage}x")
            return response
            
        except Exception as e:
            logger.error(f"레버리지 설정 실패: {e}")
            raise ExchangeError(f"레버리지 설정 실패: {e}")
    
    async def set_margin_type(self, symbol: str, margin_type: str) -> Dict[str, Any]:
        """마진 타입 설정 (ISOLATED/CROSSED)"""
        params = {
            'symbol': symbol,
            'marginType': margin_type.upper()
        }
        
        try:
            logger.info(f"💰 마진 타입 설정: {symbol} = {margin_type}")
            
            response = self._make_request('POST', '/fapi/v1/marginType', params, signed=True, weight=1)
            
            logger.info(f"✅ 마진 타입 설정 완료: {symbol} = {margin_type}")
            return response
            
        except Exception as e:
            # 이미 설정된 경우 에러가 발생할 수 있으므로 로그만 남김
            if hasattr(e, 'code') and e.code == -4046:
                logger.debug(f"마진 타입 이미 설정됨: {symbol} = {margin_type}")
                return {'msg': 'Already set'}
            else:
                logger.error(f"마진 타입 설정 실패: {e}")
                raise ExchangeError(f"마진 타입 설정 실패: {e}")
    
    def _update_market_cache_async(self, symbol: str):
        """특정 심볼의 선물 마켓 캐시 비동기 업데이트"""
        try:
            response = self._make_request('GET', FuturesEndpoints.EXCHANGE_INFO, weight=Weights.FUTURES_EXCHANGE_INFO)
            
            for data in response.get('symbols', []):
                if data['symbol'] == symbol:
                    market_info = MarketInfo.from_binance_futures(data)
                    self.cache.set_market(symbol, market_info)
                    logger.debug(f"🔄 선물 마켓 캐시 업데이트: {symbol}")
                    break
                    
        except Exception as e:
            logger.error(f"선물 마켓 캐시 업데이트 실패 {symbol}: {e}")
    
    # CCXT 호환 메서드들 (동기)
    def create_market_order(self, symbol: str, side: str, amount: float, params: Dict = None) -> Order:
        """선물 시장가 주문 (동기 래퍼)"""
        return asyncio.run(self.create_order(symbol, OrderType.MARKET, side, amount, params=params))
    
    def create_limit_order(self, symbol: str, side: str, amount: float, price: float, params: Dict = None) -> Order:
        """선물 지정가 주문 (동기 래퍼)"""
        return asyncio.run(self.create_order(symbol, OrderType.LIMIT, side, amount, price, params))
    
    def fetch_balance_sync(self) -> Dict[str, Balance]:
        """선물 잔액 조회 (동기)"""
        return asyncio.run(self.fetch_balance())
    
    def fetch_positions_sync(self) -> List[Position]:
        """포지션 조회 (동기)"""
        return asyncio.run(self.fetch_positions())
    
    def fetch_ticker_sync(self, symbol: str) -> Ticker:
        """선물 시세 조회 (동기)"""
        return asyncio.run(self.fetch_ticker(symbol))
    
    def fetch_open_orders_sync(self, symbol: str = None) -> List[Order]:
        """선물 미체결 주문 조회 (동기)"""
        return asyncio.run(self.fetch_open_orders(symbol))
    
    def load_markets_sync(self, reload: bool = False) -> Dict[str, MarketInfo]:
        """선물 마켓 정보 로드 (동기)"""
        return asyncio.run(self.load_markets(reload))
    
    # CCXT 호환성을 위한 별명
    async def fetch_markets(self, reload: bool = False) -> Dict[str, MarketInfo]:
        """선물 마켓 정보 조회 (load_markets 별명)"""
        return await self.load_markets(reload)
    
    def fetch_markets_sync(self, reload: bool = False) -> Dict[str, MarketInfo]:
        """선물 마켓 정보 조회 (동기)"""
        return asyncio.run(self.fetch_markets(reload))
    
    def set_leverage_sync(self, symbol: str, leverage: int) -> Dict[str, Any]:
        """레버리지 설정 (동기)"""
        return asyncio.run(self.set_leverage(symbol, leverage))
    
    def set_margin_type_sync(self, symbol: str, margin_type: str) -> Dict[str, Any]:
        """마진 타입 설정 (동기)"""
        return asyncio.run(self.set_margin_type(symbol, margin_type))