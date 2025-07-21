"""
대시보드 서비스 모듈
대시보드 통계 데이터 조회, 집계, 계산 등 대시보드 관련 비즈니스 로직
"""

import logging
import numpy as np
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from decimal import Decimal
from collections import defaultdict

from sqlalchemy import func, and_
from sqlalchemy.orm import joinedload, selectinload
from app import db
from app.models import (
    Strategy, StrategyAccount, StrategyCapital, StrategyPosition, 
    Trade, Account
)
from app.services.utils import to_decimal, decimal_to_float

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # 디버깅을 위한 로그 레벨 설정

class DashboardError(Exception):
    """대시보드 관련 오류"""
    pass

class DashboardService:
    """대시보드 서비스 클래스"""
    
    def __init__(self):
        self.session = db.session
    
    def get_user_dashboard_stats(self, user_id: int) -> Dict[str, Any]:
        """사용자의 대시보드 통계 데이터 조회 - 최적화된 버전"""
        try:
            # 최적화된 메서드로 교체
            return self._get_user_dashboard_stats_optimized(user_id)
            
        except Exception as e:
            logger.error(f'대시보드 통계 조회 오류: {str(e)}')
            raise DashboardError(f'대시보드 통계 조회 실패: {str(e)}')
    
    def _get_user_dashboard_stats_optimized(self, user_id: int) -> Dict[str, Any]:
        """최적화된 대시보드 통계 데이터 조회 - 5개 쿼리로 모든 데이터 처리"""
        try:
            # 1. 사용자의 모든 전략-계좌-자본 데이터를 한 번에 로드
            strategy_account_data = self._bulk_load_strategy_account_data(user_id)
            
            if not strategy_account_data:
                return self._get_empty_dashboard_stats()
            
            # 2. 집계된 재무 데이터 로드 (실현손익, 포지션 등)
            financial_aggregates = self._bulk_load_financial_aggregates(user_id)
            
            # 3. 거래 데이터 bulk 로드
            trades_data = self._bulk_load_trades_data(user_id)
            
            # 4. 30일 거래 데이터 로드
            trades_30d_data = self._bulk_load_30day_trades_data(user_id)
            
            # 5. 메모리에서 모든 지표 계산
            return self._calculate_dashboard_stats_in_memory(
                strategy_account_data, financial_aggregates, trades_data, trades_30d_data
            )
            
        except Exception as e:
            logger.error(f'최적화된 대시보드 통계 조회 오류: {str(e)}')
            raise DashboardError(f'최적화된 대시보드 통계 조회 실패: {str(e)}')
    
    def _bulk_load_strategy_account_data(self, user_id: int) -> List[Dict[str, Any]]:
        """사용자의 모든 전략-계좌-자본 데이터를 한 번에 로드"""
        try:
            # Strategy -> StrategyAccount -> Account, StrategyCapital 한 번에 JOIN
            query = (
                self.session.query(
                    Strategy.id.label('strategy_id'),
                    Strategy.name.label('strategy_name'),
                    Strategy.group_name.label('strategy_group_name'),
                    Strategy.is_active.label('strategy_is_active'),
                    StrategyAccount.id.label('strategy_account_id'),
                    Account.name.label('account_name'),
                    Account.exchange.label('account_exchange'),
                    Account.is_active.label('account_is_active'),
                    StrategyCapital.allocated_capital.label('allocated_capital'),
                    StrategyCapital.current_pnl.label('current_pnl')
                )
                .join(StrategyAccount, Strategy.id == StrategyAccount.strategy_id)
                .join(Account, StrategyAccount.account_id == Account.id)
                .outerjoin(StrategyCapital, StrategyAccount.id == StrategyCapital.strategy_account_id)
                .filter(Strategy.user_id == user_id)
            )
            
            results = query.all()
            
            # 활성 포지션이 있는 전략 계좌 조회
            active_positions_query = (
                self.session.query(
                    StrategyAccount.id.label('strategy_account_id'),
                    func.sum(func.abs(StrategyPosition.quantity)).label('total_position_qty')
                )
                .join(StrategyPosition, StrategyAccount.id == StrategyPosition.strategy_account_id)
                .join(Strategy, StrategyAccount.strategy_id == Strategy.id)
                .filter(
                    Strategy.user_id == user_id,
                    StrategyPosition.quantity != 0
                )
                .group_by(StrategyAccount.id)
            )
            
            # 활성 포지션이 있는 계좌 ID 집합 생성
            active_accounts = set()
            for row in active_positions_query.all():
                if row.total_position_qty and row.total_position_qty > 0:
                    active_accounts.add(row.strategy_account_id)
            
            # 결과를 딕셔너리 리스트로 변환
            data = []
            for row in results:
                # 실제 활성 포지션이 있는 경우만 미실현 손익 적용
                has_active_positions = row.strategy_account_id in active_accounts
                unrealized_pnl = float(row.current_pnl) if (row.current_pnl and has_active_positions) else 0
                
                data.append({
                    'strategy_id': row.strategy_id,
                    'strategy_name': row.strategy_name,
                    'strategy_group_name': row.strategy_group_name,
                    'strategy_is_active': row.strategy_is_active,
                    'account_id': row.strategy_account_id,
                    'account_name': row.account_name,
                    'account_exchange': row.account_exchange,
                    'account_is_active': row.account_is_active,
                    'allocated_capital': float(row.allocated_capital) if row.allocated_capital else 0,
                    'unrealized_pnl': unrealized_pnl
                })
            
            return data
            
        except Exception as e:
            logger.error(f'전략-계좌 데이터 bulk 로드 오류: {str(e)}')
            return []
    
    def _bulk_load_financial_aggregates(self, user_id: int) -> Dict[str, Dict[int, float]]:
        """재무 집계 데이터를 한 번에 로드 - 청산 거래 기준으로 수정"""
        try:
            # 실현손익 집계 (계좌별) - 청산 거래 기준으로 수정
            realized_pnl_query = (
                self.session.query(
                    StrategyAccount.id.label('account_id'),
                    func.coalesce(func.sum(Trade.pnl), 0).label('realized_pnl'),
                    func.count(Trade.id).label('total_trades')  # 청산 거래만 카운팅
                )
                .join(Strategy, StrategyAccount.strategy_id == Strategy.id)
                .outerjoin(Trade, and_(
                    StrategyAccount.id == Trade.strategy_account_id,
                    Trade.is_entry == False  # 청산 거래만 필터링
                ))
                .filter(Strategy.user_id == user_id)
                .group_by(StrategyAccount.id)
            )
            
            # 승리 거래 수를 별도로 계산 - 청산 거래 기준
            winning_trades_query = (
                self.session.query(
                    StrategyAccount.id.label('account_id'),
                    func.count(Trade.id).label('winning_trades')
                )
                .join(Strategy, StrategyAccount.strategy_id == Strategy.id)
                .outerjoin(Trade, StrategyAccount.id == Trade.strategy_account_id)
                .filter(
                    Strategy.user_id == user_id,
                    Trade.is_entry == False,  # 청산 거래만 필터링
                    Trade.pnl > 0  # 수익 청산 거래만
                )
                .group_by(StrategyAccount.id)
            )
            
            # 포지션 집계 (계좌별)
            position_query = (
                self.session.query(
                    StrategyAccount.id.label('account_id'),
                    func.count(StrategyPosition.id).label('position_count'),
                    func.sum(func.abs(StrategyPosition.quantity * StrategyPosition.entry_price)).label('used_capital')
                )
                .join(Strategy, StrategyAccount.strategy_id == Strategy.id)
                .outerjoin(StrategyPosition, StrategyAccount.id == StrategyPosition.strategy_account_id)
                .filter(
                    Strategy.user_id == user_id,
                    StrategyPosition.quantity != 0
                )
                .group_by(StrategyAccount.id)
            )
            
            # 실현손익 결과 처리
            realized_data = {}
            for row in realized_pnl_query.all():
                realized_data[row.account_id] = {
                    'realized_pnl': float(row.realized_pnl) if row.realized_pnl else 0,
                    'total_trades': int(row.total_trades) if row.total_trades else 0,
                    'winning_trades': 0  # 기본값
                }
            
            # 승리 거래 수 업데이트
            for row in winning_trades_query.all():
                if row.account_id in realized_data:
                    realized_data[row.account_id]['winning_trades'] = int(row.winning_trades) if row.winning_trades else 0
            
            position_data = {}
            for row in position_query.all():
                position_data[row.account_id] = {
                    'position_count': int(row.position_count) if row.position_count else 0,
                    'used_capital': float(row.used_capital) if row.used_capital else 0
                }
            
            return {
                'realized_pnl': realized_data,
                'positions': position_data
            }
            
        except Exception as e:
            logger.error(f'재무 집계 데이터 로드 오류: {str(e)}')
            return {'realized_pnl': {}, 'positions': {}}
    
    def _bulk_load_trades_data(self, user_id: int) -> List[Dict[str, Any]]:
        """사용자의 모든 거래 데이터를 bulk로 로드 (진입/청산 거래 모두 포함, 카운팅은 청산 기준)"""
        try:
            query = (
                self.session.query(
                    Trade.strategy_account_id,
                    Trade.pnl,
                    Trade.timestamp,
                    Trade.symbol,
                    Trade.side,
                    Trade.order_type,
                    Trade.price,
                    Trade.quantity,
                    Trade.fee,
                    Trade.is_entry
                )
                .join(StrategyAccount, Trade.strategy_account_id == StrategyAccount.id)
                .join(Strategy, StrategyAccount.strategy_id == Strategy.id)
                .filter(
                    Strategy.user_id == user_id,
                    Trade.pnl.isnot(None)
                )
                .order_by(Trade.timestamp)
            )
            
            results = query.all()
            
            trades_data = []
            for row in results:
                trades_data.append({
                    'strategy_account_id': row.strategy_account_id,
                    'pnl': float(row.pnl) if row.pnl else 0,
                    'timestamp': row.timestamp,
                    'symbol': row.symbol,
                    'side': row.side,
                    'order_type': row.order_type,
                    'price': row.price,
                    'quantity': row.quantity,
                    'fee': row.fee,
                    'is_entry': row.is_entry
                })
            
            return trades_data
            
        except Exception as e:
            logger.error(f'거래 데이터 bulk 로드 오류: {str(e)}')
            return []
    
    def _bulk_load_30day_trades_data(self, user_id: int) -> List[Dict[str, Any]]:
        """최근 30일 거래 데이터를 bulk로 로드 - is_entry 필드 포함"""
        try:
            thirty_days_ago = datetime.now() - timedelta(days=30)
            
            query = (
                self.session.query(
                    Trade.strategy_account_id,
                    Trade.pnl,
                    Trade.timestamp,
                    Trade.is_entry,  # 청산 거래 필터링을 위해 추가
                    StrategyAccount.strategy_id
                )
                .join(StrategyAccount, Trade.strategy_account_id == StrategyAccount.id)
                .join(Strategy, StrategyAccount.strategy_id == Strategy.id)
                .filter(
                    Strategy.user_id == user_id,
                    Trade.timestamp >= thirty_days_ago,
                    Trade.pnl.isnot(None)
                )
                .order_by(Trade.timestamp)
            )
            
            results = query.all()
            
            trades_30d_data = []
            for row in results:
                trades_30d_data.append({
                    'strategy_account_id': row.strategy_account_id,
                    'strategy_id': row.strategy_id,
                    'pnl': float(row.pnl) if row.pnl else 0,
                    'timestamp': row.timestamp,
                    'is_entry': row.is_entry  # 청산 거래 필터링을 위해 추가
                })
            
            return trades_30d_data
            
        except Exception as e:
            logger.error(f'30일 거래 데이터 bulk 로드 오류: {str(e)}')
            return []
    
    def _calculate_dashboard_stats_in_memory(
        self, 
        strategy_account_data: List[Dict[str, Any]], 
        financial_aggregates: Dict[str, Dict[int, float]], 
        trades_data: List[Dict[str, Any]], 
        trades_30d_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """메모리에서 모든 대시보드 통계 계산"""
        try:
            # 전략별, 계좌별 데이터 그룹핑
            strategies_by_id = defaultdict(lambda: {
                'data': None,
                'accounts': []
            })
            
            total_capital = 0
            total_unrealized_pnl = 0
            accounts_count = 0
            
            # 기본 데이터 그룹핑
            for item in strategy_account_data:
                strategy_id = item['strategy_id']
                if strategies_by_id[strategy_id]['data'] is None:
                    strategies_by_id[strategy_id]['data'] = {
                        'id': item['strategy_id'],
                        'name': item['strategy_name'],
                        'group_name': item['strategy_group_name'],
                        'is_active': item['strategy_is_active']
                    }
                
                strategies_by_id[strategy_id]['accounts'].append(item)
                total_capital += item['allocated_capital']
                total_unrealized_pnl += item['unrealized_pnl']
                accounts_count += 1
            
            # 실현손익 계산
            total_realized_pnl = sum(
                data.get('realized_pnl', 0) 
                for data in financial_aggregates['realized_pnl'].values()
            )
            
            # 총 포지션 수
            total_positions = sum(
                data.get('position_count', 0) 
                for data in financial_aggregates['positions'].values()
            )
            
            # 총 거래 수 및 승률 계산
            total_trades = sum(
                data.get('total_trades', 0) 
                for data in financial_aggregates['realized_pnl'].values()
            )
            
            total_winning_trades = sum(
                data.get('winning_trades', 0) 
                for data in financial_aggregates['realized_pnl'].values()
            )
            
            overall_win_rate = (total_winning_trades / total_trades * 100) if total_trades > 0 else 0
            
            # 총 손익을 실현 손익만으로 계산 (수정된 부분)
            total_pnl = total_realized_pnl
            cumulative_return = (total_pnl / total_capital * 100) if total_capital > 0 else 0
            realized_pnl_rate = (total_realized_pnl / total_capital * 100) if total_capital > 0 else 0
            unrealized_pnl_rate = (total_unrealized_pnl / total_capital * 100) if total_capital > 0 else 0
            
            # 전략별 상세 정보 계산 (메모리에서)
            strategies_detail = []
            for strategy_id, strategy_info in strategies_by_id.items():
                strategy_detail = self._calculate_strategy_details_in_memory(
                    strategy_info, financial_aggregates, trades_data, trades_30d_data
                )
                strategies_detail.append(strategy_detail)
            
            return {
                'total_capital': float(total_capital),
                'total_pnl': float(total_pnl),  # 실현 손익만
                'realized_pnl': float(total_realized_pnl),
                'unrealized_pnl': float(total_unrealized_pnl),
                'cumulative_return': float(cumulative_return),  # 실현 손익 기준 수익률
                'realized_pnl_rate': float(realized_pnl_rate),
                'unrealized_pnl_rate': float(unrealized_pnl_rate),
                'total_positions': total_positions,
                'total_trades': total_trades,
                'total_winning_trades': total_winning_trades,
                'overall_win_rate': float(overall_win_rate),  # 전체 승률 추가
                'strategies_count': len(strategies_by_id),
                'accounts_count': accounts_count,
                'strategies_detail': strategies_detail
            }
            
        except Exception as e:
            logger.error(f'메모리 대시보드 통계 계산 오류: {str(e)}')
            return self._get_empty_dashboard_stats()
    
    def _calculate_strategy_details_in_memory(
        self, 
        strategy_info: Dict[str, Any], 
        financial_aggregates: Dict[str, Dict[int, float]], 
        trades_data: List[Dict[str, Any]], 
        trades_30d_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """메모리에서 전략별 상세 정보 계산"""
        try:
            strategy_data = strategy_info['data'].copy()
            accounts = strategy_info['accounts']
            
            # 기본값 설정
            strategy_data.update({
                'allocated_capital': 0,
                'current_pnl': 0,
                'realized_pnl': 0,
                'unrealized_pnl': 0,
                'cumulative_return': 0,
                'realized_pnl_rate': 0,
                'unrealized_pnl_rate': 0,
                'mdd': 0,
                'position_count': 0,
                'position_ratio': 0,
                'total_trades': 0,
                'win_rate': 0,
                'accounts_detail': [],
                'pnl_30d': 0,
                'roi_30d': 0,
                'mdd_30d': 0,
                'sharpe_ratio_30d': 0,
                # 새로운 고급 지표들
                'profit_factor': 0,
                'sortino_ratio': 0,
                'avg_win_trade': 0,
                'avg_loss_trade': 0,
                'max_consecutive_wins': 0,
                'max_consecutive_losses': 0,
                'total_winning_trades': 0,
                'total_losing_trades': 0
            })
            
            # 계좌별 데이터 집계
            total_allocated = 0
            total_realized_pnl = 0
            total_unrealized_pnl = 0
            total_position_count = 0
            total_used_capital = 0
            total_trades = 0
            total_winning_trades = 0
            
            for account in accounts:
                account_id = account['account_id']
                
                # 계좌별 상세 정보 계산
                account_detail = self._calculate_account_details_in_memory(
                    account, financial_aggregates, trades_30d_data
                )
                strategy_data['accounts_detail'].append(account_detail)
                
                # 전략 레벨 집계
                total_allocated += account_detail['allocated_capital']
                total_realized_pnl += account_detail['realized_pnl']
                total_unrealized_pnl += account_detail['unrealized_pnl']
                total_position_count += account_detail['position_count']
                total_used_capital += account_detail['used_capital']
                total_trades += account_detail['total_trades']
                total_winning_trades += account_detail.get('winning_trades', 0)
            
            # 전략 레벨 지표 계산
            strategy_data['allocated_capital'] = total_allocated
            strategy_data['realized_pnl'] = total_realized_pnl
            strategy_data['unrealized_pnl'] = total_unrealized_pnl
            strategy_data['current_pnl'] = total_realized_pnl  # 실현손익만 사용하도록 수정
            strategy_data['position_count'] = total_position_count
            strategy_data['total_trades'] = total_trades
            strategy_data['total_winning_trades'] = total_winning_trades
            strategy_data['total_losing_trades'] = total_trades - total_winning_trades
            
            if total_allocated > 0:
                # 총 PnL을 실현손익만으로 계산하도록 수정
                strategy_data['cumulative_return'] = (total_realized_pnl / total_allocated) * 100
                strategy_data['realized_pnl_rate'] = (total_realized_pnl / total_allocated) * 100
                strategy_data['unrealized_pnl_rate'] = (total_unrealized_pnl / total_allocated) * 100
                strategy_data['position_ratio'] = (total_used_capital / total_allocated) * 100
            
            # 승률 계산
            if total_trades > 0:
                strategy_data['win_rate'] = (total_winning_trades / total_trades) * 100
            
            # 전략별 거래 데이터 필터링
            strategy_trades = [
                t for t in trades_data 
                if any(acc['account_id'] == t['strategy_account_id'] for acc in accounts)
            ]
            
            # 고급 지표 계산
            advanced_metrics = self._calculate_advanced_metrics_in_memory(strategy_trades, total_allocated)
            strategy_data.update(advanced_metrics)
            
            # MDD 계산
            strategy_data['mdd'] = self._calculate_mdd_in_memory(strategy_trades, total_allocated)
            
            # 30일 지표 계산
            strategy_trades_30d = [
                t for t in trades_30d_data 
                if t['strategy_id'] == strategy_data['id']
            ]
            
            logger.debug(f'전략 {strategy_data["name"]} - 30일 거래 필터링: 전체={len(trades_30d_data)}, 전략별={len(strategy_trades_30d)}, 할당자본={total_allocated}')
            
            metrics_30d = self._calculate_30day_metrics_in_memory(strategy_trades_30d, total_allocated)
            strategy_data.update(metrics_30d)
            
            # 차트 데이터 계산 (30일 스파크라인 포함)
            chart_data = self._calculate_chart_data_in_memory(strategy_trades_30d)
            strategy_data['chart_data'] = chart_data
            
            # 스파크라인 데이터 (간단한 30일 누적 PnL)
            sparkline_data = self._calculate_sparkline_data_in_memory(strategy_trades_30d)
            strategy_data['sparkline_data'] = sparkline_data
            
            return strategy_data
            
        except Exception as e:
            logger.error(f'메모리 전략 상세 정보 계산 오류: {str(e)}')
            return strategy_info['data']
    
    def _calculate_advanced_metrics_in_memory(self, trades: List[Dict[str, Any]], allocated_capital: float) -> Dict[str, float]:
        """고급 지표들을 메모리에서 계산 - 청산 거래 기준으로 수정"""
        try:
            if not trades:
                return {
                    'profit_factor': 0,
                    'sortino_ratio': 0,
                    'avg_win_trade': 0,
                    'avg_loss_trade': 0,
                    'max_consecutive_wins': 0,
                    'max_consecutive_losses': 0
                }
            
            # 청산 거래만 필터링 (is_entry가 False인 거래만)
            exit_trades = [t for t in trades if t.get('is_entry', True) == False]
            
            if not exit_trades:
                return {
                    'profit_factor': 0,
                    'sortino_ratio': 0,
                    'avg_win_trade': 0,
                    'avg_loss_trade': 0,
                    'max_consecutive_wins': 0,
                    'max_consecutive_losses': 0
                }
            
            # 수익/손실 거래 분리 (청산 거래 기준)
            winning_trades = [t['pnl'] for t in exit_trades if t['pnl'] > 0]
            losing_trades = [t['pnl'] for t in exit_trades if t['pnl'] < 0]
            
            # 손익비 (Profit Factor)
            total_wins = sum(winning_trades) if winning_trades else 0
            total_losses = abs(sum(losing_trades)) if losing_trades else 0
            profit_factor = (total_wins / total_losses) if total_losses > 0 else 0
            
            # 평균 거래 금액
            avg_win_trade = (total_wins / len(winning_trades)) if winning_trades else 0
            avg_loss_trade = (total_losses / len(losing_trades)) if losing_trades else 0
            
            # 연속 수익/손실 계산 (청산 거래 기준)
            consecutive_wins = 0
            consecutive_losses = 0
            max_consecutive_wins = 0
            max_consecutive_losses = 0
            
            for trade in exit_trades:
                if trade['pnl'] > 0:
                    consecutive_wins += 1
                    consecutive_losses = 0
                    max_consecutive_wins = max(max_consecutive_wins, consecutive_wins)
                elif trade['pnl'] < 0:
                    consecutive_losses += 1
                    consecutive_wins = 0
                    max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
            
            # Sortino Ratio (청산 거래 기준)
            daily_returns = []
            if allocated_capital > 0:
                for trade in exit_trades:
                    daily_return = (trade['pnl'] / allocated_capital) * 100
                    daily_returns.append(daily_return)
            
            sortino_ratio = 0
            if len(daily_returns) > 1:
                returns_array = np.array(daily_returns)
                downside_returns = returns_array[returns_array < 0]
                if len(downside_returns) > 0:
                    mean_return = np.mean(returns_array)
                    downside_deviation = np.std(downside_returns)
                    if downside_deviation > 0:
                        sortino_ratio = (mean_return / downside_deviation) * np.sqrt(252)
            
            return {
                'profit_factor': float(profit_factor),
                'sortino_ratio': float(sortino_ratio),
                'avg_win_trade': float(avg_win_trade),
                'avg_loss_trade': float(avg_loss_trade),
                'max_consecutive_wins': max_consecutive_wins,
                'max_consecutive_losses': max_consecutive_losses
            }
            
        except Exception as e:
            logger.error(f'고급 지표 계산 오류: {str(e)}')
            return {
                'profit_factor': 0,
                'sortino_ratio': 0,
                'avg_win_trade': 0,
                'avg_loss_trade': 0,
                'max_consecutive_wins': 0,
                'max_consecutive_losses': 0
            }
    
    def _calculate_sparkline_data_in_memory(self, trades_30d: List[Dict[str, Any]]) -> List[float]:
        """스파크라인용 30일 누적 PnL 데이터 계산 - 청산 거래 기준으로 수정"""
        try:
            # 청산 거래만 필터링 (is_entry가 False인 거래만)
            exit_trades_30d = [t for t in trades_30d if t.get('is_entry', True) == False]
            
            # 일별 PnL 집계 (청산 거래 기준)
            daily_pnls = defaultdict(float)
            for trade in exit_trades_30d:
                date_key = trade['timestamp'].date()
                daily_pnls[date_key] += trade['pnl']
            
            # 30일간 누적 PnL 계산
            sparkline_values = []
            cumulative_pnl = 0
            
            for i in range(29, -1, -1):  # 30일간
                date = (datetime.now() - timedelta(days=i)).date()
                daily_pnl = daily_pnls.get(date, 0)
                cumulative_pnl += daily_pnl
                sparkline_values.append(round(cumulative_pnl, 2))
            
            return sparkline_values
            
        except Exception as e:
            logger.error(f'스파크라인 데이터 계산 오류: {str(e)}')
            return [0] * 30
    
    def _calculate_account_details_in_memory(
        self, 
        account_data: Dict[str, Any], 
        financial_aggregates: Dict[str, Dict[int, float]], 
        trades_30d_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """메모리에서 계좌별 상세 정보 계산"""
        try:
            account_id = account_data['account_id']
            
            # 기본 데이터
            account_detail = {
                'account_id': account_id,
                'name': account_data['account_name'],
                'exchange': account_data['account_exchange'],
                'allocated_capital': account_data['allocated_capital'],
                'unrealized_pnl': account_data['unrealized_pnl'],
                'is_active': account_data['account_is_active'],
                'realized_pnl': 0,
                'current_pnl': 0,
                'cumulative_return': 0,
                'realized_pnl_rate': 0,
                'unrealized_pnl_rate': 0,
                'position_count': 0,
                'position_ratio': 0,
                'used_capital': 0,
                'total_trades': 0,
                'win_rate': 0,
                'winning_trades': 0,
                'profit_loss_ratio': 0,
                'pnl_30d': 0,
                'roi_30d': 0,
                'mdd_30d': 0,
                'sharpe_ratio_30d': 0
            }
            
            # 실현손익 데이터
            if account_id in financial_aggregates['realized_pnl']:
                pnl_data = financial_aggregates['realized_pnl'][account_id]
                account_detail['realized_pnl'] = pnl_data['realized_pnl']
                account_detail['total_trades'] = pnl_data['total_trades']
                account_detail['winning_trades'] = pnl_data['winning_trades']
            
            # 포지션 데이터
            if account_id in financial_aggregates['positions']:
                pos_data = financial_aggregates['positions'][account_id]
                account_detail['position_count'] = pos_data['position_count']
                account_detail['used_capital'] = pos_data['used_capital']
            
            # 총 손익
            account_detail['current_pnl'] = account_detail['realized_pnl'] + account_detail['unrealized_pnl']
            
            # 수익률 계산
            allocated = account_detail['allocated_capital']
            if allocated > 0:
                account_detail['cumulative_return'] = (account_detail['current_pnl'] / allocated) * 100
                account_detail['realized_pnl_rate'] = (account_detail['realized_pnl'] / allocated) * 100
                account_detail['unrealized_pnl_rate'] = (account_detail['unrealized_pnl'] / allocated) * 100
                account_detail['position_ratio'] = (account_detail['used_capital'] / allocated) * 100
            
            # 승률 계산
            if account_detail['total_trades'] > 0:
                account_detail['win_rate'] = (account_detail['winning_trades'] / account_detail['total_trades']) * 100
            
            # 30일 지표 계산
            account_trades_30d = [
                t for t in trades_30d_data 
                if t['strategy_account_id'] == account_id
            ]
            metrics_30d = self._calculate_30day_metrics_in_memory(account_trades_30d, allocated)
            account_detail.update(metrics_30d)
            
            return account_detail
            
        except Exception as e:
            logger.error(f'메모리 계좌 상세 정보 계산 오류: {str(e)}')
            return {'account_id': account_data['account_id'], 'name': account_data['account_name']}
    
    def _calculate_mdd_in_memory(self, trades: List[Dict[str, Any]], total_allocated: float) -> float:
        """메모리에서 MDD 계산 - 청산 거래 기준으로 수정"""
        try:
            if not trades or total_allocated <= 0:
                return 0
            
            # 청산 거래만 필터링 (is_entry가 False인 거래만)
            exit_trades = [t for t in trades if t.get('is_entry', True) == False]
            
            if not exit_trades:
                return 0
            
            # 일별 PnL 집계 (청산 거래 기준)
            daily_pnls = defaultdict(float)
            for trade in exit_trades:
                date_key = trade['timestamp'].date()
                daily_pnls[date_key] += trade['pnl']
            
            # 누적 PnL로 MDD 계산
            cumulative_pnl = 0
            peak = 0
            max_drawdown = 0
            
            for date in sorted(daily_pnls.keys()):
                cumulative_pnl += daily_pnls[date]
                if cumulative_pnl > peak:
                    peak = cumulative_pnl
                drawdown = peak - cumulative_pnl
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
            
            return (max_drawdown / total_allocated) * 100 if total_allocated > 0 else 0
            
        except Exception as e:
            logger.error(f'메모리 MDD 계산 오류: {str(e)}')
            return 0
    
    def _calculate_30day_metrics_in_memory(self, trades_30d: List[Dict[str, Any]], allocated_capital: float) -> Dict[str, float]:
        """메모리에서 30일 지표 계산 - 청산 거래 기준으로 수정"""
        try:
            if not trades_30d or allocated_capital <= 0:
                logger.debug(f'30일 지표 계산 - 거래 데이터 없음 또는 자본 없음: trades_30d={len(trades_30d) if trades_30d else 0}, allocated_capital={allocated_capital}')
                return {
                    'pnl_30d': 0,
                    'roi_30d': 0,
                    'mdd_30d': 0,
                    'sharpe_ratio_30d': 0
                }
            
            # 청산 거래만 필터링 (is_entry가 False인 거래만)
            exit_trades_30d = [t for t in trades_30d if t.get('is_entry', True) == False]
            
            logger.debug(f'30일 지표 계산 - 전체 거래: {len(trades_30d)}, 청산 거래: {len(exit_trades_30d)}')
            
            if not exit_trades_30d:
                logger.debug('30일 지표 계산 - 청산 거래 없음')
                return {
                    'pnl_30d': 0,
                    'roi_30d': 0,
                    'mdd_30d': 0,
                    'sharpe_ratio_30d': 0
                }
            
            # 30일 총 PnL (청산 거래 기준)
            total_pnl_30d = sum(trade['pnl'] for trade in exit_trades_30d)
            roi_30d = (total_pnl_30d / allocated_capital * 100)
            
            logger.debug(f'30일 지표 계산 - PnL: {total_pnl_30d}, ROI: {roi_30d}%')
            
            # 일별 PnL로 MDD와 Sharpe 계산 (청산 거래 기준)
            daily_pnls = defaultdict(float)
            for trade in exit_trades_30d:
                date_key = trade['timestamp'].date()
                daily_pnls[date_key] += trade['pnl']
            
            # MDD 계산
            cumulative_pnl = 0
            peak = 0
            max_drawdown = 0
            daily_returns = []
            
            for date in sorted(daily_pnls.keys()):
                daily_pnl = daily_pnls[date]
                cumulative_pnl += daily_pnl
                
                # 일간 수익률
                daily_return = (daily_pnl / allocated_capital) * 100
                daily_returns.append(daily_return)
                
                # MDD
                if cumulative_pnl > peak:
                    peak = cumulative_pnl
                drawdown = peak - cumulative_pnl
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
            
            mdd_30d = (max_drawdown / allocated_capital * 100)
            
            # Sharpe Ratio
            sharpe_ratio_30d = 0
            if len(daily_returns) > 1:
                returns_array = np.array(daily_returns)
                if np.std(returns_array) > 0:
                    mean_return = np.mean(returns_array)
                    std_return = np.std(returns_array)
                    sharpe_ratio_30d = (mean_return / std_return) * np.sqrt(252)
            
            result = {
                'pnl_30d': float(total_pnl_30d),
                'roi_30d': float(roi_30d),
                'mdd_30d': float(mdd_30d),
                'sharpe_ratio_30d': float(sharpe_ratio_30d)
            }
            
            logger.debug(f'30일 지표 계산 완료 - 결과: {result}')
            return result
            
        except Exception as e:
            logger.error(f'메모리 30일 지표 계산 오류: {str(e)}')
            return {
                'pnl_30d': 0,
                'roi_30d': 0,
                'mdd_30d': 0,
                'sharpe_ratio_30d': 0
            }
    
    def _calculate_chart_data_in_memory(self, trades_30d: List[Dict[str, Any]]) -> Dict[str, Any]:
        """메모리에서 차트 데이터 계산 - 청산 거래 기준으로 수정"""
        try:
            from datetime import datetime, timedelta
            
            # 청산 거래만 필터링 (is_entry가 False인 거래만)
            exit_trades_30d = [t for t in trades_30d if t.get('is_entry', True) == False]
            
            # 일별 PnL 집계 (청산 거래 기준)
            daily_pnls = defaultdict(float)
            for trade in exit_trades_30d:
                date_key = trade['timestamp'].date().isoformat()
                daily_pnls[date_key] += trade['pnl']
            
            # 최근 30일 날짜 생성 및 누적 PnL 계산
            dates = []
            pnl_values = []
            cumulative_pnl = 0
            
            for i in range(30, -1, -1):
                date = (datetime.now() - timedelta(days=i)).date()
                date_str = date.isoformat()
                dates.append(date_str)
                
                daily_pnl = daily_pnls.get(date_str, 0)
                cumulative_pnl += daily_pnl
                pnl_values.append(round(cumulative_pnl, 2))
            
            # 요약 정보
            if pnl_values:
                start_value = pnl_values[0] if len(pnl_values) > 0 else 0
                end_value = pnl_values[-1] if len(pnl_values) > 0 else 0
                total_change = end_value - start_value
                max_value = max(pnl_values) if pnl_values else 0
                min_value = min(pnl_values) if pnl_values else 0
                
                summary = {
                    'total_change': total_change,
                    'start_value': start_value,
                    'end_value': end_value,
                    'max_value': max_value,
                    'min_value': min_value,
                    'is_positive': total_change >= 0,
                    'has_data': len([v for v in pnl_values if v != 0]) > 0
                }
            else:
                summary = {
                    'total_change': 0,
                    'start_value': 0,
                    'end_value': 0,
                    'max_value': 0,
                    'min_value': 0,
                    'is_positive': True,
                    'has_data': False
                }
            
            return {
                'dates': dates,
                'pnl_values': pnl_values,
                'summary': summary
            }
            
        except Exception as e:
            logger.error(f'메모리 차트 데이터 계산 오류: {str(e)}')
            return {'dates': [], 'pnl_values': [], 'summary': {'has_data': False}}
    
    def _get_empty_dashboard_stats(self) -> Dict[str, Any]:
        """빈 대시보드 통계 반환"""
        return {
            'total_capital': 0,
            'total_pnl': 0,
            'realized_pnl': 0,
            'unrealized_pnl': 0,
            'cumulative_return': 0,
            'realized_pnl_rate': 0,
            'unrealized_pnl_rate': 0,
            'total_positions': 0,
            'total_trades': 0,
            'total_winning_trades': 0,
            'overall_win_rate': 0,
            'strategies_count': 0,
            'accounts_count': 0,
            'strategies_detail': []
        }

    def get_user_recent_trades(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """사용자의 최근 거래 내역 조회 - 최적화된 버전"""
        try:
            # 최적화된 단일 쿼리로 모든 필요한 데이터 JOIN
            query = (
                self.session.query(
                    Trade.id,
                    Trade.symbol,
                    Trade.side,
                    Trade.order_type,
                    Trade.price,
                    Trade.quantity,
                    Trade.pnl,
                    Trade.fee,
                    Trade.timestamp,
                    Trade.is_entry,
                    Strategy.name.label('strategy_name'),
                    Account.name.label('account_name'),
                    Account.exchange.label('account_exchange')
                )
                .join(StrategyAccount, Trade.strategy_account_id == StrategyAccount.id)
                .join(Strategy, StrategyAccount.strategy_id == Strategy.id)
                .join(Account, StrategyAccount.account_id == Account.id)
                .filter(Strategy.user_id == user_id)
                .order_by(Trade.timestamp.desc())
                .limit(limit)
            )
            
            results = query.all()
            
            trades_data = []
            for row in results:
                trades_data.append({
                    'id': row.id,
                    'strategy_name': row.strategy_name,
                    'name': row.account_name,
                    'exchange': row.account_exchange,
                    'symbol': row.symbol,
                    'side': row.side,
                    'order_type': row.order_type,
                    'price': row.price,
                    'quantity': row.quantity,
                    'pnl': row.pnl,
                    'fee': row.fee,
                    'timestamp': row.timestamp.isoformat(),
                    'is_entry': row.is_entry
                })
            
            return trades_data
            
        except Exception as e:
            logger.error(f'최근 거래 내역 조회 오류: {str(e)}')
            raise DashboardError(f'최근 거래 내역 조회 실패: {str(e)}')

# 전역 인스턴스 생성
dashboard_service = DashboardService() 