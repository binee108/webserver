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
from app.constants import MarketType, Exchange, OrderType

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
            
            logger.info(f"웹훅 처리 시작 - 타입: {normalized_data.get('order_type', 'UNKNOWN')}, "
                       f"전략: {normalized_data.get('group_name', 'UNKNOWN')}")
            
            # 웹훅 로그 기록
            webhook_log = WebhookLog(
                payload=str(webhook_data),  # 원본 데이터 기록
                status='processing'
            )
            self.session.add(webhook_log)
            self.session.commit()
            
            # 웹훅 타입 확인
            order_type = normalized_data.get('order_type', '')
            
            if order_type == OrderType.CANCEL_ALL_ORDER:
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
            
            # ✅ SSE 이벤트는 trading_service에서 중앙화 처리됨
            
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
    
    # ⚠️ SSE 이벤트 발송은 trading_service에서 중앙화됨 - 이 메서드는 더 이상 사용하지 않음
    
    def process_cancel_all_orders(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """모든 주문 취소 처리 - order_service를 통해 처리 (선택적 필터링 지원)"""
        group_name = webhook_data.get('group_name')
        exchange = webhook_data.get('exchange')  # 선택적: 특정 거래소만
        market_type = webhook_data.get('market_type')  # 선택적: 특정 마켓타입만 (SPOT/FUTURE)
        currency = webhook_data.get('currency')  # 선택적: 특정 통화만 (향후 확장용)
        symbol = webhook_data.get('symbol')  # 선택적: 특정 심볼만
        
        # market_type 표준화: MarketType.normalize 사용
        if market_type:
            market_type = MarketType.normalize(market_type)
        
        logger.info(f"🔄 주문 취소 처리 시작 - 전략: {group_name}, "
                   f"거래소: {exchange or '전체'}, 마켓타입: {market_type or '전체'}, "
                   f"통화: {currency or '전체'}, 심볼: {symbol or '전체'}")
        
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
        
        # order_service를 통해 계좌별 주문 취소 처리
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
                       f"거래소: {account.exchange}, 마켓: {strategy.market_type}, 활성상태: {account.is_active}")
            
            # 계좌 활성화 상태 확인
            if not account.is_active:
                logger.warning(f"❌ 계좌 {account.id}({account.name}): 비활성화 상태로 제외")
                skipped_count += 1
                continue
            
            # 거래소 필터링
            if exchange and account.exchange.upper() != exchange.upper():
                logger.info(f"⏭️ 계좌 {account.id}({account.name}): 거래소 불일치 - 스킵 "
                           f"(계좌: {account.exchange}, 요청: {exchange})")
                skipped_count += 1
                continue
            
            # 마켓 타입 필터링 - Strategy의 market_type 사용
            strategy_market = strategy.market_type.upper() if strategy.market_type else MarketType.SPOT
                
            if market_type and strategy_market != market_type:
                logger.info(f"⏭️ 계좌 {account.id}({account.name}): 마켓 타입 불일치 - 스킵 "
                           f"(전략: {strategy_market}, 요청: {market_type})")
                skipped_count += 1
                continue
            
            logger.info(f"✅ 계좌 {account.id}({account.name}): 주문 취소 처리 대상")
            processed_count += 1
            
            try:
                # order_service를 통해 주문 취소 (자동으로 OpenOrder 레코드도 처리됨)
                logger.info(f"🔄 계좌 {account.id}: order_service를 통한 주문 취소 요청...")
                cancel_result = order_service.cancel_all_orders(
                    account_id=account.id,
                    symbol=symbol,
                    market_type=strategy.market_type,  # 전략의 마켓 타입 사용
                    exchange=account.exchange  # 거래소 정보도 전달
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
            'market_type': market_type,  # 🆕 마켓 타입 정보 추가
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