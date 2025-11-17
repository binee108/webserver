"""
통합 서비스 패키지

1인 사용자를 위한 단순하고 효율적인 서비스 관리
복잡한 DI 컨테이너 제거, 직접적인 서비스 import 방식 채택

=== 서비스 의존성 계층 구조 ===

Level 1 (Infrastructure Layer): 외부 시스템 통합
  - exchange.py          : 거래소 API 통합
  - price_cache.py       : 가격 데이터 캐싱
  - symbol_validator.py  : 심볼 검증
  - telegram.py          : 텔레그램 알림
  - event_service.py     : SSE 이벤트 발행

Level 2 (Domain Layer): 핵심 비즈니스 로직
  - trading.py           : 거래 실행 및 관리 (6개 하위 모듈)
  - analytics.py         : 분석 및 통계
  - security.py          : 보안 및 인증
  - order_tracking.py    : 주문 추적
  - trade_record.py      : 거래 기록

Level 3 (Application Layer): 애플리케이션 서비스
  - webhook_service.py   : 웹훅 처리
  - strategy_service.py  : 전략 관리

의존성 규칙:
1. 상위 레벨 → 하위 레벨 의존만 허용
2. 동일 레벨 간 의존 최소화
3. Level 1은 다른 서비스 의존 금지 (외부 API만)
4. 순환 의존성 절대 금지
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


# @FEAT:exchange-service-initialization @COMP:service @TYPE:core
def initialize_services() -> Dict[str, Any]:
    """
    통합 서비스 초기화

    WHY 서비스 초기화 순서 재구성 (Issue #64 해결):
    - ExchangeService를 SymbolValidator보다 먼저 초기화
    - ExchangeService 초기화 실패 시 서비스 시작 중단
    - 의존성 관계 명확화 및 안정성 확보

    기존 복잡한 DI 시스템을 제거하고 단순한 직접 import 방식 사용
    """
    try:
        logger.info("Initializing integrated service system")

        services = {}
        initialized_services = []
        failed_services = []

        # Phase 1: ExchangeService 먼저 완전 초기화 (SymbolValidator 의존성 보장)

        # 1. Exchange Service (CRITICAL - 먼저 초기화해야 함)
        # WHY ExchangeService를 먼저 초기화해야 하는가:
        # - SymbolValidator는 거래소 클라이언트를 통해 심볼 정보를 로드
        # - ExchangeService 초기화 실패 시 모든 거래 관련 기능 동작 불가
        # - 안정적인 서비스 운영을 위해 필수 선행 조건
        try:
            logger.info("Initializing Exchange Service...")
            from app.services.exchange import exchange_service
            services['exchange_service'] = exchange_service

            # ExchangeService 완전 초기화 검증
            # Issue #64: _crypto_exchanges 비어있는 문제 방지
            if not hasattr(exchange_service, '_crypto_exchanges') or not exchange_service._crypto_exchanges:
                logger.error("ExchangeService._crypto_exchanges is empty")
                raise Exception("ExchangeService initialization failed: _crypto_exchanges dictionary is empty")

            # register_active_exchanges() 결과 검증
            # centronex4를 포함한 모든 지원 거래소 등록 확인
            registration_result = exchange_service.register_active_exchanges()
            if not registration_result['success']:
                logger.error(f"Exchange registration failed: {registration_result.get('errors', [])}")
                raise Exception(f"Exchange registration failed: {registration_result.get('errors', [])}")

            registered_count = len(registration_result['registered_exchanges'])
            logger.info(f"Exchange Service initialized: {registered_count} exchanges registered")
            logger.debug(f"Registered exchanges: {registration_result['registered_exchanges']}")
            initialized_services.append('exchange_service')

        except Exception as e:
            failed_services.append(('exchange_service', str(e)))
            logger.error(f"Exchange Service initialization failed: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            # ExchangeService 실패 시 전체 서비스 시작 중단
            # WHY: 거래소 연결 없이는 모든 핵심 기능이 동작 불가
            return {
                'success': False,
                'error': f'Service startup failed due to ExchangeService initialization failure: {str(e)}',
                'services': {},
                'initialized_services': [],
                'failed_services': [('exchange_service', str(e))],
                'mode': 'critical_failure'
            }

        # 나머지 서비스들 초기화 (ExchangeService 후)

        # 2. Security Service
        try:
            from app.services.security import security_service
            services['security_service'] = security_service
            initialized_services.append('security_service')
            logger.info("Security Service initialized")
        except Exception as e:
            failed_services.append(('security_service', str(e)))
            logger.error(f"Security Service initialization failed: {e}")

        # 3. Analytics Service
        try:
            from app.services.analytics import analytics_service
            services['analytics_service'] = analytics_service
            initialized_services.append('analytics_service')
            logger.info("Analytics Service initialized")
        except Exception as e:
            failed_services.append(('analytics_service', str(e)))
            logger.error(f"Analytics Service initialization failed: {e}")

        # 4. Trading Service
        try:
            from app.services.trading import trading_service
            services['trading_service'] = trading_service
            initialized_services.append('trading_service')
            logger.info("Trading Service initialized")
        except Exception as e:
            failed_services.append(('trading_service', str(e)))
            logger.error(f"Trading Service initialization failed: {e}")

        # 5. Telegram Service
        try:
            from app.services.telegram import telegram_service
            services['telegram_service'] = telegram_service
            initialized_services.append('telegram_service')
            logger.info("Telegram Service initialized")
        except Exception as e:
            failed_services.append(('telegram_service', str(e)))
            logger.error(f"Telegram Service initialization failed: {e}")

        # 필수 보조 서비스들

        # Event Service
        try:
            from app.services.event_service import event_service
            services['event_service'] = event_service
            initialized_services.append('event_service')
            logger.info("Event Service initialized")
        except Exception as e:
            failed_services.append(('event_service', str(e)))
            logger.warning(f"Event Service initialization failed (optional): {e}")

        # Strategy Service
        try:
            from app.services.strategy_service import strategy_service
            services['strategy_service'] = strategy_service
            initialized_services.append('strategy_service')
            logger.info("Strategy Service initialized")
        except Exception as e:
            failed_services.append(('strategy_service', str(e)))
            logger.error(f"Strategy Service initialization failed: {e}")

        # Webhook Service
        try:
            from app.services.webhook_service import webhook_service
            services['webhook_service'] = webhook_service
            initialized_services.append('webhook_service')
            logger.info("Webhook Service initialized")
        except Exception as e:
            failed_services.append(('webhook_service', str(e)))
            logger.error(f"Webhook Service initialization failed: {e}")

        # Symbol Validator (ExchangeService 후 초기화 - 의존성 해결)
        # WHY SymbolValidator를 나중에 초기화해야 하는가:
        # - ExchangeService가 제공하는 거래소 클라이언트 필요
        # - 심볼 정보 로드를 위한 API 연결 의존성
        # - 순환 의존성 방지를 위한 명확한 초기화 순서
        try:
            logger.info("Initializing Symbol Validator (checking ExchangeService dependency)...")
            from app.services.symbol_validator import symbol_validator
            services['symbol_validator'] = symbol_validator

            # ExchangeService 의존성 확인
            # WHY: SymbolValidator는 거래소 클라이언트를 통해 심볼 정보 로드
            if 'exchange_service' not in services:
                raise Exception("SymbolValidator initialization failed: ExchangeService must be initialized first")

            # Symbol Validator 초기화 (거래소 심볼 정보 필수 로드)
            # 모든 거래소의 심볼 정보를 Public API로 로드하여 거래 준비
            logger.info("Loading symbol information...")
            symbol_validator.load_initial_symbols()

            initialized_services.append('symbol_validator')
            logger.info("Symbol Validator initialized (symbol information loaded)")
        except Exception as e:
            # Symbol Validator 실패 시 전체 서비스 시작 중단
            # WHY: 심볼 정보 없이는 주문 검증 및 거래 실행 불가
            logger.error(f"Symbol Validator initialization failed: {e}")
            logger.error("Trading services cannot be provided without exchange symbol information")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            failed_services.append(('symbol_validator', str(e)))
            return {
                'success': False,
                'error': f'Service startup failed due to Symbol Validator initialization failure: {str(e)}',
                'services': {},
                'initialized_services': [],
                'failed_services': [('symbol_validator', str(e))],
                'mode': 'critical_failure'
            }

        # 결과 정리

        success = len(failed_services) == 0

        result = {
            'success': success,
            'services': services,
            'initialized_services': initialized_services,
            'failed_services': failed_services,
            'total_services': len(initialized_services) + len(failed_services),
            'success_rate': len(initialized_services) / (len(initialized_services) + len(failed_services)) * 100
        }

        # 최종 로깅
        if success:
            logger.info(f"Integrated service system initialization complete")
            logger.info(f"Successfully initialized: {len(initialized_services)}/{len(initialized_services) + len(failed_services)} services")
        else:
            logger.warning(f"Integrated service system partially initialized")
            logger.warning(f"Success: {len(initialized_services)}, Failed: {len(failed_services)}")
            for service_name, error in failed_services:
                logger.warning(f"    - {service_name}: {error}")

        return result

    except Exception as e:
        logger.error(f"Critical error during integrated service system initialization: {e}")
        return {
            'success': False,
            'error': str(e),
            'services': {},
            'initialized_services': [],
            'failed_services': [],
            'mode': 'failed'
        }


def get_service_health() -> Dict[str, Any]:
    """서비스 상태 확인"""
    try:
        health_status = {}

        # 각 서비스의 상태 확인
        services_to_check = [
            'exchange_service',
            'security_service',
            'analytics_service',
            'trading_service',
            'telegram_service'
        ]

        for service_name in services_to_check:
            try:
                if service_name == 'exchange_service':
                    from app.services.exchange import exchange_service
                    health_status[service_name] = {
                        'available': exchange_service.is_available(),
                        'status': 'healthy'
                    }
                elif service_name == 'security_service':
                    from app.services.security import security_service
                    health_status[service_name] = {
                        'available': True,
                        'status': 'healthy'
                    }
                elif service_name == 'analytics_service':
                    from app.services.analytics import analytics_service
                    health_status[service_name] = {
                        'available': analytics_service.is_available(),
                        'status': 'healthy'
                    }
                elif service_name == 'trading_service':
                    from app.services.trading import trading_service
                    health_status[service_name] = {
                        'available': trading_service.is_available(),
                        'status': 'healthy'
                    }
                elif service_name == 'telegram_service':
                    from app.services.telegram import telegram_service
                    health_status[service_name] = {
                        'available': telegram_service.is_available(),
                        'status': 'healthy'
                    }

            except Exception as e:
                health_status[service_name] = {
                    'available': False,
                    'status': 'unhealthy',
                    'error': str(e)
                }

        # 전체 상태 계산
        healthy_services = sum(1 for status in health_status.values()
                             if status.get('status') == 'healthy')
        total_services = len(health_status)

        overall_health = 'healthy' if healthy_services == total_services else 'degraded'
        if healthy_services == 0:
            overall_health = 'unhealthy'

        return {
            'overall_health': overall_health,
            'healthy_services': healthy_services,
            'total_services': total_services,
            'health_percentage': (healthy_services / total_services * 100) if total_services > 0 else 0,
            'services': health_status
        }

    except Exception as e:
        logger.error(f"서비스 상태 확인 실패: {e}")
        return {
            'overall_health': 'unknown',
            'error': str(e)
        }


# 이전 버전과의 호환성을 위한 별칭
def initialize_services_v1():
    """이전 버전 호환성을 위한 래퍼"""
    result = initialize_services()
    return result.get('services', {})


# 직접 import를 위한 서비스 참조들
def get_exchange_service():
    """Exchange Service 반환"""
    from app.services.exchange import exchange_service
    return exchange_service


def get_security_service():
    """Security Service 반환"""
    from app.services.security import security_service
    return security_service


def get_analytics_service():
    """Analytics Service 반환"""
    from app.services.analytics import analytics_service
    return analytics_service


def get_trading_service():
    """Trading Service 반환"""
    from app.services.trading import trading_service
    return trading_service


def get_telegram_service():
    """Telegram Service 반환"""
    from app.services.telegram import telegram_service
    return telegram_service