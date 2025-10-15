# @FEAT:webhook-order @COMP:service @TYPE:core @DEPS:trading,order-tracking,telegram-notification
"""
웹훅 처리 서비스 모듈

이 모듈은 외부 웹훅 요청(TradingView 등)을 수신하여 검증, 라우팅, 처리하는 핵심 로직을 담당합니다.
"""

import logging
import time
from typing import Dict, Any, Optional
from datetime import datetime

from app import db
from app.models import Strategy, WebhookLog
from app.services.utils import normalize_webhook_data
from app.services.exchange import exchange_service
from app.constants import MarketType, Exchange, OrderType
from app.utils.logging_security import get_secure_logger

logger = get_secure_logger(__name__)

# @FEAT:webhook-order @FEAT:event-sse @FEAT:securities-integration @COMP:model @TYPE:core
class WebhookError(Exception):
    """웹훅 관련 오류"""
    pass

# @FEAT:webhook-order @COMP:service @TYPE:core
class WebhookService:
    """웹훅 서비스 클래스 - 웹훅 처리 오케스트레이터"""

    def __init__(self):
        self.session = db.session

    # @FEAT:webhook-order @COMP:validation @TYPE:validation
    def _validate_order_type_params(self, normalized_data: Dict[str, Any]) -> None:
        """주문 타입별 필수 파라미터 검증 (단일 소스)

        Args:
            normalized_data: 정규화된 웹훅 데이터

        Raises:
            WebhookError: 필수 파라미터 누락 시
        """
        order_type = normalized_data.get('order_type', '')

        # STOP 주문 타입 검증
        if OrderType.requires_stop_price(order_type):
            if not normalized_data.get('stop_price'):
                raise WebhookError(f"{order_type} 주문에는 stop_price가 필수입니다")
            logger.info(f"✅ {order_type} 주문 stop_price 검증 완료: {normalized_data.get('stop_price')}")

        # LIMIT 주문 타입 검증
        if OrderType.requires_price(order_type):
            if not normalized_data.get('price'):
                raise WebhookError(f"{order_type} 주문에는 price가 필수입니다")
            logger.info(f"✅ {order_type} 주문 price 검증 완료: {normalized_data.get('price')}")

        # MARKET 주문은 price나 stop_price 불필요
        if order_type == OrderType.MARKET:
            if normalized_data.get('stop_price'):
                logger.warning(f"⚠️ MARKET 주문에서 stop_price는 무시됩니다: {normalized_data.get('stop_price')}")
                normalized_data.pop('stop_price', None)
            if normalized_data.get('price'):
                logger.warning(f"⚠️ MARKET 주문에서 price는 무시됩니다: {normalized_data.get('price')}")
                normalized_data.pop('price', None)

    # @FEAT:webhook-order @COMP:validation @TYPE:validation
    def _validate_strategy_token(self, group_name: str, token: str) -> Strategy:
        """전략 조회 및 토큰 검증 (단일 소스)

        Args:
            group_name: 전략 그룹명
            token: 웹훅 토큰

        Returns:
            Strategy: 검증된 전략 객체

        Raises:
            WebhookError: 전략을 찾을 수 없거나 토큰이 유효하지 않은 경우
        """
        strategy = Strategy.query.filter_by(group_name=group_name, is_active=True).first()
        if not strategy:
            raise WebhookError(f"활성 전략을 찾을 수 없습니다: {group_name}")

        if not token:
            raise WebhookError("웹훅 토큰이 필요합니다")

        # 허용되는 토큰 집합 구성
        valid_tokens = set()
        owner = strategy.user
        if owner and getattr(owner, 'webhook_token', None):
            valid_tokens.add(owner.webhook_token)

        # 공개 전략의 경우: 전략을 구독(연결)한 사용자들의 토큰도 허용
        if getattr(strategy, 'is_public', False):
            try:
                for sa in strategy.strategy_accounts:
                    # 전략-계좌 링크 활성 + 계좌/사용자/토큰 존재 시 수집
                    if getattr(sa, 'is_active', True) and getattr(sa, 'account', None):
                        account_user = getattr(sa.account, 'user', None)
                        user_token = getattr(account_user, 'webhook_token', None) if account_user else None
                        if user_token:
                            valid_tokens.add(user_token)
            except Exception:
                # 토큰 수집 실패는 검증 흐름에 영향 주지 않음
                pass

        if not valid_tokens:
            raise WebhookError("웹훅 토큰이 설정된 사용자가 없습니다. 전략 소유자 또는 구독자의 토큰을 생성하세요")

        if token not in valid_tokens:
            raise WebhookError("웹훅 토큰이 유효하지 않습니다")

        return strategy

    # @FEAT:webhook-order @COMP:service @TYPE:core
    def process_webhook(self, webhook_data: Dict[str, Any], webhook_received_at: Optional[float] = None) -> Dict[str, Any]:
        """웹훅 데이터 처리 메인 함수"""
        # 웹훅 수신 시간 기록 (표준화된 변수명)
        if webhook_received_at is None:
            webhook_received_at = time.time()
        # 하위 호환성을 위한 기존 변수명 유지
        webhook_start_time = webhook_received_at

        try:
            # 웹훅 데이터 표준화 (대소문자 구별 없이 처리)
            normalized_data = normalize_webhook_data(webhook_data)

            # 검증 완료 시점 기록
            webhook_validated_at = time.time()

            logger.info(f"웹훅 처리 시작 - 타입: {normalized_data.get('order_type', 'UNKNOWN')}, "
                       f"전략: {normalized_data.get('group_name', 'UNKNOWN')}")

            # 웹훅 로그 기록 (타이밍 정보 포함)
            webhook_log = WebhookLog(
                payload=str(webhook_data),  # 원본 데이터 기록
                status='processing',
                webhook_received_at=webhook_received_at  # 수신 시점 저장
            )
            self.session.add(webhook_log)
            self.session.commit()

            # 전략 정보 초기 추출
            group_name = normalized_data.get('group_name')
            token = normalized_data.get('token')
            if not group_name:
                raise WebhookError("group_name이 필요합니다")

            # 🧪 테스트 모드 검증 우회
            test_mode = normalized_data.get("test_mode", False)
            if test_mode:
                logger.info("🧪 테스트 모드: 전략 및 토큰 검증 우회")
                # @FEAT:webhook-order @FEAT:event-sse @FEAT:securities-integration @COMP:model @TYPE:helper
                # 테스트용 가상 전략 객체 생성
                class TestStrategy:
                    def __init__(self):
                        self.id = normalized_data.get("strategy_id", 999)
                        self.name = f"test_strategy_{self.id}"
                        self.group_name = group_name
                        self.is_active = True
                        self.user = None
                strategy = TestStrategy()
                # 바로 거래 처리로 이동
                # 거래 신호는 trading_service로 위임
                from app.services.trading import trading_service
                # order_type 변수 정의 (테스트 모드에서 필요)
                # 주문 타입별 필수 파라미터 검증 (배치 모드가 아닌 경우만)
                if not normalized_data.get('batch_mode'):
                    self._validate_order_type_params(normalized_data)


                # 배치 모드 감지 및 라우팅
                if normalized_data.get("batch_mode"):
                    result = trading_service.process_batch_trading_signal(normalized_data)
                else:
                    # 기존 단일 주문 처리
                    result = trading_service.process_trading_signal(normalized_data)
                webhook_log.status = "success"
                webhook_log.message = str(result)
                self.session.commit()
                return result

            # 전략 조회 및 토큰 검증 (단일 소스)
            strategy = self._validate_strategy_token(group_name, token)

            # 웹훅 타입 확인
            order_type = normalized_data.get('order_type', '')

            # 거래 처리 시작 시점 기록
            trade_started_at = time.time()

            if order_type == OrderType.CANCEL_ALL_ORDER:
                # Strategy의 market_type 기반 취소 로직 분기
                market_type = strategy.market_type or MarketType.SPOT

                if MarketType.is_crypto(market_type):
                    result = self.process_cancel_all_orders(normalized_data, webhook_received_at)
                else:
                    result = self._cancel_securities_orders(strategy, normalized_data, webhook_received_at)

            elif order_type == OrderType.CANCEL:
                result = self.process_cancel_order(normalized_data, webhook_received_at)
            else:
                # Strategy의 market_type 기반 거래 처리 분기
                market_type = strategy.market_type or MarketType.SPOT

                if MarketType.is_crypto(market_type):
                    # 크립토: 기존 로직
                    # 거래 신호는 trading_service로 위임
                    from app.services.trading import trading_service
                    # 주문 타입별 필수 파라미터 검증 (배치 모드가 아닌 경우만)
                    if not normalized_data.get('batch_mode') and OrderType.is_trading_type(order_type):
                        self._validate_order_type_params(normalized_data)

                    # 타이밍 컨텍스트 준비
                    timing_context = {
                        'webhook_received_at': webhook_received_at,
                        'webhook_validated_at': webhook_validated_at,
                        'trade_started_at': trade_started_at
                    }

                    # 전략 정보를 거래 데이터에 추가
                    normalized_data['strategy_id'] = strategy.id
                    normalized_data['strategy_name'] = strategy.name
                    normalized_data['market_type'] = market_type  # Strategy에서 가져온 market_type 주입

                    # 🆕 주문 정규화: 단일 → 배치 (비파괴적)
                    is_batch = 'orders' in normalized_data

                    if is_batch:
                        # 이미 배치 형식 → 그대로 사용
                        logger.info(f"📦 배치 주문 모드 감지 - {len(normalized_data['orders'])}개 주문")
                        result = trading_service.core.process_batch_trading_signal(normalized_data, timing_context)
                    else:
                        logger.info(f"📝 단일 주문 처리")
                        result = trading_service.core.process_trading_signal(normalized_data, timing_context)

                    # 🆕 거래 신호 처리 결과 분석 및 로깅
                    self._analyze_trading_result(result, normalized_data)

                elif MarketType.is_securities(market_type):
                    # 증권: 신규 로직
                    # 타이밍 컨텍스트 준비
                    timing_context = {
                        'webhook_received_at': webhook_received_at,
                        'webhook_validated_at': webhook_validated_at,
                        'trade_started_at': trade_started_at
                    }
                    result = self._process_securities_order(strategy, normalized_data, timing_context)

                else:
                    raise WebhookError(f"지원하지 않는 market_type: {market_type}")

            # 성공 시 로그 업데이트 (모든 타이밍 정보 저장)
            webhook_log.status = 'success'
            webhook_log.message = str(result)
            webhook_log.webhook_validated_at = webhook_validated_at
            webhook_log.trade_started_at = trade_started_at

            # 거래 결과에서 타이밍 정보 추출 (있는 경우)
            if isinstance(result, dict) and 'timing' in result:
                timing_info = result['timing']
                webhook_log.trade_requested_at = timing_info.get('trade_requested_at')
                webhook_log.trade_responded_at = timing_info.get('trade_responded_at')

            self.session.commit()

            # ✅ SSE 이벤트는 trading_service에서 중앙화 처리됨

            # 웹훅 처리 완료 시점 기록
            webhook_completed_at = time.time()

            # 성능 메트릭 계산
            validation_time_ms = round((webhook_validated_at - webhook_received_at) * 1000, 2)
            preprocessing_time_ms = round((trade_started_at - webhook_validated_at) * 1000, 2)
            total_processing_time_ms = round((webhook_completed_at - webhook_received_at) * 1000, 2)

            # 웹훅 로그에 완료 시점과 성능 메트릭 저장
            webhook_log.webhook_completed_at = webhook_completed_at
            webhook_log.validation_time_ms = validation_time_ms
            webhook_log.preprocessing_time_ms = preprocessing_time_ms
            webhook_log.total_processing_time_ms = total_processing_time_ms

            # 거래 처리 시간도 저장 (있는 경우)
            if isinstance(result, dict) and 'timing' in result:
                timing_info = result['timing']
                if timing_info.get('trade_processing_time_ms'):
                    webhook_log.trade_processing_time_ms = timing_info['trade_processing_time_ms']

            # 최종 커밋
            self.session.commit()

            # 성능 메트릭만 유지 (사용자에게 필요한 정보)
            if isinstance(result, dict):
                result['performance_metrics'] = {
                    'validation_time_ms': validation_time_ms,
                    'preprocessing_time_ms': preprocessing_time_ms,
                    'total_processing_time_ms': total_processing_time_ms
                }

            return result

        except Exception as e:
            # 실패 시 로그 업데이트 (타이밍 정보 포함)
            if 'webhook_log' in locals():
                error_time = time.time()
                webhook_log.status = 'failed'
                webhook_log.message = str(e)
                webhook_log.webhook_completed_at = error_time

                # 검증 및 전처리 시간이 기록된 경우 저장
                if 'webhook_validated_at' in locals():
                    webhook_log.webhook_validated_at = webhook_validated_at
                    webhook_log.validation_time_ms = round((webhook_validated_at - webhook_received_at) * 1000, 2)

                    if 'trade_started_at' in locals():
                        webhook_log.trade_started_at = trade_started_at
                        webhook_log.preprocessing_time_ms = round((trade_started_at - webhook_validated_at) * 1000, 2)

                # 총 처리 시간 계산
                webhook_log.total_processing_time_ms = round((error_time - webhook_received_at) * 1000, 2)

                self.session.commit()

            logger.error(f"웹훅 처리 실패: {str(e)}")
            raise WebhookError(f"웹훅 처리 실패: {str(e)}")

    # @FEAT:webhook-order @COMP:service @TYPE:helper
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

    # @FEAT:webhook-order @COMP:service @TYPE:core
    def process_cancel_all_orders(self, webhook_data: Dict[str, Any], webhook_received_at: float) -> Dict[str, Any]:
        """모든 주문 취소 처리 - order_service를 통해 처리 (선택적 필터링 지원)"""
        group_name = webhook_data.get('group_name')
        token = webhook_data.get('token')
        symbol = webhook_data.get('symbol')  # 필수: 특정 심볼
        side = webhook_data.get('side')  # 선택적: BUY/SELL (없으면 모든 주문 취소)

        logger.info(f"🔄 주문 취소 처리 시작 - 전략: {group_name}, "
                   f"심볼: {symbol}, side: {side or '전체'}")

        if not group_name:
            raise WebhookError("group_name이 필요합니다")

        # 전략 조회 및 토큰 검증 (공개 전략 구독자 토큰 허용)
        strategy = Strategy.query.filter_by(group_name=group_name, is_active=True).first()
        if not strategy:
            raise WebhookError(f"활성 전략을 찾을 수 없습니다: {group_name}")

        if not token:
            raise WebhookError("웹훅 토큰이 필요합니다")

        valid_tokens = set()
        owner = strategy.user
        if owner and getattr(owner, 'webhook_token', None):
            valid_tokens.add(owner.webhook_token)
        if getattr(strategy, 'is_public', False):
            try:
                for sa in strategy.strategy_accounts:
                    if getattr(sa, 'is_active', True) and getattr(sa, 'account', None):
                        account_user = getattr(sa.account, 'user', None)
                        user_token = getattr(account_user, 'webhook_token', None) if account_user else None
                        if user_token:
                            valid_tokens.add(user_token)
            except Exception:
                pass

        if not valid_tokens:
            raise WebhookError("웹훅 토큰이 설정된 사용자가 없습니다. 전략 소유자 또는 구독자의 토큰을 생성하세요")

        if token not in valid_tokens:
            raise WebhookError("웹훅 토큰이 유효하지 않습니다")

        logger.info(f"✅ 전략 조회 성공 - ID: {strategy.id}, 이름: {strategy.name}")

        # 전략에 연결된 계좌들 조회
        strategy_accounts = strategy.strategy_accounts
        if not strategy_accounts:
            raise WebhookError(f"전략에 연결된 계좌가 없습니다: {group_name}")

        logger.info(f"📋 전략에 연결된 계좌 수: {len(strategy_accounts)}")

        # order_service를 통해 계좌별 주문 취소 처리
        from app.services.trading import trading_service as order_service

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

            logger.info(f"✅ 계좌 {account.id}({account.name}): 주문 취소 처리 대상")
            processed_count += 1

            try:
                # ✅ 단일 소스 원칙: cancel_all_orders_by_user()를 직접 호출
                # account.user_id를 직접 전달하여 불필요한 DB 조회 방지
                logger.info(f"🔄 계좌 {account.id} (user: {account.user_id}): "
                           f"주문 취소 요청 (side={side or '전체'})...")
                cancel_result = order_service.cancel_all_orders_by_user(
                    user_id=account.user_id,  # ✅ 이미 있는 정보 활용 (성능 최적화)
                    strategy_id=strategy.id,
                    account_id=account.id,  # 특정 계좌 지정
                    symbol=symbol,
                    side=side,
                    timing_context={'webhook_received_at': webhook_received_at}
                )

                if cancel_result['success']:
                    cancelled_orders_raw = cancel_result.get('cancelled_orders', [])
                    failed_orders_raw = cancel_result.get('failed_orders', [])

                    # 정수 또는 리스트로 처리 (trading.py에서 정수로 반환하는 경우 고려)
                    if isinstance(cancelled_orders_raw, int):
                        cancelled_count = cancelled_orders_raw
                        cancelled_orders_details = []
                    else:
                        cancelled_count = len(cancelled_orders_raw)
                        cancelled_orders_details = cancelled_orders_raw

                    if isinstance(failed_orders_raw, int):
                        failed_count = failed_orders_raw
                        failed_orders_details = []
                    else:
                        failed_count = len(failed_orders_raw)
                        failed_orders_details = failed_orders_raw

                    logger.info(f"✅ 계좌 {account.id}({account.name}) 주문 취소 완료 - "
                               f"성공: {cancelled_count}개, 실패: {failed_count}개")

                    results.append({
                        'account_id': account.id,
                        'account_name': account.name,
                        'exchange': account.exchange,
                        'cancelled_orders': cancelled_count,
                        'failed_orders': failed_count,
                        'cancelled_order_details': cancelled_orders_details,
                        'failed_order_details': failed_orders_details,
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
            'results': results,
            'summary': {
                'total_accounts': len(strategy_accounts),
                'processed_accounts': processed_count,
                'skipped_accounts': skipped_count,
                'successful_accounts': len(successful_results),
                'failed_accounts': len(failed_results),
                'total_cancelled_orders': sum(r.get('cancelled_orders', 0) for r in successful_results),
                'total_failed_orders': sum(r.get('failed_orders', 0) for r in successful_results)
            },
            'webhook_timing': {
                'received_at': webhook_received_at,
                'received_timestamp': datetime.fromtimestamp(webhook_received_at).isoformat()
            }
        }

    # @FEAT:webhook-order @COMP:service @TYPE:core
    def process_cancel_order(self, normalized_data: Dict[str, Any], webhook_received_at: float) -> Dict[str, Any]:
        """개별 주문 취소 처리"""
        from app.services.trading import trading_service
        from app.models import Strategy, StrategyAccount

        group_name = normalized_data.get('group_name')
        symbol = normalized_data.get('symbol')
        order_id = normalized_data.get('order_id')  # CANCEL 주문 시 필요한 order_id

        logger.info(f"🔄 개별 주문 취소 처리 시작 - 전략: {group_name}, 주문: {order_id}")

        # 전략 조회
        strategy = Strategy.query.filter_by(name=group_name).first()
        if not strategy:
            return {
                'action': 'cancel_order',
                'success': False,
                'error': f'전략을 찾을 수 없습니다: {group_name}'
            }

        # 연결된 계좌 조회
        strategy_accounts = StrategyAccount.query.filter_by(strategy_id=strategy.id).all()
        if not strategy_accounts:
            return {
                'action': 'cancel_order',
                'success': False,
                'error': f'전략 {group_name}에 연결된 계좌가 없습니다'
            }

        results = []

        for strategy_account in strategy_accounts:
            account = strategy_account.account
            if not account or not account.is_active:
                continue

            try:
                logger.info(f"🔄 계좌 {account.id}({account.name}): 주문 {order_id} 취소 중...")

                # 개별 주문 취소
                cancel_result = trading_service.cancel_order_by_user(
                    user_id=strategy.user_id,
                    order_id=order_id,
                    symbol=symbol
                )

                if cancel_result['success']:
                    logger.info(f"✅ 계좌 {account.id}({account.name}) 주문 {order_id} 취소 완료")
                    results.append({
                        'account_id': account.id,
                        'account_name': account.name,
                        'exchange': account.exchange,
                        'order_id': order_id,
                        'success': True,
                        'message': '주문 취소 완료'
                    })
                else:
                    error_msg = cancel_result.get('error', '알 수 없는 오류')
                    logger.error(f"❌ 계좌 {account.id}({account.name}) 주문 {order_id} 취소 실패: {error_msg}")
                    results.append({
                        'account_id': account.id,
                        'account_name': account.name,
                        'exchange': account.exchange,
                        'order_id': order_id,
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
                    'order_id': order_id,
                    'error': f"처리 중 예외: {error_msg}",
                    'success': False
                })

        # 결과 요약
        successful_results = [r for r in results if r.get('success', False)]
        failed_results = [r for r in results if not r.get('success', False)]

        logger.info(f"📊 개별 주문 취소 처리 완료:")
        logger.info(f"   처리 대상: {len(results)}")
        logger.info(f"   성공: {len(successful_results)}")
        logger.info(f"   실패: {len(failed_results)}")

        return {
            'action': 'cancel_order',
            'strategy': group_name,
            'order_id': order_id,
            'symbol': symbol,
            'results': results,
            'summary': {
                'total_accounts': len(strategy_accounts),
                'processed_accounts': len(results),
                'successful_accounts': len(successful_results),
                'failed_accounts': len(failed_results)
            },
            'webhook_timing': {
                'received_at': webhook_received_at,
                'received_timestamp': datetime.fromtimestamp(webhook_received_at).isoformat()
            }
        }

    # @FEAT:webhook-order @FEAT:securities-integration @COMP:service @TYPE:integration
    def _process_securities_order(
        self,
        strategy: Strategy,
        normalized_data: Dict[str, Any],
        timing_context: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        증권 거래소 주문 처리

        Args:
            strategy: 검증된 Strategy 객체
            normalized_data: 정규화된 웹훅 데이터
            timing_context: 타이밍 정보 (webhook_received_at, trade_started_at 등)

        Returns:
            dict: 주문 처리 결과
            {
                'success': bool,
                'message': str,
                'results': [{'account_name': str, 'order_id': str, 'status': str}],
                'summary': {'total_accounts': int, 'successful': int, 'failed': int},
                'timing': {...}
            }

        Raises:
            WebhookError: 필수 필드 누락 또는 처리 실패 시
        """
        from app.exchanges import UnifiedExchangeFactory
        from app.models import Trade, OpenOrder

        logger.info(f"🏛️ 증권 주문 처리 시작 - 전략: {strategy.group_name}, "
                    f"심볼: {normalized_data.get('symbol')}, "
                    f"side: {normalized_data.get('side')}")

        # 필수 필드 검증
        required_fields = ['symbol', 'side', 'order_type']
        for field in required_fields:
            if field not in normalized_data:
                raise WebhookError(f"증권 주문에 필수 필드 누락: {field}")

        # 전략에 연결된 계좌 조회
        strategy_accounts = strategy.strategy_accounts
        if not strategy_accounts:
            raise WebhookError(f"전략 '{strategy.group_name}'에 연결된 계좌가 없습니다")

        results = []
        successful_orders = 0
        failed_orders = 0

        for sa in strategy_accounts:
            account = sa.account

            # 증권 계좌만 처리
            if account.account_type != 'STOCK':
                logger.warning(f"⚠️ 증권 웹훅이지만 계좌 타입이 STOCK이 아님 "
                              f"(account_id={account.id}, type={account.account_type})")
                continue

            try:
                # 1. 증권 거래소 어댑터 생성
                trade_request_start = time.time()
                exchange = UnifiedExchangeFactory.create(account)

                # 2. 주문 생성 (거래소 API 호출)
                order_params = {
                    'symbol': normalized_data['symbol'],
                    'side': normalized_data['side'].upper(),
                    'order_type': normalized_data['order_type'],
                    'quantity': int(normalized_data.get('qty_per', 0)),
                    'price': normalized_data.get('price')
                }

                logger.info(f"📤 증권 주문 생성 시도 (계좌={account.name}): {order_params}")

                # create_order 메서드 호출
                stock_order = exchange.create_order(**order_params)

                trade_request_end = time.time()

                logger.info(f"✅ 증권 주문 생성 완료 - order_id: {stock_order.order_id}, "
                           f"status: {stock_order.status}")

                # 3. DB 저장 (Trade 테이블)
                # Trade 모델은 status 필드가 없으므로 제외
                trade = Trade(
                    strategy_account_id=sa.id,
                    symbol=stock_order.symbol,
                    side=stock_order.side,
                    order_type=stock_order.order_type,
                    quantity=stock_order.quantity,
                    price=float(stock_order.price) if stock_order.price else 0.0,
                    exchange_order_id=stock_order.order_id,
                    market_type=strategy.market_type,
                    timestamp=datetime.utcnow()
                )
                db.session.add(trade)

                # 4. OpenOrder 저장 (미체결 주문 관리)
                if stock_order.status in ['NEW', 'PARTIALLY_FILLED']:
                    open_order = OpenOrder(
                        strategy_account_id=sa.id,
                        symbol=stock_order.symbol,
                        side=stock_order.side,
                        order_type=stock_order.order_type,
                        quantity=stock_order.quantity,
                        price=float(stock_order.price) if stock_order.price else None,
                        exchange_order_id=stock_order.order_id,
                        status=stock_order.status
                    )
                    db.session.add(open_order)

                db.session.commit()

                # 5. SSE 이벤트 발행
                self._emit_order_event(
                    account_id=account.id,
                    order_id=stock_order.order_id,
                    symbol=stock_order.symbol,
                    side=stock_order.side,
                    order_type=stock_order.order_type,
                    status=stock_order.status,
                    quantity=stock_order.quantity,
                    price=stock_order.price,
                    event_type='order_created'
                )

                results.append({
                    'account_name': account.name,
                    'order_id': stock_order.order_id,
                    'status': stock_order.status,
                    'symbol': stock_order.symbol,
                    'side': stock_order.side
                })
                successful_orders += 1

            except Exception as e:
                logger.error(f"❌ 증권 주문 생성 실패 (account_id={account.id}, "
                            f"account_name={account.name}): {e}", exc_info=True)
                results.append({
                    'account_name': account.name,
                    'error': str(e),
                    'status': 'failed'
                })
                failed_orders += 1

        # 6. 결과 반환
        if not results:
            raise WebhookError("처리할 증권 계좌가 없습니다. STOCK 타입 계좌를 확인하세요.")

        return {
            'success': successful_orders > 0,
            'message': f'증권 주문 처리 완료 - 성공: {successful_orders}, 실패: {failed_orders}',
            'results': results,
            'summary': {
                'total_accounts': len(results),
                'successful': successful_orders,
                'failed': failed_orders
            },
            'timing': timing_context  # 타이밍 정보 전달
        }

    # @FEAT:webhook-order @FEAT:securities-integration @COMP:service @TYPE:integration
    def _cancel_securities_orders(
        self,
        strategy: Strategy,
        normalized_data: Dict[str, Any],
        webhook_received_at: float
    ) -> Dict[str, Any]:
        """
        증권 거래소 미체결 주문 취소 (CANCEL_ALL_ORDER 타입)

        Args:
            strategy: 검증된 Strategy 객체
            normalized_data: 정규화된 웹훅 데이터
            webhook_received_at: 웹훅 수신 시각

        Returns:
            dict: 취소 처리 결과
            {
                'success': bool,
                'message': str,
                'cancelled_orders': int,
                'failed_orders': int,
                'results': [...]
            }
        """
        from app.exchanges import UnifiedExchangeFactory
        from app.models import OpenOrder

        symbol = normalized_data.get('symbol')  # 선택적 (특정 심볼만 취소)

        logger.info(f"🏛️ 증권 주문 취소 시작 - 전략: {strategy.group_name}, "
                    f"심볼: {symbol or '전체'}")

        cancelled_count = 0
        failed_count = 0
        results = []

        for sa in strategy.strategy_accounts:
            account = sa.account

            # 증권 계좌만 처리
            if account.account_type != 'STOCK':
                continue

            try:
                # DB에서 미체결 주문 조회
                query = OpenOrder.query.filter_by(
                    strategy_account_id=sa.id,
                    status='NEW'
                )

                # 심볼 필터 (선택적)
                if symbol:
                    query = query.filter_by(symbol=symbol)

                open_orders = query.all()

                if not open_orders:
                    logger.info(f"ℹ️ 취소할 미체결 주문 없음 (계좌={account.name}, 심볼={symbol or '전체'})")
                    continue

                logger.info(f"📋 취소 대상 주문: {len(open_orders)}개 (계좌={account.name})")

                # 증권 어댑터 생성
                exchange = UnifiedExchangeFactory.create(account)

                # 주문 취소
                account_cancelled = 0
                account_failed = 0

                for order in open_orders:
                    try:
                        # 거래소 API 호출
                        exchange.cancel_order(
                            order_id=order.exchange_order_id,
                            symbol=order.symbol
                        )

                        # DB 상태 업데이트
                        order.status = 'CANCELLED'

                        # SSE 이벤트 발행
                        self._emit_order_event(
                            account_id=account.id,
                            order_id=order.exchange_order_id,
                            symbol=order.symbol,
                            side=order.side,
                            order_type=order.order_type,
                            status='CANCELLED',
                            quantity=order.quantity,
                            price=order.price,
                            event_type='order_cancelled'
                        )

                        account_cancelled += 1
                        logger.info(f"✅ 주문 취소 완료 - order_id: {order.exchange_order_id}")

                    except Exception as e:
                        logger.error(f"❌ 주문 취소 실패 - order_id: {order.exchange_order_id}, "
                                   f"error: {e}")
                        account_failed += 1

                db.session.commit()

                cancelled_count += account_cancelled
                failed_count += account_failed

                results.append({
                    'account_name': account.name,
                    'cancelled': account_cancelled,
                    'failed': account_failed
                })

            except Exception as e:
                logger.error(f"❌ 증권 주문 취소 실패 (account_id={account.id}): {e}",
                            exc_info=True)
                results.append({
                    'account_name': account.name,
                    'error': str(e)
                })

        # 결과 메시지 생성
        if cancelled_count == 0 and failed_count == 0:
            message = "취소할 미체결 주문이 없습니다"
        else:
            message = f"증권 주문 취소 완료 - 성공: {cancelled_count}, 실패: {failed_count}"

        return {
            'success': True,  # 취소 대상이 없어도 success=True
            'message': message,
            'cancelled_orders': cancelled_count,
            'failed_orders': failed_count,
            'results': results
        }

    # @FEAT:webhook-order @FEAT:event-sse @COMP:service @TYPE:helper
    def _emit_order_event(
        self,
        account_id: int,
        order_id: str,
        symbol: str,
        side: str,
        order_type: str,
        status: str,
        quantity: float,
        price: Optional[float],
        event_type: str = 'order_created'
    ) -> None:
        """
        SSE 이벤트 발행 (주문 생성/취소/체결 알림)

        Args:
            account_id: 계좌 ID
            order_id: 거래소 주문 ID
            symbol: 심볼
            side: 주문 방향 (BUY/SELL)
            order_type: 주문 타입 (LIMIT/MARKET 등)
            status: 주문 상태 (NEW/FILLED/CANCELLED 등)
            quantity: 주문 수량
            price: 주문 가격 (선택적)
            event_type: 이벤트 타입 (order_created/order_cancelled 등)
        """
        try:
            from app.services.event_service import event_service

            event_data = {
                'account_id': account_id,
                'order_id': order_id,
                'symbol': symbol,
                'side': side,
                'order_type': order_type,
                'status': status,
                'quantity': quantity,
                'price': price,
                'timestamp': time.time()
            }

            event_service.emit_order_event(
                account_id=account_id,
                event_type=event_type,
                data=event_data
            )

            logger.debug(f"📡 SSE 이벤트 발행 완료 - event_type: {event_type}, order_id: {order_id}")

        except Exception as e:
            # SSE 이벤트 발행 실패는 치명적 에러가 아님
            logger.warning(f"⚠️ SSE 이벤트 발행 실패: {e}")

# 전역 인스턴스
webhook_service = WebhookService()
