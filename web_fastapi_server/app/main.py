"""
FastAPI 애플리케이션 진입점

비동기 암호화폐 거래 시스템의 메인 애플리케이션
"""

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging

from app.config import settings
from app.core.middleware import setup_middleware
from app.db.session import close_db

# 로깅 설정
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    애플리케이션 생명주기 관리

    startup: 앱 시작 시 실행
    shutdown: 앱 종료 시 실행
    """
    # Startup
    logger.info("🚀 Starting FastAPI Trading Bot Server...")
    logger.info(f"📊 Environment: {settings.ENV}")
    logger.info(f"🔧 Debug Mode: {settings.DEBUG}")
    logger.info(f"🌐 CORS Origins: {settings.CORS_ORIGINS}")

    yield

    # Shutdown
    logger.info("🛑 Shutting down FastAPI Trading Bot Server...")
    await close_db()
    logger.info("✅ Cleanup completed")


# FastAPI 앱 생성
app = FastAPI(
    title="Trading Bot API",
    description="FastAPI 기반 비동기 암호화폐 거래 시스템",
    version="1.0.0-alpha",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# 미들웨어 설정
setup_middleware(app)


@app.get("/", tags=["Root"])
async def root():
    """루트 엔드포인트"""
    return {
        "message": "Welcome to FastAPI Trading Bot API",
        "version": "1.0.0-alpha",
        "docs": "/docs",
        "status": "healthy",
        "environment": settings.ENV,
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """헬스 체크 엔드포인트"""
    return {
        "status": "healthy",
        "environment": settings.ENV,
        "database": "connected",  # TODO: Phase 7에서 실제 DB 연결 확인
    }


@app.get("/ping", tags=["Health"])
async def ping():
    """간단한 핑 엔드포인트"""
    return {"message": "pong"}


# API 라우터 등록 (Phase 2 이후 추가 예정)
# app.include_router(webhook.router, prefix="/api/v1", tags=["Webhook"])
# app.include_router(auth.router, prefix="/api/v1", tags=["Auth"])
# app.include_router(strategies.router, prefix="/api/v1", tags=["Strategies"])
# app.include_router(accounts.router, prefix="/api/v1", tags=["Accounts"])
# app.include_router(orders.router, prefix="/api/v1", tags=["Orders"])
# app.include_router(positions.router, prefix="/api/v1", tags=["Positions"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )
