"""
FastAPI 미들웨어

CORS, 로깅, 예외 처리 등의 미들웨어를 설정합니다.
"""

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import time
import logging
from typing import Callable

from app.config import settings
from app.core.exceptions import AppException

logger = logging.getLogger(__name__)


def setup_cors(app: FastAPI) -> None:
    """CORS 미들웨어 설정"""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=settings.CORS_ALLOW_METHODS,
        allow_headers=settings.CORS_ALLOW_HEADERS,
    )
    logger.info(f"✅ CORS configured: origins={settings.CORS_ORIGINS}")


class LoggingMiddleware(BaseHTTPMiddleware):
    """요청/응답 로깅 미들웨어"""

    async def dispatch(self, request: Request, call_next: Callable):
        start_time = time.time()

        # 요청 로깅
        logger.info(
            f"➡️ {request.method} {request.url.path} "
            f"from {request.client.host if request.client else 'unknown'}"
        )

        # 요청 처리
        response = await call_next(request)

        # 응답 시간 계산
        process_time = (time.time() - start_time) * 1000  # ms

        # 응답 로깅
        log_level = logging.INFO if response.status_code < 400 else logging.WARNING
        logger.log(
            log_level,
            f"⬅️ {request.method} {request.url.path} "
            f"→ {response.status_code} ({process_time:.2f}ms)"
        )

        # 응답 헤더에 처리 시간 추가
        response.headers["X-Process-Time"] = f"{process_time:.2f}ms"

        return response


def setup_exception_handlers(app: FastAPI) -> None:
    """예외 핸들러 설정"""

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        """커스텀 예외 처리"""
        logger.error(
            f"❌ AppException: {exc.message} "
            f"(status={exc.status_code}, details={exc.details})"
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.message,
                "details": exc.details,
                "path": str(request.url),
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """Pydantic 검증 실패 처리"""
        logger.warning(f"⚠️ Validation error: {exc.errors()}")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": "Validation failed",
                "details": exc.errors(),
                "path": str(request.url),
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """일반 예외 처리"""
        logger.exception(f"💥 Unhandled exception: {exc}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "Internal server error",
                "message": str(exc) if settings.DEBUG else "An unexpected error occurred",
                "path": str(request.url),
            },
        )

    logger.info("✅ Exception handlers configured")


def setup_middleware(app: FastAPI) -> None:
    """모든 미들웨어 설정"""
    # CORS
    setup_cors(app)

    # 로깅
    app.add_middleware(LoggingMiddleware)

    # 예외 처리
    setup_exception_handlers(app)

    logger.info("✅ All middleware configured")
