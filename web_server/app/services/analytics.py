"""
통합 분석 서비스

Analytics + Dashboard + Capital 관련 모든 기능 통합
1인 사용자를 위한 종합적인 분석 및 대시보드 서비스입니다.
"""

import logging
from collections import defaultdict
from math import sqrt
from statistics import mean, pstdev, StatisticsError
from typing import Dict, Any, Optional, List, Tuple
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta
from sqlalchemy import func, and_, desc, or_
from sqlalchemy.orm import selectinload

from app import db
from app.constants import MarketType
from app.models import (
    Strategy, StrategyPosition, OpenOrder, Trade, Account,
    StrategyAccount, User, StrategyCapital, DailyAccountSummary, TradeExecution
)
from app.services.security import security_service

logger = logging.getLogger(__name__)
class AnalyticsError(Exception):
    """분석 관련 오류"""
    pass


class AnalyticsService:
    """
    통합 분석 서비스

    기존 서비스들 통합:
    - analytics_service.py
    - dashboard_service.py
    - capital_service.py
    """

    def __init__(self):
        logger.info("✅ 통합 분석 서비스 초기화 완료")

    # === 대시보드 데이터 ===

    def get_dashboard_summary(self, user_id: int) -> Dict[str, Any]:
        """대시보드 요약 정보"""
        try:
            # 기본 통계
            strategies = Strategy.query.filter_by(user_id=user_id).all()
            total_strategies = len(strategies)
            active_strategies = len([s for s in strategies if s.is_active])

            # 계정 정보
            accounts = Account.query.filter_by(user_id=user_id).all()
            total_accounts = len(accounts)
            active_accounts = len([a for a in accounts if a.is_active])

            # 포지션 정보
            total_positions = 0
            total_position_value = Decimal('0')

            for strategy in strategies:
                positions = StrategyPosition.query.join(StrategyAccount).filter(StrategyAccount.strategy_id == strategy.id).all()
                for position in positions:
                    if position.quantity and position.quantity != 0:
                        total_positions += 1
                        if position.entry_price and position.quantity:
                            total_position_value += position.entry_price * position.quantity

            # 미체결 주문
            open_orders_count = 0
            for strategy in strategies:
                orders = OpenOrder.query.join(StrategyAccount).filter(StrategyAccount.strategy_id == strategy.id).all()
                open_orders_count += len([o for o in orders if o.status in ['NEW', 'PARTIALLY_FILLED']])

            # 오늘의 거래
            today = datetime.utcnow().date()
            today_trades = 0
            today_pnl = Decimal('0')

            for strategy in strategies:
                trades = Trade.query.filter(
                    and_(
                        Trade.strategy_account_id.in_([sa.id for sa in StrategyAccount.query.filter_by(strategy_id=strategy.id).all()]),
                        func.date(Trade.timestamp) == today
                    )
                ).all()
                today_trades += len(trades)
                for trade in trades:
                    if trade.pnl:
                        today_pnl += trade.pnl

            return {
                'success': True,
                'summary': {
                    'strategies': {
                        'total': total_strategies,
                        'active': active_strategies
                    },
                    'accounts': {
                        'total': total_accounts,
                        'active': active_accounts
                    },
                    'positions': {
                        'count': total_positions,
                        'total_value': float(total_position_value)
                    },
                    'orders': {
                        'open_count': open_orders_count
                    },
                    'today': {
                        'trades': today_trades,
                        'pnl': float(today_pnl)
                    }
                }
            }

        except Exception as e:
            logger.error(f"대시보드 요약 조회 실패: {e}")
            return {'success': False, 'error': str(e)}

    def get_recent_activities(self, user_id: int, limit: int = 10) -> Dict[str, Any]:
        """최근 활동 내역"""
        try:
            activities = []

            # 최근 거래
            strategies = Strategy.query.filter_by(user_id=user_id).all()
            strategy_ids = [s.id for s in strategies]

            if strategy_ids:
                recent_trades = Trade.query.filter(
                    Trade.strategy_account_id.in_([sa.id for sa in StrategyAccount.query.filter(StrategyAccount.strategy_id.in_(strategy_ids)).all()])
                ).order_by(desc(Trade.timestamp)).limit(limit // 2).all()

                for trade in recent_trades:
                    activities.append({
                        'type': 'trade',
                        'timestamp': trade.timestamp.isoformat(),
                        'description': f"{trade.symbol} {trade.side} {trade.quantity} @ {trade.price}",
                        'strategy': trade.strategy_account.strategy.name if trade.strategy_account and trade.strategy_account.strategy else 'Unknown',
                        'pnl': float(trade.pnl) if trade.pnl else 0
                    })

                # 최근 주문
                recent_orders = OpenOrder.query.filter(
                    OpenOrder.strategy_account_id.in_([sa.id for sa in StrategyAccount.query.filter(StrategyAccount.strategy_id.in_(strategy_ids)).all()])
                ).order_by(desc(OpenOrder.created_at)).limit(limit // 2).all()

                for order in recent_orders:
                    activities.append({
                        'type': 'order',
                        'timestamp': order.created_at.isoformat(),
                        'description': f"{order.symbol} {order.side} {order.order_type} - {order.status}",
                        'strategy': order.strategy_account.strategy.name if order.strategy_account and order.strategy_account.strategy else 'Unknown',
                        'amount': float(order.quantity) if order.quantity else 0
                    })

            # 시간순 정렬
            activities.sort(key=lambda x: x['timestamp'], reverse=True)

            return {
                'success': True,
                'activities': activities[:limit]
            }

        except Exception as e:
            logger.error(f"최근 활동 조회 실패: {e}")
            return {'success': False, 'error': str(e)}

    # === 전략 분석 ===

    def get_strategy_performance(self, strategy_id: int, period_days: int = 30) -> Dict[str, Any]:
        """전략 성과 분석"""
        try:
            strategy = Strategy.query.get(strategy_id)
            if not strategy:
                return {'success': False, 'error': '전략을 찾을 수 없습니다.'}

            # 기간 설정
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=period_days)

            # 거래 내역
            trades = Trade.query.filter(
                and_(
                    Trade.strategy_account_id.in_([sa.id for sa in StrategyAccount.query.filter_by(strategy_id=strategy_id).all()]),
                    Trade.timestamp >= start_date,
                    Trade.timestamp <= end_date
                )
            ).all()

            # 기본 통계
            total_trades = len(trades)
            winning_trades = len([t for t in trades if t.pnl and t.pnl > 0])
            losing_trades = len([t for t in trades if t.pnl and t.pnl < 0])

            total_pnl = sum([t.pnl for t in trades if t.pnl], Decimal('0'))
            total_volume = sum([t.price * t.quantity for t in trades if t.price and t.quantity], Decimal('0'))

            # 승률
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

            # 평균 수익/손실
            avg_win = Decimal('0')
            avg_loss = Decimal('0')

            if winning_trades > 0:
                win_pnls = [t.pnl for t in trades if t.pnl and t.pnl > 0]
                avg_win = sum(win_pnls, Decimal('0')) / len(win_pnls)

            if losing_trades > 0:
                loss_pnls = [t.pnl for t in trades if t.pnl and t.pnl < 0]
                avg_loss = sum(loss_pnls, Decimal('0')) / len(loss_pnls)

            # 일별 PnL
            daily_pnl = {}
            for trade in trades:
                trade_date = trade.timestamp.date().isoformat()
                if trade_date not in daily_pnl:
                    daily_pnl[trade_date] = Decimal('0')
                if trade.pnl:
                    daily_pnl[trade_date] += trade.pnl

            return {
                'success': True,
                'performance': {
                    'period_days': period_days,
                    'total_trades': total_trades,
                    'winning_trades': winning_trades,
                    'losing_trades': losing_trades,
                    'win_rate': float(win_rate),
                    'total_pnl': float(total_pnl),
                    'total_volume': float(total_volume),
                    'avg_win': float(avg_win),
                    'avg_loss': float(avg_loss),
                    'profit_factor': float(avg_win / abs(avg_loss)) if avg_loss != 0 else 0,
                    'daily_pnl': {k: float(v) for k, v in daily_pnl.items()}
                }
            }

        except Exception as e:
            logger.error(f"전략 성과 분석 실패: {e}")
            return {'success': False, 'error': str(e)}

    def get_position_analysis(self, strategy_id: int) -> Dict[str, Any]:
        """포지션 분석"""
        try:
            positions = StrategyPosition.query.join(StrategyAccount).filter(StrategyAccount.strategy_id == strategy_id).all()

            position_data = []
            total_value = Decimal('0')

            for position in positions:
                if position.quantity and position.quantity != 0:
                    position_value = Decimal('0')
                    if position.entry_price and position.quantity:
                        position_value = position.entry_price * position.quantity

                    total_value += position_value

                    position_data.append({
                        'symbol': position.symbol,
                        'quantity': float(position.quantity),
                        'entry_price': float(position.entry_price) if position.entry_price else 0,
                        'current_value': float(position_value),
                        'side': 'long' if position.quantity > 0 else 'short',
                        'last_updated': position.last_updated.isoformat() if position.last_updated else None
                    })

            return {
                'success': True,
                'positions': position_data,
                'total_value': float(total_value),
                'position_count': len(position_data)
            }

        except Exception as e:
            logger.error(f"포지션 분석 실패: {e}")
            return {'success': False, 'error': str(e)}

    # === 자본 관리 (Capital Service) ===

    def get_capital_overview(self, user_id: int) -> Dict[str, Any]:
        """자본 현황 개요"""
        try:
            # 사용자 계정들
            accounts = Account.query.filter_by(user_id=user_id, is_active=True).all()

            total_balance = Decimal('0')
            account_balances = []

            # 각 계정의 잔액 조회 (여기서는 임시로 0으로 설정)
            for account in accounts:
                # 실제로는 거래소 API를 통해 잔액 조회
                account_balance = {
                    'account_id': account.id,
                    'account_name': account.name,
                    'exchange': account.exchange,
                    'balance_usd': 0,  # 실제 구현에서는 API 호출
                    'is_testnet': account.is_testnet
                }
                account_balances.append(account_balance)

            # 포지션 가치
            strategies = Strategy.query.filter_by(user_id=user_id).all()
            total_position_value = Decimal('0')

            for strategy in strategies:
                positions = StrategyPosition.query.join(StrategyAccount).filter(StrategyAccount.strategy_id == strategy.id).all()
                for position in positions:
                    if position.quantity and position.entry_price:
                        total_position_value += position.entry_price * position.quantity

            return {
                'success': True,
                'capital': {
                    'total_balance_usd': float(total_balance),
                    'total_position_value_usd': float(total_position_value),
                    'total_capital_usd': float(total_balance + total_position_value),
                    'account_count': len(accounts),
                    'accounts': account_balances
                }
            }

        except Exception as e:
            logger.error(f"자본 현황 조회 실패: {e}")
            return {'success': False, 'error': str(e)}

    def get_pnl_history(self, user_id: int, period_days: int = 30) -> Dict[str, Any]:
        """수익/손실 이력"""
        try:
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=period_days)

            # 사용자의 모든 전략
            strategies = Strategy.query.filter_by(user_id=user_id).all()
            strategy_ids = [s.id for s in strategies]

            if not strategy_ids:
                return {
                    'success': True,
                    'pnl_history': {
                        'daily_pnl': {},
                        'cumulative_pnl': {},
                        'total_pnl': 0
                    }
                }

            # 기간별 거래
            trades = Trade.query.filter(
                and_(
                    Trade.strategy_account_id.in_([sa.id for sa in StrategyAccount.query.filter(StrategyAccount.strategy_id.in_(strategy_ids)).all()]),
                    Trade.timestamp >= start_date,
                    Trade.timestamp <= end_date
                )
            ).order_by(Trade.timestamp).all()

            # 일별 PnL 계산
            daily_pnl = {}
            cumulative_pnl = {}
            running_total = Decimal('0')

            # 모든 날짜 초기화
            current_date = start_date.date()
            while current_date <= end_date.date():
                date_str = current_date.isoformat()
                daily_pnl[date_str] = Decimal('0')
                current_date += timedelta(days=1)

            # 거래별 PnL 누적
            for trade in trades:
                trade_date = trade.timestamp.date().isoformat()
                if trade.pnl:
                    daily_pnl[trade_date] += trade.pnl

            # 누적 PnL 계산
            for date_str in sorted(daily_pnl.keys()):
                running_total += daily_pnl[date_str]
                cumulative_pnl[date_str] = running_total

            return {
                'success': True,
                'pnl_history': {
                    'daily_pnl': {k: float(v) for k, v in daily_pnl.items()},
                    'cumulative_pnl': {k: float(v) for k, v in cumulative_pnl.items()},
                    'total_pnl': float(running_total),
                    'period_days': period_days
                }
            }

        except Exception as e:
            logger.error(f"PnL 이력 조회 실패: {e}")
            return {'success': False, 'error': str(e)}

    # === 리포트 생성 ===

    def generate_monthly_report(self, user_id: int, year: int, month: int) -> Dict[str, Any]:
        """월간 리포트 생성"""
        try:
            # 해당 월 범위
            start_date = datetime(year, month, 1)
            if month == 12:
                end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
            else:
                end_date = datetime(year, month + 1, 1) - timedelta(days=1)

            # 기본 성과 데이터
            strategies = Strategy.query.filter_by(user_id=user_id).all()
            strategy_ids = [s.id for s in strategies]

            monthly_trades = []
            monthly_pnl = Decimal('0')

            if strategy_ids:
                trades = Trade.query.filter(
                    and_(
                        Trade.strategy_account_id.in_([sa.id for sa in StrategyAccount.query.filter(StrategyAccount.strategy_id.in_(strategy_ids)).all()]),
                        Trade.timestamp >= start_date,
                        Trade.timestamp <= end_date
                    )
                ).all()

                monthly_trades = trades
                monthly_pnl = sum([t.pnl for t in trades if t.pnl], Decimal('0'))

            # 리포트 데이터
            report = {
                'period': f"{year}-{month:02d}",
                'total_trades': len(monthly_trades),
                'total_pnl': float(monthly_pnl),
                'active_strategies': len([s for s in strategies if s.is_active]),
                'best_performing_strategy': None,
                'worst_performing_strategy': None
            }

            # 전략별 성과
            strategy_performance = {}
            for strategy in strategies:
                strategy_trades = [t for t in monthly_trades if t.strategy_id == strategy.id]
                strategy_pnl = sum([t.pnl for t in strategy_trades if t.pnl], Decimal('0'))

                strategy_performance[strategy.id] = {
                    'name': strategy.name,
                    'trades': len(strategy_trades),
                    'pnl': float(strategy_pnl)
                }

            # 최고/최저 성과 전략
            if strategy_performance:
                best_strategy = max(strategy_performance.values(), key=lambda x: x['pnl'])
                worst_strategy = min(strategy_performance.values(), key=lambda x: x['pnl'])

                report['best_performing_strategy'] = best_strategy
                report['worst_performing_strategy'] = worst_strategy

            report['strategy_performance'] = strategy_performance

            return {'success': True, 'report': report}

        except Exception as e:
            logger.error(f"월간 리포트 생성 실패: {e}")
            return {'success': False, 'error': str(e)}

    # === 통계 및 메트릭 ===

    def get_trading_statistics(self, user_id: int) -> Dict[str, Any]:
        """거래 통계"""
        try:
            strategies = Strategy.query.filter_by(user_id=user_id).all()
            strategy_ids = [s.id for s in strategies]

            if not strategy_ids:
                return {'success': True, 'statistics': {}}

            # 전체 거래
            all_trades = Trade.query.filter(Trade.strategy_account_id.in_([sa.id for sa in StrategyAccount.query.filter(StrategyAccount.strategy_id.in_(strategy_ids)).all()])).all()

            # 기본 통계
            total_trades = len(all_trades)
            winning_trades = len([t for t in all_trades if t.pnl and t.pnl > 0])
            losing_trades = len([t for t in all_trades if t.pnl and t.pnl < 0])

            # 거래량 및 수익
            total_volume = sum([t.price * t.quantity for t in all_trades if t.price and t.quantity], Decimal('0'))
            total_pnl = sum([t.pnl for t in all_trades if t.pnl], Decimal('0'))

            # 최대/최소 수익
            max_win = max([t.pnl for t in all_trades if t.pnl and t.pnl > 0], default=Decimal('0'))
            max_loss = min([t.pnl for t in all_trades if t.pnl and t.pnl < 0], default=Decimal('0'))

            statistics = {
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'losing_trades': losing_trades,
                'win_rate': (winning_trades / total_trades * 100) if total_trades > 0 else 0,
                'total_volume': float(total_volume),
                'total_pnl': float(total_pnl),
                'max_win': float(max_win),
                'max_loss': float(max_loss),
                'avg_trade_pnl': float(total_pnl / total_trades) if total_trades > 0 else 0
            }

            return {'success': True, 'statistics': statistics}

        except Exception as e:
            logger.error(f"거래 통계 조회 실패: {e}")
            return {'success': False, 'error': str(e)}


    # === 대시보드 호환성 메서드 ===
    
    def get_user_dashboard_stats(self, user_id: int) -> Dict[str, Any]:
        """대시보드 통계 데이터 조회 (dashboard.py 호환성) - N+1 쿼리 최적화 버전"""
        try:
            logger.info(f"대시보드 통계 조회 시작 - user_id: {user_id}")
            strategies = Strategy.query.filter_by(user_id=user_id).all()

            if not strategies:
                logger.info("사용자에게 전략이 없음")
                return {
                    'total_capital': 0.0,
                    'total_pnl': 0.0,
                    'realized_pnl': 0.0,
                    'unrealized_pnl': 0.0,
                    'cumulative_return': 0.0,
                    'overall_win_rate': 0.0,
                    'strategies_count': 0,
                    'total_trades': 0,
                    'strategies_detail': []
                }

            strategy_ids = [strategy.id for strategy in strategies]

            # 전략별 계정, 자본, 포지션, 거래를 한 번에 로딩
            strategy_accounts = []
            if strategy_ids:
                strategy_accounts = (
                    StrategyAccount.query.options(selectinload(StrategyAccount.account))
                    .filter(StrategyAccount.strategy_id.in_(strategy_ids))
                    .all()
                )

            strategy_accounts_by_strategy: Dict[int, List[StrategyAccount]] = defaultdict(list)
            all_strategy_account_ids: List[int] = []
            for sa in strategy_accounts:
                strategy_accounts_by_strategy[sa.strategy_id].append(sa)
                all_strategy_account_ids.append(sa.id)

            logger.info(
                "총 %s개의 전략 계정에 대한 벌크 로딩 수행",
                len(all_strategy_account_ids)
            )

            # StrategyCapital, Position, Trade 데이터 미리 로딩
            strategy_capitals: Dict[int, StrategyCapital] = {}
            strategy_positions: Dict[int, List[StrategyPosition]] = defaultdict(list)
            strategy_trades: Dict[int, List[Trade]] = defaultdict(list)

            if all_strategy_account_ids:
                capitals = StrategyCapital.query.filter(
                    StrategyCapital.strategy_account_id.in_(all_strategy_account_ids)
                ).all()
                for capital in capitals:
                    strategy_capitals[capital.strategy_account_id] = capital

                positions = StrategyPosition.query.filter(
                    StrategyPosition.strategy_account_id.in_(all_strategy_account_ids)
                ).all()
                for position in positions:
                    strategy_positions[position.strategy_account_id].append(position)

                trades = (
                    Trade.query
                    .filter(
                        and_(
                            Trade.strategy_account_id.in_(all_strategy_account_ids),
                            Trade.pnl.isnot(None)
                        )
                    )
                    .order_by(Trade.timestamp)
                    .all()
                )
                for trade in trades:
                    strategy_trades[trade.strategy_account_id].append(trade)

            logger.info(
                "벌크 로딩 완료 - 자본:%s 포지션:%s 거래:%s",
                len(strategy_capitals),
                sum(len(items) for items in strategy_positions.values()),
                sum(len(items) for items in strategy_trades.values())
            )

            total_capital = Decimal('0')
            total_realized_pnl = Decimal('0')
            total_unrealized_pnl = Decimal('0')
            aggregate_total_trades = 0
            aggregate_winning_trades = 0
            strategies_detail: List[Dict[str, Any]] = []

            period_days = 30

            for strategy in strategies:
                strategy_accounts_list = strategy_accounts_by_strategy.get(strategy.id, [])

                strategy_capital = Decimal('0')
                strategy_realized_pnl = Decimal('0')
                strategy_unrealized_pnl = Decimal('0')
                strategy_positions_count = 0
                strategy_exit_trades: List[Trade] = []
                accounts_detail: List[Dict[str, Any]] = []

                for sa in strategy_accounts_list:
                    sa_id = sa.id

                    capital_obj = strategy_capitals.get(sa_id)
                    allocated_capital = self._to_decimal(
                        capital_obj.allocated_capital if capital_obj else 0
                    )
                    strategy_capital += allocated_capital

                    positions = strategy_positions.get(sa_id, [])
                    account_position_count = len(
                        [p for p in positions if p.quantity and p.quantity != 0]
                    )
                    strategy_positions_count += account_position_count

                    account_unrealized_pnl = Decimal('0')
                    for position in positions:
                        unrealized_value = getattr(position, 'unrealized_pnl', None)
                        if unrealized_value not in (None, ''):
                            account_unrealized_pnl += self._to_decimal(unrealized_value)

                    strategy_unrealized_pnl += account_unrealized_pnl

                    account_trades = strategy_trades.get(sa_id, [])
                    account_exit_trades = self._filter_exit_trades(account_trades)

                    strategy_exit_trades.extend(account_exit_trades)

                    account_realized_pnl = sum(
                        (self._to_decimal(trade.pnl) for trade in account_trades),
                        Decimal('0')
                    )
                    strategy_realized_pnl += account_realized_pnl

                    account_metrics_30d = self._calculate_timeframe_metrics(
                        account_exit_trades,
                        allocated_capital,
                        period_days=period_days
                    )

                    account_detail = {
                        'id': sa_id,
                        'name': sa.account.name if sa.account else f'Account {sa_id}',
                        'exchange': sa.account.exchange if sa.account else '',
                        'is_active': sa.is_active,
                        'allocated_capital': float(allocated_capital),
                        'realized_pnl': float(account_realized_pnl),
                        'unrealized_pnl': float(account_unrealized_pnl),
                        'current_pnl': float(account_realized_pnl + account_unrealized_pnl),
                        'cumulative_return': float(
                            (account_realized_pnl / allocated_capital * 100)
                            if allocated_capital > 0 else Decimal('0')
                        ),
                        'position_count': account_position_count,
                        'mdd_30d': account_metrics_30d['mdd_30d'],
                        'pnl_30d': account_metrics_30d['pnl_30d'],
                        'roi_30d': account_metrics_30d['roi_30d']
                    }

                    accounts_detail.append(account_detail)

                trade_statistics = self._calculate_trade_statistics(strategy_exit_trades)
                risk_metrics = self._calculate_risk_metrics(strategy_exit_trades, strategy_capital)
                timeframe_metrics = self._calculate_timeframe_metrics(
                    strategy_exit_trades,
                    strategy_capital,
                    period_days=period_days
                )

                aggregate_total_trades += trade_statistics['total_trades']
                aggregate_winning_trades += trade_statistics['winning_trades']

                cumulative_return = (
                    (strategy_realized_pnl / strategy_capital * 100)
                    if strategy_capital > 0 else Decimal('0')
                )

                strategy_detail = {
                    'id': strategy.id,
                    'name': strategy.name,
                    'group_name': strategy.group_name,
                    'description': strategy.description or '',
                    'is_active': strategy.is_active,
                    'allocated_capital': float(strategy_capital),
                    'current_pnl': float(strategy_realized_pnl + strategy_unrealized_pnl),
                    'realized_pnl': float(strategy_realized_pnl),
                    'unrealized_pnl': float(strategy_unrealized_pnl),
                    'cumulative_return': float(cumulative_return),
                    'realized_pnl_rate': float(cumulative_return),
                    'unrealized_pnl_rate': float(
                        (strategy_unrealized_pnl / strategy_capital * 100)
                        if strategy_capital > 0 else Decimal('0')
                    ),
                    'position_count': strategy_positions_count,
                    'total_trades': trade_statistics['total_trades'],
                    'total_winning_trades': trade_statistics['winning_trades'],
                    'total_losing_trades': trade_statistics['losing_trades'],
                    'win_rate': trade_statistics['win_rate'],
                    'profit_factor': trade_statistics['profit_factor'],
                    'avg_win_trade': trade_statistics['avg_win_trade'],
                    'avg_loss_trade': trade_statistics['avg_loss_trade'],
                    'max_consecutive_wins': trade_statistics['max_consecutive_wins'],
                    'max_consecutive_losses': trade_statistics['max_consecutive_losses'],
                    'mdd': risk_metrics['mdd'],
                    'sharpe_ratio': risk_metrics['sharpe_ratio'],
                    'sortino_ratio': risk_metrics['sortino_ratio'],
                    'pnl_30d': timeframe_metrics['pnl_30d'],
                    'roi_30d': timeframe_metrics['roi_30d'],
                    'mdd_30d': timeframe_metrics['mdd_30d'],
                    'sharpe_ratio_30d': timeframe_metrics['sharpe_ratio_30d'],
                    'sparkline_data': timeframe_metrics['sparkline_data'],
                    'chart_data': timeframe_metrics['chart_data'],
                    'accounts_detail': accounts_detail
                }

                strategies_detail.append(strategy_detail)

                total_capital += strategy_capital
                total_realized_pnl += strategy_realized_pnl
                total_unrealized_pnl += strategy_unrealized_pnl

            total_pnl = total_realized_pnl  # 실현 손익 기준으로 표시
            cumulative_return_total = (
                (total_realized_pnl / total_capital * 100)
                if total_capital > 0 else Decimal('0')
            )
            overall_win_rate = (
                (aggregate_winning_trades / aggregate_total_trades * 100)
                if aggregate_total_trades > 0 else 0.0
            )

            logger.info(
                "대시보드 통계 조회 완료 - 전략:%s 총거래:%s 승률:%.2f%%",
                len(strategies),
                aggregate_total_trades,
                overall_win_rate
            )

            return {
                'total_capital': float(total_capital),
                'total_pnl': float(total_pnl),
                'realized_pnl': float(total_realized_pnl),
                'unrealized_pnl': float(total_unrealized_pnl),
                'cumulative_return': float(cumulative_return_total),
                'overall_win_rate': float(overall_win_rate),
                'strategies_count': len(strategies),
                'total_trades': aggregate_total_trades,
                'strategies_detail': strategies_detail
            }

        except Exception as e:
            logger.error(f"대시보드 통계 조회 실패: {e}")
            raise AnalyticsError(f"대시보드 통계 조회 실패: {str(e)}")

    def _to_decimal(self, value: Any) -> Decimal:
        """안전하게 Decimal 변환"""
        try:
            if value in (None, ''):
                return Decimal('0')
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return Decimal('0')

    def _filter_exit_trades(self, trades: List[Trade]) -> List[Trade]:
        """청산(Exit) 거래 필터링 - 없으면 전체 거래 반환"""
        exit_trades = [trade for trade in trades if trade.is_entry is False]
        if exit_trades:
            return exit_trades
        # is_entry 정보가 없다면 실현 손익이 있는 거래 전체를 사용
        return [trade for trade in trades if trade.pnl is not None]

    def _calculate_trade_statistics(self, trades: List[Trade]) -> Dict[str, Any]:
        """기본 거래 통계 계산"""
        if not trades:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
                'profit_factor': 0.0,
                'avg_win_trade': 0.0,
                'avg_loss_trade': 0.0,
                'max_consecutive_wins': 0,
                'max_consecutive_losses': 0
            }

        sorted_trades = sorted(
            trades,
            key=lambda trade: trade.timestamp or datetime.min
        )

        pnl_values = [
            self._to_decimal(trade.pnl)
            for trade in sorted_trades
            if trade.pnl is not None
        ]

        total_trades = len(pnl_values)
        if total_trades == 0:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
                'profit_factor': 0.0,
                'avg_win_trade': 0.0,
                'avg_loss_trade': 0.0,
                'max_consecutive_wins': 0,
                'max_consecutive_losses': 0
            }

        winning_pnls = [pnl for pnl in pnl_values if pnl > 0]
        losing_pnls = [pnl for pnl in pnl_values if pnl < 0]

        winning_trades = len(winning_pnls)
        losing_trades = len(losing_pnls)

        sum_wins = sum(winning_pnls, Decimal('0'))
        sum_losses = sum(losing_pnls, Decimal('0'))

        profit_factor = 0.0
        if sum_losses != 0:
            profit_factor = float(sum_wins / abs(sum_losses))
        elif sum_wins > 0:
            profit_factor = float(sum_wins)

        avg_win_trade = float(mean(winning_pnls)) if winning_pnls else 0.0
        avg_loss_trade = float(mean(losing_pnls)) if losing_pnls else 0.0

        max_consecutive_wins = 0
        max_consecutive_losses = 0
        current_wins = 0
        current_losses = 0

        for trade in sorted_trades:
            pnl_value = self._to_decimal(trade.pnl)
            if pnl_value > 0:
                current_wins += 1
                current_losses = 0
            elif pnl_value < 0:
                current_losses += 1
                current_wins = 0
            else:
                current_wins = 0
                current_losses = 0

            max_consecutive_wins = max(max_consecutive_wins, current_wins)
            max_consecutive_losses = max(max_consecutive_losses, current_losses)

        win_rate = float(winning_trades / total_trades * 100) if total_trades > 0 else 0.0

        return {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'avg_win_trade': avg_win_trade,
            'avg_loss_trade': avg_loss_trade,
            'max_consecutive_wins': max_consecutive_wins,
            'max_consecutive_losses': max_consecutive_losses
        }

    def _calculate_risk_metrics(self, trades: List[Trade], allocated_capital: Decimal) -> Dict[str, float]:
        """전략 리스크 메트릭 계산"""
        capital_decimal = self._to_decimal(allocated_capital)
        if not trades or capital_decimal <= 0:
            return {
                'mdd': 0.0,
                'sharpe_ratio': 0.0,
                'sortino_ratio': 0.0
            }

        daily_returns = self._calculate_daily_returns(trades, capital_decimal)

        return {
            'mdd': self._calculate_drawdown(trades, capital_decimal),
            'sharpe_ratio': self._calculate_sharpe_ratio(daily_returns),
            'sortino_ratio': self._calculate_sortino_ratio(daily_returns)
        }

    def _calculate_timeframe_metrics(self, trades: List[Trade], allocated_capital: Decimal, period_days: int = 30) -> Dict[str, Any]:
        """기간 기반 메트릭 계산 (기본 30일)"""
        capital_decimal = self._to_decimal(allocated_capital)
        metrics = {
            'pnl_30d': 0.0,
            'roi_30d': 0.0,
            'mdd_30d': 0.0,
            'sharpe_ratio_30d': 0.0,
            'sparkline_data': [],
            'chart_data': None
        }

        if not trades:
            sparkline_data, chart_data = self._build_equity_curve([], period_days)
            metrics['sparkline_data'] = sparkline_data
            metrics['chart_data'] = chart_data
            return metrics

        start_time = datetime.utcnow() - timedelta(days=period_days)
        trades_in_period = [
            trade for trade in trades
            if trade.timestamp and trade.timestamp >= start_time and trade.pnl is not None
        ]

        sparkline_data, chart_data = self._build_equity_curve(trades_in_period, period_days)
        metrics['sparkline_data'] = sparkline_data
        metrics['chart_data'] = chart_data

        if not trades_in_period:
            return metrics

        pnl_sum = sum(
            (self._to_decimal(trade.pnl) for trade in trades_in_period),
            Decimal('0')
        )
        metrics['pnl_30d'] = float(pnl_sum)
        if capital_decimal > 0:
            metrics['roi_30d'] = float((pnl_sum / capital_decimal) * 100)
        metrics['mdd_30d'] = self._calculate_drawdown(trades_in_period, capital_decimal)
        daily_returns = self._calculate_daily_returns(
            trades_in_period,
            capital_decimal,
            period_days=period_days
        )
        metrics['sharpe_ratio_30d'] = self._calculate_sharpe_ratio(daily_returns)
        return metrics

    def _calculate_daily_returns(
        self,
        trades: List[Trade],
        allocated_capital: Decimal,
        period_days: Optional[int] = None
    ) -> List[float]:
        """일별 수익률(%) 리스트 계산"""
        capital_decimal = self._to_decimal(allocated_capital)
        if capital_decimal <= 0:
            return []

        daily_pnl_map = self._build_daily_pnl_map(trades, period_days)
        returns: List[float] = []

        for _, pnl in sorted(daily_pnl_map.items(), key=lambda item: item[0]):
            returns.append(float((pnl / capital_decimal) * 100))

        return returns

    def _build_daily_pnl_map(
        self,
        trades: List[Trade],
        period_days: Optional[int] = None
    ) -> Dict[datetime.date, Decimal]:
        """일자별 실현 손익 합계 생성"""
        daily_pnl: Dict[datetime.date, Decimal] = defaultdict(lambda: Decimal('0'))
        cutoff_date = None
        if period_days is not None:
            cutoff_date = (datetime.utcnow() - timedelta(days=period_days)).date()

        for trade in trades:
            if not trade.timestamp or trade.pnl is None:
                continue
            trade_date = trade.timestamp.date()
            if cutoff_date and trade_date < cutoff_date:
                continue
            daily_pnl[trade_date] += self._to_decimal(trade.pnl)

        return daily_pnl

    def _calculate_drawdown(self, trades: List[Trade], allocated_capital: Decimal) -> float:
        """최대 낙폭 계산"""
        capital_decimal = self._to_decimal(allocated_capital)
        if not trades or capital_decimal <= 0:
            return 0.0

        cumulative = Decimal('0')
        peak = Decimal('0')
        max_drawdown = Decimal('0')

        for trade in sorted(trades, key=lambda t: t.timestamp or datetime.min):
            pnl_value = self._to_decimal(trade.pnl)
            cumulative += pnl_value
            if cumulative > peak:
                peak = cumulative
            drawdown = peak - cumulative
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        if capital_decimal == 0:
            return 0.0

        return float((max_drawdown / capital_decimal) * 100) if max_drawdown > 0 else 0.0

    def _calculate_sharpe_ratio(self, daily_returns: List[float]) -> float:
        """샤프 비율 계산 (252거래일 기준)"""
        if len(daily_returns) < 2:
            return 0.0
        try:
            volatility = pstdev(daily_returns)
        except StatisticsError:
            return 0.0
        if volatility == 0:
            return 0.0
        return (mean(daily_returns) / volatility) * sqrt(252)

    def _calculate_sortino_ratio(self, daily_returns: List[float]) -> float:
        """소르티노 비율 계산"""
        if not daily_returns:
            return 0.0
        negative_returns = [ret for ret in daily_returns if ret < 0]
        if not negative_returns:
            return 0.0
        downside_deviation = sqrt(
            sum(ret ** 2 for ret in negative_returns) / len(negative_returns)
        )
        if downside_deviation == 0:
            return 0.0
        return (mean(daily_returns) / downside_deviation) * sqrt(252)

    def _build_equity_curve(
        self,
        trades: List[Trade],
        period_days: int
    ) -> Tuple[List[float], Dict[str, Any]]:
        """기간 동안의 누적 손익 곡선 생성"""
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=period_days)

        daily_pnl_map = self._build_daily_pnl_map(trades, period_days)

        dates: List[str] = []
        pnl_values: List[float] = []
        cumulative = Decimal('0')

        current_date = start_date
        while current_date <= end_date:
            dates.append(current_date.isoformat())
            daily_pnl = daily_pnl_map.get(current_date, Decimal('0'))
            cumulative += daily_pnl
            pnl_values.append(float(cumulative))
            current_date += timedelta(days=1)

        has_data = any(abs(value) > 1e-9 for value in pnl_values)

        if pnl_values:
            total_change = pnl_values[-1] - pnl_values[0]
            start_value = pnl_values[0]
            end_value = pnl_values[-1]
            max_value = max(pnl_values)
            min_value = min(pnl_values)
        else:
            total_change = 0.0
            start_value = 0.0
            end_value = 0.0
            max_value = 0.0
            min_value = 0.0

        chart_data = {
            'dates': dates,
            'pnl_values': pnl_values,
            'summary': {
                'total_change': total_change,
                'start_value': start_value,
                'end_value': end_value,
                'max_value': max_value,
                'min_value': min_value,
                'is_positive': end_value >= start_value,
                'has_data': has_data
            }
        }

        return pnl_values, chart_data

    def get_user_recent_trades(self, user_id: int, limit: int = 10, offset: int = 0) -> List[Dict[str, Any]]:
        """사용자의 최근 거래 내역 조회 - TradeExecution 테이블 기반 (실제 체결된 거래만)"""
        try:
            logger.info(f"최근 거래 내역 조회 시작 (TradeExecution 기반) - user_id: {user_id}, limit: {limit}, offset: {offset}")

            # TradeExecution 테이블에서 직접 조회 - 실제 체결된 거래만 존재
            query = (
                db.session.query(
                    TradeExecution.id,
                    TradeExecution.symbol,
                    TradeExecution.side,
                    TradeExecution.execution_price.label('price'),
                    TradeExecution.execution_quantity.label('quantity'),
                    TradeExecution.realized_pnl.label('pnl'),
                    TradeExecution.commission.label('fee'),
                    TradeExecution.commission_asset,
                    TradeExecution.execution_time.label('timestamp'),
                    TradeExecution.is_maker,
                    TradeExecution.market_type,
                    TradeExecution.exchange_order_id,
                    TradeExecution.exchange_trade_id,
                    Strategy.name.label('strategy_name'),
                    Account.name.label('account_name'),
                    Account.exchange.label('account_exchange')
                )
                .join(StrategyAccount, TradeExecution.strategy_account_id == StrategyAccount.id)
                .join(Strategy, StrategyAccount.strategy_id == Strategy.id)
                .join(Account, StrategyAccount.account_id == Account.id)
                .filter(Strategy.user_id == user_id)
                .order_by(TradeExecution.execution_time.desc())
                .offset(offset)
                .limit(limit)
            )

            results = query.all()
            
            logger.info(f"TradeExecution 테이블에서 {len(results)}개의 체결 거래 조회됨")

            trades_data: List[Dict[str, Any]] = []
            for row in results:
                # 거래소별 order_type 추론 (TradeExecution에는 order_type이 없으므로)
                order_type = 'MARKET'  # 기본값
                if row.is_maker is not None:
                    order_type = 'LIMIT' if row.is_maker else 'MARKET'
                
                # side는 소문자로 변환하여 프론트엔드 색상 로직과 호환
                side_value = (row.side or '').lower()
                if side_value == 'buy':
                    side_value = 'buy'
                elif side_value == 'sell':
                    side_value = 'sell'
                
                trade_data = {
                    'id': row.id,
                    'strategy_name': row.strategy_name or 'Unknown',
                    'name': row.account_name or 'Unknown',
                    'exchange': row.account_exchange or '',
                    'symbol': row.symbol or '',
                    'side': side_value,
                    'order_type': order_type,
                    'price': float(row.price) if row.price is not None else 0.0,
                    'quantity': float(row.quantity) if row.quantity is not None else 0.0,
                    'pnl': float(row.pnl) if row.pnl is not None else None,
                    'fee': float(row.fee) if row.fee is not None else 0.0,
                    'timestamp': row.timestamp.isoformat() if row.timestamp else None,
                    'is_maker': row.is_maker,
                    'market_type': row.market_type,
                    'exchange_trade_id': row.exchange_trade_id,
                    'commission_asset': row.commission_asset
                }
                
                trades_data.append(trade_data)
                
                # 디버깅용 로그
                logger.debug(f"TradeExecution ID {row.id}: symbol={row.symbol}, side={side_value}, "
                           f"price={row.price}, qty={row.quantity}, pnl={row.pnl}, "
                           f"trade_id={row.exchange_trade_id}")

            logger.info(f"최근 거래 내역 조회 완료 (TradeExecution 기반) - {len(trades_data)}개 거래 반환")
            return trades_data
            
        except Exception as e:
            logger.error(f"최근 거래 내역 조회 실패 (TradeExecution): {e}")
            raise AnalyticsError(f"최근 거래 내역 조회 실패: {str(e)}")

    def _extract_market_totals(self, balance_snapshot: Optional[Dict[str, Any]]) -> Dict[str, float]:
        """보유 잔고 스냅샷에서 마켓별 총 잔고를 추출"""
        if not balance_snapshot:
            return {}

        market_totals: Dict[str, float] = {}

        market_summaries = balance_snapshot.get('market_summaries') or []
        for summary in market_summaries:
            if not summary:
                continue

            market_key = str(summary.get('market_type', '')).lower()
            total_balance = summary.get('total_balance')
            if not market_key:
                continue

            try:
                total_value = float(total_balance)
            except (TypeError, ValueError):
                continue

            if total_value <= 0:
                continue

            market_totals[market_key] = total_value

        # 단일 마켓에서만 전략을 사용하는 경우를 대비해 총 잔고를 보조값으로 사용
        if not market_totals:
            total_balance = balance_snapshot.get('total_balance')
            try:
                total_value = float(total_balance)
            except (TypeError, ValueError, OverflowError):
                total_value = 0.0

            if total_value > 0:
                market_totals[MarketType.SPOT_LOWER] = total_value

        return market_totals

    def _get_cached_daily_balance(self, account_id: int) -> Optional[float]:
        """가장 최근 저장된 일일 요약에서 총 잔고를 가져온다"""
        summary = (
            DailyAccountSummary.query
            .filter_by(account_id=account_id)
            .order_by(DailyAccountSummary.date.desc())
            .first()
        )

        if not summary:
            return None

        latest_balance = summary.ending_balance or summary.starting_balance or 0.0
        return float(latest_balance) if latest_balance else None

    def auto_allocate_capital_for_account(self, account_id: int) -> bool:
        """계좌에 연결된 모든 전략에 마켓 타입별로 자동 자본 할당"""
        try:
            # 계좌 조회
            account = Account.query.get(account_id)
            if not account:
                logger.error(f'자본 할당 실패: 계좌 ID {account_id}를 찾을 수 없음')
                return False

            # 해당 계좌에 연결된 모든 전략 조회
            strategy_accounts = StrategyAccount.query.filter_by(account_id=account_id).all()

            if not strategy_accounts:
                logger.info(f'계좌 {account.name}에 연결된 전략이 없음')
                return True

            # 마켓 타입별로 전략 분리
            spot_strategies = []
            futures_strategies = []

            for sa in strategy_accounts:
                if sa.strategy.market_type == MarketType.FUTURES:
                    futures_strategies.append(sa)
                else:  # 기본값은 spot
                    spot_strategies.append(sa)

            logger.info(f'계좌 {account.name}: spot 전략 {len(spot_strategies)}개, futures 전략 {len(futures_strategies)}개')

            balance_snapshot: Optional[Dict[str, Any]] = None
            total_by_market: Dict[str, float] = {}

            try:
                from flask import current_app

                skip_live_fetch = current_app.config.get('SKIP_EXCHANGE_TEST', False)
            except RuntimeError:
                # 애플리케이션 컨텍스트 외부에서는 실시간 조회 시도
                skip_live_fetch = False

            if not skip_live_fetch:
                try:
                    balance_result = security_service.get_account_balance(account.id, account.user_id)
                except Exception as e:
                    logger.error('계좌 %s 잔고 조회 호출 중 예외 발생: %s', account.name, str(e))
                else:
                    if balance_result.get('success'):
                        balance_snapshot = balance_result.get('balance') or {}
                        total_by_market = self._extract_market_totals(balance_snapshot)
                    else:
                        logger.warning(
                            '계좌 %s 잔고 조회 실패: %s',
                            account.name,
                            balance_result.get('error') or '알 수 없는 오류'
                        )
            else:
                logger.debug('SKIP_EXCHANGE_TEST 설정으로 실시간 잔고 조회를 건너뜀 (account_id=%s)', account.id)

            if not total_by_market:
                cached_total = self._get_cached_daily_balance(account.id)
                if cached_total:
                    if spot_strategies and not futures_strategies:
                        total_by_market[MarketType.SPOT_LOWER] = cached_total
                    elif futures_strategies and not spot_strategies:
                        total_by_market[MarketType.FUTURES_LOWER] = cached_total
                    else:
                        # 양쪽 마켓 모두 사용할 경우에는 절반씩 임시 분배
                        total_by_market[MarketType.SPOT_LOWER] = cached_total / 2
                        total_by_market[MarketType.FUTURES_LOWER] = cached_total / 2
                        logger.warning(
                            '계좌 %s에 대한 시장별 잔고를 찾을 수 없어 총 잔고를 균등 분배했습니다. (총 %.2f)',
                            account.name,
                            cached_total
                        )
                else:
                    logger.warning('계좌 %s에 대해 사용 가능한 잔고 정보를 찾을 수 없어 자본 할당을 건너뜀', account.name)
                    return False

            # 각 마켓 타입별로 자본 할당 처리
            success_count = 0

            # 1. Spot 전략들 처리
            spot_total = total_by_market.get(MarketType.SPOT_LOWER)
            if spot_strategies and spot_total is not None:
                if self._allocate_capital_by_market_type(account, spot_strategies, MarketType.SPOT_LOWER, spot_total):
                    success_count += 1

            # 2. Futures 전략들 처리
            futures_total = total_by_market.get(MarketType.FUTURES_LOWER)
            if futures_strategies and futures_total is not None:
                if self._allocate_capital_by_market_type(account, futures_strategies, MarketType.FUTURES_LOWER, futures_total):
                    success_count += 1

            db.session.commit()
            logger.info(f'계좌 {account.name}의 마켓별 자본 할당 완료 ({success_count}개 마켓)')
            return success_count > 0
            
        except Exception as e:
            db.session.rollback()
            logger.error(f'자동 자본 할당 오류: {str(e)}')
            return False

    def _allocate_capital_by_market_type(self, account: Account, strategy_accounts: List[StrategyAccount], market_type: str, total_balance: float) -> bool:
        """특정 마켓 타입의 전략들에 자본 할당"""
        try:
            # 해당 마켓 타입의 총 weight 계산
            total_weight = sum(sa.weight for sa in strategy_accounts)
            
            if total_weight <= 0:
                logger.warning(f'계좌 {account.name} {market_type}의 총 weight가 0 이하: {total_weight}')
                return False

            try:
                total_balance_value = float(total_balance)
            except (TypeError, ValueError):
                logger.warning(f'계좌 {account.name} {market_type} 잔고 값 변환 실패: {total_balance}')
                return False

            if total_balance_value < 0:
                logger.warning(f'계좌 {account.name} {market_type} 잔고가 음수입니다: {total_balance_value}')
                return False
            
            # 각 전략에 비례적으로 자본 할당
            for strategy_account in strategy_accounts:
                allocated_amount = (total_balance_value * strategy_account.weight) / total_weight
                
                # 기존 자본 정보가 있는지 확인
                existing_capital = StrategyCapital.query.filter_by(strategy_account_id=strategy_account.id).first()
                
                if existing_capital:
                    # 기존 자본 정보 업데이트
                    existing_capital.allocated_capital = allocated_amount
                    existing_capital.last_updated = datetime.utcnow()
                    logger.info(f'자본 할당 업데이트: 전략 {strategy_account.strategy.name} ({market_type}) - ${allocated_amount:.2f}')
                else:
                    # 새 자본 정보 생성
                    new_capital = StrategyCapital(
                        strategy_account_id=strategy_account.id,
                        allocated_capital=allocated_amount,
                        current_pnl=0.0
                    )
                    db.session.add(new_capital)
                    logger.info(f'자본 할당 생성: 전략 {strategy_account.strategy.name} ({market_type}) - ${allocated_amount:.2f}')
            
            logger.info(f'계좌 {account.name} {market_type} 자본 할당 완료 (총 잔고: ${total_balance_value:.2f}, 총 weight: {total_weight})')
            return True
            
        except Exception as e:
            logger.error(f'{market_type} 자본 할당 오류: {str(e)}')
            return False

# 싱글톤 인스턴스
analytics_service = AnalyticsService()
