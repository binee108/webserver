"""
Account 모델

Flask의 Account 테이블과 동일한 스키마를 사용하는 SQLAlchemy 2.0 모델
"""

from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Float
from sqlalchemy.orm import relationship
from datetime import datetime

from app.db.base import Base


class Account(Base):
    """거래소 계좌 API 정보 테이블"""
    __tablename__ = 'accounts'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    name = Column(String(100), nullable=False)  # 계좌명
    exchange = Column(String(50), nullable=False)  # BINANCE, BYBIT, OKX, KIS, KIWOOM 등
    public_api = Column(Text, nullable=False)  # API Key (암호화됨)
    secret_api = Column(Text, nullable=False)  # API Secret (암호화됨)
    passphrase = Column(Text, nullable=True)  # OKX 등에서 필요한 passphrase
    is_testnet = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    # 계좌 타입 (CRYPTO or STOCK)
    account_type = Column(String(20), default='CRYPTO', nullable=False, index=True)

    # 증권 전용 필드
    _securities_config = Column('securities_config', Text, nullable=True)
    _access_token = Column('access_token', Text, nullable=True)
    token_expires_at = Column(DateTime, nullable=True)

    # 자본 재할당 관련 필드
    previous_total_capital = Column(Float, nullable=True)
    last_rebalance_at = Column(DateTime, nullable=True)

    # Relationships
    user = relationship("User", back_populates="accounts")
    strategy_accounts = relationship("StrategyAccount", back_populates="account")

    def __repr__(self):
        return f'<Account {self.name} ({self.exchange})>'
