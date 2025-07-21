from decimal import Decimal
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy import func, and_, or_
from sqlalchemy.orm import Session

from app import db
from app.models import (
    Account, StrategyPosition, Trade, OpenOrder, StrategyCapital, 
    DailyAccountSummary, SystemSummary, StrategyAccount
)
from app.services.utils import to_decimal, decimal_to_float


class AnalyticsError(Exception):
    """Analytics 관련 예외"""
    pass


class AnalyticsService:
    """분석 및 요약 데이터 생성 서비스"""
    
    def get_daily_summary(self, account_id: int, date: datetime = None) -> Dict[str, Any]:
        """일일 요약 데이터 생성"""
        try:
            if date is None:
                date = datetime.now().date()
            elif isinstance(date, datetime):
                date = date.date()
            
            account = db.session.query(Account).filter(Account.id == account_id).first()
            if not account:
                raise AnalyticsError(f"계정을 찾을 수 없습니다: {account_id}")
            
            # 기존 요약 데이터 확인
            existing_summary = db.session.query(DailyAccountSummary).filter(
                and_(
                    DailyAccountSummary.account_id == account_id,
                    DailyAccountSummary.date == date
                )
            ).first()
            
            if existing_summary:
                return {
                    'date': existing_summary.date,
                    'starting_balance': decimal_to_float(existing_summary.starting_balance),
                    'ending_balance': decimal_to_float(existing_summary.ending_balance),
                    'total_pnl': decimal_to_float(existing_summary.total_pnl),
                    'realized_pnl': decimal_to_float(existing_summary.realized_pnl),
                    'unrealized_pnl': decimal_to_float(existing_summary.unrealized_pnl),
                    'total_trades': existing_summary.total_trades,
                    'winning_trades': existing_summary.winning_trades,
                    'losing_trades': existing_summary.losing_trades,
                    'win_rate': decimal_to_float(existing_summary.win_rate),
                    'max_drawdown': decimal_to_float(existing_summary.max_drawdown),
                    'total_volume': decimal_to_float(existing_summary.total_volume),
                    'total_fees': decimal_to_float(existing_summary.total_fees)
                }
            
            # 새로운 요약 데이터 계산
            start_of_day = datetime.combine(date, datetime.min.time())
            end_of_day = datetime.combine(date, datetime.max.time())
            
            # 해당 계정의 모든 전략 계정 조회
            strategy_accounts = db.session.query(StrategyAccount).filter(
                StrategyAccount.account_id == account_id
            ).all()
            
            strategy_account_ids = [sa.id for sa in strategy_accounts]
            
            # 하루 동안의 거래 조회
            trades = []
            if strategy_account_ids:
                trades = db.session.query(Trade).filter(
                    and_(
                        Trade.strategy_account_id.in_(strategy_account_ids),
                        Trade.timestamp >= start_of_day,
                        Trade.timestamp <= end_of_day
                    )
                ).all()
            
            # 거래 통계 계산
            total_trades = len(trades)
            winning_trades = len([t for t in trades if t.pnl and t.pnl > 0])
            losing_trades = len([t for t in trades if t.pnl and t.pnl < 0])
            win_rate = Decimal('0')
            if total_trades > 0:
                win_rate = Decimal(winning_trades) / Decimal(total_trades) * Decimal('100')
            
            # 실현 손익 계산
            realized_pnl = sum([t.pnl for t in trades if t.pnl], Decimal('0'))
            
            # 총 거래량 및 수수료 계산
            total_volume = sum([abs(t.quantity * t.price) for t in trades], Decimal('0'))
            total_fees = sum([t.fee for t in trades if t.fee], Decimal('0'))
            
            # 미실현 손익 계산 (현재 포지션들)
            unrealized_pnl = self._calculate_account_unrealized_pnl(strategy_account_ids)
            
            # 총 손익
            total_pnl = realized_pnl + unrealized_pnl
            
            # 시작 잔고 (전날 종료 잔고 또는 계정 초기 잔고)
            previous_date = date - timedelta(days=1)
            previous_summary = db.session.query(DailyAccountSummary).filter(
                and_(
                    DailyAccountSummary.account_id == account_id,
                    DailyAccountSummary.date == previous_date
                )
            ).first()
            
            starting_balance = previous_summary.ending_balance if previous_summary else Decimal('0')
            ending_balance = starting_balance + total_pnl
            
            # 최대 낙폭 계산
            max_drawdown = self._calculate_max_drawdown(account_id, date)
            
            # 요약 데이터 저장
            summary = DailyAccountSummary(
                account_id=account_id,
                date=date,
                starting_balance=decimal_to_float(starting_balance),
                ending_balance=decimal_to_float(ending_balance),
                total_pnl=decimal_to_float(total_pnl),
                realized_pnl=decimal_to_float(realized_pnl),
                unrealized_pnl=decimal_to_float(unrealized_pnl),
                total_trades=total_trades,
                winning_trades=winning_trades,
                losing_trades=losing_trades,
                win_rate=decimal_to_float(win_rate),
                max_drawdown=decimal_to_float(max_drawdown),
                total_volume=decimal_to_float(total_volume),
                total_fees=decimal_to_float(total_fees)
            )
            
            db.session.add(summary)
            db.session.commit()
            
            return {
                'date': date,
                'starting_balance': decimal_to_float(starting_balance),
                'ending_balance': decimal_to_float(ending_balance),
                'total_pnl': decimal_to_float(total_pnl),
                'realized_pnl': decimal_to_float(realized_pnl),
                'unrealized_pnl': decimal_to_float(unrealized_pnl),
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'losing_trades': losing_trades,
                'win_rate': decimal_to_float(win_rate),
                'max_drawdown': decimal_to_float(max_drawdown),
                'total_volume': decimal_to_float(total_volume),
                'total_fees': decimal_to_float(total_fees)
            }
            
        except Exception as e:
            db.session.rollback()
            raise AnalyticsError(f"일일 요약 데이터 생성 실패: {str(e)}")
    
    def _calculate_max_drawdown(self, account_id: int, date: datetime.date) -> Decimal:
        """최대 낙폭 계산"""
        try:
            # 해당 날짜까지의 모든 일일 요약 데이터 조회
            summaries = db.session.query(DailyAccountSummary).filter(
                and_(
                    DailyAccountSummary.account_id == account_id,
                    DailyAccountSummary.date <= date
                )
            ).order_by(DailyAccountSummary.date).all()
            
            if not summaries:
                return Decimal('0')
            
            max_balance = Decimal('0')
            max_drawdown = Decimal('0')
            
            for summary in summaries:
                # ending_balance를 Decimal로 변환하여 타입 통일
                ending_balance_decimal = to_decimal(summary.ending_balance)
                if ending_balance_decimal > max_balance:
                    max_balance = ending_balance_decimal
                
                # max_balance가 0보다 클 때만 낙폭 계산
                if max_balance > 0:
                    current_drawdown = (max_balance - ending_balance_decimal) / max_balance * Decimal('100')
                    if current_drawdown > max_drawdown:
                        max_drawdown = current_drawdown
            
            return max_drawdown
            
        except Exception as e:
            raise AnalyticsError(f"최대 낙폭 계산 실패: {str(e)}")
    
    def _calculate_account_unrealized_pnl(self, strategy_account_ids: List[int]) -> Decimal:
        """특정 계정의 미실현 손익 계산"""
        try:
            if not strategy_account_ids:
                return Decimal('0')
            
            from app.services.exchange_service import exchange_service
            from app.services.utils import to_decimal
            
            total_unrealized_pnl = Decimal('0')
            
            # 해당 전략 계정들의 모든 포지션 조회
            positions = db.session.query(StrategyPosition).filter(
                and_(
                    StrategyPosition.strategy_account_id.in_(strategy_account_ids),
                    StrategyPosition.quantity != 0
                )
            ).all()
            
            for position in positions:
                try:
                    # strategy_account를 통해 account 조회
                    strategy_account = db.session.query(StrategyAccount).get(position.strategy_account_id)
                    if not strategy_account or not strategy_account.account.is_active:
                        continue
                    
                    # 현재 시세 조회
                    ticker = exchange_service.get_ticker(strategy_account.account, position.symbol)
                    current_price = to_decimal(ticker['last'])
                    
                    # 포지션 정보를 Decimal로 변환
                    position_qty = to_decimal(position.quantity)
                    entry_price = to_decimal(position.entry_price)
                    
                    # 미실현 손익 계산
                    if position_qty > 0:
                        # 롱 포지션
                        unrealized_pnl = position_qty * (current_price - entry_price)
                    else:
                        # 숏 포지션
                        unrealized_pnl = abs(position_qty) * (entry_price - current_price)
                    
                    total_unrealized_pnl += unrealized_pnl
                    
                except Exception as e:
                    # 개별 포지션 계산 실패는 로그만 남기고 계속 진행
                    continue
            
            return total_unrealized_pnl
            
        except Exception as e:
            # 전체 계산 실패 시 0 반환
            return Decimal('0')
    
    def _calculate_system_mdd(self) -> Decimal:
        """시스템 전체 최대 낙폭 계산"""
        try:
            # 모든 계정의 일일 요약 데이터를 날짜별로 집계
            summaries = db.session.query(
                DailyAccountSummary.date,
                func.sum(DailyAccountSummary.ending_balance).label('total_balance')
            ).group_by(DailyAccountSummary.date).order_by(DailyAccountSummary.date).all()
            
            if not summaries:
                return Decimal('0')
            
            max_balance = Decimal('0')
            max_drawdown = Decimal('0')
            
            for summary in summaries:
                total_balance = to_decimal(summary.total_balance)
                
                if total_balance > max_balance:
                    max_balance = total_balance
                
                if max_balance > 0:
                    current_drawdown = (max_balance - total_balance) / max_balance * Decimal('100')
                    if current_drawdown > max_drawdown:
                        max_drawdown = current_drawdown
            
            return max_drawdown
            
        except Exception as e:
            raise AnalyticsError(f"시스템 MDD 계산 실패: {str(e)}")
    
    def get_account_performance_metrics(self, account_id: int, start_date: datetime = None, end_date: datetime = None) -> Dict[str, Any]:
        """계정 성과 지표 조회"""
        try:
            query = db.session.query(DailyAccountSummary).filter(DailyAccountSummary.account_id == account_id)
            
            if start_date:
                query = query.filter(DailyAccountSummary.date >= start_date.date())
            if end_date:
                query = query.filter(DailyAccountSummary.date <= end_date.date())
            
            summaries = query.order_by(DailyAccountSummary.date).all()
            
            if not summaries:
                return {
                    'total_pnl': 0,
                    'total_trades': 0,
                    'win_rate': 0,
                    'max_drawdown': 0,
                    'sharpe_ratio': 0,
                    'profit_factor': 0
                }
            
            # 기본 지표 계산
            total_pnl = sum([to_decimal(s.total_pnl) for s in summaries], Decimal('0'))
            total_trades = sum([s.total_trades for s in summaries])
            
            # 승률 계산
            total_winning = sum([s.winning_trades for s in summaries])
            win_rate = Decimal('0')
            if total_trades > 0:
                win_rate = Decimal(total_winning) / Decimal(total_trades) * Decimal('100')
            
            # 최대 낙폭
            max_drawdown = max([to_decimal(s.max_drawdown) for s in summaries], default=Decimal('0'))
            
            # 샤프 비율 계산 (간단한 버전)
            daily_returns = []
            for i in range(1, len(summaries)):
                prev_balance = to_decimal(summaries[i-1].ending_balance)
                curr_balance = to_decimal(summaries[i].ending_balance)
                # prev_balance가 0보다 클 때만 수익률 계산
                if prev_balance > 0:
                    daily_return = (curr_balance - prev_balance) / prev_balance
                    daily_returns.append(daily_return)
            
            sharpe_ratio = Decimal('0')
            if daily_returns:
                avg_return = sum(daily_returns) / len(daily_returns)
                if len(daily_returns) > 1:
                    variance = sum([(r - avg_return) ** 2 for r in daily_returns]) / (len(daily_returns) - 1)
                    std_dev = variance ** Decimal('0.5')
                    # std_dev가 0보다 클 때만 샤프 비율 계산
                    if std_dev > 0:
                        sharpe_ratio = avg_return / std_dev * (Decimal('252') ** Decimal('0.5'))  # 연환산
            
            # 수익 팩터 계산
            total_profit = sum([to_decimal(s.realized_pnl) for s in summaries if s.realized_pnl > 0], Decimal('0'))
            total_loss = abs(sum([to_decimal(s.realized_pnl) for s in summaries if s.realized_pnl < 0], Decimal('0')))
            profit_factor = Decimal('0')
            # total_loss가 0보다 클 때만 수익 팩터 계산
            if total_loss > 0:
                profit_factor = total_profit / total_loss
            
            return {
                'total_pnl': decimal_to_float(total_pnl),
                'total_trades': total_trades,
                'win_rate': decimal_to_float(win_rate),
                'max_drawdown': decimal_to_float(max_drawdown),
                'sharpe_ratio': decimal_to_float(sharpe_ratio),
                'profit_factor': decimal_to_float(profit_factor)
            }
            
        except Exception as e:
            raise AnalyticsError(f"성과 지표 조회 실패: {str(e)}")


# 전역 인스턴스 생성
analytics_service = AnalyticsService() 