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
        실패한 주문을 재시도합니다 (Phase 3 구현 완료).

        동작 과정:
        1. FailedOrder 조회 및 상태 검증 (존재 여부, removed 상태, 최대 재시도 횟수)
        2. StrategyAccount 조회 (시스템 오류 체크)
        3. retry_count 증가 (StrategyAccount 검증 후)
        4. ExchangeService.create_batch_orders() 호출 (배치주문 실행)
        5. 성공 시: status='removed', 캐시 무효화, order_id 반환
        6. 실패 시: retry_count만 커밋, 에러 메시지 반환
        7. 예외 시: 롤백 후 retry_count 재증가 및 커밋

        트랜잭션 경계:
        - StrategyAccount 검증은 retry_count 증가 전에 수행 (시스템 오류는 재시도 횟수 미소비)
        - 성공/실패/예외 각 경로마다 독립적인 커밋
        - 예외 발생 시 자동 롤백 후 retry_count만 저장

        최대 재시도 횟수:
        - MAX_RETRY_COUNT = 5 (retry_count 0~4 허용, 5 이상 차단)
        - 재시도 횟수 초과 시 조기 리턴 (retry_count 증가 없음)

        Args:
            failed_order_id (int): 재시도할 FailedOrder의 ID

        Returns:
            Dict[str, Any]: 재시도 결과
                - success (bool): 재시도 성공 여부
                - order_id (str | None): 성공 시 거래소 주문 ID
                - error (str | None): 실패 시 에러 메시지

        Examples:
            >>> # 성공 케이스
            >>> result = failed_order_manager.retry_failed_order(1)
            >>> result
            {'success': True, 'order_id': 'BINANCE_ORDER_12345'}

            >>> # 실패 케이스 (API 오류)
            >>> result = failed_order_manager.retry_failed_order(2)
            >>> result
            {'success': False, 'error': 'Insufficient balance'}

            >>> # 최대 재시도 횟수 초과
            >>> result = failed_order_manager.retry_failed_order(3)
            >>> result
            {'success': False, 'error': 'Maximum retry count exceeded (5)'}
        """
        failed_order = FailedOrder.query.get(failed_order_id)

        if not failed_order:
            return {'success': False, 'error': 'FailedOrder not found'}

        if failed_order.status == 'removed':
            return {'success': False, 'error': 'FailedOrder already removed'}

        # 최대 재시도 횟수 체크 (무한 재시도 방지, DoS 공격 차단)
        # retry_count=0: 초기 상태 (0회 시도)
        # retry_count=1~4: 중간 재시도 (1~4회 시도)
        # retry_count=5: 최대 도달 (5회 시도 완료, 6번째 차단)
        MAX_RETRY_COUNT = 5
        if failed_order.retry_count >= MAX_RETRY_COUNT:
            return {
                'success': False,
                'error': f'Maximum retry count exceeded ({MAX_RETRY_COUNT})'
            }

        try:
            # ExchangeService를 통한 배치주문 실행
            from app.services.exchange import exchange_service
            from app.models import StrategyAccount

            # StrategyAccount 조회 (retry_count 증가 전)
            # 시스템 오류 (StrategyAccount 삭제 등)는 재시도 횟수를 소비하지 않음
            strategy_account = StrategyAccount.query.get(failed_order.strategy_account_id)
            if not strategy_account:
                return {'success': False, 'error': 'StrategyAccount not found'}

            # retry_count 증가 (StrategyAccount 검증 후)
            # 트랜잭션: 성공/실패/예외 경로에서 각각 커밋됨
            failed_order.retry_count += 1
            failed_order.updated_at = datetime.utcnow()

            # 단일 주문을 배치 형식으로 변환
            # Decimal → float 변환 (ExchangeService API 호환성)
            # market_type 소문자 변환 ('FUTURES' → 'futures')
            orders = [{
                'symbol': failed_order.symbol,
                'side': failed_order.side,
                'type': failed_order.order_type,
                'amount': float(failed_order.quantity),  # Decimal → float
                'price': float(failed_order.price) if failed_order.price else None,
                'params': {
                    'stopPrice': float(failed_order.stop_price)
                } if failed_order.stop_price else {}
            }]

            # 배치주문 API 호출
            result = exchange_service.create_batch_orders(
                account=strategy_account.account,
                orders=orders,
                market_type=failed_order.market_type.lower()  # 'FUTURES' → 'futures'
            )

            if result['success'] and result['summary']['successful'] > 0:
                # 성공 경로: status='removed', 캐시 무효화, order_id 반환
                # 트랜잭션: status + retry_count 동시 커밋
                failed_order.status = 'removed'
                db.session.commit()
                self._invalidate_cache(failed_order)  # 캐시에서 제거 (removed 상태는 캐시 안 함)

                # 성공한 주문 ID 반환 (거래소 주문 ID)
                first_result = result['results'][0]
                return {
                    'success': True,
                    'order_id': first_result.get('order_id')
                }
            else:
                # 실패 경로: retry_count만 커밋, 에러 메시지 반환
                # status='pending_retry' 유지 (캐시에 남음)
                db.session.commit()
                error = result.get('results', [{}])[0].get('error', 'Unknown error')
                return {'success': False, 'error': error}

        except Exception as e:
            # 예외 경로: 롤백 후 retry_count 재증가 및 커밋
            # 트랜잭션 일관성 유지 (retry_count는 항상 증가)
            db.session.rollback()
            failed_order.retry_count += 1
            failed_order.updated_at = datetime.utcnow()
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
