#!/usr/bin/env python3
"""
Enhanced Exchange Factory

Registry 시스템과 통합된 차세대 Exchange Factory
- 레지스트리 기반 자동 선택
- Service Layer 통합
- CCXT 완벽 호환
- 설정 기반 동적 라우팅
- 모니터링 및 메트릭 수집
"""

import os
import logging
import time
from typing import Dict, Any, Optional, Union, Type, List
from dataclasses import dataclass
from contextlib import asynccontextmanager
from functools import wraps

from .registry import exchange_registry, ExchangeMetadata, ExchangeType
from .config import config_manager, should_use_custom_exchange, is_testnet_enabled
from .services import ServiceFactory, ServiceContext, MarketDataService, AccountService, TradingService
from .factory import ExchangeFactory as LegacyFactory  # 기존 팩토리 유지
from .interfaces import AsyncExchangeInterface
from .sync_wrapper import SyncExchangeWrapper

logger = logging.getLogger(__name__)

@dataclass
class ExchangeCreationStats:
    """거래소 생성 통계"""
    total_created: int = 0
    custom_created: int = 0
    ccxt_created: int = 0
    creation_errors: int = 0
    avg_creation_time_ms: float = 0.0

class EnhancedExchangeFactory:
    """향상된 거래소 팩토리"""
    
    def __init__(self):
        self._creation_stats = ExchangeCreationStats()
        self._instance_cache: Dict[str, Any] = {}
        self._service_cache: Dict[str, Dict[str, Any]] = {}
        
    def create_exchange(
        self,
        exchange_name: str = "binance",
        market_type: str = "spot",
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        testnet: Optional[bool] = None,
        prefer_custom: Optional[bool] = None,
        **kwargs
    ) -> Any:
        """
        거래소 인스턴스 생성 (레지스트리 기반)
        
        Args:
            exchange_name: 거래소 이름
            market_type: 'spot' 또는 'futures' 
            api_key: API 키
            api_secret: API 시크릿
            testnet: 테스트넷 사용 여부 (None이면 설정에서 자동 결정)
            prefer_custom: 커스텀 구현 선호 여부 (None이면 설정에서 자동 결정)
        """
        start_time = time.time()
        
        try:
            # 설정 기반 자동 결정
            if testnet is None:
                testnet = is_testnet_enabled(exchange_name)
            
            if prefer_custom is None:
                prefer_custom = should_use_custom_exchange(exchange_name)
            
            # 캐시 키 생성
            cache_key = f"{exchange_name}_{market_type}_{api_key[:8] if api_key else 'public'}_{testnet}_{prefer_custom}"
            
            # 캐시된 인스턴스 확인
            if cache_key in self._instance_cache:
                logger.debug(f"📈 Exchange 인스턴스 캐시 히트: {cache_key}")
                return self._instance_cache[cache_key]
            
            # 레지스트리에서 최적 구현체 선택
            logger.debug(f"🎯 구현체 검색: {exchange_name}, {market_type}, prefer_custom={prefer_custom}")
            metadata = exchange_registry.find_best_exchange(
                market_type=market_type,
                exchange_name=exchange_name,
                prefer_custom=prefer_custom
            )
            
            if metadata:
                logger.info(f"✅ 선택된 구현체: {metadata.display_name} (타입: {metadata.exchange_type.value})")
            else:
                logger.warning(f"❌ 적합한 구현체를 찾을 수 없음: {exchange_name}_{market_type}")
            
            if not metadata:
                # 폴백: 레거시 팩토리 사용
                logger.warning(f"⚠️ 레지스트리에서 구현체 없음, 레거시 팩토리로 폴백: {exchange_name}")
                instance = LegacyFactory.create_exchange(
                    exchange_name, market_type, api_key, api_secret, testnet, **kwargs
                )
                self._creation_stats.ccxt_created += 1
            else:
                # 레지스트리 기반 인스턴스 생성
                instance = exchange_registry.create_instance(
                    name=metadata.name,
                    api_key=api_key or "",
                    api_secret=api_secret or "",
                    testnet=testnet,
                    **kwargs
                )
                
                # Native 비동기 구현체는 SyncWrapper로 감싸기
                if metadata.exchange_type == ExchangeType.CUSTOM and isinstance(instance, AsyncExchangeInterface):
                    instance = SyncExchangeWrapper(instance)
                    logger.debug(f"🔄 Native async 구현체를 SyncWrapper로 래핑: {metadata.name}")
                    self._creation_stats.custom_created += 1
                else:
                    self._creation_stats.ccxt_created += 1
            
            # 인스턴스 캐시
            self._instance_cache[cache_key] = instance
            
            # 통계 업데이트
            creation_time = (time.time() - start_time) * 1000
            self._creation_stats.total_created += 1
            self._creation_stats.avg_creation_time_ms = (
                (self._creation_stats.avg_creation_time_ms * (self._creation_stats.total_created - 1) + creation_time) 
                / self._creation_stats.total_created
            )
            
            logger.info(
                f"🏭 Exchange 인스턴스 생성: {metadata.display_name if metadata else f'{exchange_name} (legacy)'} "
                f"({creation_time:.1f}ms)"
            )
            
            return instance
            
        except Exception as e:
            self._creation_stats.creation_errors += 1
            logger.error(f"❌ Exchange 인스턴스 생성 실패: {exchange_name} - {e}")
            raise
    
    def create_service_context(
        self,
        exchange_name: str = "binance",
        market_type: str = "spot", 
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        user_id: Optional[str] = None,
        **kwargs
    ) -> ServiceContext:
        """서비스 컨텍스트 생성"""
        return ServiceContext(
            user_id=user_id,
            exchange_name=exchange_name,
            market_type=market_type,
            testnet=is_testnet_enabled(exchange_name),
            api_key=api_key,
            api_secret=api_secret,
            **kwargs
        )
    
    def create_market_data_service(
        self,
        exchange_name: str = "binance",
        market_type: str = "spot",
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        **kwargs
    ) -> MarketDataService:
        """MarketDataService 생성"""
        context = self.create_service_context(
            exchange_name=exchange_name,
            market_type=market_type,
            api_key=api_key,
            api_secret=api_secret,
            **kwargs
        )
        return ServiceFactory.create_market_data_service(context)
    
    def create_account_service(
        self,
        api_key: str,
        api_secret: str,
        exchange_name: str = "binance",
        market_type: str = "spot",
        **kwargs
    ) -> AccountService:
        """AccountService 생성 (인증 필요)"""
        context = self.create_service_context(
            exchange_name=exchange_name,
            market_type=market_type,
            api_key=api_key,
            api_secret=api_secret,
            **kwargs
        )
        return ServiceFactory.create_account_service(context)
    
    def create_trading_service(
        self,
        api_key: str,
        api_secret: str,
        exchange_name: str = "binance",
        market_type: str = "spot",
        **kwargs
    ) -> TradingService:
        """TradingService 생성 (인증 필요)"""
        context = self.create_service_context(
            exchange_name=exchange_name,
            market_type=market_type,
            api_key=api_key,
            api_secret=api_secret,
            **kwargs
        )
        return ServiceFactory.create_trading_service(context)
    
    def create_all_services(
        self,
        api_key: str,
        api_secret: str,
        exchange_name: str = "binance",
        market_type: str = "spot",
        **kwargs
    ) -> Dict[str, Any]:
        """모든 서비스 생성"""
        context = self.create_service_context(
            exchange_name=exchange_name,
            market_type=market_type,
            api_key=api_key,
            api_secret=api_secret,
            **kwargs
        )
        return ServiceFactory.create_all_services(context)
    
    @asynccontextmanager
    async def exchange_session(
        self,
        exchange_name: str = "binance",
        market_type: str = "spot",
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        **kwargs
    ):
        """거래소 세션 관리 (컨텍스트 매니저)"""
        instance = None
        try:
            instance = self.create_exchange(
                exchange_name=exchange_name,
                market_type=market_type,
                api_key=api_key,
                api_secret=api_secret,
                **kwargs
            )
            yield instance
        finally:
            # 필요시 정리 작업
            if hasattr(instance, 'close') and callable(instance.close):
                try:
                    await instance.close()
                except:
                    pass
    
    def get_creation_stats(self) -> Dict[str, Any]:
        """생성 통계 조회"""
        stats_dict = {
            'total_created': self._creation_stats.total_created,
            'custom_created': self._creation_stats.custom_created,
            'ccxt_created': self._creation_stats.ccxt_created,
            'creation_errors': self._creation_stats.creation_errors,
            'avg_creation_time_ms': round(self._creation_stats.avg_creation_time_ms, 2),
            'cached_instances': len(self._instance_cache),
            'custom_usage_percentage': (
                (self._creation_stats.custom_created / max(self._creation_stats.total_created, 1)) * 100
            )
        }
        return stats_dict
    
    def clear_cache(self, pattern: Optional[str] = None):
        """인스턴스 캐시 정리"""
        if pattern:
            keys_to_remove = [k for k in self._instance_cache.keys() if pattern in k]
            for key in keys_to_remove:
                self._instance_cache.pop(key, None)
            logger.info(f"🧹 Exchange 캐시 정리: {pattern} ({len(keys_to_remove)}개)")
        else:
            self._instance_cache.clear()
            self._service_cache.clear()
            logger.info("🧹 모든 Exchange 캐시 정리")
    
    def health_check(self) -> Dict[str, Any]:
        """팩토리 상태 확인"""
        config = config_manager.load_config()
        registry_stats = exchange_registry.get_stats()
        creation_stats = self.get_creation_stats()
        
        return {
            'status': 'healthy',
            'config': {
                'custom_exchange_enabled': config.features.use_custom_exchange,
                'migration_phase': config.migration.phase.value,
                'rollout_percentage': config.migration.rollout_percentage
            },
            'registry': registry_stats,
            'creation': creation_stats,
            'recommendations': self._get_health_recommendations(config, registry_stats, creation_stats)
        }
    
    def _get_health_recommendations(self, config: Any, registry_stats: Dict, creation_stats: Dict) -> List[str]:
        """상태 기반 권고사항"""
        recommendations = []
        
        if creation_stats['creation_errors'] > 0:
            recommendations.append(f"❌ 생성 오류 {creation_stats['creation_errors']}건 발생, 로그 확인 필요")
        
        if creation_stats['avg_creation_time_ms'] > 1000:
            recommendations.append("⚠️ 평균 생성 시간이 1초 초과, 성능 최적화 검토 필요")
        
        if config.features.use_custom_exchange and creation_stats['custom_usage_percentage'] < 50:
            recommendations.append("📈 커스텀 Exchange 활성화됨, 사용률 확인 필요")
        
        if len(self._instance_cache) > 100:
            recommendations.append("🧹 캐시된 인스턴스 수가 많음, 정리 고려 필요")
        
        if not recommendations:
            recommendations.append("✅ 모든 지표가 정상 범위")
        
        return recommendations

# 전역 Enhanced Factory 인스턴스
enhanced_factory = EnhancedExchangeFactory()

# 편의 함수들
def create_exchange(
    exchange_name: str = "binance",
    market_type: str = "spot", 
    api_key: Optional[str] = None,
    api_secret: Optional[str] = None,
    **kwargs
) -> Any:
    """거래소 인스턴스 생성 (전역 함수)"""
    return enhanced_factory.create_exchange(
        exchange_name=exchange_name,
        market_type=market_type,
        api_key=api_key,
        api_secret=api_secret,
        **kwargs
    )

def create_market_data_service(
    exchange_name: str = "binance",
    market_type: str = "spot",
    **kwargs
) -> MarketDataService:
    """MarketDataService 생성 (전역 함수)"""
    return enhanced_factory.create_market_data_service(
        exchange_name=exchange_name,
        market_type=market_type,
        **kwargs
    )

def create_trading_service(
    api_key: str,
    api_secret: str,
    exchange_name: str = "binance",
    market_type: str = "spot",
    **kwargs
) -> TradingService:
    """TradingService 생성 (전역 함수)"""
    return enhanced_factory.create_trading_service(
        api_key=api_key,
        api_secret=api_secret,
        exchange_name=exchange_name,
        market_type=market_type,
        **kwargs
    )

# 호환성을 위한 데코레이터
def with_exchange_monitoring(func):
    """Exchange 사용 모니터링 데코레이터"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = await func(*args, **kwargs)
            execution_time = (time.time() - start_time) * 1000
            logger.debug(f"📊 Exchange 함수 실행: {func.__name__} ({execution_time:.1f}ms)")
            return result
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            logger.error(f"❌ Exchange 함수 실행 실패: {func.__name__} ({execution_time:.1f}ms) - {e}")
            raise
    return wrapper