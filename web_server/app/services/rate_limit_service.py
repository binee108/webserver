"""
Rate Limiting 서비스
거래소별 API 호출 제한 관리
"""

import time
import logging
from typing import Dict, Any, Optional
from threading import Lock
from collections import defaultdict, deque
from functools import wraps

logger = logging.getLogger(__name__)


class RateLimitService:
    """API Rate Limiting 관리 서비스"""

    def __init__(self):
        self.rate_limits = {
            # 거래소별 기본 rate limit (초당 요청 수)
            'binance': {'requests_per_second': 10, 'burst_limit': 50},
            'bybit': {'requests_per_second': 10, 'burst_limit': 50},
            'okx': {'requests_per_second': 20, 'burst_limit': 100},
            'default': {'requests_per_second': 5, 'burst_limit': 25}
        }

        # 각 거래소별 요청 히스토리 (sliding window)
        self.request_history = defaultdict(deque)  # {exchange_name: deque of timestamps}
        self.last_request_time = defaultdict(float)  # {exchange_name: last_request_timestamp}
        self.lock = Lock()

        # 통계
        self.stats = defaultdict(lambda: {
            'total_requests': 0,
            'blocked_requests': 0,
            'average_wait_time': 0.0
        })

    def check_rate_limit(self, exchange_name: str) -> Dict[str, Any]:
        """
        Rate limit 체크 및 대기 시간 계산

        Returns:
            {
                'allowed': bool,
                'wait_time': float,  # 초 단위
                'current_rate': float  # 현재 초당 요청 수
            }
        """
        with self.lock:
            current_time = time.time()
            exchange_name = exchange_name.lower()

            # 거래소별 설정 가져오기
            limits = self.rate_limits.get(exchange_name, self.rate_limits['default'])
            max_requests_per_second = limits['requests_per_second']
            burst_limit = limits['burst_limit']

            # 1초 윈도우에서 오래된 요청 제거
            request_queue = self.request_history[exchange_name]
            while request_queue and current_time - request_queue[0] > 1.0:
                request_queue.popleft()

            # 현재 초당 요청 수 계산
            current_requests_in_window = len(request_queue)
            current_rate = current_requests_in_window

            # Rate limit 체크
            if current_requests_in_window >= max_requests_per_second:
                # 다음 요청 가능 시간 계산
                oldest_request_time = request_queue[0] if request_queue else current_time
                wait_time = max(0, 1.0 - (current_time - oldest_request_time))

                self.stats[exchange_name]['blocked_requests'] += 1

                return {
                    'allowed': False,
                    'wait_time': wait_time,
                    'current_rate': current_rate,
                    'reason': f'Rate limit exceeded: {current_requests_in_window}/{max_requests_per_second} req/sec'
                }

            # Burst limit 체크 (더 긴 윈도우)
            burst_window = 10.0  # 10초 윈도우
            burst_requests = sum(1 for req_time in request_queue if current_time - req_time <= burst_window)

            if burst_requests >= burst_limit:
                wait_time = 1.0  # 버스트 제한 시 1초 대기

                return {
                    'allowed': False,
                    'wait_time': wait_time,
                    'current_rate': current_rate,
                    'reason': f'Burst limit exceeded: {burst_requests}/{burst_limit} in {burst_window}s'
                }

            # 연속 요청 간 최소 간격 체크
            last_request = self.last_request_time[exchange_name]
            min_interval = 1.0 / max_requests_per_second
            time_since_last = current_time - last_request

            if time_since_last < min_interval:
                wait_time = min_interval - time_since_last
                return {
                    'allowed': False,
                    'wait_time': wait_time,
                    'current_rate': current_rate,
                    'reason': f'Minimum interval not met: {time_since_last:.3f}s < {min_interval:.3f}s'
                }

            return {
                'allowed': True,
                'wait_time': 0.0,
                'current_rate': current_rate
            }

    def record_request(self, exchange_name: str):
        """요청 기록"""
        with self.lock:
            current_time = time.time()
            exchange_name = exchange_name.lower()

            # 요청 히스토리에 추가
            self.request_history[exchange_name].append(current_time)
            self.last_request_time[exchange_name] = current_time

            # 통계 업데이트
            self.stats[exchange_name]['total_requests'] += 1

    def wait_if_needed(self, exchange_name: str) -> float:
        """
        필요시 대기 후 요청 기록

        Returns:
            실제 대기한 시간 (초)
        """
        rate_check = self.check_rate_limit(exchange_name)

        if not rate_check['allowed']:
            wait_time = rate_check['wait_time']
            if wait_time > 0:
                logger.debug(f"⏳ Rate limit 대기: {exchange_name} - {wait_time:.3f}초 ({rate_check['reason']})")
                time.sleep(wait_time)

                # 평균 대기 시간 업데이트
                stats = self.stats[exchange_name]
                total_requests = stats['total_requests']
                if total_requests > 0:
                    stats['average_wait_time'] = (
                        (stats['average_wait_time'] * (total_requests - 1) + wait_time) / total_requests
                    )

            # 대기 후 다시 체크
            return wait_time + self.wait_if_needed(exchange_name)

        # 요청 기록
        self.record_request(exchange_name)
        return 0.0

    def get_rate_limit_stats(self, exchange_name: Optional[str] = None) -> Dict[str, Any]:
        """Rate limit 통계 조회"""
        with self.lock:
            if exchange_name:
                exchange_name = exchange_name.lower()
                current_time = time.time()

                # 현재 윈도우의 요청 수
                request_queue = self.request_history[exchange_name]
                current_requests = sum(1 for req_time in request_queue if current_time - req_time <= 1.0)

                return {
                    'exchange': exchange_name,
                    'current_requests_per_second': current_requests,
                    'max_requests_per_second': self.rate_limits.get(exchange_name, self.rate_limits['default'])['requests_per_second'],
                    'total_requests': self.stats[exchange_name]['total_requests'],
                    'blocked_requests': self.stats[exchange_name]['blocked_requests'],
                    'average_wait_time': self.stats[exchange_name]['average_wait_time'],
                    'last_request_time': self.last_request_time.get(exchange_name, 0)
                }
            else:
                # 전체 통계
                all_stats = {}
                for exchange in self.stats:
                    all_stats[exchange] = self.get_rate_limit_stats(exchange)
                return all_stats

    def update_rate_limits(self, exchange_name: str, requests_per_second: int, burst_limit: int):
        """거래소별 rate limit 설정 업데이트"""
        with self.lock:
            self.rate_limits[exchange_name.lower()] = {
                'requests_per_second': requests_per_second,
                'burst_limit': burst_limit
            }
            logger.info(f"📊 Rate limit 업데이트: {exchange_name} - {requests_per_second} req/sec, burst: {burst_limit}")

    def clear_history(self, exchange_name: Optional[str] = None):
        """요청 히스토리 클리어"""
        with self.lock:
            if exchange_name:
                exchange_name = exchange_name.lower()
                self.request_history[exchange_name].clear()
                self.last_request_time[exchange_name] = 0
                self.stats[exchange_name] = {
                    'total_requests': 0,
                    'blocked_requests': 0,
                    'average_wait_time': 0.0
                }
                logger.info(f"🗑️ {exchange_name} rate limit 히스토리 클리어")
            else:
                self.request_history.clear()
                self.last_request_time.clear()
                self.stats.clear()
                logger.info("🗑️ 모든 rate limit 히스토리 클리어")


def rate_limited(exchange_name_func=None):
    """
    Rate limiting 데코레이터

    Args:
        exchange_name_func: 거래소 이름을 반환하는 함수 또는 문자열
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 거래소 이름 결정
            if callable(exchange_name_func):
                exchange_name = exchange_name_func(*args, **kwargs)
            elif isinstance(exchange_name_func, str):
                exchange_name = exchange_name_func
            else:
                # 첫 번째 인자가 Account 객체인 경우
                if args and hasattr(args[0], 'exchange'):
                    exchange_name = args[0].exchange
                else:
                    exchange_name = 'default'

            # Rate limit 체크 및 대기
            wait_time = rate_limit_service.wait_if_needed(exchange_name)

            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                logger.error(f"Rate limited 함수 실행 실패: {e}")
                raise

        return wrapper
    return decorator


# 싱글톤 인스턴스
rate_limit_service = RateLimitService()