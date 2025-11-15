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

**파일:** `web_server/app/routes/strategies.py:274-431`

**핵심 함수:** `update_strategy()` (Line 215, 소유자 권한 검증 필요)

**기능 태그:** `@FEAT:strategy-subscription-safety @COMP:route @TYPE:core` (Line 274)

## Phase 2: 구독 상태 조회 API

### 기능 설명

구독 해제 전 프론트엔드에서 사용자에게 경고 메시지를 표시하기 위한 상태 조회 API입니다.
활성 포지션, 미체결 주문, 영향받는 심볼 목록, 구독 활성 상태를 반환합니다.

**호출:** `GET /api/strategies/{strategy_id}/subscribe/{account_id}/status`

### API 명세

#### Request

```http
GET /api/strategies/123/subscribe/456/status
Authorization: Bearer YOUR_TOKEN
```

**Path Parameters:**
- `strategy_id` (int): 전략 ID
- `account_id` (int): 계좌 ID

**Authorization:** Bearer token 필수 (로그인된 사용자만 접근 가능)

#### Response (200 OK)

```json
{
  "success": true,
  "data": {
    "active_positions": 2,
    "open_orders": 3,
    "symbols": ["BTC/USDT", "ETH/USDT"],
    "is_active": true
  }
}
```

**필드 설명:**
- `active_positions` (int): `quantity != 0`인 활성 포지션 개수
- `open_orders` (int): 미체결 주문 개수 (상태: OPEN, PARTIALLY_FILLED, NEW)
- `symbols` (array): 활성 포지션과 미체결 주문에 영향받는 심볼 목록 (정렬, 중복 제거)
- `is_active` (bool): 구독 활성 상태 (true=활성, false=비활성)

#### Error Responses

| Status | Error Code | 설명 | 원인 |
|--------|-----------|------|------|
| 403 | ACCESS_DENIED | 접근 권한이 없습니다. | 계좌 소유자가 아님 |
| 404 | RESOURCE_NOT_FOUND | 구독 정보를 찾을 수 없습니다. | 해당 StrategyAccount 미존재 |
| 500 | INTERNAL_SERVER_ERROR | 구독 상태 조회 중 오류가 발생했습니다. | 서버 내부 오류 |

### 보안 설계

**권한 검증 순서:**

```python
# Step 1: Account 소유권 먼저 확인 (가벼운 쿼리)
account = Account.query.filter_by(id=account_id).first()
if not account or account.user_id != current_user.id:
    # Step 2: 권한 없으면 즉시 403 반환 (expensive query 전에 차단)
    return 403  # ACCESS_DENIED

# Step 3: 권한 있으면 StrategyAccount 조회 (expensive loading)
strategy_account = StrategyAccount.query.options(
    joinedload(StrategyAccount.strategy_positions)
).filter_by(strategy_id=strategy_id, account_id=account_id).first()
```

**정보 은닉:**
- 계좌 없음과 권한 없음을 구분하지 않음 → 통일된 403 응답
- 타인의 구독 정보 존재 여부를 탐색 불가능

### 성능 최적화

**N+1 쿼리 방지:**
```python
strategy_account = StrategyAccount.query.options(
    joinedload(StrategyAccount.strategy_positions)  # 포지션 미리 로드
).filter_by(...).first()
```

**예상 쿼리 수:**
1. Account 소유권 확인 (가벼운 쿼리)
2. StrategyAccount + strategy_positions 조회 (joinedload로 1개 쿼리)
3. OpenOrder 조회 (필터링 기반, indexed 칼럼)

**조기 종료:**
- 권한 없는 요청은 expensive query 전에 차단하여 리소스 절약

### 구현 세부사항

**파일:** `web_server/app/routes/strategies.py:484-592`

**함수:** `get_subscription_status(strategy_id: int, account_id: int)`

**기능 태그:** `@FEAT:strategy-subscription-safety @COMP:route @TYPE:core`

**주요 로직:**
- Step 1: Account 소유권 검증 (보안)
- Step 2: StrategyAccount 조회 (권한 확인 후)
- Step 3: 활성 포지션 필터링 (`quantity != 0`)
- Step 4: 미체결 주문 조회 (상태 필터링)
- Step 5: 심볼 목록 추출 (중복 제거, 정렬)
- Step 6: 디버그 로깅 (DEBUG 레벨)
- Step 7: JSON 응답 반환

### 사용 예시

**예시 1: 활성 데이터 존재**
```bash
curl -X GET "http://localhost:8000/api/strategies/123/subscribe/456/status" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**응답:**
```json
{
  "success": true,
  "data": {
    "active_positions": 2,
    "open_orders": 3,
    "symbols": ["BTC/USDT", "ETH/USDT"],
    "is_active": true
  }
}
```

**프론트엔드 활용:** "주의! 활성 포지션 2개와 미체결 주문 3개(BTC/USDT, ETH/USDT)가 있습니다. 구독을 해제하시겠습니까?"

**예시 2: 빈 상태 (활성 데이터 없음)**
```json
{
  "success": true,
  "data": {
    "active_positions": 0,
    "open_orders": 0,
    "symbols": [],
    "is_active": true
  }
}
```

**프론트엔드 활용:** "구독을 안전하게 해제할 수 있습니다."

**예시 3: 권한 없음**
```json
{
  "success": false,
  "error_code": "ACCESS_DENIED",
  "message": "접근 권한이 없습니다."
}
```

**예시 4: 구독 정보 없음**
```json
{
  "success": false,
  "error_code": "RESOURCE_NOT_FOUND",
  "message": "구독 정보를 찾을 수 없습니다."
}
```

### Phase 3 연계

이 API는 **Phase 3 (구독 해제 UI 경고 메시지)**에서 다음과 같이 사용됩니다:

1. 사용자가 "구독 해제" 버튼 클릭
2. 프론트엔드가 본 API 호출 → 상태 데이터 수신
3. `active_positions > 0` 또는 `open_orders > 0`이면 경고 모달 표시
4. 경고 메시지: "활성 포지션 {N}개, 미체결 주문 {M}개({symbols})가 있습니다."
5. 사용자 최종 확인 후 구독 해제 진행

## Phase 3: 프론트엔드 경고 메시지 UI

**Status**: ✅ Complete
**Files**: `web_server/app/templates/strategies.html:1275-1347`

### 개요

전략 구독 해제 전 사용자에게 활성 포지션 및 미체결 주문 현황을 경고 메시지로 표시하여 실수로 인한 포지션 청산을 방지합니다.

### 구현 상세

#### 수정된 함수

**File**: `web_server/app/templates/strategies.html`
**Function**: `async function unsubscribeStrategy(strategyId, accountId)` (Lines 1275-1347)
**Tag**: `@FEAT:strategy-subscription-safety @COMP:frontend @TYPE:validation`

#### 작동 흐름

1. **상태 조회** (Phase 2 API 호출)
   ```javascript
   GET /api/strategies/${strategyId}/subscribe/${accountId}/status
   ```
   - 응답: `{active_positions, open_orders, symbols, is_active}`

2. **경고 메시지 생성**
   - **포지션/주문 있음**: 상세 정보 + 슬리피지 경고
   - **포지션/주문 없음**: 긍정적 빈 상태 메시지

3. **사용자 확인**
   - 브라우저 `confirm()` 다이얼로그로 경고 표시
   - 취소 시 구독 해제 중단

4. **구독 해제 실행**
   ```javascript
   DELETE /api/strategies/${strategyId}/subscribe/${accountId}?force=true
   ```
   - `force=true`: Phase 4에서 백엔드 강제 청산 처리 예정

#### 경고 메시지 예시

**활성 포지션/주문이 있는 경우:**
```
⚠️ 구독 해제 시 다음 작업이 수행됩니다:

📊 활성 포지션 3개 강제 청산 (시장가)
   ⚡ 슬리피지 발생 가능 (시장가 청산으로 예상 가격과 실제 체결가가 다를 수 있음)

📝 미체결 주문 2개 취소

🎯 영향받는 심볼: BTC/USDT, ETH/USDT, BNB/USDT 외 2개

계속하시겠습니까?
```

**포지션/주문이 없는 경우:**
```
현재 활성화된 포지션/주문이 없습니다.
구독을 해제하시겠습니까?
```

#### plan-reviewer 개선사항 반영

1. **심볼 목록 잘림 방지** (Priority 1-1)
   - 5개 초과 시 "외 N개"로 표시 (Lines 1315-1318)
   - `confirm()` 창 오버플로우 방지

2. **슬리피지 경고 명확화** (Priority 1-2)
   - 괄호로 설명 추가: "(시장가 청산으로 예상 가격과 실제 체결가가 다를 수 있음)" (Lines 1305-1307)
   - 비전문가도 이해 가능

3. **빈 상태 메시지 개선** (Priority 1-3)
   - "정리할 항목 없음" → "현재 활성화된 포지션/주문이 없습니다" (Lines 1324-1325)
   - 긍정적 프레이밍으로 사용자 혼란 방지

### 에러 처리

- **상태 조회 실패**: 구독 해제 중단 (safe failure)
  - `apiCall()`이 자동으로 에러 토스트 표시
  - 블라인드 삭제 방지

- **구독 해제 실패**: 에러 토스트 표시, UI 업데이트 안 함
  - `loadSubscribedStrategies()` 호출 안 됨 (성공 시에만 호출)

### 의존성

- **Phase 2 API**: `GET /api/strategies/{id}/subscribe/{account_id}/status` (완료)
- **기존 헬퍼 함수**:
  - `apiCall()` - API 호출 및 에러 처리
  - `showToast()` - 알림 표시
  - `loadSubscribedStrategies()` - UI 새로고침

### 사용 예시

```javascript
// 사용자가 구독 해제 버튼 클릭
unsubscribeStrategy(strategyId, accountId);

// 1. Phase 2 API 호출하여 상태 조회
// 2. 경고 메시지 표시 (포지션 N개, 주문 N개)
// 3. 사용자 확인 후 DELETE 요청
// 4. 성공 시 UI 새로고침
```

### 검색 태그

- `@FEAT:strategy-subscription-safety` - 전체 기능
- `@COMP:frontend` - 프론트엔드 컴포넌트
- `@TYPE:validation` - 사용자 확인/검증

---

## Phase 4: Backend Forced Liquidation on Unsubscribe

**Status**: ✅ Complete
**Files**:
- `web_server/app/services/strategy_service.py:778-961`
- `web_server/app/routes/strategies.py:148-183`

### 개요

구독 해제 시 `force=true` 파라미터를 사용하여 활성 포지션과 미체결 주문을 자동으로 청산/취소합니다.
Phase 1의 7단계 cleanup 패턴을 재사용하여 일관성과 안정성을 보장합니다.

### API 명세

**호출**: `DELETE /api/strategies/{id}/subscribe/{account_id}?force=true`

**Query Parameters**:
- `force` (bool): `true`일 경우 활성 포지션/주문 강제 청산 후 해제 (default: false)

### 7단계 Cleanup 프로세스

(Phase 1과 동일한 패턴, 단일 StrategyAccount 대상)

1. **Race condition 방지** - `is_active=False` + `flush()` (웹훅 차단)
2. **주문 취소** - 3-stage verification
3. **Defensive verification** - 남은 주문 확인
4. **포지션 청산** - 시장가 강제 청산
5. **SSE 연결 해제** - `disconnect_client()` 호출
6. **실패 항목 로깅** - (TODO: 텔레그램 알림)
7. **DB에서 제거** - `StrategyAccount` 삭제

### Backward Compatibility

**`force=false` (기본값)**: 기존 동작 유지
- 활성 포지션 확인 후 있으면 StrategyError 발생
- SSE 클라이언트 정리 (`disconnect_client()` 호출)
- StrategyAccount 즉시 삭제
- 안전한 구독 해제만 허용

**`force=true`**: Phase 4 신규 기능
- 활성 포지션 강제 청산
- 미체결 주문 취소
- Best-effort 방식 (일부 실패해도 계속 진행)
- 모든 cleanup 완료 후 StrategyAccount 삭제

### 구현 세부사항

**파일**: `web_server/app/services/strategy_service.py:778-961`
**태그**: `@FEAT:strategy-subscription-safety @COMP:service @TYPE:core`

**핵심 로직**:
- Line 820-846: force=false 경로 (기존 동작 - SSE 정리 + 즉시 삭제)
- Line 848-961: force=true 경로 (Phase 1 패턴 - 7단계 cleanup)
- Line 856-858: Race condition 방지
- Line 860-875: 주문 취소 + 실패 추적
- Line 877-894: Defensive verification
- Line 896-921: 포지션 청산 (best-effort)
- Line 923-932: SSE 연결 해제
- Line 934-948: 실패 항목 로깅 (TODO: 텔레그램 알림)
- Line 950-961: DB 제거 및 자본 재배분

### 실패 추적 구조 (force=true)

```python
failed_cleanups = [
    {
        'type': 'order_cancellation',  # 주문 취소 실패
        'symbol': 'BTCUSDT',
        'order_id': '12345',
        'reason': 'Insufficient balance'
    },
    {
        'type': 'remaining_order',     # Defensive verification 검출
        'symbol': 'ETHUSDT',
        'order_id': '67890',
        'quantity': '1.5'
    },
    {
        'type': 'position_close',      # 포지션 청산 실패
        'symbol': 'BNBUSDT',
        'quantity': '10.5',
        'reason': 'Market closed'
    },
    {
        'type': 'position_close_exception',  # 포지션 청산 예외
        'symbol': 'ADAUSDT',
        'quantity': '100',
        'reason': 'Connection timeout'
    }
]
```

### 테스트 시나리오

**Scenario 1: force=false + 활성 포지션 있음**
- 요청: `DELETE /api/strategies/1/subscribe/123`
- 결과: StrategyError "활성 포지션이 있는 계좌는 연결 해제할 수 없습니다."

**Scenario 2: force=false + 포지션 없음**
- 요청: `DELETE /api/strategies/1/subscribe/123`
- 결과: 정상 해제

**Scenario 3: force=true + 활성 포지션 있음**
- 요청: `DELETE /api/strategies/1/subscribe/123?force=true`
- 결과: 주문 취소 → 포지션 청산 → 정상 해제
- 로그: "공개 전략 구독 해제 (force): ... 실패 0건"

**Scenario 4: force=true + 일부 청산 실패**
- 요청: `DELETE /api/strategies/1/subscribe/123?force=true`
- 결과: Best-effort로 나머지 진행, 실패 로깅
- 로그: WARNING "[strategy_id=X] 구독 해제 중 N개 항목 정리 실패"

### Phase 1 패턴 재사용

**참조**: `routes/strategies.py:264-430` (make_private_confirm)
**차이점**:
- Phase 1: 다중 StrategyAccount 루프
- Phase 4: 단일 StrategyAccount 처리

**공통점**: 7단계 cleanup 프로세스 동일

---

## Phase 5: Webhook is_active Recheck

**Status**: ✅ Complete
**Files**:
- `web_server/app/services/trading/core.py:144-150, 210-216, 1435-1441`

### 개요

웹훅 주문 실행 직전에 `StrategyAccount.is_active` 상태를 재확인하여, Phase 1/4에서 비활성화된 계좌의 주문이 실행되지 않도록 Race Condition을 완전히 방지합니다.

### Race Condition 타임라인

**Before Phase 5 (문제)**:
```
T0: 웹훅 수신 (매수 신호)
T1: StrategyAccount 조회 (is_active=True)
T2: 주문 준비 및 계산
T3: [Phase 1/4 실행] is_active=False 설정 + flush()
T4: 주문 실행 ❌ (이미 조회한 상태로 진행)
```

**문제**: T1과 T4 사이의 시간 윈도우에서 is_active가 변경되어도 주문이 실행됨

**After Phase 5 (해결)**:
```
T0: 웹훅 수신 (매수 신호)
T1: StrategyAccount 조회 (is_active=True)
T2: 주문 준비 및 계산
T3: [Phase 1/4 실행] is_active=False 설정 + flush()
T4: [Phase 5 체크] is_active 재확인 → False 감지 → 주문 스킵 ✅
```

**효과**: 주문 실행 직전 최종 확인으로 시간 윈도우 완전 차단

### 3개 실행 경로 보호

#### 1. LIMIT/STOP 대기열 진입 (Line 144-150)
**체크 시점**: PendingOrder 진입 직전
**효과**: 대기열 오염 방지
**에러 응답**:
```python
{
    'success': False,
    'error': 'StrategyAccount가 비활성 상태입니다',
    'error_type': 'account_inactive',
    'account_id': account.id,
    'account_name': account.name,
    'strategy_account_id': strategy_account.id,
    'skipped': True,
    'skip_reason': 'strategy_account_inactive'
}
```
**로그**: `⚠️ [Phase 5] StrategyAccount {id} 비활성 상태 - LIMIT/STOP 대기열 진입 스킵 (전략: {strategy}, 계좌: {account}, 심볼: {symbol})`

#### 2. MARKET 주문 즉시 실행 (Line 210-216)
**체크 시점**: 거래소 API 호출 직전
**효과**: 즉시 실행 주문 차단
**에러 응답**: 위와 동일
**로그**: `⚠️ [Phase 5] StrategyAccount {id} 비활성 상태 - MARKET 주문 스킵 (전략: {strategy}, 계좌: {account}, 심볼: {symbol}, 방향: {side})`

#### 3. 배치 주문 실행 (Line 1435-1441)
**체크 시점**: 배치 실행 직전
**효과**: 다중 주문 일괄 차단
**배치 응답 구조** (원본 인덱스 매핑):
```python
[
    {
        'order_index': original_idx,
        'success': False,
        'error': 'StrategyAccount가 비활성 상태입니다',
        'error_type': 'account_inactive',
        'account_id': account.id,
        'account_name': account.name,
        'strategy_account_id': strategy_account.id,
        'skipped': True,
        'skip_reason': 'strategy_account_inactive',
        'batch_skipped': True
    }
]
```
**특징**: `original_index` 보존으로 정확한 에러 리포팅
**로그**: `⚠️ [Phase 5] StrategyAccount {id} 비활성 상태 - 배치 주문 실행 스킵 (전략: {strategy}, 계좌: {account})`

### 구현 세부사항

**hasattr() 방어 패턴**:
```python
if hasattr(strategy_account, 'is_active') and not strategy_account.is_active:
    # 주문 스킵
```
- 레거시 데이터 호환 (`is_active` 필드 없는 경우)
- 기존 코드 패턴 일치 (core.py Lines 730, 1054)

**성능 영향**:
- DB 재조회 없음 (이미 로드된 객체 속성 접근만)
- 오버헤드 < 1ms (hasattr + 속성 read)

### 안전성 체인 완성

Phase 5는 전체 안전성 체인의 마지막 조각입니다:

```
Phase 1/4: is_active=False 설정 (cleanup 시작)
    ↓
Phase 5: is_active 재확인 (실행 직전 게이트)
    ↓
완전한 Race Condition 방지 ✅
```

**다층 방어 (Defense in Depth)**:
- **1차 방어**: Phase 1/4에서 `is_active=False` + `flush()`
- **2차 방어**: Phase 5에서 주문 실행 직전 재확인
- **효과**: 시간 순서에 관계없이 비활성 계좌는 절대 주문 실행 불가

### 기능 태그

```python
# @FEAT:strategy-subscription-safety @COMP:service @TYPE:core
```

위치 (`web_server/app/services/trading/core.py`):
- Line 144-150: LIMIT/STOP 대기열 재확인
- Line 210-216: MARKET 주문 재확인
- Line 1435-1441: 배치 주문 재확인

### 테스트 시나리오

**Scenario 1: 정상 동작** (is_active=True)
- 웹훅 수신 → Phase 5 체크 통과 → 주문 실행
- 로그: `[Phase 5]` 메시지 없음

**Scenario 2: MARKET 주문 Race Condition**
- Phase 1/4 실행으로 is_active=False 설정
- 웹훅 수신 (MARKET) → Phase 5 체크 실패 → 주문 스킵
- 로그: `⚠️ [Phase 5] ... MARKET 주문 스킵`

**Scenario 3: LIMIT/STOP 대기열 Race Condition**
- is_active=False 설정 후 웹훅 수신
- Phase 5 체크 실패 → 대기열 진입 차단
- 로그: `⚠️ [Phase 5] ... LIMIT/STOP 대기열 진입 스킵`

**Scenario 4: 배치 주문 Race Condition**
- is_active=False 설정 후 배치 웹훅 수신
- Phase 5 체크 실패 → 배치 전체 스킵
- 결과: 모든 주문에 `batch_skipped=True` 표시

### 로그 예시

**정상 케이스** (Phase 5 로그 없음):
```
INFO: 📥 대기열 진입 (웹훅) - 타입: LIMIT, 심볼: BTC/USDT, ...
INFO: ✅ 거래 실행 성공 (주문 ID: 12345...)
```

**Race Condition 차단 케이스**:
```
WARNING: ⚠️ [Phase 5] StrategyAccount 123 비활성 상태 - MARKET 주문 스킵 (전략: My Strategy, 계좌: Binance Main, 심볼: BTC/USDT, 방향: BUY)
```

## 관련 링크

- 기능 카탈로그: `docs/FEATURE_CATALOG.md`
- 기능 태그 검색: `grep -r "@FEAT:strategy-subscription-safety" --include="*.py"`

---

## Known Issues

### Variable Shadowing in unsubscribe_from_strategy (strategy_service.py:817)
**이상한 점**: `strategy_name` 변수를 StrategyAccount 삭제 직후에 lazy load하려고 시도함
**이유**: 세션 분리 후 lazy load 방지를 위해 삭제 전에 strategy.name 캐싱 필수. 현재 코드는 hasattr/if 체크로 우회함.
**참고**: 향후 strategy 관계를 명시적 lazy load로 정리 필요

## Last Updated

**2025-10-30** - 코드 기준 전체 동기화 완료
- Phase 1: 공개→비공개 전환 (routes/strategies.py:274-431)
- Phase 2: 구독 상태 조회 API (routes/strategies.py:495-602)
- Phase 3: 프론트엔드 경고 UI (상세 코드 경로 확인 필요)
- Phase 4: 강제 청산 (service/strategy_service.py:778-961)
- Phase 5: Webhook is_active 재확인 (trading/core.py 실행 경로)
