"""
Pytest 설정 및 공통 Fixtures
"""

import pytest
import pytest_asyncio
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.config import settings
from app.db.base import Base


@pytest.fixture(scope="session")
def event_loop():
    """
    세션 범위의 이벤트 루프 생성
    pytest-asyncio에서 비동기 테스트를 위해 필요
    """
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def async_db_engine():
    """
    테스트용 비동기 데이터베이스 엔진
    각 테스트 함수마다 새로운 엔진 생성
    """
    # 테스트 데이터베이스 URL (실제 테스트에서는 별도 테스트 DB 사용 권장)
    test_database_url = settings.DATABASE_URL.replace(
        "/trading_system",
        "/trading_system_test"
    )

    engine = create_async_engine(
        test_database_url,
        poolclass=NullPool,  # 테스트에서는 풀링 비활성화
        echo=False,
    )

    # 테스트 전 테이블 생성
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # 테스트 후 테이블 삭제
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def async_db_session(async_db_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    테스트용 비동기 데이터베이스 세션
    """
    AsyncTestSessionLocal = async_sessionmaker(
        async_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with AsyncTestSessionLocal() as session:
        yield session
