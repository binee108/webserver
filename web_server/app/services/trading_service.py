"""
트레이딩 로직 서비스 모듈
핵심 거래 실행 로직
"""

import logging
from typing import Dict, Any, List, Optional
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from datetime import datetime
from sqlalchemy.orm import sessionmaker
from sqlalchemy import and_
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed  # 🆕 병렬 처리를 위한 import 추가
import threading  # 🆕 스레드 로컬 세션을 위한 import 추가
import time  # 🆕 성능 측정용

from app import db
from app.models import (
    Strategy, Account, StrategyAccount, StrategyCapital, 
    StrategyPosition, Trade, OpenOrder, WebhookLog
)
from app.services.exchange_service import exchange_service, ExchangeError
from app.services.utils import to_decimal, decimal_to_float, calculate_is_entry
from app.services.position_service import position_service
from app.constants import MarketType, Exchange, OrderType

logger = logging.getLogger(__name__)

class TradingError(Exception):
    """트레이딩 관련 오류"""
    pass


class TradingService:
    """트레이딩 서비스 클래스 - 핵심 거래 실행 로직"""
    
    def __init__(self):
        self.session = db.session
        # 🆕 스레드 로컬 세션 팩토리 생성
        self.SessionLocal = sessionmaker(bind=db.engine)
    
    def _emit_trading_events(self, order_type: str, filled_info: Dict[str, Any], order_id: str,
                           symbol: str, side: str, quantity: Decimal, price: Decimal, average_price: Decimal,
                           strategy: Strategy, account: Account, position: StrategyPosition):
        """거래 완료 후 통합 SSE 이벤트 발송 (중앙화)"""
        try:
            from app.services.event_service import event_service, OrderEvent, PositionEvent
            
            # 계좌 정보를 중첩 구조로 구성 (프론트엔드 친화적)
            account_info = {
                'id': account.id,
                'name': account.name,
                'exchange': account.exchange
            }
            
            # 1. LIMIT 주문인 경우만 주문 이벤트 발송 (시장가 주문은 제외)
            if order_type == OrderType.LIMIT and filled_info['status'] != 'FILLED':
                order_event = OrderEvent(
                    event_type='order_created',
                    order_id=order_id,
                    symbol=symbol,
                    strategy_id=strategy.id,
                    user_id=account.user_id,
                    side=side,  # 이미 BUY/SELL로 표준화되어 전달됨
                    quantity=decimal_to_float(quantity),
                    price=decimal_to_float(price),
                    status='OPEN',
                    timestamp=datetime.utcnow().isoformat(),
                    # 중첩 구조로 계좌 정보 전달
                    account=account_info
                )
                event_service.emit_order_event(order_event)
                logger.info(f"📤 LIMIT 주문 SSE 이벤트: {order_id} ({account.name})")
            
            # 2. 체결된 경우 포지션 이벤트 발송 (시장가 주문 포함)
            if filled_info['status'] == 'FILLED' and filled_info['filled_quantity'] > 0:
                position_qty = to_decimal(position.quantity)
                event_type = 'position_closed' if position_qty == 0 else 'position_updated'
                
                position_event = PositionEvent(
                    event_type=event_type,
                    position_id=position.id,
                    symbol=symbol,
                    strategy_id=strategy.id,
                    user_id=account.user_id,
                    quantity=position.quantity,
                    entry_price=position.entry_price,
                    timestamp=datetime.utcnow().isoformat(),
                    # 중첩 구조로 계좌 정보 전달
                    account=account_info
                )
                event_service.emit_position_event(position_event)
                logger.info(f"📤 포지션 SSE 이벤트: {event_type} - {symbol} ({account.name})")
                
        except Exception as e:
            logger.error(f"통합 SSE 이벤트 발송 실패: {str(e)}")
    
    def process_trading_signal(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """거래 신호 처리 (병렬 처리 개선)"""
        # 필수 필드 검증
        required_fields = ['group_name', 'exchange', 'market_type', 'currency', 'symbol', 'order_type', 'side']
        for field in required_fields:
            if field not in webhook_data:
                raise TradingError(f"필수 필드 누락: {field}")
        
        group_name = webhook_data['group_name']
        exchange = webhook_data['exchange']
        market_type = webhook_data['market_type']
        currency = webhook_data['currency']
        symbol = webhook_data['symbol']
        order_type = webhook_data['order_type']
        side = webhook_data['side']  # 이미 normalize_webhook_data에서 소문자로 표준화됨
        price = to_decimal(webhook_data.get('price')) if webhook_data.get('price') else None
        qty_per = to_decimal(webhook_data.get('qty_per', 100))  # Decimal로 변환
        
        logger.info(f"거래 신호 처리 시작 - 전략: {group_name}, 거래소: {exchange}, 심볼: {symbol}, "
                   f"사이드: {side}, 주문타입: {order_type}, 수량비율: {qty_per}%")
        
        # 전략 조회
        strategy = Strategy.query.filter_by(group_name=group_name, is_active=True).first()
        if not strategy:
            raise TradingError(f"활성 전략을 찾을 수 없습니다: {group_name}")
        
        logger.info(f"전략 조회 성공 - ID: {strategy.id}, 이름: {strategy.name}, 마켓타입: {strategy.market_type}")
        
        # 전략에 연결된 계좌들 조회
        strategy_accounts = strategy.strategy_accounts
        if not strategy_accounts:
            raise TradingError(f"전략에 연결된 계좌가 없습니다: {group_name}")
        
        logger.info(f"전략에 연결된 계좌 수: {len(strategy_accounts)}")
        
        # 🆕 계좌 필터링 및 병렬 처리를 위한 준비
        filtered_accounts = []
        inactive_accounts = []
        exchange_mismatch_accounts = []
        
        for sa in strategy_accounts:
            account = sa.account
            
            # 전략-계좌 링크 비활성화 시 스킵 (공개->비공개 전환 등)
            if hasattr(sa, 'is_active') and not sa.is_active:
                logger.debug(f"전략 링크 비활성화로 제외 - StrategyAccount {sa.id}")
                continue
            # 계좌 존재 및 활성화 상태 확인
            if not account:
                logger.warning(f"전략계좌 {sa.id}: 연결된 계좌가 없음")
                continue
                
            if not account.is_active:
                inactive_accounts.append(f"계좌 {account.id}({account.name})")
                logger.debug(f"계좌 {account.id}({account.name}): 비활성화 상태로 제외")
                continue
            
            # 거래소 필터링 (대소문자 구분 없이 비교)
            if account.exchange.upper() != exchange.upper():
                exchange_mismatch_accounts.append(f"계좌 {account.id}({account.name}): {account.exchange}")
                logger.debug(f"계좌 {account.id}({account.name}): 거래소 불일치 (계좌: {account.exchange}, 웹훅: {exchange})")
                continue
            
            # 필터링을 통과한 계좌
            filtered_accounts.append((strategy, account, sa))
        
        # 필터링 결과 요약 로깅
        filtered_account_names = [f"계좌 {account.id}({account.name})" for _, account, _ in filtered_accounts]
        logger.info(f"계좌 필터링 결과 요약:")
        logger.info(f"  - 총 연결된 계좌: {len(strategy_accounts)}")
        logger.info(f"  - 거래 실행 대상 계좌: {len(filtered_accounts)} {filtered_account_names}")
        if inactive_accounts:
            logger.warning(f"  - 비활성화된 계좌: {len(inactive_accounts)} {inactive_accounts}")
        if exchange_mismatch_accounts:
            logger.warning(f"  - 거래소 불일치 계좌: {len(exchange_mismatch_accounts)} {exchange_mismatch_accounts}")
        
        # 🆕 병렬 거래 실행
        results = []
        if filtered_accounts:
            logger.info(f"🚀 {len(filtered_accounts)}개 계좌에서 병렬 거래 실행 시작")
            results = self._execute_trades_parallel(
                filtered_accounts, symbol, side, order_type, price, qty_per, currency, market_type
            )
        
        # 결과 분석
        successful_trades = [r for r in results if r.get('success', False)]
        failed_trades = [r for r in results if not r.get('success', False)]
        
        if not results:
            logger.error(f"❌ 거래 신호 처리 실패 - 실행된 거래가 없음 (전략: {group_name})")
            logger.error(f"   가능한 원인: 활성 계좌 없음, 거래소 불일치, 모든 계좌에서 오류 발생")
        else:
            logger.info(f"✅ 거래 신호 처리 완료 - 성공: {len(successful_trades)}, 실패: {len(failed_trades)}")
            if failed_trades:
                logger.warning(f"실패한 거래들:")
                for failed in failed_trades:
                    logger.warning(f"  - 계좌 {failed.get('account_id')}({failed.get('account_name')}): {failed.get('error')}")
        
        return {
            'action': 'trading_signal',
            'strategy': group_name,
            'signal': {
                'symbol': symbol,
                'side': side,
                'order_type': order_type,
                'qty_per': qty_per
            },
            'results': results,
            'summary': {
                'total_accounts': len(strategy_accounts),
                'executed_accounts': len(filtered_accounts),
                'successful_trades': len(successful_trades),
                'failed_trades': len(failed_trades),
                'inactive_accounts': len(inactive_accounts),
                'exchange_mismatch_accounts': len(exchange_mismatch_accounts)
            }
        }
    
    def _execute_trades_parallel(self, filtered_accounts: List[tuple], symbol: str, 
                                side: str, order_type: str, price: Optional[Decimal], 
                                qty_per: Decimal, currency: str, market_type: str) -> List[Dict[str, Any]]:
        """🆕 병렬로 여러 계좌에서 거래 실행"""
        results = []
        
        # 🔧 Flask 애플리케이션 인스턴스 가져오기
        from flask import current_app
        app = current_app._get_current_object()
        
        # 병렬 처리를 위한 최대 스레드 수 (계좌 수와 4 중 작은 값)
        max_workers = min(len(filtered_accounts), 4)
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 각 계좌별로 거래 실행 작업 제출
            future_to_account = {
                executor.submit(
                    self._execute_single_trade_safe, 
                    app, strategy, account, sa, symbol, side, order_type, price, qty_per, currency, market_type
                ): (strategy, account, sa) 
                for strategy, account, sa in filtered_accounts
            }
            
            # 완료된 작업들 수집
            for future in as_completed(future_to_account):
                strategy, account, sa = future_to_account[future]
                try:
                    result = future.result()
                    results.append(result)
                    
                    if result.get('success', False):
                        logger.info(f"✅ 계좌 {account.id}({account.name}) 병렬 거래 완료 - 주문ID: {result.get('order_id')}")
                    else:
                        logger.error(f"❌ 계좌 {account.id}({account.name}) 병렬 거래 실패: {result.get('error')}")
                        
                except Exception as e:
                    error_msg = str(e)
                    logger.error(f"❌ 계좌 {account.id}({account.name}) 병렬 거래 실행 중 예외 발생: {error_msg}")
                    results.append({
                        'account_id': account.id,
                        'account_name': account.name,
                        'exchange': account.exchange,
                        'error': f"병렬 실행 실패: {error_msg}",
                        'success': False
                    })
        
        logger.info(f"🏁 병렬 거래 실행 완료 - 총 {len(results)}개 결과")
        return results
    
    def _execute_single_trade_safe(self, app, strategy: Strategy, account: Account, sa: StrategyAccount,
                                  symbol: str, side: str, order_type: str, price: Optional[Decimal], 
                                  qty_per: Decimal, currency: str, market_type: str) -> Dict[str, Any]:
        """개별 거래 실행 (독립적 트랜잭션 관리)"""
        # 🔧 Flask 애플리케이션 컨텍스트 설정
        with app.app_context():
            # 독립적 세션 생성 (병렬 처리를 위해 필요)
            session = self.SessionLocal()
            
            try:
                logger.info(f"🔄 계좌 {account.id}({account.name}) 병렬 거래 시작 - 스레드: {threading.current_thread().name}")
                
                # 독립적 세션을 사용하여 거래 실행
                result = self._execute_trade_with_session(
                    session, strategy, account, sa, symbol, side, order_type, price, qty_per, currency, market_type
                )
                
                if result.get('success'):
                    # 성공시 해당 계좌의 트랜잭션만 commit
                    session.commit()
                    logger.info(f"✅ 계좌 {account.id}({account.name}) 거래 성공 및 커밋 완료")
                else:
                    # 실패시 해당 계좌의 트랜잭션만 rollback
                    session.rollback()
                    logger.warning(f"❌ 계좌 {account.id}({account.name}) 거래 실패 후 롤백")
                
                # 실패/성공 결과에 따른 텔레그램 알림 처리 (계좌 소유자 대상)
                try:
                    from app.services.telegram_service import telegram_service
                    # 실패 알림: 스킵된 경우는 알림 제외
                    if not result.get('success') and not result.get('skipped'):
                        user = account.user
                        if getattr(user, 'telegram_id', None):
                            context = {
                                '전략': strategy.name,
                                '계좌': account.name,
                                '거래소': account.exchange,
                                '심볼': result.get('symbol') or symbol,
                                '사이드': result.get('side') or side,
                                '주문타입': result.get('order_type') or order_type,
                            }
                            telegram_service.send_user_notification(
                                user_telegram_id=user.telegram_id,
                                title='거래 실패',
                                message=result.get('error', '원인 불명 오류'),
                                context=context,
                                user_telegram_bot_token=getattr(user, 'telegram_bot_token', None)
                            )
                except Exception:
                    # 알림 실패는 거래 흐름에 영향 주지 않음
                    pass

                return result
                
            except Exception as e:
                # 예외 발생시 해당 계좌의 트랜잭션만 rollback
                session.rollback()
                error_msg = str(e)
                logger.error(f"계좌 {account.id}({account.name}) 거래 실행 실패 후 롤백: {error_msg}")
                logger.error(f"거래 실행 실패 상세 정보 - 전략: {strategy.name}, 심볼: {symbol}, "
                            f"사이드: {side}, 주문타입: {order_type}, 가격: {price}, 수량비율: {qty_per}%")
                
                # 시장가 주문 실패의 경우 추가 로깅
                if order_type == OrderType.MARKET:
                    logger.error(f"🚨 MARKET 주문 완전 실패 - 포지션 업데이트 없음, SSE 이벤트 없음")
                return {
                    'account_id': account.id,
                    'account_name': account.name,
                    'exchange': account.exchange,
                    'error': error_msg,
                    'success': False
                }
            finally:
                session.close()
    
    def _execute_trade_with_session(self, session, strategy: Strategy, account: Account, sa: StrategyAccount,
                                   symbol: str, side: str, order_type: str, price: Optional[Decimal], 
                                   qty_per: Decimal, currency: str, market_type: str) -> Dict[str, Any]:
        """🆕 세션을 사용하여 개별 계좌에서 거래 실행 (기존 execute_trade 로직)"""
        
        # 1. 할당 자본 조회
        capital_allocation = session.query(StrategyCapital).filter_by(
            strategy_account_id=sa.id
        ).first()
        
        if not capital_allocation:
            raise TradingError(f"자본 할당 정보가 없습니다 - 전략: {strategy.name}, 계좌: {account.id}")
        
        allocated_capital = to_decimal(capital_allocation.allocated_capital)
        
        # 2. 현재 포지션 조회
        position = session.query(StrategyPosition).filter_by(
            strategy_account_id=sa.id,
            symbol=symbol
        ).first()
        
        if not position:
            # 새 포지션 생성
            position = StrategyPosition(
                strategy_account_id=sa.id,
                symbol=symbol,
                quantity=0,
                entry_price=0
            )
            session.add(position)
            session.flush()
        
        # 현재 포지션을 Decimal로 변환
        current_position_qty = to_decimal(position.quantity)
        current_entry_price = to_decimal(position.entry_price)
        
        # 🆕 진입/청산 여부 계산 (utils 함수 사용)
        is_entry = calculate_is_entry(current_position_qty, side)
        
        logger.info(f"거래 유형 분석 - 현재 포지션: {current_position_qty}, 거래: {side}, "
                   f"진입/청산: {'진입' if is_entry else '청산'}")
        
        # 🆕 최대 보유 심볼 수 제한 체크
        if sa.max_symbols is not None and qty_per != Decimal('-1'):
            # 현재 보유 중인 고유 심볼 수 계산 (수량이 0이 아닌 포지션만)
            current_distinct_symbols_count = session.query(StrategyPosition)\
                .filter(
                    StrategyPosition.strategy_account_id == sa.id,
                    StrategyPosition.quantity != 0
                ).count()
            
            # 현재 주문 심볼이 이미 보유 중인 심볼인지 확인
            is_existing_symbol_position = current_position_qty != 0
            
            # 신규 심볼 진입 주문이고 최대 심볼 수에 도달한 경우
            if not is_existing_symbol_position and current_distinct_symbols_count >= sa.max_symbols:
                logger.warning(f"❌ 최대 보유 심볼 수 제한 도달 - 계좌: {account.id}({account.name}), "
                              f"심볼: {symbol}, 현재 보유: {current_distinct_symbols_count}, "
                              f"최대 허용: {sa.max_symbols}")
                
                return {
                    'account_id': account.id,
                    'account_name': account.name,
                    'exchange': account.exchange,
                    'symbol': symbol,
                    'side': side,
                    'error': f"최대 보유 심볼 수 제한 도달 ({current_distinct_symbols_count}/{sa.max_symbols})",
                    'success': False,
                    'skipped': True,
                    'skip_reason': 'max_symbols_limit_reached',
                    'current_symbols_count': current_distinct_symbols_count,
                    'max_symbols_limit': sa.max_symbols
                }
            
            logger.info(f"심볼 수 제한 체크 통과 - 계좌: {account.id}({account.name}), "
                       f"심볼: {symbol}, 현재 보유: {current_distinct_symbols_count}/{sa.max_symbols}, "
                       f"기존 포지션: {is_existing_symbol_position}")
        
        # 3. 주문 수량 계산
        leverage = to_decimal(sa.leverage)  # 레버리지를 Decimal로 변환
        
        if qty_per == Decimal('-1'):
            # 전체 청산 처리
            if side == 'SELL' and current_position_qty > 0:
                # 롱 포지션 전체 청산
                quantity = abs(current_position_qty)
            elif side == 'BUY' and current_position_qty < 0:
                # 숏 포지션 전체 청산
                quantity = abs(current_position_qty)
            else:
                raise TradingError(f"청산할 포지션이 없습니다. 현재 포지션: {current_position_qty}")
        elif side == 'BUY':
            # 롱 포지션 진입/추가
            target_value = allocated_capital * (qty_per / Decimal('100')) * leverage
            current_ticker = exchange_service.get_ticker(account, symbol)
            current_price = to_decimal(current_ticker['last'])
            quantity = target_value / current_price
        elif side == 'SELL':
            # 숏 포지션 진입 또는 롱 포지션 청산
            if current_position_qty > 0:
                # 롱 포지션 부분 청산
                quantity = abs(current_position_qty) * (qty_per / Decimal('100'))
            else:
                # 숏 포지션 진입
                target_value = allocated_capital * (qty_per / Decimal('100')) * leverage
                current_ticker = exchange_service.get_ticker(account, symbol)
                current_price = to_decimal(current_ticker['last'])
                quantity = target_value / current_price
        else:
            raise TradingError(f"지원하지 않는 사이드: {side}")
        
        # 🆕 마켓 타입 로깅 강화
        logger.info(f"주문 실행 준비 - 계좌: {account.id}({account.name}), 심볼: {symbol}, "
                   f"마켓타입: {market_type}, 사이드: {side}, 계산된 수량: {quantity}")
        
        # 4. 주문 파라미터 전처리 및 최소 주문 금액 검증
        try:
            # 🆕 성능 측정 시작
            precision_start_time = time.perf_counter()
            
            # 🆕 최적화된 precision 처리 사용 (95% API 호출 감소) + 자동 조정
            result = exchange_service.preprocess_order_params_optimized(
                account=account,
                symbol=symbol,
                amount=decimal_to_float(quantity),
                price=decimal_to_float(price) if price else None,
                market_type=market_type
            )
            
            # 반환값 언패킹 (3개 값: amount, price, adjustment_info)
            if len(result) == 3:
                preprocessed_amount, preprocessed_price, adjustment_info = result
            else:
                # 이전 버전 호환성 (2개 값만 반환하는 경우)
                preprocessed_amount, preprocessed_price = result
                adjustment_info = None
            
            # 🆕 성능 측정 완료
            precision_end_time = time.perf_counter()
            precision_duration = precision_end_time - precision_start_time
            
            # 전처리된 값을 Decimal로 변환
            final_quantity = Decimal(str(preprocessed_amount))
            final_price = Decimal(str(preprocessed_price)) if preprocessed_price else price
            
            # 전처리 결과 로깅 (성능 정보 포함)
            if abs(final_quantity - quantity) > Decimal('0.00000001'):
                logger.info(f"주문 수량 최적화 전처리 - 계산값: {quantity}, 전처리 후: {final_quantity} (처리시간: {precision_duration:.3f}초)")
            if price and final_price and abs(final_price - price) > Decimal('0.00000001'):
                logger.info(f"주문 가격 최적화 전처리 - 원래값: {price}, 전처리 후: {final_price} (처리시간: {precision_duration:.3f}초)")
            
            # 🆕 성능 로깅 (1초 이상 걸린 경우 경고)
            if precision_duration > 1.0:
                logger.warning(f"⚠️ Precision 처리 시간 지연 - {precision_duration:.3f}초 (계좌: {account.id}, 심볼: {symbol})")
            elif precision_duration > 0.1:
                logger.info(f"📊 Precision 처리 시간 - {precision_duration:.3f}초 (계좌: {account.id}, 심볼: {symbol})")
            else:
                logger.debug(f"⚡ Precision 처리 최적화 성공 - {precision_duration:.3f}초 (계좌: {account.id}, 심볼: {symbol})")
            
            # 🆕 수량 자동 조정된 경우 텔레그램 알림
            if adjustment_info and adjustment_info.get('was_adjusted'):
                try:
                    from app.services.telegram_service import telegram_service
                    # 사용자 ID 가져오기
                    user_id = account.user_id if hasattr(account, 'user_id') else None
                    if user_id:
                        telegram_service.send_order_adjustment_notification(user_id, adjustment_info)
                        logger.info(f"📱 주문 수량 자동 조정 텔레그램 알림 전송 - 사용자: {user_id}")
                except Exception as te:
                    logger.warning(f"텔레그램 알림 전송 실패: {str(te)}")
                
        except ExchangeError as e:
            # 🆕 최소 주문 금액 미달 등의 경우 주문 중단
            error_msg = str(e)
            logger.warning(f"❌ 주문 중단 (최적화 처리) - 계좌: {account.id}({account.name}), 심볼: {symbol}, "
                          f"사이드: {side}, 이유: {error_msg}")
            logger.warning(f"   계산된 수량: {quantity}, 할당자본: {allocated_capital}, "
                          f"수량비율: {qty_per}%, 레버리지: {leverage}")
            
            return {
                'account_id': account.id,
                'account_name': account.name,
                'exchange': account.exchange,
                'symbol': symbol,
                'side': side,
                'error': f"주문 조건 미달 (최적화): {error_msg}",
                'success': False,
                'skipped': True,  # 🆕 주문이 스킵되었음을 표시
                'skip_reason': error_msg,
                'optimization_used': True  # 🆕 최적화 처리 사용됨을 표시
            }
        except Exception as e:
            logger.warning(f"주문 파라미터 최적화 전처리 실패, 기존 방식으로 fallback: {str(e)}")
            # 🆕 최적화 실패 시 기존 방식으로 fallback (성능 측정 포함)
            try:
                fallback_start_time = time.perf_counter()
                
                preprocessed_amount, preprocessed_price = exchange_service.preprocess_order_params(
                    account=account,
                    symbol=symbol,
                    amount=decimal_to_float(quantity),
                    price=decimal_to_float(price) if price else None,
                    market_type=market_type
                )
                
                fallback_end_time = time.perf_counter()
                fallback_duration = fallback_end_time - fallback_start_time
                
                final_quantity = Decimal(str(preprocessed_amount))
                final_price = Decimal(str(preprocessed_price)) if preprocessed_price else price
                
                logger.info(f"Fallback 전처리 성공 - 심볼: {symbol}, 처리시간: {fallback_duration:.3f}초 (기존방식)")
                
                # 🆕 Fallback 성능 경고 (최적화 대비 느린 경우)
                if fallback_duration > 0.5:
                    logger.warning(f"⚠️ Fallback 처리 지연 - {fallback_duration:.3f}초, 최적화 필요 (계좌: {account.id}, 심볼: {symbol})")
                    
            except Exception as fallback_error:
                logger.warning(f"Fallback 전처리도 실패, 원본 값 사용: {str(fallback_error)}")
                final_quantity = quantity
                final_price = price
        
        # 5. 거래소에 주문 전송 (전처리된 값 사용)
        logger.info(f"거래소 주문 전송 - 마켓타입: {market_type}, 수량: {final_quantity}, 가격: {final_price}")
        
        order_result = exchange_service.create_order(
            account=account,
            symbol=symbol,
            order_type=order_type,
            side=side,
            amount=decimal_to_float(final_quantity),  # 전처리된 수량 사용
            price=decimal_to_float(final_price) if final_price else None,  # 전처리된 가격 사용
            market_type=market_type
        )
        
        # 디버깅을 위한 로깅
        logger.info(f"주문 결과: {order_result}")
        
        order_id = order_result.get('id')
        if not order_id:
            raise TradingError("주문 ID를 받지 못했습니다")
        
        # 6. 체결 정보 처리 (시장가 주문의 경우만 체결 대기)
        filled_info = None
        if order_type == OrderType.MARKET:
            # 시장가 주문의 경우 체결 대기
            try:
                filled_order = exchange_service.wait_for_order_fill(account, order_id, symbol, timeout=30)
                if filled_order.get('status') == 'closed' and filled_order.get('filled', 0) > 0:
                    filled_info = {
                        'filled_quantity': to_decimal(filled_order.get('filled', 0)),
                        'average_price': to_decimal(filled_order.get('average', filled_order.get('price', 0))),
                        'total_cost': to_decimal(filled_order.get('cost', 0)),
                        'fee': filled_order.get('fee', {}),
                        'status': 'FILLED'
                    }
                else:
                    # 체결되지 않은 경우 - 시장가 주문이 체결되지 않는 것은 비정상적 상황
                    logger.warning(f"⚠️ MARKET 주문 미체결 - 주문ID: {order_id}, 심볼: {symbol}, "
                                  f"계좌: {account.id}({account.name}), 주문상태: {filled_order.get('status')}, "
                                  f"체결수량: {filled_order.get('filled', 0)}")
                    filled_info = {
                        'filled_quantity': Decimal('0'),
                        'average_price': final_price if final_price else Decimal('0'),
                        'total_cost': Decimal('0'),
                        'fee': {},
                        'status': 'PENDING'
                    }
            except Exception as e:
                logger.error(f"🚨 MARKET 주문 체결 확인 실패 - 주문ID: {order_id}, 심볼: {symbol}, 계좌: {account.id}({account.name}), 오류: {str(e)}")
                logger.warning(f"시장가 주문 체결 정보 조회 실패: {str(e)}")
                # 체결 정보를 가져오지 못한 경우 전처리된 값 사용
                filled_info = {
                    'filled_quantity': final_quantity,  # 전처리된 수량 사용
                    'average_price': final_price if final_price else Decimal('0'),       # 전처리된 가격 사용
                    'total_cost': final_quantity * (final_price if final_price else Decimal('0')),
                    'fee': order_result.get('fee', {}),
                    'status': 'FILLED'
                }
        else:
            # 지정가 주문의 경우 PENDING 상태로 저장 (전처리된 값 사용)
            filled_info = {
                'filled_quantity': Decimal('0'),
                'average_price': final_price if final_price else Decimal('0'),  # 전처리된 가격 사용
                'total_cost': Decimal('0'),
                'fee': {},
                'status': 'PENDING'
            }
        
        # 7. 수수료 정보 처리
        fee_cost = Decimal('0')
        fee_info = filled_info.get('fee', {})
        if fee_info and isinstance(fee_info, dict):
            fee_cost = to_decimal(fee_info.get('cost', 0))
        
        # 8. 실현 손익 계산 (포지션 청산 시)
        realized_pnl = Decimal('0')
        if filled_info['status'] == 'FILLED' and filled_info['filled_quantity'] > 0:
            if side == 'SELL' and current_position_qty > 0:
                # 롱 포지션 청산
                close_quantity = min(filled_info['filled_quantity'], current_position_qty)
                realized_pnl = close_quantity * (filled_info['average_price'] - current_entry_price)
            elif side == 'BUY' and current_position_qty < 0:
                # 숏 포지션 청산
                close_quantity = min(filled_info['filled_quantity'], abs(current_position_qty))
                realized_pnl = close_quantity * (current_entry_price - filled_info['average_price'])
        
        # 9. 거래 기록 저장 (주문 가격과 체결 가격 구분)
        # 🆕 MARKET 주문이거나 실제 체결된 경우에만 trades 테이블에 추가
        if order_type == OrderType.MARKET or filled_info['status'] == 'FILLED':
            trade = Trade(
                strategy_account_id=sa.id,
                exchange_order_id=order_id,
                symbol=symbol,
                side=side,
                quantity=decimal_to_float(filled_info['filled_quantity']),
                order_price=decimal_to_float(final_price) if final_price else None,  # 주문 가격
                price=decimal_to_float(filled_info['average_price']) if filled_info['average_price'] > 0 else decimal_to_float(final_price) if final_price else 0,  # 체결 가격
                order_type=order_type,
                timestamp=datetime.utcnow(),
                fee=decimal_to_float(fee_cost),
                pnl=decimal_to_float(realized_pnl) if realized_pnl != 0 else None,
                is_entry=is_entry,  # 진입/청산 여부
                market_type=market_type  # 마켓 타입
            )
            session.add(trade)
            logger.info(f"📝 Trade 레코드 생성 - 주문ID: {order_id}, 타입: {order_type}, 상태: {filled_info['status']}")
        else:
            # LIMIT 주문이고 아직 체결되지 않은 경우 trades에 추가하지 않음
            logger.info(f"📋 LIMIT 주문 미체결 - 주문ID: {order_id}, OpenOrder에만 기록")
        
        # 10. 지정가 주문인 경우 미체결 주문 기록 (전처리된 정확한 값 사용)
        if order_type == OrderType.LIMIT:
            # 🆕 중앙화된 OpenOrderManager 사용 (현재 세션 전달)
            from app.services.open_order_service import open_order_manager
            
            open_order = open_order_manager.create_open_order(
                strategy_account_id=sa.id,
                exchange_order_id=order_id,
                symbol=symbol,
                side=side,
                quantity=final_quantity,  # 전처리된 수량 사용
                price=final_price if final_price else Decimal('0'),  # 전처리된 가격 사용
                market_type=market_type,
                order_type=order_type,  # 🔧 주문 타입 전달
                session=session  # 🔧 현재 세션 전달
            )
            
            # 체결 상태에 따라 처리
            if filled_info['status'] == 'FILLED':
                # 즉시 체결된 경우 체결 처리 후 삭제
                if open_order_manager.process_filled_order(open_order, {
                    'filled': decimal_to_float(filled_info['filled_quantity']),
                    'average': decimal_to_float(filled_info['average_price']),
                    'fee': filled_info.get('fee', {})
                }, session):  # 🔧 현재 세션 전달
                    logger.info(f"📋 LIMIT 주문 즉시 체결 및 레코드 삭제 - 주문ID: {order_id}")
                else:
                    logger.info(f"📋 LIMIT 주문 즉시 체결 처리 - 주문ID: {order_id}")
            else:
                logger.info(f"📋 LIMIT 주문 미체결 대기 - 주문ID: {order_id}")
        
        # 11. 포지션 업데이트 (체결된 경우만, 정확한 체결 정보 사용)
        if filled_info['status'] == 'FILLED' and filled_info['filled_quantity'] > 0:
            position_service.update_position(position, side, filled_info['filled_quantity'], filled_info['average_price'])
        
        # 12. 통합 SSE 이벤트 발송 (중앙화)
        self._emit_trading_events(order_type, filled_info, order_id, symbol, side, 
                                final_quantity, final_price, filled_info.get('average_price', Decimal('0')),
                                strategy, account, position)

        # 13. 텔레그램 알림: 체결된 거래만 계좌 소유자에게 전송
        try:
            if filled_info['status'] == 'FILLED' and filled_info['filled_quantity'] > 0:
                from app.services.telegram_service import telegram_service
                user = account.user
                if getattr(user, 'telegram_id', None):
                    filled_qty = filled_info['filled_quantity']
                    avg_price = filled_info.get('average_price', Decimal('0'))
                    msg = f"{symbol} {side} {decimal_to_float(filled_qty)} @ {decimal_to_float(avg_price)}"
                    context = {
                        '전략': strategy.name,
                        '계좌': account.name,
                        '거래소': account.exchange,
                        '마켓': market,
                        '주문ID': order_id,
                        'PnL(실현)': decimal_to_float(realized_pnl) if realized_pnl != 0 else 0
                    }
                    telegram_service.send_user_notification(
                        user_telegram_id=user.telegram_id,
                        title='체결 알림',
                        message=msg,
                        context=context,
                        user_telegram_bot_token=getattr(user, 'telegram_bot_token', None)
                    )
        except Exception:
            # 알림 실패는 무시
            pass
        
        return {
            'account_id': account.id,
            'account_name': account.name,
            'exchange': account.exchange,
            'user_id': account.user_id,  # 🔧 SSE 이벤트를 위한 user_id 추가
            'strategy_id': strategy.id,  # 🔧 SSE 이벤트를 위한 strategy_id 추가
            'order_id': order_id,
            'symbol': symbol,
            'side': side,
            'order_type': order_type,  # 🔧 주문 타입 추가 (webhook_service에서 사용)
            'quantity': decimal_to_float(filled_info['filled_quantity']) if filled_info['status'] == 'FILLED' else decimal_to_float(final_quantity),
            'order_price': decimal_to_float(final_price) if final_price else None,  # 🆕 주문 가격
            'filled_price': decimal_to_float(filled_info['average_price']),  # 🆕 체결 가격
            'status': filled_info['status'],
            'realized_pnl': decimal_to_float(realized_pnl),
            'fee': decimal_to_float(fee_cost),
            'market_type': market_type,  # 🆕 마켓 타입 정보
            'success': True,
            # 전처리 정보 추가
            'preprocessing_info': {
                'calculated_quantity': decimal_to_float(quantity),
                'preprocessed_quantity': decimal_to_float(final_quantity),
                'quantity_adjusted': abs(final_quantity - quantity) > Decimal('0.00000001'),
                'api_calls_saved': True,  # 전처리로 인한 API 호출 절약
                'optimization_used': True,  # 🆕 최적화 사용 여부
                'processing_time_seconds': precision_duration if 'precision_duration' in locals() else 0.0  # 🆕 처리 시간
            }
        }

    def execute_trade(self, strategy: Strategy, account: Account, symbol: str, 
                      side: str, order_type: str, price: Optional[Decimal], 
                      qty_per: Decimal, currency: str, market_type: str) -> Dict[str, Any]:
        """단일 계좌에서 거래 실행 (전달받은 세션 사용)"""
        # StrategyAccount 조회
        strategy_account = StrategyAccount.query.filter_by(
            strategy_id=strategy.id,
            account_id=account.id
        ).first()
        
        if not strategy_account:
            raise TradingError(f"전략-계좌 연결 정보가 없습니다 - 전략: {strategy.name}, 계좌: {account.id}")
        
        # 현재 세션 사용하여 실행 (트랜잭션 경계 유지)
        return self._execute_trade_with_session(
            self.session, strategy, account, strategy_account, symbol, side, order_type, price, qty_per, currency, market_type
        )


# 전역 인스턴스 생성
trading_service = TradingService() 