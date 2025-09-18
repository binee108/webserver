"""
메모리 기반 마켓 데이터 캐싱 시스템

무지연 주문 처리를 위한 캐싱 전략:
- L1: 마켓 정보 (24시간 TTL)
- L2: 시세 정보 (1분 TTL)  
- L3: 백그라운드 업데이트
"""

import time
import logging
import threading
from typing import Dict, Optional, Any, List
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor

from .models import MarketInfo, Ticker

logger = logging.getLogger(__name__)


@dataclass
class CacheItem:
    """캐시 아이템"""
    data: Any
    timestamp: float
    ttl: int
    
    @property
    def is_expired(self) -> bool:
        return time.time() - self.timestamp > self.ttl
    
    @property
    def age(self) -> float:
        return time.time() - self.timestamp


class MarketDataCache:
    """
    마켓 데이터 캐싱 시스템
    
    3계층 캐싱 구조:
    - L1: 마켓 정보 (무지연 액세스)
    - L2: 시세 정보 (단기 캐시)
    - L3: 백그라운드 업데이트
    """
    
    def __init__(self, exchange_name: str):
        self.exchange_name = exchange_name
        
        # 캐시 저장소
        self.markets: Dict[str, CacheItem] = {}      # 마켓 정보 (24시간)
        self.tickers: Dict[str, CacheItem] = {}      # 시세 정보 (1분)
        self.precision: Dict[str, CacheItem] = {}    # Precision 정보 (24시간)
        
        # TTL 설정
        self.MARKET_TTL = 86400      # 24시간
        self.TICKER_TTL = 60         # 1분
        self.PRECISION_TTL = 86400   # 24시간
        
        # 백그라운드 업데이트
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix=f"{exchange_name}_cache")
        self._update_lock = threading.RLock()
        
        # 통계
        self.stats = {
            'hits': 0,
            'misses': 0,
            'updates': 0,
            'errors': 0
        }
        
        logger.info(f"📦 {exchange_name} 마켓 데이터 캐시 초기화 완료")
    
    def get_market(self, symbol: str) -> Optional[MarketInfo]:
        """마켓 정보 조회 (무지연)"""
        cache_item = self.markets.get(symbol)
        
        if cache_item and not cache_item.is_expired:
            self.stats['hits'] += 1
            logger.debug(f"📈 마켓 캐시 히트: {symbol} (age: {cache_item.age:.1f}s)")
            return cache_item.data
        
        self.stats['misses'] += 1
        logger.debug(f"📉 마켓 캐시 미스: {symbol}")
        return None
    
    def set_market(self, symbol: str, market_info: MarketInfo):
        """마켓 정보 캐싱"""
        with self._update_lock:
            self.markets[symbol] = CacheItem(
                data=market_info,
                timestamp=time.time(),
                ttl=self.MARKET_TTL
            )
            logger.debug(f"💾 마켓 정보 캐싱: {symbol}")
    
    def get_ticker(self, symbol: str) -> Optional[Ticker]:
        """시세 정보 조회"""
        cache_item = self.tickers.get(symbol)
        
        if cache_item and not cache_item.is_expired:
            self.stats['hits'] += 1
            return cache_item.data
        
        self.stats['misses'] += 1
        return None
    
    def set_ticker(self, symbol: str, ticker: Ticker):
        """시세 정보 캐싱"""
        with self._update_lock:
            self.tickers[symbol] = CacheItem(
                data=ticker,
                timestamp=time.time(),
                ttl=self.TICKER_TTL
            )
    
    def get_precision(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Precision 정보 조회 (무지연)"""
        market_info = self.get_market(symbol)
        if market_info:
            return {
                'amount': market_info.amount_precision,
                'price': market_info.price_precision,
                'limits': {
                    'amount': {
                        'min': float(market_info.min_qty),
                        'max': float(market_info.max_qty)
                    },
                    'price': {
                        'min': float(market_info.min_price),
                        'max': float(market_info.max_price)
                    },
                    'cost': {
                        'min': float(market_info.min_notional)
                    }
                },
                'active': market_info.active,
                'type': market_info.market_type.lower()
            }
        return None
    
    def update_markets_batch(self, markets_data: List[Dict[str, Any]], market_type: str = "SPOT"):
        """마켓 정보 배치 업데이트"""
        updated_count = 0
        
        with self._update_lock:
            for data in markets_data:
                try:
                    if market_type == "SPOT":
                        market_info = MarketInfo.from_binance_spot(data)
                    else:
                        market_info = MarketInfo.from_binance_futures(data)
                    
                    self.set_market(market_info.symbol, market_info)
                    updated_count += 1
                    
                except Exception as e:
                    logger.error(f"마켓 정보 파싱 실패 {data.get('symbol', 'unknown')}: {e}")
                    self.stats['errors'] += 1
        
        self.stats['updates'] += updated_count
        logger.info(f"📊 {self.exchange_name} 마켓 정보 배치 업데이트 완료: {updated_count}개")
        
        return updated_count
    
    def update_tickers_batch(self, tickers_data: List[Dict[str, Any]]):
        """시세 정보 배치 업데이트"""
        updated_count = 0
        
        with self._update_lock:
            for data in tickers_data:
                try:
                    ticker = Ticker.from_binance(data)
                    self.set_ticker(ticker.symbol, ticker)
                    updated_count += 1
                    
                except Exception as e:
                    logger.error(f"시세 정보 파싱 실패 {data.get('symbol', 'unknown')}: {e}")
                    self.stats['errors'] += 1
        
        logger.debug(f"📈 시세 정보 배치 업데이트: {updated_count}개")
        return updated_count
    
    def schedule_background_update(self, update_func, interval: int = 300):
        """백그라운드 업데이트 스케줄링"""
        def background_updater():
            while True:
                try:
                    logger.debug(f"🔄 {self.exchange_name} 백그라운드 업데이트 시작")
                    update_func()
                    time.sleep(interval)
                except Exception as e:
                    logger.error(f"백그라운드 업데이트 실패: {e}")
                    time.sleep(60)  # 에러 시 1분 대기
        
        self._executor.submit(background_updater)
        logger.info(f"⏰ 백그라운드 업데이트 스케줄링 완료 (간격: {interval}초)")
    
    def clear_expired(self):
        """만료된 캐시 항목 정리"""
        with self._update_lock:
            expired_markets = [k for k, v in self.markets.items() if v.is_expired]
            expired_tickers = [k for k, v in self.tickers.items() if v.is_expired]
            
            for key in expired_markets:
                del self.markets[key]
            
            for key in expired_tickers:
                del self.tickers[key]
            
            if expired_markets or expired_tickers:
                logger.debug(f"🧹 만료된 캐시 정리: markets={len(expired_markets)}, tickers={len(expired_tickers)}")
    
    def get_stats(self) -> Dict[str, Any]:
        """캐시 통계 반환"""
        return {
            **self.stats,
            'cache_sizes': {
                'markets': len(self.markets),
                'tickers': len(self.tickers),
                'precision': len(self.precision)
            },
            'hit_ratio': self.stats['hits'] / max(1, self.stats['hits'] + self.stats['misses'])
        }
    
    def clear_all(self):
        """모든 캐시 클리어"""
        with self._update_lock:
            self.markets.clear()
            self.tickers.clear()
            self.precision.clear()
            logger.info(f"🗑️ {self.exchange_name} 모든 캐시 클리어")
    
    def __del__(self):
        """소멸자 - 스레드 풀 정리"""
        if hasattr(self, '_executor'):
            self._executor.shutdown(wait=False)