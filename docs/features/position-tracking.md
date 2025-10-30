# 포지션 관리 (Position Tracking)

**기능 태그**: `@FEAT:position-tracking`
**의존성**: `order-tracking`, `exchange-integration`, `event-sse`, `price-cache`

---

## 1. 개요 (Purpose)

거래 체결 시 포지션을 자동 생성/업데이트하고, 평균 진입가 계산, 실현/미실현 손익(PnL) 추적을 담당하는 시스템입니다.

**핵심 기능**:
- 주문 체결 → 포지션 자동 업데이트
- 가중 평균 방식의 정확한 진입가 계산
- 청산 시 실현 손익 계산 및 Trade 기록
- 백그라운드 작업을 통한 미실현 손익 실시간 갱신
- `qty_per=-100` 감지하여 전체 포지션 시장가 청산
- SSE 이벤트를 통한 프론트엔드 실시간 알림

**포지션 방향**: `quantity > 0` (롱), `quantity < 0` (숏), `quantity = 0` (중립)

---

## 2. 실행 플로우 (Execution Flow)

### 주문 체결 → 포지션 업데이트

```
Order Fill (order_manager.py)
          ↓
position_manager.process_order_fill()
  1. 거래소 주문 조회 (fetch_order)
  2. Trade 테이블 기록 (record_manager)
  3. Position 업데이트 (_update_position)
     - 평균 진입가 계산
     - 실현 손익 계산 (청산 시)
     - 포지션 수량 업데이트
  4. TradeExecution 기록 (상세 체결 정보)
  5. SSE 이벤트 발송 (position_updated)
          ↓
Database Update (StrategyPosition, Trade, TradeExecution)
```

### 백그라운드 미실현 손익 계산 (APScheduler - 10초 주기)

```
APScheduler (10초 간격)
          ↓
position_manager.calculate_unrealized_pnl()
  1. 활성 포지션 조회 (quantity != 0)
  2. exchange_service.get_current_price()로 현재가 조회
  3. 미실현 손익 계산:
     - 롱: (현재가 - 진입가) × 수량
     - 숏: (진입가 - 현재가) × |수량|
  4. ⚠️ 현재는 DB에 저장하지 않음 (계산만 수행)
     향후 StrategyPosition에 unrealized_pnl 필드 추가 시 저장 예정
```

---

## 3. 데이터 플로우 (Data Flow)

**Input**: 체결된 주문 정보 (order_id, symbol, side, quantity, price)
**Process**:
  - 포지션 수량 가감
  - 평균 진입가 재계산 (동일 방향 진입 시)
  - 실현 손익 계산 (반대 방향 청산 시)
**Output**: 업데이트된 포지션 (quantity, entry_price, realized_pnl)

**의존성**:
- `order-tracking`: 체결 감지 및 주문 정보 제공
- `price-cache`: 현재가 조회 (미실현 손익 계산)
- `event-sse`: 프론트엔드 실시간 업데이트
- `exchange-integration`: 거래소 주문 조회 API

---

## 4. 주요 컴포넌트 (Components)

| 파일 | 역할 | 태그 | 핵심 메서드 |
|------|------|------|-------------|
| `position_manager.py` | 포지션 업데이트 핵심 로직 | `@FEAT:position-tracking @COMP:service @TYPE:core` | `process_order_fill()`, `_update_position()`, `calculate_unrealized_pnl()` |
| `models.py` (StrategyPosition) | 포지션 데이터 모델 | `@FEAT:position-tracking @COMP:model @TYPE:core` | `quantity`, `entry_price`, `unrealized_pnl` |
| `positions.py` (routes) | 포지션 조회/청산 API | `@FEAT:position-tracking @COMP:route @TYPE:core` | `close_position()`, `get_positions_with_orders()` |
| `utils.py` | 진입/청산 판단 유틸 | `@FEAT:position-tracking @COMP:util @TYPE:helper` | `calculate_is_entry()` |
| `quantity_calculator.py` | qty_per=-100 감지 | `@FEAT:position-tracking @FEAT:webhook-order @COMP:service @TYPE:core` | `calculate_order_quantity()` |

---

## 5. 핵심 로직 (Core Logic)

### 평균 진입가 계산 알고리즘

```python
# 1. 포지션 없음 (quantity = 0)
if current_qty == 0:
    new_qty = trade_qty  # BUY=양수, SELL=음수
    new_price = price

# 2. 동일 방향 진입 (추가 매수/매도)
elif current_qty * trade_qty > 0:
    new_qty = current_qty + trade_qty
    # 가중 평균 계산
    total_abs = abs(current_qty) + abs(trade_qty)
    new_price = (abs(current_qty) * current_price + abs(trade_qty) * price) / total_abs

# 3. 반대 방향 (청산 또는 반전)
else:
    closing_qty = min(abs(current_qty), abs(trade_qty))

    # 실현 손익 계산
    if current_qty > 0:  # 롱 청산
        realized_pnl = closing_qty * (price - current_price)
    else:  # 숏 청산
        realized_pnl = closing_qty * (current_price - price)

    residual_qty = current_qty + trade_qty

    if residual_qty == 0:  # 완전 청산
        new_qty = 0
        new_price = 0
    elif current_qty * residual_qty > 0:  # 부분 청산
        new_qty = residual_qty
        new_price = current_price  # 평균가 유지
    else:  # 포지션 반전
        new_qty = residual_qty
        new_price = price  # 새 방향 진입가
```

### 진입/청산 판단 로직 (calculate_is_entry)

- 포지션 없음 (qty=0) → 항상 진입
- 롱 보유 (qty>0) + BUY → 진입 (추가 매수)
- 롱 보유 (qty>0) + SELL → 청산
- 숏 보유 (qty<0) + SELL → 진입 (추가 매도)
- 숏 보유 (qty<0) + BUY → 청산

### 포지션 청산 (qty_per=-100)

**감지 로직** (`quantity_calculator.py`):
```python
if qty_per == Decimal('-100'):
    position = StrategyPosition.query.filter_by(
        strategy_account_id=strategy_account.id,
        symbol=symbol
    ).first()

    if not position or position.quantity == 0:
        raise ValueError("청산할 포지션이 없습니다")

    # 롱 청산: SELL, 숏 청산: BUY
    actual_side = 'SELL' if position.quantity > 0 else 'BUY'
    actual_qty = abs(position.quantity)

    return actual_qty, actual_side
```

---

## 6. 손익(PnL) 계산

### 실현 손익 (Realized PnL)
**계산 시점**: 포지션 청산 시 (전체 또는 부분)

```python
# 롱 포지션 청산
realized_pnl = closing_qty * (청산가 - 진입가)

# 숏 포지션 청산
realized_pnl = closing_qty * (진입가 - 청산가)
```

**저장 위치**: `Trade.pnl`, `TradeExecution.realized_pnl`

**계산 로직** (`position_manager.py:_update_position()`):
- 청산 수량(closing_qty) = min(|현재수량|, |거래수량|)
- 포지션 반전 시에도 부분 청산 실현 손익 먼저 계산, 초과분은 새 포지션으로 기록

### 미실현 손익 (Unrealized PnL)
**계산 시점**: 백그라운드 작업 (APScheduler - 10초 주기)
**호출 경로**: `TradingService.calculate_unrealized_pnl()` → `PositionManager.calculate_unrealized_pnl()`

```python
# 롱 포지션
unrealized_pnl = quantity * (현재가 - 진입가)

# 숏 포지션
unrealized_pnl = abs(quantity) * (진입가 - 현재가)
```

**저장 정책**:
- 현재는 DB에 저장하지 않음 (계산만 수행)
- 향후 `StrategyPosition.unrealized_pnl` 필드 추가 시 백그라운드에서 갱신할 예정
- 현재가 조회 실패 시 DEBUG 로그만 기록하고 계속 진행

---

## 7. API 엔드포인트

| 엔드포인트 | 메서드 | 역할 |
|-----------|--------|------|
| `/api/positions/<id>/close` | POST | 포지션 시장가 청산 |
| `/api/positions-with-orders` | GET | 포지션+주문 통합 조회 |
| `/api/symbol/<symbol>/positions-orders` | GET | 심볼별 포지션/주문 조회 |
| `/api/strategies/<id>/positions` | GET | 전략별 포지션 조회 |

---

## 8. 데이터베이스 스키마

### StrategyPosition 테이블
```python
class StrategyPosition(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    strategy_account_id = db.Column(db.Integer, db.ForeignKey('strategy_accounts.id'), nullable=False)
    symbol = db.Column(db.String(20), nullable=False)  # 거래 페어
    quantity = db.Column(db.Float, default=0.0, nullable=False)  # 양수: 롱, 음수: 숏
    entry_price = db.Column(db.Float, default=0.0, nullable=False)  # 평균 진입가
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    # ⚠️ unrealized_pnl 필드는 DB에 저장하지 않음 (백그라운드 작업에서 계산만)

    # 복합 유니크 제약
    __table_args__ = (db.UniqueConstraint('strategy_account_id', 'symbol'),)
```

**핵심 특징**:
- `strategy_account_id + symbol` 조합으로 유니크 제약
- `quantity` 부호로 방향 구분 (양수=롱, 음수=숏)
- `entry_price`는 가중 평균 진입가 (추가 진입 시 재계산)
- **미실현 손익**: DB 필드 없음, 백그라운드 작업에서 계산만 수행 (향후 필드 추가 고려 중)

---

## 9. 설계 결정 히스토리 (Design Decisions)

### 가중 평균 진입가 방식 채택 이유
- 추가 진입 시 정확한 평균 비용 반영 필요
- 부분 청산 시에도 평균가 유지로 일관성 확보
- 표준 회계 원칙 (FIFO 대신 가중 평균) 적용

### 포지션 반전(Reversal) 허용
- 롱 → 숏, 숏 → 롱 자동 전환 지원
- 청산 + 신규 진입을 한 번의 주문으로 처리
- 기존 포지션 청산분 실현 손익 계산 후, 초과분은 새 포지션으로 기록

### qty_per=-100 특수 값 사용
- 웹훅에서 명시적으로 "전체 청산" 의도 표현
- 포지션 수량을 자동 조회하여 정확한 청산 보장
- side 자동 결정 (롱→SELL, 숏→BUY)

---

## 10. 유지보수 가이드

### 주의사항
1. **Decimal 타입 사용 필수**: 금액 계산 시 float 오차 방지
2. **트랜잭션 관리**: 포지션 업데이트는 DB 트랜잭션 내에서 처리 (롤백 가능)
3. **최소 수량 검증**: 거래소 규칙 확인 후 청산 (최소 단위 미달 시 에러)
4. **WebSocket 연결 유지**: 실시간 체결 감지를 위한 거래소 WebSocket 필수

### 확장 포인트
1. **미실현 손익 DB 필드 추가**: `StrategyPosition.unrealized_pnl` 필드 추가 (현재 백그라운드 작업에서 갱신)
2. **수수료 반영**: 실현 손익 계산 시 수수료 차감 로직 추가 가능
3. **포지션 히스토리**: 포지션 변경 이력 추적 테이블 추가 (감사 로깅)

### 트러블슈팅
- **포지션 업데이트 안됨**: WebSocket 연결 상태, `order_fill_monitor` 작업 실행 여부 확인
- **평균가 비정상**: 거래소 `average_price` 필드 누락 시 현재가 Fallback 로직 작동 확인
- **qty_per=-100 실패**: 포지션 존재 여부, symbol 포맷 (BTC/USDT), side 일치 확인
- **미실현 손익 0**: APScheduler 실행 상태, Price Cache 갱신 확인

---

## 11. 검색 명령어 (Grep Examples)

```bash
# 모든 포지션 관련 코드
grep -r "@FEAT:position-tracking" --include="*.py"

# 핵심 로직만
grep -r "@FEAT:position-tracking" --include="*.py" | grep "@TYPE:core"

# PnL 계산 로직
grep -r "@FEAT:position-tracking" --include="*.py" | grep -i "pnl"

# 포지션 청산 관련
grep -r "@FEAT:position-tracking" --include="*.py" | grep -i "close"

# 웹훅 통합 지점
grep -r "@FEAT:webhook-order" --include="*.py" | grep "@FEAT:position-tracking"
```

---

## 12. 관련 문서

- **[웹훅 주문 처리 가이드](./webhook-order-processing.md)**: 웹훅 → 주문 → 포지션 전체 플로우
- **[주문 큐 시스템](./order-queue-system.md)**: 주문 관리 및 재정렬
- **[백그라운드 스케줄러](./background-scheduler.md)**: 미실현 손익 계산 작업
- **[거래소 통합](./exchange-integration.md)**: 거래소 API 호출 및 에러 처리

---

*Last Updated: 2025-10-30*
*Lines: ~310 (더 정확한 실시간 주기 및 호출 경로 추가)*
*Version: 2.1.0*
