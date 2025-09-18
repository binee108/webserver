#!/usr/bin/env python3
"""
Exchange Service Layer

비즈니스 로직과 거래소 구현체를 분리하는 서비스 계층
- TradingService: 주문 처리 비즈니스 로직
- MarketDataService: 시장 데이터 관리
- AccountService: 계정 정보 관리
- Dependency Injection 지원
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List, Union
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime, timedelta
import time

from .registry import exchange_registry, ExchangeMetadata
from .config import config_manager, get_config
from .models import MarketInfo, TickerInfo, BalanceInfo, OrderInfo, PositionInfo

logger = logging.getLogger(__name__)

@dataclass
class ServiceContext:
    """서비스 실행 컨텍스트"""
    user_id: Optional[str] = None
    exchange_name: str = "binance"
    market_type: str = "spot"
    testnet: bool = False
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None

class ExchangeServiceError(Exception):
    """서비스 계층 오류"""
    pass

class BaseService(ABC):
    """서비스 기본 클래스"""
    
    def __init__(self, context: ServiceContext):
        self.context = context
        self.config = get_config()
        self._exchange_instance = None
        self._exchange_metadata = None
    
    async def _get_exchange_instance(self):
        """거래소 인스턴스 조회 (지연 로딩)"""
        if self._exchange_instance is None:
            # 최적 거래소 구현체 선택
            metadata = exchange_registry.find_best_exchange(
                market_type=self.context.market_type,
                exchange_name=self.context.exchange_name,
                prefer_custom=config_manager.should_use_custom_exchange(self.context.exchange_name)
            )
            
            if not metadata:
                raise ExchangeServiceError(
                    f"사용 가능한 거래소 구현체 없음: {self.context.exchange_name} ({self.context.market_type})"
                )
            
            self._exchange_metadata = metadata
            
            # 인스턴스 생성
            self._exchange_instance = exchange_registry.create_instance(
                name=metadata.name,
                api_key=self.context.api_key,
                api_secret=self.context.api_secret,
                testnet=self.context.testnet or config_manager.is_testnet_enabled(self.context.exchange_name)
            )
            
            logger.info(f"📡 거래소 인스턴스 로드: {metadata.display_name}")
        
        return self._exchange_instance
    
    def get_exchange_metadata(self) -> Optional[ExchangeMetadata]:
        """현재 사용중인 거래소 메타데이터"""
        return self._exchange_metadata

class MarketDataService(BaseService):
    """시장 데이터 서비스"""
    
    def __init__(self, context: ServiceContext):
        super().__init__(context)
        self._markets_cache = {}
        self._tickers_cache = {}
        self._cache_ttl = self.config.performance.cache_ttl_seconds
    
    async def get_markets(self, reload: bool = False) -> Dict[str, MarketInfo]:
        """시장 정보 조회"""
        cache_key = f"{self.context.exchange_name}_{self.context.market_type}"
        
        # 캐시 확인
        if not reload and cache_key in self._markets_cache:
            cached_data, timestamp = self._markets_cache[cache_key]
            if time.time() - timestamp < self._cache_ttl:
                logger.debug(f"📈 Markets 캐시 히트: {cache_key}")
                return cached_data
        
        # 거래소에서 조회
        exchange = await self._get_exchange_instance()
        
        try:
            markets_data = await exchange.load_markets()
            
            # MarketInfo 객체로 변환
            markets = {}
            for symbol, market in markets_data.items():
                markets[symbol] = MarketInfo(
                    symbol=symbol,
                    base_asset=market.get('base', ''),
                    quote_asset=market.get('quote', ''),
                    min_qty=Decimal(str(market.get('limits', {}).get('amount', {}).get('min', 0))),
                    max_qty=Decimal(str(market.get('limits', {}).get('amount', {}).get('max', 0))),
                    min_price=Decimal(str(market.get('limits', {}).get('price', {}).get('min', 0))),
                    max_price=Decimal(str(market.get('limits', {}).get('price', {}).get('max', 0))),
                    min_notional=Decimal(str(market.get('limits', {}).get('cost', {}).get('min', 0))),
                    price_precision=market.get('precision', {}).get('price', 8),
                    qty_precision=market.get('precision', {}).get('amount', 8),
                    is_active=market.get('active', True),
                    market_type=market.get('type', self.context.market_type),
                    raw_data=market
                )
            
            # 캐시 저장
            self._markets_cache[cache_key] = (markets, time.time())
            
            logger.info(f"📊 Markets 조회 완료: {len(markets)}개 ({self._exchange_metadata.display_name})")
            return markets
            
        except Exception as e:
            logger.error(f"❌ Markets 조회 실패: {e}")
            raise ExchangeServiceError(f"Markets 조회 실패: {e}")
    
    async def get_ticker(self, symbol: str, use_cache: bool = True) -> TickerInfo:
        """티커 정보 조회"""
        cache_key = f"{self.context.exchange_name}_{symbol}"
        
        # 캐시 확인 (티커는 짧은 TTL 사용)
        ticker_ttl = min(self._cache_ttl, 60)  # 최대 1분
        if use_cache and cache_key in self._tickers_cache:
            cached_ticker, timestamp = self._tickers_cache[cache_key]
            if time.time() - timestamp < ticker_ttl:
                logger.debug(f"🎯 Ticker 캐시 히트: {symbol}")
                return cached_ticker
        
        # 거래소에서 조회
        exchange = await self._get_exchange_instance()
        
        try:
            ticker_data = await exchange.fetch_ticker(symbol)
            
            # TickerInfo 객체로 변환
            ticker = TickerInfo(
                symbol=ticker_data.get('symbol', symbol),
                bid_price=Decimal(str(ticker_data.get('bid', 0))),
                ask_price=Decimal(str(ticker_data.get('ask', 0))),
                last_price=Decimal(str(ticker_data.get('last', 0))),
                high_price=Decimal(str(ticker_data.get('high', 0))),
                low_price=Decimal(str(ticker_data.get('low', 0))),
                volume=Decimal(str(ticker_data.get('baseVolume', 0))),
                quote_volume=Decimal(str(ticker_data.get('quoteVolume', 0))),
                open_price=Decimal(str(ticker_data.get('open', 0))),
                close_price=Decimal(str(ticker_data.get('close', 0))),
                change_24h=Decimal(str(ticker_data.get('change', 0))),
                change_percent_24h=Decimal(str(ticker_data.get('percentage', 0))),
                timestamp=datetime.fromtimestamp(ticker_data.get('timestamp', 0) / 1000) if ticker_data.get('timestamp') else datetime.now(),
                raw_data=ticker_data
            )
            
            # 캐시 저장
            if use_cache:
                self._tickers_cache[cache_key] = (ticker, time.time())
            
            logger.debug(f"🎯 Ticker 조회: {symbol} = {ticker.last_price}")
            return ticker
            
        except Exception as e:
            logger.error(f"❌ Ticker 조회 실패 ({symbol}): {e}")
            raise ExchangeServiceError(f"Ticker 조회 실패 ({symbol}): {e}")
    
    async def get_multiple_tickers(self, symbols: List[str], use_cache: bool = True) -> Dict[str, TickerInfo]:
        """다중 티커 조회 (병렬 처리)"""
        if not symbols:
            return {}
        
        # 병렬 요청 활성화 여부 확인
        if self.config.features.enable_parallel_requests and len(symbols) > 3:
            # 병렬 처리
            tasks = [self.get_ticker(symbol, use_cache) for symbol in symbols]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            tickers = {}
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"❌ Ticker 조회 실패 ({symbols[i]}): {result}")
                else:
                    tickers[symbols[i]] = result
            
            return tickers
        else:
            # 순차 처리
            tickers = {}
            for symbol in symbols:
                try:
                    ticker = await self.get_ticker(symbol, use_cache)
                    tickers[symbol] = ticker
                except Exception as e:
                    logger.error(f"❌ Ticker 조회 실패 ({symbol}): {e}")
            
            return tickers
    
    def clear_cache(self, symbol: Optional[str] = None):
        """캐시 정리"""
        if symbol:
            cache_key = f"{self.context.exchange_name}_{symbol}"
            self._tickers_cache.pop(cache_key, None)
        else:
            self._markets_cache.clear()
            self._tickers_cache.clear()
        
        logger.info(f"🧹 MarketData 캐시 정리: {symbol or 'all'}")

class AccountService(BaseService):
    """계정 관리 서비스"""
    
    async def get_balance(self, currency: Optional[str] = None) -> Union[BalanceInfo, Dict[str, BalanceInfo]]:
        """잔액 조회"""
        exchange = await self._get_exchange_instance()
        
        try:
            balance_data = await exchange.fetch_balance()
            
            if currency:
                # 특정 통화 잔액
                if currency in balance_data and currency != 'info':
                    currency_balance = balance_data[currency]
                    return BalanceInfo(
                        asset=currency,
                        free=Decimal(str(currency_balance.get('free', 0))),
                        locked=Decimal(str(currency_balance.get('used', 0))),
                        total=Decimal(str(currency_balance.get('total', 0))),
                        raw_data=currency_balance
                    )
                else:
                    raise ExchangeServiceError(f"통화 {currency} 잔액 정보 없음")
            else:
                # 전체 잔액
                balances = {}
                for asset, balance in balance_data.items():
                    if asset == 'info' or not isinstance(balance, dict):
                        continue
                    
                    if balance.get('total', 0) > 0:  # 잔액이 있는 것만
                        balances[asset] = BalanceInfo(
                            asset=asset,
                            free=Decimal(str(balance.get('free', 0))),
                            locked=Decimal(str(balance.get('used', 0))),
                            total=Decimal(str(balance.get('total', 0))),
                            raw_data=balance
                        )
                
                logger.info(f"💰 잔액 조회 완료: {len(balances)}개 자산")
                return balances
            
        except Exception as e:
            logger.error(f"❌ 잔액 조회 실패: {e}")
            raise ExchangeServiceError(f"잔액 조회 실패: {e}")
    
    async def get_positions(self, symbol: Optional[str] = None) -> Union[PositionInfo, List[PositionInfo]]:
        """포지션 조회 (Futures)"""
        if self.context.market_type != "futures":
            raise ExchangeServiceError("포지션 조회는 Futures 마켓에서만 가능")
        
        exchange = await self._get_exchange_instance()
        
        try:
            positions_data = await exchange.fetch_positions(symbols=[symbol] if symbol else None)
            
            positions = []
            for pos_data in positions_data:
                if pos_data.get('contracts', 0) != 0:  # 포지션이 있는 것만
                    position = PositionInfo(
                        symbol=pos_data.get('symbol', ''),
                        position_side=pos_data.get('side', '').upper(),
                        position_amount=Decimal(str(pos_data.get('contracts', 0))),
                        entry_price=Decimal(str(pos_data.get('entryPrice', 0))),
                        mark_price=Decimal(str(pos_data.get('markPrice', 0))),
                        unrealized_pnl=Decimal(str(pos_data.get('unrealizedPnl', 0))),
                        leverage=pos_data.get('leverage', 1),
                        margin_type=pos_data.get('marginMode', 'cross').lower(),
                        timestamp=datetime.fromtimestamp(pos_data.get('timestamp', 0) / 1000) if pos_data.get('timestamp') else datetime.now(),
                        raw_data=pos_data
                    )
                    positions.append(position)
            
            if symbol:
                # 특정 심볼 포지션
                symbol_positions = [p for p in positions if p.symbol == symbol]
                if symbol_positions:
                    return symbol_positions[0]
                else:
                    raise ExchangeServiceError(f"심볼 {symbol}의 포지션 없음")
            else:
                # 전체 포지션
                logger.info(f"🎯 포지션 조회 완료: {len(positions)}개")
                return positions
            
        except Exception as e:
            logger.error(f"❌ 포지션 조회 실패: {e}")
            raise ExchangeServiceError(f"포지션 조회 실패: {e}")

class TradingService(BaseService):
    """거래 서비스"""
    
    def __init__(self, context: ServiceContext):
        super().__init__(context)
        self.market_data_service = MarketDataService(context)
        self.account_service = AccountService(context)
    
    async def create_order(
        self,
        symbol: str,
        side: str,  # 'buy' or 'sell'
        order_type: str,  # 'market', 'limit', 'stop_market', 'stop_limit'
        amount: Union[Decimal, float],
        price: Optional[Union[Decimal, float]] = None,
        stop_price: Optional[Union[Decimal, float]] = None,
        time_in_force: str = "GTC",
        params: Optional[Dict[str, Any]] = None
    ) -> OrderInfo:
        """주문 생성"""
        exchange = await self._get_exchange_instance()
        
        try:
            # 주문 파라미터 준비
            order_params = params or {}
            if stop_price:
                order_params['stopPrice'] = float(stop_price)
            if time_in_force != "GTC":
                order_params['timeInForce'] = time_in_force
            
            # 주문 실행
            order_data = await exchange.create_order(
                symbol=symbol,
                type=order_type.lower(),
                side=side.lower(),
                amount=float(amount),
                price=float(price) if price else None,
                params=order_params
            )
            
            # OrderInfo 객체로 변환
            order = OrderInfo(
                order_id=order_data.get('id', ''),
                client_order_id=order_data.get('clientOrderId', ''),
                symbol=order_data.get('symbol', symbol),
                side=side.upper(),
                order_type=order_type.upper(),
                quantity=Decimal(str(order_data.get('amount', amount))),
                price=Decimal(str(price)) if price else None,
                stop_price=Decimal(str(stop_price)) if stop_price else None,
                status=self._map_order_status(order_data.get('status', 'NEW')),
                time_in_force=time_in_force,
                timestamp=datetime.fromtimestamp(order_data.get('timestamp', 0) / 1000) if order_data.get('timestamp') else datetime.now(),
                filled_quantity=Decimal(str(order_data.get('filled', 0))),
                remaining_quantity=Decimal(str(order_data.get('remaining', amount))),
                avg_price=Decimal(str(order_data.get('average', 0))) if order_data.get('average') else None,
                commission=Decimal(str(order_data.get('fee', {}).get('cost', 0))) if order_data.get('fee') else None,
                raw_data=order_data
            )
            
            logger.info(f"📋 주문 생성: {symbol} {side} {amount} @ {price} (ID: {order.order_id})")
            return order
            
        except Exception as e:
            logger.error(f"❌ 주문 생성 실패: {e}")
            raise ExchangeServiceError(f"주문 생성 실패: {e}")
    
    async def cancel_order(self, order_id: str, symbol: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """주문 취소"""
        exchange = await self._get_exchange_instance()
        
        try:
            cancel_result = await exchange.cancel_order(order_id, symbol, params or {})
            logger.info(f"🚫 주문 취소: {symbol} (ID: {order_id})")
            return cancel_result
            
        except Exception as e:
            logger.error(f"❌ 주문 취소 실패 ({order_id}): {e}")
            raise ExchangeServiceError(f"주문 취소 실패: {e}")
    
    async def get_order(self, order_id: str, symbol: str, params: Optional[Dict[str, Any]] = None) -> OrderInfo:
        """주문 조회"""
        exchange = await self._get_exchange_instance()
        
        try:
            order_data = await exchange.fetch_order(order_id, symbol, params or {})
            
            # OrderInfo 객체로 변환
            order = OrderInfo(
                order_id=order_data.get('id', order_id),
                client_order_id=order_data.get('clientOrderId', ''),
                symbol=order_data.get('symbol', symbol),
                side=order_data.get('side', '').upper(),
                order_type=order_data.get('type', '').upper(),
                quantity=Decimal(str(order_data.get('amount', 0))),
                price=Decimal(str(order_data.get('price', 0))) if order_data.get('price') else None,
                status=self._map_order_status(order_data.get('status', 'UNKNOWN')),
                timestamp=datetime.fromtimestamp(order_data.get('timestamp', 0) / 1000) if order_data.get('timestamp') else datetime.now(),
                filled_quantity=Decimal(str(order_data.get('filled', 0))),
                remaining_quantity=Decimal(str(order_data.get('remaining', 0))),
                avg_price=Decimal(str(order_data.get('average', 0))) if order_data.get('average') else None,
                commission=Decimal(str(order_data.get('fee', {}).get('cost', 0))) if order_data.get('fee') else None,
                raw_data=order_data
            )
            
            return order
            
        except Exception as e:
            logger.error(f"❌ 주문 조회 실패 ({order_id}): {e}")
            raise ExchangeServiceError(f"주문 조회 실패: {e}")
    
    def _map_order_status(self, exchange_status: str) -> str:
        """거래소 주문 상태를 표준 상태로 매핑"""
        status_mapping = {
            'NEW': 'PENDING',
            'PARTIALLY_FILLED': 'PARTIALLY_FILLED',
            'FILLED': 'FILLED',
            'CANCELED': 'CANCELED',
            'PENDING_CANCEL': 'PENDING_CANCEL',
            'REJECTED': 'REJECTED',
            'EXPIRED': 'EXPIRED',
            # CCXT 표준
            'open': 'PENDING',
            'closed': 'FILLED',
            'canceled': 'CANCELED'
        }
        
        return status_mapping.get(exchange_status.upper(), 'UNKNOWN')

# 서비스 팩토리
class ServiceFactory:
    """서비스 인스턴스 생성 팩토리"""
    
    @staticmethod
    def create_market_data_service(context: ServiceContext) -> MarketDataService:
        """MarketDataService 생성"""
        return MarketDataService(context)
    
    @staticmethod
    def create_account_service(context: ServiceContext) -> AccountService:
        """AccountService 생성"""
        return AccountService(context)
    
    @staticmethod
    def create_trading_service(context: ServiceContext) -> TradingService:
        """TradingService 생성"""
        return TradingService(context)
    
    @staticmethod
    def create_all_services(context: ServiceContext) -> Dict[str, BaseService]:
        """모든 서비스 생성"""
        return {
            'market_data': ServiceFactory.create_market_data_service(context),
            'account': ServiceFactory.create_account_service(context), 
            'trading': ServiceFactory.create_trading_service(context)
        }