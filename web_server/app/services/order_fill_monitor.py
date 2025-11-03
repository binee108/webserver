"""
주문 체결 모니터

WebSocket 이벤트 수신 → REST API 확인 → DB 업데이트 → 재정렬 트리거

@FEAT:order-tracking @FEAT:trade-execution @FEAT:event-sse @COMP:service @TYPE:integration
"""

import asyncio
import logging
from decimal import Decimal
from typing import Dict, Any, Optional
from flask import Flask

from app import db
from app.models import OpenOrder, Account
from app.services.exchange import exchange_service
from app.utils.symbol_utils import (
    from_binance_format,
    from_upbit_format,
    from_bithumb_format,
    SymbolFormatError
)

logger = logging.getLogger(__name__)


# @FEAT:order-tracking @FEAT:trade-execution @COMP:service @TYPE:integration
class OrderFillMonitor:
    """주문 체결 모니터

    핵심 기능:
    1. WebSocket 이벤트 수신 (from BinanceWebSocket/BybitWebSocket)
    2. REST API로 주문 상태 확인 (신뢰도 확보)
    3. DB 업데이트 (OpenOrder 삭제 또는 수정)
    4. OpenOrder 상태 동기화 (Phase 4+)
    """

    def __init__(self, app: Flask):
        self.app = app

    # @FEAT:order-tracking @FEAT:trade-execution @COMP:service @TYPE:core
    async def on_order_update(
        self,
        account_id: int,
        exchange_order_id: str,
        symbol: str,
        status: str
    ):
        """WebSocket 이벤트 수신 시 호출됨

        Args:
            account_id: 계정 ID
            exchange_order_id: 거래소 주문 ID
            symbol: 심볼 (예: "BTCUSDT" - 거래소 네이티브 포맷)
            status: WebSocket에서 받은 상태 (예: "FILLED")
        """
        try:
            logger.info(
                f"📦 주문 업데이트 이벤트 수신 - "
                f"계정: {account_id}, 주문 ID: {exchange_order_id}, "
                f"심볼: {symbol} (원본), 상태: {status}"
            )

            # Step 0: 거래소별 심볼 포맷 정규화
            normalized_symbol = symbol  # 기본값: 원본 유지
            try:
                # 계좌 정보로 거래소 확인
                with self.app.app_context():
                    account = Account.query.get(account_id)
                    if not account:
                        logger.error(f"❌ 계좌를 찾을 수 없음: account_id={account_id}")
                        return

                    exchange_name = account.exchange.upper()

                    # 거래소별 심볼 포맷 변환
                    if exchange_name == 'BINANCE':
                        normalized_symbol = from_binance_format(symbol)  # BTCUSDT → BTC/USDT
                        logger.debug(f"🔄 Binance 심볼 변환: {symbol} → {normalized_symbol}")
                    elif exchange_name == 'UPBIT':
                        normalized_symbol = from_upbit_format(symbol)    # KRW-BTC → BTC/KRW
                        logger.debug(f"🔄 Upbit 심볼 변환: {symbol} → {normalized_symbol}")
                    elif exchange_name == 'BITHUMB':
                        normalized_symbol = from_bithumb_format(symbol)  # KRW-BTC → BTC/KRW
                        logger.debug(f"🔄 Bithumb 심볼 변환: {symbol} → {normalized_symbol}")
                    else:
                        # 알 수 없는 거래소 또는 이미 표준 포맷
                        normalized_symbol = symbol
                        logger.warning(
                            f"⚠️ 알 수 없는 거래소 또는 표준 포맷: "
                            f"exchange={exchange_name}, symbol={symbol}"
                        )

            except SymbolFormatError as e:
                logger.error(
                    f"❌ 심볼 포맷 오류: symbol={symbol}, account_id={account_id}, "
                    f"error={str(e)}",
                    exc_info=True
                )
                # 악의적인 입력 거부
                return
            except Exception as e:
                logger.error(
                    f"❌ 심볼 정규화 실패: symbol={symbol}, account_id={account_id}, "
                    f"error={type(e).__name__}: {str(e)}",
                    exc_info=True
                )
                # 정규화 실패 시 원본 사용 (하위 호환성)
                normalized_symbol = symbol

            # Step 1: REST API로 주문 상태 확인 (정규화된 심볼 사용)
            confirmed_order = await self._confirm_order_status(
                account_id, exchange_order_id, normalized_symbol
            )

            if not confirmed_order:
                logger.warning(
                    f"⚠️ REST API 주문 확인 실패 - "
                    f"주문 ID: {exchange_order_id}, 심볼: {normalized_symbol}, DB 업데이트 스킵"
                )
                return

            # Step 2: DB 업데이트 + 재정렬 (트랜잭션 통합)
            confirmed_status = confirmed_order.get('status', '').upper()

            with self.app.app_context():
                try:
                    # DB 업데이트 (커밋하지 않음)
                    self._update_order_in_db(confirmed_order, commit=False)

                    # Phase 5: 재정렬 로직 완전 제거됨 (Queue 인프라 제거)
                    # 모든 작업 성공 시 한 번에 커밋
                    db.session.commit()

                except Exception as e:
                    db.session.rollback()
                    logger.error(
                        f"❌ WebSocket 트리거 처리 실패 - {normalized_symbol}: {e}",
                        exc_info=True
                    )

        except Exception as e:
            logger.error(f"❌ 주문 업데이트 처리 실패: {e}", exc_info=True)

    # @FEAT:order-tracking @COMP:service @TYPE:integration
    async def _confirm_order_status(
        self,
        account_id: int,
        exchange_order_id: str,
        symbol: str
    ) -> Optional[Dict[str, Any]]:
        """REST API로 주문 상태 확인

        Args:
            account_id: 계정 ID
            exchange_order_id: 거래소 주문 ID
            symbol: 심볼

        Returns:
            dict: 주문 정보 또는 None
            {
                'exchange_order_id': str,
                'status': str,  # 'NEW', 'FILLED', 'CANCELED', etc.
                'filled_quantity': Decimal,
                'average_price': Decimal,
                ...
            }
        """
        try:
            # Flask app context 내에서 실행
            with self.app.app_context():
                # OpenOrder에서 market_type 가져오기 (가장 정확함)
                open_order = OpenOrder.query.filter_by(
                    exchange_order_id=exchange_order_id
                ).first()

                if open_order:
                    market_type = open_order.market_type or 'SPOT'
                else:
                    # OpenOrder가 없으면 기본값 사용 (경고 로그)
                    logger.warning(
                        f"⚠️ OpenOrder를 찾을 수 없음 - order_id: {exchange_order_id}, "
                        f"SPOT 기본값 사용"
                    )
                    market_type = 'SPOT'

                account = Account.query.get(account_id)
                if not account:
                    logger.error(f"❌ 계정을 찾을 수 없습니다: {account_id}")
                    return None

                # REST API로 주문 조회 (5초 타임아웃)
                try:
                    result = await asyncio.wait_for(
                        asyncio.to_thread(
                            exchange_service.fetch_order,
                            account=account,
                            symbol=symbol,
                            order_id=exchange_order_id,
                            market_type=market_type.lower()
                        ),
                        timeout=5.0
                    )

                    if not result or not result.get('success'):
                        logger.error(
                            f"❌ REST API 주문 조회 실패 - "
                            f"주문 ID: {exchange_order_id}, "
                            f"오류: {result.get('error') if result else 'No result'}"
                        )
                        return None

                    # 주문 정보 추출
                    order_info = {
                        'exchange_order_id': exchange_order_id,
                        'status': result.get('status', ''),
                        'filled_quantity': Decimal(str(result.get('filled_quantity', 0))),
                        'average_price': Decimal(str(result.get('average_price', 0))),
                        'side': result.get('side', ''),
                        'order_type': result.get('order_type', '')
                    }

                    logger.info(
                        f"✅ REST API 주문 확인 완료 - "
                        f"주문 ID: {exchange_order_id}, "
                        f"상태: {order_info['status']}"
                    )

                    return order_info

                except asyncio.TimeoutError:
                    logger.error(f"❌ REST API 타임아웃 (5초 초과) - 주문 ID: {exchange_order_id}")
                    return None
                except asyncio.CancelledError:
                    logger.warning(f"⚠️ REST API 요청 취소됨 - 주문 ID: {exchange_order_id}")
                    return None

        except Exception as e:
            logger.error(f"❌ REST API 주문 확인 실패: {e}")
            return None

    # @FEAT:order-tracking @FEAT:limit-order @COMP:service @TYPE:core
    def _check_and_lock_order(self, exchange_order_id: str, order_info: dict) -> tuple:
        """
        Step 1: Optimistic Locking으로 OpenOrder 획득

        Returns:
            (open_order, should_process_fill):
            - open_order이 None이면 이미 처리 중이거나 없음
            - should_process_fill이 True면 process_order_fill() 호출 필요
        """
        from datetime import datetime

        open_order = OpenOrder.query.filter_by(
            exchange_order_id=exchange_order_id,
            is_processing=False
        ).with_for_update(skip_locked=True).first()

        if not open_order:
            return None, False

        open_order.is_processing = True
        open_order.processing_started_at = datetime.utcnow()
        db.session.flush()

        status = order_info.get('status', '').upper()
        should_process_fill = status in ['FILLED', 'PARTIALLY_FILLED']

        return open_order, should_process_fill

    # @FEAT:order-tracking @FEAT:limit-order @COMP:service @TYPE:core
    def _process_fill_for_order(self, open_order: OpenOrder, order_info: dict) -> dict:
        """
        Step 2: process_order_fill() 호출 (별도 transaction)

        CRITICAL: order_result 포맷 변환 필수
        - order_info['exchange_order_id'] → order_result['order_id']
        - position_manager.py:84에서 'order_id' 키를 기대함
        """
        # TradingService import
        from app.services.trading import trading_service

        # 포맷 변환: exchange_order_id → order_id
        order_result = self._convert_order_info_to_result(order_info, open_order)

        fill_summary = trading_service.position_manager.process_order_fill(
            strategy_account=open_order.strategy_account,
            order_id=order_info.get('exchange_order_id'),
            symbol=open_order.symbol,
            side=open_order.side,
            order_type=open_order.order_type,
            order_result=order_result,
            market_type=open_order.strategy_account.strategy.market_type
        )

        return fill_summary

    # @FEAT:order-tracking @FEAT:limit-order @COMP:service @TYPE:helper
    def _convert_order_info_to_result(self, order_info: dict, open_order: OpenOrder) -> dict:
        """
        공통 로직: order_info → order_result 포맷 변환
        Phase 1, 2에서 공유
        """
        return {
            'order_id': order_info.get('exchange_order_id'),
            'status': order_info.get('status'),
            'filled_quantity': order_info.get('filled_quantity'),
            'average_price': order_info.get('average_price'),
            'side': order_info.get('side') or open_order.side,
            'order_type': order_info.get('order_type') or open_order.order_type
        }

    # @FEAT:order-tracking @FEAT:limit-order @FEAT:event-sse @COMP:service @TYPE:core
    def _finalize_order_update(self, open_order: OpenOrder, status: str, order_info: dict):
        """Step 3: OpenOrder 업데이트 또는 삭제

        주문 상태에 따라 OpenOrder를 업데이트하거나 삭제합니다.
        CANCELED/CANCELLED/EXPIRED 상태의 경우 삭제 전 SSE 이벤트를 발송합니다.

        Args:
            open_order: 처리할 OpenOrder 객체
            status: 주문 상태 ('PARTIALLY_FILLED', 'FILLED', 'CANCELED', 'CANCELLED', 'EXPIRED')
            order_info: 거래소 API 응답 데이터

        처리 로직:
            - PARTIALLY_FILLED: 수량 업데이트 후 계속 모니터링
            - CANCELED/CANCELLED/EXPIRED: SSE 이벤트 발송 → DB 삭제
            - FILLED: DB 삭제 (이벤트는 다른 경로에서 발송)
            - 기타: 방어적 로깅 후 삭제

        SSE 이벤트:
            - 이벤트 발송은 db.session.delete() **전**에 수행 (타이밍 critical)
            - 이벤트 실패 시에도 DB 삭제는 정상 진행 (에러 격리)
            - Phase 1의 EventEmitter.emit_order_cancelled_or_expired_event() 사용
        """
        if status == 'PARTIALLY_FILLED':
            open_order.status = status
            open_order.filled_quantity = float(order_info.get('filled_quantity', 0))
            open_order.is_processing = False  # 계속 모니터링
            db.session.flush()
        elif status in ['CANCELED', 'CANCELLED', 'EXPIRED']:
            # ⚠️ CRITICAL: SSE 이벤트 발송은 db.session.delete() **전**에 수행
            # 이유: 삭제 후에는 open_order 데이터 접근 불가능 (Phase 1 EventEmitter 제약사항)
            try:
                # Lazy import (순환 참조 방지, Line 134-135 패턴 재사용)
                from app.services.trading import trading_service
                event_emitter = trading_service.event_emitter

                # SSE 이벤트 발송 (삭제 전이므로 OpenOrder 데이터 접근 가능)
                event_emitter.emit_order_cancelled_or_expired_event(open_order, status)
            except Exception as e:
                # 이벤트 발송 실패는 로그만 남기고 계속 진행 (DB 트랜잭션 보호)
                logger.error(
                    f"❌ {status} 이벤트 발송 실패 - order_id={open_order.exchange_order_id}, error={e}",
                    exc_info=True
                )

            # OpenOrder 삭제
            db.session.delete(open_order)
            logger.info(f"🗑️ OpenOrder 삭제 완료 - order_id={open_order.exchange_order_id}, status={status}")
        elif status == 'FILLED':
            # FILLED는 기존 로직 유지 (다른 경로에서 이미 이벤트 발송됨)
            db.session.delete(open_order)
            logger.info(f"🗑️ OpenOrder 삭제 완료 - order_id={open_order.exchange_order_id}, status={status}")
        elif status == 'NEW':
            # NEW 상태: 주문 생성 직후의 정상 상태, 추가 처리 불필요
            # WebSocket이 주문 생성을 감지했지만 상태 변경은 없음
            open_order.is_processing = False
            logger.debug(f"📝 NEW 상태 확인 - order_id={open_order.exchange_order_id} (처리 플래그 해제)")
        else:
            # 예상치 못한 상태 (OPEN, PENDING_NEW 등)
            logger.warning(f"⚠️ 처리되지 않은 주문 상태 - status={status}, order_id={open_order.exchange_order_id}")
            # ⚠️ 삭제하지 않고 플래그만 해제 (다음 주기에 재처리)
            open_order.is_processing = False

    # @FEAT:order-tracking @COMP:service @TYPE:core
    def _update_order_in_db(self, order_info: Dict[str, Any], commit: bool = True):
        """DB의 OpenOrder 업데이트 또는 삭제 (Phase 2: 낙관적 잠금 적용)

        Args:
            order_info: 주문 정보
            commit: 트랜잭션 커밋 여부 (기본값: True)
        """
        from datetime import datetime

        try:
            exchange_order_id = order_info['exchange_order_id']
            status = order_info['status'].upper()

            # Step 1: 낙관적 잠금 획득 및 체결 여부 확인
            open_order, should_process_fill = self._check_and_lock_order(exchange_order_id, order_info)

            if not open_order:
                logger.debug(
                    f"OpenOrder를 찾을 수 없거나 이미 처리 중입니다 - 주문 ID: {exchange_order_id} "
                    f"(중복 처리 방지됨)"
                )
                return

            try:
                # Step 2: 체결 처리 (FILLED/PARTIALLY_FILLED)
                if should_process_fill:
                    fill_summary = self._process_fill_for_order(open_order, order_info)

                    if not fill_summary.get('success'):
                        logger.error(
                            f"❌ 체결 처리 실패 - 주문 ID: {exchange_order_id}, "
                            f"error: {fill_summary.get('error')}"
                        )
                        # 플래그 해제 후 재시도 가능하도록
                        if open_order in db.session:
                            open_order.is_processing = False
                            open_order.processing_started_at = None
                        if commit:
                            db.session.rollback()
                        return

                    logger.info(
                        f"✅ 체결 처리 완료 - 주문 ID: {exchange_order_id}, "
                        f"심볼: {open_order.symbol}, "
                        f"Trade ID: {fill_summary.get('trade_id')}"
                    )

                # Step 3: OpenOrder 업데이트 또는 삭제
                self._finalize_order_update(open_order, status, order_info)

                # 호출자가 commit 제어
                if commit:
                    db.session.commit()

            except Exception as inner_e:
                # 에러 발생 시 플래그 해제
                if open_order in db.session:
                    open_order.is_processing = False
                    open_order.processing_started_at = None

                if commit:
                    db.session.rollback()
                logger.error(f"❌ DB 업데이트 실패: {inner_e}", exc_info=True)
                raise

        except Exception as e:
            if commit:
                db.session.rollback()
            logger.error(f"❌ DB 업데이트 실패: {e}", exc_info=True)


# 싱글톤 인스턴스 (app 초기화 시 생성됨)
order_fill_monitor: Optional[OrderFillMonitor] = None


def init_order_fill_monitor(app: Flask):
    """OrderFillMonitor 초기화

    Args:
        app: Flask 앱 인스턴스
    """
    global order_fill_monitor
    order_fill_monitor = OrderFillMonitor(app)
    logger.info("✅ OrderFillMonitor 초기화 완료")
