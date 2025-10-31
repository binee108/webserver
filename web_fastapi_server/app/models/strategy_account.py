"""
StrategyAccount 모델

Flask의 StrategyAccount 테이블과 동일한 스키마를 사용하는 SQLAlchemy 2.0 모델
"""

from sqlalchemy import Column, Integer, Float, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship

from app.db.base import Base


class StrategyAccount(Base):
    """전략-계좌 연결 및 설정 테이블"""
    __tablename__ = 'strategy_accounts'

    id = Column(Integer, primary_key=True)
    strategy_id = Column(Integer, ForeignKey('strategies.id'), nullable=False)
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=False)
    weight = Column(Float, nullable=False)  # 전략 비중
    leverage = Column(Float, nullable=False)  # 레버리지 설정
    max_symbols = Column(Integer, nullable=True, default=None)  # 최대 보유 심볼 수
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    # 복합 유니크 제약조건
    __table_args__ = (UniqueConstraint('strategy_id', 'account_id'),)

    # Relationships
    strategy = relationship("Strategy", back_populates="strategy_accounts")
    account = relationship("Account", back_populates="strategy_accounts")

    def __repr__(self):
        max_symbols_str = f", max_symbols: {self.max_symbols}" if self.max_symbols is not None else ""
        return f'<StrategyAccount strategy_id={self.strategy_id} account_id={self.account_id}{max_symbols_str}>'
