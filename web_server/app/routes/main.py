from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from app.models import Strategy, Account, Trade, OpenOrder, StrategyAccount, StrategyPosition
from app.services.strategy_service import strategy_service, StrategyError
from app import db
from app.constants import MarketType
from datetime import datetime, timedelta
from sqlalchemy import func
from sqlalchemy.orm import joinedload

bp = Blueprint('main', __name__)

@bp.route('/')
def index():
    """홈페이지"""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('auth.login'))

@bp.route('/dashboard')
@login_required
def dashboard():
    """대시보드 페이지"""
    # 사용자의 전략들
    strategies = Strategy.query.filter_by(user_id=current_user.id).all()
    active_strategies = [s for s in strategies if s.is_active]
    
    # 오늘 거래 수 계산
    today = datetime.now().date()
    today_trades_count = 0
    
    # 미체결 주문 수 계산
    pending_orders_count = 0
    
    # 최근 거래 내역 (최대 5개)
    recent_trades = []
    
    if strategies:
        strategy_ids = [s.id for s in strategies]
        
        # 오늘 거래 수
        today_trades_count = db.session.query(Trade).join(StrategyAccount).filter(
            StrategyAccount.strategy_id.in_(strategy_ids),
            func.date(Trade.timestamp) == today
        ).count()
        
        # 미체결 주문 수
        pending_orders_count = db.session.query(OpenOrder).join(StrategyAccount).filter(
            StrategyAccount.strategy_id.in_(strategy_ids),
            OpenOrder.status.in_(['OPEN', 'PARTIALLY_FILLED'])
        ).count()
        
        # 최근 거래 내역
        recent_trades = db.session.query(Trade).join(StrategyAccount).filter(
            StrategyAccount.strategy_id.in_(strategy_ids)
        ).order_by(Trade.timestamp.desc()).limit(5).all()
    
    return render_template('dashboard.html', MarketType=MarketType,
                         strategies=active_strategies,
                         active_strategies_count=len(active_strategies),
                         today_trades_count=today_trades_count,
                         pending_orders_count=pending_orders_count,
                         recent_trades=recent_trades)

@bp.route('/accounts')
@login_required
def accounts():
    """계좌 관리 페이지"""
    # 현재 사용자의 계좌 목록 조회
    accounts = Account.query.filter_by(user_id=current_user.id).all()
    return render_template('accounts.html', accounts=accounts, MarketType=MarketType)

@bp.route('/strategies')
@login_required
def strategies():
    """전략 관리 페이지"""
    try:
        # 내 전략만 서버 렌더, 구독/공개 전략은 클라이언트에서 API 호출로 로드
        strategies_data = strategy_service.get_strategies_by_user(current_user.id)
        return render_template('strategies.html', strategies=strategies_data, MarketType=MarketType)
    except StrategyError as e:
        # 오류 발생 시 빈 목록으로 처리
        return render_template('strategies.html', strategies=[], MarketType=MarketType)
    except Exception as e:
        # 예상치 못한 오류 발생 시에도 빈 목록으로 처리
        return render_template('strategies.html', strategies=[], MarketType=MarketType)

@bp.route('/strategies/<int:strategy_id>/positions')
@login_required
def strategy_positions(strategy_id):
    """전략별 포지션 관리 페이지 (소유 전략 + 구독 전략 모두 지원)"""
    # 전략 존재 확인
    strategy = Strategy.query.filter_by(id=strategy_id).first()
    if not strategy:
        return redirect(url_for('main.strategies'))

    # 권한 확인: 소유자이거나, 해당 전략에 내 계좌가 연결되어 있어야 함
    is_owner = (strategy.user_id == current_user.id)
    if not is_owner:
        has_subscription = db.session.query(StrategyAccount)\
            .join(StrategyAccount.account)\
            .filter(StrategyAccount.strategy_id == strategy_id, Account.user_id == current_user.id)\
            .count() > 0
        if not has_subscription:
            return redirect(url_for('main.strategies'))

    # 해당 전략의 활성 포지션만 조회 (항상 내 계좌 기준으로 제한)
    positions_query = StrategyPosition.query\
        .join(StrategyAccount)\
        .join(Account)\
        .options(joinedload(StrategyPosition.strategy_account).joinedload(StrategyAccount.account))\
        .filter(
            StrategyAccount.strategy_id == strategy_id,
            Account.user_id == current_user.id,
            StrategyPosition.quantity != 0
        ).all()
    
    # StrategyPosition 객체들을 딕셔너리로 변환 (JSON 직렬화 가능하도록)
    positions = []
    for pos in positions_query:
        position_dict = {
            'position_id': pos.id,  # 통일된 명명: position_id 사용
            'symbol': pos.symbol,
            'quantity': float(pos.quantity) if pos.quantity else 0,
            'entry_price': float(pos.entry_price) if pos.entry_price else 0,
            'last_updated': pos.last_updated.isoformat() if pos.last_updated else None,
            'strategy_account_id': pos.strategy_account_id,
            'account': {
                'id': pos.strategy_account.account.id,
                'name': pos.strategy_account.account.name,
                'exchange': pos.strategy_account.account.exchange
            } if pos.strategy_account and pos.strategy_account.account else None
        }
        positions.append(position_dict)
    
    return render_template('positions.html', strategy=strategy, positions=positions, MarketType=MarketType) 