#!/usr/bin/env python3
"""
Exchange Configuration Management

환경별 설정 관리 및 Feature Flag 시스템
- 개발/스테이징/프로덕션 환경 분리
- 런타임 설정 변경 지원
- Feature Flag 기반 점진적 마이그레이션
- 설정 검증 및 기본값 관리
"""

import os
import json
import logging
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
import threading
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    딕셔너리를 깊이 병합하는 함수
    override의 값이 base의 값을 덮어씀
    """
    result = base.copy()
    
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    
    return result

class Environment(Enum):
    """실행 환경"""
    DEVELOPMENT = "development"
    PRODUCTION = "production"

@dataclass
class PerformanceSettings:
    """성능 관련 설정"""
    cache_ttl_seconds: int = 300  # 5분
    rate_limit_buffer: float = 0.8  # 80% 사용
    connection_pool_size: int = 10
    request_timeout_seconds: int = 30
    retry_attempts: int = 3
    retry_delay_seconds: float = 1.0
    enable_http_keep_alive: bool = True

@dataclass
class FeatureFlags:
    """기능 플래그"""
    use_custom_exchange: bool = False
    enable_advanced_caching: bool = True
    enable_websocket: bool = False
    enable_parallel_requests: bool = True
    enable_circuit_breaker: bool = True
    enable_detailed_logging: bool = False
    enable_metrics_collection: bool = True
    enable_automatic_failover: bool = False

@dataclass
class ExchangeSettings:
    """거래소별 설정"""
    preferred_implementation: str = "native"  # native only
    fallback_implementation: str = "native"
    rate_limit_mode: str = "conservative"  # conservative, aggressive, adaptive
    market_data_source: str = "primary"  # primary, fallback, hybrid
    order_execution_mode: str = "safe"  # safe, fast, balanced


@dataclass
class SecuritySettings:
    """보안 관련 설정"""
    encrypt_api_keys: bool = True
    api_key_rotation_days: int = 90
    rate_limit_enforcement: bool = True
    whitelist_enabled: bool = False
    allowed_ips: List[str] = field(default_factory=list)
    audit_logging: bool = True

@dataclass
class ExchangeConfig:
    """통합 거래소 설정"""
    environment: Environment = Environment.DEVELOPMENT
    performance: PerformanceSettings = field(default_factory=PerformanceSettings)
    features: FeatureFlags = field(default_factory=FeatureFlags)
    exchanges: Dict[str, ExchangeSettings] = field(default_factory=dict)
    security: SecuritySettings = field(default_factory=SecuritySettings)
    
    def __post_init__(self):
        """초기화 후 기본값 설정"""
        if not self.exchanges:
            self.exchanges["binance"] = ExchangeSettings()

class ConfigurationManager:
    """설정 관리자"""
    
    def __init__(self, config_dir: Optional[str] = None):
        self.config_dir = Path(config_dir) if config_dir else Path(__file__).parent / "configs"
        self.config_dir.mkdir(exist_ok=True)
        
        self._config: Optional[ExchangeConfig] = None
        self._config_lock = threading.RLock()
        self._watchers: List[callable] = []
        self._last_loaded = datetime.now()
        
        # 환경 감지
        self.environment = self._detect_environment()
        
    def _detect_environment(self) -> Environment:
        """현재 실행 환경 감지"""
        env_name = os.getenv('ENVIRONMENT', os.getenv('ENV', 'development')).lower()
        
        env_mapping = {
            'dev': Environment.DEVELOPMENT,
            'development': Environment.DEVELOPMENT,
            'prod': Environment.PRODUCTION,
            'production': Environment.PRODUCTION
        }
        
        return env_mapping.get(env_name, Environment.DEVELOPMENT)
    
    def get_config_file_path(self) -> Path:
        """환경별 설정 파일 경로"""
        return self.config_dir / f"exchange_config_{self.environment.value}.json"
    
    def get_base_config_file_path(self) -> Path:
        """기본 설정 파일 경로"""
        return self.config_dir / "base.json"
    
    def load_base_config(self) -> Dict[str, Any]:
        """기본 설정 로드"""
        base_config_file = self.get_base_config_file_path()
        
        if base_config_file.exists():
            try:
                with open(base_config_file, 'r', encoding='utf-8') as f:
                    base_config = json.load(f)
                logger.debug(f"✅ 기본 설정 로드 완료: {base_config_file}")
                return base_config
            except Exception as e:
                logger.warning(f"⚠️ 기본 설정 로드 실패: {base_config_file} - {e}")
        
        # 기본 설정이 없으면 빈 딕셔너리 반환
        return {}
    
    def load_config(self, reload: bool = False) -> ExchangeConfig:
        """계층적 설정 로드 (base.json + 환경별 설정 + 환경 변수)"""
        with self._config_lock:
            if self._config and not reload:
                return self._config
            
            try:
                # 1단계: 기본 설정 로드
                base_config = self.load_base_config()
                logger.debug(f"📋 기본 설정 로드됨: {list(base_config.keys())}")
                
                # 2단계: 환경별 설정 로드
                config_file = self.get_config_file_path()
                env_config = {}
                
                if config_file.exists():
                    with open(config_file, 'r', encoding='utf-8') as f:
                        env_config = json.load(f)
                    logger.debug(f"🌍 환경별 설정 로드됨: {config_file}")
                else:
                    logger.warning(f"⚠️ 환경별 설정 파일 없음: {config_file}")
                
                # 3단계: 설정 병합 (base <- env)
                merged_config = deep_merge(base_config, env_config)
                logger.debug(f"🔄 설정 병합 완료")
                
                # 4단계: 환경 변수 오버라이드 적용
                final_config = self._apply_env_overrides(merged_config)
                
                # 5단계: 설정 객체 생성
                self._config = self._dict_to_config(final_config)
                logger.info(f"✅ 계층적 설정 로드 완료 - 환경: {self.environment.value}")
                
            except Exception as e:
                logger.error(f"❌ 설정 로드 실패 - {e}")
                self._config = self._create_default_config()
                self.save_config()  # 기본 설정 파일 생성
            
            # 설정 검증
            self._validate_config()
            
            # 환경별 설정 조정
            self._adjust_config_for_environment()
            
            self._last_loaded = datetime.now()
            
            # 감시자들에게 알림
            for watcher in self._watchers:
                try:
                    watcher(self._config)
                except Exception as e:
                    logger.error(f"❌ 설정 감시자 실행 오류: {e}")
            
            return self._config
    
    def _create_default_config(self) -> ExchangeConfig:
        """기본 설정 생성"""
        config = ExchangeConfig(environment=self.environment)
        
        # 환경별 기본 설정
        if self.environment == Environment.PRODUCTION:
            config.features.use_custom_exchange = True
            config.features.enable_detailed_logging = False
            config.security.audit_logging = True
        else:  # DEVELOPMENT
            config.features.use_custom_exchange = False
            config.features.enable_detailed_logging = True
            config.performance.cache_ttl_seconds = 60  # 짧은 캐시
        
        return config
    
    def _apply_env_overrides(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """환경 변수로 설정 오버라이드"""
        overrides = {
            'USE_CUSTOM_EXCHANGE': 'features.use_custom_exchange',
            'CACHE_TTL_SECONDS': 'performance.cache_ttl_seconds',
            'ENABLE_WEBSOCKET': 'features.enable_websocket',
        }
        
        for env_var, config_path in overrides.items():
            env_value = os.getenv(env_var)
            if env_value is not None:
                self._set_nested_value(config_data, config_path, self._convert_env_value(env_value))
        
        return config_data
    
    def _set_nested_value(self, data: Dict[str, Any], path: str, value: Any):
        """중첩된 딕셔너리에 값 설정"""
        keys = path.split('.')
        current = data
        
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        
        current[keys[-1]] = value
    
    def _convert_env_value(self, value: str) -> Any:
        """환경 변수 값을 적절한 타입으로 변환"""
        # Boolean 변환
        if value.lower() in ('true', 'false'):
            return value.lower() == 'true'
        
        # Integer 변환 시도
        try:
            return int(value)
        except ValueError:
            pass
        
        # Float 변환 시도
        try:
            return float(value)
        except ValueError:
            pass
        
        # 문자열 그대로 반환
        return value
    
    def _dict_to_config(self, data: Dict[str, Any]) -> ExchangeConfig:
        """딕셔너리를 설정 객체로 변환"""
        # 중첩된 객체들 먼저 변환
        if 'performance' in data:
            data['performance'] = PerformanceSettings(**data['performance'])
        if 'features' in data:
            data['features'] = FeatureFlags(**data['features'])
        if 'security' in data:
            data['security'] = SecuritySettings(**data['security'])
        if 'exchanges' in data:
            exchanges = {}
            for name, settings in data['exchanges'].items():
                exchanges[name] = ExchangeSettings(**settings)
            data['exchanges'] = exchanges
        
        # 환경 변환
        if 'environment' in data and isinstance(data['environment'], str):
            data['environment'] = Environment(data['environment'])
        
        return ExchangeConfig(**data)
    
    def _validate_config(self):
        """설정 유효성 검증"""
        config = self._config
        
        # 성능 설정 검증
        if config.performance.cache_ttl_seconds < 0:
            logger.warning("⚠️ cache_ttl_seconds는 0 이상이어야 함")
            config.performance.cache_ttl_seconds = 300
        
        # 보안 설정 검증
        if config.security.api_key_rotation_days < 1:
            logger.warning("⚠️ api_key_rotation_days는 1 이상이어야 함")
            config.security.api_key_rotation_days = 90
    
    def _adjust_config_for_environment(self):
        """환경별 설정 조정"""
        config = self._config
        
        if config.environment == Environment.PRODUCTION:
            # 프로덕션: 보수적 설정
            config.performance.rate_limit_buffer = 0.7
            config.performance.retry_attempts = 5
            config.features.enable_circuit_breaker = True
        elif config.environment == Environment.DEVELOPMENT:
            # 개발: 빠른 피드백
            config.performance.cache_ttl_seconds = min(config.performance.cache_ttl_seconds, 120)
            config.features.enable_detailed_logging = True
    
    def save_config(self, config: Optional[ExchangeConfig] = None):
        """설정 저장"""
        if config is None:
            config = self._config
        
        config_file = self.get_config_file_path()
        
        try:
            # 설정을 딕셔너리로 변환 (Enum 값도 문자열로)
            config_dict = asdict(config)
            
            # Enum 값들을 문자열로 변환
            config_dict['environment'] = config.environment.value
            
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config_dict, f, indent=2, ensure_ascii=False)
            
            logger.info(f"✅ 설정 저장 완료: {config_file}")
            
        except Exception as e:
            logger.error(f"❌ 설정 저장 실패: {config_file} - {e}")
    
    def update_config(self, updates: Dict[str, Any]):
        """설정 동적 업데이트"""
        with self._config_lock:
            config = self.load_config()
            
            for path, value in updates.items():
                self._set_nested_config_value(config, path, value)
            
            self._validate_config()
            self.save_config()
            
            logger.info(f"🔄 설정 업데이트 완료: {list(updates.keys())}")
    
    def _set_nested_config_value(self, config: ExchangeConfig, path: str, value: Any):
        """중첩된 설정 객체에 값 설정"""
        keys = path.split('.')
        current = config
        
        for key in keys[:-1]:
            if hasattr(current, key):
                current = getattr(current, key)
            elif isinstance(current, dict) and key in current:
                current = current[key]
            else:
                raise AttributeError(f"'{type(current).__name__}' object has no attribute '{key}'")
        
        # 마지막 키에 값 설정
        final_key = keys[-1]
        if hasattr(current, final_key):
            setattr(current, final_key, value)
        elif isinstance(current, dict):
            current[final_key] = value
        else:
            raise AttributeError(f"Cannot set '{final_key}' on '{type(current).__name__}' object")
    
    def add_config_watcher(self, callback: callable):
        """설정 변경 감시자 추가"""
        self._watchers.append(callback)
    
    def should_use_custom_exchange(self, exchange_name: str = "binance") -> bool:
        """커스텀 거래소 사용 여부 결정"""
        config = self.load_config()
        
        # Feature flag 확인
        return config.features.use_custom_exchange
    
    def get_exchange_preference(self, exchange_name: str) -> str:
        """거래소별 선호 구현체 조회"""
        config = self.load_config()
        
        if exchange_name in config.exchanges:
            return config.exchanges[exchange_name].preferred_implementation
        
        return "auto"  # 기본값
    
    def is_testnet_enabled(self, exchange_name: str = "binance") -> bool:
        """
        [DEPRECATED] 테스트넷 사용 여부
        
        이 함수는 더 이상 사용되지 않습니다. 
        testnet 설정은 이제 계좌별로 관리됩니다 (Account.is_testnet).
        """
        import warnings
        warnings.warn(
            "is_testnet_enabled()는 deprecated 되었습니다. 계좌별 is_testnet 필드를 사용하세요.",
            DeprecationWarning,
            stacklevel=2
        )
        # 기본적으로 False 반환
        return False

# 전역 설정 매니저
config_manager = ConfigurationManager()

# 편의 함수들
def get_config() -> ExchangeConfig:
    """현재 설정 조회"""
    return config_manager.load_config()

def should_use_custom_exchange(exchange_name: str = "binance") -> bool:
    """커스텀 거래소 사용 여부"""
    return config_manager.should_use_custom_exchange(exchange_name)

def is_testnet_enabled(exchange_name: str = "binance") -> bool:
    """
    [DEPRECATED] 테스트넷 사용 여부
    
    이 함수는 더 이상 사용되지 않습니다. 
    testnet 설정은 이제 계좌별로 관리됩니다 (Account.is_testnet).
    """
    return config_manager.is_testnet_enabled(exchange_name)

def enable_custom_exchange(enabled: bool = True):
    """커스텀 거래소 활성화/비활성화"""
    config_manager.update_config({
        'features.use_custom_exchange': enabled
    })