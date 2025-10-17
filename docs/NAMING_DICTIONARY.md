# Naming Dictionary

> **목적**: 프로젝트 전체에서 일관된 네이밍을 유지하여 코드 가독성과 유지보수성을 향상시킵니다.
> AI가 코드를 생성할 때도 이 사전을 참조하여 일관성을 유지해야 합니다.

**문제 방지**: Frankenstein Code (Problem #2) - 여러 AI/개발자가 같은 기능을 다른 이름으로 구현하는 것을 방지

---

## 🎯 네이밍 원칙

1. **명확성 우선**: 함수/변수 이름만 보고도 역할을 알 수 있어야 함
2. **일관성 유지**: 같은 동작은 항상 같은 동사를 사용
3. **중복 금지**: 유사 기능을 다른 이름으로 구현하지 않음
4. **검색 가능**: 네이밍 사전에 등록된 이름만 사용

---

## 📚 데이터 조회 (Read Operations)

### ✅ 승인된 네이밍

| 용도 | 함수명 패턴 | 예시 |
|------|------------|------|
| **단일 항목 조회** | `get_<entity>()` | `get_user()`, `get_order()`, `get_strategy()` |
| **목록 조회** | `get_<entities>()` 또는 `list_<entities>()` | `get_users()`, `list_orders()` |
| **검색/필터링** | `find_<entities>()` | `find_users_by_email()`, `find_orders_by_status()` |
| **존재 확인** | `exists_<entity>()` | `exists_user()`, `exists_strategy()` |
| **개수 세기** | `count_<entities>()` | `count_orders()`, `count_active_positions()` |

### ❌ 사용 금지

- ❌ `fetchUser()` → ✅ `get_user()`
- ❌ `retrieveOrder()` → ✅ `get_order()`
- ❌ `loadStrategy()` → ✅ `get_strategy()`
- ❌ `queryUsers()` → ✅ `find_users()` 또는 `list_users()`

---

## 📝 데이터 생성 (Create Operations)

### ✅ 승인된 네이밍

| 용도 | 함수명 패턴 | 예시 |
|------|------------|------|
| **신규 생성** | `create_<entity>()` | `create_user()`, `create_order()`, `create_strategy()` |
| **등록** | `register_<entity>()` | `register_account()`, `register_exchange()` |
| **추가** | `add_<entity>()` | `add_to_queue()`, `add_subscriber()` |

### ❌ 사용 금지

- ❌ `insertOrder()` → ✅ `create_order()`
- ❌ `newUser()` → ✅ `create_user()`
- ❌ `saveStrategy()` → ✅ `create_strategy()` (신규 생성 시)

---

## 🔄 데이터 수정 (Update Operations)

### ✅ 승인된 네이밍

| 용도 | 함수명 패턴 | 예시 |
|------|------------|------|
| **전체 수정** | `update_<entity>()` | `update_user()`, `update_order()` |
| **부분 수정** | `modify_<attribute>()` | `modify_quantity()`, `modify_price()` |
| **변경** | `change_<attribute>()` | `change_status()`, `change_priority()` |
| **설정** | `set_<attribute>()` | `set_active()`, `set_priority()` |
| **저장 (기존 수정)** | `save_<entity>()` | `save_user()`, `save_order()` |

### ❌ 사용 금지

- ❌ `editUser()` → ✅ `update_user()`
- ❌ `alterOrder()` → ✅ `update_order()`
- ❌ `modifyUser()` → ✅ `update_user()` (전체 수정 시)

---

## 🗑️ 데이터 삭제 (Delete Operations)

### ✅ 승인된 네이밍

| 용도 | 함수명 패턴 | 예시 |
|------|------------|------|
| **영구 삭제** | `delete_<entity>()` | `delete_user()`, `delete_order()` |
| **소프트 삭제** | `deactivate_<entity>()` 또는 `archive_<entity>()` | `deactivate_strategy()`, `archive_order()` |
| **제거** | `remove_<entity>()` | `remove_from_queue()`, `remove_subscriber()` |
| **취소** | `cancel_<entity>()` | `cancel_order()`, `cancel_trade()` |

### ❌ 사용 금지

- ❌ `destroyUser()` → ✅ `delete_user()`
- ❌ `eraseOrder()` → ✅ `delete_order()`
- ❌ `killStrategy()` → ✅ `deactivate_strategy()`

---

## ✔️ 검증 (Validation Operations)

### ✅ 승인된 네이밍

| 용도 | 함수명 패턴 | 예시 |
|------|------------|------|
| **검증** | `validate_<entity>()` | `validate_order()`, `validate_email()` |
| **확인 (boolean)** | `is_<condition>()` | `is_valid()`, `is_active()`, `is_owner()` |
| **가능 여부** | `can_<action>()` | `can_execute()`, `can_cancel()` |
| **소유 여부** | `has_<attribute>()` | `has_permission()`, `has_balance()` |

### ❌ 사용 금지

- ❌ `checkEmail()` → ✅ `validate_email()`
- ❌ `verifyOrder()` → ✅ `validate_order()`
- ❌ `isEmailValid()` → ✅ `is_valid_email()` (is_로 시작)

---

## 🔄 비즈니스 로직 (Business Operations)

### ✅ 승인된 네이밍

| 용도 | 함수명 패턴 | 예시 |
|------|------------|------|
| **처리** | `process_<entity>()` | `process_webhook()`, `process_order()` |
| **실행** | `execute_<action>()` | `execute_trade()`, `execute_strategy()` |
| **계산** | `calculate_<metric>()` | `calculate_quantity()`, `calculate_pnl()` |
| **변환** | `convert_<from>_to_<to>()` | `convert_to_exchange_format()` |
| **동기화** | `sync_<entity>()` | `sync_positions()`, `sync_orders()` |

### ❌ 사용 금지

- ❌ `handleWebhook()` → ✅ `process_webhook()`
- ❌ `doTrade()` → ✅ `execute_trade()`
- ❌ `computeQuantity()` → ✅ `calculate_quantity()`

---

## 📊 집계 및 통계 (Aggregation)

### ✅ 승인된 네이밍

| 용도 | 함수명 패턴 | 예시 |
|------|------------|------|
| **합계** | `sum_<metric>()` | `sum_pnl()`, `sum_volumes()` |
| **평균** | `average_<metric>()` | `average_price()`, `average_win_rate()` |
| **집계** | `aggregate_<metric>()` | `aggregate_trades()`, `aggregate_by_strategy()` |

---

## 🔐 인증 및 권한 (Auth Operations)

### ✅ 승인된 네이밍

| 용도 | 함수명 패턴 | 예시 |
|------|------------|------|
| **인증** | `authenticate_<entity>()` | `authenticate_user()`, `authenticate_webhook()` |
| **권한 확인** | `authorize_<action>()` | `authorize_access()`, `authorize_trade()` |
| **로그인** | `login()` | `login()` |
| **로그아웃** | `logout()` | `logout()` |
| **토큰 생성** | `generate_token()` | `generate_auth_token()` |
| **토큰 검증** | `verify_token()` | `verify_webhook_token()` |

---

## 🎯 클래스 네이밍

### ✅ 승인된 네이밍

| 타입 | 네이밍 패턴 | 예시 |
|------|------------|------|
| **Service** | `<Entity>Service` | `OrderService`, `WebhookService`, `TradingService` |
| **Repository** | `<Entity>Repository` | `UserRepository`, `OrderRepository` |
| **Manager** | `<Entity>Manager` | `OrderManager`, `PositionManager` |
| **Calculator** | `<Entity>Calculator` | `QuantityCalculator`, `PnLCalculator` |
| **Validator** | `<Entity>Validator` | `OrderValidator`, `SymbolValidator` |
| **Factory** | `<Entity>Factory` | `ExchangeFactory`, `OrderFactory` |
| **Adapter** | `<Entity>Adapter` | `BinanceAdapter`, `BybitAdapter` |

### ❌ 사용 금지

- ❌ `OrderHandler` → ✅ `OrderService` 또는 `OrderManager`
- ❌ `OrderHelper` → ✅ `OrderService` (역할에 따라)
- ❌ `OrderUtil` → ✅ 구체적인 이름 사용 (예: `OrderValidator`)

---

## 📦 변수 네이밍

### ✅ 승인된 네이밍

| 타입 | 네이밍 패턴 | 예시 |
|------|------------|------|
| **Boolean** | `is_<condition>`, `has_<attribute>`, `can_<action>` | `is_active`, `has_permission`, `can_trade` |
| **List/Array** | `<entity>_list` 또는 `<entities>` | `order_list`, `orders` |
| **Dictionary** | `<entity>_dict` 또는 `<entity>_map` | `user_dict`, `symbol_map` |
| **Count** | `<entity>_count` 또는 `num_<entities>` | `order_count`, `num_trades` |
| **Total** | `total_<metric>` | `total_volume`, `total_pnl` |

### ❌ 사용 금지

- ❌ `orderArr` → ✅ `orders` 또는 `order_list`
- ❌ `userMap` → ✅ `user_dict` 또는 `users_by_id`
- ❌ `cnt` → ✅ `count` 또는 `<entity>_count`

---

## 🔄 상태 및 플래그

### ✅ 승인된 네이밍

| 상태 | 변수명 | 설명 |
|------|--------|------|
| **활성 상태** | `is_active` | True = 활성, False = 비활성 |
| **완료 상태** | `is_completed` | True = 완료, False = 미완료 |
| **체결 상태** | `is_filled` | True = 체결, False = 미체결 |
| **성공 상태** | `is_success` | True = 성공, False = 실패 |
| **유효 상태** | `is_valid` | True = 유효, False = 무효 |

---

## 🎨 예외 네이밍 (Exceptions)

### ✅ 승인된 네이밍

| 타입 | 네이밍 패턴 | 예시 |
|------|------------|------|
| **기본 예외** | `<Entity>Error` | `OrderError`, `ValidationError` |
| **특정 예외** | `<Entity><Reason>Error` | `OrderNotFoundError`, `InsufficientBalanceError` |
| **비즈니스 예외** | `<BusinessReason>Exception` | `InvalidQuantityException`, `ExchangeConnectionException` |

### ❌ 사용 금지

- ❌ `OrderException` → ✅ `OrderError` (Error 접미사 사용)
- ❌ `BadOrderError` → ✅ `InvalidOrderError` (명확한 형용사 사용)

---

## 📝 상수 네이밍

### ✅ 승인된 네이밍

```python
# 전역 상수: UPPER_SNAKE_CASE
MAX_ORDER_QUEUE_SIZE = 200
DEFAULT_TIMEOUT_SECONDS = 30
WEBHOOK_TOKEN_LENGTH = 32

# Enum 값: PascalCase
class OrderStatus(Enum):
    Pending = "pending"
    Filled = "filled"
    Cancelled = "cancelled"

# 클래스 상수: UPPER_SNAKE_CASE
class OrderService:
    MAX_RETRY_ATTEMPTS = 3
    RETRY_DELAY_SECONDS = 5
```

---

## 🔍 검색 예시

### 특정 패턴의 함수 찾기

```bash
# 모든 validation 함수 찾기
grep -r "def validate_" --include="*.py"

# 모든 데이터 조회 함수 찾기
grep -r "def get_\|def find_\|def list_" --include="*.py"

# 네이밍 규칙 위반 찾기 (fetchUser, retrieveOrder 등)
grep -r "def fetch\|def retrieve\|def load" --include="*.py"
```

---

## 🚨 네이밍 검증 규칙

### 코드 리뷰 시 체크리스트

- [ ] 모든 함수명이 네이밍 사전에 등록된 패턴을 따름
- [ ] Boolean 변수는 `is_`, `has_`, `can_` 접두사 사용
- [ ] 클래스명은 적절한 접미사 사용 (Service, Manager, Repository 등)
- [ ] 유사 기능을 다른 이름으로 구현하지 않음 (@SIMILAR: 태그 사용)
- [ ] 약어 사용 최소화 (cnt → count, usr → user)

---

## 💡 추가 시 프로세스

새로운 네이밍 패턴이 필요한 경우:

1. **팀 논의**: 새 패턴이 정말 필요한지 확인
2. **문서 업데이트**: 이 파일에 패턴 추가
3. **기존 코드 검토**: 유사 패턴이 이미 존재하는지 확인
4. **일관성 검증**: 전체 프로젝트에서 일관되게 사용 가능한지 확인

---

*Last Updated: 2025-10-10*
*Version: 1.0.0*

