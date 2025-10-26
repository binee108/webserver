# Capital Management

> 자본 배분, 재할당, 전략별 수량 계산을 관리하는 핵심 기능

**Tag**: `@FEAT:capital-management` | **Files**: `web_server/app/services/analytics.py`, `web_server/app/routes/capital.py`

---

## 개요

자본 관리 기능은 계좌의 자본을 여러 전략에 효율적으로 배분하고, 마켓 타입별(현물/선물)로 각 전략에 할당하는 책임을 담당합니다.

### 핵심 기능
- 계좌별 마켓 타입 감지 및 자본 배분
- 전략별 마켓 타입별 자본 할당
- 수량 계산 (포지션별 크기 결정)
- 선물 전략의 잔고 정확성 보장

---

## 마켓별 잔고 조회

### 개요

`_get_cached_daily_balance()` 함수는 캐시된 일일 잔고를 조회하며, **마켓 타입별로 개별 조회가 가능합니다**. Issue #7 수정으로 인해 현물과 선물 전략이 각각 정확한 잔고를 할당받을 수 있습니다.

### 사용법

**현물 잔고 조회**:
```python
from web_server.app.models import MarketType

spot_balance = analytics_service._get_cached_daily_balance(
    account_id=1,
    market_type=MarketType.SPOT_LOWER
)
# 반환: spot_balance 값 (또는 0.0)
```

**선물 잔고 조회**:
```python
futures_balance = analytics_service._get_cached_daily_balance(
    account_id=1,
    market_type=MarketType.FUTURES_LOWER
)
# 반환: futures_balance 값 (또는 0.0)
```

**전체 잔고 조회** (하위 호환성):
```python
total_balance = analytics_service._get_cached_daily_balance(account_id=1)
# 반환: ending_balance (또는 starting_balance, 0.0)
```

### 동작 방식

1. `DailyAccountSummary` 테이블에서 최신 레코드 조회
2. 마켓 타입에 따라 적절한 필드 반환:
   - `MarketType.SPOT_LOWER` → `spot_balance` (현물 전용 잔고)
   - `MarketType.FUTURES_LOWER` → `futures_balance` (선물 전용 잔고)
   - `None` (기본값) → `ending_balance` (또는 `starting_balance`) - 기존 동작 유지
3. 데이터가 없으면 `None` 반환
4. 필드 값이 NULL이면 `0.0` 반환

### 폴백 로직

실시간 잔고 조회 실패 시 캐시된 잔고를 사용합니다.

**우선순위**:
1. 실시간 거래소 잔고 조회 (1순위)
2. `DailyAccountSummary` 캐시 조회 (2순위, 마켓별)
3. 자본 할당 건너뜀 (캐시도 없을 경우)

**마켓별 폴백** (Issue #7 수정):
- **현물 전략**: `spot_balance` 캐시 사용
- **선물 전략**: `futures_balance` 캐시 사용
- **혼합 전략**: 각 마켓별로 개별 캐시 사용

**중요**: 전체 잔고(`ending_balance`)를 마켓 구분 없이 사용하지 않습니다. 각 마켓 타입의 전략은 해당 마켓의 잔고만 할당받습니다.

**예시**:
```python
# 실시간 조회 실패 시
# 현물 전략 → spot_balance ($10,369)
# 선물 전략 → futures_balance ($5,000)
# ❌ 선물 전략 → ending_balance ($15,369) - 이전 버그
```

**잔고 필드 우선순위** (캐시 내부):
1. 지정된 마켓 타입의 잔고 (`spot_balance` / `futures_balance`)
2. 전체 잔고 (`ending_balance`)
3. 시작 잔고 (`starting_balance`, 방어적 폴백)
4. `0.0` (최종 폴백 - NULL 처리)

**로그**:
- WARNING: "계좌 X: 실시간 현물 잔고 조회 실패, 캐시 사용 ($X.XX)"
- WARNING: "계좌 X: 실시간 선물 잔고 조회 실패, 캐시 사용 ($X.XX)"

### 로깅

각 잔고 조회 시 DEBUG 레벨 로그 출력:
```
계좌 1: 캐시된 현물 잔고 $10000.00
계좌 1: 캐시된 선물 잔고 $5000.00
계좌 1: 캐시된 전체 잔고 $15000.00
```

---

## 자동 자본 할당

### 개요

`auto_allocate_capital_for_account()` 함수는 계좌에 연결된 모든 전략에 대해 **마켓 타입별로 자동 자본 할당**을 수행합니다.

### 할당 기준

- **활성 전략**: 상태가 `ACTIVE`인 전략만 처리
- **마켓 타입별 분리**: 각 전략의 마켓 타입에 맞는 잔고만 할당
  - SPOT 전략 → `spot_balance` 할당
  - FUTURES 전략 → `futures_balance` 할당

### 호출 시점

- 웹훅 주문 처리 시
- 수동 자본 할당 요청 시
- 백그라운드 재할당 작업 시

---

## 알려진 이슈 (Known Issues)

### Issue #7: 선물 전략 잔고 할당 버그 (해결)

**문제**: 선물 전략이 현물+선물 합산 잔고(`ending_balance`)를 할당받음
**원인**: `_get_cached_daily_balance()`가 마켓 타입을 무시하고 전체 잔고만 반환
**해결**: 마켓 타입 파라미터 추가 + 마켓별 필드 분리

**적용 파일**:
- `web_server/app/services/analytics.py:1480-1522`
- `web_server/app/services/analytics.py:1525-...` (auto_allocate_capital_for_account)

---

## 관련 기능

- **Analytics**: 거래 성과 분석, ROI/승률 계산
- **Strategy Management**: 전략 CRUD, 계좌 연결
- **Position Tracking**: 포지션 관리, 손익 추적
