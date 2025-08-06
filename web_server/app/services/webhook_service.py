"""
웹훅 처리 서비스 모듈
웹훅 수신, 파싱, 라우팅 등 웹훅 관련 로직
"""

import logging
from typing import Dict, Any
from datetime import datetime

from app import db
from app.models import Strategy, WebhookLog
from app.services.utils import normalize_webhook_data
from app.services.exchange_service import exchange_service

logger = logging.getLogger(__name__)

class WebhookError(Exception):
    """웹훅 관련 오류"""
    pass

class WebhookService:
    """웹훅 서비스 클래스"""
    
    def __init__(self):
        self.session = db.session
    
    def process_webhook(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """웹훅 데이터 처리 메인 함수"""
        try:
            # 웹훅 데이터 표준화 (대소문자 구별 없이 처리)
            normalized_data = normalize_webhook_data(webhook_data)
            
            logger.info(f"웹훅 처리 시작 - 타입: {normalized_data.get('orderType', 'UNKNOWN')}, "
                       f"전략: {normalized_data.get('group_name', 'UNKNOWN')}")
            
            # 웹훅 로그 기록
            webhook_log = WebhookLog(
                payload=str(webhook_data),  # 원본 데이터 기록
                status='processing'
            )
            self.session.add(webhook_log)
            self.session.commit()
            
            # 웹훅 타입 확인
            order_type = normalized_data.get('orderType', '').upper()
            
            if order_type == 'CANCEL_ALL_ORDER':
                result = self.process_cancel_all_orders(normalized_data)
            else:
                # 거래 신호는 trading_service로 위임
                from app.services.trading_service import trading_service
                result = trading_service.process_trading_signal(normalized_data)
                
                # 🆕 거래 신호 처리 결과 분석 및 로깅
                self._analyze_trading_result(result, normalized_data)
            
            # 성공 시 로그 업데이트
            webhook_log.status = 'success'
            webhook_log.message = str(result)
            self.session.commit()
            
            # 🆕 SSE 이벤트 발송 추가
            self._emit_webhook_events(result, normalized_data)
            
            return result
            
        except Exception as e:
            # 실패 시 로그 업데이트
            if 'webhook_log' in locals():
                webhook_log.status = 'failed'
                webhook_log.message = str(e)
                self.session.commit()
            
            logger.error(f"웹훅 처리 실패: {str(e)}")
            raise WebhookError(f"웹훅 처리 실패: {str(e)}")
    
    def _analyze_trading_result(self, result: Dict[str, Any], webhook_data: Dict[str, Any]):
        """거래 신호 처리 결과 분석 및 로깅"""
        try:
            strategy_name = result.get('strategy', 'UNKNOWN')
            results = result.get('results', [])
            summary = result.get('summary', {})
            
            total_accounts = summary.get('total_accounts', 0)
            executed_accounts = summary.get('executed_accounts', 0)
            successful_trades = summary.get('successful_trades', 0)
            failed_trades = summary.get('failed_trades', 0)
            inactive_accounts = summary.get('inactive_accounts', 0)
            exchange_mismatch_accounts = summary.get('exchange_mismatch_accounts', 0)
            
            # 🆕 최대 심볼 수 제한으로 스킵된 건수 집계
            max_symbols_skipped = sum(1 for r in results 
                                    if r.get('skipped') and r.get('skip_reason') == 'max_symbols_limit_reached')
            
            logger.info(f"📊 웹훅 처리 결과 분석 (전략: {strategy_name}):")
            logger.info(f"   총 계좌: {total_accounts}, 실행: {executed_accounts}, 성공: {successful_trades}, 실패: {failed_trades}")
            
            # 🆕 최대 심볼 수 제한 관련 로깅
            if max_symbols_skipped > 0:
                logger.warning(f"⚠️  최대 심볼 수 제한으로 스킵된 주문: {max_symbols_skipped}건")
                for result_item in results:
                    if result_item.get('skip_reason') == 'max_symbols_limit_reached':
                        logger.warning(f"   - 계좌 {result_item.get('account_id')}({result_item.get('account_name')}): "
                                     f"{result_item.get('symbol')} - {result_item.get('current_symbols_count', 0)}/"
                                     f"{result_item.get('max_symbols_limit', 0)}")
            
            # 경고 상황 체크
            if not results:
                logger.error(f"🚨 웹훅 처리 심각한 문제 - 어떤 계좌에서도 거래가 실행되지 않음!")
                logger.error(f"   전략: {strategy_name}")
                logger.error(f"   웹훅 데이터: {webhook_data}")
                logger.error(f"   비활성 계좌: {inactive_accounts}, 거래소 불일치: {exchange_mismatch_accounts}")
                
            elif successful_trades == 0:
                logger.error(f"🚨 웹훅 처리 문제 - 모든 거래가 실패함!")
                logger.error(f"   전략: {strategy_name}, 실패한 거래 수: {failed_trades}")
                for result_item in results:
                    if not result_item.get('success', False):
                        logger.error(f"   실패 상세: 계좌 {result_item.get('account_id')} - {result_item.get('error')}")
                        
            elif failed_trades > 0:
                logger.warning(f"⚠️  일부 거래 실패 - 성공: {successful_trades}, 실패: {failed_trades}")
                
            else:
                logger.info(f"✅ 모든 거래 성공 - {successful_trades}개 계좌에서 거래 완료")
                
        except Exception as e:
            logger.error(f"거래 결과 분석 중 오류: {str(e)}")
    
    def _emit_webhook_events(self, result: Dict[str, Any], webhook_data: Dict[str, Any]):
        """웹훅 처리 결과를 바탕으로 SSE 이벤트 발송"""
        try:
            from app.services.event_service import event_service, OrderEvent, PositionEvent
            from datetime import datetime
            
            action = result.get('action', '')
            strategy = result.get('strategy', 'UNKNOWN')
            results = result.get('results', [])
            
            logger.debug(f"SSE 이벤트 발송 시작 - 액션: {action}, 전략: {strategy}, 결과 수: {len(results)}")
            
            # 거래 신호 처리 결과에서 이벤트 생성
            if action == 'trading_signal':
                for result_item in results:
                    if result_item.get('success', False):
                        # trading_service 결과에서 user_id 직접 추출 (수정됨)
                        user_id = result_item.get('user_id')
                        if not user_id:
                            # user_id가 없는 경우, strategy_id로부터 추출
                            strategy_id = result_item.get('strategy_id')
                            if strategy_id:
                                from app.models import Strategy
                                strategy = Strategy.query.get(strategy_id)
                                if strategy:
                                    user_id = strategy.user_id
                        
                        if not user_id:
                            logger.warning(f"⚠️ 사용자 ID를 찾을 수 없음 - 결과: {result_item}")
                            continue
                            
                        # LIMIT 주문만 SSE 이벤트 발송 (시장가 주문은 즉시 체결되므로 제외)
                        order_type = result_item.get('order_type', 'LIMIT')  # 기본값은 LIMIT
                        if order_type.upper() == 'LIMIT':
                            # 주문 이벤트 생성
                            order_event = OrderEvent(
                                event_type='order_created',
                                order_id=result_item.get('order_id', 'webhook_generated'),
                                symbol=result_item.get('symbol', ''),
                                strategy_id=result_item.get('strategy_id', 0),
                                user_id=user_id,
                                side=result_item.get('side', ''),
                                quantity=float(result_item.get('quantity', 0)),
                                price=float(result_item.get('price', 0)),
                                status='filled' if result_item.get('filled') else 'created',
                                timestamp=datetime.utcnow().isoformat(),
                                # 계좌 정보 추가
                                account_id=result_item.get('account_id', 0),
                                account_name=result_item.get('account_name', ''),
                                exchange=result_item.get('exchange', '')
                            )
                            
                            event_service.emit_order_event(order_event)
                            logger.info(f"📤 LIMIT 주문 SSE 이벤트 발송: 사용자 {user_id}, 심볼 {result_item.get('symbol')}")
                        else:
                            logger.info(f"📈 MARKET 주문은 SSE 이벤트 생략: 사용자 {user_id}, 심볼 {result_item.get('symbol')} (즉시 포지션 반영 예정)")
                        
                        # 포지션 변경이 있는 경우 포지션 이벤트도 생성
                        if result_item.get('position_updated'):
                            position_event = PositionEvent(
                                event_type='position_updated',
                                position_id=result_item.get('position_id', 0),
                                symbol=result_item.get('symbol', ''),
                                strategy_id=result_item.get('strategy_id', 0),
                                user_id=user_id,
                                quantity=float(result_item.get('position_quantity', 0)),
                                entry_price=float(result_item.get('entry_price', 0)),
                                timestamp=datetime.utcnow().isoformat()
                            )
                            
                            event_service.emit_position_event(position_event)
                            logger.info(f"📤 포지션 SSE 이벤트 발송: 사용자 {user_id}, 심볼 {result_item.get('symbol')}")
            
            elif action == 'cancel_all_orders':
                # 주문 취소 이벤트 처리
                for result_item in results:
                    if result_item.get('success', False):
                        user_id = result_item.get('user_id')
                        if not user_id:
                            # strategy_id로부터 user_id 추출
                            strategy_id = result_item.get('strategy_id')  
                            if strategy_id:
                                from app.models import Strategy
                                strategy = Strategy.query.get(strategy_id)
                                if strategy:
                                    user_id = strategy.user_id
                        
                        if not user_id:
                            logger.warning(f"⚠️ 주문 취소 이벤트: 사용자 ID를 찾을 수 없음")
                            continue
                            
                        cancelled_orders = result_item.get('cancelled_order_details', [])
                        for cancelled_order in cancelled_orders:
                            order_event = OrderEvent(
                                event_type='order_cancelled',
                                order_id=cancelled_order.get('order_id', 'webhook_cancelled'),
                                symbol=cancelled_order.get('symbol', ''),
                                strategy_id=result_item.get('strategy_id', 0),
                                user_id=user_id,
                                side=cancelled_order.get('side', ''),
                                quantity=float(cancelled_order.get('quantity', 0)),
                                price=float(cancelled_order.get('price', 0)),
                                status='cancelled',
                                timestamp=datetime.utcnow().isoformat()
                            )
                            
                            event_service.emit_order_event(order_event)
                            logger.info(f"📤 주문 취소 SSE 이벤트 발송: 사용자 {user_id}, 주문ID {cancelled_order.get('order_id')}")
            
            logger.info(f"✅ 웹훅 SSE 이벤트 발송 완료 - 전략: {strategy}, 액션: {action}")
            
        except Exception as e:
            logger.error(f"웹훅 SSE 이벤트 발송 실패: {str(e)}")
    
    def process_cancel_all_orders(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """모든 주문 취소 처리 - order_service를 통해 처리"""
        group_name = webhook_data.get('group_name')
        exchange = webhook_data.get('exchange')
        symbol = webhook_data.get('symbol')
        market = webhook_data.get('market', 'spot')  # 🆕 웹훅에서 market 타입 추출, 기본값 'spot'
        
        logger.info(f"🔄 주문 취소 처리 시작 - 전략: {group_name}, 거래소: {exchange}, 심볼: {symbol}, 마켓: {market}")
        
        if not group_name:
            raise WebhookError("group_name이 필요합니다")
        
        # 전략 조회
        strategy = Strategy.query.filter_by(group_name=group_name, is_active=True).first()
        if not strategy:
            raise WebhookError(f"활성 전략을 찾을 수 없습니다: {group_name}")
        
        logger.info(f"✅ 전략 조회 성공 - ID: {strategy.id}, 이름: {strategy.name}")
        
        # 전략에 연결된 계좌들 조회
        strategy_accounts = strategy.strategy_accounts
        if not strategy_accounts:
            raise WebhookError(f"전략에 연결된 계좌가 없습니다: {group_name}")
        
        logger.info(f"📋 전략에 연결된 계좌 수: {len(strategy_accounts)}")
        
        # 🆕 order_service를 통해 계좌별 주문 취소 처리
        from app.services.order_service import order_service
        
        results = []
        processed_count = 0
        skipped_count = 0
        
        for idx, sa in enumerate(strategy_accounts):
            account = sa.account
            logger.debug(f"[{idx+1}/{len(strategy_accounts)}] 계좌 처리 중 - StrategyAccount ID: {sa.id}")
            
            # 계좌 존재 여부 확인
            if not account:
                logger.warning(f"❌ StrategyAccount {sa.id}: 연결된 계좌가 없음")
                skipped_count += 1
                continue
            
            logger.info(f"🏦 계좌 정보 - ID: {account.id}, 이름: {account.name}, "
                       f"거래소: {account.exchange}, 활성상태: {account.is_active}")
            
            # 계좌 활성화 상태 확인
            if not account.is_active:
                logger.warning(f"❌ 계좌 {account.id}({account.name}): 비활성화 상태로 제외")
                skipped_count += 1
                continue
            
            # 거래소 필터링
            if exchange and account.exchange.upper() != exchange.upper():
                logger.warning(f"❌ 계좌 {account.id}({account.name}): 거래소 불일치 "
                              f"(계좌: {account.exchange}, 요청: {exchange})")
                skipped_count += 1
                continue
            
            logger.info(f"✅ 계좌 {account.id}({account.name}): 주문 취소 처리 대상")
            processed_count += 1
            
            try:
                # 🆕 order_service를 통해 주문 취소 (자동으로 OpenOrder 레코드도 처리됨)
                logger.info(f"🔄 계좌 {account.id}: order_service를 통한 주문 취소 요청...")
                cancel_result = order_service.cancel_all_orders(
                    account_id=account.id,
                    symbol=symbol,
                    market_type=market
                )
                
                if cancel_result['success']:
                    cancelled_orders = cancel_result.get('cancelled_orders', [])
                    failed_orders = cancel_result.get('failed_orders', [])
                    
                    logger.info(f"✅ 계좌 {account.id}({account.name}) 주문 취소 완료 - "
                               f"성공: {len(cancelled_orders)}개, 실패: {len(failed_orders)}개")
                    
                    results.append({
                        'account_id': account.id,
                        'account_name': account.name,
                        'exchange': account.exchange,
                        'cancelled_orders': len(cancelled_orders),
                        'failed_orders': len(failed_orders),
                        'cancelled_order_details': cancelled_orders,
                        'failed_order_details': failed_orders,
                        'success': True,
                        'message': cancel_result.get('message', '주문 취소 완료')
                    })
                else:
                    error_msg = cancel_result.get('error', '알 수 없는 오류')
                    logger.error(f"❌ 계좌 {account.id}({account.name}) 주문 취소 실패: {error_msg}")
                    results.append({
                        'account_id': account.id,
                        'account_name': account.name,
                        'exchange': account.exchange,
                        'error': error_msg,
                        'success': False
                    })
                
            except Exception as e:
                error_msg = str(e)
                logger.error(f"❌ 계좌 {account.id}({account.name}) 주문 취소 처리 중 예외 발생: {error_msg}")
                results.append({
                    'account_id': account.id,
                    'account_name': account.name,
                    'exchange': account.exchange,
                    'error': f"처리 중 예외: {error_msg}",
                    'success': False
                })
        
        # 요약 로깅
        successful_results = [r for r in results if r.get('success', False)]
        failed_results = [r for r in results if not r.get('success', False)]
        
        logger.info(f"📊 주문 취소 처리 완료 요약:")
        logger.info(f"   총 연결 계좌: {len(strategy_accounts)}")
        logger.info(f"   처리 대상: {processed_count}")
        logger.info(f"   제외됨: {skipped_count}")
        logger.info(f"   성공: {len(successful_results)}")
        logger.info(f"   실패: {len(failed_results)}")
        
        if successful_results:
            total_cancelled = sum(r.get('cancelled_orders', 0) for r in successful_results)
            total_failed = sum(r.get('failed_orders', 0) for r in successful_results)
            logger.info(f"   총 취소된 주문: {total_cancelled}개 (실패: {total_failed}개)")
        
        if skipped_count > 0:
            logger.warning(f"⚠️  {skipped_count}개 계좌가 제외되었습니다. 비활성화 또는 거래소 불일치를 확인하세요.")
        
        return {
            'action': 'cancel_all_orders',
            'strategy': group_name,
            'market_type': market,  # 🆕 마켓 타입 정보 추가
            'results': results,
            'summary': {
                'total_accounts': len(strategy_accounts),
                'processed_accounts': processed_count,
                'skipped_accounts': skipped_count,
                'successful_accounts': len(successful_results),
                'failed_accounts': len(failed_results),
                'total_cancelled_orders': sum(r.get('cancelled_orders', 0) for r in successful_results),
                'total_failed_orders': sum(r.get('failed_orders', 0) for r in successful_results)
            }
        }

# 전역 인스턴스
webhook_service = WebhookService() 