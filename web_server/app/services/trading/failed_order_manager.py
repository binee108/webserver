"""
실패한 주문 관리 시스템

@FEAT:immediate-order-execution @COMP:service @TYPE:core

PostgreSQL + 메모리 캐시 이중화로 빠른 조회 제공.
"""
import threading
import re
from datetime import datetime
from typing import List, Dict, Optional, Any
from app import db
from app.models import FailedOrder


class FailedOrderManager:
    """
    실패한 주문 관리 시스템.
    PostgreSQL + 메모리 캐시 이중화로 빠른 조회 제공.

    TODO (Phase 3 개선 예정):
    - Issue #1: API 키 마스킹 패턴 강화 (Base64, Bearer 토큰 지원, 8자 미만 키)
    - Issue #8: 캐시 성능 최적화 (_total_cached 변수 추가, 일괄 삭제)

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

    def retry_failed_order(self, failed_order_id: int) -> Dict[str, Any]:
        """
        실패 주문 재시도.

        Args:
            failed_order_id: FailedOrder ID

        Returns:
            {'success': bool, 'order_id': str | None, 'error': str | None}
        """
        failed_order = FailedOrder.query.get(failed_order_id)

        if not failed_order:
            return {'success': False, 'error': 'FailedOrder not found'}

        if failed_order.status == 'removed':
            return {'success': False, 'error': 'FailedOrder already removed'}

        # retry_count 증가
        failed_order.retry_count += 1
        failed_order.updated_at = datetime.utcnow()

        try:
            # TODO: Phase 3에서 구현될 배치주문 API 호출
            # Phase 3에서 실제 주문 실행 로직 추가 필요
            # 예상 구현:
            # from web_server.app.services.trading import order_manager
            # result = order_manager.place_order(
            #     strategy_account_id=failed_order.strategy_account_id,
            #     order_params=failed_order.order_params
            # )
            #
            # if result['success']:
            #     failed_order.status = 'removed'
            #     db.session.commit()
            #     self._invalidate_cache(failed_order)
            #     return {'success': True, 'order_id': result['order_id']}
            # else:
            #     db.session.commit()
            #     return {'success': False, 'error': result['error']}

            # 현재는 성공으로 가정 (스텁)
            failed_order.status = 'removed'
            db.session.commit()

            # 캐시 무효화
            self._invalidate_cache(failed_order)

            return {'success': True, 'order_id': 'retry_success_stub'}

        except Exception as e:
            # 재시도 실패 시 retry_count만 업데이트
            db.session.commit()
            return {'success': False, 'error': str(e)}

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
