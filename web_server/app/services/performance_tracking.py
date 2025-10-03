"""
성과 추적 서비스
전략별 성과 메트릭 계산 및 저장
"""
from typing import Dict, List, Optional, Any
from datetime import datetime, date, timedelta
import logging
import numpy as np
from sqlalchemy import func
from app import db
from app.models import (
    StrategyPerformance, Trade, TradeExecution,
    Strategy, StrategyAccount, StrategyCapital
)

logger = logging.getLogger(__name__)


class PerformanceTrackingService:
    """전략 성과 추적 서비스 (기본 구조)"""
    
    def calculate_daily_performance(self, strategy_id: int, 
                                   target_date: date = None) -> Optional[StrategyPerformance]:
        """일일 성과 계산"""
        try:
            if not target_date:
                target_date = date.today()
            
            # 기존 레코드 확인
            performance = StrategyPerformance.query.filter_by(
                strategy_id=strategy_id,
                date=target_date
            ).first()
            
            if not performance:
                performance = StrategyPerformance(
                    strategy_id=strategy_id,
                    date=target_date
                )
                db.session.add(performance)
            
            # 기본 메트릭 계산
            metrics = self._calculate_metrics(strategy_id, target_date)
            
            # 성과 레코드 업데이트
            for key, value in metrics.items():
                setattr(performance, key, value)
            
            performance.updated_at = datetime.utcnow()
            db.session.commit()
            
            logger.info(f"Performance calculated for strategy {strategy_id} on {target_date}")
            return performance
            
        except Exception as e:
            logger.error(f"Error calculating daily performance: {e}")
            db.session.rollback()
            return None
    
    def _calculate_metrics(self, strategy_id: int, target_date: date) -> Dict[str, Any]:
        """메트릭 계산 (기본 구조)"""
        try:
            # 전략의 모든 계좌 조회
            strategy_accounts = StrategyAccount.query.filter_by(
                strategy_id=strategy_id,
                is_active=True
            ).all()
            
            if not strategy_accounts:
                return self._get_empty_metrics()
            
            # 당일 거래 집계
            start_time = datetime.combine(target_date, datetime.min.time())
            end_time = datetime.combine(target_date, datetime.max.time())
            
            total_trades = 0
            winning_trades = 0
            losing_trades = 0
            daily_pnl = 0.0
            total_commission = 0.0
            
            for sa in strategy_accounts:
                # TradeExecution에서 데이터 집계
                executions = TradeExecution.query.filter(
                    TradeExecution.strategy_account_id == sa.id,
                    TradeExecution.execution_time >= start_time,
                    TradeExecution.execution_time <= end_time
                ).all()
                
                for exec in executions:
                    total_trades += 1
                    if exec.realized_pnl:
                        daily_pnl += exec.realized_pnl
                        if exec.realized_pnl > 0:
                            winning_trades += 1
                        else:
                            losing_trades += 1
                    
                    if exec.commission:
                        total_commission += exec.commission
            
            # 승률 계산
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            
            # 누적 메트릭 계산 (이전 날짜 데이터 참조)
            previous_perf = StrategyPerformance.query.filter(
                StrategyPerformance.strategy_id == strategy_id,
                StrategyPerformance.date < target_date
            ).order_by(StrategyPerformance.date.desc()).first()
            
            cumulative_pnl = daily_pnl
            if previous_perf:
                cumulative_pnl += previous_perf.cumulative_pnl
            
            return {
                'daily_pnl': daily_pnl,
                'cumulative_pnl': cumulative_pnl,
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'losing_trades': losing_trades,
                'win_rate': win_rate,
                'total_commission': total_commission,
                'commission_ratio': (total_commission / abs(daily_pnl) * 100) if daily_pnl != 0 else 0
            }
            
        except Exception as e:
            logger.error(f"Error calculating metrics: {e}")
            return self._get_empty_metrics()
    
    def _get_empty_metrics(self) -> Dict[str, Any]:
        """빈 메트릭 반환"""
        return {
            'daily_return': 0.0,
            'cumulative_return': 0.0,
            'daily_pnl': 0.0,
            'cumulative_pnl': 0.0,
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': 0.0,
            'max_drawdown': 0.0,
            'total_commission': 0.0,
            'commission_ratio': 0.0
        }
    
    def get_performance_summary(self, strategy_id: int,
                               days: int = 30) -> Dict[str, Any]:
        """성과 요약 조회"""
        try:
            end_date = date.today()
            start_date = end_date - timedelta(days=days)
            
            performances = StrategyPerformance.query.filter(
                StrategyPerformance.strategy_id == strategy_id,
                StrategyPerformance.date >= start_date,
                StrategyPerformance.date <= end_date
            ).order_by(StrategyPerformance.date).all()
            
            if not performances:
                return {
                    'period_days': days,
                    'total_return': 0.0,
                    'total_pnl': 0.0,
                    'avg_daily_pnl': 0.0,
                    'best_day': 0.0,
                    'worst_day': 0.0,
                    'total_trades': 0,
                    'avg_win_rate': 0.0
                }
            
            # 집계 계산
            total_pnl = sum(p.daily_pnl for p in performances)
            total_trades = sum(p.total_trades for p in performances)
            daily_pnls = [p.daily_pnl for p in performances]
            win_rates = [p.win_rate for p in performances if p.total_trades > 0]
            
            return {
                'period_days': len(performances),
                'total_return': performances[-1].cumulative_return if performances else 0.0,
                'total_pnl': total_pnl,
                'avg_daily_pnl': total_pnl / len(performances) if performances else 0.0,
                'best_day': max(daily_pnls) if daily_pnls else 0.0,
                'worst_day': min(daily_pnls) if daily_pnls else 0.0,
                'total_trades': total_trades,
                'avg_win_rate': sum(win_rates) / len(win_rates) if win_rates else 0.0,
                'max_drawdown': self._calculate_max_drawdown(performances)
            }
            
        except Exception as e:
            logger.error(f"Error getting performance summary: {e}")
            return {}
    
    def _calculate_max_drawdown(self, performances: List[StrategyPerformance]) -> float:
        """최대 낙폭 계산"""
        if not performances:
            return 0.0
        
        cumulative_pnls = [p.cumulative_pnl for p in performances]
        if not cumulative_pnls or max(cumulative_pnls) <= 0:
            return 0.0
        
        peak = cumulative_pnls[0]
        max_dd = 0.0
        
        for pnl in cumulative_pnls:
            if pnl > peak:
                peak = pnl
            else:
                drawdown = (peak - pnl) / peak * 100 if peak > 0 else 0
                max_dd = max(max_dd, drawdown)
        
        return max_dd
    
    def batch_calculate(self, days_back: int = 7) -> Dict[str, Any]:
        """배치로 여러 전략의 성과 계산"""
        try:
            # 활성 전략 조회
            strategies = Strategy.query.filter_by(is_active=True).all()
            
            results = {
                'processed': 0,
                'failed': 0,
                'strategies': []
            }
            
            end_date = date.today()
            start_date = end_date - timedelta(days=days_back)
            
            for strategy in strategies:
                current_date = start_date
                while current_date <= end_date:
                    performance = self.calculate_daily_performance(
                        strategy.id, 
                        current_date
                    )
                    
                    if performance:
                        results['processed'] += 1
                    else:
                        results['failed'] += 1
                    
                    current_date += timedelta(days=1)
                
                results['strategies'].append({
                    'id': strategy.id,
                    'name': strategy.name,
                    'group_name': strategy.group_name
                })
            
            logger.info(f"Batch calculation complete: {results}")
            return results
            
        except Exception as e:
            logger.error(f"Error in batch calculation: {e}")
            return {'error': str(e)}


# 싱글톤 인스턴스
performance_tracking_service = PerformanceTrackingService()
