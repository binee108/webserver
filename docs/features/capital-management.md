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
- 수동 UI 트리거 (/accounts 페이지)
- 포지션 청산 후 즉시 재할당

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

```python
# @FEAT:capital-management @COMP:service @TYPE:core
def should_rebalance(account_id):
    """
    자동 리밸런싱 조건 판단 (Phase 1: 이중 임계값 기반)

    조건:
    1. 모든 포지션 청산 (has_open_positions() == False)
    2. 잔고 변화가 임계값 초과:
       - 절대값: 최소 10 USDT 변화
       - 비율: 최소 0.1% 변화
       - 양쪽 모두 충족 시 재할당 (AND 조건)

    Returns:
    {
        'should_rebalance': True/False,
        'reason': '잔고 변화 감지 (0.1234%)',
        'has_positions': False,
        'current_total': 10015.0,
        'previous_total': 10000.0,
        'delta': 15.0,
        'percent_change': 0.0015
    }
    """
    pass
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

**경로**: /strategies 페이지 → 전략 자본 재할당 버튼

### 기본 동작 (force=false)

**재할당 조건**:
- 조건 1: 계좌의 모든 전략 포지션 = 0
- 조건 2: 잔고 변화 감지 (10 USDT 이상 AND 0.1% 이상)

**조건 미충족 시 메시지**:
- "포지션 존재" (조건 1 미충족)
- "변화량 부족" (조건 2 절대값 미달)
- "임계값 미달" (조건 2 비율 미달)

### 강제 실행 모드 (force=true) - Phase 4

**API 엔드포인트**: `POST /api/capital/auto-rebalance-all`

**요청 예시**:
```json
{
  "force": true
}
```

**동작**:
- should_rebalance() 조건 **완전 우회**
- 포지션 존재 시에도 재할당 실행
- 잔고 변화 없어도 재할당 실행

**사용 시나리오**:
- 긴급 자본 재배치 필요 시
- 수동 개입으로 조건 무시 필요 시
- 테스트/디버깅 목적

**⚠️ 주의사항**:
- 포지션 존재 시 강제 재할당 리스크:
  - 진행 중인 포지션의 자본 배분이 왜곡될 수 있음
  - 전략별 손익 계산이 부정확해질 수 있음
- WARNING 레벨 로그 자동 기록 (user_id, IP 주소)
- 권장: 긴급 상황에서만 사용 (예: 계좌 자금 긴급 이동 필요 시)

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

## 캐싱 (capital_service.py:41-49)

거래소 API 호출 70% 감소

- **TTL**: 5분 (300초)
- **무효화**: 재할당 완료 시 `invalidate_cache(account_id)` 호출

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

## 버전 이력

### Phase 5 (2025-10-21)
- **UI 위치 변경**: accounts → strategies 페이지로 이동
- **논리적 배치**: 전략별 자본 배분 맥락에 맞는 위치
- **force 파라미터 UI**: 체크박스로 강제 실행 모드 선택 가능
- **버튼 텍스트 개선**: "자본 재할당" → "전략 자본 재할당" (명확성)
- **파일 변경**:
  - accounts.html: -6 lines (버튼 삭제)
  - accounts.js: -43 lines (함수 삭제, export 제거)
  - strategies.html: +74 lines (액션 바 10 + 함수 64)
  - capital-management.md: +14 lines
- **태그**: `@FEAT:capital-management @COMP:ui @TYPE:core`

### Phase 4 (2025-10-21)
- **강제 실행 모드 추가**: `force=true` 파라미터로 조건 우회 가능
- **보안 감사 추적**: 강제 실행 시 user_id, IP 주소 WARNING 로그 기록
- **포지션 리스크 경고**: 포지션 존재 중 강제 재할당 시 WARNING 로그
- **응답 일관성**: 모든 경로에 `forced` 플래그 포함
- **파일**: `app/routes/capital.py` (Lines 212-334)
- **태그**: `@FEAT:capital-management @COMP:route @TYPE:core`

### Phase 2 (2025-10-21)
- **자동 재할당 스케줄 개선**: 7개 cron job → 1개 interval job (660초 간격)
- **실행 빈도 증가**: 7회/일 → 130회/일 (약 18.6배 증가)
- **코드 단순화**: DRY 원칙 강화 (-10% 코드 감소)
- **파일**: `app/__init__.py` (Lines 636-653)
- **태그**: `@FEAT:capital-management @COMP:job @TYPE:core`

### Phase 1 (2025-10-21)
- **이중 임계값 기반 재할당**: 시간 기반 → 잔고 변화 감지
- **포지션 청산 즉시 재할당**: `position_manager.py` 통합
- **캐싱 도입**: 거래소 API 부하 70% 감소 (5분 TTL)
- **트랜잭션 분리**: 재할당 결과 DB 저장 지연 방지

*Last Updated: 2025-10-21*
