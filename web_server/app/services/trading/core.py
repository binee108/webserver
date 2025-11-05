# @FEAT:framework @FEAT:webhook-order @FEAT:order-tracking @COMP:service @TYPE:core
"""Core trading execution logic extracted from the legacy trading service."""

from __future__ import annotations

import logging
import os
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from flask import current_app

from app import db
from app.models import Account, Strategy, StrategyAccount, OpenOrder
from app.constants import Exchange, MarketType, OrderType, OrderStatus
from app.services.exchange import exchange_service
from app.services.security import security_service
from app.services.utils import to_decimal

logger = logging.getLogger(__name__)

# @FEAT:batch-parallel-processing @COMP:service @TYPE:config
# ✅ Priority 2: 병렬 배치 처리 타임아웃 설정 (환경 변수 기반)
BATCH_ACCOUNT_TIMEOUT_SEC = int(os.getenv('BATCH_ACCOUNT_TIMEOUT_SEC', '30'))


def _parse_retry_delays(env_value: str, default: str = '125,250,500,1000,2000') -> List[float]:
    """
    MARKET_ORDER_RETRY_DELAYS_MS 환경 변수 파싱 및 검증

    Args:
        env_value: 환경 변수 값 (예: "125,250,500,1000,2000")
        default: 파싱 실패 시 기본값

    Returns:
        재시도 간격 리스트 (초 단위, 예: [0.125, 0.25, 0.5, 1.0, 2.0])

    Raises:
        None (파싱 실패 시 기본값 반환 및 에러 로그)
    """
    try:
        delays = [int(d.strip()) / 1000.0 for d in env_value.split(',') if d.strip()]
        if not delays or any(d <= 0 for d in delays):
            raise ValueError("재시도 간격은 양수여야 합니다")
        # ✅ Priority 3: 최대 재시도 횟수 제한 (과도한 재시도 방지)
        if len(delays) > 10:
            logger.warning(f"⚠️ 재시도 간격이 {len(delays)}개입니다. 10개로 제한합니다.")
            delays = delays[:10]
        return delays
    except (ValueError, AttributeError) as e:
        logger.error(
            f"❌ MARKET_ORDER_RETRY_DELAYS_MS 파싱 실패: {e}, "
            f"기본값 사용 ({default})"
        )
        # ✅ Priority 2: 기본값 파싱도 안전하게 처리 (이중 안전망)
        try:
            return [int(d.strip()) / 1000.0 for d in default.split(',') if d.strip()]
        except Exception as fallback_error:
            # 하드코딩된 폴백 (마지막 안전망)
            logger.critical(
                f"❌ 기본 재시도 간격 파싱 실패: {fallback_error}, "
                f"하드코딩 값 사용 [0.125, 0.25, 0.5, 1.0, 2.0]"
            )
            return [0.125, 0.25, 0.5, 1.0, 2.0]


def sanitize_error_message(error_msg: str, max_length: int = 500) -> str:
    """
    Remove sensitive information from error messages before DB storage.

    Security patterns to remove:
    - API keys: Remove patterns like "key=ABC123", "apikey: XYZ"
    - Account numbers: Remove digit sequences >8 chars
    - Tokens: Remove "token=...", "bearer ..."
    - Email addresses: Redact to "***@***.***"
    - IP addresses: Partial redaction (e.g., "192.168.*.*")

    @FEAT:webhook-order @COMP:service @TYPE:core
    @DATA:error_message - 에러 메시지 보안 처리 (Phase 1: 2025-10-30)

    Args:
        error_msg: Raw error message from exchange API
        max_length: Maximum length of sanitized message (default: 500)

    Returns:
        str: Sanitized error message (max 500 characters)

    Examples:
        >>> sanitize_error_message("API key abc123 invalid")
        "API key [REDACTED] invalid"

        >>> sanitize_error_message("Account 123456789 insufficient balance")
        "Account [REDACTED] insufficient balance"
    """
    if not error_msg:
        return ""

    sanitized = error_msg

    # 1. API key pattern: API_KEY, API-KEY, SECRET, TOKEN 뒤에 오는 문자열 마스킹
    # 예: "API-KEY: abc123def456ghi789..." → "API-KEY: abc123***"
    sanitized = re.sub(
        r'(API[_-]?KEY|SECRET|TOKEN)["\s:=]+([a-zA-Z0-9]{8})[a-zA-Z0-9]+',
        r'\1: \2***',
        sanitized,
        flags=re.IGNORECASE
    )

    # 2. Account number pattern: 9자리 이상의 연속된 숫자 제거
    # 예: "Account 123456789 insufficient balance" → "Account [REDACTED]"
    sanitized = re.sub(r'\b\d{9,}\b', '[REDACTED]', sanitized)

    # 3. Bearer token pattern: "bearer abc123..." 형태
    # 예: "bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." → "bearer [REDACTED]"
    sanitized = re.sub(
        r'(bearer|authorization)\s+[a-zA-Z0-9\-._~+/]+=*',
        r'\1 [REDACTED]',
        sanitized,
        flags=re.IGNORECASE
    )

    # 4. Email pattern: "user@example.com" → "***@***.***"
    # 예: "invalid user@example.com" → "invalid ***@***.***"
    sanitized = re.sub(
        r'\b[\w\.-]+@[\w\.-]+\.\w+\b',
        '***@***.***',
        sanitized
    )

    # 5. IP address pattern: Partial redaction "192.168.*.*"
    # 예: "Connection refused from 192.168.1.100" → "Connection refused from 192.168.*.*"
    sanitized = re.sub(
        r'(\d{1,3}\.\d{1,3})\.\d{1,3}\.\d{1,3}',
        r'\1.*.*',
        sanitized
    )

    # 6. Truncate to max_length
    return sanitized[:max_length]




# @FEAT:framework @FEAT:webhook-order @FEAT:order-tracking @COMP:service @TYPE:core
class TradingCore:
    """Encapsulates trading execution, signal processing, and exchange coordination."""

    def __init__(self, service: Optional[object] = None) -> None:
        self.service = service

    # @FEAT:webhook-order @FEAT:order-tracking @FEAT:order-queue @COMP:service @TYPE:core
    def execute_trade(self, strategy: Strategy, symbol: str, side: str,
                     quantity: Decimal, order_type: str,
                     price: Optional[Decimal] = None,
                     stop_price: Optional[Decimal] = None,
                     strategy_account_override: Optional[StrategyAccount] = None,
                     schedule_refresh: bool = True,
                     timing_context: Optional[Dict[str, float]] = None,
                     from_pending_queue: bool = False) -> Dict[str, Any]:
        """
        거래 실행 (Phase 4: 즉시 실행)

        Phase 4 변경사항:
        - 모든 주문 타입: 검증 후 즉시 거래소 실행
        - MARKET 주문: 기존대로 즉시 거래소 제출
        - LIMIT/STOP 주문: 검증 후 즉시 거래소 실행 (Phase 4+)

        Args:
            strategy: 전략 객체
            symbol: 심볼
            side: 매수/매도 방향 (BUY/SELL)
            quantity: 수량
            order_type: 주문 유형 (MARKET/LIMIT/STOP_MARKET/STOP_LIMIT)
            price: 가격 (지정가 주문시)
            stop_price: 스탑 가격 (스탑 주문시)
            strategy_account_override: 특정 전략 계좌로 거래를 강제할 때 사용
            timing_context: 타이밍 측정 딕셔너리 (webhook_received_at: Unix timestamp)

        Returns:
            거래 실행 결과
        """
        try:
            logger.info(f"거래 실행 시작 - 전략: {strategy.name}, 심볼: {symbol}, "
                       f"주문: {side} {quantity} {order_type}")

            # 계정 정보 조회
            strategy_account = strategy_account_override or StrategyAccount.query.filter_by(
                strategy_id=strategy.id
            ).first()

            if not strategy_account or not strategy_account.account:
                return {
                    'success': False,
                    'error': '전략에 연결된 계정이 없습니다',
                    'error_type': 'account_error'
                }

            account = strategy_account.account

            # 마켓 타입 결정 (대소문자 구분 없이)
            strategy_market_type = getattr(strategy, 'market_type', 'SPOT').upper()
            market_type = 'futures' if strategy_market_type == 'FUTURES' else 'spot'

            logger.info(f"📊 전략 마켓타입: {strategy_market_type} → 거래소 마켓타입: {market_type}")

            # @FEAT:immediate-execution @COMP:service @TYPE:core
            # Phase 4: Queue 제거 및 즉시 실행 전환 (모든 주문 타입)
            # 모든 주문 타입을 즉시 거래소에 제출합니다.
            from app.constants import ORDER_TYPE_GROUPS, OrderStatus

            type_group = None
            for group_name, types in ORDER_TYPE_GROUPS.items():
                if order_type.upper() in types:
                    type_group = group_name
                    break

            # MARKET/CANCEL/LIMIT/STOP 주문: 모두 즉시 거래소 제출
            # (Phase 4: Queue 시스템 제거 완료)
            # 🆕 Phase 5: 주문 실행 직전 is_active 재확인 (Race Condition 방지)
            if hasattr(strategy_account, 'is_active') and not strategy_account.is_active:
                logger.warning(
                    f"⚠️ [Phase 5] StrategyAccount {strategy_account.id} 비활성 상태 - "
                    f"MARKET 주문 스킵 (전략: {strategy.group_name}, 계좌: {account.name}, "
                    f"심볼: {symbol}, 방향: {side})"
                )
                return {
                    'success': False,
                    'error': 'StrategyAccount가 비활성 상태입니다',
                    'error_type': 'account_inactive',
                    'account_id': account.id,
                    'account_name': account.name,
                    'strategy_account_id': strategy_account.id,
                    'skipped': True,
                    'skip_reason': 'strategy_account_inactive'
                }

            # ============================================================
            # STEP 1: Create PENDING order (before exchange API)
            # ============================================================
            # @FEAT:webhook-order @COMP:service @TYPE:core
            # @DATA:OrderStatus.PENDING - DB-first 패턴 (Phase 2: 2025-10-30)
            pending_order = OpenOrder(
                strategy_account_id=strategy_account.id,
                exchange_order_id=f"PENDING-{uuid.uuid4().hex}",  # Full UUID (Fixed Issue #3)
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=float(quantity) if quantity else 0.0,
                filled_quantity=0.0,
                status=OrderStatus.PENDING,
                market_type=market_type,
                price=float(price) if price else None,
                stop_price=float(stop_price) if stop_price else None,
                created_at=datetime.utcnow()
            )

            db.session.add(pending_order)
            db.session.commit()
            pending_order_id = pending_order.id

            logger.debug(
                f"✅ PENDING 주문 생성: id={pending_order_id}, "
                f"symbol={symbol}, side={side}, qty={quantity}"
            )

            try:
                # ============================================================
                # STEP 2: Exchange API call
                # ============================================================
                order_result = self._execute_exchange_order(
                    account=account,
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    order_type=order_type,
                    market_type=market_type,
                    price=price,
                    stop_price=stop_price,
                    timing_context=timing_context
                )

                order_result['account_id'] = account.id

                # ============================================================
                # STEP 3: Update PENDING → OPEN (on success)
                # ============================================================
                if order_result.get('success'):
                    order = OpenOrder.query.get(pending_order_id)
                    if not order:
                        raise ValueError(
                            f"PENDING order not found: id={pending_order_id}. "
                            f"This should never happen - indicates data corruption."
                        )  # Fixed Issue #2

                    old_status = order.status
                    order.status = OrderStatus.OPEN

                    # Update with exchange data
                    exchange_order = {
                        'id': order_result.get('order_id'),
                        'price': float(price) if price else None,
                        'filled': float(order_result.get('filled_quantity', 0)) if order_result.get('filled_quantity') else 0.0
                    }
                    order.exchange_order_id = exchange_order.get('id', order.exchange_order_id)
                    if exchange_order.get('price'):
                        order.price = exchange_order['price']
                    if exchange_order.get('filled'):
                        order.filled_quantity = exchange_order['filled']

                    # @FEAT:orphan-order-prevention @COMP:service @TYPE:core @DEPS:db-connection-pool
                    # 🆕 Phase 1: DB commit with 3 retries (50ms/100ms/150ms)
                    # 목적: stale connection으로 인한 커밋 실패 시 재시도 (고아 주문 방지)
                    retry_delays = [0.05, 0.10, 0.15]
                    db_update_success = False

                    for attempt in range(3):
                        try:
                            db.session.commit()
                            db_update_success = True
                            if attempt > 0:
                                logger.info(
                                    f"✅ PENDING→OPEN 성공 (재시도 {attempt}회 후) - "
                                    f"order_id={pending_order_id}, symbol={symbol}"
                                )
                            else:
                                logger.debug(
                                    f"🔄 주문 상태 전환: {old_status} → {OrderStatus.OPEN} "
                                    f"(exchange_order_id={exchange_order.get('id')})"
                                )
                            break
                        except Exception as e:
                            db.session.rollback()
                            logger.warning(
                                f"⚠️ PENDING→OPEN 재시도 {attempt+1}/3: {e} - "
                                f"order_id={pending_order_id}, symbol={symbol}"
                            )
                            if attempt < 2:
                                time.sleep(retry_delays[attempt])

                    if not db_update_success:
                        logger.critical(
                            f"🚨 ORPHAN ORDER - PENDING→OPEN 실패 (3회 재시도) - "
                            f"order_id={pending_order_id}, symbol={symbol}, "
                            f"exchange_order_id={exchange_order.get('id')}"
                        )
                        # PENDING 상태 유지 → Phase 4 백그라운드 정리 대상

                else:
                    # ============================================================
                    # STEP 5: Update PENDING → FAILED (on exchange API failure)
                    # ============================================================
                    order = OpenOrder.query.get(pending_order_id)
                    if not order:
                        raise ValueError(
                            f"PENDING order not found: id={pending_order_id}. "
                            f"This should never happen - indicates data corruption."
                        )  # Fixed Issue #2

                    old_status = order.status
                    error_msg = sanitize_error_message(order_result.get('error', 'Exchange order failed'))
                    order.status = OrderStatus.FAILED
                    order.error_message = error_msg

                    # @FEAT:orphan-order-prevention @COMP:service @TYPE:core @DEPS:db-connection-pool
                    # 🆕 Phase 1: DB commit with 3 retries (50ms/100ms/150ms)
                    # 목적: stale connection으로 인한 커밋 실패 시 재시도 (고아 주문 방지)
                    retry_delays = [0.05, 0.10, 0.15]
                    db_update_success = False

                    for attempt in range(3):
                        try:
                            db.session.commit()
                            db_update_success = True
                            if attempt > 0:
                                logger.info(
                                    f"✅ PENDING→FAILED 성공 (재시도 {attempt}회 후) - "
                                    f"order_id={pending_order_id}, error={error_msg}"
                                )
                            else:
                                logger.warning(
                                    f"⚠️ 주문 실패: {old_status} → {OrderStatus.FAILED} "
                                    f"(error: {error_msg[:50]}...)"
                                )
                            break
                        except Exception as e:
                            db.session.rollback()
                            logger.warning(
                                f"⚠️ PENDING→FAILED 재시도 {attempt+1}/3: {e} - "
                                f"order_id={pending_order_id}"
                            )
                            if attempt < 2:
                                time.sleep(retry_delays[attempt])

                    if not db_update_success:
                        logger.critical(
                            f"🚨 ORPHAN ORDER - PENDING→FAILED 실패 (3회 재시도) - "
                            f"order_id={pending_order_id}, error={error_msg}"
                        )
                        # PENDING 상태 유지 → Phase 4 백그라운드 정리 대상

                    # Phase 4: FailedOrder 생성 (재시도 메커니즘)
                    from app.services.trading.failed_order_manager import failed_order_manager

                    failed_order_manager.create_failed_order(
                        strategy_account_id=strategy_account.id,
                        order_params={
                            'symbol': symbol,
                            'side': side,
                            'order_type': order_type,
                            'quantity': quantity,
                            'price': price,
                            'stop_price': stop_price,
                            'market_type': market_type
                        },
                        reason=order_result.get('error', 'Exchange order failed'),
                        exchange_error=order_result.get('exchange_error')
                    )

                    logger.warning(
                        f"⚠️ 주문 실패 → FailedOrder 생성 - "
                        f"심볼: {symbol}, 타입: {order_type}, side: {side}, "
                        f"오류: {order_result.get('error')}"
                    )

                    return order_result

            except Exception as e:
                # ============================================================
                # STEP 5b: Update PENDING → FAILED (on exception)
                # ============================================================
                try:
                    order = OpenOrder.query.get(pending_order_id)
                    if not order:
                        raise ValueError(
                            f"PENDING order not found: id={pending_order_id}. "
                            f"This should never happen - indicates data corruption."
                        )  # Fixed Issue #2

                    old_status = order.status
                    error_msg = sanitize_error_message(str(e))
                    order.status = OrderStatus.FAILED
                    order.error_message = error_msg

                    # @FEAT:orphan-order-prevention @COMP:service @TYPE:core @DEPS:db-connection-pool
                    # 🆕 Phase 1: DB commit with 3 retries (50ms/100ms/150ms)
                    # 목적: stale connection으로 인한 커밋 실패 시 재시도 (고아 주문 방지)
                    retry_delays = [0.05, 0.10, 0.15]
                    db_update_success = False

                    for attempt in range(3):
                        try:
                            db.session.commit()
                            db_update_success = True
                            if attempt > 0:
                                logger.info(
                                    f"✅ PENDING→FAILED (exception) 성공 (재시도 {attempt}회 후) - "
                                    f"order_id={pending_order_id}, exception={str(e)[:50]}"
                                )
                            break
                        except Exception as commit_error:
                            db.session.rollback()
                            logger.warning(
                                f"⚠️ PENDING→FAILED (exception) 재시도 {attempt+1}/3: {commit_error} - "
                                f"order_id={pending_order_id}"
                            )
                            if attempt < 2:
                                time.sleep(retry_delays[attempt])

                    if not db_update_success:
                        logger.critical(
                            f"🚨 ORPHAN ORDER - PENDING→FAILED (exception) 실패 (3회 재시도) - "
                            f"order_id={pending_order_id}, exception={str(e)[:50]}"
                        )
                        # PENDING 상태 유지 → Phase 4 백그라운드 정리 대상
                    else:
                        logger.error(
                            f"❌ 주문 실패 (exception): {old_status} → {OrderStatus.FAILED} "
                            f"(error: {error_msg[:50]}...)"
                        )
                except Exception as inner_e:
                    logger.error(f"❌ PENDING → FAILED 전환 실패: {inner_e}")

                # 예외를 상위로 재전달
                raise

            # 조정된 수량/가격 보관 (거래소 제한 반영)
            adjusted_quantity = order_result.get('adjusted_quantity', quantity)
            adjusted_price = order_result.get('adjusted_price', price)
            adjusted_stop_price = order_result.get('adjusted_stop_price', stop_price)

            fill_summary = self.service.position_manager.process_order_fill(
                strategy_account=strategy_account,
                order_id=order_result.get('order_id'),
                symbol=symbol,
                side=side,
                order_type=order_type,
                order_result=order_result,
                market_type=market_type
            )

            # @FEAT:market-order-fill @COMP:service @TYPE:integration
            # ✅ MARKET 주문 즉시 체결 확인 (헬퍼 메서드 사용)
            # 단일 주문 경로: execute_trade() → _handle_market_order_immediate_fill()
            if not fill_summary.get('success') and order_type.upper() == 'MARKET':
                immediate_fill_result = self._handle_market_order_immediate_fill(
                    account=account,
                    strategy_account=strategy_account,
                    order_id=order_result.get('order_id'),
                    symbol=symbol,
                    side=side,
                    order_type=order_type,
                    market_type=market_type
                )

                if immediate_fill_result.get('filled'):
                    fill_summary = immediate_fill_result.get('fill_summary', {})
                    order_result = immediate_fill_result.get('filled_order', {})

            if not fill_summary.get('success'):
                logger.warning(
                    "체결 처리를 완료하지 못했습니다 - order_id=%s reason=%s",
                    order_result.get('order_id'),
                    fill_summary.get('error')
                )
                return {
                    'action': 'trading_signal',
                    'success': False,
                    'error': fill_summary.get('error'),
                    'order_id': order_result.get('order_id'),
                    'account_id': account.id,
                    'order_result': fill_summary.get('order_result')
                }

            order_result = fill_summary.get('order_result', order_result)
            filled_decimal = fill_summary.get('filled_quantity', Decimal('0'))
            average_decimal = fill_summary.get('average_price', Decimal('0'))

            # @FEAT:webhook-order @COMP:service @TYPE:core
            # OpenOrder 저장 (webhook_received_at 추출 및 전달 - Snapshot 쿼리용)
            # Note: timing_context은 선택적 (None이면 webhook_received_at = None)
            # UTC 변환: 전체 시스템이 UTC 기반이므로 utcfromtimestamp 사용
            webhook_received_at_dt = None
            if timing_context and 'webhook_received_at' in timing_context:
                webhook_received_at_dt = datetime.utcfromtimestamp(timing_context['webhook_received_at'])

            # OpenOrder 레코드 생성 (미체결 주문인 경우)
            open_order_result = self.service.order_manager.create_open_order_record(
                strategy_account=strategy_account,
                order_result=order_result,
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=adjusted_quantity,
                price=adjusted_price,
                stop_price=adjusted_stop_price,
                webhook_received_at=webhook_received_at_dt  # ✅ Added for Snapshot query
            )
            if open_order_result['success']:
                logger.info(f"📝 미체결 주문 OpenOrder 저장: {order_result.get('order_id')}")

                # 심볼 구독 추가 (WebSocket 연결)
                try:
                    self.service.subscribe_symbol(account.id, symbol)
                except Exception as e:
                    logger.warning(
                        f"⚠️ 심볼 구독 실패 (WebSocket health check에서 재시도): "
                        f"계정: {account.id}, 심볼: {symbol}, 오류: {e}"
                    )
                    # OpenOrder는 유지, WebSocket 헬스체크에서 재구독
            else:
                logger.debug(f"OpenOrder 저장 스킵: {open_order_result.get('reason', 'unknown')}")

            if not fill_summary.get('events_emitted'):
                self.service.event_emitter.emit_order_events_smart(strategy, symbol, side, adjusted_quantity, order_result)

            # 응답 데이터 구성 (filled_quantity를 숫자로 변환, 실제 체결가 사용)
            filled_qty_num = 0.0
            avg_price_num = 0.0

            try:
                if filled_decimal and filled_decimal > Decimal('0'):
                    filled_qty_num = float(filled_decimal)
            except (ValueError, TypeError):
                filled_qty_num = 0.0

            # average_price 결정 (실제 체결가 우선)
            if average_decimal and average_decimal > Decimal('0'):
                avg_price_num = float(average_decimal)
            else:
                avg_price_num = float(order_result.get('actual_execution_price', 0) or 0)
                if avg_price_num <= 0:
                    avg_price_num = float(order_result.get('average_price', 0) or 0)
                if avg_price_num <= 0:
                    avg_price_num = float(order_result.get('adjusted_average_price', 0) or 0)

            # results 배열 구성 (시장가 주문 체결 정보)
            results = []
            if filled_qty_num > 0 and avg_price_num > 0:
                results.append({
                    'symbol': symbol,
                    'side': side,
                    'executed_qty': filled_qty_num,
                    'executed_price': avg_price_num,
                    'trade_id': fill_summary.get('trade_id'),
                    'order_id': order_result.get('order_id'),
                    'timestamp': datetime.utcnow().isoformat()
                })

            result_payload = {
                'action': 'trading_signal',
                'success': True,
                'trade_id': fill_summary.get('trade_id'),
                'order_id': order_result.get('order_id'),
                'filled_quantity': filled_qty_num,  # 숫자로 반환
                'average_price': avg_price_num,  # 실제 체결가 반환
                'price': float(adjusted_price) if adjusted_price else None,  # 🆕 지정가 (LIMIT 주문용)
                'stop_price': float(adjusted_stop_price) if adjusted_stop_price else None,  # 🆕 스탑 가격
                'status': order_result.get('status'),
                'trade_status': fill_summary.get('trade_status'),
                'execution_status': fill_summary.get('execution_status'),
                'order_type': order_type,  # 🆕 주문 타입
                'account_id': account.id,
                'results': results  # 체결 상세 정보 배열
            }


            if schedule_refresh:
                security_service.refresh_account_balance_async(account.id)

            return result_payload

        except Exception as e:
            logger.error(f"거래 실행 실패: {e}")
            failure_payload = {
                'action': 'trading_signal',
                'success': False,
                'error': str(e),
                'error_type': 'execution_error'
            }
            if 'account_id' not in failure_payload and 'account' in locals() and account:
                failure_payload['account_id'] = account.id
            return failure_payload

    # @FEAT:webhook-order @FEAT:order-tracking @COMP:service @TYPE:integration
    def _execute_exchange_order(self, account: Account, symbol: str, side: str,
                                quantity: Decimal, order_type: str, market_type: str,
                                price: Optional[Decimal] = None,
                                stop_price: Optional[Decimal] = None,
                                timing_context: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """
        거래소 주문 실행

        Args:
            account: 계정 정보
            symbol: 거래 심볼
            side: 매수/매도 방향
            quantity: 수량
            order_type: 주문 유형
            market_type: 마켓 유형 (spot/futures)
            price: 지정가 (선택)
            stop_price: 스탑 가격 (선택)
            timing_context: 타이밍 컨텍스트 (사용하지 않음, 호환성 유지)

        Returns:
            주문 실행 결과
        """
        # exchange_service를 통한 주문 생성
        return exchange_service.create_order(
            account=account,
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            market_type=market_type,
            price=price,
            stop_price=stop_price
        )

    # @FEAT:webhook-order @FEAT:order-tracking @COMP:service @TYPE:helper
    def _merge_order_with_exchange(self, account: Account, symbol: str,
                                   market_type: str, order_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        거래소에서 최신 주문 정보를 조회하여 로컬 주문 결과와 병합

        Args:
            account: Account 객체
            symbol: 거래 심볼
            market_type: 마켓 유형 (spot/futures)
            order_result: 로컬 주문 결과 딕셔너리

        Returns:
            병합된 주문 정보
        """
        order_id = order_result.get('order_id')
        if not order_id:
            logger.warning("주문 ID가 없어 거래소 조회를 건너뜁니다")
            return order_result

        try:
            # 거래소에서 최신 주문 정보 조회
            fetched_order = exchange_service.fetch_order(
                account=account,
                symbol=symbol,
                order_id=order_id,
                market_type=market_type
            )

            if fetched_order and fetched_order.get('success'):
                # 거래소 데이터로 업데이트 (로컬 데이터 우선 유지)
                merged = {**order_result, **fetched_order}
                logger.debug(f"주문 정보 병합 완료: order_id={order_id}, status={merged.get('status')}")
                return merged
            else:
                logger.warning(f"거래소 주문 조회 실패, 로컬 데이터 사용: order_id={order_id}")
                return order_result

        except Exception as e:
            logger.error(f"주문 정보 병합 중 오류: {e}, 로컬 데이터 사용")
            return order_result

    # @FEAT:market-order-fill @COMP:service @TYPE:helper
    def _handle_market_order_immediate_fill(
        self,
        account: Account,
        strategy_account: StrategyAccount,
        order_id: str,
        symbol: str,
        side: str,
        order_type: str,
        market_type: str
    ) -> Dict[str, Any]:
        """
        MARKET 주문 즉시 체결 확인 및 처리 (지수 백오프 재시도)

        Phase 1 변경사항:
        - 0.5초 고정 지연 제거
        - 지수 백오프 재시도 로직 추가 (125ms → 250ms → 500ms → 1s → 2s, 총 3.9초, 최대 5회)
        - 환경 변수 기반 Feature Flag (롤백 용이성)
        - 4번째 재시도부터 경고 로그 (거래소 서버 상태 모니터링)

        Args:
            account: Account 객체
            strategy_account: StrategyAccount 객체
            order_id: 거래소 주문 ID
            symbol: 거래 심볼 (예: "BTC/USDT")
            side: 주문 방향 ("buy" or "sell")
            order_type: 주문 타입 ("MARKET")
            market_type: 시장 타입 ("futures" or "spot")

        Returns:
            Dict[str, Any]: {
                'filled': bool,  # 체결 성공 여부
                'fill_summary': Dict or None,  # 체결 처리 결과
                'filled_order': Dict or None  # 체결된 주문 정보
            }
        """
        logger.info(f"⏱️ MARKET 주문 즉시 체결 확인: order_id={order_id}, symbol={symbol}")

        # 환경 변수 로딩
        delay_ms = int(os.getenv('MARKET_ORDER_DELAY_MS', '0'))
        retry_delays_str = os.getenv('MARKET_ORDER_RETRY_DELAYS_MS', '125,250,500,1000,2000')
        max_retries = int(os.getenv('MAX_MARKET_ORDER_RETRIES', '5'))

        try:
            # 옵션: 초기 지연 (기본값 0, 롤백 시 500)
            if delay_ms > 0:
                logger.debug(f"⏳ MARKET 주문 초기 지연: {delay_ms}ms")
                time.sleep(delay_ms / 1000.0)

            # 재시도 간격 파싱 및 최대 재시도 횟수 제한
            retry_delays = _parse_retry_delays(retry_delays_str)
            retry_delays = retry_delays[:max_retries]  # MAX_RETRIES로 제한

            # ✅ Priority 1: 빈 리스트 방지 (최소 1회 시도 보장)
            if not retry_delays:
                logger.error(
                    "❌ 재시도 간격이 비어있습니다 (MAX_RETRIES=0 또는 잘못된 설정). "
                    "최소 1회 시도 보장을 위해 [0.0] 사용"
                )
                retry_delays = [0.0]  # 즉시 1회 시도

            # 지수 백오프 재시도 로직
            filled_order = None
            market_order_fill_start = time.time()

            for attempt in range(len(retry_delays)):
                # 거래소에서 최신 주문 상태 조회
                filled_order = exchange_service.fetch_order(
                    account=account,
                    symbol=symbol,
                    order_id=order_id,
                    market_type=market_type
                )

                # 체결 확인 (status + filled_quantity 검증)
                if filled_order:
                    filled_qty = filled_order.get('filled_quantity', 0)
                    order_status = (filled_order.get('status') or '').upper()

                    if order_status in ['CLOSED', 'FILLED'] and filled_qty > 0:
                        # ✅ 체결 성공
                        market_order_fill_end = time.time()
                        duration_ms = round((market_order_fill_end - market_order_fill_start) * 1000, 2)

                        logger.info(
                            f"✅ MARKET 주문 체결 확인 완료: order_id={order_id}, "
                            f"duration={duration_ms}ms, retries={attempt + 1}/{len(retry_delays)}"
                        )
                        break

                # 재시도 로직 (마지막 시도가 아닐 경우)
                if attempt < len(retry_delays) - 1:
                    retry_delay = retry_delays[attempt]

                    # 4번째 재시도부터 경고 로그 (거래소 서버 상태 의심)
                    if attempt >= 3:
                        logger.warning(
                            f"🚨 MARKET 주문 체결 확인 장기 지연 (재시도 {attempt + 1}/{len(retry_delays)}): "
                            f"order_id={order_id}, "
                            f"status={filled_order.get('status') if filled_order else 'None'}, "
                            f"filled_qty={filled_order.get('filled_quantity', 0) if filled_order else 0}, "
                            f"거래소 서버 상태 불안정 의심, "
                            f"다음 대기: {retry_delay * 1000}ms"
                        )
                    else:
                        logger.warning(
                            f"⚠️ MARKET 주문 체결 미확인 (재시도 {attempt + 1}/{len(retry_delays)}): "
                            f"order_id={order_id}, "
                            f"status={filled_order.get('status') if filled_order else 'None'}, "
                            f"filled_qty={filled_order.get('filled_quantity', 0) if filled_order else 0}, "
                            f"다음 대기: {retry_delay * 1000}ms"
                        )
                    time.sleep(retry_delay)

            # 최종 체결 확인 실패
            if not filled_order:
                logger.error(
                    f"❌ MARKET 주문 상태 조회 실패 ({len(retry_delays)}회 재시도): "
                    f"order_id={order_id}"
                )
                return {
                    'filled': False,
                    'fill_summary': None,
                    'filled_order': None
                }

            filled_qty = filled_order.get('filled_quantity', 0)
            order_status = (filled_order.get('status') or '').upper()

            if order_status not in ['CLOSED', 'FILLED'] or filled_qty <= 0:
                logger.warning(
                    f"⚠️ MARKET 주문 체결 미완료 ({len(retry_delays)}회 재시도): "
                    f"order_id={order_id}, status={order_status}, filled_qty={filled_qty}"
                )
                return {
                    'filled': False,
                    'fill_summary': None,
                    'filled_order': None
                }

            # ✅ 체결 처리 (기존 로직 유지)
            logger.info(
                f"🎯 MARKET 주문 체결 감지: order_id={order_id}, "
                f"filled_qty={filled_qty}"
            )

            fill_summary = self.service.position_manager.process_order_fill(
                strategy_account=strategy_account,
                order_id=order_id,
                symbol=symbol,
                side=side,
                order_type=order_type,
                order_result=filled_order,
                market_type=market_type
            )

            if fill_summary.get('success'):
                logger.info(
                    f"✅ MARKET 주문 즉시 체결 처리 완료: order_id={order_id}"
                )
                return {
                    'filled': True,
                    'fill_summary': fill_summary,
                    'filled_order': filled_order
                }
            else:
                logger.warning(
                    f"⚠️ 재시도 체결 처리 실패, OpenOrder로 저장: order_id={order_id}"
                )
                return {
                    'filled': False,
                    'fill_summary': None,
                    'filled_order': None
                }

        except Exception as e:
            logger.error(
                f"❌ MARKET 주문 즉시 체결 확인 실패: order_id={order_id}, "
                f"symbol={symbol}, error={type(e).__name__}: {str(e)}",
                exc_info=True
            )
            return {
                'filled': False,
                'fill_summary': None,
                'filled_order': None
            }

    # @FEAT:webhook-order @COMP:service @TYPE:core
    def process_trading_signal(self, webhook_data: Dict[str, Any],
                               timing_context: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """거래 신호 처리"""
        from app.services.utils import to_decimal

        # 필수 필드 검증 (market_type은 webhook_service에서 주입됨, exchange는 Strategy 연동 계좌에서 자동 결정)
        required_fields = ['group_name', 'symbol', 'order_type']
        for field in required_fields:
            if field not in webhook_data:
                raise Exception(f"필수 필드 누락: {field}")

        # market_type 검증 (webhook_service에서 주입되어야 함)
        if 'market_type' not in webhook_data:
            raise Exception("market_type이 필요합니다 (내부 호출 시 주입되어야 함)")

        # side 검증 (CANCEL_ALL_ORDER, CANCEL 제외 필수)
        order_type = webhook_data.get('order_type')
        if order_type not in ['CANCEL_ALL_ORDER', 'CANCEL'] and 'side' not in webhook_data:
            raise Exception("필수 필드 누락: side")

        group_name = webhook_data['group_name']
        market_type = webhook_data['market_type']
        symbol = webhook_data['symbol']
        order_type = webhook_data['order_type']
        side = webhook_data.get('side')  # CANCEL_ALL_ORDER는 side 없음
        price = to_decimal(webhook_data.get('price')) if webhook_data.get('price') else None
        stop_price = to_decimal(webhook_data.get('stop_price')) if webhook_data.get('stop_price') else None
        qty_per = to_decimal(webhook_data.get('qty_per', 100))

        # STOP_LIMIT 주문 필수 필드 검증
        if order_type == 'STOP_LIMIT':
            if not stop_price:
                raise Exception("STOP_LIMIT 주문: stop_price가 필수입니다")
            if not price:
                raise Exception("STOP_LIMIT 주문: price가 필수입니다")

        logger.info(f"거래 신호 처리 시작 - 전략: {group_name}, 심볼: {symbol}, "
                   f"사이드: {side}, 주문타입: {order_type}, 수량비율: {qty_per}%")

        # 전략 조회
        strategy = Strategy.query.filter_by(group_name=group_name, is_active=True).first()
        if not strategy:
            raise Exception(f"활성 전략을 찾을 수 없습니다: {group_name}")

        logger.info(f"전략 조회 성공 - ID: {strategy.id}, 이름: {strategy.name}, 마켓타입: {strategy.market_type}")

        # 전략에 연결된 계좌들 조회
        strategy_accounts = strategy.strategy_accounts
        if not strategy_accounts:
            raise Exception(f"전략에 연결된 계좌가 없습니다: {group_name}")

        logger.info(f"전략에 연결된 계좌 수: {len(strategy_accounts)}")

        # 계좌 필터링 (활성 계좌만, exchange는 모두 허용)
        filtered_accounts = []
        seen_exchanges = {}  # 중복 거래소 감지용

        for sa in strategy_accounts:
            account = sa.account

            if hasattr(sa, 'is_active') and not sa.is_active:
                continue
            if not account or not account.is_active:
                continue

            # exchange 필터링 제거 - Strategy 연동 모든 계좌에서 주문 실행
            # 중복 거래소 경고 (사용자 관리 권장)
            exchange_key = f"{account.exchange}_{market_type}"
            if exchange_key in seen_exchanges:
                logger.warning(
                    f"⚠️ 중복 거래소 감지: {account.exchange} (마켓: {market_type}) - "
                    f"계좌: {account.name}, 기존: {seen_exchanges[exchange_key]} | "
                    f"의도하지 않은 중복 주문을 방지하려면 전략에 동일 거래소 계좌를 중복 연동하지 마세요."
                )
            seen_exchanges[exchange_key] = account.name

            filtered_accounts.append((strategy, account, sa))

        logger.info(f"거래 실행 대상 계좌: {len(filtered_accounts)}")

        # 병렬 거래 실행
        results = []
        if filtered_accounts:
            results = self._execute_trades_parallel(
                filtered_accounts, symbol, side, order_type, price, stop_price, qty_per, market_type, timing_context
            )

        successful_trades = [r for r in results if r.get('success', False)]
        failed_trades = [r for r in results if not r.get('success', False)]

        logger.info(f"거래 신호 처리 완료 - 성공: {len(successful_trades)}, 실패: {len(failed_trades)}")

        # 🆕 Phase 2: 단일 주문도 배치 SSE 발송 (배치 주문과 통일)
        # @FEAT:toast-ux-improvement @COMP:service @TYPE:integration @DEPS:webhook-order
        if len(successful_trades) > 0 and self.service.event_emitter:
            # results에서 order_type, event_type 메타데이터가 있는 항목만 필터링
            # LIMIT/STOP 주문은 _execute_trades_parallel()에서 메타데이터 포함
            # MARKET 주문은 메타데이터 없음 (자연스럽게 제외)
            batch_results = [
                result for result in results
                if result.get('success') and result.get('order_type') and result.get('event_type')
            ]

            # 배치 SSE 발송 (메타데이터가 있는 경우만)
            if batch_results:
                self.service.event_emitter.emit_order_batch_update(
                    user_id=strategy.user_id,
                    strategy_id=strategy.id,
                    batch_results=batch_results
                )

        # @FEAT:webhook-order @COMP:service @TYPE:core
        # @DATA:successful_orders,failed_orders - 통계 필드명 (2025-10-30 통일)
        # 표준 응답 포맷 (process_cancel_all_orders와 동일한 구조)
        return {
            'action': side.lower(),  # 'buy' or 'sell'
            'strategy': group_name,
            'market_type': market_type,
            'success': len(successful_trades) > 0,
            'results': results,
            'summary': {
                'total_accounts': len(filtered_accounts),
                'executed_accounts': len(results),
                'successful_orders': len(successful_trades),
                'failed_orders': len(failed_trades),
                'inactive_accounts': len(strategy_accounts) - len(filtered_accounts)
            }
        }

    # @FEAT:batch-order-race-condition @FEAT:order-queue @COMP:service @TYPE:core @DEPS:order-tracking,exchange-integration
    def _execute_trades_parallel(self, filtered_accounts: List[tuple], symbol: str,
                                 side: str, order_type: str, price: Optional[Decimal],
                                 stop_price: Optional[Decimal], qty_per: Decimal,
                                 market_type: str,
                                 timing_context: Optional[Dict[str, float]] = None) -> List[Dict[str, Any]]:
        """
        배치 주문 병렬 실행 (타입 그룹별 분리)

        Issue #10: Lock 기반 Race Condition 방지
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        배치 주문 생성 시 동시 접근을 Lock으로 차단합니다.

        Lock 획득 전략:
        - 대상: LIMIT/STOP 주문 (거래소 즉시 실행)
        - 제외: MARKET 주문 (즉시 거래소 실행, Lock 불필요)
        - Deadlock 방지: (account_id, symbol) 튜플 정렬 순서로 Lock 획득
        - Lock 범위: 거래소 주문 실행 + 배치 커밋 + SSE 발송
        - 자동 해제: contextlib.ExitStack으로 예외 시에도 Lock 해제 보장

        처리 흐름:
        1. 타입 그룹 확인 (LIMIT/STOP/MARKET)
        2. LIMIT/STOP: Lock 획득 → 배치 주문 생성 → Lock 해제
        3. MARKET: Lock 없이 즉시 실행

        Args:
            filtered_accounts (List[tuple]): (strategy, account, strategy_account) 튜플 리스트
            symbol (str): 거래 심볼
            side (str): 주문 방향 ('BUY' 또는 'SELL')
            order_type (str): 주문 타입 ('MARKET', 'LIMIT', 'STOP' 등)
            price (Optional[Decimal]): LIMIT 주문 가격
            stop_price (Optional[Decimal]): STOP 주문 트리거 가격
            qty_per (Decimal): 계좌별 주문 수량 (%)
            market_type (str): 마켓 유형
            timing_context (Optional[Dict[str, float]]): 웹훅 타이밍 정보

        Returns:
            List[Dict[str, Any]]: [
                {
                    'success': bool,
                    'account_id': int,
                    'account_name': str,
                    'message': str,
                    'pending_order_id': Optional[int],  # LIMIT/STOP만
                    'priority': Optional[int],
                    'order_type': str,
                    'event_type': str,
                    'queued': Optional[bool],  # LIMIT/STOP만
                    'error': Optional[str]
                },
                ...
            ]

        Side Effects:
        - db.session.commit() 호출 (배치 커밋)
        - PendingOrder SSE 이벤트 발송
        - 재정렬 알고리즘 Lock 획득/해제

        Performance:
        - ThreadPoolExecutor: max(min(10, account_count)) 병렬 처리
        - Lock 보유 시간: ThreadPoolExecutor 완료까지 (개별 함수 선택)
        - Lock 정렬: (account_id, symbol) 조합 정렬으로 Deadlock 방지
        """
        results = []
        max_workers = min(10, len(filtered_accounts))

        # Flask app context를 미리 캡처
        app = current_app._get_current_object()

        # Phase 4: LIMIT/STOP 주문 타입 그룹 확인
        from app.constants import ORDER_TYPE_GROUPS

        type_group = None
        for group_name, types in ORDER_TYPE_GROUPS.items():
            if order_type.upper() in types:
                type_group = group_name
                break

        # ✅ Issue #10: 배치 주문 실행 로직 (enqueue 내부에서 자동 Lock 보호)
        def _execute_batch_logic():
            """
            배치 주문 실행 로직 (모든 주문 타입 공통)

            Issue #10: enqueue 내부에서 심볼별 Lock 자동 획득
            - 단일 주문: enqueue(commit=True) → 자동 Lock 보호
            - 배치 주문: enqueue(commit=False) × N → 자동 Lock 보호
            - 리밸런서: _move_to_pending() → 자동 Lock 보호

            처리 단계:
            1. ThreadPoolExecutor로 병렬 enqueue (commit=False)
            2. 배치 커밋 (db.session.commit())
            3. SSE 일괄 발송

            Returns:
                None (results는 외부 스코프 변수에 추가)

            Side Effects:
            - db.session.commit()
            - PendingOrder SSE 이벤트 발송
            - results 리스트 업데이트 (외부 스코프)
            """
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {}
                for strategy, account, sa in filtered_accounts:
                    # qty_per를 실제 주문 수량으로 변환
                    try:
                        calculated_quantity = self.service.quantity_calculator.calculate_order_quantity(
                            strategy_account=sa,
                            qty_per=qty_per,
                            symbol=symbol,
                            order_type=order_type,
                            market_type=market_type,
                            price=price,
                            stop_price=stop_price,
                            side=side
                        )

                        if calculated_quantity == Decimal('0'):
                            logger.warning(f"계좌 {account.id}: 수량 계산 결과 0, 주문 스킵")
                            results.append({
                                'success': False,
                                'error': '계산된 주문 수량이 0입니다',
                                'account_id': account.id,
                                'skipped': True
                            })
                            continue

                        logger.debug(f"계좌 {account.id}: qty_per {qty_per}% → quantity {calculated_quantity}")

                    except Exception as calc_error:
                        logger.error(f"계좌 {account.id}: 수량 계산 실패 - {calc_error}")
                        results.append({
                            'success': False,
                            'error': f'수량 계산 실패: {calc_error}',
                            'account_id': account.id
                        })
                        continue

                    # Phase 4: 모든 주문 타입을 즉시 거래소에 제출 (Queue 제거)
                    # LIMIT/STOP/MARKET/CANCEL 주문: 모두 즉시 거래소 제출
                    def execute_in_context(app, strategy, account, sa, symbol, side, calculated_quantity, order_type, price, stop_price, timing_context):
                        with app.app_context():
                            return self.execute_trade(
                                strategy=strategy,
                                symbol=symbol,
                                side=side,
                                quantity=calculated_quantity,  # ✅ 변환된 수량 사용
                                order_type=order_type,
                                price=price,
                                stop_price=stop_price,
                                strategy_account_override=sa,
                                timing_context=timing_context
                            )

                    future = executor.submit(
                        execute_in_context,
                        app, strategy, account, sa, symbol, side, calculated_quantity, order_type, price, stop_price, timing_context
                    )
                    futures[future] = (strategy, account, sa)

                for future in as_completed(futures):
                    strategy, account, sa = futures[future]
                    try:
                        result = future.result(timeout=30)
                        results.append(result)
                    except Exception as e:
                        logger.error(f"거래 실행 실패 (계좌 {account.id}): {e}")
                        results.append({
                            'success': False,
                            'error': str(e),
                            'account_id': account.id
                        })

            # Phase 4: 배치 커밋 (거래소 주문만)
            db.session.commit()

        # ✅ Issue #10: enqueue 내부에서 자동으로 Lock 획득하므로 여기서는 불필요
        _execute_batch_logic()

        return results

    # @FEAT:webhook-order @COMP:service @TYPE:helper
    def _prepare_batch_orders_by_account(
        self,
        strategy: Strategy,
        orders: List[Dict[str, Any]],
        market_type: str,
        timing_context: Optional[Dict[str, float]] = None
    ) -> Dict[int, Dict[str, Any]]:
        """
        배치 주문을 계좌별로 그룹화하고 Exchange 형식으로 변환

        Args:
            strategy: Strategy 객체
            orders: 웹훅 배치 주문 리스트 (원본 형식)
            market_type: 'SPOT' or 'FUTURES'
            timing_context: 타이밍 측정 딕셔너리

        Returns:
            {
                account_id: {
                    'account': Account 객체,
                    'strategy_account': StrategyAccount 객체,
                    'orders': [
                        {
                            'symbol': 'BTC/USDT',
                            'side': 'buy',
                            'type': 'LIMIT',
                            'amount': Decimal('0.01'),
                            'price': Decimal('95000'),
                            'params': {'stopPrice': Decimal('...')}
                        },
                        ...
                    ],
                    'timing_context': {  # Snapshot 쿼리용 webhook_received_at 포함
                        'webhook_received_at': float (Unix timestamp)
                    }
                },
                ...
            }
        """
        from app.services.utils import to_decimal

        orders_by_account = {}

        # 전략의 모든 활성 계좌 순회
        strategy_accounts = strategy.strategy_accounts
        if not strategy_accounts:
            logger.warning(f"전략 {strategy.name}에 연결된 계좌가 없습니다")
            return {}

        for sa in strategy_accounts:
            account = sa.account

            # 활성 계좌만 필터링
            if hasattr(sa, 'is_active') and not sa.is_active:
                continue
            if not account or not account.is_active:
                continue

            account_orders = []

            # 각 주문에 대해 처리
            for order in orders:
                try:
                    # 필수 필드 추출
                    symbol = order.get('symbol')
                    side = order.get('side')
                    order_type = order.get('order_type')
                    qty_per = to_decimal(order.get('qty_per', 100))
                    price = to_decimal(order.get('price')) if order.get('price') else None
                    stop_price = to_decimal(order.get('stop_price')) if order.get('stop_price') else None
                    original_index = order.get('original_index')  # ✅ 인덱스 추출

                    # qty_per를 실제 수량으로 변환
                    calculated_quantity = self.service.quantity_calculator.calculate_order_quantity(
                        strategy_account=sa,
                        qty_per=qty_per,
                        symbol=symbol,
                        order_type=order_type,
                        market_type=market_type.lower(),  # 'FUTURES' → 'futures'
                        price=price,
                        stop_price=stop_price,
                        side=side
                    )

                    # 수량이 0이면 스킵
                    if calculated_quantity == Decimal('0'):
                        logger.warning(
                            f"계좌 {account.name}: 수량 계산 결과 0, 주문 스킵 "
                            f"(symbol={symbol}, qty_per={qty_per}%)"
                        )
                        continue

                    logger.debug(
                        f"계좌 {account.name}: {symbol} qty_per {qty_per}% → quantity {calculated_quantity}"
                    )

                    # Exchange 표준 형식으로 변환
                    exchange_order = {
                        'symbol': symbol,  # 표준 형식 유지 (BTC/USDT)
                        'side': side.lower(),  # 'buy' or 'sell'
                        'type': order_type,  # 'LIMIT', 'MARKET', etc.
                        'amount': calculated_quantity,  # 수량 계산 완료
                        'original_index': original_index  # ✅ 인덱스 보존
                    }

                    # 조건부 파라미터 추가
                    if price is not None:
                        exchange_order['price'] = price

                    # params 딕셔너리로 stop_price 전달
                    params = {}
                    if stop_price is not None:
                        params['stopPrice'] = stop_price

                    if params:
                        exchange_order['params'] = params

                    account_orders.append(exchange_order)

                except Exception as calc_error:
                    logger.error(
                        f"계좌 {account.name}: 주문 준비 실패 - {calc_error} "
                        f"(symbol={order.get('symbol')})"
                    )
                    continue

            # 계좌별 그룹화 저장 (주문이 있는 경우만)
            if account_orders:
                # @FEAT:webhook-order @COMP:service @TYPE:helper
                # timing_context 배치 플로우 전달: webhook_received_at 추출용
                orders_by_account[account.id] = {
                    'account': account,
                    'strategy_account': sa,
                    'orders': account_orders,
                    'timing_context': timing_context  # ✅ Pass timing_context through batch flow
                }

        logger.info(
            f"📦 배치 주문 준비 완료: {len(orders_by_account)}개 계좌, "
            f"총 {sum(len(data['orders']) for data in orders_by_account.values())}개 주문"
        )

        return orders_by_account

    # @FEAT:batch-parallel-processing @FEAT:webhook-order @COMP:service @TYPE:core
    def process_batch_trading_signal(self, webhook_data: Dict[str, Any],
                                     timing_context: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """
        배치 거래 신호 처리 (Exchange 배치 API 활용 + ThreadPoolExecutor 병렬 처리)

        Phase 2 개선사항:
        - 계좌별 병렬 처리로 성능 50% 향상 (651ms vs 1302ms 예상)
        - ThreadPoolExecutor 기반 비블로킹 실행
        - Flask app context 안전성 보장
        - 환경 변수 기반 타임아웃 (BATCH_ACCOUNT_TIMEOUT_SEC)
        """
        from app.services.utils import to_decimal
        from app.constants import OrderType

        # 필수 필드 검증 (exchange, market_type은 strategy에서 가져옴)
        required_fields = ['group_name', 'orders']
        for field in required_fields:
            if field not in webhook_data:
                raise Exception(f"필수 필드 누락: {field}")

        group_name = webhook_data['group_name']
        orders = webhook_data['orders']

        if not isinstance(orders, list) or len(orders) == 0:
            raise Exception("orders 필드는 비어있지 않은 배열이어야 합니다")

        logger.info(f"배치 거래 신호 처리 시작 - 전략: {group_name}, 주문 수: {len(orders)}")

        # 배치 주문 order_type 사전 검증 (정렬 전 필수)
        for idx, order in enumerate(orders):
            if not isinstance(order, dict):
                raise Exception(f"배치 주문 {idx + 1}번째가 올바른 형식이 아닙니다 (dict 필요)")
            if not order.get('order_type'):
                raise Exception(f"배치 주문 {idx + 1}번째에 order_type이 필요합니다")

        # Strategy 조회 및 market_type 가져오기
        from app.models import Strategy
        from app.constants import MarketType

        strategy = Strategy.query.filter_by(group_name=group_name, is_active=True).first()
        if not strategy:
            raise Exception(f"활성 전략을 찾을 수 없습니다: {group_name}")

        market_type = strategy.market_type or MarketType.SPOT
        logger.info(f"전략 조회 성공 - ID: {strategy.id}, 마켓타입: {market_type}")

        # 🆕 우선순위 기반 정렬 (CANCEL_ALL_ORDER 최우선)
        sorted_orders_with_idx = sorted(
            enumerate(orders),
            key=lambda x: OrderType.get_priority(x[1]['order_type'])
        )

        logger.info(f"📊 주문 우선순위 정렬 완료:")
        for original_idx, order in sorted_orders_with_idx:
            order_type = order.get('order_type', 'UNKNOWN')
            priority = OrderType.get_priority(order_type)
            logger.info(f"  - [{original_idx}] {order_type} (우선순위: {priority})")

        # CANCEL_ALL_ORDER와 거래 주문 분리
        cancel_orders = [
            order for order in sorted_orders_with_idx
            if order[1].get('order_type') == OrderType.CANCEL_ALL_ORDER
        ]
        trading_orders = [
            order for order in sorted_orders_with_idx
            if order[1].get('order_type') != OrderType.CANCEL_ALL_ORDER
        ]

        # 결과 저장
        results = []

        # 1. CANCEL_ALL_ORDER 처리 (기존 로직 유지)
        for original_idx, order in cancel_orders:
            try:
                symbol = order.get('symbol')
                side = order.get('side')  # 선택적

                logger.info(f"🔄 배치 내 CANCEL_ALL_ORDER 처리 - symbol: {symbol}, side: {side or '전체'}")

                # strategy의 모든 활성 계좌에 대해 취소 처리
                from app.models import StrategyAccount
                strategy_accounts = StrategyAccount.query.filter_by(
                    strategy_id=strategy.id
                ).all()

                cancel_results = []
                for sa in strategy_accounts:
                    account = sa.account
                    if not account or not account.is_active:
                        continue

                    # order_manager.cancel_all_orders_by_user() 호출
                    try:
                        cancel_result = self.service.order_manager.cancel_all_orders_by_user(
                            user_id=account.user_id,
                            strategy_id=strategy.id,
                            account_id=account.id,
                            symbol=symbol,
                            side=side,
                            timing_context=timing_context
                        )
                        cancel_results.append({
                            'account_id': account.id,
                            'account_name': account.name,
                            **cancel_result
                        })
                    except Exception as cancel_error:
                        logger.error(f"계좌 {account.id} 주문 취소 실패: {cancel_error}")
                        cancel_results.append({
                            'account_id': account.id,
                            'account_name': account.name,
                            'success': False,
                            'error': str(cancel_error)
                        })

                # 결과 집계
                successful_cancels = [r for r in cancel_results if r.get('success')]
                result = {
                    'action': 'cancel_all_orders',
                    'strategy': group_name,
                    'symbol': symbol,
                    'side': side,
                    'success': len(successful_cancels) > 0,
                    'results': cancel_results,
                    'summary': {
                        'total_accounts': len(cancel_results),
                        'successful_accounts': len(successful_cancels),
                        'failed_accounts': len(cancel_results) - len(successful_cancels)
                    }
                }

                # Phase 2: Calculate total cancelled orders for batch SSE
                # @FEAT:webhook-order @COMP:service @TYPE:core
                # Bug Fix: Type-safe handling of cancelled_orders (can be List[Dict] or int)
                total_cancelled = 0
                for r in successful_cancels:
                    cancelled = r.get('cancelled_orders', [])
                    if isinstance(cancelled, list):
                        total_cancelled += len(cancelled)
                    elif isinstance(cancelled, int):
                        total_cancelled += cancelled
                    else:
                        logger.warning(
                            f"Unexpected type for cancelled_orders: {type(cancelled)}, "
                            f"account_id={r.get('account_id')}"
                        )

                results.append({
                    'order_index': original_idx,
                    'success': result.get('success', False),
                    'result': result,
                    'order_type': 'CANCEL_ALL_ORDER',
                    'event_type': 'order_cancelled',
                    'cancelled_count': total_cancelled
                })
            except Exception as e:
                logger.error(f"배치 주문 {original_idx} (CANCEL_ALL_ORDER) 처리 실패: {e}")
                results.append({
                    'order_index': original_idx,
                    'success': False,
                    'error': str(e)
                })

        # 2. 거래 주문을 계좌별로 그룹화 및 변환
        if trading_orders:
            trading_order_list = [order for _, order in trading_orders]
            orders_by_account = self._prepare_batch_orders_by_account(
                strategy, trading_order_list, market_type, timing_context
            )

            # 빈 계좌 체크 (strategy.strategy_accounts가 비었을 경우 방어)
            if not orders_by_account:
                logger.warning(
                    f"⚠️ Strategy '{group_name}'에 활성 계좌가 없습니다. "
                    f"strategy_id={strategy.id}, user_id={strategy.user_id}"
                )
                return {
                    'action': 'batch_order',
                    'strategy': group_name,
                    'success': False,
                    'error': '활성 계좌가 없습니다. 전략 설정을 확인하세요.',
                    'results': [],
                    'summary': {
                        'total_orders': len(orders),
                        'executed_orders': 0,
                        'successful_orders': 0,
                        'failed_orders': 0
                    }
                }

            # 3. 계좌별 배치 주문 병렬 실행 (Phase 2: ThreadPoolExecutor)
            # max_workers 방어: 최소 1 보장 (len(orders_by_account) == 0 방지)
            max_workers = max(1, min(10, len(orders_by_account)))
            app = current_app._get_current_object()  # Flask app context 캡처
            batch_start = time.time()  # 성능 측정 시작

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {}

                for account_id, account_data in orders_by_account.items():
                    # Flask app context 전달 함수
                    def execute_account_batch_in_context(app, account_data, market_type, strategy, trading_orders):
                        with app.app_context():
                            return self._execute_account_batch(account_data, market_type, strategy, trading_orders)

                    # Future 제출
                    future = executor.submit(
                        execute_account_batch_in_context,
                        app, account_data, market_type, strategy, trading_orders
                    )
                    futures[future] = account_data

                # 결과 수집 (as_completed로 완료되는 대로 처리)
                # ✅ Priority 1 Fix: as_completed timeout 제거 (각 계좌가 독립적으로 타임아웃)
                # ✅ Priority 2: 환경 변수 기반 타임아웃 (기본 30초)
                for future in as_completed(futures):
                    try:
                        account_results = future.result(timeout=BATCH_ACCOUNT_TIMEOUT_SEC)
                        results.extend(account_results)
                    except Exception as e:
                        account_data = futures[future]
                        account_name = account_data['account'].name
                        logger.error(f"계좌 {account_name} 병렬 처리 실패: {str(e)}")

                        # 해당 계좌의 모든 주문 실패 처리
                        for trading_idx, (original_idx, _) in enumerate(trading_orders):
                            results.append({
                                'order_index': original_idx,
                                'success': False,
                                'result': {
                                    'action': 'trading_signal',
                                    'success': False,
                                    'error': f'병렬 처리 실패: {str(e)}',
                                    'account_id': account_data['account'].id,
                                    'account_name': account_name
                                }
                            })

            # 성능 측정 완료 및 로깅
            batch_end = time.time()
            batch_duration_ms = round((batch_end - batch_start) * 1000, 2)
            logger.info(
                f"📊 배치 병렬 처리 완료: {len(orders_by_account)}개 계좌, "
                f"duration={batch_duration_ms}ms"
            )

        # 4. 기존 집계 로직 유지
        successful = [r for r in results if r.get('success', False)]
        failed = [r for r in results if not r.get('success', False)]

        logger.info(f"배치 거래 신호 처리 완료 - 성공: {len(successful)}, 실패: {len(failed)}")

        # Phase 2: Emit batch SSE event after all orders processed
        if len(successful) > 0:
            self.service.event_emitter.emit_order_batch_update(
                user_id=strategy.user_id,
                strategy_id=strategy.id,
                batch_results=results
            )

        # 표준 응답 포맷
        return {
            'action': 'batch_order',
            'strategy': group_name,
            'success': len(successful) > 0,
            'results': results,
            'summary': {
                'total_orders': len(orders),
                'executed_orders': len(results),
                'successful_orders': len(successful),
                'failed_orders': len(failed)
            }
        }

    # @FEAT:batch-parallel-processing @FEAT:webhook-batch-queue @COMP:service @TYPE:helper
    def _execute_account_batch(
        self,
        account_data: Dict[str, Any],
        market_type: str,
        strategy: Strategy,
        trading_orders: List[tuple]
    ) -> List[Dict[str, Any]]:
        """
        단일 계좌의 배치 주문 처리 (병렬 실행용 헬퍼)

        @FEAT:webhook-batch-queue @COMP:service @TYPE:core Individual commit routing pattern

        Phase 1 Implementation: Intelligent Order Routing with Individual Commits

        Core Pattern:
        - QUEUED_TYPES (LIMIT/STOP_LIMIT/STOP_MARKET) → PendingOrder table (queue)
        - DIRECT_TYPES (MARKET/CANCEL_ALL_ORDER) → Exchange batch API (immediate)

        Individual Commit Strategy (Binance Batch API alignment):
        - Each queue order commits independently (commit=True)
        - Failures don't block subsequent orders (error recovery via continue)
        - Partial success is supported: 5 orders → 3 success, 2 failed is valid
          (vs. all-or-nothing: 1 error = entire batch rollback, 5 orders lost)
        - Reflects real Binance behavior: [success, success, error, success, error]

        Transaction Guarantees:
        - Individual commit: Each order commits independently
        - Error recovery: Failures don't stop processing (continue)
        - Partial success: 5 orders → 3 success, 2 failed is valid
        - SSE emission: After each successful commit

        Error Handling (Individual Commit Pattern):
        - DB commit failure: Order skipped, error logged, next order continues
        - SSE emission failure: Non-blocking warning (order processing unaffected)
        - No batch rollback: Successfully committed orders persist in PendingOrder table
        - Example: Order 1 success → Order 2 commit fails → Order 3 continues

        Phase 2 enhancements:
        - DRY: Reuses existing enqueue/direct execution logic (no code duplication)
        - Parallel execution: ThreadPoolExecutor for multi-account batches
        - Rate limiting: account_id passed to exchange_service for Phase 0 integration

        Args:
            account_data: {'account': Account, 'strategy_account': StrategyAccount, 'orders': List[Dict], 'timing_context': Optional[Dict] - 타이밍 정보 (webhook_received_at 포함)}
            market_type: 'SPOT' or 'FUTURES'
            strategy: Strategy 객체
            trading_orders: [(original_idx, order), ...] 원본 인덱스 매핑용

        Returns:
            List[Dict]: Combined success and failed results
            - success=True: Order queued, includes pending_order_id
            - success=False: Order failed, includes error message
        """
        account = account_data['account']
        strategy_account = account_data['strategy_account']
        exchange_orders = account_data['orders']
        # @FEAT:webhook-order @COMP:service @TYPE:helper
        # timing_context 배치 실행 단계 추출: webhook_received_at을 OpenOrder에 저장
        timing_context = account_data.get('timing_context')  # ✅ Extract timing_context
        results = []

        logger.info(
            f"📦 계좌 {account.name} 배치 주문 실행: {len(exchange_orders)}건"
        )

        # 🆕 Phase 5: 배치 실행 직전 is_active 재확인 (Race Condition 방지)
        if hasattr(strategy_account, 'is_active') and not strategy_account.is_active:
            logger.warning(
                f"⚠️ [Phase 5] StrategyAccount {strategy_account.id} 비활성 상태 - "
                f"배치 주문 실행 스킵 (전략: {strategy.group_name}, 계좌: {account.name})"
            )
            # 배치 전체 스킵 (원본 인덱스 매핑)
            for order in exchange_orders:
                original_idx = order.get('original_index', 0)
                results.append({
                    'order_index': original_idx,
                    'success': False,
                    'error': 'StrategyAccount가 비활성 상태입니다',
                    'error_type': 'account_inactive',
                    'account_id': account.id,
                    'account_name': account.name,
                    'strategy_account_id': strategy_account.id,
                    'skipped': True,
                    'skip_reason': 'strategy_account_inactive',
                    'batch_skipped': True
                })
            return results

        # @FEAT:webhook-order @COMP:service @TYPE:core
        # Phase 4: 모든 주문 타입을 즉시 거래소에 제출 (Queue 시스템 제거)
        # LIMIT/STOP/MARKET/CANCEL 모두 direct_orders로 처리
        direct_orders = exchange_orders  # 모든 주문을 즉시 실행

        logger.info(f"Phase 4: All orders immediate execution - Total: {len(direct_orders)}")

        # Phase 4: 모든 주문을 즉시 거래소에 제출
        if not direct_orders:
            return results

        try:
            # CRITICAL FIX: account_id 전달 (Phase 0 Rate Limiting 활성화)
            batch_result = exchange_service.create_batch_orders(
                account=account,
                orders=direct_orders,  # Only MARKET/CANCEL
                market_type=market_type.lower(),
                account_id=account.id  # ✅ 필수 파라미터
            )

            # 결과 로깅
            if batch_result.get('success'):
                implementation = batch_result.get('implementation', 'UNKNOWN')
                summary = batch_result.get('summary', {})
                logger.info(
                    f"✅ 계좌 {account.name} 배치 완료: "
                    f"{implementation} - "
                    f"성공 {summary.get('successful', 0)}/{summary.get('total', 0)}"
                )
            else:
                logger.error(
                    f"❌ 계좌 {account.name} 배치 실패: {batch_result.get('error')}"
                )

            # 결과 처리 (direct_orders 기준으로 수정)
            batch_results = batch_result.get('results', [])
            for result_item in batch_results:
                batch_order_idx = result_item.get('order_index', 0)

                if batch_order_idx >= len(direct_orders):
                    logger.warning(f"⚠️ 잘못된 order_index: {batch_order_idx}")
                    continue

                direct_order = direct_orders[batch_order_idx]

                # exchange_orders에서 원본 인덱스 찾기
                original_idx = exchange_orders.index(direct_order)

                if result_item.get('success'):
                    order_data = result_item.get('order', {})

                    logger.info(
                        f"✅ 배치 주문 성공 - 계좌: {account.name}, 심볼: {direct_order['symbol']}, "
                        f"주문ID: {order_data.get('id')}"
                    )

                    # order_id 매핑
                    if 'id' in order_data and 'order_id' not in order_data:
                        order_data['order_id'] = order_data['id']
                    if 'account_id' not in order_data:
                        order_data['account_id'] = account.id

                    # MARKET 주문 즉시 체결 확인
                    if direct_order['type'].upper() == 'MARKET':
                        immediate_fill_result = self._handle_market_order_immediate_fill(
                            account=account,
                            strategy_account=account_data['strategy_account'],
                            order_id=order_data.get('order_id'),
                            symbol=direct_order['symbol'],
                            side=direct_order['side'],
                            order_type=direct_order['type'],
                            market_type=market_type.lower()
                        )

                        if immediate_fill_result.get('filled'):
                            filled_order = immediate_fill_result.get('filled_order', {})
                            results.append({
                                'order_index': original_idx,
                                'success': True,
                                'result': {
                                    'action': 'trading_signal',
                                    'success': True,
                                    'order': filled_order,
                                    'order_id': order_data.get('order_id'),
                                    'account_id': account.id,
                                    'account_name': account.name,
                                    'filled_immediately': True
                                }
                            })
                            continue

                    # @FEAT:webhook-order @COMP:service @TYPE:core
                    # OpenOrder 저장 (webhook_received_at 추출 및 전달 - Snapshot 쿼리용)
                    # Note: timing_context은 선택적 (None이면 webhook_received_at = None)
                    # UTC 변환: 전체 시스템이 UTC 기반이므로 utcfromtimestamp 사용
                    webhook_received_at_dt = None
                    if timing_context and 'webhook_received_at' in timing_context:
                        webhook_received_at_dt = datetime.utcfromtimestamp(timing_context['webhook_received_at'])

                    open_order_result = self.service.order_manager.create_open_order_record(
                        strategy_account=account_data['strategy_account'],
                        order_result=order_data,
                        symbol=direct_order['symbol'],
                        side=direct_order['side'],
                        order_type=direct_order['type'],
                        quantity=direct_order['amount'],
                        price=direct_order.get('price'),
                        stop_price=direct_order.get('params', {}).get('stopPrice'),
                        webhook_received_at=webhook_received_at_dt  # ✅ Added for Snapshot query
                    )

                    if open_order_result['success']:
                        logger.info(f"📝 배치 주문 OpenOrder 저장: {order_data.get('id')}")

                        # 심볼 구독
                        try:
                            self.service.subscribe_symbol(account.id, direct_order['symbol'])
                        except Exception as e:
                            logger.warning(
                                f"⚠️ 심볼 구독 실패 (WebSocket health check에서 재시도): "
                                f"계정: {account.id}, 심볼: {direct_order['symbol']}, 오류: {e}"
                            )
                    else:
                        logger.debug(f"OpenOrder 저장 스킵: {open_order_result.get('reason', 'unknown')}")

                    # SSE 이벤트 발송
                    self.service.event_emitter.emit_order_events_smart(
                        strategy,
                        direct_order['symbol'],
                        direct_order['side'],
                        direct_order['amount'],
                        order_data,
                        suppress_toast=True  # 배치 주문: 개별 토스트 억제, 배치 요약만 표시
                    )

                    # Phase 2: Track event metadata for batch SSE aggregation
                    result_entry = {
                        'order_index': original_idx,
                        'success': True,
                        'result': {
                            'action': 'trading_signal',
                            'success': True,
                            'order': order_data,
                            'order_id': result_item.get('order_id'),
                            'account_id': account.id,
                            'account_name': account.name
                        },
                        'order_type': direct_order['type'],
                        'event_type': 'order_created'
                    }
                    results.append(result_entry)
                else:
                    # 실패 처리
                    logger.warning(
                        f"❌ 배치 주문 실패 - 계좌: {account.name}, "
                        f"원인: {result_item.get('error', 'Unknown error')}"
                    )
                    results.append({
                        'order_index': original_idx,
                        'success': False,
                        'result': {
                            'action': 'trading_signal',
                            'success': False,
                            'error': result_item.get('error', 'Unknown error'),
                            'account_id': account.id,
                            'account_name': account.name
                        }
                    })

        except Exception as batch_error:
            logger.error(f"계좌 {account.name} 배치 실행 예외: {batch_error}")

            # 해당 계좌의 모든 주문 실패 처리
            for trading_idx, (original_idx, _) in enumerate(trading_orders):
                results.append({
                    'order_index': original_idx,
                    'success': False,
                    'result': {
                        'action': 'trading_signal',
                        'success': False,
                        'error': f'배치 실행 실패: {batch_error}',
                        'account_id': account.id,
                        'account_name': account.name
                    }
                })

        return results

    # Remaining methods continue as before...
    # (Include all other methods from the original file to maintain functionality)
