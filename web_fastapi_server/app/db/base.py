"""
SQLAlchemy Base 클래스

모든 모델이 상속받는 DeclarativeBase
"""

from sqlalchemy.orm import DeclarativeBase
from typing import Any


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 스타일 Base 클래스"""

    # 타입 힌트를 위한 공통 속성
    __name__: str

    # 모든 모델에 적용될 설정
    __table_args__ = {"extend_existing": True}

    def dict(self) -> dict[str, Any]:
        """모델을 딕셔너리로 변환"""
        return {
            column.name: getattr(self, column.name)
            for column in self.__table__.columns
        }

    def __repr__(self) -> str:
        """모델 repr 기본 구현"""
        class_name = self.__class__.__name__
        attributes = ", ".join(
            f"{key}={value!r}"
            for key, value in self.dict().items()
            if not key.startswith("_")
        )
        return f"{class_name}({attributes})"
