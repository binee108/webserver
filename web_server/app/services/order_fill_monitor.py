"""
주문 체결 모니터

WebSocket 이벤트 수신 → REST API 확인 → DB 업데이트 → 재정렬 트리거
"""

import asyncio
import logging
from decimal import Decimal
from typing import Dict, Any, Optional
from flask import Flask

from app import db
from app.models import OpenOrder, Account
from app.services.exchange import exchange_service

logger = logging.getLogger(__name__)


class OrderFillMonitor:
    """주문 체결 모니터

    핵심 기능:
    1. WebSocket 이벤트 수신 (from BinanceWebSocket/BybitWebSocket)
    2. REST API로 주문 상태 확인 (신뢰도 확보)
    3. DB 업데이트 (OpenOrder 삭제 또는 수정)
    4. 재정렬 트리거 (OrderQueueManager.rebalance_symbol)
    """

    def __init__(self, app: Flask):
        self.app = app

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
            symbol: 심볼 (예: "BTCUSDT")
            status: WebSocket에서 받은 상태 (예: "FILLED")
        """
        try:
            logger.info(
                f"📦 주문 업데이트 이벤트 수신 - "
                f"계정: {account_id}, 주문 ID: {exchange_order_id}, "
                f"심볼: {symbol}, 상태: {status}"
            )

            # Step 1: REST API로 주문 상태 확인 (WebSocket 신뢰도 이슈 방지)
            confirmed_order = await self._confirm_order_status(
                account_id, exchange_order_id, symbol
            )

            if not confirmed_order:
                logger.warning(
                    f"⚠️ REST API 주문 확인 실패 - "
                    f"주문 ID: {exchange_order_id}, DB 업데이트 스킵"
                )
                return

            # Step 2: DB 업데이트 + 재정렬 (트랜잭션 통합)
            confirmed_status = confirmed_order.get('status', '').upper()

            with self.app.app_context():
                try:
                    # DB 업데이트 (커밋하지 않음)
                    self._update_order_in_db(confirmed_order, commit=False)

                    # 재정렬 트리거 (주문이 완료되었을 때만)
                    if confirmed_status in ['FILLED', 'CANCELED', 'CANCELLED', 'EXPIRED']:
                        from app.services.trading import trading_service
                        queue_manager = trading_service.order_queue_manager

                        result = queue_manager.rebalance_symbol(
                            account_id=account_id,
                            symbol=symbol,
                            commit=False  # 커밋하지 않음
                        )

                        if not result.get('success'):
                            raise Exception(f"재정렬 실패: {result.get('error')}")

                    # 모든 작업 성공 시 한 번에 커밋
                    db.session.commit()

                    if confirmed_status in ['FILLED', 'CANCELED', 'CANCELLED', 'EXPIRED']:
                        logger.info(
                            f"🔄 WebSocket 트리거 재정렬 완료 - {symbol}: "
                            f"취소 {result.get('cancelled', 0)}개, 실행 {result.get('executed', 0)}개"
                        )

                except Exception as e:
                    db.session.rollback()
                    logger.error(f"❌ WebSocket 트리거 처리 실패 - {symbol}: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"❌ 주문 업데이트 처리 실패: {e}", exc_info=True)

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

    def _update_order_in_db(self, order_info: Dict[str, Any], commit: bool = True):
        """DB의 OpenOrder 업데이트 또는 삭제

        Args:
            order_info: 주문 정보
            commit: 트랜잭션 커밋 여부 (기본값: True)
        """
        try:
            exchange_order_id = order_info['exchange_order_id']
            status = order_info['status'].upper()

            # OpenOrder 조회
            open_order = OpenOrder.query.filter_by(
                exchange_order_id=exchange_order_id
            ).first()

            if not open_order:
                logger.debug(
                    f"OpenOrder를 찾을 수 없습니다 - 주문 ID: {exchange_order_id} "
                    f"(이미 처리되었거나 WebSocket이 먼저 도착했을 수 있습니다)"
                )
                # OpenOrder가 없어도 완료 상태면 그대로 반환 (재정렬은 상위에서 처리)
                return

            # FILLED/CANCELED/EXPIRED → OpenOrder 삭제
            if status in ['FILLED', 'CANCELED', 'CANCELLED', 'EXPIRED']:
                logger.info(
                    f"🗑️ OpenOrder 삭제 - 주문 ID: {exchange_order_id}, "
                    f"심볼: {open_order.symbol}, "
                    f"계정: {open_order.strategy_account.account.id if open_order.strategy_account else 'N/A'}, "
                    f"상태: {status}"
                )
                db.session.delete(open_order)
            else:
                # PARTIALLY_FILLED → filled_quantity 업데이트
                logger.info(
                    f"📝 OpenOrder 업데이트 - 주문 ID: {exchange_order_id}, "
                    f"심볼: {open_order.symbol}, "
                    f"상태: {status}, "
                    f"체결량: {order_info['filled_quantity']}"
                )
                open_order.status = status
                open_order.filled_quantity = float(order_info['filled_quantity'])

            # 호출자가 commit 제어
            if commit:
                db.session.commit()

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
