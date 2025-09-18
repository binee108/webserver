"""
의존성 주입 컨테이너
서비스 생명주기 및 의존성 관리
"""

import logging
from typing import Dict, Any, Optional, Type, Callable, List, Set
from collections import defaultdict, deque
import inspect
import os

logger = logging.getLogger(__name__)


class ServiceContainer:
    """의존성 주입 컨테이너"""

    def __init__(self):
        self._services: Dict[str, Any] = {}  # 인스턴스 저장
        self._service_factories: Dict[str, Callable] = {}  # 팩토리 함수
        self._dependencies: Dict[str, List[str]] = defaultdict(list)  # 의존성 그래프
        self._initialized: Set[str] = set()  # 초기화 완료 서비스들
        self._initializing: Set[str] = set()  # 초기화 중인 서비스들 (순환 의존성 감지용)
        self._fallback_enabled = True  # 폴백 모드 활성화

        # 초기화 단계별 그룹 정의 (토폴로지 정렬 기반)
        self._initialization_layers = [
            # Layer 1: 기본 유틸리티 (의존성 없음)
            ['precision_cache_service', 'rate_limit_service'],

            # Layer 2: 연결 서비스
            ['exchange_connection_service', 'exchange_adapter_factory'],

            # Layer 3: 실행 서비스
            ['order_execution_service'],

            # Layer 4: 복합 서비스
            ['new_exchange_service'],

            # Layer 5: 어댑터 레이어
            ['exchange_service_adapter'],

            # Layer 6: 이벤트 및 알림
            ['event_service', 'telegram_service'],

            # Layer 7: 핵심 비즈니스 로직
            ['unified_order_service', 'trading_service', 'position_service'],

            # Layer 8: 오케스트레이터
            ['trading_orchestrator']
        ]

    def register_service(self, name: str, factory: Callable, dependencies: List[str] = None):
        """서비스 등록"""
        self._service_factories[name] = factory
        if dependencies:
            self._dependencies[name] = dependencies
        logger.debug(f"서비스 등록: {name} (의존성: {dependencies or 'None'})")

    def get_service(self, name: str) -> Optional[Any]:
        """서비스 인스턴스 반환"""
        if name in self._services:
            return self._services[name]

        return self._create_service(name)

    def _create_service(self, name: str) -> Optional[Any]:
        """서비스 인스턴스 생성"""
        # 순환 의존성 감지
        if name in self._initializing:
            logger.error(f"순환 의존성 감지: {name}")
            return None

        if name not in self._service_factories:
            logger.warning(f"서비스 팩토리를 찾을 수 없음: {name}")
            return None

        try:
            self._initializing.add(name)

            # 의존성 먼저 생성
            dependencies = {}
            for dep_name in self._dependencies.get(name, []):
                dep_service = self.get_service(dep_name)
                if dep_service is None:
                    logger.error(f"의존성 서비스 생성 실패: {dep_name} (required by {name})")
                    if not self._fallback_enabled:
                        return None
                dependencies[dep_name] = dep_service

            # 서비스 생성
            factory = self._service_factories[name]

            # 팩토리 함수 시그니처 확인
            sig = inspect.signature(factory)
            if sig.parameters:
                # 의존성이 필요한 팩토리
                service = factory(**dependencies)
            else:
                # 의존성이 필요 없는 팩토리
                service = factory()

            if service is not None:
                self._services[name] = service
                self._initialized.add(name)
                logger.info(f"✅ 서비스 생성 완료: {name}")

            return service

        except Exception as e:
            logger.error(f"❌ 서비스 생성 실패: {name} - {e}")
            return None
        finally:
            self._initializing.discard(name)

    def initialize_all_services(self) -> Dict[str, Any]:
        """모든 서비스 초기화 (순서대로)"""
        results = {
            'success': True,
            'initialized_services': [],
            'failed_services': [],
            'total_services': 0,
            'error_details': {}
        }

        try:
            # 단계별 초기화
            for layer_index, layer_services in enumerate(self._initialization_layers):
                logger.info(f"🔄 Layer {layer_index + 1} 서비스 초기화 시작: {layer_services}")

                layer_results = self._initialize_layer(layer_services)

                results['initialized_services'].extend(layer_results['success'])
                results['failed_services'].extend(layer_results['failed'])
                results['error_details'].update(layer_results['errors'])

                logger.info(f"✅ Layer {layer_index + 1} 완료: 성공 {len(layer_results['success'])}, 실패 {len(layer_results['failed'])}")

            # 등록되었지만 layer에 없는 서비스들도 초기화
            remaining_services = set(self._service_factories.keys()) - set(results['initialized_services']) - set(results['failed_services'])
            if remaining_services:
                logger.info(f"🔄 남은 서비스들 초기화: {list(remaining_services)}")
                for service_name in remaining_services:
                    if self.get_service(service_name):
                        results['initialized_services'].append(service_name)
                    else:
                        results['failed_services'].append(service_name)

            results['total_services'] = len(self._service_factories)

            # 성공률 계산
            success_rate = len(results['initialized_services']) / max(results['total_services'], 1) * 100

            if results['failed_services']:
                results['success'] = False
                logger.warning(f"⚠️ 일부 서비스 초기화 실패: {results['failed_services']}")

            logger.info(f"🎯 서비스 초기화 완료: {len(results['initialized_services'])}/{results['total_services']} ({success_rate:.1f}%)")

        except Exception as e:
            logger.error(f"❌ 서비스 초기화 중 치명적 오류: {e}")
            results['success'] = False
            results['error_details']['critical_error'] = str(e)

        return results

    def _initialize_layer(self, layer_services: List[str]) -> Dict[str, Any]:
        """단일 레이어 서비스들 초기화"""
        results = {
            'success': [],
            'failed': [],
            'errors': {}
        }

        for service_name in layer_services:
            if service_name not in self._service_factories:
                logger.debug(f"서비스 팩토리 없음 (건너뜀): {service_name}")
                continue

            try:
                service = self.get_service(service_name)
                if service:
                    results['success'].append(service_name)
                else:
                    results['failed'].append(service_name)
                    results['errors'][service_name] = "서비스 생성 실패"
            except Exception as e:
                results['failed'].append(service_name)
                results['errors'][service_name] = str(e)
                logger.error(f"❌ {service_name} 초기화 실패: {e}")

        return results

    def get_all_services(self) -> Dict[str, Any]:
        """모든 초기화된 서비스 반환"""
        return self._services.copy()

    def get_service_health(self) -> Dict[str, Any]:
        """서비스 상태 확인"""
        health_info = {
            'total_registered': len(self._service_factories),
            'total_initialized': len(self._initialized),
            'initialization_rate': len(self._initialized) / max(len(self._service_factories), 1) * 100,
            'services': {}
        }

        for service_name in self._service_factories:
            status = 'initialized' if service_name in self._initialized else 'not_initialized'
            health_info['services'][service_name] = {
                'status': status,
                'dependencies': self._dependencies.get(service_name, []),
                'has_instance': service_name in self._services
            }

        return health_info

    def reset(self):
        """컨테이너 리셋"""
        self._services.clear()
        self._initialized.clear()
        self._initializing.clear()
        logger.info("🔄 서비스 컨테이너 리셋 완료")

    def enable_fallback_mode(self, enabled: bool = True):
        """폴백 모드 설정"""
        self._fallback_enabled = enabled
        logger.info(f"🔄 폴백 모드: {'활성화' if enabled else '비활성화'}")


# 전역 컨테이너 인스턴스
container = ServiceContainer()