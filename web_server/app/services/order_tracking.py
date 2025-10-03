"""
주문 추적 서비스 (완전 구현)
WebSocket 연결 관리 및 실시간 주문 추적
"""
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from decimal import Decimal
import logging
import json
import uuid
from app import db
from app.models import (
    OrderTrackingSession, TradeExecution, TrackingLog,
    OpenOrder, Trade, StrategyAccount, Account
)
from app.constants import OrderStatus

logger = logging.getLogger(__name__)


class OrderTrackingService:
    """핵심 주문 추적 서비스"""
    
    def __init__(self):
        self.active_sessions: Dict[str, OrderTrackingSession] = {}
        self._load_active_sessions()
    
    def _load_active_sessions(self):
        """활성 세션 로드"""
        try:
            sessions = OrderTrackingSession.query.filter(
                OrderTrackingSession.status.in_(['connecting', 'connected'])
            ).all()
            
            for session in sessions:
                self.active_sessions[session.session_id] = session
            
            logger.info(f"Loaded {len(self.active_sessions)} active tracking sessions")
        except Exception as e:
            logger.error(f"Error loading active sessions: {e}")
    
    def create_session(self, user_id: int, connection_type: str = 'websocket',
                      exchange: str = None, account_id: int = None) -> OrderTrackingSession:
        """새 추적 세션 생성"""
        try:
            session_id = str(uuid.uuid4())
            
            session = OrderTrackingSession(
                user_id=user_id,
                session_id=session_id,
                connection_type=connection_type,
                exchange=exchange,
                account_id=account_id,
                status='connecting',
                started_at=datetime.utcnow()
            )
            
            db.session.add(session)
            db.session.commit()
            
            self.active_sessions[session_id] = session
            
            TrackingLog.log(
                log_type='session_created',
                message=f'Tracking session created: {session_id}',
                source='OrderTrackingService',
                user_id=user_id,
                account_id=account_id
            )
            
            return session
            
        except Exception as e:
            logger.error(f"Error creating tracking session: {e}")
            db.session.rollback()
            raise
    
    def update_session_status(self, session_id: str, status: str, 
                            error_message: str = None) -> bool:
        """세션 상태 업데이트"""
        try:
            session = OrderTrackingSession.query.filter_by(
                session_id=session_id
            ).first()
            
            if not session:
                return False
            
            session.status = status
            
            if status == 'connected':
                session.last_ping = datetime.utcnow()
            elif status in ['disconnected', 'error']:
                session.ended_at = datetime.utcnow()
                if error_message:
                    session.error_message = error_message
                # 활성 세션에서 제거
                self.active_sessions.pop(session_id, None)
            
            db.session.commit()
            
            TrackingLog.log(
                log_type='session_status_update',
                message=f'Session {session_id} status changed to {status}',
                source='OrderTrackingService',
                user_id=session.user_id,
                severity='info' if status == 'connected' else 'warning'
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating session status: {e}")
            db.session.rollback()
            return False
    
    def ping_session(self, session_id: str) -> bool:
        """세션 핑 업데이트"""
        try:
            session = self.active_sessions.get(session_id)
            if not session:
                return False
            
            session.last_ping = datetime.utcnow()
            db.session.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error pinging session: {e}")
            db.session.rollback()
            return False
    
    def cleanup_stale_sessions(self, timeout_minutes: int = 5):
        """오래된 세션 정리"""
        try:
            cutoff_time = datetime.utcnow() - timedelta(minutes=timeout_minutes)
            
            stale_sessions = OrderTrackingSession.query.filter(
                OrderTrackingSession.status.in_(['connecting', 'connected']),
                OrderTrackingSession.last_ping < cutoff_time
            ).all()
            
            for session in stale_sessions:
                session.status = 'disconnected'
                session.ended_at = datetime.utcnow()
                session.error_message = 'Session timed out'
                
                self.active_sessions.pop(session.session_id, None)
            
            if stale_sessions:
                db.session.commit()
                logger.info(f"Cleaned up {len(stale_sessions)} stale sessions")
            
        except Exception as e:
            logger.error(f"Error cleaning up stale sessions: {e}")
            db.session.rollback()
    
    def track_order_update(self, order_data: Dict[str, Any], 
                          session_id: str = None) -> bool:
        """주문 업데이트 추적"""
        try:
            # OpenOrder 테이블 업데이트
            order = OpenOrder.query.filter_by(
                exchange_order_id=order_data.get('exchange_order_id')
            ).first()
            
            if order:
                # 기존 주문 업데이트
                order.status = order_data.get('status', order.status)
                order.filled_quantity = order_data.get('filled_quantity', order.filled_quantity)
                order.updated_at = datetime.utcnow()
            else:
                # 새 주문 생성 (필요한 경우)
                logger.warning(f"Order not found: {order_data.get('exchange_order_id')}")
            
            # 추적 로그 생성
            TrackingLog.log(
                log_type='order_update',
                message=f"Order updated: {order_data.get('exchange_order_id')}",
                source='OrderTrackingService',
                order_id=order_data.get('exchange_order_id'),
                symbol=order_data.get('symbol'),
                details=order_data
            )
            
            db.session.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error tracking order update: {e}")
            db.session.rollback()
            return False
    
    def track_trade_execution(self, trade_data: Dict[str, Any],
                            strategy_account_id: int) -> Optional[TradeExecution]:
        """거래 체결 추적 - TradeRecordService와 통합"""
        try:
            from app.services.trade_record import trade_record_service
            
            # TradeRecordService를 통해 체결 기록
            execution_data = {
                'strategy_account_id': strategy_account_id,
                'exchange_trade_id': trade_data.get('exchange_trade_id'),
                'exchange_order_id': trade_data.get('exchange_order_id'),
                'symbol': trade_data.get('symbol'),
                'side': trade_data.get('side'),
                'price': trade_data.get('price'),
                'quantity': trade_data.get('quantity'),
                'commission': trade_data.get('commission'),
                'commission_asset': trade_data.get('commission_asset'),
                'time': trade_data.get('time', datetime.utcnow()),
                'is_maker': trade_data.get('is_maker'),
                'realized_pnl': trade_data.get('realized_pnl'),
                'market_type': trade_data.get('market_type', 'SPOT'),
                'meta_data': trade_data.get('meta_data', {})
            }
            
            execution = trade_record_service.record_execution(execution_data)
            
            if execution:
                # 추적 로그 생성
                TrackingLog.log(
                    log_type='trade_execution',
                    message=f"Trade executed: {trade_data.get('symbol')} "
                           f"{trade_data.get('quantity')}@{trade_data.get('price')}",
                    source='OrderTrackingService',
                    trade_id=trade_data.get('exchange_trade_id'),
                    order_id=trade_data.get('exchange_order_id'),
                    symbol=trade_data.get('symbol'),
                    details=trade_data
                )
            
            return execution
            
        except Exception as e:
            logger.error(f"Error tracking trade execution: {e}")
            return None
    
    def sync_open_orders(self, account_id: int) -> Dict[str, Any]:
        """계좌의 미체결 주문 완전 동기화 - 개선된 버전"""
        try:
            from app.services.exchange import exchange_service
            from app.services.trade_record import trade_record_service
            from sqlalchemy.exc import IntegrityError
            
            # 1. 계좌 조회
            account = Account.query.get(account_id)
            if not account:
                return {'success': False, 'error': 'Account not found'}
            
            # 2. 모든 활성 전략 계좌 조회 (Phase 1 수정)
            strategy_accounts = StrategyAccount.query.filter_by(
                account_id=account_id,
                is_active=True
            ).all()
            
            if not strategy_accounts:
                logger.warning(f"No active strategy accounts for account {account_id}")
                return {'success': False, 'error': 'No active strategy accounts found'}
            
            # 각 전략 계좌별로 마켓 타입 매핑
            strategy_market_map = {}
            for sa in strategy_accounts:
                if sa.strategy:
                    market_type = sa.strategy.market_type.lower()
                    if market_type not in strategy_market_map:
                        strategy_market_map[market_type] = []
                    strategy_market_map[market_type].append(sa)
            
            # 기본 마켓 타입 설정 (전략이 없는 계좌용)
            if not strategy_market_map:
                strategy_market_map['spot'] = strategy_accounts
            
            logger.info(f"Syncing orders for account {account.name} (ID: {account_id}) with {len(strategy_accounts)} strategy accounts")
            
            # 결과 집계 변수
            total_synced = 0
            total_created = 0
            total_updated = 0
            total_closed = 0
            total_filled = 0
            all_errors = []
            market_results = {}
            
            # 3. 각 마켓 타입별로 주문 동기화
            for market_type, market_strategy_accounts in strategy_market_map.items():
                try:
                    logger.info(f"Processing {market_type} market with {len(market_strategy_accounts)} strategy accounts")
                    
                    # 거래소에서 미체결 주문 조회
                    result = exchange_service.get_open_orders(account, market_type=market_type)
                    
                    if not result.get('success'):
                        error_msg = result.get('error', 'Unknown error')
                        logger.error(f"Failed to fetch {market_type} orders: {error_msg}")
                        all_errors.append(f"{market_type}: {error_msg}")
                        continue
                    
                    exchange_orders = result.get('orders', [])
                    logger.info(f"Fetched {len(exchange_orders)} orders from {market_type} market")
                    
                    # Phase 3: 체결 내역 조회 추가
                    recent_trades = []
                    if hasattr(exchange_service, 'get_recent_trades'):
                        trades_result = exchange_service.get_recent_trades(
                            account, 
                            market_type=market_type,
                            limit=100
                        )
                        if trades_result.get('success'):
                            recent_trades = trades_result.get('trades', [])
                            logger.info(f"Fetched {len(recent_trades)} recent trades for fill detection")
                    
                    # 이 마켓의 모든 전략 계좌에서 DB 주문 조회
                    strategy_account_ids = [sa.id for sa in market_strategy_accounts]
                    db_orders = OpenOrder.query.filter(
                        OpenOrder.strategy_account_id.in_(strategy_account_ids),
                        OpenOrder.status.in_(OrderStatus.get_open_statuses())
                    ).all()
                    
                    db_order_map = {order.exchange_order_id: order for order in db_orders}
                    logger.info(f"Found {len(db_orders)} open orders in DB for {market_type}")
                    
                    # 거래소 주문을 전략 계좌와 매칭
                    processed_order_ids = set()
                    
                    for raw_order in exchange_orders:
                        exchange_order = self._order_to_dict(raw_order)
                        
                        try:
                            order_id = str(exchange_order.get('orderId', exchange_order.get('id', '')))
                            if not order_id:
                                logger.warning(f"Order without ID skipped: {exchange_order}")
                                continue
                            
                            # 중복 처리 방지
                            if order_id in processed_order_ids:
                                continue
                            processed_order_ids.add(order_id)
                            
                            symbol = exchange_order.get('symbol', '')
                            side = exchange_order.get('side', '').upper()
                            status = OrderStatus.from_exchange(
                                exchange_order.get('status', ''),
                                account.exchange
                            )
                            order_type = exchange_order.get('type', exchange_order.get('orderType', 'LIMIT'))
                            price = float(exchange_order.get('price', 0))
                            stop_price = float(exchange_order.get('stopPrice', 0))
                            quantity = float(exchange_order.get('origQty', exchange_order.get('quantity', 0)))
                            filled_quantity = float(exchange_order.get('executedQty', exchange_order.get('filledQty', 0)))
                            timestamp = exchange_order.get('timestamp')
                            
                            # 기존 DB 주문 확인
                            db_order = db_order_map.get(order_id)
                            
                            if db_order:
                                # 기존 주문 업데이트
                                old_status = db_order.status
                                db_order.status = status
                                db_order.filled_quantity = filled_quantity
                                db_order.updated_at = datetime.utcnow()
                                total_updated += 1
                                
                                # 새로 체결된 주문 체크
                                if status == OrderStatus.FILLED and old_status != OrderStatus.FILLED:
                                    total_filled += 1
                                    logger.info(f"🎯 체결 감지: {order_id} ({symbol}) - {filled_quantity} @ {price}")
                                    # 체결 기록 생성 및 포지션 업데이트
                                    self._record_trade_execution(
                                        db_order.strategy_account_id,
                                        order_id, symbol, side, price,
                                        filled_quantity, market_type
                                    )
                                
                                logger.debug(f"Updated order {order_id}: {old_status} -> {status}")
                            else:
                                # 새 주문 생성 - 적절한 전략 계좌 찾기
                                strategy_account = self._find_best_strategy_account(
                                    market_strategy_accounts,
                                    symbol,
                                    timestamp
                                )
                                
                                if not strategy_account:
                                    logger.warning(f"No suitable strategy account for order {order_id} ({symbol})")
                                    continue
                                
                                # Phase 2: UPSERT 패턴으로 중복 방지
                                existing = OpenOrder.query.filter_by(
                                    exchange_order_id=order_id
                                ).first()
                                
                                if existing:
                                    # 이미 존재하는 주문 업데이트
                                    existing.status = status
                                    existing.filled_quantity = filled_quantity
                                    existing.updated_at = datetime.utcnow()
                                    total_updated += 1
                                    logger.debug(f"Updated existing order {order_id} (was in different status)")
                                else:
                                    # 새 주문 생성
                                    new_order = OpenOrder(
                                        strategy_account_id=strategy_account.id,
                                        exchange_order_id=order_id,
                                        symbol=symbol,
                                        side=side,
                                        order_type=order_type,
                                        price=price,
                                        stop_price=stop_price if stop_price > 0 else None,
                                        quantity=quantity,
                                        filled_quantity=filled_quantity,
                                        status=status,
                                        market_type=market_type.upper(),
                                        created_at=datetime.utcnow(),
                                        updated_at=datetime.utcnow()
                                    )
                                    db.session.add(new_order)
                                    total_created += 1
                                    logger.debug(f"Created order {order_id}: {symbol} {side} {quantity}@{price}")
                            
                            total_synced += 1
                            
                        except IntegrityError as e:
                            # Phase 2: Unique constraint 충돌 처리
                            db.session.rollback()
                            logger.warning(f"Integrity error for order {order_id}: {e}")
                            
                            # 기존 주문 조회 후 업데이트
                            existing = OpenOrder.query.filter_by(
                                exchange_order_id=order_id
                            ).first()
                            if existing:
                                existing.status = status
                                existing.filled_quantity = filled_quantity
                                existing.updated_at = datetime.utcnow()
                                db.session.add(existing)
                                total_updated += 1
                            
                        except Exception as e:
                            error_msg = f"Error processing order {order_id}: {e}"
                            logger.error(error_msg)
                            all_errors.append(error_msg)
                    
                    # Phase 4: 거래소에 없는 DB 주문 처리 (개선된 상태 추정)
                    exchange_order_ids = processed_order_ids
                    
                    for db_order in db_orders:
                        if db_order.exchange_order_id not in exchange_order_ids:
                            # 체결 내역에서 확인
                            was_filled = self._check_if_order_filled(
                                db_order.exchange_order_id,
                                recent_trades
                            )
                            
                            if was_filled:
                                # 체결됨으로 확인
                                db_order.status = OrderStatus.FILLED
                                total_filled += 1
                                logger.info(f"🎯 거래 내역에서 체결 확인: {db_order.exchange_order_id} ({db_order.symbol})")
                                # 체결 기록 생성 및 포지션 업데이트
                                self._record_trade_from_history(
                                    db_order,
                                    recent_trades
                                )
                            elif db_order.filled_quantity > 0:
                                # 부분 체결 후 취소로 추정
                                db_order.status = OrderStatus.CANCELLED
                                logger.info(f"Order {db_order.exchange_order_id} partially filled then cancelled")
                            else:
                                # 취소됨
                                db_order.status = OrderStatus.CANCELLED
                            
                            db_order.updated_at = datetime.utcnow()
                            total_closed += 1
                            logger.debug(f"Closed order {db_order.exchange_order_id}: {db_order.status}")
                    
                    # 이 마켓의 결과 저장
                    market_results[market_type] = {
                        'synced': total_synced,
                        'created': total_created,
                        'updated': total_updated,
                        'closed': total_closed,
                        'filled': total_filled
                    }
                    
                except Exception as e:
                    error_msg = f"Error processing {market_type} market: {str(e)}"
                    logger.error(error_msg, exc_info=True)
                    all_errors.append(error_msg)
                    db.session.rollback()
            
            # DB 커밋
            try:
                db.session.commit()
                logger.info(f"Order sync committed: {total_synced} synced, {total_created} created, "
                           f"{total_updated} updated, {total_closed} closed, {total_filled} filled")
            except Exception as e:
                db.session.rollback()
                logger.error(f"Failed to commit sync changes: {e}")
                return {'success': False, 'error': f'Database commit failed: {str(e)}'}
            
            # 추적 로그 생성
            TrackingLog.log(
                log_type='sync_complete',
                message=f'Order sync completed for account {account.name}',
                source='OrderTrackingService',
                account_id=account_id,
                details={
                    'strategy_accounts': len(strategy_accounts),
                    'markets_processed': list(strategy_market_map.keys()),
                    'total_synced': total_synced,
                    'created': total_created,
                    'updated': total_updated,
                    'closed': total_closed,
                    'filled': total_filled,
                    'errors': len(all_errors),
                    'market_results': market_results
                }
            )
            
            # 완료된 주문 정리 (FILLED/CANCELLED 상태)
            try:
                # 해당 계정의 완료된 주문들 조회
                closed_orders = OpenOrder.query.filter(
                    OpenOrder.strategy_account_id.in_([sa.id for sa in strategy_accounts]),
                    OpenOrder.status.in_(OrderStatus.get_closed_statuses())
                ).all()
                
                deleted_count = 0
                for order in closed_orders:
                    try:
                        logger.info(f"🗑️ OpenOrder 정리: {order.exchange_order_id} (상태: {order.status})")
                        db.session.delete(order)
                        deleted_count += 1
                    except Exception as e:
                        logger.warning(f"Failed to delete closed order {order.exchange_order_id}: {e}")
                
                if deleted_count > 0:
                    db.session.commit()
                    logger.info(f"✅ {deleted_count}개의 완료된 주문이 정리되었습니다")
                    
            except Exception as e:
                logger.error(f"Error cleaning up closed orders: {e}")
                # 정리 실패는 전체 동작에 영향을 주지 않음
            
            return {
                'success': True,
                'synced_count': total_synced,
                'created_count': total_created,
                'updated_count': total_updated,
                'closed_count': total_closed,
                'filled_count': total_filled,
                'strategy_accounts': len(strategy_accounts),
                'market_results': market_results,
                'errors': all_errors if all_errors else None
            }
            
        except Exception as e:
            logger.error(f"Critical error in sync_open_orders: {e}", exc_info=True)
            db.session.rollback()
            return {'success': False, 'error': str(e)}
    
    def _find_best_strategy_account(self, strategy_accounts: List[StrategyAccount],
                                   symbol: str, timestamp: Optional[datetime]) -> Optional[StrategyAccount]:
        """주문에 가장 적합한 전략 계좌 찾기"""
        # 전략이 활성화되고 심볼을 거래하는 계좌 찾기
        for sa in strategy_accounts:
            if sa.is_active:
                # 전략이 이 심볼을 거래하는지 확인 (추가 로직 필요)
                # 일단 첫 번째 활성 계좌 반환
                return sa
        
        # 활성 계좌가 없으면 첫 번째 반환
        return strategy_accounts[0] if strategy_accounts else None
    
    def _check_if_order_filled(self, order_id: str, recent_trades: List[Dict]) -> bool:
        """최근 거래 내역에서 주문 체결 여부 확인"""
        for trade in recent_trades:
            trade_order_id = str(trade.get('order', trade.get('orderId', '')))
            if trade_order_id == order_id:
                return True
        return False
    
    def _record_trade_execution(self, strategy_account_id: int, order_id: str,
                               symbol: str, side: str, price: float,
                               quantity: float, market_type: str):
        """체결 기록 생성 및 SSE 전파 (통합 루틴 사용)"""
        from app.services.trading import trading_service

        try:
            strategy_account = StrategyAccount.query.get(strategy_account_id)
            if not strategy_account:
                logger.warning(f"StrategyAccount {strategy_account_id} not found for order {order_id}")
                return

            order_result_seed = {
                'order_id': order_id,
                'symbol': symbol,
                'side': side,
                'average_price': Decimal(str(price)) if price else None,
                'filled_quantity': Decimal(str(quantity)) if quantity else None,
            }

            fill_result = trading_service.process_order_fill(
                strategy_account=strategy_account,
                order_id=order_id,
                symbol=symbol,
                side=side,
                order_result=order_result_seed,
                market_type=market_type
            )

            if not fill_result.get('success'):
                logger.critical(
                    "체결 처리 실패(크리티컬) - order_id=%s reason=%s",
                    order_id,
                    fill_result.get('error')
                )
                return

            logger.info(
                "✅ 체결 처리 완료: order_id=%s filled=%s avg_price=%s",
                order_id,
                fill_result.get('filled_quantity'),
                fill_result.get('average_price')
            )

        except Exception as e:
            logger.error(f"Failed to process trade execution via unified routine: {e}", exc_info=True)
    
    def _record_trade_from_history(self, db_order: OpenOrder, recent_trades: List[Dict]):
        """거래 내역에서 체결 정보 추출하여 통합 루틴으로 처리"""
        from app.services.trading import trading_service
        from decimal import Decimal

        try:
            if db.session.is_active:
                db.session.rollback()

            order_trades = [
                trade for trade in recent_trades
                if str(trade.get('order', trade.get('orderId', '')))
                == db_order.exchange_order_id
            ]

            if not order_trades:
                self._record_trade_execution(
                    db_order.strategy_account_id,
                    db_order.exchange_order_id,
                    db_order.symbol,
                    db_order.side,
                    db_order.price,
                    db_order.filled_quantity or db_order.quantity,
                    db_order.market_type
                )
                return

            total_quantity = Decimal('0')
            total_value = Decimal('0')

            for trade in order_trades:
                trade_price = Decimal(str(trade.get('price', db_order.price or 0)))
                trade_qty = Decimal(str(trade.get('amount', trade.get('quantity', 0))))
                total_quantity += trade_qty
                total_value += trade_price * trade_qty

            average_price = Decimal('0')
            if total_quantity > 0:
                average_price = total_value / total_quantity

            strategy_account = StrategyAccount.query.get(db_order.strategy_account_id)
            if not strategy_account:
                logger.warning(f"StrategyAccount {db_order.strategy_account_id} not found for order {db_order.exchange_order_id}")
                return

            order_result_seed = {
                'order_id': db_order.exchange_order_id,
                'symbol': db_order.symbol,
                'side': db_order.side,
                'filled_quantity': total_quantity if total_quantity > 0 else Decimal(str(db_order.filled_quantity or db_order.quantity)),
                'average_price': average_price if average_price > 0 else Decimal(str(db_order.price or 0)),
            }

            fill_result = trading_service.process_order_fill(
                strategy_account=strategy_account,
                order_id=db_order.exchange_order_id,
                symbol=db_order.symbol,
                side=db_order.side,
                order_result=order_result_seed,
                market_type=db_order.market_type
            )

            if not fill_result.get('success'):
                logger.critical(
                    "거래 내역 기반 체결 처리 실패(크리티컬) - order_id=%s reason=%s",
                    db_order.exchange_order_id,
                    fill_result.get('error')
                )

        except Exception as e:
            db.session.rollback()
            logger.critical(
                "거래 내역 기반 체결 처리 중 예외 발생(크리티컬) - order_id=%s error=%s",
                db_order.exchange_order_id,
                e,
                exc_info=True
            )

    def _order_to_dict(self, order):
        """Convert Order object or dict to dict format"""
        # If it's already a dict, return it
        if isinstance(order, dict):
            return order
        
        # If it's an Order object, convert to dict
        if hasattr(order, '__dict__'):
            return {
                'orderId': getattr(order, 'id', ''),
                'symbol': getattr(order, 'symbol', ''),
                'side': getattr(order, 'side', ''),
                'status': getattr(order, 'status', ''),
                'type': getattr(order, 'type', ''),
                'price': str(getattr(order, 'price', 0)),
                'stopPrice': str(getattr(order, 'stop_price', 0)),
                'origQty': str(getattr(order, 'amount', 0)),
                'executedQty': str(getattr(order, 'filled', 0)),
                'timestamp': getattr(order, 'timestamp', None)
            }
        
        return order

    def detect_filled_orders(self, account_id: int) -> Dict[str, Any]:
        """체결된 주문 감지 및 처리"""
        try:
            from app.services.trade_record import trade_record_service
            
            # 부분 체결 상태 주문 조회
            partial_orders = OpenOrder.query.join(
                StrategyAccount
            ).filter(
                StrategyAccount.account_id == account_id,
                OpenOrder.status == OrderStatus.PARTIALLY_FILLED
            ).all()
            
            filled_orders = []
            
            for order in partial_orders:
                # 체결 내역 확인 및 기록
                if order.filled_quantity > 0:
                    trade_data = {
                        'strategy_account_id': order.strategy_account_id,
                        'exchange_trade_id': f"{order.exchange_order_id}_partial",
                        'exchange_order_id': order.exchange_order_id,
                        'symbol': order.symbol,
                        'side': order.side,
                        'price': order.price,
                        'quantity': order.filled_quantity,
                        'market_type': order.market_type
                    }
                    
                    execution = trade_record_service.record_execution(trade_data)
                    if execution:
                        filled_orders.append({
                            'order_id': order.exchange_order_id,
                            'symbol': order.symbol,
                            'filled_quantity': order.filled_quantity
                        })
            
            return {
                'success': True,
                'filled_orders': filled_orders,
                'total_detected': len(filled_orders)
            }
            
        except Exception as e:
            logger.error(f"Error detecting filled orders: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_session_stats(self) -> Dict[str, Any]:
        """세션 통계 조회"""
        try:
            total_sessions = OrderTrackingSession.query.count()
            active_sessions = len(self.active_sessions)
            
            # 최근 24시간 세션 통계
            day_ago = datetime.utcnow() - timedelta(days=1)
            recent_sessions = OrderTrackingSession.query.filter(
                OrderTrackingSession.started_at > day_ago
            ).all()
            
            successful_sessions = sum(1 for s in recent_sessions if s.status == 'disconnected' and not s.error_message)
            error_sessions = sum(1 for s in recent_sessions if s.status == 'error' or s.error_message)
            
            return {
                'total_sessions': total_sessions,
                'active_sessions': active_sessions,
                'recent_24h': len(recent_sessions),
                'successful_rate': (successful_sessions / len(recent_sessions) * 100) if recent_sessions else 0,
                'error_rate': (error_sessions / len(recent_sessions) * 100) if recent_sessions else 0,
                'sessions_by_exchange': self._get_sessions_by_exchange(),
                'avg_session_duration': self._get_avg_session_duration()
            }
            
        except Exception as e:
            logger.error(f"Error getting session stats: {e}")
            return {}
    
    def _get_sessions_by_exchange(self) -> Dict[str, int]:
        """거래소별 세션 통계"""
        result = {}
        for session in self.active_sessions.values():
            if session.exchange:
                result[session.exchange] = result.get(session.exchange, 0) + 1
        return result
    
    def _get_avg_session_duration(self) -> float:
        """평균 세션 지속 시간 (분)"""
        try:
            completed_sessions = OrderTrackingSession.query.filter(
                OrderTrackingSession.ended_at.isnot(None),
                OrderTrackingSession.started_at.isnot(None)
            ).limit(100).all()  # 최근 100개만 계산
            
            if not completed_sessions:
                return 0.0
            
            durations = []
            for session in completed_sessions:
                duration = (session.ended_at - session.started_at).total_seconds() / 60
                durations.append(duration)
            
            return sum(durations) / len(durations) if durations else 0.0
            
        except Exception as e:
            logger.error(f"Error calculating avg session duration: {e}")
            return 0.0


# 싱글톤 인스턴스
order_tracking_service = OrderTrackingService()
