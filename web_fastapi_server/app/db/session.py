"""
비동기 데이터베이스 세션 관리

SQLAlchemy 2.0 비동기 모드를 사용한 DB 연결 및 세션 관리
"""

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
    AsyncEngine,
)
from sqlalchemy.pool import NullPool
from typing import AsyncGenerator
import logging

from app.config import settings

logger = logging.getLogger(__name__)

# 비동기 엔진 생성
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,  # SQL 쿼리 로깅 (디버그 모드에서만)
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=settings.DB_POOL_PRE_PING,
    pool_recycle=3600,  # 1시간마다 커넥션 재생성
    # 테스트 환경에서는 NullPool 사용
    poolclass=NullPool if settings.ENV == "test" else None,
)

# 비동기 세션 팩토리
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # commit 후에도 객체 접근 가능
    autocommit=False,
    autoflush=False,
)

logger.info(
    f"✅ Database engine created: "
    f"pool_size={settings.DB_POOL_SIZE}, "
    f"max_overflow={settings.DB_MAX_OVERFLOW}"
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI 의존성으로 사용할 DB 세션 생성기

    Usage:
        @app.get("/items/")
        async def read_items(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(Item))
            return result.scalars().all()
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"❌ Database session error: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """
    데이터베이스 초기화

    Note: Alembic을 사용하므로 실제로는 마이그레이션으로 테이블 생성
    이 함수는 테스트 환경에서만 사용
    """
    from app.db.base import Base

    if settings.ENV == "test":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        logger.info("🧪 Test database initialized")


async def close_db() -> None:
    """데이터베이스 연결 종료"""
    await engine.dispose()
    logger.info("🔌 Database connections closed")
