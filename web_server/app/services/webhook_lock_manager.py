"""
웹훅 동시 처리를 위한 Lock 관리자

@FEAT:webhook-concurrency-fix @COMP:service @TYPE:core @DEPS:webhook-order

동일 전략+심볼의 웹훅을 직렬화하여 경쟁 조건(Race Condition)을 방지합니다.

주요 특징:
- Lock 범위: (strategy_id, symbol) 조합 단위
- 데드락 방지: 정렬된 순서로 Lock 획득/해제
- 성능: 다른 전략/심볼은 병렬 처리
- 스레드 안전성: 내부 Lock dict도 보호
"""

import os
import time
import logging
import threading
from typing import Dict, Optional, List
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# 환경변수 설정
WEBHOOK_LOCK_TIMEOUT = int(os.getenv("WEBHOOK_LOCK_TIMEOUT", "30"))
MAX_WEBHOOK_LOCKS = int(os.getenv("MAX_WEBHOOK_LOCKS", "1000"))


class WebhookLockManager:
    """
    웹훅 동시 처리를 위한 전략+심볼 단위 Lock 관리자

    동일 전략/심볼 웹훅을 직렬화하여 경쟁 조건 방지:
    - Lock 범위: (strategy_id, symbol) 조합
    - 데드락 방지: 정렬된 Lock 획득 순서
    - 성능 유지: 다른 전략/심볼은 병렬 처리

    예시:
        lock_manager = WebhookLockManager()
        with lock_manager.acquire_webhook_lock(strategy_id=1, symbols=["BTCUSDT"]):
            # 동시성 보호된 코드 실행
            process_webhook()
    """

    def __init__(self):
        """WebhookLockManager 초기화"""
        # Lock dict 자체를 보호하는 Lock
        self._locks_dict_lock = threading.Lock()
        # 전략+심볼별 Lock 저장소
        self._strategy_symbol_locks: Dict[str, threading.Lock] = {}
        logger.info("✅ WebhookLockManager 초기화 완료")

    def _get_lock_key(self, strategy_id: int, symbol: str) -> str:
        """
        전략+심볼 조합으로 유니크 Lock 키 생성

        Args:
            strategy_id (int): 전략 ID
            symbol (str): 거래 심볼

        Returns:
            str: Lock 키 (형식: "strategy_{id}_symbol_{symbol}")
        """
        return f"strategy_{strategy_id}_symbol_{symbol}"

    @contextmanager
    def acquire_webhook_lock(
        self,
        strategy_id: int,
        symbols: List[str],
        timeout: Optional[int] = None,
    ):
        """
        웹훅 처리를 위한 전략+심볼 Lock 획득

        동일 전략/심볼의 웹훅은 순차 처리되며, 다른 전략/심볼은 병렬 처리됩니다.

        Args:
            strategy_id (int): 전략 ID
            symbols (List[str]): 심볼 목록 (배치 모드에서 여러 심볼 가능)
            timeout (Optional[int]): Lock 획득 타임아웃 (초 단위)
                                    기본값: WEBHOOK_LOCK_TIMEOUT 환경변수 또는 30초

        Raises:
            TimeoutError: Lock 획득 실패 (타임아웃)
            RuntimeError: Lock pool 초과

        Yields:
            None

        Example:
            try:
                with lock_manager.acquire_webhook_lock(
                    strategy_id=1,
                    symbols=["BTCUSDT", "ETHUSDT"],
                    timeout=10
                ):
                    # 임계 섹션: 동시성 보호됨
                    process_webhook_batch()
            except TimeoutError:
                logger.error("Lock 획득 실패")
        """
        # 기본 타임아웃 설정
        timeout = timeout if timeout is not None else WEBHOOK_LOCK_TIMEOUT

        # 1. Lock 키 생성 및 정렬 (데드락 방지)
        lock_keys = sorted(
            [self._get_lock_key(strategy_id, symbol) for symbol in symbols]
        )

        # 2. Lock 객체 준비 (없으면 생성)
        locks_to_acquire = []
        with self._locks_dict_lock:
            for key in lock_keys:
                if key not in self._strategy_symbol_locks:
                    # Lock pool 크기 제한 체크
                    if len(self._strategy_symbol_locks) >= MAX_WEBHOOK_LOCKS:
                        logger.error(
                            f"❌ Lock pool exhausted: {len(self._strategy_symbol_locks)} "
                            f"locks (max: {MAX_WEBHOOK_LOCKS})"
                        )
                        raise RuntimeError(
                            f"Lock pool exhausted (max: {MAX_WEBHOOK_LOCKS}). "
                            f"Consider increasing MAX_WEBHOOK_LOCKS."
                        )
                    self._strategy_symbol_locks[key] = threading.Lock()

                locks_to_acquire.append((key, self._strategy_symbol_locks[key]))

        # 3. Lock 획득 (정렬된 순서)
        acquired_locks = []
        try:
            for key, lock in locks_to_acquire:
                start_time = time.time()

                # Lock 획득 시도
                if not lock.acquire(timeout=timeout):
                    raise TimeoutError(
                        f"Lock acquisition timeout for {key} (timeout: {timeout}s)"
                    )

                # Lock 대기 시간 모니터링
                wait_time = time.time() - start_time
                if wait_time > 5:  # 5초 이상 대기 시 경고
                    logger.warning(
                        f"⏱️ Lock waited {wait_time:.2f}s for {key} "
                        f"(timeout: {timeout}s)"
                    )
                else:
                    logger.debug(
                        f"🔒 Acquired lock for {key} (waited {wait_time:.2f}s)"
                    )

                acquired_locks.append(lock)

            # 임계 섹션 실행
            yield

        except TimeoutError:
            # Lock 획득 실패
            logger.error(
                f"❌ Failed to acquire lock for strategy {strategy_id} "
                f"symbols {symbols} (timeout: {timeout}s)"
            )
            raise

        finally:
            # 4. Lock 해제 (역순으로 해제하여 데드락 방지)
            for lock in reversed(acquired_locks):
                try:
                    lock.release()
                except RuntimeError:
                    # Lock이 이미 해제된 경우 (드문 경우)
                    logger.debug("⚠️ Lock already released")

            released_count = len(acquired_locks)
            if released_count > 0:
                logger.debug(
                    f"🔓 Released {released_count} lock(s) for "
                    f"strategy {strategy_id}"
                )


# 싱글톤 인스턴스
webhook_lock_manager = WebhookLockManager()
