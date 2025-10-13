"""
체결 내역 저장 서비스
거래 체결 내역을 기록하고 관리

@FEAT:trade-execution @COMP:service @TYPE:core
"""
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import logging
from sqlalchemy import func
from app import db
from app.models import TradeExecution, Trade, StrategyAccount

logger = logging.getLogger(__name__)


# @FEAT:trade-execution @COMP:service @TYPE:core
class TradeRecordService:
    """체결 내역 저장 서비스"""

    # @FEAT:trade-execution @COMP:service @TYPE:core
    def record_execution(self, execution_data: Dict[str, Any]) -> Optional[TradeExecution]:
        """
        거래 체결 기록

        exchange_trade_id 기반 중복 체크 후 신규 체결 기록 생성.
        Trade 레코드와 연결 가능.
        """
        try:
            # 중복 체크
            existing = TradeExecution.query.filter_by(
                exchange_trade_id=execution_data['exchange_trade_id']
            ).first()

            if existing:
                logger.info(f"Execution already recorded: {execution_data['exchange_trade_id']}")
                return existing

            # 새 체결 기록 생성
            execution = TradeExecution(
                strategy_account_id=execution_data['strategy_account_id'],
                exchange_trade_id=execution_data['exchange_trade_id'],
                exchange_order_id=execution_data['exchange_order_id'],
                symbol=execution_data['symbol'],
                side=execution_data['side'],
                execution_price=execution_data['price'],
                execution_quantity=execution_data['quantity'],
                commission=execution_data.get('commission'),
                commission_asset=execution_data.get('commission_asset'),
                execution_time=execution_data.get('time', datetime.utcnow()),
                is_maker=execution_data.get('is_maker'),
                realized_pnl=execution_data.get('realized_pnl'),
                market_type=execution_data.get('market_type', 'SPOT'),
                meta_data=execution_data.get('meta_data', {})
            )

            db.session.add(execution)

            # 관련 Trade 레코드 연결 (있는 경우)
            if 'trade_id' in execution_data:
                execution.trade_id = execution_data['trade_id']

            db.session.commit()
            logger.info(f"Execution recorded: {execution.exchange_trade_id}")

            return execution

        except Exception as e:
            logger.error(f"Error recording execution: {e}")
            db.session.rollback()
            return None

    # @FEAT:trade-execution @COMP:service @TYPE:core
    def get_executions_by_order(self, exchange_order_id: str) -> List[TradeExecution]:
        """주문별 체결 내역 조회 (부분 체결 포함)"""
        try:
            return TradeExecution.query.filter_by(
                exchange_order_id=exchange_order_id
            ).order_by(TradeExecution.execution_time.desc()).all()
        except Exception as e:
            logger.error(f"Error fetching executions by order: {e}")
            return []

    # @FEAT:trade-execution @COMP:service @TYPE:core
    def get_executions_by_symbol(self, symbol: str,
                                 strategy_account_id: int = None,
                                 start_date: datetime = None,
                                 end_date: datetime = None) -> List[TradeExecution]:
        """심볼별 체결 내역 조회 (필터링 옵션 지원)"""
        try:
            query = TradeExecution.query.filter_by(symbol=symbol)

            if strategy_account_id:
                query = query.filter_by(strategy_account_id=strategy_account_id)

            if start_date:
                query = query.filter(TradeExecution.execution_time >= start_date)

            if end_date:
                query = query.filter(TradeExecution.execution_time <= end_date)

            return query.order_by(TradeExecution.execution_time.desc()).all()

        except Exception as e:
            logger.error(f"Error fetching executions by symbol: {e}")
            return []

    # @FEAT:trade-execution @COMP:service @TYPE:core
    def get_execution_stats(self, strategy_account_id: int = None,
                           start_date: datetime = None) -> Dict[str, Any]:
        """
        체결 통계 조회

        총 체결 건수, 거래량, 수수료, 평균 체결가 등 집계.
        """
        try:
            query = db.session.query(TradeExecution)

            if strategy_account_id:
                query = query.filter(TradeExecution.strategy_account_id == strategy_account_id)

            if start_date:
                query = query.filter(TradeExecution.execution_time >= start_date)

            # 기본 통계
            total_executions = query.count()

            if total_executions == 0:
                return {
                    'total_executions': 0,
                    'total_volume': 0,
                    'total_commission': 0,
                    'avg_execution_price': 0,
                    'symbols_traded': 0
                }

            # 집계 통계
            stats = db.session.query(
                func.count(TradeExecution.id).label('count'),
                func.sum(TradeExecution.execution_quantity * TradeExecution.execution_price).label('volume'),
                func.sum(TradeExecution.commission).label('commission'),
                func.avg(TradeExecution.execution_price).label('avg_price'),
                func.count(func.distinct(TradeExecution.symbol)).label('symbols')
            ).filter(
                TradeExecution.id.in_(query.with_entities(TradeExecution.id))
            ).first()

            return {
                'total_executions': stats.count or 0,
                'total_volume': float(stats.volume or 0),
                'total_commission': float(stats.commission or 0),
                'avg_execution_price': float(stats.avg_price or 0),
                'symbols_traded': stats.symbols or 0,
                'executions_by_side': self._get_executions_by_side(query),
                'executions_by_market': self._get_executions_by_market(query)
            }

        except Exception as e:
            logger.error(f"Error getting execution stats: {e}")
            return {}

    # @FEAT:trade-execution @COMP:service @TYPE:helper
    def _get_executions_by_side(self, base_query) -> Dict[str, int]:
        """매수/매도별 체결 통계"""
        try:
            results = db.session.query(
                TradeExecution.side,
                func.count(TradeExecution.id)
            ).filter(
                TradeExecution.id.in_(base_query.with_entities(TradeExecution.id))
            ).group_by(TradeExecution.side).all()

            return {side: count for side, count in results}

        except Exception as e:
            logger.error(f"Error getting executions by side: {e}")
            return {}

    # @FEAT:trade-execution @COMP:service @TYPE:helper
    def _get_executions_by_market(self, base_query) -> Dict[str, int]:
        """시장별 체결 통계 (SPOT/FUTURES)"""
        try:
            results = db.session.query(
                TradeExecution.market_type,
                func.count(TradeExecution.id)
            ).filter(
                TradeExecution.id.in_(base_query.with_entities(TradeExecution.id))
            ).group_by(TradeExecution.market_type).all()

            return {market: count for market, count in results}

        except Exception as e:
            logger.error(f"Error getting executions by market: {e}")
            return {}

    # @FEAT:trade-execution @COMP:service @TYPE:core
    def sync_with_trades(self, strategy_account_id: int) -> Dict[str, Any]:
        """
        기존 Trade 테이블과 동기화

        레거시 Trade 데이터를 TradeExecution으로 마이그레이션.
        중복 체크 후 신규 레코드만 생성.
        """
        try:
            # Trade 테이블의 레코드 조회
            trades = Trade.query.filter_by(
                strategy_account_id=strategy_account_id
            ).all()

            synced = 0
            skipped = 0

            for trade in trades:
                # 이미 연결된 체결이 있는지 확인
                existing = TradeExecution.query.filter_by(
                    exchange_order_id=trade.exchange_order_id,
                    strategy_account_id=strategy_account_id
                ).first()

                if existing:
                    skipped += 1
                    continue

                # 새 체결 레코드 생성
                execution = TradeExecution(
                    trade_id=trade.id,
                    strategy_account_id=strategy_account_id,
                    exchange_trade_id=f"{trade.exchange_order_id}_legacy",  # 레거시 식별자
                    exchange_order_id=trade.exchange_order_id,
                    symbol=trade.symbol,
                    side=trade.side,
                    execution_price=trade.price,
                    execution_quantity=trade.quantity,
                    commission=trade.fee,
                    execution_time=trade.timestamp,
                    realized_pnl=trade.pnl,
                    market_type=trade.market_type,
                    meta_data={'source': 'legacy_sync'}
                )

                db.session.add(execution)
                synced += 1

            db.session.commit()

            return {
                'success': True,
                'synced': synced,
                'skipped': skipped,
                'total': len(trades)
            }

        except Exception as e:
            logger.error(f"Error syncing with trades: {e}")
            db.session.rollback()
            return {
                'success': False,
                'error': str(e)
            }


# 싱글톤 인스턴스
trade_record_service = TradeRecordService()
