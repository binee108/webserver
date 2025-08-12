"""
포지션 관리 서비스 모듈
포지션 업데이트, 청산, 미실현 손익 계산 등 포지션 관련 로직
"""

import logging
from typing import Dict, Any, Optional, Tuple, List
from decimal import Decimal
from datetime import datetime
from collections import defaultdict

from sqlalchemy.orm import joinedload
from app import db
from app.models import StrategyPosition, StrategyAccount, StrategyCapital, Account, OpenOrder
from app.services.utils import to_decimal, decimal_to_float
from app.services.exchange_service import exchange_service

# 백그라운드 작업용 로거 사용
logger = logging.getLogger('trading_system.background')

class PositionError(Exception):
    """포지션 관련 오류"""
    pass

class PositionService:
    """포지션 서비스 클래스"""
    
    def __init__(self):
        self.session = db.session
    
    # ⚠️ SSE 이벤트 발송은 trading_service에서 중앙화됨 - 이 메서드는 더 이상 사용하지 않음
    
    def update_position(self, position: StrategyPosition, side: str, quantity: Decimal, price: Decimal):
        """포지션 업데이트 (평균가 계산 포함)"""
        current_qty = to_decimal(position.quantity)
        current_price = to_decimal(position.entry_price)
        
        # 업데이트 전 상태 로깅
        logger.info(f"포지션 업데이트 시작 - 심볼: {position.symbol}, "
                   f"현재 포지션: {current_qty}, 현재 평균가: {current_price}, "
                   f"추가 거래: {side} {quantity} @ {price}")
        
        # 이전 수량 저장 (이벤트 판단용)
        previous_qty = current_qty
        
        if side.upper() == 'BUY':
            if current_qty >= 0:
                # 롱 포지션 추가 - 가중평균 계산
                if current_qty == 0:
                    # 신규 진입
                    new_qty = quantity
                    new_entry_price = price
                    logger.info(f"신규 롱 포지션 진입 - 수량: {new_qty}, 진입가: {new_entry_price}")
                else:
                    # 기존 롱 포지션에 추가
                    total_cost = (current_qty * current_price) + (quantity * price)
                    new_qty = current_qty + quantity
                    new_entry_price = total_cost / new_qty
                    logger.info(f"롱 포지션 추가 - 기존: {current_qty}@{current_price}, "
                               f"추가: {quantity}@{price}, 새 평균가: {new_entry_price}")
                
                position.quantity = decimal_to_float(new_qty)
                position.entry_price = decimal_to_float(new_entry_price)
            else:
                # 숏 포지션 청산
                if quantity >= abs(current_qty):
                    # 완전 청산 + 롱 전환
                    realized_pnl = abs(current_qty) * (current_price - price)
                    logger.info(f"숏 포지션 완전 청산 후 롱 전환 - 실현 손익: {realized_pnl}")
                    remaining_qty = quantity - abs(current_qty)
                    position.quantity = decimal_to_float(remaining_qty)
                    position.entry_price = decimal_to_float(price) if remaining_qty > 0 else 0
                else:
                    # 부분 청산
                    realized_pnl = quantity * (current_price - price)
                    logger.info(f"숏 포지션 부분 청산 - 실현 손익: {realized_pnl}")
                    new_qty = current_qty + quantity  # 음수에서 0에 가까워짐
                    position.quantity = decimal_to_float(new_qty)
        
        elif side.upper() == 'SELL':
            if current_qty <= 0:
                # 숏 포지션 추가 - 가중평균 계산
                if current_qty == 0:
                    # 신규 숏 진입
                    new_qty = -quantity
                    new_entry_price = price
                    logger.info(f"신규 숏 포지션 진입 - 수량: {new_qty}, 진입가: {new_entry_price}")
                else:
                    # 기존 숏 포지션에 추가
                    total_cost = (abs(current_qty) * current_price) + (quantity * price)
                    new_qty = current_qty - quantity  # 더 음수가 됨
                    new_entry_price = total_cost / abs(new_qty)
                    logger.info(f"숏 포지션 추가 - 기존: {current_qty}@{current_price}, "
                               f"추가: {quantity}@{price}, 새 평균가: {new_entry_price}")
                
                position.quantity = decimal_to_float(new_qty)
                position.entry_price = decimal_to_float(new_entry_price) if new_qty != 0 else 0
            else:
                # 롱 포지션 청산
                if quantity >= current_qty:
                    # 완전 청산 + 숏 전환
                    realized_pnl = current_qty * (price - current_price)
                    logger.info(f"롱 포지션 완전 청산 후 숏 전환 - 실현 손익: {realized_pnl}")
                    remaining_qty = quantity - current_qty
                    position.quantity = decimal_to_float(-remaining_qty)  # 숏 포지션
                    position.entry_price = decimal_to_float(price) if remaining_qty > 0 else 0
                else:
                    # 부분 청산
                    realized_pnl = quantity * (price - current_price)
                    logger.info(f"롱 포지션 부분 청산 - 실현 손익: {realized_pnl}")
                    new_qty = current_qty - quantity
                    position.quantity = decimal_to_float(new_qty)
        
        position.last_updated = datetime.utcnow()
        
        # 최종 상태 로깅
        logger.info(f"포지션 업데이트 완료 - 심볼: {position.symbol}, "
                   f"최종 포지션: {position.quantity}, 최종 평균가: {position.entry_price}")
        
        # ✅ SSE 이벤트는 trading_service에서 중앙화 처리됨
        final_qty = to_decimal(position.quantity)
        logger.debug(f"포지션 업데이트 완료, SSE는 중앙 처리: {position.symbol}, 수량: {final_qty}")
    
    def update_position_from_order(self, order, strategy_account: StrategyAccount, 
                                  filled_quantity: Decimal, average_price: Decimal,
                                  session=None):
        """주문 체결에 따른 포지션 업데이트"""
        current_session = session or self.session
        
        # 중복 처리 방지: 이미 처리된 주문인지 확인
        from app.models import Trade
        processed_trade = current_session.query(Trade).filter_by(
            strategy_account_id=order.strategy_account_id,
            exchange_order_id=order.exchange_order_id
        ).first()
        
        # Trade 레코드가 이미 체결된 수량과 현재 처리하려는 수량이 같다면 이미 포지션 업데이트됨
        if processed_trade and abs(processed_trade.quantity - decimal_to_float(filled_quantity)) < 0.00000001:
            logger.debug(f"주문 {order.exchange_order_id} 포지션 이미 업데이트됨, 건너뛰기")
            return
        
        # 포지션 조회/생성
        position = current_session.query(StrategyPosition).filter_by(
            strategy_account_id=order.strategy_account_id,
            symbol=order.symbol
        ).first()
        
        if not position:
            position = StrategyPosition(
                strategy_account_id=order.strategy_account_id,
                symbol=order.symbol,
                quantity=0,
                entry_price=0
            )
            current_session.add(position)
            current_session.flush()
        
        # 포지션 업데이트
        logger.info(f"포지션 업데이트 시작 - 주문: {order.exchange_order_id}, 수량: {filled_quantity}, 가격: {average_price}")
        self.update_position(position, order.side, filled_quantity, average_price)
    
    def close_position_market(self, strategy_account, symbol):
        """포지션 시장가 청산"""
        try:
            # 현재 포지션 조회
            position = StrategyPosition.query.filter_by(
                strategy_account_id=strategy_account.id,
                symbol=symbol
            ).first()
            
            if not position or position.quantity == 0:
                return {
                    'success': False,
                    'error': '청산할 포지션이 없습니다.'
                }
            
            # 포지션 방향에 따라 청산 파라미터 계산
            current_qty = to_decimal(position.quantity)
            
            if current_qty > 0:
                # 롱 포지션 청산 (SELL)
                side = 'SELL'
            else:
                # 숏 포지션 청산 (BUY)
                side = 'BUY'
            
            # 청산 실행 전 상세 로깅
            market_type = strategy_account.strategy.market_type.upper()
            logger.info(f"포지션 청산 시작 - 계좌: {strategy_account.account.id}({strategy_account.account.name}), "
                       f"심볼: {symbol}, 수량: {current_qty}, 사이드: {side}, 마켓타입: {market_type}")
            
            # 청산 거래 실행 (기존 세션 사용, 병렬 처리 없이)
            try:
                # 전체 청산을 위해 qty_per = -1 사용하되, 단일 계좌이므로 직접 execute_trade 호출
                from app.services.trading_service import trading_service
                result = trading_service.execute_trade(
                    strategy=strategy_account.strategy,
                    account=strategy_account.account,
                    symbol=symbol,
                    side=side,
                    order_type='MARKET',
                    price=None,
                    qty_per=Decimal('-1'),  # 전체 청산 신호
                    currency='USDT',
                    market=market_type
                )
                
                if result.get('success'):
                    logger.info(f'포지션 청산 완료: {symbol} {side.upper()} {result.get("quantity")}')
                    
                    # 트랜잭션은 상위에서 처리하도록 함
                    return {
                        'success': True,
                        'order_id': result.get('order_id'),
                        'filled_quantity': result.get('quantity'),
                        'average_price': result.get('filled_price'),  # 체결 가격 사용
                        'realized_pnl': result.get('realized_pnl'),
                        'fee': result.get('fee')
                    }
                else:
                    logger.error(f'포지션 청산 실패: {symbol} - {result.get("error", "알 수 없는 오류")}')
                    return {
                        'success': False,
                        'error': result.get('error', '포지션 청산에 실패했습니다.')
                    }
            except Exception as trade_error:
                logger.error(f'거래 실행 중 오류: {str(trade_error)}')
                return {
                    'success': False,
                    'error': f'거래 실행 실패: {str(trade_error)}'
                }
                
        except Exception as e:
            logger.error(f'포지션 청산 오류: {str(e)}')
            return {
                'success': False,
                'error': str(e)
            }
    
    def calculate_unrealized_pnl(self):
        """미실현 손익 계산 (최적화된 버전)"""
        try:
            # Step 1: Reset all current_pnl to 0
            self._reset_all_current_pnl()
            
            # Step 2: Fetch all positions with related data in single query
            positions_with_details = self._fetch_positions_with_details()
            
            if not positions_with_details:
                logger.info("계산할 활성 포지션이 없습니다.")
                return
            
            # Step 3: Collect unique tickers needed and fetch them in batch
            ticker_cache = self._fetch_tickers_batch(positions_with_details)
            
            # Step 4: Calculate PnL for each strategy account
            strategy_account_pnls = self._calculate_strategy_account_pnls(
                positions_with_details, ticker_cache
            )
            
            # Step 5: Update StrategyCapital records
            self._update_strategy_capitals(strategy_account_pnls)
            
            # Step 6: Update position timestamps
            self._update_position_timestamps(positions_with_details)
            
            # Commit all changes
            self.session.commit()
            logger.debug(f"미실현 손익 계산 완료: {len(strategy_account_pnls)}개 계좌 업데이트")
            
        except Exception as e:
            logger.error(f"미실현 손익 계산 중 오류: {str(e)}")
            self.session.rollback()
            raise
    
    def _reset_all_current_pnl(self):
        """모든 StrategyCapital의 current_pnl을 0으로 초기화"""
        try:
            # 모든 StrategyCapital의 current_pnl을 0으로 리셋
            updated_count = (
                StrategyCapital.query
                .filter(StrategyCapital.current_pnl != 0)
                .update({
                    'current_pnl': 0,
                    'last_updated': datetime.utcnow()
                })
            )
            
            if updated_count > 0:
                logger.debug(f"StrategyCapital current_pnl 초기화: {updated_count}개 레코드")
            
        except Exception as e:
            logger.warning(f"current_pnl 초기화 중 오류: {str(e)}")
            # Fallback to individual update
            all_strategy_capitals = StrategyCapital.query.all()
            for sc in all_strategy_capitals:
                sc.current_pnl = 0
                sc.last_updated = datetime.utcnow()
    
    def _fetch_positions_with_details(self) -> List[StrategyPosition]:
        """모든 관련 정보와 함께 활성 포지션 조회 (최적화된 단일 쿼리)"""
        return (
            StrategyPosition.query
            .join(StrategyAccount)
            .join(StrategyAccount.account)
            .join(StrategyAccount.strategy)
            .options(
                joinedload(StrategyPosition.strategy_account)
                .joinedload(StrategyAccount.account),
                joinedload(StrategyPosition.strategy_account)
                .joinedload(StrategyAccount.strategy)
            )
            .filter(
                StrategyPosition.quantity != 0,
                Account.is_active == True
            )
            .all()
        )
    
    def _fetch_tickers_batch(self, positions: List[StrategyPosition]) -> Dict[Tuple[int, str], Dict[str, Any]]:
        """필요한 시세를 배치로 조회하여 캐시 생성"""
        # Collect unique (account_id, symbol) combinations
        unique_tickers_needed = set()
        for pos in positions:
            account_id = pos.strategy_account.account.id
            symbol = pos.symbol
            unique_tickers_needed.add((account_id, symbol))
        
        # Fetch tickers and cache them
        ticker_cache = {}
        for account_id, symbol in unique_tickers_needed:
            try:
                # Find account object from positions (already loaded)
                account = None
                for pos in positions:
                    if pos.strategy_account.account.id == account_id:
                        account = pos.strategy_account.account
                        break
                
                if account:
                    ticker = exchange_service.get_ticker(account, symbol)
                    ticker_cache[(account_id, symbol)] = ticker
                    logger.debug(f"시세 조회 성공: {symbol} @ {ticker['last']}")
                    
            except Exception as e:
                logger.warning(f"시세 조회 실패: {symbol} (계좌 {account_id}) - {str(e)}")
                continue
        
        logger.info(f"배치 시세 조회 완료: {len(ticker_cache)}/{len(unique_tickers_needed)}개 성공")
        return ticker_cache
    
    def _calculate_strategy_account_pnls(self, 
                                       positions: List[StrategyPosition], 
                                       ticker_cache: Dict[Tuple[int, str], Dict[str, Any]]) -> Dict[int, Decimal]:
        """전략 계좌별 미실현 손익 계산"""
        strategy_account_pnls = defaultdict(Decimal)
        
        for pos in positions:
            try:
                account_id = pos.strategy_account.account.id
                strategy_account_id = pos.strategy_account_id
                symbol = pos.symbol
                
                # Get cached ticker
                ticker_key = (account_id, symbol)
                if ticker_key not in ticker_cache:
                    logger.warning(f"시세 정보 없음: {symbol} (계좌 {account_id})")
                    continue
                
                current_price = to_decimal(ticker_cache[ticker_key]['last'])
                
                # Calculate unrealized PnL for this position
                position_pnl = self._calculate_position_pnl(pos, current_price)
                strategy_account_pnls[strategy_account_id] += position_pnl
                
                logger.debug(f"포지션 손익 계산: {symbol} = {position_pnl} "
                           f"(수량: {pos.quantity}, 진입가: {pos.entry_price}, 현재가: {current_price})")
                
            except Exception as e:
                logger.warning(f"포지션 {pos.id} 손익 계산 실패: {str(e)}")
                continue
        
        return dict(strategy_account_pnls)
    
    def _calculate_position_pnl(self, position: StrategyPosition, current_price: Decimal) -> Decimal:
        """개별 포지션의 미실현 손익 계산"""
        position_qty = to_decimal(position.quantity)
        entry_price = to_decimal(position.entry_price)
        
        if position_qty > 0:
            # Long position: profit when current > entry
            return position_qty * (current_price - entry_price)
        else:
            # Short position: profit when entry > current
            return abs(position_qty) * (entry_price - current_price)
    
    def _update_strategy_capitals(self, strategy_account_pnls: Dict[int, Decimal]):
        """StrategyCapital 레코드 일괄 업데이트"""
        if not strategy_account_pnls:
            return
        
        # Fetch all required StrategyCapital records in single query
        strategy_account_ids = list(strategy_account_pnls.keys())
        strategy_capitals = StrategyCapital.query.filter(
            StrategyCapital.strategy_account_id.in_(strategy_account_ids)
        ).all()
        
        # Update current_pnl for each record
        for sc in strategy_capitals:
            pnl = strategy_account_pnls.get(sc.strategy_account_id, Decimal('0'))
            sc.current_pnl = decimal_to_float(pnl)
            sc.last_updated = datetime.utcnow()
            logger.debug(f"StrategyCapital 업데이트: 계좌 {sc.strategy_account_id} PnL = {pnl}")
    
    def _update_position_timestamps(self, positions: List[StrategyPosition]):
        """포지션들의 last_updated 시간 일괄 업데이트"""
        current_time = datetime.utcnow()
        for pos in positions:
            pos.last_updated = current_time
    
    def close_position_by_id(self, position_id: int, user_id: int) -> Dict[str, Any]:
        """포지션 ID로 포지션 청산 (권한 확인 포함, 완전한 트랜잭션 관리)"""
        try:
            from app.models import Strategy, StrategyAccount
            
            # 포지션 조회 및 권한 확인
            position = StrategyPosition.query.join(StrategyAccount).join(Strategy).join(Account).filter(
                StrategyPosition.id == position_id,
                (Strategy.user_id == user_id) | (Account.user_id == user_id)
            ).first()
            
            if not position:
                return {
                    'success': False,
                    'error': '포지션을 찾을 수 없습니다.'
                }
            
            if position.quantity == 0:
                return {
                    'success': False,
                    'error': '청산할 포지션이 없습니다.'
                }
            
            # 전략 계좌 정보 조회
            strategy_account = StrategyAccount.query.get(position.strategy_account_id)
            if not strategy_account:
                return {
                    'success': False,
                    'error': '전략 계좌 정보를 찾을 수 없습니다.'
                }
            
            # 포지션 청산 실행
            result = self.close_position_market(
                strategy_account=strategy_account,
                symbol=position.symbol
            )
            
            if result.get('success'):
                # 성공시 트랜잭션 commit
                self.session.commit()
                logger.info(f'포지션 청산 및 커밋 완료: 포지션 ID {position_id}')
                
                # ✅ SSE 이벤트는 trading_service에서 중앙화 처리됨
            else:
                # 실패시 롤백
                self.session.rollback()
                logger.warning(f'포지션 청산 실패 후 롤백: 포지션 ID {position_id}')
            
            return result
            
        except Exception as e:
            # 예외 발생시 롤백
            self.session.rollback()
            logger.error(f'포지션 청산 오류 후 롤백: {str(e)}')
            return {
                'success': False,
                'error': f'포지션 청산 실패: {str(e)}'
            }

    def get_user_open_orders_with_positions(self, user_id: int) -> Dict[str, Any]:
        """사용자의 열린 주문과 포지션 통합 조회"""
        try:
            from app.models import OpenOrder, Strategy, Account
            from sqlalchemy.orm import joinedload
            from sqlalchemy import desc
            
            # 열린 주문 조회
            open_orders = (
                self.session.query(OpenOrder)
                .join(StrategyAccount)
                .join(Strategy)
                .join(Account)
                .options(
                    joinedload(OpenOrder.strategy_account)
                    .joinedload(StrategyAccount.strategy),
                    joinedload(OpenOrder.strategy_account)
                    .joinedload(StrategyAccount.account)
                )
                .filter(
                    (Strategy.user_id == user_id) | (Account.user_id == user_id),
                    OpenOrder.status == 'OPEN',
                    Account.is_active == True
                )
                .order_by(desc(OpenOrder.created_at))
                .all()
            )
            
            # 활성 포지션 조회
            active_positions = (
                self.session.query(StrategyPosition)
                .join(StrategyAccount)
                .join(Strategy)
                .join(Account)
                .options(
                    joinedload(StrategyPosition.strategy_account)
                    .joinedload(StrategyAccount.strategy),
                    joinedload(StrategyPosition.strategy_account)
                    .joinedload(StrategyAccount.account)
                )
                .filter(
                    (Strategy.user_id == user_id) | (Account.user_id == user_id),
                    StrategyPosition.quantity != 0,
                    Account.is_active == True
                )
                .all()
            )
            
            # 심볼별로 포지션과 주문을 그룹화
            symbol_data = defaultdict(lambda: {
                'positions': [],
                'open_orders': [],
                'total_position_value': 0,
                'total_order_value': 0
            })
            
            # 포지션 데이터 처리
            for position in active_positions:
                strategy_account = position.strategy_account
                strategy = strategy_account.strategy
                account = strategy_account.account
                
                position_value = abs(position.quantity * position.entry_price)
                symbol_data[position.symbol]['positions'].append({
                    'id': position.id,
                    'quantity': position.quantity,
                    'entry_price': position.entry_price,
                    'last_updated': position.last_updated.isoformat(),
                    'strategy': {
                        'id': strategy.id,
                        'name': strategy.name,
                        'group_name': strategy.group_name,
                        'market_type': strategy.market_type
                    },
                    'account': {
                        'id': account.id,
                        'name': account.name,
                        'exchange': account.exchange
                    }
                })
                symbol_data[position.symbol]['total_position_value'] += position_value
            
            # 열린 주문 데이터 처리
            for order in open_orders:
                strategy_account = order.strategy_account
                strategy = strategy_account.strategy
                account = strategy_account.account
                
                order_value = order.quantity * order.price
                symbol_data[order.symbol]['open_orders'].append({
                    'id': order.id,
                    'exchange_order_id': order.exchange_order_id,
                    'side': order.side,
                    'quantity': order.quantity,
                    'price': order.price,
                    'filled_quantity': order.filled_quantity,
                    'status': order.status,
                    'market_type': order.market_type,
                    'created_at': order.created_at.isoformat(),
                    'strategy': {
                        'id': strategy.id,
                        'name': strategy.name,
                        'group_name': strategy.group_name,
                        'market_type': strategy.market_type
                    },
                    'account': {
                        'id': account.id,
                        'name': account.name,
                        'exchange': account.exchange
                    }
                })
                symbol_data[order.symbol]['total_order_value'] += order_value
            
            # 결과 구성
            result = {
                'success': True,
                'symbol_data': dict(symbol_data),
                'summary': {
                    'total_positions': len(active_positions),
                    'total_open_orders': len(open_orders),
                    'active_symbols': len(symbol_data),
                    'total_position_value': sum(data['total_position_value'] for data in symbol_data.values()),
                    'total_order_value': sum(data['total_order_value'] for data in symbol_data.values())
                }
            }
            
            logger.info(f"통합 포지션/주문 조회 완료 - 사용자: {user_id}, "
                       f"포지션: {len(active_positions)}개, 주문: {len(open_orders)}개, "
                       f"활성 심볼: {len(symbol_data)}개")
            
            return result
            
        except Exception as e:
            logger.error(f"통합 포지션/주문 조회 실패 - 사용자: {user_id}, 오류: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'symbol_data': {},
                'summary': {}
            }
    
    def get_position_and_orders_by_symbol(self, user_id: int, symbol: str) -> Dict[str, Any]:
        """특정 심볼의 포지션과 열린 주문 조회"""
        try:
            from app.models import OpenOrder, Strategy, Account
            from sqlalchemy.orm import joinedload
            
            # 해당 심볼의 포지션 조회
            positions = (
                self.session.query(StrategyPosition)
                .join(StrategyAccount)
                .join(Strategy)
                .join(Account)
                .options(
                    joinedload(StrategyPosition.strategy_account)
                    .joinedload(StrategyAccount.strategy),
                    joinedload(StrategyPosition.strategy_account)
                    .joinedload(StrategyAccount.account)
                )
                .filter(
                    (Strategy.user_id == user_id) | (Account.user_id == user_id),
                    StrategyPosition.symbol == symbol,
                    StrategyPosition.quantity != 0,
                    Account.is_active == True
                )
                .all()
            )
            
            # 해당 심볼의 열린 주문 조회
            open_orders = (
                self.session.query(OpenOrder)
                .join(StrategyAccount)
                .join(Strategy)
                .join(Account)
                .options(
                    joinedload(OpenOrder.strategy_account)
                    .joinedload(StrategyAccount.strategy),
                    joinedload(OpenOrder.strategy_account)
                    .joinedload(StrategyAccount.account)
                )
                .filter(
                    (Strategy.user_id == user_id) | (Account.user_id == user_id),
                    OpenOrder.symbol == symbol,
                    OpenOrder.status == 'OPEN',
                    Account.is_active == True
                )
                .all()
            )
            
            # 포지션 데이터 구성
            positions_data = []
            total_long_qty = Decimal('0')
            total_short_qty = Decimal('0')
            weighted_long_price = Decimal('0')
            weighted_short_price = Decimal('0')
            
            for position in positions:
                strategy_account = position.strategy_account
                strategy = strategy_account.strategy
                account = strategy_account.account
                
                qty = to_decimal(position.quantity)
                entry_price = to_decimal(position.entry_price)
                
                if qty > 0:
                    total_long_qty += qty
                    weighted_long_price += qty * entry_price
                else:
                    total_short_qty += abs(qty)
                    weighted_short_price += abs(qty) * entry_price
                
                positions_data.append({
                    'id': position.id,
                    'quantity': position.quantity,
                    'entry_price': position.entry_price,
                    'last_updated': position.last_updated.isoformat(),
                    'strategy': {
                        'id': strategy.id,
                        'name': strategy.name,
                        'group_name': strategy.group_name,
                        'market_type': strategy.market_type
                    },
                    'account': {
                        'id': account.id,
                        'name': account.name,
                        'exchange': account.exchange
                    }
                })
            
            # 열린 주문 데이터 구성
            orders_data = []
            total_buy_orders = Decimal('0')
            total_sell_orders = Decimal('0')
            
            for order in open_orders:
                strategy_account = order.strategy_account
                strategy = strategy_account.strategy
                account = strategy_account.account
                
                qty = to_decimal(order.quantity)
                if order.side.upper() == 'BUY':
                    total_buy_orders += qty
                else:
                    total_sell_orders += qty
                
                orders_data.append({
                    'id': order.id,
                    'exchange_order_id': order.exchange_order_id,
                    'side': order.side,
                    'quantity': order.quantity,
                    'price': order.price,
                    'filled_quantity': order.filled_quantity,
                    'status': order.status,
                    'market_type': order.market_type,
                    'created_at': order.created_at.isoformat(),
                    'strategy': {
                        'id': strategy.id,
                        'name': strategy.name,
                        'group_name': strategy.group_name,
                        'market_type': strategy.market_type
                    },
                    'account': {
                        'id': account.id,
                        'name': account.name,
                        'exchange': account.exchange
                    }
                })
            
            # 평균 가격 계산
            avg_long_price = decimal_to_float(weighted_long_price / total_long_qty) if total_long_qty > 0 else 0
            avg_short_price = decimal_to_float(weighted_short_price / total_short_qty) if total_short_qty > 0 else 0
            
            result = {
                'success': True,
                'symbol': symbol,
                'positions': positions_data,
                'open_orders': orders_data,
                'summary': {
                    'total_positions': len(positions),
                    'total_open_orders': len(open_orders),
                    'net_position': decimal_to_float(total_long_qty - total_short_qty),
                    'long_position': decimal_to_float(total_long_qty),
                    'short_position': decimal_to_float(total_short_qty),
                    'avg_long_price': avg_long_price,
                    'avg_short_price': avg_short_price,
                    'pending_buy_orders': decimal_to_float(total_buy_orders),
                    'pending_sell_orders': decimal_to_float(total_sell_orders)
                }
            }
            
            logger.info(f"심볼별 포지션/주문 조회 완료 - 사용자: {user_id}, 심볼: {symbol}, "
                       f"포지션: {len(positions)}개, 주문: {len(open_orders)}개")
            
            return result
            
        except Exception as e:
            logger.error(f"심볼별 포지션/주문 조회 실패 - 사용자: {user_id}, 심볼: {symbol}, 오류: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'symbol': symbol,
                'positions': [],
                'open_orders': [],
                'summary': {}
            }

    def get_user_open_orders(self, user_id: int) -> Dict[str, Any]:
        """사용자의 열린 주문 조회 (Service 계층)"""
        try:
            from app.models import OpenOrder, Strategy, Account
            from sqlalchemy.orm import joinedload
            from sqlalchemy import desc
            
            # 사용자의 모든 열린 주문을 조회 (권한 확인 포함)
            open_orders = (
                self.session.query(OpenOrder)
                .join(StrategyAccount)
                .join(Strategy)
                .join(Account)
                .options(
                    joinedload(OpenOrder.strategy_account)
                    .joinedload(StrategyAccount.strategy),
                    joinedload(OpenOrder.strategy_account)
                    .joinedload(StrategyAccount.account)
                )
                .filter(
                    Strategy.user_id == user_id,
                    OpenOrder.status == 'OPEN',
                    Account.is_active == True
                )
                .order_by(desc(OpenOrder.created_at))
                .all()
            )
            
            # 응답 데이터 구성
            orders_data = []
            for order in open_orders:
                strategy_account = order.strategy_account
                strategy = strategy_account.strategy
                account = strategy_account.account
                
                orders_data.append({
                    'order_id': order.exchange_order_id,  # 통일된 명명: order_id 사용 (exchange_order_id를 매핑)
                    'symbol': order.symbol,
                    'side': order.side,
                    'quantity': order.quantity,
                    'price': order.price,
                    'filled_quantity': order.filled_quantity,
                    'status': order.status,
                    'market_type': order.market_type,
                    'created_at': order.created_at.isoformat(),
                    'strategy': {
                        'id': strategy.id,
                        'name': strategy.name,
                        'group_name': strategy.group_name,
                        'market_type': strategy.market_type
                    },
                    'account': {
                        'id': account.id,
                        'name': account.name,
                        'exchange': account.exchange
                    },
                    'strategy_account_id': strategy_account.id
                })
            
            logger.info(f"사용자 열린 주문 조회 완료 - 사용자: {user_id}, {len(orders_data)}개 주문")
            
            return {
                'success': True,
                'open_orders': orders_data,
                'total_count': len(orders_data)
            }
            
        except Exception as e:
            logger.error(f"사용자 열린 주문 조회 실패 - 사용자: {user_id}, 오류: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'open_orders': [],
                'total_count': 0
            }

# 전역 인스턴스
position_service = PositionService() 