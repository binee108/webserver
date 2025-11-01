"""
Cancel Queue Worker

주기적으로 Cancel Queue를 polling하여 PENDING 주문을 취소 처리합니다.

@FEAT:cancel-queue @COMP:job @TYPE:core
"""

import asyncio
import logging
from datetime import datetime, timedelta
from collections import defaultdict
from typing import List, Tuple, Optional, Dict, Any

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cancel_queue import CancelQueue
from app.models.account import Account
from app.db.session import AsyncSessionLocal
from app.exchanges import get_exchange_adapter
from app.exchanges.exceptions import (
    OrderNotFoundException,
    ExchangeAPIError,
    ExchangeServerError,
    ExchangeAuthError
)

logger = logging.getLogger(__name__)


class CancelQueueWorker:
    """
    Cancel Queue 백그라운드 워커

    주기적으로 PENDING 상태의 취소 요청을 처리합니다.

    @FEAT:cancel-queue @COMP:job @TYPE:core
    """

    def __init__(self, poll_interval: int = 5):
        """
        Args:
            poll_interval: Polling 간격 (초)
        """
        self.poll_interval = poll_interval
        self.running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """워커 시작"""
        self.running = True
        self._task = asyncio.create_task(self._run())
        logger.info("✅ Cancel Queue Worker started")

    async def stop(self):
        """워커 종료"""
        self.running = False
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=30.0)
            except asyncio.TimeoutError:
                logger.warning("⚠️ Worker stop timeout, force cancelling")
                self._task.cancel()
        logger.info("🛑 Cancel Queue Worker stopped")

    async def _run(self):
        """메인 루프"""
        while self.running:
            try:
                await self._process_queue()
            except Exception as e:
                logger.error(f"❌ Unexpected error in worker loop: {e}", exc_info=True)

            await asyncio.sleep(self.poll_interval)

    async def _process_queue(self):
        """
        큐 처리 로직

        @FEAT:cancel-queue @COMP:job @TYPE:core
        """
        async with AsyncSessionLocal() as db:
            try:
                # 1. PENDING 또는 재시도 대상 조회
                items = await self._fetch_pending_items(db)

                if not items:
                    # Early Return (빈 큐는 로그 없음)
                    return

                # 2. 거래소별로 취소 실행
                await self._process_batch(items, db)

            except Exception as e:
                await db.rollback()
                logger.error(f"❌ Queue processing failed: {e}", exc_info=True)

    async def _fetch_pending_items(self, db: AsyncSession) -> List[CancelQueue]:
        """
        처리 대상 큐 아이템 조회 (중복 처리 방지)

        @FEAT:cancel-queue @COMP:job @TYPE:core

        SELECT FOR UPDATE를 사용하여 여러 워커가 같은 아이템을 처리하지 않도록 방지합니다.
        """
        now = datetime.utcnow()

        stmt = (
            select(CancelQueue)
            .with_for_update(skip_locked=True)  # 중복 처리 방지
            .where(
                CancelQueue.status.in_(['PENDING', 'PROCESSING']),
                or_(
                    CancelQueue.next_retry_at.is_(None),
                    CancelQueue.next_retry_at <= now
                )
            )
            .limit(100)  # 배치 사이즈
        )

        result = await db.execute(stmt)
        items = result.scalars().all()

        # 즉시 PROCESSING으로 변경 (같은 트랜잭션)
        for item in items:
            item.status = 'PROCESSING'
        await db.commit()

        logger.debug(f"🔍 Cancel queue fetched: {len(items)} items")

        return items

    async def _process_batch(self, items: List[CancelQueue], db: AsyncSession):
        """
        배치 처리 (거래소별 병렬)

        @FEAT:cancel-queue @COMP:job @TYPE:core
        """
        # 거래소별로 그룹화
        by_exchange: Dict[str, List[CancelQueue]] = defaultdict(list)
        for item in items:
            by_exchange[item.exchange].append(item)

        # 거래소별 병렬 처리
        tasks = []
        for exchange, exchange_items in by_exchange.items():
            task = self._process_exchange_batch(exchange_items, db)
            tasks.append(task)

        # 예외 격리
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 결과 처리
        success_count = 0
        retry_count = 0
        failed_count = 0

        for result in results:
            if isinstance(result, Exception):
                logger.error(f"❌ Exchange batch processing failed: {result}")
            elif isinstance(result, dict):
                success_count += result.get('success', 0)
                retry_count += result.get('retry', 0)
                failed_count += result.get('failed', 0)

        # 처리 요약 (DEBUG)
        logger.debug(
            f"🔄 Cancel queue processed: "
            f"total={len(items)}, "
            f"success={success_count}, "
            f"retry={retry_count}, "
            f"failed={failed_count}"
        )

    async def _process_exchange_batch(
        self,
        items: List[CancelQueue],
        db: AsyncSession
    ) -> Dict[str, int]:
        """
        거래소별 배치 처리

        @FEAT:cancel-queue @COMP:job @TYPE:core

        Returns:
            처리 결과 카운트 {'success': X, 'retry': Y, 'failed': Z}
        """
        success_count = 0
        retry_count = 0
        failed_count = 0

        # 계좌 정보 조회 (첫 번째 아이템의 exchange 사용)
        if not items:
            return {'success': 0, 'retry': 0, 'failed': 0}

        exchange_name = items[0].exchange

        # 각 아이템 처리
        for item in items:
            try:
                # Account 정보 조회
                account_stmt = select(Account).where(Account.id == item.account_id)
                account_result = await db.execute(account_stmt)
                account = account_result.scalar_one_or_none()

                if not account:
                    item.mark_failed("Account not found")
                    await db.commit()
                    failed_count += 1
                    logger.error(f"❌ Account not found: account_id={item.account_id}")
                    continue

                # Exchange adapter 생성
                adapter = get_exchange_adapter(
                    exchange_name,
                    api_key=account.public_api,
                    api_secret=account.secret_api
                )

                # 취소 실행
                success, error_message = await self._cancel_single_order(item, adapter, db)

                if success:
                    success_count += 1
                elif item.can_retry:
                    retry_count += 1
                else:
                    failed_count += 1

            except Exception as e:
                # 예외 처리
                error_message = str(e)
                await self._handle_cancel_result(item, False, error_message, db)
                if item.can_retry:
                    retry_count += 1
                else:
                    failed_count += 1

        return {'success': success_count, 'retry': retry_count, 'failed': failed_count}

    async def _cancel_single_order(
        self,
        item: CancelQueue,
        adapter,
        db: AsyncSession
    ) -> Tuple[bool, Optional[str]]:
        """
        단일 주문 취소 실행

        @FEAT:cancel-queue @COMP:job @TYPE:core

        Returns:
            (success, error_message)
        """
        try:
            # Exchange adapter로 취소 요청
            result = await adapter.cancel_order(
                symbol=item.symbol,
                order_id=item.exchange_order_id
            )

            # 성공 처리
            await self._handle_cancel_result(item, True, None, db)
            return True, None

        except OrderNotFoundException:
            # 주문이 이미 취소되었거나 체결됨 (멱등성)
            await self._handle_cancel_result(item, True, None, db)
            return True, None

        except (ExchangeAuthError, ExchangeAPIError) as e:
            # 재시도 불가능한 에러
            error_message = str(e)
            await self._handle_cancel_result(item, False, error_message, db)
            return False, error_message

        except (ExchangeServerError, Exception) as e:
            # 재시도 가능한 에러
            error_message = str(e)
            if self._is_retriable_error(error_message):
                await self._handle_cancel_result(item, False, error_message, db)
                return False, error_message
            else:
                # 재시도 불가능
                await self._handle_cancel_result(item, False, error_message, db)
                return False, error_message

    def _is_retriable_error(self, error_message: str) -> bool:
        """
        재시도 가능한 에러인지 판단

        @FEAT:cancel-queue @COMP:job @TYPE:helper

        Non-Retriable 에러:
        - 400 (Bad Request): 잘못된 요청 파라미터
        - 401 (Unauthorized): 인증 실패
        - 403 (Forbidden): 권한 없음
        - 404 (Not Found): 주문 미존재

        Retriable 에러:
        - timeout: 네트워크 타임아웃
        - network_error: 네트워크 연결 오류
        - rate_limit: 요청 속도 제한
        - 500 (Internal Server Error): 거래소 서버 오류
        - 503 (Service Unavailable): 서비스 일시 중단
        - 504 (Gateway Timeout): 게이트웨이 타임아웃

        기본값: True (보수적 접근 - 알 수 없는 에러는 재시도)
        """
        error_lower = error_message.lower()

        # Non-retriable 먼저 체크
        NON_RETRIABLE_ERRORS = ['400', '401', '403', '404']
        if any(err in error_lower for err in NON_RETRIABLE_ERRORS):
            return False

        # Retriable 체크
        RETRIABLE_ERRORS = ['timeout', 'network_error', 'rate_limit', '500', '503', '504']
        if any(err in error_lower for err in RETRIABLE_ERRORS):
            return True

        # 기본값: 재시도 (보수적 접근)
        return True

    def _calculate_next_retry(self, retry_count: int) -> datetime:
        """
        다음 재시도 시각 계산 (exponential backoff)

        @FEAT:cancel-queue @COMP:job @TYPE:helper

        재시도 간격:
        - 0회: 1분 (60초)
        - 1회: 2분 (120초)
        - 2회: 4분 (240초)
        - 3회: 8분 (480초)
        - 4회: 16분 (960초)
        - 5회 이상: 1시간 (3600초, 최대값)

        Args:
            retry_count: 현재 재시도 횟수 (0부터 시작)

        Returns:
            다음 재시도 시각 (UTC)
        """
        delay_seconds = min(60 * (2 ** retry_count), 3600)  # 최대 1시간
        return datetime.utcnow() + timedelta(seconds=delay_seconds)

    async def _handle_cancel_result(
        self,
        item: CancelQueue,
        success: bool,
        error_message: Optional[str],
        db: AsyncSession
    ):
        """
        취소 결과 처리

        @FEAT:cancel-queue @COMP:job @TYPE:core
        """
        if success:
            item.mark_success()
            logger.info(f"✅ Order cancelled: order_id={item.order_id}, exchange={item.exchange}")
        else:
            if item.can_retry:
                next_retry = self._calculate_next_retry(item.retry_count)
                item.increment_retry(next_retry)
                logger.warning(
                    f"⚠️ Cancel retry scheduled: "
                    f"order_id={item.order_id}, "
                    f"retry={item.retry_count}/{item.max_retries}, "
                    f"next_retry={next_retry.isoformat()}, "
                    f"error={error_message}"
                )
            else:
                item.mark_failed(error_message or "Max retries exceeded")
                logger.error(
                    f"❌ Cancel permanently failed: "
                    f"order_id={item.order_id}, "
                    f"retries={item.retry_count}, "
                    f"error={error_message}"
                )

        await db.commit()
