from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db

class User(UserMixin, db.Model):
    """사용자 정보 테이블"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    telegram_id = db.Column(db.String(100), nullable=True)  # 텔레그램 Chat ID
    # 웹훅/외부 연동 시 사용자 식별을 위한 고유 토큰 (재발행 가능)
    webhook_token = db.Column(db.String(64), unique=True, nullable=True)
    telegram_bot_token = db.Column(db.Text, nullable=True)  # 사용자별 텔레그램 봇 토큰
    is_active = db.Column(db.Boolean, default=False, nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    must_change_password = db.Column(db.Boolean, default=False, nullable=False)  # 비밀번호 변경 강제 여부
    last_login = db.Column(db.DateTime, nullable=True)  # 마지막 로그인 시간
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 관계 설정
    accounts = db.relationship('Account', backref='user', lazy=True, cascade='all, delete-orphan')
    strategies = db.relationship('Strategy', backref='user', lazy=True, cascade='all, delete-orphan')
    
    def set_password(self, password):
        """비밀번호 해싱"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """비밀번호 확인"""
        return check_password_hash(self.password_hash, password)
    
    def __repr__(self):
        return f'<User {self.username}>'

class Account(db.Model):
    """거래소 계좌 API 정보 테이블"""
    __tablename__ = 'accounts'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)  # 계좌명
    exchange = db.Column(db.String(50), nullable=False)  # BINANCE, BYBIT, OKX 등
    public_api = db.Column(db.Text, nullable=False)  # 기존 필드 유지
    secret_api = db.Column(db.Text, nullable=False)
    passphrase = db.Column(db.Text, nullable=True)  # OKX 등에서 필요한 passphrase
    is_active = db.Column(db.Boolean, default=True, nullable=False)  # 활성화 상태
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)  # 마지막 업데이트
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 관계 설정
    strategy_accounts = db.relationship('StrategyAccount', backref='account', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Account {self.name} ({self.exchange})>'

class Strategy(db.Model):
    """전략 정보 테이블"""
    __tablename__ = 'strategies'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)  # 전략명
    description = db.Column(db.Text, nullable=True)  # 전략 설명
    group_name = db.Column(db.String(100), unique=True, nullable=False)  # 웹훅 연동 키
    market_type = db.Column(db.String(10), nullable=False, default='spot')  # 마켓 타입: 'spot' 또는 'futures'
    is_active = db.Column(db.Boolean, default=True, nullable=False)  # 전략 활성화 상태
    # 공개 전략 여부: True이면 타 사용자가 구독하여 자신의 계좌로 신호를 실행할 수 있음
    is_public = db.Column(db.Boolean, default=False, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 관계 설정
    strategy_accounts = db.relationship('StrategyAccount', backref='strategy', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Strategy {self.name} ({self.group_name}) - {self.market_type}>'

class StrategyAccount(db.Model):
    """전략-계좌 연결 및 설정 테이블"""
    __tablename__ = 'strategy_accounts'
    
    id = db.Column(db.Integer, primary_key=True)
    strategy_id = db.Column(db.Integer, db.ForeignKey('strategies.id'), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=False)
    weight = db.Column(db.Float, nullable=False)  # 전략 비중
    leverage = db.Column(db.Float, nullable=False)  # 레버리지 설정
    max_symbols = db.Column(db.Integer, nullable=True, default=None)  # 최대 보유 심볼 수 (None은 제한 없음)
    
    # 복합 유니크 제약조건
    __table_args__ = (db.UniqueConstraint('strategy_id', 'account_id'),)
    
    # 관계 설정
    strategy_capital = db.relationship('StrategyCapital', backref='strategy_account', uselist=False, cascade='all, delete-orphan')
    strategy_positions = db.relationship('StrategyPosition', backref='strategy_account', lazy=True, cascade='all, delete-orphan')
    trades = db.relationship('Trade', backref='strategy_account', lazy=True, cascade='all, delete-orphan')
    open_orders = db.relationship('OpenOrder', backref='strategy_account', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        max_symbols_str = f", max_symbols: {self.max_symbols}" if self.max_symbols is not None else ""
        return f'<StrategyAccount {self.strategy.group_name} - {self.account.name}{max_symbols_str}>'

class StrategyCapital(db.Model):
    """전략별 할당 자본 관리 테이블"""
    __tablename__ = 'strategy_capital'
    
    id = db.Column(db.Integer, primary_key=True)
    strategy_account_id = db.Column(db.Integer, db.ForeignKey('strategy_accounts.id'), unique=True, nullable=False)
    allocated_capital = db.Column(db.Float, default=0.0, nullable=False)  # 할당된 자본
    current_pnl = db.Column(db.Float, default=0.0, nullable=False)  # 현재 미실현 손익
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<StrategyCapital {self.strategy_account.strategy.group_name}: {self.allocated_capital}>'

class StrategyPosition(db.Model):
    """전략별 가상 포지션 관리 테이블"""
    __tablename__ = 'strategy_positions'
    
    id = db.Column(db.Integer, primary_key=True)
    strategy_account_id = db.Column(db.Integer, db.ForeignKey('strategy_accounts.id'), nullable=False)
    symbol = db.Column(db.String(20), nullable=False)  # 거래 페어 (예: BTCUSDT)
    quantity = db.Column(db.Float, default=0.0, nullable=False)  # 포지션 수량 (양수: 롱, 음수: 숏)
    entry_price = db.Column(db.Float, default=0.0, nullable=False)  # 평균 진입 가격
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 복합 유니크 제약조건
    __table_args__ = (db.UniqueConstraint('strategy_account_id', 'symbol'),)
    
    def __repr__(self):
        return f'<StrategyPosition {self.symbol}: {self.quantity}>'

class Trade(db.Model):
    """거래 기록 테이블"""
    __tablename__ = 'trades'
    
    id = db.Column(db.Integer, primary_key=True)
    strategy_account_id = db.Column(db.Integer, db.ForeignKey('strategy_accounts.id'), nullable=False)
    exchange_order_id = db.Column(db.String(100), nullable=False)  # 거래소 주문 ID
    symbol = db.Column(db.String(20), nullable=False)
    side = db.Column(db.String(10), nullable=False)  # BUY, SELL
    order_type = db.Column(db.String(10), nullable=False)  # MARKET, LIMIT
    order_price = db.Column(db.Float, nullable=True)  # 🆕 주문 가격 (지정가 주문 시)
    price = db.Column(db.Float, nullable=False)  # 체결 가격 (실제 체결된 평균 가격)
    quantity = db.Column(db.Float, nullable=False)  # 체결 수량
    timestamp = db.Column(db.DateTime, nullable=False)  # 체결 일시
    pnl = db.Column(db.Float, nullable=True)  # 실현 손익
    fee = db.Column(db.Float, nullable=True)  # 거래 수수료
    is_entry = db.Column(db.Boolean, nullable=True)  # 진입/청산 여부
    market_type = db.Column(db.String(10), nullable=False, default='spot')  # 마켓 타입: 'spot' 또는 'futures'
    
    def __repr__(self):
        return f'<Trade {self.symbol} {self.side} {self.quantity} @ {self.price} ({self.market_type})>'

class OpenOrder(db.Model):
    """미체결 지정가 주문 정보 테이블"""
    __tablename__ = 'open_orders'
    
    id = db.Column(db.Integer, primary_key=True)
    strategy_account_id = db.Column(db.Integer, db.ForeignKey('strategy_accounts.id'), nullable=False)
    exchange_order_id = db.Column(db.String(100), unique=True, nullable=False)  # 거래소 주문 ID
    symbol = db.Column(db.String(20), nullable=False)
    side = db.Column(db.String(10), nullable=False)  # BUY, SELL
    price = db.Column(db.Float, nullable=False)  # 지정가 가격
    quantity = db.Column(db.Float, nullable=False)  # 주문 수량
    filled_quantity = db.Column(db.Float, default=0.0, nullable=False)  # 체결된 수량
    status = db.Column(db.String(20), nullable=False)  # OPEN, PARTIALLY_FILLED, CANCELLED, FILLED
    market_type = db.Column(db.String(10), nullable=False, default='spot')  # 🆕 마켓 타입: 'spot' 또는 'futures'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<OpenOrder {self.symbol} {self.side} {self.quantity} @ {self.price} ({self.market_type})>'

class WebhookLog(db.Model):
    """웹훅 수신 로그 테이블"""
    __tablename__ = 'webhook_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    received_at = db.Column(db.DateTime, default=datetime.utcnow)
    payload = db.Column(db.Text, nullable=False)  # 수신된 메시지 내용 (JSON)
    status = db.Column(db.String(20), nullable=False)  # SUCCESS, FAILED, PENDING
    message = db.Column(db.Text, nullable=True)  # 처리 결과 메시지 또는 오류 내용
    
    def __repr__(self):
        return f'<WebhookLog {self.status} at {self.received_at}>'

class DailyAccountSummary(db.Model):
    """일일 계정 요약 테이블"""
    __tablename__ = 'daily_account_summaries'
    
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    starting_balance = db.Column(db.Float, default=0.0, nullable=False)  # 시작 잔고
    ending_balance = db.Column(db.Float, default=0.0, nullable=False)  # 종료 잔고
    total_pnl = db.Column(db.Float, default=0.0, nullable=False)  # 총 손익
    realized_pnl = db.Column(db.Float, default=0.0, nullable=False)  # 실현 손익
    unrealized_pnl = db.Column(db.Float, default=0.0, nullable=False)  # 미실현 손익
    total_trades = db.Column(db.Integer, default=0, nullable=False)  # 총 거래 수
    winning_trades = db.Column(db.Integer, default=0, nullable=False)  # 수익 거래 수
    losing_trades = db.Column(db.Integer, default=0, nullable=False)  # 손실 거래 수
    win_rate = db.Column(db.Float, default=0.0, nullable=False)  # 승률 (%)
    max_drawdown = db.Column(db.Float, default=0.0, nullable=False)  # 최대 낙폭 (%)
    total_volume = db.Column(db.Float, default=0.0, nullable=False)  # 총 거래량
    total_fees = db.Column(db.Float, default=0.0, nullable=False)  # 총 수수료
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 복합 유니크 제약조건
    __table_args__ = (db.UniqueConstraint('account_id', 'date'),)
    
    def __repr__(self):
        return f'<DailyAccountSummary {self.date} - Account {self.account_id}>'

class SystemSummary(db.Model):
    """시스템 전체 요약 테이블"""
    __tablename__ = 'system_summaries'
    
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, unique=True)
    total_balance = db.Column(db.Float, default=0.0, nullable=False)  # 전체 잔고
    total_pnl = db.Column(db.Float, default=0.0, nullable=False)  # 전체 손익
    total_trades = db.Column(db.Integer, default=0, nullable=False)  # 전체 거래 수
    active_accounts = db.Column(db.Integer, default=0, nullable=False)  # 활성 계정 수
    active_strategies = db.Column(db.Integer, default=0, nullable=False)  # 활성 전략 수
    system_mdd = db.Column(db.Float, default=0.0, nullable=False)  # 시스템 최대 낙폭 (%)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<SystemSummary {self.date}>'

class SystemSetting(db.Model):
    """시스템 전역 설정 테이블"""
    __tablename__ = 'system_settings'
    
    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text, nullable=True)
    description = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    @classmethod
    def get_setting(cls, key: str, default_value: str = None) -> str:
        """설정 값 조회"""
        setting = cls.query.filter_by(key=key).first()
        return setting.value if setting and setting.value else default_value
    
    @classmethod
    def set_setting(cls, key: str, value: str, description: str = None):
        """설정 값 업데이트 또는 생성"""
        from app import db
        setting = cls.query.filter_by(key=key).first()
        if setting:
            setting.value = value
            setting.updated_at = datetime.utcnow()
            if description:
                setting.description = description
        else:
            setting = cls(key=key, value=value, description=description)
            db.session.add(setting)
        db.session.commit()
        return setting
    
    def __repr__(self):
        return f'<SystemSetting {self.key}={self.value}>' 