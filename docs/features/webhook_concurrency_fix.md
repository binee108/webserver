# Webhook Concurrency Fix

**Feature ID**: webhook-concurrency-fix
**Phase**: Phase 1-2 완료
**Status**: Phase 2 Step 5 (Documentation)
**Date**: 2025-11-02

---

## 개요

동일 전략/심볼의 웹훅 동시 호출 시 발생하는 경쟁 조건(Race Condition)을 해결하는 Lock 메커니즘입니다.

### 문제 상황

```
배치1(CANCEL_ALL)과 배치2(LIMIT) 간 시간 간격 없음
↓
웹훅1의 배치2 완료 전에 웹훅2의 배치1 시작
↓
CANCEL_ALL이 일부 주문만 감지하여 부분 취소
↓
거래소-DB 주문 불일치 발생
```

### 해결 방안

**전략+심볼 단위 Lock**: `(strategy_id, symbol)` 조합에 대한 Lock 메커니즘
- 동일 전략/심볼 웹훅: 직렬화 (순차 처리)
- 다른 전략/심볼: 병렬 처리 유지
- 데드락 방지: 정렬된 Lock 획득 순서
- 성능: Lock pool 크기 제한 및 timeout 메커니즘

---

## 구현 내역

### 신규 파일

**`web_server/app/services/webhook_lock_manager.py`** (186 lines)
- `WebhookLockManager` 클래스
- `webhook_lock_manager` 싱글톤 인스턴스

### 주요 메서드

| 메서드 | 목적 | 반환값 |
|--------|------|--------|
| `acquire_webhook_lock(strategy_id, symbols, timeout)` | Lock 획득 (컨텍스트 매니저) | ContextManager |
| `_get_lock_key(strategy_id, symbol)` | Lock 키 생성 | str |

### 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `WEBHOOK_LOCK_TIMEOUT` | 30 | Lock 획득 타임아웃 (초) |
| `MAX_WEBHOOK_LOCKS` | 1000 | Lock pool 최대 크기 |

---

## 사용 방법

```python
from app.services.webhook_lock_manager import webhook_lock_manager

with webhook_lock_manager.acquire_webhook_lock(
    strategy_id=1,
    symbols=['BTC/USDT', 'ETH/USDT'],
    timeout=30
):
    # 배치1: CANCEL_ALL 처리
    # 배치2: LIMIT 주문 생성
    # Lock은 자동 해제
```

---

## 로깅

| 로그 | 레벨 | 설명 |
|------|------|------|
| `🔒 Acquired lock for strategy_X_symbol_Y (waited 0.05s)` | DEBUG | 정상 획득 |
| `⏱️ Lock waited 6.23s for strategy_X_symbol_Y` | WARNING | 5초 이상 대기 |
| `❌ Lock pool exhausted: 1000 locks` | ERROR | Pool 고갈 |

---

## 기대 효과

- ✅ 동일 전략/심볼 웹훅 직렬화 → 경쟁 조건 해결
- ✅ 다른 전략/심볼 병렬 유지 → 성능 영향 최소화
- ✅ 데드락 방지 → 안정성 확보
- ✅ Timeout 메커니즘 → 무한 대기 방지

---

## 성능 특성

- **Lock 획득 시간**: 정상 < 100ms
- **대기 시간 경고**: 5초 이상
- **메모리**: Lock당 ~100 bytes
- **확장성**: Max 1000 locks (환경변수로 조정 가능)

---

## Phase 2: webhook_service.py 통합

### 개요
WebhookLockManager를 webhook_service.py의 모든 주문 처리 경로에 통합하여 완전한 동시성 제어를 실현합니다.

### 구현 변경사항

#### 1. Lock 래퍼 메서드 추가 (Lines 119-148)

`_acquire_strategy_lock()` context manager를 추가하여 Lock 로직을 중앙화했습니다.

**특징:**
- `@contextmanager` 데코레이터로 자동 Lock 해제 보장
- TimeoutError → WebhookError 변환 (도메인 에러 제공)
- 30초 타임아웃 (WEBHOOK_LOCK_TIMEOUT 환경변수)
- 단일 소스 원칙 준수 (DRY)

#### 2. Symbol 조기 검증 (Lines 184-187)

Lock 획득 전에 symbol 필드를 검증하여 명확한 에러 메시지를 제공합니다.

**효과:**
- Lock 타임아웃 에러로 오도되지 않음
- 조기 실패로 불필요한 Lock 대기 방지

#### 3. 통합 Lock 적용 (Line 227부터)

모든 주문 처리 경로를 하나의 Lock 컨텍스트로 보호합니다.

**보호되는 경로:**
- CANCEL_ALL_ORDER (Crypto)
- CANCEL_ALL_ORDER (Securities)
- CANCEL
- 배치 주문 (CANCEL_ALL+MARKET, LIMIT+STOP)
- 단일 주문

### 동작 예시

**동일 전략+심볼 직렬화:**
```
T0: 웹훅1 (Strategy 1, BTC/USDT, 배치 3개) → Lock 획득 성공
T0.5: 웹훅2 (Strategy 1, BTC/USDT, 단일) → Lock 대기 중
T2.5: 웹훅1 완료 → Lock 해제
T2.5: 웹훅2 Lock 획득 → 대기 시간: 2.0초
```

**다른 심볼 병렬 처리:**
```
T0: 웹훅1 (Strategy 1, BTC/USDT) → Lock 획득
T0: 웹훅2 (Strategy 1, ETH/USDT) → Lock 획득 (다른 Lock)
→ 두 웹훅 동시 처리 (병렬)
```

### 성능 영향

| 시나리오 | Lock 영향 | 처리 시간 |
|---------|----------|----------|
| 동일 strategy+symbol (직렬화) | Lock 대기 발생 | 기존 대비 +100% (순차 처리) |
| 다른 strategy/symbol (병렬) | Lock 대기 없음 | 기존과 동일 (병렬 유지) |

### 환경변수

| 변수 | 기본값 | 설명 | 권장 범위 |
|------|--------|------|----------|
| `WEBHOOK_LOCK_TIMEOUT` | 30 | Lock 획득 타임아웃 (초) | 10-120 |
| `MAX_WEBHOOK_LOCKS` | 1000 | Lock pool 최대 크기 | 100-10000 |

### 로깅

| 이벤트 | 레벨 | 메시지 | 위치 |
|--------|------|--------|------|
| Lock 획득 성공 | DEBUG | `🔒 Acquired lock for strategy_X_symbol_Y (waited 0.05s)` | webhook_lock_manager.py |
| 대기 시간 5초 이상 | WARNING | `⏱️ Lock waited 6.23s for strategy_X_symbol_Y` | webhook_lock_manager.py |
| Lock 타임아웃 | ERROR | `❌ Lock 획득 타임아웃 - 전략: X, 심볼: Y` | webhook_service.py |

---

## 다음 Phase

**Phase 3**: 기능 테스트 (`.test/test_webhook_concurrency.py`)

---

**문서화**: documentation-manager | **검토**: documentation-reviewer | **최종**: 2025-11-02
