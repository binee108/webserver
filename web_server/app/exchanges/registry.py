#!/usr/bin/env python3
"""
Exchange Registry - 거래소 구현체 중앙 관리 시스템

확장성과 유지보수성을 고려한 거래소 등록/관리 시스템
- 플러그인 방식의 거래소 추가
- 런타임 거래소 선택
- 설정 기반 자동 구성
- 호환성 검증
"""

import importlib
import inspect
import logging
from typing import Dict, Any, List, Optional, Type, Callable, Union
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path

logger = logging.getLogger(__name__)

class ExchangeType(Enum):
    """지원하는 거래소 타입"""
    CCXT = "ccxt"
    CUSTOM = "custom"
    HYBRID = "hybrid"  # CCXT + 커스텀 최적화

@dataclass
class ExchangeCapability:
    """거래소 지원 기능"""
    spot_trading: bool = True
    futures_trading: bool = False
    margin_trading: bool = False
    websocket_support: bool = False
    advanced_orders: bool = False
    position_management: bool = False
    funding_rates: bool = False
    historical_data: bool = True

@dataclass
class ExchangeMetadata:
    """거래소 메타데이터"""
    name: str
    display_name: str
    exchange_type: ExchangeType
    capabilities: ExchangeCapability
    supported_markets: List[str]  # ['spot', 'futures', 'margin']
    api_endpoints: Dict[str, str]
    rate_limits: Dict[str, Any]
    implementation_class: Optional[Type] = None
    ccxt_id: Optional[str] = None
    priority: int = 0  # 우선순위 (높을수록 우선)
    status: str = "active"  # active, deprecated, experimental
    
# Interfaces imported from separate file to avoid circular imports
from .interfaces import ExchangeInterface, AsyncExchangeInterface

class ExchangeRegistry:
    """거래소 구현체 중앙 등록소"""
    
    def __init__(self):
        self._exchanges: Dict[str, ExchangeMetadata] = {}
        self._instances: Dict[str, Any] = {}
        self._default_exchange: Optional[str] = None
        self._config_handlers: Dict[str, Callable] = {}
        self._initialization_hooks: List[Callable] = []
        
    def register(
        self, 
        name: str, 
        display_name: str, 
        exchange_type: ExchangeType,
        capabilities: ExchangeCapability,
        implementation_class: Optional[Type] = None,
        ccxt_id: Optional[str] = None,
        **kwargs
    ) -> None:
        """거래소 구현체 등록
        
        Args:
            name: 내부 식별자 (예: 'binance_custom')
            display_name: 사용자 친화적 이름 (예: 'Binance (Custom)')
            exchange_type: 거래소 타입
            capabilities: 지원 기능
            implementation_class: 구현 클래스
            ccxt_id: CCXT 거래소 ID (해당하는 경우)
        """
        metadata = ExchangeMetadata(
            name=name,
            display_name=display_name,
            exchange_type=exchange_type,
            capabilities=capabilities,
            implementation_class=implementation_class,
            ccxt_id=ccxt_id,
            **kwargs
        )
        
        # 인터페이스 검증 (유연한 처리)
        validation_passed = True
        if implementation_class:
            validation_result = self._validate_interface(implementation_class, exchange_type)
            if not validation_result:
                logger.warning(f"⚠️ {implementation_class.__name__} 인터페이스 검증 실패, 부분 등록 진행")
                validation_passed = False
        
        self._exchanges[name] = metadata
        status_icon = "✅" if validation_passed else "⚠️"
        logger.info(f"{status_icon} Exchange 등록 완료: {display_name} ({exchange_type.value})")
        
    def _validate_interface(self, cls: Type, exchange_type: ExchangeType) -> bool:
        """구현 클래스가 적절한 인터페이스를 구현했는지 검증"""
        # CCXT 타입은 동적 생성이므로 검증 스킵
        if exchange_type == ExchangeType.CCXT:
            return True
            
        # 동기/비동기 인터페이스 확인
        is_sync_interface = issubclass(cls, ExchangeInterface) if hasattr(cls, '__mro__') else False
        is_async_interface = issubclass(cls, AsyncExchangeInterface) if hasattr(cls, '__mro__') else False
        
        if not is_sync_interface and not is_async_interface:
            logger.debug(f"🔍 {cls.__name__}가 정의된 인터페이스를 구현하지 않음 (검증 통과)")
            return True  # 유연한 처리
        
        required_methods = [
            'load_markets', 'fetch_ticker', 'fetch_balance', 
            'create_order', 'cancel_order', 'fetch_order'
        ]
        
        for method_name in required_methods:
            if not hasattr(cls, method_name):
                logger.warning(f"⚠️ {cls.__name__}에 필수 메서드 {method_name} 누락")
                continue
            
            method = getattr(cls, method_name)
            is_async_method = inspect.iscoroutinefunction(method)
            
            # 비동기 인터페이스는 async 메서드, 동기 인터페이스는 일반 메서드
            if is_async_interface and not is_async_method:
                logger.warning(f"⚠️ {cls.__name__}.{method_name}는 async 메서드여야 함")
            elif is_sync_interface and is_async_method:
                logger.warning(f"⚠️ {cls.__name__}.{method_name}는 동기 메서드여야 함")
                
        return True  # 경고만 출력하고 등록은 허용
    
    def auto_discover(self, base_path: str = None) -> int:
        """자동으로 거래소 구현체 발견 및 등록
        
        Returns:
            등록된 거래소 수
        """
        if base_path is None:
            base_path = os.path.dirname(__file__)
        
        discovered_count = 0
        
        # exchanges 폴더 내 구현체 스캔
        exchanges_path = Path(base_path)
        
        # Binance 커스텀 구현 자동 등록
        binance_path = exchanges_path / "binance"
        if binance_path.exists():
            try:
                # Spot 구현
                from .binance.spot import BinanceSpot
                self.register(
                    name="binance_spot_custom",
                    display_name="Binance Spot (Custom)",
                    exchange_type=ExchangeType.CUSTOM,
                    capabilities=ExchangeCapability(
                        spot_trading=True,
                        websocket_support=True,
                        advanced_orders=True,
                        historical_data=True
                    ),
                    implementation_class=BinanceSpot,
                    supported_markets=["spot"],
                    api_endpoints={"spot": "https://api.binance.com"},
                    rate_limits={"requests_per_minute": 1200},
                    priority=100  # 커스텀 구현 우선순위 높게
                )
                discovered_count += 1
                
                # Futures 구현
                from .binance.futures import BinanceFutures
                self.register(
                    name="binance_futures_custom", 
                    display_name="Binance Futures (Custom)",
                    exchange_type=ExchangeType.CUSTOM,
                    capabilities=ExchangeCapability(
                        futures_trading=True,
                        position_management=True,
                        advanced_orders=True,
                        funding_rates=True,
                        websocket_support=True
                    ),
                    implementation_class=BinanceFutures,
                    supported_markets=["futures"],
                    api_endpoints={"futures": "https://fapi.binance.com"},
                    rate_limits={"requests_per_minute": 1200},
                    priority=100
                )
                discovered_count += 1
                
                logger.info("✅ Binance 커스텀 구현 자동 발견 및 등록 완료")
                
            except ImportError as e:
                logger.warning(f"⚠️ Binance 커스텀 구현 로드 실패: {e}")
        
        # CCXT 기반 폴백 등록
        self._register_ccxt_fallbacks()
        discovered_count += 2  # binance spot/futures
        
        logger.info(f"🔍 총 {discovered_count}개 거래소 구현체 자동 등록 완료")
        return discovered_count
    
    def _register_ccxt_fallbacks(self):
        """CCXT 기반 폴백 구현 등록"""
        # Binance CCXT 폴백
        self.register(
            name="binance_spot_ccxt",
            display_name="Binance Spot (CCXT)",
            exchange_type=ExchangeType.CCXT,
            capabilities=ExchangeCapability(
                spot_trading=True,
                advanced_orders=True,
                historical_data=True
            ),
            ccxt_id="binance",
            supported_markets=["spot"],
            api_endpoints={"spot": "https://api.binance.com"},
            rate_limits={"requests_per_minute": 1200},
            priority=10  # 낮은 우선순위
        )
        
        self.register(
            name="binance_futures_ccxt",
            display_name="Binance Futures (CCXT)", 
            exchange_type=ExchangeType.CCXT,
            capabilities=ExchangeCapability(
                futures_trading=True,
                position_management=True,
                advanced_orders=True
            ),
            ccxt_id="binanceusdm",
            supported_markets=["futures"],
            api_endpoints={"futures": "https://fapi.binance.com"},
            rate_limits={"requests_per_minute": 1200},
            priority=10
        )
    
    def get_exchange(self, name: str) -> Optional[ExchangeMetadata]:
        """등록된 거래소 메타데이터 조회"""
        return self._exchanges.get(name)
    
    def list_exchanges(
        self, 
        exchange_type: Optional[ExchangeType] = None,
        market_type: Optional[str] = None,
        status: str = "active"
    ) -> List[ExchangeMetadata]:
        """조건에 맞는 거래소 목록 조회"""
        results = []
        
        for metadata in self._exchanges.values():
            if status and metadata.status != status:
                continue
                
            if exchange_type and metadata.exchange_type != exchange_type:
                continue
                
            if market_type and market_type not in metadata.supported_markets:
                continue
                
            results.append(metadata)
        
        # 우선순위 순으로 정렬
        results.sort(key=lambda x: x.priority, reverse=True)
        return results
    
    def find_best_exchange(
        self, 
        market_type: str,
        exchange_name: Optional[str] = None,
        prefer_custom: bool = True
    ) -> Optional[ExchangeMetadata]:
        """최적의 거래소 구현체 선택
        
        Args:
            market_type: 'spot' 또는 'futures'
            exchange_name: 특정 거래소 선호 (예: 'binance')
            prefer_custom: 커스텀 구현 우선 선택
        """
        logger.debug(f"🔍 최적 구현체 검색: market_type={market_type}, exchange_name={exchange_name}, prefer_custom={prefer_custom}")
        
        candidates = self.list_exchanges(market_type=market_type)
        
        logger.debug(f"📊 후보 구현체 {len(candidates)}개 발견:")
        for i, candidate in enumerate(candidates):
            logger.debug(f"  {i+1}. {candidate.display_name} (타입: {candidate.exchange_type.value}, 우선순위: {candidate.priority}, 마켓: {candidate.supported_markets})")
        
        if not candidates:
            logger.warning(f"⚠️ 사용 가능한 거래소 구현체 없음 (market_type={market_type})")
            # 모든 등록된 거래소 출력
            all_exchanges = list(self._exchanges.values())
            logger.debug(f"📋 전체 등록된 거래소 {len(all_exchanges)}개:")
            for i, ex in enumerate(all_exchanges):
                logger.debug(f"  {i+1}. {ex.display_name} (마켓: {ex.supported_markets})")
            return None
        
        # exchange_name 지정된 경우 해당 거래소만 필터링
        if exchange_name:
            original_count = len(candidates)
            candidates = [c for c in candidates if exchange_name.lower() in c.name.lower()]
            logger.debug(f"🔍 {exchange_name} 필터링: {original_count} → {len(candidates)}개")
        
        if not candidates:
            logger.debug(f"⚠️ {exchange_name}에 해당하는 구현체 없음")
            return None
        
        # 커스텀 구현 우선 선택
        if prefer_custom:
            custom_candidates = [c for c in candidates if c.exchange_type == ExchangeType.CUSTOM]
            if custom_candidates:
                selected = custom_candidates[0]
                logger.debug(f"✅ 커스텀 구현체 선택: {selected.display_name}")
                return selected
            else:
                logger.debug(f"⚠️ 커스텀 구현체 없음, 기본 구현체 사용")
        
        # 우선순위 기반 선택 (높은 우선순위 → CUSTOM → CCXT 순)
        sorted_candidates = sorted(candidates, key=lambda x: (x.priority, x.exchange_type == ExchangeType.CUSTOM), reverse=True)
        selected = sorted_candidates[0]
        
        logger.debug(f"✅ 최적 구현체 선택: {selected.display_name} (타입: {selected.exchange_type.value}, 우선순위: {selected.priority})")
        return selected
    
    def create_instance(
        self, 
        name: str, 
        api_key: str, 
        api_secret: str,
        testnet: bool = False,
        **kwargs
    ) -> Any:
        """거래소 인스턴스 생성
        
        Args:
            name: 등록된 거래소 이름
            api_key: API 키
            api_secret: API 시크릿
            testnet: 테스트넷 사용 여부
        """
        metadata = self.get_exchange(name)
        if not metadata:
            raise ValueError(f"등록되지 않은 거래소: {name}")
        
        instance_key = f"{name}_{api_key[:8]}_{testnet}"
        
        # 인스턴스 캐시 확인
        if instance_key in self._instances:
            return self._instances[instance_key]
        
        # 새 인스턴스 생성
        if metadata.exchange_type == ExchangeType.CUSTOM:
            if not metadata.implementation_class:
                raise ValueError(f"커스텀 거래소 {name}의 구현 클래스가 없음")
            
            instance = metadata.implementation_class(api_key, api_secret, testnet=testnet, **kwargs)
            
        elif metadata.exchange_type == ExchangeType.CCXT:
            if not metadata.ccxt_id:
                raise ValueError(f"CCXT 거래소 {name}의 ccxt_id가 없음")
            
            # CCXT Adapter 사용
            from .factory import ExchangeFactory
            # market_type은 metadata.supported_markets에서 첫 번째 것 사용
            market_type = metadata.supported_markets[0] if metadata.supported_markets else 'spot'
            instance = ExchangeFactory.create_exchange(
                metadata.ccxt_id, market_type, api_key, api_secret, testnet=testnet
            )
        else:
            raise ValueError(f"지원되지 않는 거래소 타입: {metadata.exchange_type}")
        
        # 초기화 훅 실행
        for hook in self._initialization_hooks:
            hook(instance, metadata)
        
        # 인스턴스 캐시
        self._instances[instance_key] = instance
        
        logger.info(f"📡 거래소 인스턴스 생성: {metadata.display_name} (testnet={testnet})")
        return instance
    
    def add_initialization_hook(self, hook: Callable[[Any, ExchangeMetadata], None]):
        """인스턴스 초기화 시 실행할 훅 추가"""
        self._initialization_hooks.append(hook)
    
    def set_default(self, name: str):
        """기본 거래소 설정"""
        if name not in self._exchanges:
            raise ValueError(f"등록되지 않은 거래소: {name}")
        self._default_exchange = name
        logger.info(f"🎯 기본 거래소 설정: {self._exchanges[name].display_name}")
    
    def get_default(self) -> Optional[ExchangeMetadata]:
        """기본 거래소 조회"""
        return self._exchanges.get(self._default_exchange) if self._default_exchange else None
    
    def get_stats(self) -> Dict[str, Any]:
        """레지스트리 통계"""
        stats = {
            'total_exchanges': len(self._exchanges),
            'active_instances': len(self._instances),
            'by_type': {},
            'by_status': {},
            'capabilities_summary': {}
        }
        
        for metadata in self._exchanges.values():
            # 타입별 통계
            type_key = metadata.exchange_type.value
            stats['by_type'][type_key] = stats['by_type'].get(type_key, 0) + 1
            
            # 상태별 통계
            status_key = metadata.status
            stats['by_status'][status_key] = stats['by_status'].get(status_key, 0) + 1
            
            # 기능별 통계
            capabilities = metadata.capabilities
            for attr_name in dir(capabilities):
                if not attr_name.startswith('_') and isinstance(getattr(capabilities, attr_name), bool):
                    if getattr(capabilities, attr_name):
                        stats['capabilities_summary'][attr_name] = stats['capabilities_summary'].get(attr_name, 0) + 1
        
        return stats
    
    def clear_cache(self, name: Optional[str] = None):
        """인스턴스 캐시 정리"""
        if name:
            keys_to_remove = [k for k in self._instances.keys() if k.startswith(f"{name}_")]
            for key in keys_to_remove:
                del self._instances[key]
            logger.info(f"🧹 {name} 인스턴스 캐시 정리 완료")
        else:
            self._instances.clear()
            logger.info("🧹 모든 인스턴스 캐시 정리 완료")
    
    def _register_basic_ccxt_exchanges(self):
        """CCXT 제거됨 - Native 구현만 사용"""
        pass

# 전역 레지스트리 인스턴스
exchange_registry = ExchangeRegistry()

# Native 구현체 등록
def _register_native_implementations():
    """Native 구현체들을 Registry에 등록"""
    try:
        from .binance.spot import BinanceSpot
        from .binance.futures import BinanceFutures
        
        # Binance Spot Native 구현 등록
        exchange_registry.register(
            name="binance_spot_native",
            display_name="Binance Spot (Native)",
            exchange_type=ExchangeType.CUSTOM,
            capabilities=ExchangeCapability(
                spot_trading=True,
                futures_trading=False,
                margin_trading=False,
                websocket_support=False,
                advanced_orders=True,
                position_management=False,
                funding_rates=False,
                historical_data=True
            ),
            supported_markets=["spot"],
            api_endpoints={"spot": "https://api.binance.com"},
            rate_limits={"spot": {"requests_per_minute": 1200, "weight_per_minute": 6000}},
            implementation_class=BinanceSpot,
            priority=100,  # 높은 우선순위
            status="active"
        )
        
        # Binance Futures Native 구현 등록
        exchange_registry.register(
            name="binance_futures_native",
            display_name="Binance Futures (Native)",
            exchange_type=ExchangeType.CUSTOM,
            capabilities=ExchangeCapability(
                spot_trading=False,
                futures_trading=True,
                margin_trading=True,
                websocket_support=False,
                advanced_orders=True,
                position_management=True,
                funding_rates=True,
                historical_data=True
            ),
            supported_markets=["futures"],
            api_endpoints={"futures": "https://fapi.binance.com"},
            rate_limits={"futures": {"requests_per_minute": 2400, "weight_per_minute": 6000}},
            implementation_class=BinanceFutures,
            priority=100,  # 높은 우선순위
            status="active"
        )
        
        logger.info("✅ Native 구현체 등록 완료: Binance Spot, Futures")
        
    except ImportError as e:
        logger.warning(f"⚠️ Native 구현체 가져오기 실패: {e}")
    except Exception as e:
        logger.error(f"❌ Native 구현체 등록 실패: {e}")

# 자동 초기화
def initialize_registry() -> ExchangeRegistry:
    """레지스트리 초기화 및 자동 발견"""
    if not exchange_registry._exchanges:
        # Native 구현체 먼저 등록
        _register_native_implementations()
        
        try:
            exchange_registry.auto_discover()
        except Exception as e:
            logger.warning(f"⚠️ Auto-discover 실패, 수동 등록으로 진행: {e}")
            # 기본 CCXT 구현체들만 수동 등록
            # CCXT 기본 구현체 등록 (수동)
            exchange_registry._register_basic_ccxt_exchanges()
        
        # 환경 변수에 따른 기본 거래소 설정
        prefer_custom = os.getenv('USE_CUSTOM_EXCHANGE', 'false').lower() == 'true'
        
        if prefer_custom:
            # 커스텀 구현 우선 설정
            best_spot = exchange_registry.find_best_exchange('spot', prefer_custom=True)
            if best_spot:
                exchange_registry.set_default(best_spot.name)
        
        logger.info("🚀 Exchange Registry 초기화 완료")
    
    return exchange_registry

# 모듈 로드 시 자동 초기화
exchange_registry = initialize_registry()