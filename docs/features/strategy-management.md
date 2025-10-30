# Strategy Management (전략 관리)

## 1. Purpose (개요)

트레이딩 전략의 CRUD 관리 시스템. 웹훅 주문 처리의 핵심 단위로, 계좌 연결, 자본 배분, 주문/포지션 격리를 담당합니다.

**핵심 기능**: 전략 생성/수정/삭제, 전략-계좌 연결, 공개/비공개 전략, 웹훅 토큰 인증, 전략별 격리

**Feature Tags**: `@FEAT:strategy-management`

---

## 2. Execution Flow (실행 플로우)

### 전략 생명주기
```
생성 (Created) → 활성화 (Active) ←→ 비활성화 (Inactive)
                  ↓ 웹훅 수신 가능    ↓ 웹훅 수신 불가
                주문 처리              (대기 상태)
                  ↓
                삭제 (조건: 계좌 연결 없음, 활성 포지션 없음)
```

### 웹훅 주문 처리
```
TradingView Webhook
  ↓ POST /api/webhook
  ├─ group_name 추출
  ├─ token 검증 (_validate_strategy_token)
  │   ├─ Strategy 조회 (group_name, is_active=True)
  │   ├─ 소유자 토큰 확인
  │   └─ 구독자 토큰 확인 (is_public=True인 경우)
  ↓
전략 조회 성공 → 연결된 계좌 조회 → 각 계좌별 주문 실행
```

### 공개 전략 구독
```
구독자 → 공개 전략 목록 조회 (GET /api/strategies/public)
       → 구독 (POST /api/strategies/{id}/subscribe)
       → 계좌 연결 (StrategyAccount 생성)
       → 자본 자동 배분
       → 웹훅 수신 시 구독자 토큰으로 주문 가능
```

---

## 3. Data Flow (데이터 플로우)

### 전략 생성 플로우
```
Input: {name, group_name, description, market_type, is_active, is_public, accounts[]}
  ↓ 검증 (_validate_strategy_data, _validate_account_data)
  ↓ Strategy 생성 (DB)
  ↓ StrategyAccount 생성 (계좌 연결)
  ↓ StrategyCapital 생성 (자본 할당)
Output: {strategy_id, name, group_name, market_type}
```

### 주문 실행 플로우
```
Webhook Request
  ↓ group_name → Strategy 조회
  ↓ strategy_accounts → 계좌 목록
  ↓ strategy_account_id → 주문/포지션 격리
  ↓ OpenOrder (strategy_account_id로 저장)
  ↓ StrategyPosition (strategy_account_id로 추적)
```

**주요 의존성**:
- `webhook-order`: 웹훅 토큰 검증 및 주문 실행
- `capital-management`: 전략별 자본 배분
- `order-tracking`: 전략별 주문 격리
- `position-tracking`: 전략별 포지션 격리

---

## 4. Components (주요 컴포넌트)

| 파일 | 역할 | 태그 | 핵심 메서드 |
|------|------|------|-------------|
| `services/strategy_service.py` | 전략 비즈니스 로직 | `@FEAT:strategy-management @COMP:service @TYPE:core` | `create_strategy()`, `update_strategy()`, `delete_strategy()`, `subscribe_to_strategy()` |
| `routes/strategies.py` | REST API 엔드포인트 | `@FEAT:strategy-management @COMP:route @TYPE:core` | GET/POST/PUT/DELETE `/api/strategies/*` |
| `models.py:Strategy` | 전략 데이터 모델 | `@FEAT:strategy-management @COMP:model @TYPE:core` | `group_name`, `is_public`, `is_active` |
| `models.py:StrategyAccount` | 전략-계좌 연결 | `@FEAT:strategy-management @COMP:model @TYPE:core` | `weight`, `leverage`, `max_symbols` |

### StrategyService 주요 메서드

**권한 검증**:
- `verify_strategy_access(strategy_id, user_id)`: 소유자 또는 구독자 여부 확인 (보안: 전략 미존재 시 403)

**조회**:
- `get_strategies_by_user(user_id)`: 소유 전략 목록
- `get_accessible_strategies(user_id)`: 소유 + 구독 전략

**생성/수정/삭제**:
- `create_strategy(user_id, strategy_data)`: 전략 생성 + 계좌 연결 + 자본 할당
- `update_strategy(strategy_id, user_id, update_data)`: 전략 수정 (is_public → False 시 구독자 연결 비활성화)
- `delete_strategy(strategy_id, user_id)`: 전략 삭제 (제약: 계좌 연결 없음, 활성 포지션 없음)

**계좌 연결**:
- `connect_account_to_strategy()`: 계좌 연결
- `update_strategy_account()`: 전략-계좌 설정 업데이트 (is_active, weight, leverage, max_symbols)
- `subscribe_to_strategy()`: 공개 전략 구독
- `unsubscribe_from_strategy(force=False)`: 구독 해제
  - `force=False` (기본): 활성 포지션 없을 때만 해제
  - `force=True` (Phase 4): 활성 포지션/주문 강제 청산 후 해제

**검증** (`@TYPE:validation`):
- `_validate_strategy_data()`: RCE 예방 (타입/길이/정규식/위험문자 검증)
- `_validate_account_data()`: weight(0.01~100), leverage(0.1~125), max_symbols(1~1000)

### API 엔드포인트 (주요)

| Method | Endpoint | 설명 | 권한 |
|--------|----------|------|------|
| GET | `/api/strategies` | 소유 전략 목록 | 인증 사용자 |
| GET | `/api/strategies/accessibles` | 소유 + 구독 전략 | 인증 사용자 |
| GET | `/api/strategies/public` | 공개 전략 목록 (기본정보) | 인증 사용자 |
| GET | `/api/strategies/public/{id}` | 공개 전략 상세 조회 | 인증 사용자 |
| POST | `/api/strategies` | 전략 생성 | 인증 사용자 |
| PUT | `/api/strategies/{id}` | 전략 수정 | 소유자 |
| DELETE | `/api/strategies/{id}` | 전략 삭제 | 소유자 |
| POST | `/api/strategies/{id}/subscribe` | 공개 전략 구독 | 인증 사용자 |
| DELETE | `/api/strategies/{id}/subscribe/{account_id}` | 구독 해제 (force 파라미터 지원) | 구독자 |
| GET | `/api/strategies/{id}/subscribe/{account_id}/status` | 구독 상태 조회 (활성 포지션/주문 확인) | 구독자 |
| POST | `/api/strategies/{id}/toggle` | 전략 활성화/비활성화 토글 | 소유자 |
| POST | `/api/strategies/{id}/accounts` | 계좌 연결 | 소유자 |
| GET | `/api/strategies/{id}/accounts` | 연결된 계좌 목록 조회 | 소유자 |
| PUT | `/api/strategies/{id}/accounts/{account_id}` | 계좌 설정 업데이트 | 소유자 |
| DELETE | `/api/strategies/{id}/accounts/{account_id}` | 계좌 연결 해제 | 소유자 |

### 데이터 모델

**Strategy** (`models.py:249-269`):
```python
# @FEAT:strategy-management @COMP:model @TYPE:core
id, user_id, name, description
group_name (unique, 웹훅 연동 키)
market_type (SPOT/FUTURES)
is_active (활성화 상태)
is_public (공개 전략 여부)
created_at, updated_at
```

**StrategyAccount** (`models.py:271-295`):
```python
# @FEAT:strategy-management @COMP:model @TYPE:core
id, strategy_id, account_id
weight (자본 배분 비중)
leverage (레버리지)
max_symbols (최대 보유 심볼 수)
is_active (연결 활성화 상태)
# CASCADE: 삭제 시 StrategyCapital, StrategyPosition, Trade, OpenOrder 자동 삭제
```

---

## 5. Design Decisions (설계 결정)

### 전략 격리 메커니즘
**WHY**: 동일 계좌에서 여러 전략 사용 시 주문/포지션 간섭 방지

**구현**:
- **주문 격리**: `OpenOrder.strategy_account_id`로 전략별 주문 구분
- **포지션 격리**: `StrategyPosition.strategy_account_id`로 전략별 포지션 추적
- **자본 격리**: `StrategyCapital.allocated_capital` 전략별 할당

**예시**:
```
계좌: Binance Account A (account_id=1)
전략1: BTC Momentum (strategy_id=1, sa_id=1)
전략2: ETH Swing (strategy_id=2, sa_id=2)

OpenOrder:
- order1: sa_id=1, symbol=BTC/USDT (전략1 주문)
- order2: sa_id=2, symbol=ETH/USDT (전략2 주문)

CANCEL_ALL_ORDER (전략1) → order1만 취소, order2 유지
```

### 공개 전략 보안
**WHY**: 공개 전략 소유자의 시그널을 다수가 따라가되, 타인 계좌 간섭 방지

**구현**:
- 구독자는 자신의 계좌만 연결 가능
- 구독자의 토큰으로 주문 시 자신의 계좌에만 실행
- 전략 소유자는 구독자 계좌 정보 열람 불가 (API 필터링)

### 웹훅 토큰 검증
**WHY**: 전략별 주문 권한 제어

**로직** (`webhook_service.py:_validate_strategy_token`):
```python
# @FEAT:webhook-order @FEAT:strategy-management @COMP:validation @TYPE:validation
valid_tokens = set()
# 1. 소유자 토큰 (항상 허용, 방어적 getattr 사용)
owner = strategy.user
if owner and getattr(owner, 'webhook_token', None):
    valid_tokens.add(owner.webhook_token)
# 2. 구독자 토큰 (is_public=True인 경우만, 예외 처리 포함)
if getattr(strategy, 'is_public', False):
    try:
        for sa in strategy.strategy_accounts:
            if getattr(sa, 'is_active', True) and getattr(sa, 'account', None):
                account_user = getattr(sa.account, 'user', None)
                user_token = getattr(account_user, 'webhook_token', None) if account_user else None
                if user_token:
                    valid_tokens.add(user_token)
    except Exception:
        pass
# 3. 토큰 검증
if token not in valid_tokens: raise WebhookError()
```

### RCE 예방 수칙
**검증 항목** (`strategy_service.py:_validate_strategy_data`):
- 타입 검증: dict, str, bool, int, float만 허용
- 길이 제한: name(100), group_name(50), description(1000)
- 정규식: `group_name = ^[a-zA-Z0-9_-]+$`
- 위험 문자 차단: `<`, `>`, `{`, `}`, `"`, `'`, `\`, `\n`, `\r`
- 범위: weight(0.01~100), leverage(0.1~125), max_symbols(1~1000)

---

## 6. Maintenance Guide (유지보수 가이드)

### 주의사항

1. **권한 검증 (verify_strategy_access)**: 모든 전략 조회/수정에서 사용 필수
   - 소유자 또는 활성 구독자(StrategyAccount) 확인
   - 보안상 전략 미존재 시 403 응답 (404 아님)
   - 구독자 여부: `StrategyAccount.is_active=True && Account.user_id=user_id`

2. **전략 삭제 제약**: 계좌 연결 및 활성 포지션이 없어야 삭제 가능
   - 해결: 포지션 청산 → 계좌 연결 해제 → 전략 삭제 순서

3. **is_public 전환**: True → False 전환 시 구독자 연결 자동 비활성화 (데이터 삭제 없음)

4. **전략 격리**: DB 쿼리에서 `strategy_account_id` 필터링 필수
   ```python
   # 특정 전략의 주문만 조회
   OpenOrder.query.join(StrategyAccount).filter(
       StrategyAccount.strategy_id == strategy_id
   ).all()
   ```

5. **CASCADE 삭제**: StrategyAccount 삭제 시 하위 데이터 자동 삭제
   - StrategyCapital, StrategyPosition, Trade, OpenOrder

### Phase 4: 안전한 구독 해제 (force 청산)

**구독 해제 플로우** (`unsubscribe_from_strategy(force=False)`):
1. **비활성화**: `is_active = False` (웹훅 차단)
2. **주문 취소**: `cancel_all_orders_by_user()` 호출
3. **포지션 청산**: `close_position_by_id()` 호출
4. **SSE 연결**: `disconnect_client()` 강제 종료
5. **DB 삭제**: StrategyAccount 제거
6. **자본 재배분**: 남은 전략들에 대해 자동 할당

**구현** (`strategy_service.py:778-961`):
```python
# force=True: 3-stage verification + cleanup tracking
1️⃣ is_active=False → flush (DB 즉시 반영, race condition 방지)
2️⃣ order_manager.cancel_all_orders_by_user() → failed_orders 추적
3️⃣ Defensive verification → OpenOrder 남은 항목 확인
4️⃣ position_manager.close_position_by_id() → 예외 처리
5️⃣ event_service.disconnect_client() → SSE 강제 종료
6️⃣ Failed cleanup 로깅 (TODO: 텔레그램 알림)
7️⃣ DB 삭제 + 자본 재배분
```

### 전략 비공개 전환 (is_public 제어)

**True → False 전환 시** (`routes/strategies.py:279-431`):
- **N+1 최적화**: `joinedload` 사용 모든 데이터 미리 로드
- **배타적 비활성화**: 구독자 계좌만 비활성화 (`sa.account.user_id != current_user.id && is_active=True`)
- **주문 취소 + 포지션 청산**: 각 구독자별로 cleanup 수행
- **SSE 강제 종료**: 모든 구독자 연결 해제
- **실패 추적**: `failed_cleanups` 리스트로 모든 오류 기록
- **로깅**: 완료 상황(성공/실패) 기록

**예시**:
```
전략: BTC-Signal (is_public=True → False로 전환)
구독자 1: Alice (sa.is_active=True) → 비활성화 + 청산
구독자 2: Bob (sa.is_active=True) → 비활성화 + 청산
결과: 구독 연결은 유지(데이터 삭제 없음), 단 비활성 상태
```

### 구독 상태 조회 API

**엔드포인트**: `GET /api/strategies/{id}/subscribe/{account_id}/status`

**응답 데이터**:
```json
{
  "success": true,
  "data": {
    "active_positions": 2,          # quantity != 0인 포지션
    "open_orders": 3,               # OPEN/PARTIALLY_FILLED/NEW 주문
    "symbols": ["BTC/USDT", "ETH/USDT"],  # 영향받는 심볼 (정렬)
    "is_active": true               # 구독 활성 상태
  }
}
```

**구현 로직** (`routes/strategies.py:495-602`):
1. 계좌 소유권 확인 (보안: 가벼운 쿼리로 권한 먼저 검증)
2. StrategyAccount 조회 (joinedload 최적화)
3. 활성 포지션 필터링 (quantity != 0만)
4. 미체결 주문 조회 (OPEN/PARTIALLY_FILLED/NEW)
5. 심볼 추출 및 정렬

### 전략 성과 분석 API

**ROI 조회**: `GET /api/strategies/{id}/performance/roi`
- Query: `days` (일 단위, 생략 시 전체 기간)
- 응답: ROI(%), total_pnl, invested_capital, profit_factor, avg_win/loss

**성과 요약**: `GET /api/strategies/{id}/performance/summary`
- Query: `days` (기본값: 30)
- 응답: total_return, daily_pnl, total_trades, win_rate, max_drawdown 등

**일일 성과**: `GET /api/strategies/{id}/performance/daily`
- Query: `date` (YYYY-MM-DD, 생략 시 오늘)
- 응답: daily_pnl, sharpe_ratio, sortino_ratio, volatility 등

**의존성**: `performance_tracking_service` (`services/performance_tracking.py`)

### 확장 포인트

1. **전략 타입 추가**: `market_type` enum 확장 (예: OPTIONS)
2. **구독 제한**: `max_subscribers` 필드 추가 (유료 전략 구현)
3. **자본 할당 알고리즘**: `analytics_service.auto_allocate_capital_for_account()` 커스터마이징
4. **텔레그램 알림**: `unsubscribe_from_strategy(force=True)` 실패 시 (TODO 참고)

### Grep 검색 예시

```bash
# 전략 관리 모든 코드
grep -r "@FEAT:strategy-management" --include="*.py"

# 핵심 로직만
grep -r "@FEAT:strategy-management" --include="*.py" | grep "@TYPE:core"

# 검증 로직만
grep -r "@FEAT:strategy-management" --include="*.py" | grep "@TYPE:validation"

# 웹훅 통합 지점
grep -r "@FEAT:webhook-order" --include="*.py" | grep "@FEAT:strategy-management"

# 토큰 검증 로직
grep -n "_validate_strategy_token" web_server/app/services/webhook_service.py
```

---

## Related Documents

- **[Webhook Order Processing](./webhook-order-processing.md)**: 전략과 웹훅의 통합
- **[Capital Management](./capital-management.md)**: 전략별 자본 배분 로직
- **[Order Queue System](./order-queue-system.md)**: 전략별 주문 격리
- **[Position Tracking](./position-tracking.md)**: 전략별 포지션 관리
- **[ARCHITECTURE.md](../ARCHITECTURE.md)**: 시스템 전체 아키텍처

---

*Last Updated: 2025-10-30*
*Lines: ~330 (최신화: 코드 기준)*
*Feature Tags: `@FEAT:strategy-management`, `@FEAT:strategy-subscription-safety`*
*Dependencies: webhook-order, capital-management, order-tracking, position-tracking, performance-tracking*

**변경 사항** (2025-10-30):
- Phase 4 안전한 구독 해제 (force 청산) 메커니즘 추가 → unsubscribe_from_strategy(force=True)
- 전략 비공개 전환 시 구독자 청산 로직 상세화 (is_public: True→False)
- 구독 상태 조회 API 문서화 → GET /strategies/{id}/subscribe/{account_id}/status
- 전략-계좌 업데이트 메서드 추가 → update_strategy_account()
- 전략 성과 분석 API 문서화 (ROI, 성과 요약, 일일 성과)
- 전략 토글 API 추가 → POST /strategies/{id}/toggle
