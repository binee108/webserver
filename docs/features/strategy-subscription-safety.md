# 전략 공개/구독 안전성 강화

## 개요

전략 소유자가 공개 전략을 비공개로 전환하거나, 구독자가 구독을 해제할 때 발생할 수 있는 고아 포지션을 방지하는 안전 장치입니다.

## Phase 1: 공개→비공개 전환 시 구독자 정리

### 기능 설명

전략 소유자가 공개 전략을 비공개로 전환하면, 모든 구독자의 포지션/주문이 자동으로 청산/취소됩니다.

**호출:** `PUT /api/strategies/{id}` with `{"is_public": false}`

### 처리 순서

1. **데이터 사전 로드** - N+1 쿼리 최적화 (`joinedload()`)
2. **구독 비활성화** - `is_active=False` + `flush()` (웹훅 차단)
3. **미체결 주문 취소** - `cancel_all_orders_by_user()` 호출
4. **잔여 주문 검증** - OpenOrder 상태 확인 (방어적 검증)
5. **활성 포지션 청산** - `close_position_by_id()` 시장가 청산
6. **SSE 연결 종료** - `event_service.disconnect_client()` 호출
7. **실패 추적** - `failed_cleanups` 배열에 저장
8. **텔레그램 알림** - 실패 시 관리자에게 통보 (TODO)
9. **로그 기록** - 작업 결과 기록

### Race Condition 방지

```python
sa.is_active = False
db.session.flush()  # DB 즉시 반영 (웹훅 입수 차단)
```

`is_active=False`를 먼저 DB에 반영한 후 청산 작업을 진행하여, 웹훅이 새로운 주문/포지션을 생성하는 것을 사전 차단합니다.

### Best-Effort 방식

- 일부 청산 실패해도 작업 계속 진행
- 실패 내역은 `failed_cleanups` 배열에 추적
- 로그 기록: WARNING (일부 실패), INFO (모두 성공)

### 실패 추적 구조

```python
failed_cleanups = [
    {
        'account': 'binee_account_1',
        'type': 'order_cancellation',  # order_cancellation | remaining_order | position_close | cleanup_exception
        'symbol': 'BTCUSDT',
        'order_id': '12345',
        'reason': 'Insufficient balance'
    }
]
```

### 구현 코드

**파일:** `web_server/app/routes/strategies.py:264-420`

**핵심 함수:** `update_strategy()` (소유자 권한 검증 필요)

## Phase 2-5 (향후 작업)

- **Phase 2**: 구독 해제 상태 조회 API
- **Phase 3**: 구독 해제 UI 경고 메시지
- **Phase 4**: 구독 해제 백엔드 강제 청산
- **Phase 5**: 웹훅 실행 시 `is_active` 재확인

## 관련 링크

- 기능 카탈로그: `docs/FEATURE_CATALOG.md`
- 계획서: `.plan/strategy_subscription_safety_plan.md`
