# 자본 관리 (Capital Management)

## 1. 개요 (Purpose)

전략별 자본 할당, 계좌별 자금 배분, 레버리지 관리를 담당하는 시스템입니다.

**핵심 기능**:
- 전략별 자본 할당: 가중치 기반 자본 배분
- 레버리지 관리: 선물 거래 수량 계산 시 레버리지 적용
- 실현 손익 반영: 거래 수익/손실을 자본에 반영 (복리 효과)
- 자동 리밸런싱: 포지션 청산 시 조건 충족 시 자동 재배분

---

## 2. 실행 플로우 (Execution Flow)

### 자본 배분 흐름

```
계좌 총 자산 조회
(DB: DailyAccountSummary.ending_balance 또는 실시간 API)
        ↓
전략별 가중치 합 계산
(total_weight = Σ(StrategyAccount.weight))
        ↓
전략별 할당 자본 계산
(allocated = total_capital × strategy_weight / total_weight)
        ↓
StrategyCapital 업데이트
(allocated_capital, last_rebalance_at)
```

### 주문 수량 계산 흐름

```
웹훅 주문 요청 (qty_per: 5%)
        ↓
StrategyCapital.allocated_capital 조회
        ↓
주문 수량 계산
(quantity = allocated × qty_per% ÷ price × leverage)
        ↓
주문 생성 및 거래소 전송
```

---

## 3. 데이터 플로우 (Data Flow)

### Input
- `DailyAccountSummary.ending_balance`: DB에서 계좌 잔고 조회
- `ExchangeService.get_balance()`: 실시간 잔고 조회 (선택)
- `StrategyAccount.weight`: 전략별 가중치
- `StrategyAccount.leverage`: 레버리지 배율

### Process
- 가중치 기반 자본 할당 계산
- 레버리지 적용 주문 수량 계산
- 리밸런싱 조건 판단

### Output
- `StrategyCapital.allocated_capital`: 할당된 자본
- `StrategyCapital.last_rebalance_at`: 리밸런싱 시각
- 계산된 주문 수량

### 의존성
- **사용**: ExchangeService (잔고 조회), DailyAccountSummary (DB 잔고)
- **사용됨**: QuantityCalculator (주문 수량 계산), WebhookService (주문 생성)

---

## 4. 주요 컴포넌트 (Components)

| 파일 | 역할 | 태그 | 핵심 메서드 |
|------|------|------|-------------|
| `services/capital_service.py` | 자본 배분 비즈니스 로직 | @FEAT:capital-management @COMP:service @TYPE:core | `recalculate_strategy_capital()`, `should_rebalance()`, `has_open_positions()`, `apply_realized_pnl_to_capital()` |
| `services/trading/quantity_calculator.py` | 주문 수량 계산 | @FEAT:capital-management @COMP:service @TYPE:core | `calculate_order_quantity()`, `calculate_quantity_from_percentage()` |
| `routes/capital.py` | 자본 관리 API | @FEAT:capital-management @COMP:route @TYPE:core | `/api/capital/reallocate/<int:account_id>`, `/api/capital/reallocate-all`, `/api/capital/rebalance-status/<int:account_id>`, `/api/capital/auto-rebalance-all` |
| `models.py` (StrategyAccount) | 전략-계좌 연결 | @FEAT:capital-management @COMP:model @TYPE:core | `weight`, `leverage`, `max_symbols`, `is_active` |
| `models.py` (StrategyCapital) | 전략별 자본 정보 | @FEAT:capital-management @COMP:model @TYPE:core | `allocated_capital`, `current_pnl`, `last_updated`, `last_rebalance_at` |

### 주요 메서드 상세

#### `recalculate_strategy_capital(account_id, use_live_balance=False)`
**역할**: 계좌의 전략별 자본 재배분 실행

**공식**:
```python
allocated_capital = (total_capital × strategy_weight) / total_weight
```

**반환값**:
```python
{
    'account_id': 1,
    'account_name': 'Main Account',
    'total_capital': 10000.0,
    'allocations': [
        {
            'strategy_account_id': 5,
            'strategy_name': 'test1',
            'weight': 0.6,
            'old_capital': 5000.0,
            'allocated_capital': 6000.0,
            'change': 1000.0
        }
    ],
    'source': 'db',  # or 'live', 'live_fallback'
    'total_weight': 1.0,
    'timestamp': '2025-10-12T10:30:00.123456'
}
```

#### `should_rebalance(account_id, min_interval_hours=1)`
**역할**: 자동 리밸런싱 조건 판단

**조건**:
1. 모든 포지션 청산 완료 (`has_open_positions() == False`)
2. 마지막 리밸런싱 이후 최소 시간 경과

**반환값**:
```python
{
    'should_rebalance': True/False,
    'reason': '리밸런싱 조건 충족',
    'has_positions': False,
    'time_since_last': 2.5  # hours
}
```

#### `calculate_order_quantity()`
**역할**: 할당 자본 기반 주문 수량 계산

**공식**:
```python
quantity = (allocated_capital × qty_per% ÷ price) × leverage
```

**예시**:
- 할당 자본: 6,000 USDT
- qty_per: 10%
- BTC 가격: 100,000 USDT
- 레버리지: 10배

→ 주문 수량: (6,000 × 0.1 ÷ 100,000) × 10 = **0.06 BTC**

---

## 5. 자동 재할당 스케줄러 (Auto Rebalancing Scheduler)

### 실행 일정
**빈도**: 하루 7회 (고정 시각)
**시각**: 01:17, 04:52, 08:37, 12:22, 16:07, 19:52, 23:37
**소수 선택 이유**: 트래픽 분산 (정시 회피)

### 실행 조건
1. 모든 포지션 청산 완료 (`has_open_positions() == False`)
2. 마지막 재할당 이후 최소 1시간 경과

조건 미충족 시 로그만 기록하고 재할당 스킵.

### 구현 방식
- **트리거**: APScheduler `cron` 트리거
- **주의**: APScheduler cron은 hour/minute 곱집합 사용 → 개별 job 등록 (7개)
- **Job ID**: `auto_rebalance_accounts_{hour:02d}_{minute:02d}` (예: `auto_rebalance_accounts_01_17`)
- **코드 위치**: `/web_server/app/__init__.py` Line 636-654

### 로그 확인
```bash
# 스케줄러 시작/종료
grep "Auto Rebalance" /web_server/logs/app.log

# 실행 결과
grep "자동 리밸런싱" /web_server/logs/app.log

# 조건 미충족 (포지션 존재)
grep "포지션 존재|시간 미경과" /web_server/logs/app.log
```

### 수동 실행
```bash
curl -k -X POST https://222.98.151.163/api/capital/auto-rebalance-all
```

---

## 6. 설계 결정 히스토리 (Design Decisions)

### 가중치 기반 상대 비율 시스템
**결정**: 가중치 합이 1.0일 필요 없음 (상대적 비율로 계산)

**이유**:
- 유연성: 가중치 0.5 + 0.3 = 0.8 → 비율 5:3으로 해석
- 확장성: 전략 추가/제거 시 다른 전략 가중치 수정 불필요

**예시**:
```python
# 가중치: 0.5, 0.3 (합 0.8)
# 총 자본: 10,000 USDT
전략 A: (10,000 × 0.5) / 0.8 = 6,250 USDT
전략 B: (10,000 × 0.3) / 0.8 = 3,750 USDT
```

### DB 잔고 우선 + 실시간 API 옵션
**결정**: 기본 DB 조회, 선택적 실시간 API 조회

**이유**:
- 성능: DB 조회가 빠름, API Rate Limit 절약
- 안정성: API 장애 시에도 DB 폴백 가능
- 유연성: 중요한 재배분 시 `use_live=true` 옵션 사용

### 자동 재할당 스케줄러 조건부 실행
**결정**: 포지션 청산 완료 + 최소 시간 경과 시에만 실행

**이유**:
- 안전성: 포지션 보유 중 자본 변경 방지
- 효율성: 과도한 재할당 방지 (최소 간격 1시간)

### APScheduler Cron 곱집합 문제와 해결법
**문제**: `trigger="cron", hour=1, minute=17` 형태는 실제로 hour=1이고 minute가 0~59인 **모든 시각**을 의미 (곱집합)

**해결**: 각 실행 시각마다 개별 job 등록
```python
for (hour, minute) in [(1, 17), (4, 52), ...]:
    scheduler.add_job(..., hour=hour, minute=minute, id=f"auto_rebalance_{hour}_{minute}")
```

---

## 7. API 엔드포인트

### 1. 특정 계좌 자본 재배분
**Endpoint**: `POST /api/capital/reallocate/<int:account_id>`

**Query Params**:
- `use_live`: 실시간 잔고 조회 여부 (true/false, 기본값: false)

**예시**:
```bash
curl -k -X POST https://222.98.151.163/api/capital/reallocate/1?use_live=true
```

### 2. 모든 계좌 자본 재배분
**Endpoint**: `POST /api/capital/reallocate-all`

**예시**:
```bash
curl -k -X POST https://222.98.151.163/api/capital/reallocate-all?use_live=true
```

### 3. 리밸런싱 상태 조회
**Endpoint**: `GET /api/capital/rebalance-status/<int:account_id>`

**예시**:
```bash
curl -k https://222.98.151.163/api/capital/rebalance-status/1
```

### 4. 자동 리밸런싱 수동 트리거
**Endpoint**: `POST /api/capital/auto-rebalance-all`

**설명**: 조건 충족 계좌만 선별 재배분

**예시**:
```bash
curl -k -X POST https://222.98.151.163/api/capital/auto-rebalance-all
```

---

## 6. 수동 재할당 UI (프론트엔드)

### 위치
- **페이지**: `/accounts` (계좌 관리 페이지)
- **버튼 위치**: 우측 상단, "잔고 새로고침" 버튼 좌측
- **버튼명**: "자본 재할당"

### 사용 방법
1. `/accounts` 페이지 접속
2. "자본 재할당" 버튼 클릭
3. Toast 알림으로 결과 확인 (1~2초)

### 응답 메시지

| 상황 | Toast 메시지 | 타입 | 의미 |
|------|-------------|------|------|
| 활성 계좌 없음 | "활성 계좌가 없습니다." | INFO | 계좌 없음 (설정 확인 필요) |
| 재할당 성공 | "자본 재할당 완료: X개 계좌 처리됨 (Y개 건너뜀)" | SUCCESS | 성공, Y개는 조건 미충족 |
| 조건 불만족 | "자본 재할당: 모든 계좌가 재할당 조건을 만족하지 않습니다." | INFO | 포지션 보유 중 또는 시간 미경과 |
| 네트워크 오류 | "자본 재할당 중 오류가 발생했습니다" | ERROR | 서버 또는 네트워크 오류 |

### 재할당 조건
재할당이 실행되려면 **다음 두 조건을 모두 충족**해야 합니다:

1. **포지션 청산 완료**: 모든 포지션 청산 완료 (`has_open_positions() == False`)
2. **최소 1시간 경과**: 마지막 재할당 이후 최소 1시간 경과

조건 미충족 계좌는 자동 건너뜀 (로그에만 기록).

### 주의사항
- 포지션 보유 중에는 재할당 불가 (조건 미충족 메시지 표시)
- 최소 1시간 간격 필수 (빈번한 재할당 방지, API 부하 감소)
- 일반 사용자는 자동 스케줄러(하루 7회)에 의존 권장

### 구현 코드
**파일**: `app/static/js/accounts.js`
**함수**: `triggerCapitalReallocation()` (라인 301-341)
**태그**: `@FEAT:capital-management @COMP:route @TYPE:core`

---

## 8. 유지보수 가이드

### 주의사항

1. **가중치 변경 후 재배분 필수**
   - StrategyAccount.weight 수정 후 `/api/capital/reallocate/<id>` 호출 필요

2. **포지션 보유 중 재배분 금지**
   - 포지션 청산 후에만 재배분 권장 (자동 리밸런싱 조건)

3. **실시간 API 호출 주의**
   - Rate Limit 고려하여 `use_live=true` 사용 최소화
   - 중요 재배분 시에만 사용 권장

### 확장 포인트

1. **포지션 가치 기반 가용 자본 계산**
   - 현재: 할당 자본 전체 사용 가능으로 간주
   - 향후: `가용_자본 = 할당_자본 - 사용중_자본 - 예약_자본`

2. **실시간 레버리지 계산**
   - 현재: 고정 레버리지 사용
   - 향후: `실시간_레버리지 = Σ(포지션_가치) / 계좌_자본`

3. **복리 효과 자동 적용**
   - 현재: 수동 호출 필요 (`apply_realized_pnl_to_capital()`)
   - 향후: 체결 시 자동 적용

4. **백그라운드 자동 리밸런싱**
   - 현재: API 수동 트리거만 지원
   - 향후: APScheduler 기반 주기적 조건 확인 및 자동 실행

### 트러블슈팅

#### 할당 자본이 0으로 표시됨
**원인**: StrategyCapital 레코드 미생성 또는 재배분 미실행

**해결**:
```bash
# 1. 수동 재배분
curl -k -X POST https://222.98.151.163/api/capital/reallocate/1?use_live=true

# 2. 로그 확인
grep "자본 재배분" web_server/logs/app.log
```

#### 자동 리밸런싱 미실행
**원인**: 최소 시간 간격 미충족 또는 열린 포지션 존재

**해결**:
```bash
# 1. 상태 확인
curl -k https://222.98.151.163/api/capital/rebalance-status/1

# 2. 강제 실행 (조건 무시)
curl -k -X POST https://222.98.151.163/api/capital/reallocate/1?use_live=true
```

#### qty_per 계산 오류
**원인**: 할당 자본/레버리지 오류 또는 가격 캐시 오래됨

**검증**:
```python
# 예상 수량 계산
allocated_capital = 6000 USDT
qty_per = 10%
price = 100,000 USDT
leverage = 10

expected_quantity = (6000 * 0.1 / 100000) * 10 = 0.06 BTC
```

**디버깅**:
```bash
# 로그 확인
grep "수량 계산:" web_server/logs/app.log
```

---

## 9. Grep 검색용 태그

```bash
# 모든 capital-management 코드 찾기
grep -r "@FEAT:capital-management" --include="*.py"

# 핵심 로직만 찾기
grep -r "@FEAT:capital-management" --include="*.py" | grep "@TYPE:core"

# 서비스 레이어만 찾기
grep -r "@FEAT:capital-management" --include="*.py" | grep "@COMP:service"

# API 엔드포인트만 찾기
grep -r "@FEAT:capital-management" --include="*.py" | grep "@COMP:route"

# 모델 정의 찾기
grep -r "@FEAT:capital-management" --include="*.py" | grep "@COMP:model"
```

---

## 관련 문서

- [아키텍처 개요](../ARCHITECTURE.md)
- [웹훅 주문 처리](./webhook-order-processing.md)
- [포지션 트래킹](./position-tracking.md)

---

*Last Updated: 2025-10-21*
*Version: 2.2.0 - Frontend Manual Reallocation UI*
*Changes: Added Section 6 (Manual UI), 4-state toast messaging, condition documentation*
