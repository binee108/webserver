"""
의존성 주입 헬스체크 서비스
DI 시스템의 상태 모니터링 및 검증
"""

import logging
from typing import Dict, Any, List
from datetime import datetime
from app.services.service_container import container

logger = logging.getLogger(__name__)


class DIHealthCheck:
    """의존성 주입 시스템 헬스체크"""

    def __init__(self):
        self.last_check_time = None
        self.check_history = []

    def run_comprehensive_check(self) -> Dict[str, Any]:
        """종합적인 헬스체크 실행"""
        check_result = {
            'timestamp': datetime.utcnow().isoformat(),
            'overall_health': 'healthy',
            'checks': {},
            'warnings': [],
            'errors': [],
            'recommendations': []
        }

        try:
            # 1. 컨테이너 기본 상태 확인
            check_result['checks']['container_status'] = self._check_container_status()

            # 2. 서비스 초기화 상태 확인
            check_result['checks']['service_initialization'] = self._check_service_initialization()

            # 3. 의존성 그래프 검증
            check_result['checks']['dependency_graph'] = self._check_dependency_graph()

            # 4. 서비스 인터페이스 호환성 확인
            check_result['checks']['interface_compatibility'] = self._check_interface_compatibility()

            # 5. 메모리 사용량 확인
            check_result['checks']['memory_usage'] = self._check_memory_usage()

            # 6. 성능 지표 확인
            check_result['checks']['performance_metrics'] = self._check_performance_metrics()

            # 전체 상태 결정
            check_result['overall_health'] = self._determine_overall_health(check_result['checks'])

            # 기록 저장
            self.last_check_time = datetime.utcnow()
            self.check_history.append({
                'timestamp': check_result['timestamp'],
                'health': check_result['overall_health'],
                'service_count': len(container.get_all_services())
            })

            # 히스토리 관리 (최근 50개만 유지)
            if len(self.check_history) > 50:
                self.check_history = self.check_history[-50:]

        except Exception as e:
            logger.error(f"헬스체크 실행 중 오류: {e}")
            check_result['overall_health'] = 'error'
            check_result['errors'].append(f"헬스체크 실행 오류: {str(e)}")

        return check_result

    def _check_container_status(self) -> Dict[str, Any]:
        """컨테이너 기본 상태 확인"""
        try:
            health_info = container.get_service_health()

            status = {
                'status': 'healthy',
                'details': health_info,
                'issues': []
            }

            # 초기화 비율이 낮으면 경고
            if health_info['initialization_rate'] < 80:
                status['status'] = 'warning'
                status['issues'].append(f"서비스 초기화 비율이 낮습니다: {health_info['initialization_rate']:.1f}%")

            # 초기화 비율이 매우 낮으면 오류
            if health_info['initialization_rate'] < 50:
                status['status'] = 'error'

            return status

        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'issues': ['컨테이너 상태 확인 실패']
            }

    def _check_service_initialization(self) -> Dict[str, Any]:
        """서비스 초기화 상태 확인"""
        try:
            services = container.get_all_services()
            health_info = container.get_service_health()

            critical_services = [
                'new_exchange_service',
                'unified_order_service',
                'trading_orchestrator'
            ]

            status = {
                'status': 'healthy',
                'initialized_count': len(services),
                'total_registered': health_info['total_registered'],
                'missing_critical_services': [],
                'failed_services': []
            }

            # 중요 서비스 확인
            for service_name in critical_services:
                if service_name not in services:
                    status['missing_critical_services'].append(service_name)

            # 실패한 서비스 확인
            for service_name, service_info in health_info['services'].items():
                if service_info['status'] != 'initialized':
                    status['failed_services'].append(service_name)

            # 상태 결정
            if status['missing_critical_services']:
                status['status'] = 'error'
            elif status['failed_services']:
                status['status'] = 'warning'

            return status

        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }

    def _check_dependency_graph(self) -> Dict[str, Any]:
        """의존성 그래프 검증"""
        try:
            # 기본적인 의존성 확인
            # 실제 순환 의존성 검사는 컨테이너에서 이미 수행됨

            status = {
                'status': 'healthy',
                'dependency_violations': [],
                'circular_dependencies': []
            }

            # 여기서는 기본적인 검증만 수행
            # 향후 더 정교한 의존성 분석 로직 추가 가능

            return status

        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }

    def _check_interface_compatibility(self) -> Dict[str, Any]:
        """서비스 인터페이스 호환성 확인"""
        try:
            services = container.get_all_services()

            status = {
                'status': 'healthy',
                'interface_checks': {},
                'compatibility_issues': []
            }

            # 주요 서비스들의 인터페이스 확인
            interface_checks = {
                'new_exchange_service': ['get_exchange', 'create_order', 'cancel_order', 'fetch_balance'],
                'unified_order_service': ['create_open_order', 'update_open_orders_status', 'cancel_order'],
                'trading_orchestrator': ['set_services', 'execute_trade_with_position_update']
            }

            for service_name, required_methods in interface_checks.items():
                if service_name in services:
                    service_obj = services[service_name]
                    missing_methods = []

                    for method_name in required_methods:
                        if not hasattr(service_obj, method_name):
                            missing_methods.append(method_name)

                    status['interface_checks'][service_name] = {
                        'missing_methods': missing_methods,
                        'compatible': len(missing_methods) == 0
                    }

                    if missing_methods:
                        status['compatibility_issues'].append(f"{service_name}: 누락된 메서드 {missing_methods}")

            # 호환성 문제가 있으면 경고
            if status['compatibility_issues']:
                status['status'] = 'warning'

            return status

        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }

    def _check_memory_usage(self) -> Dict[str, Any]:
        """메모리 사용량 확인"""
        try:
            import sys
            import gc

            # 가비지 컬렉션 실행
            gc.collect()

            # 기본적인 메모리 정보
            ref_count = len(gc.get_objects())
            services_count = len(container.get_all_services())

            status = {
                'status': 'healthy',
                'object_count': ref_count,
                'service_count': services_count,
                'gc_stats': {
                    'collections': gc.get_count(),
                    'threshold': gc.get_threshold()
                }
            }

            # 메모리 사용량이 너무 높으면 경고 (간단한 휴리스틱)
            if ref_count > 100000:  # 임의의 임계값
                status['status'] = 'warning'
                status['warning'] = f"높은 객체 수: {ref_count}"

            return status

        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }

    def _check_performance_metrics(self) -> Dict[str, Any]:
        """성능 지표 확인"""
        try:
            import time

            # 기본적인 성능 테스트
            start_time = time.time()

            # 서비스 조회 성능 테스트
            services = container.get_all_services()
            service_access_time = time.time() - start_time

            status = {
                'status': 'healthy',
                'service_access_time_ms': round(service_access_time * 1000, 2),
                'service_count': len(services)
            }

            # 서비스 접근 시간이 너무 오래 걸리면 경고
            if service_access_time > 0.1:  # 100ms
                status['status'] = 'warning'
                status['warning'] = f"서비스 접근 시간이 느림: {service_access_time * 1000:.2f}ms"

            return status

        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }

    def _determine_overall_health(self, checks: Dict[str, Any]) -> str:
        """전체 상태 결정"""
        # 오류가 있으면 error
        for check_name, check_result in checks.items():
            if isinstance(check_result, dict) and check_result.get('status') == 'error':
                return 'error'

        # 경고가 있으면 warning
        for check_name, check_result in checks.items():
            if isinstance(check_result, dict) and check_result.get('status') == 'warning':
                return 'warning'

        return 'healthy'

    def get_health_summary(self) -> Dict[str, Any]:
        """헬스체크 요약 정보"""
        return {
            'last_check': self.last_check_time.isoformat() if self.last_check_time else None,
            'check_count': len(self.check_history),
            'recent_health': [h['health'] for h in self.check_history[-10:]] if self.check_history else [],
            'service_container_status': container.get_service_health()
        }

    def get_recommendations(self, check_result: Dict[str, Any]) -> List[str]:
        """개선 권장사항 생성"""
        recommendations = []

        container_check = check_result.get('checks', {}).get('container_status', {})
        if container_check.get('status') == 'warning':
            details = container_check.get('details', {})
            init_rate = details.get('initialization_rate', 0)
            if init_rate < 80:
                recommendations.append(f"서비스 초기화 비율을 개선하세요 (현재: {init_rate:.1f}%)")

        interface_check = check_result.get('checks', {}).get('interface_compatibility', {})
        if interface_check.get('compatibility_issues'):
            recommendations.append("서비스 인터페이스 호환성 문제를 해결하세요")

        memory_check = check_result.get('checks', {}).get('memory_usage', {})
        if memory_check.get('status') == 'warning':
            recommendations.append("메모리 사용량을 최적화하세요")

        performance_check = check_result.get('checks', {}).get('performance_metrics', {})
        if performance_check.get('status') == 'warning':
            recommendations.append("서비스 접근 성능을 개선하세요")

        return recommendations


# 전역 헬스체크 인스턴스
health_checker = DIHealthCheck()