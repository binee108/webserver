#!/usr/bin/env python3
"""
UniversalExchange - 거래소별 SPOT/FUTURES API를 통일된 인터페이스로 제공 (Enhanced Factory 지원)

모든 거래소의 SPOT/FUTURES API 차이를 추상화하여
일관된 방식으로 precision 정보를 조회할 수 있도록 합니다.

주요 특징:
- Binance: 별도 API (binance vs binanceusdm)
- KuCoin: 별도 API (kucoin vs kucoinfutures) 
- OKX, Bybit 등: 통합 API (defaultType으로 구분)
- 자동 심볼 형식 변환
- 거래소별 특성 고려
- Enhanced Factory 우선 사용 (Feature Flag 기반)
"""

import ccxt
from typing import Dict, Any, Optional, List
import logging

from app.constants import MarketType

logger = logging.getLogger(__name__)

# Enhanced Factory import (optional)
try:
    from web_server.app.exchanges.enhanced_factory import enhanced_factory
    from web_server.app.exchanges.config import should_use_custom_exchange
    ENHANCED_FACTORY_AVAILABLE = True
    logger.info("✅ UniversalExchange: Enhanced Factory 사용 가능")
except ImportError as e:
    ENHANCED_FACTORY_AVAILABLE = False
    enhanced_factory = None
    logger.warning(f"⚠️ UniversalExchange: Enhanced Factory 사용 불가 (레거시 모드): {e}")

class UniversalExchange:
    """거래소별 SPOT/FUTURES API를 통일된 인터페이스로 제공하는 클래스"""
    
    # 검증된 거래소별 API 매핑
    EXCHANGE_API_MAPPING = {
        'binance': {
            'spot_api': 'binance',
            'futures_api': 'binanceusdm',
            'has_separate_api': True,
            'futures_default_type': 'swap',
            'symbol_formats': {
                'spot': ['BTC/USDT', 'BTCUSDT'],      
                'futures': ['BTC/USDT:USDT', 'BTCUSDT'] 
            }
        },
        'kucoin': {
            'spot_api': 'kucoin',
            'futures_api': 'kucoinfutures',
            'has_separate_api': True,
            'futures_default_type': 'swap',
            'symbol_formats': {
                'spot': ['BTC/USDT', 'BTCUSDT'],      
                'futures': ['BTC/USDT:USDT', 'BTCUSDT']
            }
        },
        'okx': {
            'spot_api': 'okx',
            'futures_api': 'okx',
            'has_separate_api': False,
            'futures_default_type': 'swap',
            'symbol_formats': {
                'spot': ['BTC/USDT:USDT', 'BTC/USDT', 'BTCUSDT'],
                'futures': ['BTC/USDT:USDT', 'BTC/USDT', 'BTCUSDT']
            }
        },
        'bybit': {
            'spot_api': 'bybit',
            'futures_api': 'bybit',
            'has_separate_api': False,
            'futures_default_type': 'linear',  # Bybit는 linear 사용
            'symbol_formats': {
                'spot': ['BTC/USDT:USDT', 'BTC/USDT', 'BTCUSDT'],
                'futures': ['BTC/USDT:USDT', 'BTC/USDT', 'BTCUSDT']
            }
        },
        'gate': {
            'spot_api': 'gate',
            'futures_api': 'gate',
            'has_separate_api': False,
            'futures_default_type': 'swap',
            'symbol_formats': {
                'spot': ['BTC/USDT:USDT', 'BTC/USDT', 'BTCUSDT'],
                'futures': ['BTC/USDT:USDT', 'BTC/USDT', 'BTCUSDT']
            }
        },
        'huobi': {
            'spot_api': 'huobipro',
            'futures_api': 'huobipro',
            'has_separate_api': False,
            'futures_default_type': 'swap',
            'symbol_formats': {
                'spot': ['BTC/USDT:USDT', 'BTC/USDT', 'BTCUSDT'],
                'futures': ['BTC/USDT:USDT', 'BTC/USDT', 'BTCUSDT']
            }
        }
    }
    
    def __init__(self, exchange_name: str, api_credentials: Dict[str, Any] = None):
        """
        Args:
            exchange_name: 거래소 이름 ('binance', 'okx', 'bybit' 등)
            api_credentials: API 인증 정보 (apiKey, secret 등)
        """
        self.exchange_name = exchange_name.lower()
        self.api_credentials = api_credentials or {}
        self._spot_instance = None
        self._futures_instance = None
        self._config = self.EXCHANGE_API_MAPPING.get(self.exchange_name)
        
        if not self._config:
            raise ValueError(f"지원되지 않는 거래소: {exchange_name}. 지원 거래소: {list(self.EXCHANGE_API_MAPPING.keys())}")
    
    def _create_exchange_instance(self, api_class_name: str, market_type: str) -> ccxt.Exchange:
        """거래소 인스턴스 생성"""
        try:
            exchange_class = getattr(ccxt, api_class_name)
            
            # 기본 설정
            config = {
                'sandbox': False,
                'enableRateLimit': True,
                'timeout': 30000,
                **self.api_credentials  # API 인증 정보 추가
            }
            
            instance = exchange_class(config)
            
            # 통합 API인 경우 defaultType 설정
            if not self._config['has_separate_api']:
                if market_type == MarketType.FUTURES:
                    instance.options['defaultType'] = self._config['futures_default_type']
                else:
                    instance.options['defaultType'] = 'spot'
                    
                logger.debug(f"🔧 {self.exchange_name} 통합 API defaultType 설정: {instance.options.get('defaultType')}")
            else:
                logger.debug(f"🔧 {self.exchange_name} 별도 API 사용: {api_class_name}")
            
            return instance
            
        except AttributeError:
            raise ValueError(f"CCXT에서 {api_class_name} 클래스를 찾을 수 없음")
        except Exception as e:
            raise Exception(f"거래소 인스턴스 생성 실패 ({api_class_name}): {e}")
    
    def get_spot_instance(self) -> ccxt.Exchange:
        """SPOT 거래소 인스턴스 반환 (지연 로딩)"""
        if not self._spot_instance:
            api_class = self._config['spot_api']
            self._spot_instance = self._create_exchange_instance(api_class, MarketType.SPOT)
            self._spot_instance.load_markets()
            logger.debug(f"📊 {self.exchange_name} SPOT 인스턴스 생성 완료: {len(self._spot_instance.markets)}개 심볼")
            
        return self._spot_instance
    
    def get_futures_instance(self) -> ccxt.Exchange:
        """FUTURES 거래소 인스턴스 반환 (지연 로딩)"""
        if not self._futures_instance:
            api_class = self._config['futures_api']
            self._futures_instance = self._create_exchange_instance(api_class, MarketType.FUTURES)
            self._futures_instance.load_markets()
            logger.debug(f"🚀 {self.exchange_name} FUTURES 인스턴스 생성 완료: {len(self._futures_instance.markets)}개 심볼")
            
        return self._futures_instance
    
    def get_instance(self, market_type: str) -> ccxt.Exchange:
        """Market Type에 따른 인스턴스 반환"""
        normalized_type = MarketType.normalize(market_type)
        
        if normalized_type == MarketType.FUTURES:
            return self.get_futures_instance()
        else:
            return self.get_spot_instance()
    
    def _generate_symbol_formats(self, symbol: str, market_type: str) -> List[str]:
        """심볼을 거래소/마켓 타입에 맞는 다양한 형식으로 변환"""
        
        # 거래소별 선호 형식
        preferred_formats = self._config.get('symbol_formats', {}).get(market_type, [])
        
        # 기본 변환 패턴
        if '/' not in symbol and 'USDT' in symbol:
            base = symbol.replace('USDT', '')
            base_formats = [
                f"{base}/USDT",      # BTC/USDT
                f"{base}/USDT:USDT", # BTC/USDT:USDT  
                f"{base}USDT",       # BTCUSDT (원본)
            ]
        elif symbol.endswith('USDT') and '/' in symbol:
            # BTC/USDT -> 다양한 형식
            base = symbol.split('/')[0]
            base_formats = [
                symbol,              # BTC/USDT (원본)
                f"{symbol}:USDT",    # BTC/USDT:USDT
                f"{base}USDT",       # BTCUSDT
            ]
        else:
            base_formats = [symbol]
        
        # 선호 형식을 앞에 배치
        all_formats = []
        for preferred in preferred_formats:
            if preferred not in all_formats:
                all_formats.append(preferred)
        
        for fmt in base_formats:
            if fmt not in all_formats:
                all_formats.append(fmt)
        
        return all_formats
    
    def get_precision(self, symbol: str, market_type: str) -> Optional[Dict[str, Any]]:
        """심볼의 precision 정보 반환 (Enhanced Factory 우선 지원)"""
        
        # Enhanced Factory 우선 시도 (Feature Flag 기반)
        if (ENHANCED_FACTORY_AVAILABLE and 
            should_use_custom_exchange is not None and 
            should_use_custom_exchange(self.exchange_name)):
            try:
                logger.info(f"🔄 Enhanced Factory를 사용하여 {self.exchange_name} precision 조회")
                enhanced_instance = enhanced_factory.create_exchange(
                    exchange_name=self.exchange_name,
                    market_type=market_type,
                    api_key=self.api_credentials.get('apiKey'),
                    api_secret=self.api_credentials.get('secret'),
                    testnet=False  # 기본값
                )
                
                if hasattr(enhanced_instance, 'markets') and enhanced_instance.markets:
                    logger.info(f"✅ Enhanced Factory precision 조회 성공: {self.exchange_name}")
                    # Enhanced Factory 결과를 기존 형식으로 변환
                    return self._convert_enhanced_precision_format(enhanced_instance, symbol, market_type)
                    
            except Exception as e:
                logger.warning(f"⚠️ Enhanced Factory precision 조회 실패, 레거시로 폴백: {e}")
        
        # 레거시 방식 (기존 코드)
        try:
            instance = self.get_instance(market_type)
            test_symbols = self._generate_symbol_formats(symbol, market_type)
            
            logger.debug(f"🔍 {self.exchange_name} {market_type} precision 조회: {symbol} -> {test_symbols}")
            
            for test_symbol in test_symbols:
                if test_symbol in instance.markets:
                    market = instance.markets[test_symbol]
                    precision = market.get('precision', {})
                    
                    result = {
                        'symbol': test_symbol,
                        'original_symbol': symbol,
                        'amount_precision': precision.get('amount'),
                        'price_precision': precision.get('price'),
                        'market_type': market.get('type'),
                        'limits': market.get('limits', {}),
                        'exchange': self.exchange_name,
                        'api_class': self._config['futures_api'] if market_type == MarketType.FUTURES else self._config['spot_api'],
                        'has_separate_api': self._config['has_separate_api'],
                        'market_info': {
                            'base': market.get('base'),
                            'quote': market.get('quote'),
                            'settle': market.get('settle'),
                            'active': market.get('active', True)
                        }
                    }
                    
                    logger.debug(f"✅ {self.exchange_name} {market_type} precision 찾음: {test_symbol} -> amount={result['amount_precision']}, price={result['price_precision']}")
                    return result
            
            logger.warning(f"❌ {self.exchange_name} {market_type} precision 찾을 수 없음: {symbol} (시도한 형식: {test_symbols})")
            return None
            
        except Exception as e:
            logger.error(f"❌ {self.exchange_name} {market_type} precision 조회 실패: {symbol} - {e}")
            raise Exception(f"{self.exchange_name} {market_type} precision 조회 실패: {e}")
    
    def reload_markets(self, market_type: str = None):
        """markets 강제 reload"""
        if market_type is None:
            # 모든 인스턴스 reload
            if self._spot_instance:
                self._spot_instance.load_markets(reload=True)
                logger.info(f"🔄 {self.exchange_name} SPOT markets 리로드 완료")
            if self._futures_instance:
                self._futures_instance.load_markets(reload=True)
                logger.info(f"🔄 {self.exchange_name} FUTURES markets 리로드 완료")
        else:
            instance = self.get_instance(market_type)
            instance.load_markets(reload=True)
            logger.info(f"🔄 {self.exchange_name} {market_type} markets 리로드 완료")
    
    def get_supported_exchanges(self) -> List[str]:
        """지원하는 거래소 목록 반환"""
        return list(self.EXCHANGE_API_MAPPING.keys())
    
    def get_exchange_info(self) -> Dict[str, Any]:
        """현재 거래소 설정 정보 반환"""
        return {
            'exchange_name': self.exchange_name,
            'config': self._config,
            'spot_loaded': self._spot_instance is not None,
            'futures_loaded': self._futures_instance is not None,
            'spot_markets_count': len(self._spot_instance.markets) if self._spot_instance else 0,
            'futures_markets_count': len(self._futures_instance.markets) if self._futures_instance else 0
        }
    
    def is_supported(self, exchange_name: str) -> bool:
        """거래소 지원 여부 확인"""
        return exchange_name.lower() in self.EXCHANGE_API_MAPPING
    
    def close(self):
        """리소스 정리"""
        if self._spot_instance:
            try:
                self._spot_instance.close()
            except:
                pass
            self._spot_instance = None
            
        if self._futures_instance:
            try:
                self._futures_instance.close()
            except:
                pass
            self._futures_instance = None
        
        logger.debug(f"🔒 {self.exchange_name} UniversalExchange 리소스 정리 완료")
    
    def _convert_enhanced_precision_format(self, enhanced_instance, symbol: str, market_type: str) -> Optional[Dict[str, Any]]:
        """Enhanced Factory 결과를 기존 UniversalExchange 형식으로 변환"""
        try:
            test_symbols = self._generate_symbol_formats(symbol, market_type)
            
            for test_symbol in test_symbols:
                if hasattr(enhanced_instance, 'markets') and test_symbol in enhanced_instance.markets:
                    market = enhanced_instance.markets[test_symbol]
                    
                    return {
                        'amount_precision': market.get('precision', {}).get('amount', 8),
                        'price_precision': market.get('precision', {}).get('price', 8),
                        'limits': market.get('limits', {}),
                        'symbol': test_symbol,
                        'original_symbol': symbol,
                        'market_type': market_type,
                        'market_info': {
                            'active': market.get('active', True),
                            'base': market.get('base'),
                            'quote': market.get('quote'),
                            'type': market.get('type')
                        },
                        'api_class': enhanced_instance.__class__.__name__,
                        'has_separate_api': self._config.get('has_separate_api', False)
                    }
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Enhanced Factory 결과 변환 실패: {e}")
            return None
    
    def __del__(self):
        """소멸자"""
        self.close()


class UniversalExchangeManager:
    """여러 거래소의 UniversalExchange 인스턴스를 관리하는 매니저"""
    
    def __init__(self):
        self._exchanges: Dict[str, UniversalExchange] = {}
    
    def get_exchange(self, exchange_name: str, api_credentials: Dict[str, Any] = None) -> UniversalExchange:
        """거래소별 UniversalExchange 인스턴스 반환 (캐시됨)"""
        cache_key = f"{exchange_name}_{id(api_credentials) if api_credentials else 'no_cred'}"
        
        if cache_key not in self._exchanges:
            self._exchanges[cache_key] = UniversalExchange(exchange_name, api_credentials)
            logger.debug(f"🆕 UniversalExchange 생성: {exchange_name}")
        
        return self._exchanges[cache_key]
    
    def clear_cache(self, exchange_name: str = None):
        """캐시 정리"""
        if exchange_name:
            # 특정 거래소만 정리
            keys_to_remove = [k for k in self._exchanges.keys() if k.startswith(f"{exchange_name}_")]
            for key in keys_to_remove:
                self._exchanges[key].close()
                del self._exchanges[key]
            logger.info(f"🗑️ {exchange_name} UniversalExchange 캐시 정리 완료")
        else:
            # 모든 캐시 정리
            for exchange in self._exchanges.values():
                exchange.close()
            self._exchanges.clear()
            logger.info("🗑️ 모든 UniversalExchange 캐시 정리 완료")
    
    def get_cache_info(self) -> Dict[str, Any]:
        """캐시 상태 정보 반환"""
        return {
            'cached_exchanges': len(self._exchanges),
            'exchanges': {k: v.get_exchange_info() for k, v in self._exchanges.items()}
        }
    
    def __del__(self):
        """소멸자"""
        self.clear_cache()


# 전역 매니저 인스턴스
universal_exchange_manager = UniversalExchangeManager()