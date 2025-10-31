"""
실패한 주문 관리 시스템

@FEAT:immediate-order-execution @COMP:service @TYPE:core
@FEAT:orphan-order-prevention @COMP:service @TYPE:core @PHASE:2

Phase 2 (2025-10-31): 취소 실패 추적 기능 추가
- create_failed_cancellation(): 취소 실패 FailedOrder 생성
- retry_failed_order(): operation_type 분기 추가 (CREATE/CANCEL)
- _retry_cancellation(): 취소 재시도 로직
- _retry_creation(): 기존 생성 재시도 로직 추출

PostgreSQL + 메모리 캐시 이중화로 빠른 조회 제공.
"""
import threading
import re
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any
from app import db
from app.models import FailedOrder, FailedOrderOperation

logger = logging.getLogger(__name__)


class FailedOrderManager:
    """
    실패한 주문 관리 시스템.
    PostgreSQL + 메모리 캐시 이중화로 빠른 조회 제공.

    TODO (향후 개선 예정):
    - Issue #1: API 키 마스킹 패턴 강화 (Base64, Bearer 토큰 지원, 8자 미만 키)
    - Issue #8: 캐시 성능 최적화 (_total_cached 변수 추가, 일괄 삭제)

    Phase 3 완료 (2025-10-27):
    - retry_failed_order() 실제 배치주문 API 호출 구현
    - 최대 재시도 횟수(5회) 체크 로직 추가
    - StrategyAccount 검증 → retry_count 증가 순서 확립 (시스템 오류 재시도 미소비)
    - 트랜잭션 경계 명확화 (예외 시 롤백 + retry_count 재증가)
    - ExchangeService.create_batch_orders() 통합 완료

    @FEAT:immediate-order-execution @COMP:service @TYPE:core
    """

    def __init__(self):
        self._cache = {}  # {(strategy_account_id, symbol): [FailedOrder, ...]}
        self._cache_lock = threading.Lock()
        self._cache_max_size = 1000  # 최대 1000개 FailedOrder 캐싱 (메모리 누수 방지)

    def _sanitize_exchange_error(self, error_text: str) -> str:
        """
        거래소 에러 메시지에서 민감 정보 제거.

        - API 키 패턴 마스킹 (예: "API-KEY: abc123..." → "API-KEY: abc123***")
        - 최대 500자로 제한

        Args:
            error_text: 거래소 원본 에러 메시지

        Returns:
            마스킹된 에러 메시지 (최대 500자)
        """
        if not error_text:
            return ""

        # API 키, Secret 패턴 마스킹
        # 패턴: API_KEY, API-KEY, SECRET, TOKEN 등 뒤에 오는 긴 문자열을 마스킹
        # 예: "API-KEY: abc123def456ghi789..." → "API-KEY: abc123***"
        sanitized = re.sub(
            r'(API[_-]?KEY|SECRET|TOKEN)["\s:=]+([a-zA-Z0-9]{8})[a-zA-Z0-9]+',
            r'\1: \2***',
            error_text,
            flags=re.IGNORECASE
        )

        return sanitized[:500]

    def create_failed_order(
        self,
        strategy_account_id: int,
        order_params: Dict[str, Any],
        reason: str,
        exchange_error: Optional[str] = None
    ) -> FailedOrder:
        """
        실패한 주문 생성.

        Args:
            strategy_account_id: 전략 계정 ID
            order_params: 주문 파라미터 (symbol, side, order_type, quantity, price 등)
            reason: 실패 이유 (예: "Rate limit exceeded")
            exchange_error: 거래소 응답 원문 (옵션)

        Returns:
            생성된 FailedOrder 인스턴스
        """
        # 민감 정보 마스킹
        sanitized_error = self._sanitize_exchange_error(exchange_error or "")

        # FailedOrder 생성
        failed_order = FailedOrder(
            operation_type=FailedOrderOperation.CREATE,  # Phase 2: 명시적 설정 (SQLAlchemy DEFAULT 대신)
            strategy_account_id=strategy_account_id,
            symbol=order_params.get('symbol'),
            side=order_params.get('side'),
            order_type=order_params.get('order_type'),
            quantity=order_params.get('quantity'),
            price=order_params.get('price'),
            stop_price=order_params.get('stop_price'),
            market_type=order_params.get('market_type', 'FUTURES'),
            reason=reason[:100],  # 최대 100자
            exchange_error=sanitized_error,
            order_params=order_params,
            status='pending_retry',
            retry_count=0
        )

        # DB 저장
        db.session.add(failed_order)
        db.session.commit()

        # 캐시 업데이트
        self._update_cache(failed_order)

        return failed_order

    # @FEAT:orphan-order-prevention @COMP:service @TYPE:core @PHASE:2
    # Phase 2: 취소 실패 추적 - OpenOrder 객체로 완전한 컨텍스트 캡처
    def create_failed_cancellation(self, order, exchange_error=None):
        """
        취소 실패한 주문을 FailedOrder에 기록.

        Design: OpenOrder 객체를 직접 받아 완전한 주문 정보 보존
        - 파라미터 폭발 방지 (개별 필드 5개 → 객체 1개)
        - 타입 안정성 (OpenOrder 타입 보장)
        - 정확한 재시도 가능 (원본 주문 상세 정보 유지)

        Args:
            order (OpenOrder): 취소 실패한 주문 객체
            exchange_error (str, optional): 거래소 API 오류 메시지

        Returns:
            FailedOrder: 생성된 FailedOrder 객체 또는 None (실패 시)
        """
        try:
            failed_order = FailedOrder(
                operation_type=FailedOrderOperation.CANCEL,
                original_order_id=order.exchange_order_id,
                strategy_account_id=order.strategy_account_id,
                symbol=order.symbol,
                side=order.side,
                order_type=order.order_type,
                quantity=order.quantity,
                price=order.price,
                reason='Cancellation failed',
                exchange_error=self._sanitize_exchange_error(exchange_error),
                order_params={
                    'symbol': order.symbol,
                    'side': order.side,
                    'order_type': order.order_type,
                    'quantity': float(order.quantity),
                    'price': float(order.price) if order.price else None,
                    'market_type': order.market_type
                },
                retry_count=0,
                status='pending_retry'
            )

            db.session.add(failed_order)
            db.session.commit()

            logger.info(
                f"✅ FailedOrder 생성 (CANCEL) - "
                f"order_id={order.exchange_order_id}, symbol={order.symbol}"
            )

            return failed_order

        except Exception as e:
            db.session.rollback()
            logger.error(
                f"❌ FailedOrder 생성 실패 - "
                f"order_id={order.exchange_order_id}, error={e}"
            )
            return None

    def _update_cache(self, failed_order: FailedOrder):
        """
        메모리 캐시 업데이트 (thread-safe).

        Note: pending_retry 상태만 캐시하여 메모리 효율성 향상.
        removed 상태는 캐시하지 않음 (Code Review Issue #3).
        """
        # pending_retry 상태만 캐시 (removed 상태는 제외)
        if failed_order.status != 'pending_retry':
            return

        with self._cache_lock:
            cache_key = (failed_order.strategy_account_id, failed_order.symbol)

            if cache_key not in self._cache:
                self._cache[cache_key] = []

            self._cache[cache_key].append(failed_order)

            # 캐시 크기 제한 (LRU 방식: 오래된 것부터 제거)
            total_cached = sum(len(orders) for orders in self._cache.values())
            if total_cached > self._cache_max_size:
                # 가장 오래된 캐시 엔트리 제거
                oldest_key = min(
                    self._cache.keys(),
                    key=lambda k: min(o.created_at for o in self._cache[k])
                )
                del self._cache[oldest_key]

    def get_failed_orders(
        self,
        strategy_account_id: Optional[int] = None,
        symbol: Optional[str] = None
    ) -> List[FailedOrder]:
        """
        실패 주문 조회 (캐시 우선).

        캐시 정책:
        - 두 필터 모두 제공 (strategy_account_id + symbol): 캐시 먼저 조회
        - 캐시 히트: 메모리 캐시 반환 (pending_retry만 캐시됨, 최신순 정렬)
        - 캐시 미스 또는 필터 부족: DB 조회 (pending_retry만 반환)

        Args:
            strategy_account_id: 전략 계정 ID (옵션, 미제공 시 모든 계정)
            symbol: 심볼 (옵션, 미제공 시 모든 심볼)

        Returns:
            FailedOrder 리스트 (status='pending_retry'만 반환, 최신순 정렬)
        """
        # 캐시 조회 시도 (strategy_account_id와 symbol이 모두 제공된 경우)
        if strategy_account_id and symbol:
            cache_key = (strategy_account_id, symbol)
            with self._cache_lock:
                if cache_key in self._cache:
                    # 캐시된 데이터 반환 (이미 pending_retry만 저장됨)
                    return self._cache[cache_key]

        # DB 조회 (캐시 미스 또는 필터 조건)
        query = FailedOrder.query

        if strategy_account_id:
            query = query.filter_by(strategy_account_id=strategy_account_id)

        if symbol:
            query = query.filter_by(symbol=symbol)

        # status='pending_retry'만 조회
        query = query.filter_by(status='pending_retry')

        # 최신순 정렬
        query = query.order_by(FailedOrder.created_at.desc())

        return query.all()

    # @FEAT:orphan-order-prevention @COMP:service @TYPE:core @PHASE:2
    # Phase 2: operation_type 기반 분기 - CREATE/CANCEL 각각의 재시도 로직 호출
    def retry_failed_order(self, failed_order_id: int) -> Dict[str, Any]:
        """
        FailedOrder 재시도 (CREATE/CANCEL 타입 자동 분기).

        Operation Types:
        - CREATE: _retry_creation() 호출 → 주문 생성 재시도
        - CANCEL: _retry_cancellation() 호출 → 주문 취소 재시도
        - Unknown: ERROR 로그 + False 반환

        Phase 2 (2025-10-31): operation_type 분기 추가
        - CREATE: 주문 생성 재시도 (_retry_creation)
        - CANCEL: 주문 취소 재시도 (_retry_cancellation)

        Args:
            failed_order_id: FailedOrder ID

        Returns:
            dict: {'success': bool, 'message': str}
        """
        failed_order = FailedOrder.query.get(failed_order_id)

        if not failed_order:
            return {'success': False, 'error': 'FailedOrder not found'}

        if failed_order.status in ['completed', 'removed']:
            return {'success': True, 'message': f'Already {failed_order.status}'}

        # operation_type 분기
        if failed_order.operation_type == FailedOrderOperation.CREATE:
            return self._retry_creation(failed_order)
        elif failed_order.operation_type == FailedOrderOperation.CANCEL:
            return self._retry_cancellation(failed_order)
        else:
            logger.error(
                f"❌ 알 수 없는 operation_type - "
                f"failed_order_id={failed_order_id}, "
                f"operation_type={failed_order.operation_type}"
            )
            return {
                'success': False,
                'error': f'Unknown operation_type: {failed_order.operation_type}'
            }

    # @FEAT:orphan-order-prevention @COMP:service @TYPE:core @PHASE:2
    def _retry_creation(self, failed_order: FailedOrder) -> Dict[str, Any]:
        """
        CREATE 타입 FailedOrder 재시도 (기존 로직)

        Args:
            failed_order: FailedOrder 객체 (operation_type='CREATE')

        Returns:
            dict: {'success': bool, 'message': str}
        """
        # 최대 재시도 횟수 체크
        MAX_RETRY_COUNT = 5
        if failed_order.retry_count >= MAX_RETRY_COUNT:
            return {
                'success': False,
                'error': f'Maximum retry count exceeded ({MAX_RETRY_COUNT})'
            }

        try:
            from app.services.exchange import exchange_service
            from app.models import StrategyAccount

            # StrategyAccount 조회 (retry_count 증가 전)
            strategy_account = StrategyAccount.query.get(failed_order.strategy_account_id)
            if not strategy_account:
                return {'success': False, 'error': 'StrategyAccount not found'}

            # retry_count 증가
            failed_order.retry_count += 1
            failed_order.updated_at = datetime.utcnow()

            # 배치주문 API 호출
            orders = [{
                'symbol': failed_order.symbol,
                'side': failed_order.side,
                'type': failed_order.order_type,
                'amount': float(failed_order.quantity),
                'price': float(failed_order.price) if failed_order.price else None,
                'params': {
                    'stopPrice': float(failed_order.stop_price)
                } if failed_order.stop_price else {}
            }]

            result = exchange_service.create_batch_orders(
                account=strategy_account.account,
                orders=orders,
                market_type=failed_order.market_type.lower()
            )

            if result['success'] and result['summary']['successful'] > 0:
                # 성공 경로
                failed_order.status = 'removed'
                db.session.commit()
                self._invalidate_cache(failed_order)

                first_result = result['results'][0]
                return {
                    'success': True,
                    'order_id': first_result.get('order_id')
                }
            else:
                # 실패 경로
                db.session.commit()
                error = result.get('results', [{}])[0].get('error', 'Unknown error')
                return {'success': False, 'error': error}

        except Exception as e:
            # 예외 경로
            db.session.rollback()
            failed_order.retry_count += 1
            failed_order.updated_at = datetime.utcnow()
            db.session.commit()
            return {'success': False, 'error': str(e)}

    # @FEAT:orphan-order-prevention @COMP:service @TYPE:core @PHASE:2
    # Phase 2: 취소 재시도 로직 - 엣지 케이스 처리 포함
    def _retry_cancellation(self, failed_order: FailedOrder) -> Dict[str, Any]:
        """
        CANCEL 타입 FailedOrder 재시도.

        Edge Cases:
        1. OpenOrder 없음 → status='completed' (이미 삭제됨, 다른 프로세스에서 처리)
        2. 5회 초과 → status='removed' (재시도 포기, 수동 개입 필요)
        3. OrderManager 호출 실패 → retry_count 증가 후 재시도 대기

        Status Transitions:
        - 성공: status='completed' (취소 완료)
        - 실패 (5회 미만): retry_count++ (재시도 대기)
        - 실패 (5회 이상): status='removed' (포기)

        Args:
            failed_order: FailedOrder 객체 (operation_type='CANCEL')

        Returns:
            dict: {'success': bool, 'message': str}
        """
        # 1. 원본 주문 확인
        from app.models import OpenOrder
        open_order = OpenOrder.query.filter_by(
            exchange_order_id=failed_order.original_order_id
        ).first()

        if not open_order:
            # 이미 삭제됨 (다른 프로세스에서 처리) - 성공으로 간주
            logger.info(
                f"🔄 취소 재시도 스킵 (주문 이미 삭제) - "
                f"original_order_id={failed_order.original_order_id}"
            )
            failed_order.status = 'completed'
            db.session.commit()
            return {'success': True, 'message': '주문 이미 삭제됨'}

        # 최대 재시도 횟수 체크
        MAX_RETRY_COUNT = 5
        if failed_order.retry_count >= MAX_RETRY_COUNT:
            failed_order.status = 'removed'
            db.session.commit()
            logger.warning(
                f"⚠️ 취소 재시도 최종 실패 (5회 초과) - "
                f"order_id={failed_order.original_order_id}"
            )
            return {
                'success': False,
                'error': f'Maximum retry count exceeded ({MAX_RETRY_COUNT})'
            }

        # 2. OrderManager를 통해 취소 재시도
        try:
            from app.services.trading.order_manager import OrderManager
            order_manager = OrderManager()

            result = order_manager.cancel_order(
                order_id=open_order.exchange_order_id,
                symbol=open_order.symbol,
                account_id=open_order.strategy_account.account.id,
                open_order=open_order
            )

            if result.get('success'):
                failed_order.status = 'completed'
                db.session.commit()

                logger.info(
                    f"✅ 취소 재시도 성공 - "
                    f"order_id={failed_order.original_order_id}"
                )

                return {'success': True, 'message': '취소 성공'}
            else:
                # 재시도 실패 - retry_count 증가
                failed_order.retry_count += 1
                failed_order.exchange_error = self._sanitize_exchange_error(
                    result.get('error')
                )

                if failed_order.retry_count >= MAX_RETRY_COUNT:
                    failed_order.status = 'removed'
                    logger.warning(
                        f"⚠️ 취소 재시도 최종 실패 (5회 초과) - "
                        f"order_id={failed_order.original_order_id}"
                    )

                db.session.commit()

                return {
                    'success': False,
                    'message': f"취소 실패 (재시도 {failed_order.retry_count}회)"
                }

        except Exception as e:
            logger.error(
                f"❌ 취소 재시도 중 예외 - "
                f"order_id={failed_order.original_order_id}, error={e}"
            )

            failed_order.retry_count += 1
            if failed_order.retry_count >= MAX_RETRY_COUNT:
                failed_order.status = 'removed'

            db.session.commit()

            return {'success': False, 'message': str(e)}

    def remove_failed_order(self, failed_order_id: int) -> bool:
        """
        실패 주문 제거 (사용자 수동 제거).

        Args:
            failed_order_id: FailedOrder ID

        Returns:
            성공 여부
        """
        failed_order = FailedOrder.query.get(failed_order_id)

        if not failed_order:
            return False

        # status를 'removed'로 변경 (soft delete)
        failed_order.status = 'removed'
        failed_order.updated_at = datetime.utcnow()
        db.session.commit()

        # 캐시 무효화
        self._invalidate_cache(failed_order)

        return True

    def _invalidate_cache(self, failed_order: FailedOrder):
        """
        캐시 무효화 (thread-safe).

        특정 FailedOrder를 캐시에서 제거하고, 빈 리스트는 키 자체 삭제.
        """
        with self._cache_lock:
            cache_key = (failed_order.strategy_account_id, failed_order.symbol)
            if cache_key in self._cache:
                # 해당 FailedOrder를 캐시에서 제거
                self._cache[cache_key] = [
                    fo for fo in self._cache[cache_key]
                    if fo.id != failed_order.id
                ]

                # 빈 리스트면 키 자체 삭제
                if not self._cache[cache_key]:
                    del self._cache[cache_key]


# 싱글톤 인스턴스
failed_order_manager = FailedOrderManager()
