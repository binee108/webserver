"""
거래소 팩토리 및 어댑터 레이어

CCXT와 호환되는 인터페이스를 제공하면서 새로운 고성능 구현으로 점진적 전환을 지원합니다.
"""

import os
import asyncio
import logging
from typing import Dict, Any, Optional, Union
from abc import ABC, abstractmethod

from .base import BaseExchange
from .binance.spot import BinanceSpot
from .binance.futures import BinanceFutures

# CCXT 호환성을 위한 임포트 (기존 코드)
try:
    import ccxt  # CCXT_LEGACY
    CCXT_AVAILABLE = True
except ImportError:
    CCXT_AVAILABLE = False

logger = logging.getLogger(__name__)


class ExchangeFactory:
    """
    거래소 인스턴스 팩토리
    
    환경변수를 통한 점진적 전환 지원:
    - USE_CUSTOM_EXCHANGE=true: 새 구현 사용
    - USE_CUSTOM_EXCHANGE=false: CCXT 사용 (기본값)
    """
    
    SUPPORTED_EXCHANGES = {
        'binance': {
            'spot_class': BinanceSpot,
            'futures_class': BinanceFutures,
            'ccxt_spot': 'binance',      # CCXT_LEGACY
            'ccxt_futures': 'binanceusdm'  # CCXT_LEGACY
        }
    }
    
    @classmethod
    def create_exchange(cls, exchange_name: str, market_type: str, api_key: str, secret: str,
                       testnet: bool = False, **kwargs) -> Union[BaseExchange, 'ccxt.Exchange']:
        """
        거래소 인스턴스 생성
        
        Args:
            exchange_name: 거래소 이름 ('binance')
            market_type: 마켓 타입 ('SPOT', 'FUTURES')
            api_key: API 키
            secret: API 시크릿
            testnet: 테스트넷 사용 여부
            **kwargs: 추가 파라미터
        
        Returns:
            거래소 인스턴스 (Custom 또는 CCXT)
        """
        exchange_name = exchange_name.lower()
        market_type = market_type.upper()
        
        # 환경변수로 구현 선택
        use_custom = os.getenv('USE_CUSTOM_EXCHANGE', 'false').lower() == 'true'
        
        if use_custom and exchange_name in cls.SUPPORTED_EXCHANGES:
            logger.info(f"🚀 Custom {exchange_name} {market_type} API 사용")
            return cls._create_custom_exchange(exchange_name, market_type, api_key, secret, testnet, **kwargs)
        else:
            logger.info(f"🔄 CCXT {exchange_name} {market_type} API 사용")  # CCXT_LEGACY
            return cls._create_ccxt_exchange(exchange_name, market_type, api_key, secret, testnet, **kwargs)  # CCXT_LEGACY
    
    @classmethod
    def _create_custom_exchange(cls, exchange_name: str, market_type: str, api_key: str, secret: str,
                               testnet: bool = False, **kwargs) -> BaseExchange:
        """커스텀 거래소 인스턴스 생성"""
        config = cls.SUPPORTED_EXCHANGES.get(exchange_name)
        if not config:
            raise ValueError(f"지원되지 않는 거래소: {exchange_name}")
        
        if market_type == "FUTURES":
            exchange_class = config['futures_class']
        else:
            exchange_class = config['spot_class']
        
        try:
            instance = exchange_class(api_key, secret, testnet)
            
            # 마켓 정보 백그라운드 로딩
            if hasattr(instance, 'load_markets'):
                asyncio.create_task(instance.load_markets())
            
            logger.info(f"✅ {exchange_class.__name__} 인스턴스 생성 완료")
            return instance
            
        except Exception as e:
            logger.error(f"커스텀 거래소 인스턴스 생성 실패: {e}")
            raise
    
    @classmethod
    def _create_ccxt_exchange(cls, exchange_name: str, market_type: str, api_key: str, secret: str,  # CCXT_LEGACY
                             testnet: bool = False, **kwargs):  # CCXT_LEGACY
        """CCXT 거래소 인스턴스 생성 (레거시)"""  # CCXT_LEGACY
        if not CCXT_AVAILABLE:  # CCXT_LEGACY
            raise ImportError("CCXT 라이브러리가 설치되지 않았습니다")  # CCXT_LEGACY
        
        config = cls.SUPPORTED_EXCHANGES.get(exchange_name)  # CCXT_LEGACY
        if not config:  # CCXT_LEGACY
            raise ValueError(f"지원되지 않는 거래소: {exchange_name}")  # CCXT_LEGACY
        
        # CCXT 클래스 이름 선택  # CCXT_LEGACY
        if market_type == "FUTURES":  # CCXT_LEGACY
            ccxt_class_name = config['ccxt_futures']  # CCXT_LEGACY
        else:  # CCXT_LEGACY
            ccxt_class_name = config['ccxt_spot']  # CCXT_LEGACY
        
        try:  # CCXT_LEGACY
            # CCXT 클래스 가져오기  # CCXT_LEGACY
            exchange_class = getattr(ccxt, ccxt_class_name)  # CCXT_LEGACY
            
            # CCXT 설정  # CCXT_LEGACY
            ccxt_config = {  # CCXT_LEGACY
                'apiKey': api_key,  # CCXT_LEGACY
                'secret': secret,  # CCXT_LEGACY
                'sandbox': testnet,  # CCXT_LEGACY
                'enableRateLimit': True,  # CCXT_LEGACY
                'timeout': 30000,  # CCXT_LEGACY
                **kwargs  # CCXT_LEGACY
            }  # CCXT_LEGACY
            
            instance = exchange_class(ccxt_config)  # CCXT_LEGACY
            
            # 선물 거래소의 경우 defaultType 설정  # CCXT_LEGACY
            if market_type == "FUTURES" and exchange_name == 'binance' and ccxt_class_name == 'binanceusdm':  # CCXT_LEGACY
                instance.options['defaultType'] = 'future'  # CCXT_LEGACY
            elif market_type == "FUTURES":  # CCXT_LEGACY
                instance.options['defaultType'] = 'future'  # CCXT_LEGACY
            else:  # CCXT_LEGACY
                instance.options['defaultType'] = 'spot'  # CCXT_LEGACY
            
            logger.info(f"✅ CCXT {ccxt_class_name} 인스턴스 생성 완료")  # CCXT_LEGACY
            return instance  # CCXT_LEGACY
            
        except Exception as e:  # CCXT_LEGACY
            logger.error(f"CCXT 거래소 인스턴스 생성 실패: {e}")  # CCXT_LEGACY
            raise  # CCXT_LEGACY
    
    @classmethod
    def is_supported(cls, exchange_name: str) -> bool:
        """지원되는 거래소인지 확인"""
        return exchange_name.lower() in cls.SUPPORTED_EXCHANGES
    
    @classmethod
    def get_supported_exchanges(cls) -> list:
        """지원되는 거래소 목록 반환"""
        return list(cls.SUPPORTED_EXCHANGES.keys())


class ExchangeAdapter:
    """
    CCXT 호환 어댑터
    
    기존 ExchangeService 코드와의 호환성을 유지하면서
    점진적으로 새 구현으로 전환할 수 있도록 지원합니다.
    """
    
    def __init__(self, account):
        """
        Args:
            account: Account 모델 인스턴스 (public_api, secret_api, exchange, market_type 속성 필요)
        """
        self.account = account
        self.exchange_name = account.exchange.lower()
        self.market_type = getattr(account, 'market_type', 'SPOT')
        
        # 거래소 인스턴스 생성
        self.exchange = ExchangeFactory.create_exchange(
            exchange_name=self.exchange_name,
            api_key=account.public_api,
            secret=account.secret_api,
            market_type=self.market_type,
            testnet=False
        )
        
        # 커스텀 구현인지 CCXT인지 구분
        self.is_custom = isinstance(self.exchange, BaseExchange)
        
        logger.info(f"📡 ExchangeAdapter 초기화: {self.exchange_name} {self.market_type} (custom={self.is_custom})")
    
    # CCXT 호환 메서드들
    def fetch_balance(self):
        """잔액 조회 (CCXT 호환)"""
        if self.is_custom:
            return self.exchange.fetch_balance_sync()
        else:
            return self.exchange.fetch_balance()  # CCXT_LEGACY
    
    def fetch_ticker(self, symbol: str):
        """시세 조회 (CCXT 호환)"""
        if self.is_custom:
            return self.exchange.fetch_ticker_sync(symbol)
        else:
            return self.exchange.fetch_ticker(symbol)  # CCXT_LEGACY
    
    def create_market_order(self, symbol: str, side: str, amount: float, params: Dict = None):
        """시장가 주문 (CCXT 호환)"""
        if self.is_custom:
            return self.exchange.create_market_order(symbol, side, amount, params)
        else:
            return self.exchange.create_market_order(symbol, side, amount)  # CCXT_LEGACY
    
    def create_limit_order(self, symbol: str, side: str, amount: float, price: float, params: Dict = None):
        """지정가 주문 (CCXT 호환)"""
        if self.is_custom:
            return self.exchange.create_limit_order(symbol, side, amount, price, params)
        else:
            return self.exchange.create_limit_order(symbol, side, amount, price)  # CCXT_LEGACY
    
    def create_order(self, symbol: str, type: str, side: str, amount: float, price: float = None, params: Dict = None):
        """주문 생성 (CCXT 호환)"""
        if self.is_custom:
            return asyncio.run(self.exchange.create_order(symbol, type, side, amount, price, params))
        else:
            return self.exchange.create_order(symbol, type, side, amount, price, params)  # CCXT_LEGACY
    
    def cancel_order(self, order_id: str, symbol: str):
        """주문 취소 (CCXT 호환)"""
        if self.is_custom:
            return asyncio.run(self.exchange.cancel_order(order_id, symbol))
        else:
            return self.exchange.cancel_order(order_id, symbol)  # CCXT_LEGACY
    
    def fetch_order(self, order_id: str, symbol: str):
        """주문 조회 (CCXT 호환)"""
        if self.is_custom:
            return asyncio.run(self.exchange.fetch_order(order_id, symbol))
        else:
            return self.exchange.fetch_order(order_id, symbol)  # CCXT_LEGACY
    
    def fetch_open_orders(self, symbol: str = None):
        """미체결 주문 조회 (CCXT 호환)"""
        if self.is_custom:
            return self.exchange.fetch_open_orders_sync(symbol)
        else:
            return self.exchange.fetch_open_orders(symbol)  # CCXT_LEGACY
    
    def load_markets(self, reload: bool = False):
        """마켓 정보 로드 (CCXT 호환)"""
        if self.is_custom:
            return self.exchange.load_markets_sync(reload)
        else:
            return self.exchange.load_markets(reload)  # CCXT_LEGACY
    
    def fetch_positions(self, symbol: str = None):
        """포지션 조회 (CCXT 호환 - Futures 전용)"""
        if self.is_custom:
            if hasattr(self.exchange, 'fetch_positions'):
                positions = asyncio.run(self.exchange.fetch_positions())
                if symbol:
                    return [pos for pos in positions if pos.symbol == symbol]
                return positions
            else:
                raise NotImplementedError("이 거래소는 포지션 조회를 지원하지 않습니다")
        else:
            return self.exchange.fetch_positions(symbol)  # CCXT_LEGACY
    
    def set_leverage(self, symbol: str, leverage: int):
        """레버리지 설정 (CCXT 호환 - Futures 전용)"""
        if self.is_custom:
            if hasattr(self.exchange, 'set_leverage'):
                return asyncio.run(self.exchange.set_leverage(symbol, leverage))
            else:
                raise NotImplementedError("이 거래소는 레버리지 설정을 지원하지 않습니다")
        else:
            return self.exchange.set_leverage(symbol, leverage)  # CCXT_LEGACY
    
    def set_margin_type(self, symbol: str, margin_type: str):
        """마진 타입 설정 (CCXT 호환 - Futures 전용)"""
        if self.is_custom:
            if hasattr(self.exchange, 'set_margin_type'):
                return asyncio.run(self.exchange.set_margin_type(symbol, margin_type))
            else:
                raise NotImplementedError("이 거래소는 마진 타입 설정을 지원하지 않습니다")
        else:
            return self.exchange.set_margin_type(symbol, margin_type)  # CCXT_LEGACY
    
    # 속성 접근 (CCXT 호환)
    @property
    def markets(self):
        """마켓 정보 (CCXT 호환)"""
        if self.is_custom:
            # 캐시에서 마켓 정보 반환
            markets = {}
            for symbol, cache_item in self.exchange.cache.markets.items():
                if not cache_item.is_expired:
                    market_info = cache_item.data
                    # CCXT 형식으로 변환
                    markets[symbol] = {
                        'id': symbol,
                        'symbol': symbol,
                        'base': market_info.base_asset,
                        'quote': market_info.quote_asset,
                        'active': market_info.active,
                        'type': market_info.market_type.lower(),
                        'precision': {
                            'amount': market_info.amount_precision,
                            'price': market_info.price_precision
                        },
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
                        }
                    }
            return markets
        else:
            return self.exchange.markets  # CCXT_LEGACY
    
    @property
    def has(self):
        """지원 기능 정보 (CCXT 호환)"""
        if self.is_custom:
            return {
                'fetchBalance': True,
                'fetchTicker': True,
                'fetchOrder': True,
                'fetchOpenOrders': True,
                'createOrder': True,
                'cancelOrder': True,
                'fetchPositions': isinstance(self.exchange, BinanceFutures)
            }
        else:
            return self.exchange.has  # CCXT_LEGACY
    
    @property
    def name(self):
        """거래소 이름 (CCXT 호환)"""
        if self.is_custom:
            return self.exchange.__class__.__name__
        else:
            return self.exchange.name  # CCXT_LEGACY
    
    @property
    def id(self):
        """거래소 ID (CCXT 호환)"""
        if self.is_custom:
            return self.exchange_name
        else:
            return self.exchange.id  # CCXT_LEGACY
    
    @property
    def options(self):
        """거래소 옵션 (CCXT 호환)"""
        if self.is_custom:
            return {
                'defaultType': self.market_type.lower()
            }
        else:
            return self.exchange.options  # CCXT_LEGACY
    
    def market(self, symbol: str):
        """특정 심볼의 마켓 정보 (CCXT 호환)"""
        if self.is_custom:
            market_info = self.exchange.get_market_info(symbol)
            if market_info:
                return {
                    'id': symbol,
                    'symbol': symbol,
                    'base': market_info.base_asset,
                    'quote': market_info.quote_asset,
                    'active': market_info.active,
                    'type': market_info.market_type.lower(),
                    'precision': {
                        'amount': market_info.amount_precision,
                        'price': market_info.price_precision
                    },
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
                    }
                }
            else:
                raise ValueError(f"마켓 정보를 찾을 수 없음: {symbol}")
        else:
            return self.exchange.market(symbol)  # CCXT_LEGACY
    
    def get_stats(self):
        """성능 통계 (커스텀 기능)"""
        if self.is_custom:
            return self.exchange.get_stats()
        else:
            return {'api_calls': 0, 'cache': {'hits': 0, 'misses': 0}}  # CCXT_LEGACY
    
    # Futures 전용 메서드들
    def fetch_positions(self, symbol: str = None):
        """포지션 조회 (Futures 전용)"""
        if self.is_custom and isinstance(self.exchange, BinanceFutures):
            return self.exchange.fetch_positions_sync()
        elif hasattr(self.exchange, 'fetch_positions'):
            return self.exchange.fetch_positions(symbol)  # CCXT_LEGACY
        else:
            raise NotImplementedError("포지션 조회는 Futures 거래소에서만 지원됩니다")
    
    def set_leverage(self, symbol: str, leverage: int):
        """레버리지 설정 (Futures 전용)"""
        if self.is_custom and isinstance(self.exchange, BinanceFutures):
            return self.exchange.set_leverage_sync(symbol, leverage)
        elif hasattr(self.exchange, 'set_leverage'):
            return self.exchange.set_leverage(symbol, leverage)  # CCXT_LEGACY
        else:
            raise NotImplementedError("레버리지 설정은 Futures 거래소에서만 지원됩니다")
    
    def set_margin_type(self, symbol: str, margin_type: str):
        """마진 타입 설정 (Futures 전용)"""
        if self.is_custom and isinstance(self.exchange, BinanceFutures):
            return self.exchange.set_margin_type_sync(symbol, margin_type)
        elif hasattr(self.exchange, 'set_margin_type'):
            return self.exchange.set_margin_type(symbol, margin_type)  # CCXT_LEGACY
        else:
            raise NotImplementedError("마진 타입 설정은 Futures 거래소에서만 지원됩니다")