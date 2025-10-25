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

**조회**:
- `get_strategies_by_user(user_id)`: 소유 전략 목록
- `get_accessible_strategies(user_id)`: 소유 + 구독 전략

**생성/수정/삭제**:
- `create_strategy(user_id, strategy_data)`: 전략 생성 + 계좌 연결 + 자본 할당
- `update_strategy(strategy_id, user_id, update_data)`: 전략 수정 (is_public → False 시 구독자 연결 비활성화)
- `delete_strategy(strategy_id, user_id)`: 전략 삭제 (제약: 계좌 연결 없음, 활성 포지션 없음)

**계좌 연결**:
- `connect_account_to_strategy()`: 계좌 연결
- `subscribe_to_strategy()`: 공개 전략 구독
- `unsubscribe_from_strategy()`: 구독 해제 (제약: 활성 포지션 없음)

**검증** (`@TYPE:validation`):
- `_validate_strategy_data()`: RCE 예방 (타입/길이/정규식/위험문자 검증)
- `_validate_account_data()`: weight(0.01~100), leverage(0.1~125), max_symbols(1~1000)

### API 엔드포인트 (주요)

| Method | Endpoint | 설명 | 권한 |
|--------|----------|------|------|
| GET | `/api/strategies` | 소유 전략 목록 | 소유자 |
| GET | `/api/strategies/public` | 공개 전략 목록 | 모든 사용자 |
| POST | `/api/strategies` | 전략 생성 | 인증 사용자 |
| PUT | `/api/strategies/{id}` | 전략 수정 | 소유자 |
| DELETE | `/api/strategies/{id}` | 전략 삭제 | 소유자 |
| POST | `/api/strategies/{id}/subscribe` | 공개 전략 구독 | 인증 사용자 |
| DELETE | `/api/strategies/{id}/subscribe/{account_id}` | 구독 해제 | 구독자 |
| POST | `/api/strategies/{id}/accounts` | 계좌 연결 | 소유자 |
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

1. **전략 삭제 제약**: 계좌 연결 및 활성 포지션이 없어야 삭제 가능
   - 해결: 포지션 청산 → 계좌 연결 해제 → 전략 삭제 순서

2. **is_public 전환**: True → False 전환 시 구독자 연결 자동 비활성화 (데이터 삭제 없음)

3. **전략 격리**: DB 쿼리에서 `strategy_account_id` 필터링 필수
   ```python
   # 특정 전략의 주문만 조회
   OpenOrder.query.join(StrategyAccount).filter(
       StrategyAccount.strategy_id == strategy_id
   ).all()
   ```

4. **CASCADE 삭제**: StrategyAccount 삭제 시 하위 데이터 자동 삭제
   - StrategyCapital, StrategyPosition, Trade, OpenOrder

### 확장 포인트

1. **전략 타입 추가**: `market_type` enum 확장 (예: OPTIONS)
2. **전략 성과 분석**: `routes/strategies.py:GET /api/strategies/{id}/performance/*`
3. **구독 제한**: `max_subscribers` 필드 추가 (유료 전략 구현)
4. **자본 할당 알고리즘**: `analytics_service.auto_allocate_capital_for_account()` 커스터마이징

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

*Last Updated: 2025-10-10*
*Lines: ~250 (간결화: 853줄 → 250줄, 70% 축소)*
*Feature Tags: `@FEAT:strategy-management`*
*Dependencies: webhook-order, capital-management, order-tracking, position-tracking*
