"""
User 모델

Flask의 User 테이블과 동일한 스키마를 사용하는 SQLAlchemy 2.0 모델
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.orm import relationship
from datetime import datetime

from app.db.base import Base


class User(Base):
    """사용자 정보 테이블"""
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    email = Column(String(120), unique=True, nullable=True)
    telegram_id = Column(String(100), nullable=True)
    webhook_token = Column(String(64), unique=True, nullable=True)
    telegram_bot_token = Column(Text, nullable=True)
    is_active = Column(Boolean, default=False, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    must_change_password = Column(Boolean, default=False, nullable=False)
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    strategies = relationship("Strategy", back_populates="user")
    accounts = relationship("Account", back_populates="user")

    def __repr__(self):
        return f'<User {self.username}>'
