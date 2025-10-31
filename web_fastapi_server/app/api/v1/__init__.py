"""
API v1

버전 1 API 엔드포인트
"""

from fastapi import APIRouter
from app.api.v1 import cancel_queue, webhook

api_router = APIRouter(prefix="/api/v1")

# 라우터 등록
api_router.include_router(cancel_queue.router)
api_router.include_router(webhook.router)

__all__ = ["api_router"]
