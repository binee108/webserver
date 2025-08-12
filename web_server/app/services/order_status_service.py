"""
주문 상태 업데이트 처리 서비스 모듈
복잡한 주문 상태 업데이트 로직을 작은 단위로 분리하여 가독성과 유지보수성 향상
"""

import logging
from typing import Dict, Any, List, Tuple
from decimal import Decimal
from datetime import datetime
from collections import defaultdict
from sqlalchemy.orm import joinedload, Session

from app import db
from app.models import OpenOrder, StrategyAccount, Account, Strategy
from app.services.open_order_service import open_order_manager
from app.services.exchange_service import exchange_service
from app.constants import MarketType
from app.services.utils import to_decimal

logger = logging.getLogger(__name__)


class OrderStatusProcessor:
    """주문 상태 업데이트를 처리하는 클래스"""
    
    def __init__(self, session: Session = None):
        self.session = session or db.session
    
    def process_all_open_orders(self) -> Dict[str, Any]:
        """모든 미체결 주문 상태 업데이트 메인 함수"""
        try:
            # 1. 세션 새로고침 및 완료된 주문 정리
            self._prepare_session()
            cleanup_count = open_order_manager.cleanup_completed_orders(session=self.session)
            
            # 2. 활성 미체결 주문 조회
            open_orders = self._fetch_active_open_orders()
            if not open_orders:
                return self._create_summary_result(cleanup_count, 0, 0, 0, 0)
            
            # 3. 계좌별 그룹화 및 통계
            orders_by_account, strategy_stats = self._group_orders_by_account(open_orders)
            if not orders_by_account:
                return self._create_summary_result(cleanup_count, len(open_orders), 0, 0, 0)
            
            # 4. 계좌별 주문 처리
            processing_stats = self._process_orders_by_account(orders_by_account)
            
            # 5. 트랜잭션 커밋 및 결과 반환
            self.session.commit()
            
            return self._create_summary_result(
                cleanup_count=cleanup_count,
                total_orders=len(open_orders),
                processed_orders=processing_stats['processed'],
                filled_orders=processing_stats['filled'],
                cancelled_orders=processing_stats['cancelled'],
                deleted_orders=processing_stats['deleted'],
                strategy_stats=strategy_stats
            )
            
        except Exception as e:
            self.session.rollback()
            logger.error(f"주문 상태 업데이트 처리 실패: {str(e)}")
            raise
    
    def _prepare_session(self):
        """세션 준비 및 초기화"""
        self.session.expire_all()
        self.session.commit()
    
    def _fetch_active_open_orders(self) -> List[OpenOrder]:
        """활성 미체결 주문 조회 (eager loading 적용)"""
        return (
            self.session.query(OpenOrder)
            .options(
                joinedload(OpenOrder.strategy_account)
                .joinedload(StrategyAccount.account),
                joinedload(OpenOrder.strategy_account)  
                .joinedload(StrategyAccount.strategy)
            )
            .filter(OpenOrder.status == 'OPEN')
            .all()
        )
    
    def _group_orders_by_account(self, open_orders: List[OpenOrder]) -> Tuple[Dict[int, List], Dict[str, int]]:
        """주문을 계좌별로 그룹화하고 전략별 통계 생성"""
        orders_by_account = defaultdict(list)
        strategy_stats = defaultdict(int)
        
        for order in open_orders:
            strategy_account = order.strategy_account
            if not strategy_account or not strategy_account.account or not strategy_account.account.is_active:
                continue
            
            account_id = strategy_account.account.id
            orders_by_account[account_id].append({
                'order': order,
                'strategy_account': strategy_account,
                'account': strategy_account.account
            })
            
            # 전략별 통계
            strategy_name = strategy_account.strategy.name if strategy_account.strategy else 'Unknown'
            strategy_stats[strategy_name] += 1
        
        logger.info(f"주문 그룹화 완료 - {len(orders_by_account)}개 계좌, 전략별 분포: {dict(strategy_stats)}")
        return dict(orders_by_account), dict(strategy_stats)
    
    def _process_orders_by_account(self, orders_by_account: Dict[int, List]) -> Dict[str, int]:
        """계좌별 주문 처리"""
        stats = {'processed': 0, 'filled': 0, 'cancelled': 0, 'deleted': 0}
        
        for account_id, order_infos in orders_by_account.items():
            account = order_infos[0]['account']
            
            try:
                # 마켓 타입별로 주문 그룹화
                orders_by_market = self._group_orders_by_market_type(order_infos)
                
                # 마켓 타입별 처리
                for market_type, market_order_infos in orders_by_market.items():
                    account_stats = self._process_account_market_orders(
                        account, market_type, market_order_infos
                    )
                    
                    # 통계 누적
                    for key in stats:
                        stats[key] += account_stats.get(key, 0)
                        
            except Exception as e:
                logger.error(f"계좌 {account_id} 주문 처리 실패: {str(e)}")
                # 실패한 경우 개별 처리로 폴백
                fallback_stats = self._fallback_individual_processing(order_infos)
                for key in stats:
                    stats[key] += fallback_stats.get(key, 0)
        
        return stats
    
    def _group_orders_by_market_type(self, order_infos: List[Dict]) -> Dict[str, List]:
        """주문을 마켓 타입별로 그룹화"""
        orders_by_market = defaultdict(list)
        
        for info in order_infos:
            strategy = info['strategy_account'].strategy
            market_type = strategy.market_type if strategy else MarketType.SPOT
            orders_by_market[market_type].append(info)
        
        return dict(orders_by_market)
    
    def _process_account_market_orders(self, account: Account, market_type: str, 
                                     order_infos: List[Dict]) -> Dict[str, int]:
        """특정 계좌의 특정 마켓 타입 주문들 처리"""
        stats = {'processed': 0, 'filled': 0, 'cancelled': 0, 'deleted': 0}
        
        try:
            # 1. 거래소에서 열린 주문 조회
            exchange_orders = self._fetch_exchange_orders(account, market_type, order_infos)
            exchange_orders_dict = {str(order.get('id', '')): order for order in exchange_orders}
            
            # 2. 각 주문 처리
            for order_info in order_infos:
                order = order_info['order']
                
                try:
                    if order.status != 'OPEN':
                        continue
                    
                    order_stats = self._process_single_order(order, exchange_orders_dict, account, market_type)
                    
                    # 통계 누적
                    for key in stats:
                        stats[key] += order_stats.get(key, 0)
                        
                except Exception as e:
                    logger.warning(f"개별 주문 {order.exchange_order_id} 처리 실패: {str(e)}")
                    continue
                    
        except Exception as e:
            logger.error(f"계좌 {account.id} 마켓 {market_type} 주문 처리 실패: {str(e)}")
            raise
        
        logger.info(f"계좌 {account.id} ({market_type}) 처리 완료: {stats}")
        return stats
    
    def _fetch_exchange_orders(self, account: Account, market_type: str, 
                             order_infos: List[Dict]) -> List[Dict]:
        """거래소에서 열린 주문 조회 (최적화된 방식)"""
        symbols = list(set(info['order'].symbol for info in order_infos))
        
        # 바이낸스의 경우 심볼이 적으면 심볼별 조회
        if account.exchange.lower() == 'binance' and len(symbols) <= 5:
            logger.debug(f"바이낸스 계좌 {account.id}: 심볼별 조회 사용")
            return exchange_service.fetch_open_orders_by_symbols(
                account, symbols, market_type=market_type
            )
        else:
            return exchange_service.fetch_open_orders(account, market_type=market_type)
    
    def _process_single_order(self, order: OpenOrder, exchange_orders_dict: Dict[str, Dict], 
                            account: Account, market_type: str) -> Dict[str, int]:
        """개별 주문 처리"""
        stats = {'processed': 1, 'filled': 0, 'cancelled': 0, 'deleted': 0}
        exchange_order_id = str(order.exchange_order_id)
        
        if exchange_order_id in exchange_orders_dict:
            # 거래소에 존재하는 주문
            exchange_order = exchange_orders_dict[exchange_order_id]
            deleted = self._handle_existing_order(order, exchange_order)
            
        else:
            # 거래소에 없는 주문 - 개별 조회
            deleted = self._handle_missing_order(order, account, market_type)
        
        if deleted:
            order_status = getattr(order, '_cached_status', 'UNKNOWN')
            if order_status == 'FILLED':
                stats['filled'] = 1
            elif order_status == 'CANCELLED':
                stats['cancelled'] = 1
            stats['deleted'] = 1
        
        return stats
    
    def _handle_existing_order(self, order: OpenOrder, exchange_order: Dict[str, Any]) -> bool:
        """거래소에 존재하는 주문 처리"""
        order_status = exchange_order.get('status', '').lower()
        filled_amount = to_decimal(exchange_order.get('filled', 0))
        
        # 상태 캐싱 (삭제 후 통계 용도)
        if order_status in ['closed', 'filled'] and filled_amount > 0:
            order._cached_status = 'FILLED'
            return open_order_manager.process_filled_order(order, exchange_order, session=self.session)
            
        elif order_status in ['canceled', 'cancelled']:
            order._cached_status = 'CANCELLED'
            return open_order_manager.process_cancelled_order(order, session=self.session)
            
        elif order_status in ['partially_filled'] and filled_amount > 0:
            # 부분 체결 - 삭제하지 않음
            open_order_manager.update_order_status(order, 'PARTIALLY_FILLED', filled_amount, session=self.session)
            return False
        
        return False
    
    def _handle_missing_order(self, order: OpenOrder, account: Account, market_type: str) -> bool:
        """거래소에서 찾을 수 없는 주문 처리"""
        try:
            # 개별 조회로 정확한 상태 확인
            order_status = exchange_service.get_order_status(
                account, order.exchange_order_id, order.symbol, market_type=market_type
            )
            
            return self._handle_existing_order(order, order_status)
            
        except Exception as e:
            error_msg = str(e).lower()
            if "does not exist" in error_msg or "-2013" in error_msg:
                # 주문이 존재하지 않음 - 체결된 것으로 간주
                order._cached_status = 'FILLED'
                return self._handle_missing_order_as_filled(order)
            else:
                logger.warning(f"주문 {order.exchange_order_id} 개별 조회 실패: {str(e)}")
                return False
    
    def _handle_missing_order_as_filled(self, order: OpenOrder) -> bool:
        """누락된 주문을 체결 처리"""
        try:
            # 기존 Trade 레코드 확인
            from app.models import Trade
            existing_trade = self.session.query(Trade).filter_by(
                strategy_account_id=order.strategy_account_id,
                exchange_order_id=order.exchange_order_id
            ).first()
            
            if existing_trade and existing_trade.quantity > 0:
                # 이미 처리됨
                return open_order_manager.delete_completed_order(order, "already_processed", session=self.session)
            
            # 주문 정보로 체결 처리
            filled_quantity = to_decimal(order.quantity)
            average_price = to_decimal(order.price)
            
            if open_order_manager.mark_order_filled(order, filled_quantity, average_price, session=self.session):
                return open_order_manager.delete_completed_order(order, "missing_order_filled", session=self.session)
            
            return False
            
        except Exception as e:
            logger.error(f"누락 주문 처리 실패 - ID: {order.exchange_order_id}, 오류: {str(e)}")
            return False
    
    def _fallback_individual_processing(self, order_infos: List[Dict]) -> Dict[str, int]:
        """개별 주문 처리로 폴백"""
        logger.warning(f"개별 주문 처리로 폴백 - {len(order_infos)}개 주문")
        stats = {'processed': 0, 'filled': 0, 'cancelled': 0, 'deleted': 0}
        
        for order_info in order_infos:
            order = order_info['order']
            account = order_info['account']
            strategy = order_info['strategy_account'].strategy
            market_type = strategy.market_type if strategy else MarketType.SPOT
            
            try:
                order_stats = self._process_single_order(order, {}, account, market_type)
                for key in stats:
                    stats[key] += order_stats.get(key, 0)
                    
            except Exception as e:
                logger.error(f"폴백 개별 주문 처리 실패 - ID: {order.exchange_order_id}, 오류: {str(e)}")
                continue
        
        return stats
    
    def _create_summary_result(self, cleanup_count: int, total_orders: int, 
                             processed_orders: int, filled_orders: int, 
                             cancelled_orders: int, deleted_orders: int = 0,
                             strategy_stats: Dict[str, int] = None) -> Dict[str, Any]:
        """처리 결과 요약 생성"""
        result = {
            'success': True,
            'cleanup_deleted_count': cleanup_count,
            'total_orders': total_orders,
            'processed_orders': processed_orders,
            'filled_orders': filled_orders,
            'cancelled_orders': cancelled_orders,
            'deleted_orders': deleted_orders,
            'strategy_stats': strategy_stats or {},
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # 로깅
        if total_orders == 0:
            if cleanup_count > 0:
                logger.info(f"🧹 완료된 주문 정리만 수행 - {cleanup_count}개 레코드 삭제")
            else:
                logger.debug("처리할 미체결 주문이 없습니다.")
        else:
            msg = f"✅ 미체결 주문 상태 업데이트 완료 - 처리: {processed_orders}개, 체결: {filled_orders}개, 취소: {cancelled_orders}개"
            if deleted_orders > 0:
                msg += f", 삭제: {deleted_orders}개 레코드"
            if cleanup_count > 0:
                msg += f" (사전 정리: {cleanup_count}개)"
            logger.info(msg)
        
        return result


# 전역 인스턴스
order_status_processor = OrderStatusProcessor() 