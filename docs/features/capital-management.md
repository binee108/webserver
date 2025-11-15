# Capital Management (자본 관리)

**Feature**: `@FEAT:capital-management`, `@FEAT:capital-reallocation`  
**Status**: ✅ Phase 1 Complete (2025-10-21)  
**Last Updated**: 2025-10-21

---

## 목적 (Purpose)

거래 전략의 효율성을 극대화하기 위해 여러 전략 간 자본을 동적으로 배분하고, 실시간 잔고 변화를 감지하여 자동으로 재할당하는 시스템입니다.

**주요 특징**:
- 전략별 정적 배분 (고정 비율 또는 고정액)
- 동적 재할당 (잔고 변화 감지 시 이중 임계값 기반)
- 자동 스케줄러 (660초마다 = 11분 간격, 하루 약 130회)
- 수동 UI 트리거 (`/strategies` 페이지 - Phase 5에서 이동)
- 포지션 청산 후 즉시 재할당 (position_manager 통합)

---

## 핵심 개념 (Key Concepts)

### 1. 재할당 조건 (Phase 1)

| 조건 | 설명 |
|-----|------|
| **포지션 청산** | 모든 전략 포지션 = 0 |
| **절대값** | Δ balance ≥ 10 USDT |
| **비율** | Δ% ≥ 0.1% |
| **조합** | 절대값 AND 비율 모두 충족 |

### 2. `should_rebalance()` 메서드

**파일**: `web_server/app/services/capital_service.py:309-449`

자동 리밸런싱 조건 판단 (Phase 1: 이중 임계값 기반)

**조건:**
1. 모든 포지션 청산 (`has_open_positions() == False`)
2. 잔고 변화가 임계값 초과:
   - 절대값: 최소 10 USDT 변화
   - 비율: 최소 0.1% 변화
   - 양쪽 모두 충족 시 재할당 (AND 조건)

**반환값:**
```python
{
    'should_rebalance': True/False,      # 리밸런싱 실행 여부
    'reason': '잔고 변화 감지 (0.15%)',   # 판단 근거
    'has_positions': False,              # 포지션 존재 여부
    'current_total': 10015.0,            # 현재 총 자산
    'previous_total': 10000.0,           # 이전 총 자산
    'delta': 15.0,                       # 변화량 (절대값)
    'percent_change': 0.0015             # 변화율 (소수점)
}
```

---

## 자동 재할당 스케줄 (2025-10-21 Phase 2 업데이트)

**실행 주기**: 660초(11분)마다 (하루 약 130회)
- 계산: 1일 = 1440분 ÷ 11분 = 130.9회/일

**주기 선택 이유**:
- 사용자 요구사항: "5~15분 사이마다 백그라운드에서 시도"
- 11분(660초)은 소수로 시간대 분산 효과
- Phase 1의 이중 임계값 조건으로 불필요한 재할당 자동 차단
- 5분 TTL 캐싱으로 거래소 API 부하 70% 감소

**실행 조건 (Phase 1)**:
1. 모든 포지션 청산 상태
2. 잔고 변화가 임계값 초과:
   - 절대값: 10 USDT 이상
   - 비율: 0.1% 이상

**예시**:
- 10:00:00 실행 → 10:11:00 재실행 → 10:22:00 재실행...
- 포지션 존재 시 자동 스킵
- 잔고 변화 없으면 자동 스킵 (불필요한 API 호출 방지)

---

## 수동 재할당 UI

**경로**: `/strategies` 페이지 → 전략 자본 재할당 버튼

**UI 컴포넌트**:
- 위치: `web_server/templates/strategies.html:58-65` (HTML), Lines 1615+ (JavaScript)
- 디자인: Purple gradient 버튼 (`from-purple-500 to-purple-600`)
- 아이콘: `fas fa-sync-alt` (순환 아이콘)
- 확인 모달: 2단계 경고 메시지 포함
  - "⚠️ 주의: 다음 작업이 즉시 실행됩니다..."
  - "이 작업은 되돌릴 수 없습니다. 계속하시겠습니까?"
- 태그: `@FEAT:capital-management @COMP:ui @TYPE:core`

### 기본 동작 (조건 검증 모드)

**재할당 조건**:
- 조건 1: 계좌의 모든 전략 포지션 = 0
- 조건 2: 잔고 변화 감지 (10 USDT 이상 AND 0.1% 이상)

**조건 미충족 시 메시지**:
- "포지션 존재" (조건 1 미충족)
- "변화량 부족" (조건 2 절대값 미달)
- "임계값 미달" (조건 2 비율 미달)

### 강제 실행 모드 - Phase 4 & 5.1

**API 엔드포인트**: `POST /api/capital/auto-rebalance-all`

**파일**: `web_server/app/routes/capital.py:212-333`

**UI 동작 (Phase 5.1)**: 항상 `force=true` 고정 (조건 우회 자동화)

**요청 예시**:
```json
{
  "force": true
}
```

**백엔드 동작**:
- `should_rebalance()` 조건 **완전 우회**
- 포지션 존재 여부와 무관하게 재할당 실행
- 잔고 변화 없어도 재할당 실행

**보안 감시**:
- `force=true` 사용 시 WARNING 레벨 로그 자동 기록
  - user_id, IP 주소 포함 (감사 추적)
  - 포지션 존재 시 추가 경고 로그
- 코드: `capital.py:232-236`, `capital.py:282-287`

**사용 시나리오**:
- 긴급 자본 재배치 필요 시
- 포지션 존재 상황에서도 강제 재할당 필요 시
- 테스트/디버깅 목적

**⚠️ 주의사항**:
- **포지션 리스크**: 활성 포지션 중 강제 재할당 실행
  - 진행 중인 포지션의 자본 배분이 왜곡될 수 있음
  - 전략별 손익 계산이 부정확해질 수 있음
  - UI 모달로 2단계 확인 (의도적 사용 강조)
- **권장**: 긴급 상황 또는 의도적 개입이 필요한 경우에만 사용

**응답 예시**:
```json
{
  "success": true,
  "data": {
    "forced": true,
    "total_accounts": 3,
    "rebalanced": 3,
    "skipped": 0,
    "results": [
      {
        "account_id": 1,
        "account_name": "snlbinee",
        "rebalanced": true,
        "forced": true,
        "total_capital": 10000.0,
        "allocations_count": 2
      }
    ]
  }
}
```

---

## 캐싱 (capital_service.py:41-77)

거래소 API 호출 70% 감소

**구현**:
- **TTL**: 5분 (300초)
- **저장소**: `_capital_cache` (dict)
- **무효화**: 재할당 완료 시 `invalidate_cache(account_id)` 호출

**메서드**:
- `_get_account_total_capital_cached()`: 캐시 조회 → 미스 시 API 호출
- `invalidate_cache()`: 캐시 제거

**효과**: 5분 간격 재할당 시 거래소 API 호출량 70% 감소

---

## Known Limitations (Phase 4)

**권한 제한 미구현**:
- 현재 모든 로그인 사용자가 `force=true` 파라미터 사용 가능
- `@login_required` 데코레이터만 적용 (admin 체크 없음)

**향후 계획**:
- Admin 권한 체크 추가 예정 (Phase 5 고려)
- RBAC(Role-Based Access Control) 통합 시 `@admin_required` 적용 검토

**현재 보안 조치**:
- WARNING 레벨 로그로 모든 force=true 사용 추적
- user_id, IP 주소 자동 기록으로 감사 추적 가능

---

## 핵심 코드 파일 (Phase 1-5.1)

| 파일 | 위치 | 역할 | 태그 |
|------|------|------|------|
| **CapitalAllocationService** | `capital_service.py` | 자본 배분 로직 (재할당, 검증, 캐싱) | @FEAT:capital-management @COMP:service |
| **Capital Routes** | `routes/capital.py:1-334` | API 엔드포인트 (UI 트리거, 조건 확인) | @FEAT:capital-management @COMP:route |
| **Auto Rebalance Job** | `__init__.py:744-760, 1184-1243` | 백그라운드 스케줄 (660초 간격) | @FEAT:capital-management @COMP:job |
| **UI Components** | `templates/strategies.html:58-65, 1615+` | 버튼 및 모달 UI | @FEAT:capital-management @COMP:ui |

---

## 버전 이력

### Phase 5.1 (2025-10-21) - UI 안전장치
- **UI 개선**: 체크박스 제거, purple gradient 버튼으로 단순화
- **동작 변경**: `force=true` 고정 (항상 조건 우회)
- **안전장치**: 2단계 확인 모달
  - "⚠️ 주의: 다음 작업이 즉시 실행됩니다..."
  - "이 작업은 되돌릴 수 없습니다. 계속하시겠습니까?"
- **디자인**: Purple gradient, shadow effects, sync 아이콘
- **코드**: `strategies.html` Lines 58-65, 1615+
- **태그**: `@FEAT:capital-management @COMP:ui @TYPE:core`

### Phase 5 (2025-10-21) - UI 위치 이동
- **UI 위치**: `/accounts` → `/strategies` 페이지로 이동
- **논리적 배치**: 전략별 자본 배분 맥락에 맞는 위치
- **파일 변경**: accounts 제거, strategies 추가 (총 +74 lines)
- **태그**: `@FEAT:capital-management @COMP:ui @TYPE:core`

### Phase 4 (2025-10-21) - 강제 실행 모드
- **강제 실행**: `force=true` 파라미터로 조건 우회 가능
- **보안 감시**: user_id, IP 주소 WARNING 로그 기록
- **포지션 경고**: 포지션 존재 시 추가 경고
- **응답**: 모든 경로에 `forced` 플래그 포함
- **파일**: `routes/capital.py:212-333`
- **태그**: `@FEAT:capital-management @COMP:route @TYPE:core`

### Phase 2 (2025-10-21) - 자동 스케줄
- **스케줄**: 7개 cron → 1개 interval job (660초)
- **빈도**: 7회/일 → 130회/일 (18.6배 증가)
- **파일**: `__init__.py:744-760` (정의), `__init__.py:1184-1243` (실행)
- **태그**: `@FEAT:capital-management @COMP:job @TYPE:core`

### Phase 1 (2025-10-21) - 핵심 로직
- **이중 임계값**: 절대값(10 USDT) + 비율(0.1%) AND 조건
- **캐싱**: 5분 TTL (API 호출 70% 감소)
- **포지션 청산 즉시 재할당**: position_manager 통합
- **파일**: `capital_service.py:28-449`

---

---

## 코드 위치 맵핑

| 기능 | 파일 | 줄 번호 | 태그 |
|------|------|--------|------|
| 캐싱 구현 | `capital_service.py` | 40-86 | @COMP:service @TYPE:helper |
| 자본 재배분 로직 | `capital_service.py` | 87-200+ | @COMP:service @TYPE:core |
| 리밸런싱 조건 판단 | `capital_service.py` | 309-449 | @COMP:service @TYPE:core |
| API: 단일 계좌 재배분 | `capital.py` | 20-77 | @COMP:route @TYPE:core |
| API: 전체 계좌 재배분 | `capital.py` | 80-200+ | @COMP:route @TYPE:core |
| API: 강제 재할당 | `capital.py` | 212-333 | @COMP:route @TYPE:core |
| 백그라운드 스케줄 | `__init__.py` | 744-760, 1184-1243 | @COMP:job @TYPE:core |
| 수량 계산 (자본 기반) | `quantity_calculator.py` | - | @FEAT:capital-management |
| 거래 기록 (자본 추적) | `record_manager.py` | - | @FEAT:capital-management |

*Last Updated: 2025-10-30*

---

## qty_per 제한 해제 (2025-11-13 업데이트)

### 변경 사항
- **이전**: qty_per 범위 제한 0-100%
- **현재**: 양수 qty_per 무제한 (레버리지 거래 지원)
- **청산 로직**: 음수 qty_per는 여전히 -100% 상한 유지 (안전 장치)

### 수량 계산 공식
```
quantity = (allocated_capital × qty_per% ÷ price) × leverage
```

**예시**:
- allocated_capital = 1000 USDT
- qty_per = 200 (200%)
- price = 50000 USDT (BTC)
- leverage = 10x

```
quantity = (1000 × 2 ÷ 50000) × 10 = 0.4 BTC
total_exposure = 0.4 BTC × 50000 = 20000 USDT (20배 익스포저)
```

### 적용 거래소
- Binance Futures
- Bybit Futures
- 거래소별 최대 레버리지 한도 적용

### 제한 사항
- 거래소의 증거금 요구사항 및 최대 주문 크기 제한 적용
- 계좌 자본 부족 시 주문 거부 (거래소 레벨)
- qty_per=0은 여전히 수량 0 반환

**관련 이슈**: #46 - qty_per > 100% validation removal
**코드**: `quantity_calculator.py`
- Line 216-223: 수량 계산 공식 (양수 qty_per 무제한)
- Line 342-348: 청산 로직 (음수 qty_per -100% 상한)
- Issue #46: 진입 주문 validation 제약 제거
