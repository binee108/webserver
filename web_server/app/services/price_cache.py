"""
가격 캐싱 서비스
심볼별 현재가를 메모리에 캐싱하고 주기적으로 업데이트
"""

import logging
import time
import threading
from typing import Dict, Optional, Any
from decimal import Decimal
from datetime import datetime, timedelta
from collections import defaultdict

from app.constants import Exchange, MarketType
from app.services.exchange import exchange_service

logger = logging.getLogger(__name__)


class PriceCache:
    """
    가격 캐싱 시스템
    - Thread-safe 구현
    - TTL 및 fallback 메커니즘
    - 거래소별, 마켓타입별 캐싱
    """
    
    def __init__(self, ttl_seconds: int = 60):
        """
        Args:
            ttl_seconds: 캐시 유효 시간 (기본 60초)
        """
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._update_counts = defaultdict(int)
        self._hit_counts = defaultdict(int)
        self._miss_counts = defaultdict(int)
        
        logger.info(f"✅ PriceCache 초기화 완료 (TTL: {ttl_seconds}초)")
    
    def _get_cache_key(self, symbol: str, exchange: str = Exchange.BINANCE, 
                      market_type: str = MarketType.FUTURES) -> str:
        """캐시 키 생성"""
        return f"{exchange}:{market_type}:{symbol}".upper()
    
    def get_price(self, symbol: str, exchange: str = Exchange.BINANCE,
                  market_type: str = MarketType.FUTURES,
                  fallback_to_api: bool = True,
                  return_details: bool = False) -> Optional[Any]:
        """
        캐시된 가격 조회
        
        Args:
            symbol: 심볼 (예: BTCUSDT)
            exchange: 거래소
            market_type: 마켓 타입
            fallback_to_api: 캐시 미스 시 API 호출 여부
            
        Returns:
            가격 (Decimal) 또는 None
        """
        cache_key = self._get_cache_key(symbol, exchange, market_type)
        
        with self._lock:
            # 캐시 확인
            if cache_key in self._cache:
                cached_data = self._cache[cache_key]
                cached_time = cached_data.get('timestamp', 0)
                age_seconds = time.time() - cached_time

                if age_seconds > 3600:
                    logger.critical(
                        "가격 캐시 갱신 지연 감지 - symbol=%s exchange=%s market_type=%s age=%.1fs",
                        symbol, exchange, market_type, age_seconds
                    )
                    return None

                # TTL 체크
                if age_seconds < self.ttl_seconds:
                    price = cached_data.get('price')
                    if price is not None:
                        self._hit_counts[cache_key] += 1
                        logger.debug(
                            "💰 캐시 HIT: %s = %s (age: %.1f초)",
                            symbol, price, age_seconds
                        )
                        result = Decimal(str(price))
                        if return_details:
                            return {
                                'price': result,
                                'age_seconds': age_seconds,
                                'source': 'cache',
                                'timestamp': cached_time
                            }
                        return result
                else:
                    logger.debug(
                        "⏰ 캐시 만료: %s (age: %.1f초)",
                        symbol, age_seconds
                    )

            self._miss_counts[cache_key] += 1

            # Fallback: API 직접 호출
            if fallback_to_api:
                logger.info(f"📡 캐시 MISS: {symbol} - API 호출")
                price = self._fetch_price_from_api(symbol, exchange, market_type)
                if price is not None:
                    # 캐시 업데이트
                    self.set_price(symbol, price, exchange, market_type)
                    if return_details:
                        return {
                            'price': price,
                            'age_seconds': 0.0,
                            'source': 'api',
                            'timestamp': time.time()
                        }
                    return price

            return None
    
    def set_price(self, symbol: str, price: Decimal, 
                  exchange: str = Exchange.BINANCE,
                  market_type: str = MarketType.FUTURES) -> None:
        """
        가격 캐시 업데이트
        
        Args:
            symbol: 심볼
            price: 가격
            exchange: 거래소
            market_type: 마켓 타입
        """
        cache_key = self._get_cache_key(symbol, exchange, market_type)
        
        with self._lock:
            old_price = self._cache.get(cache_key, {}).get('price')
            self._cache[cache_key] = {
                'price': float(price),
                'timestamp': time.time(),
                'exchange': exchange,
                'market_type': market_type,
                'symbol': symbol
            }
            self._update_counts[cache_key] += 1
            
            if old_price != float(price):
                logger.debug(f"📊 가격 업데이트: {symbol} = {price} "
                           f"(이전: {old_price})")
    
    def update_batch_prices(self, symbols: list, 
                           exchange: str = Exchange.BINANCE,
                           market_type: str = MarketType.FUTURES) -> Dict[str, Decimal]:
        """
        여러 심볼 가격 일괄 업데이트
        
        Args:
            symbols: 심볼 리스트
            exchange: 거래소
            market_type: 마켓 타입
            
        Returns:
            업데이트된 가격 딕셔너리
        """
        updated_prices: Dict[str, Decimal] = {}

        try:
            if not symbols:
                logger.debug('업데이트할 심볼이 없어 가격 캐시 배치를 건너뜁니다')
                return updated_prices

            exchange_normalized = Exchange.normalize(exchange) if exchange else Exchange.BINANCE
            if not exchange_normalized:
                exchange_normalized = Exchange.BINANCE

            market_normalized = MarketType.normalize(market_type) if market_type else MarketType.SPOT

            symbol_list = sorted({symbol.upper() for symbol in symbols})
            quotes = exchange_service.get_price_quotes(
                exchange=exchange_normalized,
                market_type=market_normalized,
                symbols=symbol_list
            )

            for symbol in symbol_list:
                quote = quotes.get(symbol)
                if not quote:
                    logger.debug(
                        "가격 정보를 찾을 수 없어 캐시 업데이트를 건너뜁니다 - exchange=%s market=%s symbol=%s",
                        exchange_normalized, market_normalized, symbol
                    )
                    continue

                self.set_price(symbol, quote.last_price, exchange_normalized, market_normalized)
                updated_prices[symbol] = quote.last_price

            logger.info(
                "✅ 배치 가격 업데이트 완료: %s/%s 심볼 (exchange=%s market=%s)",
                len(updated_prices),
                len(symbol_list),
                exchange_normalized,
                market_normalized
            )

        except Exception as e:
            logger.error(f"❌ 배치 가격 업데이트 실패: {e}")
        
        return updated_prices
    
    def _fetch_price_from_api(self, symbol: str, 
                             exchange: str = Exchange.BINANCE,
                             market_type: str = MarketType.FUTURES) -> Optional[Decimal]:
        """
        API에서 직접 가격 조회
        
        Args:
            symbol: 심볼
            exchange: 거래소
            market_type: 마켓 타입
            
        Returns:
            가격 또는 None
        """
        try:
            exchange_normalized = Exchange.normalize(exchange) if exchange else Exchange.BINANCE
            if not exchange_normalized:
                exchange_normalized = Exchange.BINANCE

            market_normalized = MarketType.normalize(market_type) if market_type else MarketType.SPOT

            quotes = exchange_service.get_price_quotes(
                exchange=exchange_normalized,
                market_type=market_normalized,
                symbols=[symbol.upper()]
            )

            quote = quotes.get(symbol.upper())
            if quote:
                return quote.last_price

        except Exception as e:
            logger.error(f"API 가격 조회 실패: {symbol} - {e}")
        
        return None
    
    def clear_cache(self, exchange: Optional[str] = None, 
                    market_type: Optional[str] = None) -> int:
        """
        캐시 클리어
        
        Args:
            exchange: 특정 거래소만 클리어 (None이면 전체)
            market_type: 특정 마켓타입만 클리어 (None이면 전체)
            
        Returns:
            삭제된 항목 수
        """
        with self._lock:
            if exchange is None and market_type is None:
                # 전체 클리어
                count = len(self._cache)
                self._cache.clear()
                logger.info(f"🗑️ 전체 캐시 클리어: {count}개 항목 삭제")
                return count
            
            # 조건부 클리어
            keys_to_delete = []
            for key, data in self._cache.items():
                if exchange and data.get('exchange') != exchange:
                    continue
                if market_type and data.get('market_type') != market_type:
                    continue
                keys_to_delete.append(key)
            
            for key in keys_to_delete:
                del self._cache[key]
            
            logger.info(f"🗑️ 조건부 캐시 클리어: {len(keys_to_delete)}개 항목 삭제")
            return len(keys_to_delete)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        캐시 통계 정보
        
        Returns:
            통계 정보 딕셔너리
        """
        with self._lock:
            total_hits = sum(self._hit_counts.values())
            total_misses = sum(self._miss_counts.values())
            total_updates = sum(self._update_counts.values())
            hit_rate = total_hits / (total_hits + total_misses) * 100 if (total_hits + total_misses) > 0 else 0
            
            return {
                'cache_size': len(self._cache),
                'total_hits': total_hits,
                'total_misses': total_misses,
                'total_updates': total_updates,
                'hit_rate': f"{hit_rate:.1f}%",
                'ttl_seconds': self.ttl_seconds
            }
    
    def get_cached_symbols(self, exchange: Optional[str] = None,
                          market_type: Optional[str] = None) -> list:
        """
        캐시된 심볼 목록 조회
        
        Args:
            exchange: 거래소 필터
            market_type: 마켓타입 필터
            
        Returns:
            심볼 리스트
        """
        with self._lock:
            symbols = []
            for key, data in self._cache.items():
                if exchange and data.get('exchange') != exchange:
                    continue
                if market_type and data.get('market_type') != market_type:
                    continue
                symbols.append(data.get('symbol'))
            return symbols


# 싱글톤 인스턴스
price_cache = PriceCache(ttl_seconds=30)  # 30초 TTL
