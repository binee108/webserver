"""
마이그레이션 모니터링 서비스
신규/레거시 서비스 간 성능 및 안정성 비교
"""

import logging
import time
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict, deque
import statistics
import threading

logger = logging.getLogger(__name__)


class MigrationMonitor:
    """마이그레이션 모니터링 서비스"""

    def __init__(self):
        self.metrics = defaultdict(lambda: {
            'call_count': 0,
            'success_count': 0,
            'error_count': 0,
            'response_times': deque(maxlen=1000),  # 최근 1000개 응답시간
            'error_types': defaultdict(int),
            'last_call': None
        })

        self.comparison_data = {
            'new_service': defaultdict(lambda: self._create_service_metrics()),
            'legacy_service': defaultdict(lambda: self._create_service_metrics())
        }

        self.lock = threading.Lock()
        self.monitoring_start_time = datetime.utcnow()

    def _create_service_metrics(self) -> Dict[str, Any]:
        """서비스 메트릭 기본 구조 생성"""
        return {
            'call_count': 0,
            'success_count': 0,
            'error_count': 0,
            'response_times': deque(maxlen=1000),
            'error_types': defaultdict(int),
            'avg_response_time': 0.0,
            'p95_response_time': 0.0,
            'success_rate': 0.0
        }

    def record_service_call(self, service_type: str, method_name: str,
                           response_time: float, success: bool,
                           error_type: Optional[str] = None):
        """서비스 호출 기록"""
        with self.lock:
            # 전체 메트릭 업데이트
            metrics = self.metrics[method_name]
            metrics['call_count'] += 1
            metrics['response_times'].append(response_time)
            metrics['last_call'] = datetime.utcnow()

            if success:
                metrics['success_count'] += 1
            else:
                metrics['error_count'] += 1
                if error_type:
                    metrics['error_types'][error_type] += 1

            # 서비스별 메트릭 업데이트
            service_metrics = self.comparison_data[service_type][method_name]
            service_metrics['call_count'] += 1
            service_metrics['response_times'].append(response_time)

            if success:
                service_metrics['success_count'] += 1
            else:
                service_metrics['error_count'] += 1
                if error_type:
                    service_metrics['error_types'][error_type] += 1

            # 통계 업데이트
            self._update_statistics(service_metrics)

    def _update_statistics(self, metrics: Dict[str, Any]):
        """통계 정보 업데이트"""
        response_times = list(metrics['response_times'])

        if response_times:
            metrics['avg_response_time'] = statistics.mean(response_times)
            if len(response_times) >= 20:  # 최소 20개 데이터가 있을 때만 P95 계산
                metrics['p95_response_time'] = statistics.quantiles(response_times, n=20)[18]  # 95th percentile
            else:
                metrics['p95_response_time'] = max(response_times)

        if metrics['call_count'] > 0:
            metrics['success_rate'] = (metrics['success_count'] / metrics['call_count']) * 100

    def get_comparison_report(self) -> Dict[str, Any]:
        """새 서비스 vs 레거시 서비스 비교 보고서"""
        with self.lock:
            report = {
                'monitoring_duration': str(datetime.utcnow() - self.monitoring_start_time),
                'monitoring_start_time': self.monitoring_start_time.isoformat(),
                'comparison': {},
                'recommendations': [],
                'summary': {}
            }

            # 메서드별 비교
            all_methods = set()
            all_methods.update(self.comparison_data['new_service'].keys())
            all_methods.update(self.comparison_data['legacy_service'].keys())

            for method in all_methods:
                new_metrics = self.comparison_data['new_service'].get(method, self._create_service_metrics())
                legacy_metrics = self.comparison_data['legacy_service'].get(method, self._create_service_metrics())

                method_comparison = {
                    'new_service': self._format_metrics(new_metrics),
                    'legacy_service': self._format_metrics(legacy_metrics),
                    'performance_comparison': self._compare_performance(new_metrics, legacy_metrics),
                    'reliability_comparison': self._compare_reliability(new_metrics, legacy_metrics)
                }

                report['comparison'][method] = method_comparison

            # 전체 요약
            report['summary'] = self._generate_summary(report['comparison'])

            # 권장사항 생성
            report['recommendations'] = self._generate_recommendations(report['comparison'], report['summary'])

            return report

    def _format_metrics(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """메트릭 데이터 포맷팅"""
        return {
            'call_count': metrics['call_count'],
            'success_count': metrics['success_count'],
            'error_count': metrics['error_count'],
            'success_rate': round(metrics['success_rate'], 2),
            'avg_response_time_ms': round(metrics['avg_response_time'] * 1000, 2),
            'p95_response_time_ms': round(metrics['p95_response_time'] * 1000, 2),
            'top_error_types': dict(list(metrics['error_types'].most_common(3))) if hasattr(metrics['error_types'], 'most_common') else dict(metrics['error_types'])
        }

    def _compare_performance(self, new_metrics: Dict[str, Any], legacy_metrics: Dict[str, Any]) -> Dict[str, Any]:
        """성능 비교"""
        comparison = {
            'winner': 'none',
            'performance_improvement': 0.0,
            'details': {}
        }

        if new_metrics['call_count'] > 0 and legacy_metrics['call_count'] > 0:
            new_avg = new_metrics['avg_response_time']
            legacy_avg = legacy_metrics['avg_response_time']

            if legacy_avg > 0:
                improvement = ((legacy_avg - new_avg) / legacy_avg) * 100
                comparison['performance_improvement'] = round(improvement, 2)

                if improvement > 5:  # 5% 이상 개선
                    comparison['winner'] = 'new_service'
                elif improvement < -5:  # 5% 이상 저하
                    comparison['winner'] = 'legacy_service'
                else:
                    comparison['winner'] = 'similar'

            comparison['details'] = {
                'new_service_avg_ms': round(new_avg * 1000, 2),
                'legacy_service_avg_ms': round(legacy_avg * 1000, 2),
                'new_service_p95_ms': round(new_metrics['p95_response_time'] * 1000, 2),
                'legacy_service_p95_ms': round(legacy_metrics['p95_response_time'] * 1000, 2)
            }

        return comparison

    def _compare_reliability(self, new_metrics: Dict[str, Any], legacy_metrics: Dict[str, Any]) -> Dict[str, Any]:
        """안정성 비교"""
        comparison = {
            'winner': 'none',
            'reliability_improvement': 0.0,
            'details': {}
        }

        if new_metrics['call_count'] > 0 and legacy_metrics['call_count'] > 0:
            new_success_rate = new_metrics['success_rate']
            legacy_success_rate = legacy_metrics['success_rate']

            improvement = new_success_rate - legacy_success_rate
            comparison['reliability_improvement'] = round(improvement, 2)

            if improvement > 2:  # 2% 이상 개선
                comparison['winner'] = 'new_service'
            elif improvement < -2:  # 2% 이상 저하
                comparison['winner'] = 'legacy_service'
            else:
                comparison['winner'] = 'similar'

            comparison['details'] = {
                'new_service_success_rate': round(new_success_rate, 2),
                'legacy_service_success_rate': round(legacy_success_rate, 2),
                'new_service_error_count': new_metrics['error_count'],
                'legacy_service_error_count': legacy_metrics['error_count']
            }

        return comparison

    def _generate_summary(self, comparison_data: Dict[str, Any]) -> Dict[str, Any]:
        """전체 요약 생성"""
        summary = {
            'total_methods_compared': len(comparison_data),
            'performance_winners': {'new_service': 0, 'legacy_service': 0, 'similar': 0},
            'reliability_winners': {'new_service': 0, 'legacy_service': 0, 'similar': 0},
            'overall_recommendation': 'insufficient_data'
        }

        for method, data in comparison_data.items():
            perf_winner = data['performance_comparison']['winner']
            rel_winner = data['reliability_comparison']['winner']

            if perf_winner in summary['performance_winners']:
                summary['performance_winners'][perf_winner] += 1

            if rel_winner in summary['reliability_winners']:
                summary['reliability_winners'][rel_winner] += 1

        # 전체 권장사항 결정
        perf_new_wins = summary['performance_winners']['new_service']
        perf_legacy_wins = summary['performance_winners']['legacy_service']
        rel_new_wins = summary['reliability_winners']['new_service']
        rel_legacy_wins = summary['reliability_winners']['legacy_service']

        total_comparisons = summary['total_methods_compared']

        if total_comparisons > 0:
            if (perf_new_wins + rel_new_wins) > (perf_legacy_wins + rel_legacy_wins) * 1.5:
                summary['overall_recommendation'] = 'switch_to_new_service'
            elif (perf_legacy_wins + rel_legacy_wins) > (perf_new_wins + rel_new_wins) * 1.5:
                summary['overall_recommendation'] = 'keep_legacy_service'
            else:
                summary['overall_recommendation'] = 'gradual_migration'

        return summary

    def _generate_recommendations(self, comparison_data: Dict[str, Any], summary: Dict[str, Any]) -> List[str]:
        """권장사항 생성"""
        recommendations = []

        overall_rec = summary.get('overall_recommendation', 'insufficient_data')

        if overall_rec == 'switch_to_new_service':
            recommendations.append("새로운 서비스가 전반적으로 우수합니다. 전면 전환을 권장합니다.")
        elif overall_rec == 'keep_legacy_service':
            recommendations.append("레거시 서비스가 더 안정적입니다. 새 서비스 개선 후 재검토를 권장합니다.")
        elif overall_rec == 'gradual_migration':
            recommendations.append("점진적 마이그레이션을 권장합니다. 메서드별로 검토 후 선택적 전환하세요.")
        else:
            recommendations.append("비교할 데이터가 부족합니다. 더 많은 호출 데이터 수집 후 재검토하세요.")

        # 개별 메서드별 권장사항
        performance_issues = []
        reliability_issues = []

        for method, data in comparison_data.items():
            perf_comp = data['performance_comparison']
            rel_comp = data['reliability_comparison']

            if perf_comp['winner'] == 'legacy_service' and perf_comp['performance_improvement'] < -20:
                performance_issues.append(f"{method}: 성능이 {abs(perf_comp['performance_improvement']):.1f}% 저하")

            if rel_comp['winner'] == 'legacy_service' and rel_comp['reliability_improvement'] < -5:
                reliability_issues.append(f"{method}: 안정성이 {abs(rel_comp['reliability_improvement']):.1f}% 저하")

        if performance_issues:
            recommendations.append(f"성능 개선 필요: {', '.join(performance_issues)}")

        if reliability_issues:
            recommendations.append(f"안정성 개선 필요: {', '.join(reliability_issues)}")

        return recommendations

    def get_real_time_metrics(self) -> Dict[str, Any]:
        """실시간 메트릭 조회"""
        with self.lock:
            current_time = datetime.utcnow()
            recent_window = current_time - timedelta(minutes=5)  # 최근 5분

            metrics = {
                'timestamp': current_time.isoformat(),
                'recent_activity': {},
                'active_services': []
            }

            for method, data in self.metrics.items():
                if data['last_call'] and data['last_call'] > recent_window:
                    metrics['recent_activity'][method] = {
                        'last_call': data['last_call'].isoformat(),
                        'recent_call_count': data['call_count'],
                        'recent_success_rate': (data['success_count'] / max(data['call_count'], 1)) * 100
                    }

            # 활성 서비스 확인
            for service_type in ['new_service', 'legacy_service']:
                if any(data['call_count'] > 0 for data in self.comparison_data[service_type].values()):
                    metrics['active_services'].append(service_type)

            return metrics

    def reset_metrics(self):
        """메트릭 초기화"""
        with self.lock:
            self.metrics.clear()
            self.comparison_data['new_service'].clear()
            self.comparison_data['legacy_service'].clear()
            self.monitoring_start_time = datetime.utcnow()
            logger.info("마이그레이션 모니터링 메트릭 초기화 완료")


# 전역 모니터 인스턴스
migration_monitor = MigrationMonitor()


# 데코레이터 함수들
def monitor_service_call(service_type: str, method_name: str):
    """서비스 호출 모니터링 데코레이터"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            start_time = time.time()
            success = False
            error_type = None

            try:
                result = func(*args, **kwargs)
                success = True
                return result
            except Exception as e:
                error_type = type(e).__name__
                raise
            finally:
                response_time = time.time() - start_time
                migration_monitor.record_service_call(
                    service_type, method_name, response_time, success, error_type
                )

        return wrapper
    return decorator