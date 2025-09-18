#!/usr/bin/env python3
"""
Exchange System 모니터링 및 검증 시스템

Enhanced Exchange와 Legacy CCXT의 성능, 정확성, 안정성을 지속적으로 모니터링
- 실시간 성능 메트릭
- 데이터 정확성 검증 
- 자동 경고 및 알림
- 대시보드용 메트릭 수집
"""

import time
import json
import logging
import asyncio
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from collections import defaultdict, deque
from threading import Lock
import statistics

from .enhanced_factory import enhanced_factory
# Migration system removed - using simplified configuration
from .registry import exchange_registry

logger = logging.getLogger(__name__)

@dataclass
class PerformanceMetric:
    """성능 메트릭"""
    timestamp: datetime
    exchange: str
    function: str
    is_enhanced: bool
    response_time_ms: float
    success: bool
    error_type: Optional[str] = None
    user_id: Optional[str] = None

@dataclass
class AccuracyTest:
    """정확성 테스트 결과"""
    timestamp: datetime
    exchange: str
    function: str
    symbol: str
    enhanced_result: Any
    legacy_result: Any
    is_identical: bool
    differences: List[str]
    
class MetricsCollector:
    """메트릭 수집기"""
    
    def __init__(self, max_history: int = 10000):
        self.max_history = max_history
        self._metrics: deque = deque(maxlen=max_history)
        self._accuracy_tests: deque = deque(maxlen=max_history)
        self._lock = Lock()
        
        # 실시간 통계용 버퍼
        self._recent_metrics = defaultdict(lambda: deque(maxlen=100))
        
        logger.info("📊 MetricsCollector 초기화 완료")
    
    def record_performance(
        self, 
        exchange: str,
        function: str,
        is_enhanced: bool,
        response_time_ms: float,
        success: bool,
        error_type: str = None,
        user_id: str = None
    ):
        """성능 메트릭 기록"""
        metric = PerformanceMetric(
            timestamp=datetime.now(),
            exchange=exchange,
            function=function,
            is_enhanced=is_enhanced,
            response_time_ms=response_time_ms,
            success=success,
            error_type=error_type,
            user_id=user_id
        )
        
        with self._lock:
            self._metrics.append(metric)
            
            # 실시간 통계용 버퍼 업데이트
            key = f"{exchange}_{function}_{is_enhanced}"
            self._recent_metrics[key].append(metric)
        
        # Migration system removed - performance recorded locally only
        
        # 경고 임계값 확인
        self._check_performance_alerts(metric)
    
    def record_accuracy_test(
        self,
        exchange: str,
        function: str, 
        symbol: str,
        enhanced_result: Any,
        legacy_result: Any
    ):
        """정확성 테스트 결과 기록"""
        differences = []
        is_identical = self._compare_results(enhanced_result, legacy_result, differences)
        
        test = AccuracyTest(
            timestamp=datetime.now(),
            exchange=exchange,
            function=function,
            symbol=symbol,
            enhanced_result=enhanced_result,
            legacy_result=legacy_result,
            is_identical=is_identical,
            differences=differences
        )
        
        with self._lock:
            self._accuracy_tests.append(test)
        
        if not is_identical:
            logger.warning(f"⚠️ 정확성 차이 발견: {exchange} {function} {symbol} - {len(differences)}개 차이점")
            for diff in differences[:3]:  # 처음 3개만 로그
                logger.warning(f"   - {diff}")
    
    def _compare_results(self, enhanced: Any, legacy: Any, differences: List[str]) -> bool:
        """결과 비교 (재귀적)"""
        try:
            if type(enhanced) != type(legacy):
                differences.append(f"Type mismatch: {type(enhanced).__name__} vs {type(legacy).__name__}")
                return False
            
            if isinstance(enhanced, dict):
                enhanced_keys = set(enhanced.keys())
                legacy_keys = set(legacy.keys())
                
                if enhanced_keys != legacy_keys:
                    missing_in_enhanced = legacy_keys - enhanced_keys
                    missing_in_legacy = enhanced_keys - legacy_keys
                    if missing_in_enhanced:
                        differences.append(f"Missing in enhanced: {missing_in_enhanced}")
                    if missing_in_legacy:
                        differences.append(f"Missing in legacy: {missing_in_legacy}")
                
                is_identical = True
                for key in enhanced_keys & legacy_keys:
                    if not self._compare_results(enhanced[key], legacy[key], differences):
                        is_identical = False
                        if len(differences) > 10:  # 너무 많은 차이점은 제한
                            break
                
                return is_identical and enhanced_keys == legacy_keys
            
            elif isinstance(enhanced, (list, tuple)):
                if len(enhanced) != len(legacy):
                    differences.append(f"Length mismatch: {len(enhanced)} vs {len(legacy)}")
                    return False
                
                for i, (e_item, l_item) in enumerate(zip(enhanced, legacy)):
                    if not self._compare_results(e_item, l_item, differences):
                        differences.append(f"Index {i} differs")
                        if len(differences) > 10:
                            break
                
                return len(differences) == 0
            
            elif isinstance(enhanced, float) and isinstance(legacy, float):
                # 부동소수점 비교 (작은 오차 허용)
                if abs(enhanced - legacy) > 1e-8:
                    differences.append(f"Float precision: {enhanced} vs {legacy}")
                    return False
                return True
            
            else:
                if enhanced != legacy:
                    differences.append(f"Value mismatch: {enhanced} vs {legacy}")
                    return False
                return True
                
        except Exception as e:
            differences.append(f"Comparison error: {e}")
            return False
    
    def _check_performance_alerts(self, metric: PerformanceMetric):
        """성능 경고 확인"""
        # 응답 시간 경고 (2초 초과)
        if metric.response_time_ms > 2000:
            logger.warning(f"🐌 느린 응답: {metric.exchange} {metric.function} ({metric.response_time_ms:.1f}ms)")
        
        # 오류 경고
        if not metric.success:
            logger.error(f"❌ 실행 오류: {metric.exchange} {metric.function} - {metric.error_type}")
    
    def get_performance_summary(self, hours: int = 24) -> Dict[str, Any]:
        """성능 요약 통계"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        with self._lock:
            recent_metrics = [m for m in self._metrics if m.timestamp > cutoff_time]
        
        if not recent_metrics:
            return {'total_requests': 0, 'message': 'No recent data'}
        
        # 기본 통계
        total_requests = len(recent_metrics)
        enhanced_requests = len([m for m in recent_metrics if m.is_enhanced])
        successful_requests = len([m for m in recent_metrics if m.success])
        
        # 성능 통계
        response_times = [m.response_time_ms for m in recent_metrics]
        
        # 거래소별 통계
        exchange_stats = defaultdict(lambda: {'total': 0, 'enhanced': 0, 'success': 0, 'response_times': []})
        for metric in recent_metrics:
            stats = exchange_stats[metric.exchange]
            stats['total'] += 1
            if metric.is_enhanced:
                stats['enhanced'] += 1
            if metric.success:
                stats['success'] += 1
            stats['response_times'].append(metric.response_time_ms)
        
        return {
            'period_hours': hours,
            'total_requests': total_requests,
            'enhanced_usage_percentage': (enhanced_requests / total_requests * 100) if total_requests > 0 else 0,
            'success_rate_percentage': (successful_requests / total_requests * 100) if total_requests > 0 else 0,
            'performance': {
                'avg_response_time_ms': statistics.mean(response_times) if response_times else 0,
                'median_response_time_ms': statistics.median(response_times) if response_times else 0,
                'p95_response_time_ms': statistics.quantiles(response_times, n=20)[18] if len(response_times) > 20 else 0,
                'max_response_time_ms': max(response_times) if response_times else 0
            },
            'exchanges': {
                name: {
                    'total_requests': stats['total'],
                    'enhanced_percentage': (stats['enhanced'] / stats['total'] * 100) if stats['total'] > 0 else 0,
                    'success_rate': (stats['success'] / stats['total'] * 100) if stats['total'] > 0 else 0,
                    'avg_response_time_ms': statistics.mean(stats['response_times']) if stats['response_times'] else 0
                }
                for name, stats in exchange_stats.items()
            }
        }
    
    def get_accuracy_summary(self, hours: int = 24) -> Dict[str, Any]:
        """정확성 요약 통계"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        with self._lock:
            recent_tests = [t for t in self._accuracy_tests if t.timestamp > cutoff_time]
        
        if not recent_tests:
            return {'total_tests': 0, 'message': 'No recent accuracy tests'}
        
        total_tests = len(recent_tests)
        identical_results = len([t for t in recent_tests if t.is_identical])
        
        # 기능별 정확성
        function_stats = defaultdict(lambda: {'total': 0, 'identical': 0, 'differences': []})
        for test in recent_tests:
            stats = function_stats[test.function]
            stats['total'] += 1
            if test.is_identical:
                stats['identical'] += 1
            else:
                stats['differences'].extend(test.differences[:3])  # 처음 3개만
        
        return {
            'period_hours': hours,
            'total_tests': total_tests,
            'accuracy_percentage': (identical_results / total_tests * 100) if total_tests > 0 else 0,
            'identical_results': identical_results,
            'different_results': total_tests - identical_results,
            'functions': {
                name: {
                    'total_tests': stats['total'],
                    'accuracy_percentage': (stats['identical'] / stats['total'] * 100) if stats['total'] > 0 else 0,
                    'common_differences': list(set(stats['differences'][:5]))  # 상위 5개 차이점
                }
                for name, stats in function_stats.items()
            }
        }

class SystemMonitor:
    """전체 시스템 모니터링"""
    
    def __init__(self):
        self.metrics_collector = MetricsCollector()
        self._monitoring_active = False
        self._monitoring_task = None
        
        logger.info("🔍 SystemMonitor 초기화 완료")
    
    async def start_monitoring(self, interval_seconds: int = 60):
        """모니터링 시작"""
        if self._monitoring_active:
            logger.warning("⚠️ 모니터링이 이미 실행 중입니다")
            return
        
        self._monitoring_active = True
        self._monitoring_task = asyncio.create_task(self._monitoring_loop(interval_seconds))
        logger.info(f"🚀 시스템 모니터링 시작 (간격: {interval_seconds}초)")
    
    async def stop_monitoring(self):
        """모니터링 중지"""
        if not self._monitoring_active:
            return
        
        self._monitoring_active = False
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        
        logger.info("⏹️ 시스템 모니터링 중지")
    
    async def _monitoring_loop(self, interval_seconds: int):
        """모니터링 루프"""
        while self._monitoring_active:
            try:
                await self._collect_system_metrics()
                await asyncio.sleep(interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ 모니터링 루프 오류: {e}")
                await asyncio.sleep(interval_seconds)
    
    async def _collect_system_metrics(self):
        """시스템 메트릭 수집"""
        try:
            # Enhanced Factory 통계
            factory_stats = enhanced_factory.get_creation_stats()
            
            # Registry 통계
            registry_stats = exchange_registry.get_stats()
            
            # 성능 요약
            performance_summary = self.metrics_collector.get_performance_summary(hours=1)
            
            # 경고 조건 확인
            await self._check_system_health(performance_summary, factory_stats)
            
        except Exception as e:
            logger.error(f"❌ 시스템 메트릭 수집 실패: {e}")
    
    async def _check_system_health(self, performance: Dict, factory: Dict):
        """시스템 건강성 확인"""
        warnings = []
        
        # 성공률 확인
        if performance.get('success_rate_percentage', 100) < 95:
            warnings.append(f"낮은 성공률: {performance['success_rate_percentage']:.1f}%")
        
        # 응답 시간 확인
        avg_response = performance.get('performance', {}).get('avg_response_time_ms', 0)
        if avg_response > 1000:
            warnings.append(f"느린 응답시간: {avg_response:.1f}ms")
        
        # Factory 오류 확인
        if factory.get('creation_errors', 0) > 10:
            warnings.append(f"Factory 오류 다발: {factory['creation_errors']}건")
        
        # 경고 로깅
        if warnings:
            logger.warning(f"⚠️ 시스템 건강성 경고: {', '.join(warnings)}")
        
        # 긴급 상황 확인
        if (performance.get('success_rate_percentage', 100) < 90 and 
            performance.get('total_requests', 0) > 100):
            logger.critical("🚨 긴급상황: 성공률 90% 미만, 긴급 롤백 고려")
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """대시보드용 데이터"""
        return {
            'timestamp': datetime.now().isoformat(),
            'performance': self.metrics_collector.get_performance_summary(),
            'accuracy': self.metrics_collector.get_accuracy_summary(),
            # Migration system removed - using simplified configuration
            'factory': enhanced_factory.get_creation_stats(),
            'registry': exchange_registry.get_stats()
        }

# 전역 모니터링 인스턴스
system_monitor = SystemMonitor()

# 데코레이터 함수들
def monitor_performance(exchange: str, function: str, is_enhanced: bool = False):
    """성능 모니터링 데코레이터"""
    def decorator(func):
        if asyncio.iscoroutinefunction(func):
            async def async_wrapper(*args, **kwargs):
                start_time = time.time()
                success = False
                error_type = None
                
                try:
                    result = await func(*args, **kwargs)
                    success = True
                    return result
                except Exception as e:
                    error_type = type(e).__name__
                    raise
                finally:
                    response_time_ms = (time.time() - start_time) * 1000
                    system_monitor.metrics_collector.record_performance(
                        exchange=exchange,
                        function=function,
                        is_enhanced=is_enhanced,
                        response_time_ms=response_time_ms,
                        success=success,
                        error_type=error_type
                    )
            return async_wrapper
        else:
            def sync_wrapper(*args, **kwargs):
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
                    response_time_ms = (time.time() - start_time) * 1000
                    system_monitor.metrics_collector.record_performance(
                        exchange=exchange,
                        function=function,
                        is_enhanced=is_enhanced,
                        response_time_ms=response_time_ms,
                        success=success,
                        error_type=error_type
                    )
            return sync_wrapper
    return decorator

# 편의 함수들
def record_performance_metric(
    exchange: str,
    function: str, 
    is_enhanced: bool,
    response_time_ms: float,
    success: bool,
    error_type: str = None
):
    """성능 메트릭 기록 (전역 함수)"""
    system_monitor.metrics_collector.record_performance(
        exchange=exchange,
        function=function,
        is_enhanced=is_enhanced,
        response_time_ms=response_time_ms,
        success=success,
        error_type=error_type
    )

def record_accuracy_test(
    exchange: str,
    function: str,
    symbol: str,
    enhanced_result: Any,
    legacy_result: Any
):
    """정확성 테스트 기록 (전역 함수)"""
    system_monitor.metrics_collector.record_accuracy_test(
        exchange=exchange,
        function=function,
        symbol=symbol,
        enhanced_result=enhanced_result,
        legacy_result=legacy_result
    )