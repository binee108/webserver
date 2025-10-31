"""
Webhook API 엔드포인트

외부 트레이딩 신호 (TradingView 등)를 수신하는 웹훅 엔드포인트
"""

import logging
import time
import asyncio
from typing import Any, Dict
from fastapi import APIRouter, BackgroundTasks, Request, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.webhook import WebhookRequest, WebhookResponse, WebhookErrorResponse
from app.services.webhook_service import webhook_service
from app.core.exceptions import WebhookException
from app.dependencies import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhook"])


@router.post(
    "",
    response_model=WebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="웹훅 수신",
    description="""
    외부 트레이딩 신호 (TradingView, 커스텀 봇 등)를 수신하여 처리합니다.

    **Phase 4 제한사항:**
    - MARKET 주문: 즉시 실행
    - CANCEL 주문: Cancel Queue 진입 (Phase 2)
    - LIMIT/STOP 주문: Phase 5에서 구현 예정

    **타임아웃:**
    - 최대 10초 (asyncio.wait_for 사용)
    - 타임아웃 발생 시에도 HTTP 200 반환 (TradingView 재전송 방지)

    **백그라운드 작업:**
    - DB 로그 저장은 응답 후 백그라운드에서 처리
    """
)
async def receive_webhook(
    webhook: WebhookRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    웹훅 수신 엔드포인트

    Args:
        webhook: Pydantic으로 자동 검증된 웹훅 요청 데이터
        background_tasks: FastAPI 백그라운드 작업 관리자
        request: FastAPI Request 객체
        db: 비동기 DB 세션

    Returns:
        Dict: 웹훅 처리 결과 (WebhookResponse 스키마)
    """
    webhook_received_at = time.time()

    logger.info(
        f"🔔 웹훅 수신 - 전략: {webhook.group_name}, "
        f"타입: {webhook.order_type}, 심볼: {webhook.symbol}"
    )

    try:
        # 10초 타임아웃 설정 (비동기 네이티브)
        result = await asyncio.wait_for(
            webhook_service.process_webhook(
                db=db,
                webhook=webhook,
                webhook_received_at=webhook_received_at
            ),
            timeout=10.0
        )

        # 백그라운드 DB 저장 (응답 후 실행)
        background_tasks.add_task(
            save_webhook_log,
            webhook_data=webhook.dict(),
            result=result,
            webhook_received_at=webhook_received_at
        )

        logger.info(
            f"✅ 웹훅 처리 완료 - 전략: {webhook.group_name}, "
            f"처리시간: {result['performance_metrics']['total_processing_time_ms']:.2f}ms"
        )

        return result

    except asyncio.TimeoutError:
        # 타임아웃 발생 시에도 HTTP 200 반환 (TradingView 재전송 방지)
        logger.error(
            f"⏱️ 웹훅 처리 타임아웃 (10s) - "
            f"전략: {webhook.group_name}"
        )

        error_response = {
            "success": False,
            "error": "Webhook processing timeout (10s)",
            "timeout": True,
            "processing_time_ms": 10000.0
        }

        # 타임아웃도 백그라운드 로그 저장
        background_tasks.add_task(
            save_webhook_log,
            webhook_data=webhook.dict(),
            result=error_response,
            webhook_received_at=webhook_received_at
        )

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=error_response
        )

    except WebhookException as e:
        # 웹훅 비즈니스 로직 에러 (HTTP 200 + error)
        logger.error(
            f"❌ 웹훅 처리 실패 - 전략: {webhook.group_name}, "
            f"오류: {e.message}"
        )

        processing_time_ms = (time.time() - webhook_received_at) * 1000

        error_response = {
            "success": False,
            "error": e.message,
            "processing_time_ms": round(processing_time_ms, 2)
        }

        # 에러도 백그라운드 로그 저장
        background_tasks.add_task(
            save_webhook_log,
            webhook_data=webhook.dict(),
            result=error_response,
            webhook_received_at=webhook_received_at
        )

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=error_response
        )

    except Exception as e:
        # 예상치 못한 오류 (HTTP 500)
        logger.error(
            f"💥 웹훅 처리 중 예상치 못한 오류 - "
            f"전략: {webhook.group_name}, 오류: {str(e)}",
            exc_info=True
        )

        processing_time_ms = (time.time() - webhook_received_at) * 1000

        error_response = {
            "success": False,
            "error": f"Internal server error: {str(e)}",
            "processing_time_ms": round(processing_time_ms, 2)
        }

        # 예외도 백그라운드 로그 저장
        background_tasks.add_task(
            save_webhook_log,
            webhook_data=webhook.dict(),
            result=error_response,
            webhook_received_at=webhook_received_at
        )

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_response
        )


async def save_webhook_log(
    webhook_data: Dict[str, Any],
    result: Dict[str, Any],
    webhook_received_at: float
) -> None:
    """
    웹훅 로그 비동기 저장 (백그라운드 작업)

    응답 후 실행되어 레이턴시에 영향을 주지 않습니다.

    Args:
        webhook_data: 웹훅 요청 데이터
        result: 웹훅 처리 결과
        webhook_received_at: 웹훅 수신 시각
    """
    try:
        # TODO: WebhookLog 모델 생성 및 DB 저장 로직 구현
        # Phase 4 현재는 로깅만 수행
        logger.info(
            f"📝 웹훅 로그 저장 (백그라운드) - "
            f"전략: {webhook_data.get('group_name')}, "
            f"성공: {result.get('success')}"
        )

        # 향후 구현:
        # async with AsyncSessionLocal() as session:
        #     webhook_log = WebhookLog(
        #         payload=str(webhook_data),
        #         status="success" if result["success"] else "failed",
        #         webhook_received_at=webhook_received_at,
        #         response=str(result)
        #     )
        #     session.add(webhook_log)
        #     await session.commit()

    except Exception as e:
        logger.error(
            f"❌ 웹훅 로그 저장 실패 (백그라운드): {str(e)}",
            exc_info=True
        )
