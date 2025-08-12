"""
주문 관리 서비스 모듈 - 리팩토링 버전
새로운 모듈들을 사용하여 복잡성을 줄이고 책임을 분리
"""

import logging
from typing import Dict, Any, List
from decimal import Decimal
from datetime import datetime

from app import db
from app.models import OpenOrder, StrategyAccount, Account
from app.services.utils import to_decimal, decimal_to_float
from app.services.exchange_service import exchange_service
from app.services.open_order_service import open_order_manager
from app.services.order_status_service import order_status_processor
from app.constants import MarketType, Exchange, OrderType

# 백그라운드 작업용 로거 사용
logger = logging.getLogger('trading_system.background')

class OrderError(Exception):
    """주문 관련 오류"""
    pass

class OrderService:
    """주문 서비스 클래스 - 리팩토링된 버전"""
    
    def __init__(self):
        self.session = db.session
    
    def _emit_order_cancelled_event(self, open_order: OpenOrder, account: Account, strategy):
        """주문 취소 SSE 이벤트 발송"""
        try:
            from app.services.event_service import event_service, OrderEvent
            from datetime import datetime
            
            # 계좌 정보를 중첩 구조로 구성
            account_info = {
                'id': account.id,
                'name': account.name,
                'exchange': account.exchange
            }
            
            # 주문 취소 이벤트 생성
            order_event = OrderEvent(
                event_type='order_cancelled',
                order_id=open_order.exchange_order_id,
                symbol=open_order.symbol,
                strategy_id=strategy.id,
                user_id=strategy.user_id,
                side=open_order.side,
                quantity=float(open_order.quantity),
                price=float(open_order.price),
                status='CANCELLED',
                timestamp=datetime.utcnow().isoformat(),
                account=account_info
            )
            
            event_service.emit_order_event(order_event)
            logger.info(f"📤 주문 취소 SSE 이벤트 발송: 사용자 {strategy.user_id}, 주문ID {open_order.exchange_order_id}")
            
        except Exception as e:
            logger.warning(f"주문 취소 SSE 이벤트 발송 실패: {str(e)}")
    
    # ⚠️ SSE 이벤트 발송은 trading_service에서 중앙화됨 - 이 메서드는 더 이상 사용하지 않음
    
    def update_open_orders_status(self):
        """미체결 주문 상태 업데이트 (백그라운드 작업) - 새로운 모듈 사용"""
        try:
            logger.debug("미체결 주문 상태 업데이트 시작")
            
            # 새로운 주문 상태 처리기를 사용하여 업데이트
            result = order_status_processor.process_all_open_orders()
            
            if result.get('success'):
                summary = (
                    f"처리: {result.get('processed_orders', 0)}개, "
                    f"체결: {result.get('filled_orders', 0)}개, "
                    f"취소: {result.get('cancelled_orders', 0)}개, "
                    f"삭제: {result.get('deleted_orders', 0)}개"
                )
                
                if result.get('cleanup_deleted_count', 0) > 0:
                    summary += f" (사전 정리: {result.get('cleanup_deleted_count')}개)"
                
                logger.debug(f"미체결 주문 상태 업데이트 완료 - {summary}")
                
                # 전략별 통계 로깅 (DEBUG 레벨)
                strategy_stats = result.get('strategy_stats', {})
                if strategy_stats:
                    logger.debug(f"전략별 주문 현황: {strategy_stats}")
            else:
                logger.error("미체결 주문 상태 업데이트 실패")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 미체결 주문 상태 업데이트 처리 실패: {str(e)}")
            raise
    
    def create_open_order(self, strategy_account_id: int, exchange_order_id: str,
                         symbol: str, side: str, quantity: Decimal, price: Decimal,
                         market_type: str = None, order_type: str = OrderType.LIMIT) -> OpenOrder:
        """새로운 OpenOrder 레코드 생성 (중앙화된 관리)"""
        try:
            if market_type is None:
                market_type = MarketType.SPOT
            order = open_order_manager.create_open_order(
                strategy_account_id=strategy_account_id,
                exchange_order_id=exchange_order_id,
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price,
                market_type=market_type,
                order_type=order_type,  # 🔧 주문 타입 전달
                session=self.session
            )
            
            # ✅ SSE 이벤트는 trading_service에서 중앙화 처리됨
            logger.info(f"📋 OpenOrder 레코드 생성 완료: {exchange_order_id} (SSE 이벤트는 trading_service에서 처리)")
            
            return order
        except Exception as e:
            logger.error(f"OpenOrder 생성 실패: {str(e)}")
            raise OrderError(f"주문 레코드 생성 실패: {str(e)}")
    
    def cancel_order(self, order_id: str, symbol: str, account_id: int, market_type: str = None) -> Dict[str, Any]:
        """주문 취소 기능 - 중앙화된 OpenOrder 관리 사용"""
        try:
            # OpenOrder 조회
            open_order = OpenOrder.query.filter_by(
                exchange_order_id=order_id
            ).join(StrategyAccount).join(Account).filter(
                Account.id == account_id
            ).first()
            
            if not open_order:
                raise OrderError(f"취소할 주문을 찾을 수 없습니다: {order_id}")
            
            if open_order.status != 'OPEN':
                raise OrderError(f"취소할 수 없는 주문 상태입니다: {open_order.status}")
            
            # 계좌 정보 조회
            strategy_account = open_order.strategy_account
            account = strategy_account.account
            
            logger.info(f"주문 취소 요청 시작 - ID: {order_id}, 심볼: {symbol}, 계좌: {account.name}")
            
            # 거래소에 취소 요청
            cancel_result = exchange_service.cancel_order(
                account=account,
                order_id=order_id,
                symbol=symbol,
                market_type=market_type
            )
            
            # 취소 성공 여부 확인
            if cancel_result.get('status') in ['canceled', 'cancelled'] or cancel_result.get('id') == order_id:
                # 중앙화된 관리자를 통해 취소 처리 (세션 전달)
                if open_order_manager.process_cancelled_order(open_order, session=self.session):
                    self.session.commit()
                    
                    # 주문 취소 SSE 이벤트 발송
                    self._emit_order_cancelled_event(open_order, strategy_account.account, strategy_account.strategy)
                    logger.info(f"📋 주문 취소 처리 완료: {order_id} (SSE 이벤트 발송)")
                    
                    logger.info(f"✅ 주문 취소 성공 및 레코드 삭제 완료 - ID: {order_id}")
                    
                    return {
                        'success': True,
                        'order_id': order_id,
                        'symbol': symbol,
                        'status': 'CANCELLED',
                        'message': '주문이 성공적으로 취소되었습니다.',
                        'deleted_from_db': True
                    }
                else:
                    raise OrderError("주문 취소 처리 중 데이터베이스 오류 발생")
            else:
                raise OrderError(f"주문 취소 실패: {cancel_result}")
        
        except Exception as e:
            self.session.rollback()
            error_msg = str(e)
            logger.error(f"❌ 주문 취소 실패 - ID: {order_id}, 오류: {error_msg}")
            
            return {
                'success': False,
                'order_id': order_id,
                'symbol': symbol,
                'error': error_msg,
                'message': f'주문 취소 실패: {error_msg}'
            }
    
    def cancel_all_orders(self, account_id: int, symbol: str = None, market_type: str = None, 
                         exchange: str = None) -> Dict[str, Any]:
        """모든 미체결 주문 취소 - 중앙화된 OpenOrder 관리 사용 (선택적 필터링 지원)"""
        try:
            # 해당 계좌의 미체결 주문 조회
            query = (
                self.session.query(OpenOrder)
                .join(StrategyAccount)
                .join(Account)
                .filter(Account.id == account_id, OpenOrder.status == 'OPEN')
            )
            
            # 심볼 필터링
            if symbol:
                query = query.filter(OpenOrder.symbol == symbol)
                logger.debug(f"심볼 필터 적용: {symbol}")
            
            # 마켓 타입 필터링 (OpenOrder의 market_type 필드 사용)
            if market_type:
                query = query.filter(OpenOrder.market_type == market_type)
                logger.debug(f"마켓 타입 필터 적용: {market_type}")
            
            open_orders = query.all()
            
            # 로그 메시지 개선
            filter_info = []
            if symbol:
                filter_info.append(f"심볼: {symbol}")
            if market_type:
                filter_info.append(f"마켓: {market_type}")
            if exchange:
                filter_info.append(f"거래소: {exchange}")
            
            filter_str = f" ({', '.join(filter_info)})" if filter_info else ""
            
            if not open_orders:
                logger.info(f"취소할 미체결 주문이 없습니다 - 계좌: {account_id}{filter_str}")
                return {
                    'success': True,
                    'cancelled_orders': [],
                    'failed_orders': [],
                    'message': f'취소할 미체결 주문이 없습니다{filter_str}'
                }
            
            logger.info(f"모든 미체결 주문 취소 시작 - 계좌: {account_id}{filter_str}, 대상: {len(open_orders)}개")
            
            cancelled_orders = []
            failed_orders = []
            
            for order in open_orders:
                try:
                    cancel_result = self.cancel_order(
                        order_id=order.exchange_order_id,
                        symbol=order.symbol,
                        account_id=account_id,
                        market_type=market_type
                    )
                    
                    if cancel_result['success']:
                        cancelled_orders.append({
                            'order_id': order.exchange_order_id,
                            'symbol': order.symbol,
                            'side': order.side,
                            'quantity': order.quantity,
                            'price': order.price
                        })
                    else:
                        failed_orders.append({
                            'order_id': order.exchange_order_id,
                            'symbol': order.symbol,
                            'error': cancel_result['error']
                        })
                
                except Exception as e:
                    failed_orders.append({
                        'order_id': order.exchange_order_id,
                        'symbol': order.symbol,
                        'error': str(e)
                    })
            
            logger.info(f"모든 미체결 주문 취소 완료 - 성공: {len(cancelled_orders)}개, 실패: {len(failed_orders)}개")
            
            return {
                'success': len(failed_orders) == 0,
                'cancelled_orders': cancelled_orders,
                'failed_orders': failed_orders,
                'message': f'총 {len(open_orders)}개 중 {len(cancelled_orders)}개 취소 성공, {len(failed_orders)}개 실패'
            }
        
        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ 모든 미체결 주문 취소 실패 - 계좌: {account_id}, 오류: {error_msg}")
            
            return {
                'success': False,
                'cancelled_orders': [],
                'failed_orders': [],
                'error': error_msg,
                'message': f'모든 주문 취소 실패: {error_msg}'
            }
    
    def get_open_orders_summary(self) -> Dict[str, Any]:
        """미체결 주문 현황 요약"""
        try:
            # 전체 미체결 주문 수
            total_open_orders = self.session.query(OpenOrder).filter_by(status='OPEN').count()
            
            # 계좌별 미체결 주문 수 (상위 10개)
            from sqlalchemy import func
            account_stats = (
                self.session.query(
                    Account.name,
                    func.count(OpenOrder.id).label('order_count')
                )
                .join(StrategyAccount, StrategyAccount.account_id == Account.id)
                .join(OpenOrder, OpenOrder.strategy_account_id == StrategyAccount.id)
                .filter(OpenOrder.status == 'OPEN')
                .group_by(Account.id, Account.name)
                .order_by(func.count(OpenOrder.id).desc())
                .limit(10)
                .all()
            )
            
            # 심볼별 미체결 주문 수 (상위 10개)
            symbol_stats = (
                self.session.query(
                    OpenOrder.symbol,
                    func.count(OpenOrder.id).label('order_count')
                )
                .filter(OpenOrder.status == 'OPEN')
                .group_by(OpenOrder.symbol)
                .order_by(func.count(OpenOrder.id).desc())
                .limit(10)
                .all()
            )
            
            return {
                'total_open_orders': total_open_orders,
                'top_accounts': [{'account': name, 'orders': count} for name, count in account_stats],
                'top_symbols': [{'symbol': symbol, 'orders': count} for symbol, count in symbol_stats],
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"미체결 주문 요약 조회 실패: {str(e)}")
            return {
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }

    def cancel_order_by_user(self, order_id: str, user_id: int) -> Dict[str, Any]:
        """사용자별 개별 주문 취소 (Service 계층)"""
        try:
            from app.models import Strategy
            
            # 주문 권한 확인
            open_order = (
                OpenOrder.query
                .join(StrategyAccount)
                .join(Strategy)
                .filter(
                    OpenOrder.exchange_order_id == order_id,
                    Strategy.user_id == user_id,
                    OpenOrder.status == 'OPEN'
                )
                .first()
            )
            
            if not open_order:
                return {
                    'success': False,
                    'error': '취소할 수 있는 주문을 찾을 수 없습니다.'
                }
            
            # 필요한 정보 수집
            strategy_account = open_order.strategy_account
            account = strategy_account.account
            strategy = strategy_account.strategy
            
            logger.info(f'사용자별 주문 취소 요청: 주문 ID {order_id}, 사용자: {user_id}')
            
            # 기존 cancel_order 함수 사용
            result = self.cancel_order(
                order_id=order_id,
                symbol=open_order.symbol,
                account_id=account.id,
                market_type=strategy.market_type
            )
            
            if result.get('success'):
                result['symbol'] = open_order.symbol
                logger.info(f'사용자별 주문 취소 완료: 주문 ID {order_id}, 사용자: {user_id}')
            
            return result
            
        except Exception as e:
            logger.error(f'사용자별 주문 취소 실패: 주문 ID {order_id}, 사용자: {user_id}, 오류: {str(e)}')
            return {
                'success': False,
                'error': str(e)
            }
    
    def cancel_all_orders_by_user(self, user_id: int, account_id: int = None, 
                                 symbol: str = None, strategy_id: int = None) -> Dict[str, Any]:
        """사용자별 일괄 주문 취소 (Service 계층)"""
        try:
            from app.models import Strategy, Account
            
            # 기본 쿼리 구성 (사용자 권한 확인 포함)
            query = (
                OpenOrder.query
                .join(StrategyAccount)
                .join(Strategy)
                .join(Account)
                .filter(
                    Strategy.user_id == user_id,
                    OpenOrder.status == 'OPEN',
                    Account.is_active == True
                )
            )
            
            # 조건별 필터링
            filter_conditions = []
            if account_id:
                query = query.filter(Account.id == account_id)
                filter_conditions.append(f"계좌 ID: {account_id}")
            
            if symbol:
                query = query.filter(OpenOrder.symbol == symbol)
                filter_conditions.append(f"심볼: {symbol}")
            
            if strategy_id:
                query = query.filter(Strategy.id == strategy_id)
                filter_conditions.append(f"전략 ID: {strategy_id}")
            
            # 취소 대상 주문들 조회
            target_orders = query.all()
            
            if not target_orders:
                return {
                    'success': True,
                    'message': '취소할 주문이 없습니다.',
                    'cancelled_orders': [],
                    'failed_orders': [],
                    'total_processed': 0,
                    'filter_conditions': filter_conditions
                }
            
            filter_desc = ", ".join(filter_conditions) if filter_conditions else "전체"
            logger.info(f'사용자별 일괄 주문 취소 요청: 사용자 {user_id}, 조건: {filter_desc}, 대상: {len(target_orders)}개')
            
            # 계좌별로 그룹화하여 일괄 취소
            orders_by_account = {}
            for order in target_orders:
                account_id_key = order.strategy_account.account.id
                if account_id_key not in orders_by_account:
                    orders_by_account[account_id_key] = {
                        'account': order.strategy_account.account,
                        'market_type': order.strategy_account.strategy.market_type,
                        'orders': []
                    }
                orders_by_account[account_id_key]['orders'].append(order)
            
            all_cancelled_orders = []
            all_failed_orders = []
            
            # 각 계좌별로 일괄 취소 실행
            for account_id_key, account_info in orders_by_account.items():
                account = account_info['account']
                market_type = account_info['market_type']
                orders = account_info['orders']
                
                try:
                    # 특정 심볼이 지정된 경우 해당 심볼만 취소
                    target_symbol = symbol if symbol else None
                    
                    result = self.cancel_all_orders(
                        account_id=account.id,
                        symbol=target_symbol,
                        market_type=market_type
                    )
                    
                    all_cancelled_orders.extend(result.get('cancelled_orders', []))
                    all_failed_orders.extend(result.get('failed_orders', []))
                    
                except Exception as e:
                    # 개별 계좌 처리 실패시 해당 주문들을 실패 목록에 추가
                    for order in orders:
                        all_failed_orders.append({
                            'order_id': order.exchange_order_id,
                            'symbol': order.symbol,
                            'error': f'계좌 {account.name} 처리 실패: {str(e)}'
                        })
            
            success_count = len(all_cancelled_orders)
            failed_count = len(all_failed_orders)
            total_count = len(target_orders)
            
            logger.info(f'사용자별 일괄 주문 취소 완료: 사용자 {user_id}, 성공 {success_count}개, 실패 {failed_count}개')
            
            return {
                'success': failed_count == 0,
                'message': f'총 {total_count}개 주문 중 {success_count}개 취소 성공, {failed_count}개 실패',
                'cancelled_orders': all_cancelled_orders,
                'failed_orders': all_failed_orders,
                'total_processed': total_count,
                'filter_conditions': filter_conditions
            }
            
        except Exception as e:
            logger.error(f'사용자별 일괄 주문 취소 실패: 사용자 {user_id}, 오류: {str(e)}')
            return {
                'success': False,
                'error': str(e),
                'cancelled_orders': [],
                'failed_orders': [],
                'total_processed': 0,
                'filter_conditions': []
            }

# 전역 인스턴스
order_service = OrderService() 