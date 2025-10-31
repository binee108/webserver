# 데이터베이스 모델 문서

FastAPI Trading Bot의 데이터베이스 모델 상세 문서입니다.

---

## CancelQueue (취소 대기열)

**파일**: `app/models/cancel_queue.py`

**목적**: PENDING 상태 주문의 취소 요청을 추적하여 고아 주문을 방지합니다.

### 테이블 구조

```python
class CancelQueue(Base):
    __tablename__ = "cancel_queue"
```

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|------|------|------|--------|------|
| `id` | Integer | ✓ | - | Primary Key |
| `order_id` | Integer | ✓ | - | 취소할 주문 ID (FK: open_orders.id) |
| `strategy_id` | Integer | - | NULL | 전략 ID (FK: strategies.id) |
| `account_id` | Integer | - | NULL | 계정 ID (FK: accounts.id) |
| `requested_at` | DateTime | ✓ | utcnow | 취소 요청 시각 (UTC) |
| `retry_count` | Integer | ✓ | 0 | 재시도 횟수 |
| `max_retries` | Integer | ✓ | 5 | 최대 재시도 횟수 |
| `next_retry_at` | DateTime | - | NULL | 다음 재시도 시각 (UTC) |
| `status` | String(20) | ✓ | PENDING | 취소 상태 |
| `error_message` | Text | - | NULL | 오류 메시지 |
| `created_at` | DateTime | ✓ | utcnow | 생성 시각 (UTC) |
| `updated_at` | DateTime | ✓ | utcnow | 수정 시각 (UTC) |

### 상태 (Status)

- **PENDING**: 취소 대기 중
- **PROCESSING**: 취소 처리 중
- **SUCCESS**: 취소 성공
- **FAILED**: 취소 실패 (재시도 소진)

### 인덱스

- `ix_cancel_queue_status`: status 필드
- `ix_cancel_queue_next_retry_at`: next_retry_at 필드

### 주요 메서드

#### `can_retry() -> bool`
재시도 가능 여부 확인
```python
cancel_item = CancelQueue(order_id=123, retry_count=3, max_retries=5)
if cancel_item.can_retry():
    # 재시도 가능
    pass
```

#### `increment_retry() -> None`
재시도 횟수 증가 및 다음 재시도 시각 계산 (Exponential Backoff)
```python
cancel_item.increment_retry()
# retry_count: 0 -> 1
# next_retry_at: now + 2^1 = 2초 후
```

#### `mark_success() -> None`
취소 성공으로 상태 변경
```python
cancel_item.mark_success()
# status: PROCESSING -> SUCCESS
```

#### `mark_failed(error_message: str) -> None`
취소 실패로 상태 변경
```python
cancel_item.mark_failed("Order already filled")
# status: PROCESSING -> FAILED
# error_message: "Order already filled"
```

### 사용 예시

```python
from app.models.cancel_queue import CancelQueue
from app.db.session import AsyncSessionLocal

async def add_to_cancel_queue(order_id: int, strategy_id: int):
    """주문을 취소 대기열에 추가"""
    async with AsyncSessionLocal() as session:
        cancel_item = CancelQueue(
            order_id=order_id,
            strategy_id=strategy_id,
            requested_at=datetime.utcnow(),
        )
        session.add(cancel_item)
        await session.commit()
        return cancel_item
```

---

## StrategyOrderLog (전략별 주문 로그)

**파일**: `app/models/strategy_order_log.py`

**목적**: 전략 단위로 주문 실행 결과를 추적하여 무손실 보장을 위한 감사 로그를 제공합니다.

### 테이블 구조

```python
class StrategyOrderLog(Base):
    __tablename__ = "strategy_order_logs"
```

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|------|------|------|--------|------|
| `id` | Integer | ✓ | - | Primary Key |
| `strategy_id` | Integer | ✓ | - | 전략 ID (FK: strategies.id) |
| `webhook_log_id` | Integer | - | NULL | 웹훅 로그 ID (FK: webhook_logs.id) |
| `symbol` | String(50) | ✓ | - | 심볼 (예: BTC/USDT) |
| `side` | String(10) | ✓ | - | 매매 방향 (buy, sell) |
| `order_type` | String(20) | ✓ | - | 주문 타입 (MARKET, LIMIT, STOP_LIMIT) |
| `quantity` | Numeric(20,8) | ✓ | - | 수량 |
| `price` | Numeric(20,8) | - | NULL | 지정가 (LIMIT 주문) |
| `stop_price` | Numeric(20,8) | - | NULL | 스탑 가격 (STOP 주문) |
| `execution_results` | JSON | ✓ | {} | 계정별 실행 결과 |
| `total_accounts` | Integer | ✓ | - | 전체 계정 수 |
| `successful_accounts` | Integer | ✓ | 0 | 성공한 계정 수 |
| `failed_accounts` | Integer | ✓ | 0 | 실패한 계정 수 |
| `status` | String(20) | ✓ | PROCESSING | 실행 상태 |
| `created_at` | DateTime | ✓ | utcnow | 생성 시각 (UTC) |
| `completed_at` | DateTime | - | NULL | 완료 시각 (UTC) |

### execution_results JSON 형식

```json
{
  "account_1": {
    "success": true,
    "order_id": 123,
    "exchange_order_id": "abc123",
    "account_name": "Binance Main",
    "exchange": "binance"
  },
  "account_2": {
    "success": false,
    "error": "Insufficient balance",
    "account_name": "Bybit Sub",
    "exchange": "bybit"
  }
}
```

### 상태 (Status)

- **PROCESSING**: 실행 중
- **COMPLETED**: 모든 계정 성공
- **PARTIAL_FAILURE**: 일부 계정 실패

### 인덱스

- `ix_strategy_order_logs_strategy_id`: strategy_id 필드
- `ix_strategy_order_logs_status`: status 필드

### 주요 프로퍼티

#### `is_processing -> bool`
처리 중인지 확인

#### `is_completed -> bool`
완료되었는지 확인 (성공 또는 부분 실패)

#### `is_all_success -> bool`
모든 계정에서 성공했는지 확인

#### `is_partial_failure -> bool`
일부 계정이 실패했는지 확인

#### `is_all_failed -> bool`
모든 계정이 실패했는지 확인

#### `success_rate -> float`
성공률 계산 (0.0 ~ 1.0)
```python
log = StrategyOrderLog(
    total_accounts=10,
    successful_accounts=8,
    failed_accounts=2
)
print(log.success_rate)  # 0.8
```

### 주요 메서드

#### `update_statistics(execution_results: Dict[str, Any]) -> None`
실행 결과를 기반으로 통계 업데이트
```python
results = {
    "account_1": {"success": True, "order_id": 123},
    "account_2": {"success": True, "order_id": 124},
    "account_3": {"success": False, "error": "Insufficient balance"}
}
log.update_statistics(results)
# successful_accounts: 2
# failed_accounts: 1
# status: PARTIAL_FAILURE
```

#### `get_failed_accounts() -> list[Dict[str, Any]]`
실패한 계정 목록 반환
```python
failed = log.get_failed_accounts()
# [{"account_key": "account_3", "success": False, "error": "Insufficient balance"}]
```

#### `get_successful_accounts() -> list[Dict[str, Any]]`
성공한 계정 목록 반환
```python
successful = log.get_successful_accounts()
# [
#   {"account_key": "account_1", "success": True, "order_id": 123},
#   {"account_key": "account_2", "success": True, "order_id": 124}
# ]
```

### 사용 예시

```python
from app.models.strategy_order_log import StrategyOrderLog
from app.db.session import AsyncSessionLocal
from decimal import Decimal

async def create_strategy_order_log(
    strategy_id: int,
    symbol: str,
    side: str,
    order_type: str,
    quantity: Decimal,
    total_accounts: int
):
    """전략별 주문 로그 생성"""
    async with AsyncSessionLocal() as session:
        log = StrategyOrderLog(
            strategy_id=strategy_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            execution_results={},
            total_accounts=total_accounts,
        )
        session.add(log)
        await session.commit()
        await session.refresh(log)
        return log
```

---

## 관계 (Relationships)

### CancelQueue

- `open_orders`: 취소할 주문 (1:1)
- `strategies`: 연관 전략 (N:1)
- `accounts`: 연관 계정 (N:1)

### StrategyOrderLog

- `strategies`: 연관 전략 (N:1)
- `webhook_logs`: 연관 웹훅 로그 (N:1, optional)

---

## 마이그레이션

### 테이블 생성

```bash
# 마이그레이션 파일 확인
alembic current

# 마이그레이션 적용
alembic upgrade head

# 테이블 확인
psql -d trading_system -c "\d cancel_queue"
psql -d trading_system -c "\d strategy_order_logs"
```

### 테이블 삭제 (주의)

```bash
# 마이그레이션 되돌리기
alembic downgrade -1
```

---

**최종 업데이트**: 2025-10-31
**Phase**: Phase 1 - 비동기 인프라 구축
