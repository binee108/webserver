# Webhook Concurrency Fix

**Feature ID**: webhook-concurrency-fix
**Phase**: Phase 1 - WebhookLockManager 구현
**Status**: Phase 1 Step 5 (Documentation)
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

## 다음 Phase

**Phase 2**: `webhook_service.py` 통합
**Phase 3**: 기능 테스트 (`.test/test_webhook_concurrency.py`)

---

**문서화**: documentation-manager | **검토**: documentation-reviewer | **최종**: 2025-11-02
