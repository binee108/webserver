"""
FastAPI 의존성 주입

공통으로 사용하는 의존성들을 정의합니다.
"""

from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db

# DB 세션 의존성 (re-export)
__all__ = ["get_db"]
