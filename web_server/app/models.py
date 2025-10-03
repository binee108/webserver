from datetime import datetime
import threading
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
from app.constants import MarketType
from app.security.encryption import decrypt_value, is_likely_legacy_hash
import logging

logger = logging.getLogger(__name__)

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

class UserSession(db.Model):
    """사용자 세션 관리 테이블"""
    __tablename__ = 'user_sessions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    session_token = db.Column(db.String(64), unique=True, nullable=False)
    ip_address = db.Column(db.String(45), nullable=True)  # IPv6 지원
    user_agent = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_accessed = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)

    # 관계 설정
    user = db.relationship('User', backref='sessions')

    def __repr__(self):
        return f'<UserSession {self.user.username}: {self.session_token[:8]}...>'

class Account(db.Model):
    """거래소 계좌 API 정보 테이블"""
    __tablename__ = 'accounts'

    # 클래스 레벨 캐시 (메모리 내 저장)
    _decrypted_api_cache = {}
    _cache_lock = threading.Lock()
    _cache_max_size = 1000  # 최대 캐시 크기

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)  # 계좌명
    exchange = db.Column(db.String(50), nullable=False)  # BINANCE, BYBIT, OKX 등
    public_api = db.Column(db.Text, nullable=False)  # 기존 필드 유지
    secret_api = db.Column(db.Text, nullable=False)
    passphrase = db.Column(db.Text, nullable=True)  # OKX 등에서 필요한 passphrase
    is_testnet = db.Column(db.Boolean, default=False, nullable=False)  # 테스트넷 사용 여부
    is_active = db.Column(db.Boolean, default=True, nullable=False)  # 활성화 상태
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)  # 마지막 업데이트
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 관계 설정
    strategy_accounts = db.relationship('StrategyAccount', backref='account', lazy=True, cascade='all, delete-orphan')
    daily_summaries = db.relationship('DailyAccountSummary', backref='account_ref', lazy=True, cascade='all, delete-orphan')
    
    @staticmethod
    def _decode_api_value(value: str) -> str:
        if not value:
            return ""

        decrypted = decrypt_value(value)

        if decrypted == value and is_likely_legacy_hash(value):
            logger.warning('레거시 해시 형태의 API 자격 증명이 감지되었습니다. 계좌를 다시 저장해 주세요.')
            return ""

        return decrypted

    @classmethod
    def _cleanup_old_cache(cls, account_id: int):
        """특정 계정의 오래된 캐시 항목 정리"""
        keys_to_remove = [key for key in cls._decrypted_api_cache.keys()
                         if key.startswith(f"api_key_{account_id}_") or key.startswith(f"api_secret_{account_id}_")]
        for key in keys_to_remove[:-2]:  # 최신 2개 항목을 제외하고 삭제
            cls._decrypted_api_cache.pop(key, None)

    @classmethod
    def _enforce_cache_size_limit(cls):
        """캐시 크기 제한 강제 적용"""
        if len(cls._decrypted_api_cache) > cls._cache_max_size:
            # 오래된 항목부터 삭제 (dict는 Python 3.7+에서 순서 보장)
            items_to_remove = len(cls._decrypted_api_cache) - cls._cache_max_size + 100
            keys_to_remove = list(cls._decrypted_api_cache.keys())[:items_to_remove]
            for key in keys_to_remove:
                cls._decrypted_api_cache.pop(key, None)

    def _get_cached_decrypted_value(self, field_name: str, encrypted_value: str) -> str:
        """캐시된 복호화 값 반환 또는 새로 복호화하여 캐싱"""
        # updated_at이 None인 경우 현재 시간 사용
        timestamp = self.updated_at.timestamp() if self.updated_at else 0
        cache_key = f"{field_name}_{self.id}_{timestamp}"

        with self._cache_lock:
            # 캐시에서 확인
            if cache_key in self._decrypted_api_cache:
                return self._decrypted_api_cache[cache_key]

            # 복호화 수행
            decrypted = self._decode_api_value(encrypted_value)

            # 캐시에 저장
            self._decrypted_api_cache[cache_key] = decrypted

            # 이 계정의 오래된 캐시 정리
            self._cleanup_old_cache(self.id)

            # 전체 캐시 크기 제한 강제
            self._enforce_cache_size_limit()

        return decrypted

    @property
    def api_key(self) -> str:
        """거래소 클라이언트에 전달할 API 키 (캐싱 적용)"""
        return self._get_cached_decrypted_value("api_key", self.public_api)

    @property
    def api_secret(self) -> str:
        """거래소 클라이언트에 전달할 API 시크릿 (캐싱 적용)"""
        return self._get_cached_decrypted_value("api_secret", self.secret_api)

    @classmethod
    def get_cache_stats(cls) -> dict:
        """캐시 통계 반환"""
        with cls._cache_lock:
            return {
                'cache_size': len(cls._decrypted_api_cache),
                'max_cache_size': cls._cache_max_size,
                'cache_keys': list(cls._decrypted_api_cache.keys())[:10]  # 첫 10개 키만 표시
            }

    @classmethod
    def clear_cache(cls, account_id: int = None):
        """캐시 정리 (특정 계정 또는 전체)"""
        with cls._cache_lock:
            if account_id:
                # 특정 계정의 캐시만 정리
                keys_to_remove = [key for key in cls._decrypted_api_cache.keys()
                                 if key.startswith(f"api_key_{account_id}_") or key.startswith(f"api_secret_{account_id}_")]
                for key in keys_to_remove:
                    cls._decrypted_api_cache.pop(key, None)
            else:
                # 전체 캐시 정리
                cls._decrypted_api_cache.clear()

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
    market_type = db.Column(db.String(10), nullable=False, default=MarketType.SPOT)  # 마켓 타입: SPOT 또는 FUTURES
    is_active = db.Column(db.Boolean, default=True, nullable=False)  # 전략 활성화 상태
    # 공개 전략 여부: True이면 타 사용자가 구독하여 자신의 계좌로 신호를 실행할 수 있음
    is_public = db.Column(db.Boolean, default=False, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
    # 공개 전략 비공개 전환 등으로 연결을 비활성화할 때 사용
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    
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
    market_type = db.Column(db.String(10), nullable=False, default=MarketType.SPOT)  # 마켓 타입: SPOT 또는 FUTURES
    
    def __repr__(self):
        return f'<Trade {self.symbol} {self.side} {self.quantity} @ {self.price} ({self.market_type})>'

class OpenOrder(db.Model):
    """미체결 주문 정보 테이블"""
    __tablename__ = 'open_orders'
    
    id = db.Column(db.Integer, primary_key=True)
    strategy_account_id = db.Column(db.Integer, db.ForeignKey('strategy_accounts.id'), nullable=False)
    exchange_order_id = db.Column(db.String(100), unique=True, nullable=False)  # 거래소 주문 ID
    symbol = db.Column(db.String(20), nullable=False)
    side = db.Column(db.String(10), nullable=False)  # BUY, SELL
    order_type = db.Column(db.String(20), nullable=False, default='LIMIT')  # MARKET, LIMIT, STOP_LIMIT, STOP_MARKET
    price = db.Column(db.Float, nullable=True)  # 지정가 가격 (MARKET 주문시 null 가능)
    stop_price = db.Column(db.Float, nullable=True)  # Stop 가격 (STOP 주문시 필수)
    quantity = db.Column(db.Float, nullable=False)  # 주문 수량
    filled_quantity = db.Column(db.Float, default=0.0, nullable=False)  # 체결된 수량
    status = db.Column(db.String(20), nullable=False)  # OPEN, PARTIALLY_FILLED, CANCELLED, FILLED
    market_type = db.Column(db.String(10), nullable=False, default=MarketType.SPOT)  # 마켓 타입: SPOT 또는 FUTURES
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<OpenOrder {self.symbol} {self.side} {self.order_type} {self.quantity} @ {self.price} ({self.market_type})>'

class WebhookLog(db.Model):
    """웹훅 수신 로그 테이블"""
    __tablename__ = 'webhook_logs'

    id = db.Column(db.Integer, primary_key=True)
    received_at = db.Column(db.DateTime, default=datetime.utcnow)
    payload = db.Column(db.Text, nullable=False)  # 수신된 메시지 내용 (JSON)
    status = db.Column(db.String(20), nullable=False)  # SUCCESS, FAILED, PENDING
    message = db.Column(db.Text, nullable=True)  # 처리 결과 메시지 또는 오류 내용

    # 표준화된 타이밍 정보 컬럼 추가
    webhook_received_at = db.Column(db.Float, nullable=True)  # Unix timestamp (초)
    webhook_validated_at = db.Column(db.Float, nullable=True)  # 검증 완료 시점
    trade_started_at = db.Column(db.Float, nullable=True)  # 거래 처리 시작 시점
    trade_requested_at = db.Column(db.Float, nullable=True)  # 거래소 API 요청 시점
    trade_responded_at = db.Column(db.Float, nullable=True)  # 거래소 API 응답 시점
    webhook_completed_at = db.Column(db.Float, nullable=True)  # 웹훅 처리 완료 시점

    # 성능 메트릭 컬럼 (밀리초 단위)
    validation_time_ms = db.Column(db.Float, nullable=True)  # 검증 소요 시간
    preprocessing_time_ms = db.Column(db.Float, nullable=True)  # 전처리 소요 시간
    trade_processing_time_ms = db.Column(db.Float, nullable=True)  # 거래 처리 소요 시간
    total_processing_time_ms = db.Column(db.Float, nullable=True)  # 총 처리 소요 시간

    def __repr__(self):
        return f'<WebhookLog {self.status} at {self.received_at}>'

class DailyAccountSummary(db.Model):
    """일일 계정 요약 테이블"""
    __tablename__ = 'daily_account_summaries'
    
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    starting_balance = db.Column(db.Float, default=0.0, nullable=False)  # 시작 잔고
    ending_balance = db.Column(db.Float, default=0.0, nullable=False)  # 종료 잔고 (총합)
    spot_balance = db.Column(db.Float, default=0.0, nullable=False)  # 현물 잔고
    futures_balance = db.Column(db.Float, default=0.0, nullable=False)  # 선물 잔고
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

# ============================================
# Phase 1: 열린 주문 트래킹 시스템 테이블
# ============================================

class OrderTrackingSession(db.Model):
    """WebSocket 연결 세션 관리 테이블"""
    __tablename__ = 'order_tracking_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    session_id = db.Column(db.String(100), unique=True, nullable=False)  # WebSocket 세션 ID
    connection_type = db.Column(db.String(20), nullable=False)  # websocket, polling
    exchange = db.Column(db.String(50), nullable=True)  # 연결된 거래소
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True)
    status = db.Column(db.String(20), nullable=False, default='connecting')  # connecting, connected, disconnected, error
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_ping = db.Column(db.DateTime, nullable=True)
    ended_at = db.Column(db.DateTime, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    meta_data = db.Column(db.JSON, nullable=True)  # 추가 메타데이터 저장
    
    # 관계 설정
    user = db.relationship('User', backref='tracking_sessions')
    account = db.relationship('Account', backref='tracking_sessions')
    
    # 인덱스
    __table_args__ = (
        db.Index('idx_tracking_session_user', 'user_id'),
        db.Index('idx_tracking_session_status', 'status'),
        db.Index('idx_tracking_session_started', 'started_at'),
    )
    
    def __repr__(self):
        return f'<OrderTrackingSession {self.session_id} - {self.status}>'


class TradeExecution(db.Model):
    """체결된 거래 상세 정보 테이블 (기존 trades 테이블 보완)"""
    __tablename__ = 'trade_executions'
    
    id = db.Column(db.Integer, primary_key=True)
    trade_id = db.Column(db.Integer, db.ForeignKey('trades.id'), nullable=True)  # 기존 Trade와 연결
    strategy_account_id = db.Column(db.Integer, db.ForeignKey('strategy_accounts.id'), nullable=False)
    exchange_trade_id = db.Column(db.String(100), nullable=False)  # 거래소 거래 ID
    exchange_order_id = db.Column(db.String(100), nullable=False)  # 거래소 주문 ID
    symbol = db.Column(db.String(20), nullable=False)
    side = db.Column(db.String(10), nullable=False)  # BUY, SELL
    execution_price = db.Column(db.Float, nullable=False)  # 실제 체결가
    execution_quantity = db.Column(db.Float, nullable=False)  # 실제 체결량
    commission = db.Column(db.Float, nullable=True)  # 수수료
    commission_asset = db.Column(db.String(20), nullable=True)  # 수수료 자산
    execution_time = db.Column(db.DateTime, nullable=False)  # 체결 시간
    is_maker = db.Column(db.Boolean, nullable=True)  # Maker/Taker 여부
    realized_pnl = db.Column(db.Float, nullable=True)  # 실현 손익 (선물)
    market_type = db.Column(db.String(10), nullable=False)  # SPOT, FUTURES
    meta_data = db.Column(db.JSON, nullable=True)  # 추가 거래소별 메타데이터
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 관계 설정
    trade = db.relationship('Trade', backref='executions')
    strategy_account = db.relationship('StrategyAccount', backref='trade_executions')
    
    # 인덱스
    __table_args__ = (
        db.Index('idx_trade_exec_symbol', 'symbol'),
        db.Index('idx_trade_exec_time', 'execution_time'),
        db.Index('idx_trade_exec_strategy', 'strategy_account_id'),
        db.UniqueConstraint('exchange_trade_id', 'strategy_account_id', name='uq_exchange_trade'),
    )
    
    @property
    def exchange(self):
        """거래소 정보 가져오기"""
        if self.strategy_account and self.strategy_account.account:
            return self.strategy_account.account.exchange
        return None
    
    def __repr__(self):
        return f'<TradeExecution {self.symbol} {self.side} {self.execution_quantity}@{self.execution_price}>'


class StrategyPerformance(db.Model):
    """전략별 성과 메트릭 테이블"""
    __tablename__ = 'strategy_performance'
    
    id = db.Column(db.Integer, primary_key=True)
    strategy_id = db.Column(db.Integer, db.ForeignKey('strategies.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    
    # 수익률 메트릭
    daily_return = db.Column(db.Float, default=0.0, nullable=False)  # 일일 수익률 (%)
    cumulative_return = db.Column(db.Float, default=0.0, nullable=False)  # 누적 수익률 (%)
    
    # 손익 메트릭
    daily_pnl = db.Column(db.Float, default=0.0, nullable=False)  # 일일 손익
    cumulative_pnl = db.Column(db.Float, default=0.0, nullable=False)  # 누적 손익
    
    # 거래 통계
    total_trades = db.Column(db.Integer, default=0, nullable=False)  # 총 거래 수
    winning_trades = db.Column(db.Integer, default=0, nullable=False)  # 수익 거래 수
    losing_trades = db.Column(db.Integer, default=0, nullable=False)  # 손실 거래 수
    win_rate = db.Column(db.Float, default=0.0, nullable=False)  # 승률 (%)
    
    # 리스크 메트릭
    max_drawdown = db.Column(db.Float, default=0.0, nullable=False)  # 최대 낙폭 (%)
    sharpe_ratio = db.Column(db.Float, nullable=True)  # 샤프 비율
    sortino_ratio = db.Column(db.Float, nullable=True)  # 소르티노 비율
    volatility = db.Column(db.Float, nullable=True)  # 변동성 (%)
    
    # 포지션 통계
    avg_position_size = db.Column(db.Float, nullable=True)  # 평균 포지션 크기
    max_position_size = db.Column(db.Float, nullable=True)  # 최대 포지션 크기
    active_positions = db.Column(db.Integer, default=0, nullable=False)  # 활성 포지션 수
    
    # 수수료 통계
    total_commission = db.Column(db.Float, default=0.0, nullable=False)  # 총 수수료
    commission_ratio = db.Column(db.Float, default=0.0, nullable=False)  # 수수료 비율 (%)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 관계 설정
    strategy = db.relationship('Strategy', backref='performances')
    
    # 인덱스 및 제약
    __table_args__ = (
        db.UniqueConstraint('strategy_id', 'date', name='uq_strategy_date'),
        db.Index('idx_performance_date', 'date'),
        db.Index('idx_performance_strategy', 'strategy_id'),
    )
    
    def __repr__(self):
        return f'<StrategyPerformance {self.strategy_id} {self.date}: {self.daily_return:.2f}%>'


class TrackingLog(db.Model):
    """시스템 추적 로그 테이블"""
    __tablename__ = 'tracking_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    log_type = db.Column(db.String(50), nullable=False)  # order_update, trade_execution, error, sync, etc.
    severity = db.Column(db.String(20), nullable=False, default='info')  # debug, info, warning, error, critical
    source = db.Column(db.String(100), nullable=False)  # 로그 발생 소스 (서비스명, 모듈명 등)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True)
    strategy_id = db.Column(db.Integer, db.ForeignKey('strategies.id'), nullable=True)
    
    # 로그 내용
    message = db.Column(db.Text, nullable=False)
    details = db.Column(db.JSON, nullable=True)  # 구조화된 추가 정보
    
    # 관련 엔티티 참조
    order_id = db.Column(db.String(100), nullable=True)  # 거래소 주문 ID
    trade_id = db.Column(db.String(100), nullable=True)  # 거래소 거래 ID
    symbol = db.Column(db.String(20), nullable=True)
    
    # 성능 메트릭
    execution_time_ms = db.Column(db.Float, nullable=True)  # 처리 시간 (밀리초)
    
    # 타임스탬프
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 관계 설정
    user = db.relationship('User', backref='tracking_logs')
    account = db.relationship('Account', backref='tracking_logs')
    strategy = db.relationship('Strategy', backref='tracking_logs')
    
    # 인덱스
    __table_args__ = (
        db.Index('idx_tracking_log_type', 'log_type'),
        db.Index('idx_tracking_log_severity', 'severity'),
        db.Index('idx_tracking_log_created', 'created_at'),
        db.Index('idx_tracking_log_user', 'user_id'),
        db.Index('idx_tracking_log_symbol', 'symbol'),
        db.Index('idx_tracking_log_order', 'order_id'),
    )
    
    @classmethod
    def log(cls, log_type, message, source, severity='info', **kwargs):
        """간편한 로그 생성 메서드"""
        log_entry = cls(
            log_type=log_type,
            message=message,
            source=source,
            severity=severity,
            **kwargs
        )
        db.session.add(log_entry)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to write tracking log: {e}")
        return log_entry
    
    def __repr__(self):
        return f'<TrackingLog [{self.severity}] {self.log_type}: {self.message[:50]}...>'
