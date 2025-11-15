# ⚠️ Order Queue System (ARCHIVED - v3.1.0)

> **상태**: DEPRECATED (2025-10-26)
> **대체 시스템**: [Immediate Order Execution](./immediate-order-execution.md)

## 아카이브 사유

이 문서는 **v3.1.0까지의 Order Queue 시스템**을 설명합니다. 현재 코드베이스에서는 다음과 같이 변경되었습니다:

**커밋 f8000de (Phase 5)**: Queue 인프라 완전 제거
- ❌ `PendingOrder` 테이블 삭제
- ❌ `OrderQueueManager` 클래스 삭제
- ❌ `queue_rebalancer` 백그라운드 작업 삭제
- ✅ 웹훅 즉시 실행 방식으로 전환
- ✅ 실패 주문 추적 = `FailedOrder` 테이블

## 이유

Order Queue 기반 설계의 문제점:
- **복잡성**: 우선순위 재정렬, 동시성 제어, Race Condition 해결 필요
- **지연**: 대기열 처리로 인한 주문 실행 지연
- **모니터링**: 대기 중 주문 상태 추적 어려움

**해결책**:
1. 웹훅 수신 즉시 거래소 전송
2. 실패 시 `FailedOrder` 테이블에 기록
3. 배치 재시도로 재실행

## 전환 가이드

**기존 Order Queue 개념 → 새 시스템 매핑**:

| 기존 개념 | 새 개념 | 파일 |
|---------|--------|-----|
| PendingOrder | FailedOrder | models/trading.py |
| OrderQueueManager.rebalance_symbol() | OrderManager.retry_failed_order() | services/trading/order_manager.py |
| queue_rebalancer (1초 주기) | 배치 재시도 (15초 주기) | services/background/retry_failed_orders.py |

## 상세 내용

- **이전 문서**: `docs/archive/order-queue-system-v3.1.md` (참고용)
- **현재 구현**: [Immediate Order Execution](./immediate-order-execution.md)
- **아키텍처 결정**: `docs/decisions/005-immediate-order-execution.md`

---

---

## 코드 태그 상태

`@FEAT:order-queue` 태그는 여전히 다음 코드에 존재합니다:
- `services/trading/core.py`: `execute_trade()` - 거래 실행 로직
- `services/trading/core.py`: `_execute_batch_for_symbol()` - 배치 경쟁 조건 처리
- `exchanges/crypto/upbit.py`: 거래소 통합 로직
- `exchanges/crypto/bithumb.py`: 거래소 통합 로직

이 태그들은 **역사적 컨텍스트로 유지**되며, 현재 기능은 `@FEAT:immediate-order-execution`이 담당합니다.

---

*Archive Date: 2025-10-26*
*Last Version: 3.1.0*
*Last Updated: 2025-10-30*
*Related Feature: immediate-order-execution*
