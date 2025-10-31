"""
Strategy 모델

Flask의 Strategy 테이블과 동일한 스키마를 사용하는 SQLAlchemy 2.0 모델
"""

from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime

from app.db.base import Base


class Strategy(Base):
    """전략 정보 테이블"""
    __tablename__ = 'strategies'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    group_name = Column(String(100), unique=True, nullable=False)  # 웹훅 연동 키
    market_type = Column(String(10), nullable=False, default='SPOT')  # SPOT or FUTURES
    is_active = Column(Boolean, default=True, nullable=False)
    is_public = Column(Boolean, default=False, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="strategies")
    strategy_accounts = relationship("StrategyAccount", back_populates="strategy")

    def __repr__(self):
        return f'<Strategy {self.name} ({self.group_name}) - {self.market_type}>'
