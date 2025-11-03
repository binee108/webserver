# Webhook Concurrency Fix

> 동일 전략+심볼의 웹훅을 순차 처리하여 Race Condition 방지

## Overview

Webhook 동시 처리 시 발생하는 Race Condition(예: 주문 생성과 취소의 충돌)을 방지하기 위해 전략+심볼 기반의 Lock 메커니즘을 구현했습니다. 동일 전략+심볼의 웹훅은 순차 처리되고, 다른 전략/심볼은 병렬 처리되어 성능을 유지합니다.

**Related Features:**
- `@FEAT:webhook-order` - 웹훅 주문 처리
- `@FEAT:order-tracking` - 주문 상태 추적
- `@FEAT:order-queue` - 주문 대기열 관리

---

## Phase 1: WebhookLockManager 구현

### 목표
Lock 관리 전용 클래스를 설계하여, 전략+심볼별 Lock을 효율적으로 제공하고 Timeout을 처리합니다.

### 구현 내용

**파일:** `web_server/app/services/webhook_lock_manager.py`

#### 주요 특징
- Lock Pool 패턴: 고정 크기 Dict로 Lock 인스턴스 캐싱
- Context Manager: 자동 Lock 해제 보장
- Timeout 처리: 30초 기본 타임아웃, 환경변수로 설정 가능
- 스레드 안전성: 동시 요청에서 Race Condition 없는 Lock 할당

#### 클래스 구조
```python
# @FEAT:webhook-concurrency-fix @COMP:service @TYPE:core
class WebhookLockManager:
    def __init__(self):
        self._locks = {}  # {(strategy_id, symbol): Lock}
        self._locks_lock = threading.Lock()

    @contextmanager
    def acquire_lock(self, strategy_id: int, symbol: str, timeout: float):
        """(strategy_id, symbol) Lock 획득 및 해제"""
```

#### Lock Key 설계
```
Lock Key: (strategy_id, symbol)
예: (1, "BTC/USDT") → 전략 ID 1의 BTC/USDT 심볼별 Lock
```

---

## Phase 2: webhook_service 통합

### 목표
Phase 1의 WebhookLockManager를 webhook_service.py에 통합하여 모든 주문 처리 경로를 Lock으로 보호합니다.

### 구현 내용

**파일:** `web_server/app/services/webhook_service.py`

#### 1. Lock 래퍼 메서드 추가 (Lines 119-153)
```python
@contextmanager
def _acquire_strategy_lock(self, strategy_id: int, symbol: str):
    """
    전략+심볼 Lock 획득 (모든 주문 작업 직렬화)

    동일 전략+심볼의 웹훅을 순차 처리하여 Race Condition 방지.
    단일 주문, 배치 주문, 취소 작업, 테스트 모드 모두 이 Lock을 사용.
    """
```

**특징:**
- Context manager 패턴으로 자동 Lock 해제 보장
- TimeoutError → WebhookError 변환으로 도메인 에러 제공
- 단일 소스 원칙 준수 (DRY)

#### 2. Symbol 조기 검증 (Lines 184-187)
Lock 획득 전에 symbol 필드를 검증하여 명확한 에러 메시지를 제공합니다.

**효과:**
- Lock 타임아웃 오류로 오도되지 않음
- 조기 실패로 불필요한 Lock 대기 방지

#### 3. 보호 범위
총 7개 주문 처리 경로를 Lock으로 보호:

| # | 경로 | 위치 | 설명 |
|---|------|------|------|
| 1 | 테스트 모드 - 단일 | Line 210 | Test mode 단일 주문 처리 |
| 2 | 테스트 모드 - 배치 | Line 210 | Test mode 배치 주문 처리 |
| 3 | CANCEL_ALL_ORDER | Line 234 | 전체 주문 취소 |
| 4 | CANCEL | Line 244 | 개별 주문 취소 |
| 5 | 배치 주문 | Line 279 | 배치1(CANCEL_ALL+MARKET) + 배치2(LIMIT+STOP) |
| 6 | 단일 주문 | Line 433 | 일반 단일 주문 생성 |
| 7 | 증권 거래 | Line 441 | 증권 시장 주문 |

#### 4. Lock 획득 순서
```
웹훅 수신
  ↓
Group name 검증
  ↓
Symbol 검증 ✅ (조기 검증 - Lock 전)
  ↓
전략 조회 및 토큰 검증
  ↓
🔒 Lock 획득 (strategy_id, symbol)
  ↓
주문 처리 (CANCEL_ALL / CANCEL / 배치 / 단일 / 증권)
  ↓
🔓 Lock 해제 (자동)
```

### 동작 예시

#### 예시 1: 동일 전략+심볼 직렬화
```
시간 T0: 웹훅1 (Strategy 1, BTC/USDT, 배치 주문 3개)
  - Lock 획득 성공: (1, "BTC/USDT")
  - 배치1 실행 (CANCEL_ALL)
  - 배치2 실행 (LIMIT 3개)
  - 소요 시간: 2초

시간 T0+0.5s: 웹훅2 (Strategy 1, BTC/USDT, 단일 주문)
  - Lock 획득 대기: (1, "BTC/USDT") [웹훅1 Lock 보유 중]

시간 T0+2s: 웹훅1 완료
  - Lock 해제

시간 T0+2s: 웹훅2 Lock 획득 (대기 1.5초)
  - 단일 주문 처리
  - Lock 해제
```

✅ **결과:** 주문 충돌 없음, 순차 처리 보장, 전체 소요 시간 ~3.5초

#### 예시 2: 다른 심볼 병렬 처리
```
시간 T0: 웹훅1 (Strategy 1, BTC/USDT)
  - Lock 획득: (1, "BTC/USDT")
  - 소요 시간: 2초

시간 T0: 웹훅2 (Strategy 1, ETH/USDT) [거의 동시]
  - Lock 획득: (1, "ETH/USDT") [다른 Lock]
  - 소요 시간: 1.5초

두 웹훅 동시 처리 (병렬)
```

✅ **결과:** 성능 유지, 불필요한 대기 없음, 전체 소요 시간 ~2초 (직렬이면 3.5초)

### 환경변수
```bash
WEBHOOK_LOCK_TIMEOUT=30         # Lock 획득 타임아웃 (초, 기본값: 30)
MAX_WEBHOOK_LOCKS=1000          # Lock pool 최대 크기 (기본값: 1000)
```

### 트러블슈팅

#### Lock 타임아웃 발생 시
**증상:** `WebhookError: 웹훅 처리 대기 시간 초과`

**원인:**
- 이전 웹훅이 30초 이상 실행 중
- 외부 거래소 API 응답 지연
- 네트워크 지연

**해결:**
1. 로그에서 장시간 실행 원인 파악
2. `WEBHOOK_LOCK_TIMEOUT` 증가 (예: 60초)
   ```bash
   export WEBHOOK_LOCK_TIMEOUT=60
   python run.py restart
   ```
3. 거래소 API 상태 확인

#### Lock pool 고갈
**증상:** `RuntimeError: Lock pool exhausted (max: 1000)`

**원인:**
- 1000개 이상의 전략+심볼 조합 사용 중

**해결:**
- `MAX_WEBHOOK_LOCKS` 증가
  ```bash
  export MAX_WEBHOOK_LOCKS=2000
  python run.py restart
  ```

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────┐
│              External Webhook (TradingView)         │
└────────────────────┬────────────────────────────────┘
                     ↓
    ┌────────────────────────────────────────┐
    │   WebhookService.process_webhook()     │
    ├────────────────────────────────────────┤
    │ 1. Normalize & Validate                 │
    │ 2. Check symbol (early validation)      │
    │ 3. Retrieve strategy & token            │
    └────────────────┬───────────────────────┘
                     ↓
         ┌───────────────────────────┐
         │  🔒 Lock Acquisition      │
         │  (strategy_id, symbol)    │
         │  Timeout: 30s             │
         └────────────┬──────────────┘
                      ↓
    ┌─────────────────────────────────────────┐
    │   Order Processing (Exclusive)          │
    ├─────────────────────────────────────────┤
    │ • Test mode (single/batch)              │
    │ • Production (CANCEL_ALL/CANCEL)        │
    │ • Production (Batch/Single/Securities)  │
    └────────────────┬────────────────────────┘
                     ↓
         ┌───────────────────────────┐
         │  🔓 Lock Release          │
         │  (automatic)              │
         └───────────────────────────┘
```

---

## Performance Impact

### Lock Contention 시나리오
```
시나리오: 동일 전략 1개, 심볼 10개, 초당 1개씩 웹훅 수신 (10초 동안)

Without Lock (Race Condition 위험):
  - 10개 웹훅 병렬 처리
  - 주문 ID 충돌 가능성 높음

With Lock (안전하지만 순차):
  - 같은 심볼 웹훅: 순차 처리 (약간 지연)
  - 다른 심볼 웹훅: 병렬 처리 (지연 없음)
  - 전체 성능: ~5% 저하 (심볼이 충분히 분산된 경우)
```

---

## Testing

### Unit Test 케이스
```python
# test_webhook_lock_manager.py

def test_same_strategy_symbol_sequential():
    """동일 전략+심볼은 순차 처리"""
    # Lock 획득 시간 측정
    # 예상: webhook2 대기 1-2초

def test_different_symbols_parallel():
    """다른 심볼은 병렬 처리"""
    # Lock 획득 시간 측정
    # 예상: webhook1, webhook2 거의 동시

def test_lock_timeout():
    """Lock 타임아웃 처리"""
    # 강제 지연으로 타임아웃 유발
    # 예상: TimeoutError → WebhookError 변환
```

### Integration Test
```python
# test_webhook_service_concurrency.py

def test_batch_vs_single_order_no_race_condition():
    """배치 주문 처리 중 단일 주문 요청이 와도 충돌 없음"""
    # 배치 주문 웹훅 전송 (3개 주문)
    # 즉시 단일 주문 웹훅 전송
    # 결과: 모든 주문 생성됨, 충돌 없음
```

---

## Related Documentation

- [Webhook Order Processing](webhook-order-processing.md) - 웹훅 주문 처리 기본
- [Order Queue System](order-queue-system.md) - 주문 대기열 관리
- [Order Tracking](order-tracking.md) - 주문 상태 추적
