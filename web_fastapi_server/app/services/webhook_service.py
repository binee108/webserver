"""
Webhook Service

비동기 웹훅 처리 서비스 - TradingView 및 외부 트레이딩 신호 수신
"""

import logging
import time
import asyncio
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import Strategy, Account, StrategyAccount, User
from app.schemas.webhook import (
    WebhookRequest,
    WebhookResponse,
    OrderResult,
    OrderSummary,
    PerformanceMetrics,
    OrderTypeEnum,
)
from app.exchanges import get_exchange_adapter
from app.core.exceptions import WebhookException

logger = logging.getLogger(__name__)


class WebhookService:
    """
    웹훅 서비스 클래스

    외부 트레이딩 신호를 받아 비동기로 처리합니다.
    Phase 4: MARKET/CANCEL 주문만 지원
    """

    async def _validate_strategy_token(
        self,
        db: AsyncSession,
        group_name: str,
        token: str
    ) -> Strategy:
        """
        전략 조회 및 토큰 검증 (비동기)

        Flask webhook_service._validate_strategy_token()과 동일한 로직을
        비동기로 구현합니다.

        Args:
            db: 비동기 DB 세션
            group_name: 전략 그룹명
            token: 웹훅 인증 토큰

        Returns:
            Strategy: 검증된 전략 객체

        Raises:
            WebhookException: 전략을 찾을 수 없거나 토큰이 유효하지 않은 경우
        """
        # 전략 조회 (관계 eager loading)
        stmt = (
            select(Strategy)
            .options(
                selectinload(Strategy.user),
                selectinload(Strategy.strategy_accounts)
                .selectinload(StrategyAccount.account)
                .selectinload(Account.user)
            )
            .where(Strategy.group_name == group_name, Strategy.is_active == True)
        )
        result = await db.execute(stmt)
        strategy = result.scalar_one_or_none()

        if not strategy:
            raise WebhookException(f"활성 전략을 찾을 수 없습니다: {group_name}")

        if not token:
            raise WebhookException("웹훅 토큰이 필요합니다")

        # 허용되는 토큰 집합 구성 (Flask 로직과 동일)
        valid_tokens = set()

        # 전략 소유자의 토큰
        if strategy.user and strategy.user.webhook_token:
            valid_tokens.add(strategy.user.webhook_token)

        # 공개 전략의 경우: 구독자(연결된 계좌의 사용자) 토큰도 허용
        if strategy.is_public:
            try:
                for sa in strategy.strategy_accounts:
                    if sa.is_active and sa.account and sa.account.user:
                        user_token = sa.account.user.webhook_token
                        if user_token:
                            valid_tokens.add(user_token)
            except Exception as e:
                logger.warning(f"구독자 토큰 수집 중 오류 (무시됨): {e}")

        if not valid_tokens:
            raise WebhookException(
                "웹훅 토큰이 설정된 사용자가 없습니다. "
                "전략 소유자 또는 구독자의 토큰을 생성하세요"
            )

        if token not in valid_tokens:
            raise WebhookException("웹훅 토큰이 유효하지 않습니다")

        logger.info(
            f"✅ 전략 검증 완료 - ID: {strategy.id}, "
            f"이름: {strategy.name}, 그룹: {group_name}"
        )

        return strategy

    async def _execute_market_orders(
        self,
        strategy: Strategy,
        webhook: WebhookRequest
    ) -> List[OrderResult]:
        """
        MARKET 주문 병렬 실행

        Phase 3 Exchange Adapters를 활용하여 모든 연결된 계좌에
        동시에 MARKET 주문을 실행합니다.

        Args:
            strategy: 검증된 전략 객체
            webhook: 웹훅 요청 데이터

        Returns:
            List[OrderResult]: 계좌별 주문 실행 결과
        """
        logger.info(
            f"⚡ MARKET 주문 병렬 실행 시작 - "
            f"전략: {strategy.name}, 심볼: {webhook.symbol}, "
            f"수량: {webhook.quantity}"
        )

        # 활성 계좌만 필터링
        active_accounts = [
            sa for sa in strategy.strategy_accounts
            if sa.is_active and sa.account and sa.account.is_active
        ]

        if not active_accounts:
            logger.warning(f"활성 계좌가 없습니다 - 전략: {strategy.name}")
            return []

        logger.info(f"📋 활성 계좌 수: {len(active_accounts)}")

        # 비동기 주문 태스크 생성
        tasks = []
        for sa in active_accounts:
            account = sa.account
            task = self._execute_single_market_order(
                account=account,
                symbol=webhook.symbol,
                side=webhook.side,
                quantity=webhook.quantity,
                exchange_filter=webhook.exchange  # 선택적 거래소 필터
            )
            tasks.append(task)

        # 병렬 실행 (예외 격리)
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 결과 처리
        order_results = []
        for idx, result in enumerate(results):
            account = active_accounts[idx].account

            if isinstance(result, Exception):
                logger.error(
                    f"❌ 주문 실패 - 계좌: {account.name}, "
                    f"오류: {str(result)}"
                )
                order_results.append(
                    OrderResult(
                        account_id=account.id,
                        account_name=account.name,
                        exchange=account.exchange,
                        symbol=webhook.symbol,
                        success=False,
                        error=str(result)
                    )
                )
            else:
                order_results.append(result)

        return order_results

    async def _execute_single_market_order(
        self,
        account: Account,
        symbol: str,
        side: str,
        quantity: float,
        exchange_filter: Optional[str] = None
    ) -> OrderResult:
        """
        단일 계좌에 MARKET 주문 실행

        Args:
            account: 계좌 객체
            symbol: 거래 심볼 (예: BTC/USDT)
            side: 주문 방향 (BUY or SELL)
            quantity: 주문 수량
            exchange_filter: 특정 거래소만 실행 (선택적)

        Returns:
            OrderResult: 주문 실행 결과
        """
        try:
            # 거래소 필터 체크
            if exchange_filter and account.exchange.upper() != exchange_filter.upper():
                logger.info(
                    f"⏭️ 거래소 불일치로 스킵 - "
                    f"계좌: {account.name} ({account.exchange}), "
                    f"요청: {exchange_filter}"
                )
                return OrderResult(
                    account_id=account.id,
                    account_name=account.name,
                    exchange=account.exchange,
                    symbol=symbol,
                    success=False,
                    error=f"거래소 불일치 (요청: {exchange_filter})"
                )

            # Phase 3 Exchange Adapter 가져오기
            # TODO: API 키 복호화 로직 필요 (Flask의 decrypt_value 함수)
            # 현재는 암호화되지 않은 상태로 가정
            adapter = get_exchange_adapter(
                exchange_name=account.exchange,
                api_key=account.public_api,
                api_secret=account.secret_api
            )

            logger.info(
                f"📤 주문 생성 중 - 계좌: {account.name}, "
                f"거래소: {account.exchange}, 심볼: {symbol}"
            )

            # MARKET 주문 실행
            order_data = await adapter.create_order(
                symbol=symbol,
                side=side.lower(),
                order_type="market",
                quantity=quantity
            )

            logger.info(
                f"✅ 주문 성공 - 계좌: {account.name}, "
                f"주문ID: {order_data.get('order_id')}"
            )

            return OrderResult(
                account_id=account.id,
                account_name=account.name,
                exchange=account.exchange,
                symbol=symbol,
                success=True,
                order_id=order_data.get("order_id"),
                executed_quantity=order_data.get("executed_quantity"),
                executed_price=order_data.get("executed_price")
            )

        except Exception as e:
            logger.error(
                f"❌ 주문 실패 - 계좌: {account.name}, "
                f"오류: {str(e)}", exc_info=True
            )
            return OrderResult(
                account_id=account.id,
                account_name=account.name,
                exchange=account.exchange,
                symbol=symbol,
                success=False,
                error=str(e)
            )

    async def _queue_cancel_orders(
        self,
        strategy: Strategy,
        webhook: WebhookRequest
    ) -> List[OrderResult]:
        """
        CANCEL 주문 큐 진입

        Phase 2 Cancel Queue를 활용하여 미체결 주문 취소를 처리합니다.

        Args:
            strategy: 검증된 전략 객체
            webhook: 웹훅 요청 데이터

        Returns:
            List[OrderResult]: 계좌별 취소 요청 결과
        """
        logger.info(
            f"🔄 CANCEL 주문 처리 - "
            f"전략: {strategy.name}, 심볼: {webhook.symbol}"
        )

        # Phase 2 Cancel Queue 통합은 향후 구현
        # 현재는 placeholder 응답 반환
        logger.warning("⚠️ CANCEL 주문은 Phase 2 Cancel Queue 통합이 필요합니다")

        return [
            OrderResult(
                account_id=0,
                account_name="placeholder",
                exchange="placeholder",
                symbol=webhook.symbol,
                success=False,
                error="CANCEL 주문은 현재 구현 중입니다 (Phase 2 통합 필요)"
            )
        ]

    async def process_webhook(
        self,
        db: AsyncSession,
        webhook: WebhookRequest,
        webhook_received_at: float
    ) -> Dict[str, Any]:
        """
        웹훅 처리 메인 로직

        1. 전략/토큰 검증
        2. 주문 타입 분기 (MARKET/CANCEL)
        3. 거래소 API 호출 (비동기 병렬)
        4. 결과 수집 및 반환

        Args:
            db: 비동기 DB 세션
            webhook: 검증된 웹훅 요청 데이터
            webhook_received_at: 웹훅 수신 시각 (Unix timestamp)

        Returns:
            Dict: 웹훅 처리 결과
        """
        validation_start = time.time()

        # 1. 전략/토큰 검증 (비동기 DB 쿼리)
        strategy = await self._validate_strategy_token(
            db=db,
            group_name=webhook.group_name,
            token=webhook.token
        )

        validation_time_ms = (time.time() - validation_start) * 1000
        execution_start = time.time()

        # 2. 주문 타입 분기
        results: List[OrderResult] = []

        if webhook.order_type == OrderTypeEnum.MARKET:
            # MARKET: 즉시 실행 경로
            logger.info(f"⚡ MARKET 주문 처리 시작 - 전략: {strategy.name}")
            results = await self._execute_market_orders(strategy, webhook)

        elif webhook.order_type == OrderTypeEnum.CANCEL:
            # CANCEL: Cancel Queue 진입 (Phase 2)
            logger.info(f"🔄 CANCEL 주문 처리 시작 - 전략: {strategy.name}")
            results = await self._queue_cancel_orders(strategy, webhook)

        else:
            # Phase 4에서는 LIMIT/STOP 미지원 (validator에서 차단됨)
            raise WebhookException(
                f"지원하지 않는 주문 타입: {webhook.order_type}. "
                f"Phase 4에서는 MARKET/CANCEL만 지원됩니다."
            )

        execution_time_ms = (time.time() - execution_start) * 1000
        total_time_ms = (time.time() - webhook_received_at) * 1000

        # 3. 결과 집계
        successful_orders = sum(1 for r in results if r.success)
        failed_orders = sum(1 for r in results if not r.success)
        total_accounts = len(results)

        logger.info(
            f"📊 웹훅 처리 완료 - 전략: {strategy.name}, "
            f"성공: {successful_orders}/{total_accounts}, "
            f"처리시간: {total_time_ms:.2f}ms"
        )

        # 4. 응답 생성
        return {
            "success": successful_orders > 0,
            "action": webhook.action,
            "strategy": strategy.name,
            "message": (
                f"웹훅 처리 완료 - 성공: {successful_orders}, 실패: {failed_orders}"
            ),
            "results": [r.dict() for r in results],
            "summary": OrderSummary(
                total_accounts=total_accounts,
                successful_orders=successful_orders,
                failed_orders=failed_orders,
                success_rate=round(
                    (successful_orders / total_accounts * 100) if total_accounts > 0 else 0,
                    2
                )
            ).dict(),
            "performance_metrics": PerformanceMetrics(
                total_processing_time_ms=round(total_time_ms, 2),
                validation_time_ms=round(validation_time_ms, 2),
                execution_time_ms=round(execution_time_ms, 2)
            ).dict()
        }


# 전역 인스턴스
webhook_service = WebhookService()
