# Services package

# Services module

"""
서비스 모듈 초기화 - 완전한 의존성 주입 시스템
ServiceContainer를 통한 체계적인 서비스 관리
"""

import logging
import os
from typing import Dict, Any

logger = logging.getLogger(__name__)


def initialize_services() -> Dict[str, Any]:
    """
    완전한 의존성 주입 시스템을 통한 서비스 초기화
    """
    try:
        # ServiceContainer import
        from app.services.service_container import container
        from app.services.di_health_check import health_checker
        from app.services.migration_monitor import migration_monitor

        logger.info("🚀 의존성 주입 기반 서비스 초기화 시작")

        # === Phase 1: 서비스 팩토리 등록 ===
        _register_service_factories(container)

        # === Phase 2: 모든 서비스 초기화 ===
        initialization_result = container.initialize_all_services()

        # === Phase 3: 후처리 및 검증 ===
        services = container.get_all_services()
        health_result = health_checker.run_comprehensive_check()

        # === Phase 4: 결과 정리 ===
        result = {
            'success': initialization_result['success'],
            'services': services,
            'initialization_details': initialization_result,
            'health_check': health_result,
            'container': container,
            'health_checker': health_checker,
            'migration_monitor': migration_monitor
        }

        # 성공/실패 로깅
        if initialization_result['success']:
            logger.info(f"✅ 의존성 주입 시스템 초기화 완료")
            logger.info(f"  - 초기화된 서비스: {len(initialization_result['initialized_services'])}")
            logger.info(f"  - 실패한 서비스: {len(initialization_result['failed_services'])}")
            logger.info(f"  - 전체 상태: {health_result['overall_health']}")

            if initialization_result['failed_services']:
                logger.warning(f"  - 실패한 서비스 목록: {initialization_result['failed_services']}")
        else:
            logger.error("❌ 의존성 주입 시스템 초기화 실패")
            logger.error(f"  - 오류 세부사항: {initialization_result.get('error_details', {})}")

        return result

    except Exception as e:
        logger.error(f"❌ 의존성 주입 시스템 초기화 중 치명적 오류: {e}")

        # 폴백: 기존 방식으로 초기화
        logger.info("🔄 폴백: 기존 방식으로 서비스 초기화")
        return _initialize_services_legacy()


def _register_service_factories(container):
    """모든 서비스 팩토리를 컨테이너에 등록"""

    # === Layer 1: 기본 유틸리티 (의존성 없음) ===

    def create_precision_cache_service():
        from app.services.precision_cache_service import precision_cache_service
        return precision_cache_service

    def create_rate_limit_service():
        from app.services.rate_limit_service import rate_limit_service
        return rate_limit_service

    container.register_service('precision_cache_service', create_precision_cache_service)
    container.register_service('rate_limit_service', create_rate_limit_service)

    # === Layer 2: 연결 서비스 ===

    def create_exchange_adapter_factory():
        from app.services.exchange_adapter_factory import exchange_adapter_factory
        return exchange_adapter_factory

    container.register_service('exchange_adapter_factory', create_exchange_adapter_factory)

    # === Layer 3: 실행 서비스 ===

    def create_order_execution_service():
        from app.services.order_execution_service import order_execution_service
        return order_execution_service

    container.register_service('order_execution_service', create_order_execution_service)

    # === Layer 4: 복합 서비스 ===

    def create_new_exchange_service():
        from app.services.new_exchange_service import new_exchange_service
        return new_exchange_service

    container.register_service('new_exchange_service', create_new_exchange_service)

    # === Layer 5: 어댑터 레이어 ===

    def create_exchange_service_adapter(new_exchange_service):
        from app.services.adapters import create_exchange_service_adapter

        # 레거시 서비스도 시도해서 가져오기
        legacy_service = None
        try:
            from app.services.exchange_service import exchange_service
            legacy_service = exchange_service
        except ImportError:
            logger.debug("레거시 exchange_service를 가져올 수 없습니다")

        return create_exchange_service_adapter(new_exchange_service, legacy_service)

    container.register_service('exchange_service_adapter', create_exchange_service_adapter,
                             ['new_exchange_service'])

    # === Layer 6: 이벤트 및 알림 서비스 ===

    def create_event_service():
        try:
            from app.services.event_service import event_service
            return event_service
        except ImportError:
            logger.debug("event_service를 가져올 수 없습니다")
            return None

    def create_telegram_service():
        try:
            from app.services.telegram_service import telegram_service
            return telegram_service
        except ImportError:
            logger.debug("telegram_service를 가져올 수 없습니다")
            return None

    container.register_service('event_service', create_event_service)
    container.register_service('telegram_service', create_telegram_service)

    # === Layer 6.5: 보안 서비스 ===

    def create_security_service():
        from app.services.security_service import security_service
        return security_service

    container.register_service('security_service', create_security_service)

    # === Layer 7: 핵심 비즈니스 로직 ===

    def create_unified_order_service(new_exchange_service):
        from app.services.unified_order_service import unified_order_service
        unified_order_service.set_exchange_service(new_exchange_service)
        return unified_order_service

    def create_trading_service():
        from app.services.trading_service import trading_service
        return trading_service

    def create_position_service():
        from app.services.position_service import position_service
        return position_service

    container.register_service('unified_order_service', create_unified_order_service,
                             ['new_exchange_service'])
    container.register_service('trading_service', create_trading_service)
    container.register_service('position_service', create_position_service)

    # === Layer 8: 오케스트레이터 ===

    def create_trading_orchestrator(trading_service, position_service):
        from app.services.trading_orchestrator import trading_orchestrator
        trading_orchestrator.set_services(trading_service, position_service)

        # trading_service에도 orchestrator 설정
        trading_service.set_orchestrator(trading_orchestrator)

        return trading_orchestrator

    container.register_service('trading_orchestrator', create_trading_orchestrator,
                             ['trading_service', 'position_service'])


def _initialize_services_legacy():
    """폴백용 레거시 초기화 방식"""
    try:
        from app.services.trading_service import trading_service
        from app.services.position_service import position_service
        from app.services.trading_orchestrator import trading_orchestrator

        # 기본적인 의존성만 설정
        trading_orchestrator.set_services(trading_service, position_service)
        trading_service.set_orchestrator(trading_orchestrator)

        logger.info("✅ 레거시 방식으로 기본 서비스 초기화 완료")

        return {
            'success': True,
            'services': {
                'trading_service': trading_service,
                'position_service': position_service,
                'trading_orchestrator': trading_orchestrator
            },
            'mode': 'legacy'
        }

    except Exception as e:
        logger.error(f"❌ 레거시 초기화도 실패: {e}")
        return {
            'success': False,
            'error': str(e),
            'mode': 'failed'
        }


# 이전 버전과의 호환성을 위한 별칭
def initialize_services_v1():
    """이전 버전 호환성을 위한 래퍼"""
    result = initialize_services()
    return result.get('services', {}) 