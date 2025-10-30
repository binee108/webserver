# 거래 실행 기록 (Trade Execution)

## 1. 개요 (Purpose)

**목적**: 주문 체결 내역을 체결 단위로 상세 기록하여 거래 성과 분석, 수수료 추적, 실현 손익 계산을 지원합니다.

**주요 특징**:
- 체결 단위 기록: 부분 체결 시 각 체결을 개별 레코드로 저장
- 중복 방지: `exchange_trade_id` 기반 중복 체크
- 자동 연계: 체결 발생 시 실시간 성과 업데이트 및 자본 반영 Hook 자동 실행
- 상세 정보: Maker/Taker, 수수료, 실현 손익 등 추적

**Trade vs TradeExecution**:
- **Trade**: 주문 단위 집계 (1 주문 = 1 레코드, 간단한 조회용)
- **TradeExecution**: 체결 단위 상세 (1 주문 = N 레코드, 분석/감사용)

---

## 2. 실행 플로우 (Execution Flow)

### 2.1 단일 주문 체결 (Real-time WebSocket)

```
WebSocket 체결 이벤트
    ↓
OrderFillMonitor.on_order_update()
    ↓
TradingService.process_order_fill()
    ↓
RecordManager.create_trade_execution_record()
    ├─→ 중복 체크 (exchange_order_id)
    ├─→ TradeExecution 생성/업데이트
    ├─→ Hook 1: _trigger_performance_update() - 실시간 성과 재계산
    └─→ Hook 2: _trigger_capital_pnl_reflection() - 실현 손익 자본 반영
```

### 2.2 배치 거래 처리 (Parallel ThreadPoolExecutor)

```
process_batch_trading_signal() 호출
    ↓
1️⃣ 계좌별 배치 주문 준비
    ├─ symbol별 매수/매도 수량 집계
    └─ 거래소 배치 API 포맷 생성
    ↓
2️⃣ ThreadPoolExecutor 병렬 실행 (max_workers = min(10, account_count))
    ├─ 계좌1: _execute_account_batch() [async]
    ├─ 계좌2: _execute_account_batch() [async]
    ├─ ... (모든 계좌 동시 처리)
    └─ 계좌N: _execute_account_batch() [async]
    ↓
3️⃣ as_completed()로 완료되는 대로 처리
    ├─ 각 계좌의 거래 결과 수집
    ├─ TradeExecution 레코드 생성
    └─ Hook 자동 실행 (성과 + 자본 반영)
```

**병렬 처리 특징**:
- **독립적 실행**: 각 계좌는 독립적인 ThreadPoolExecutor 워커에서 실행
- **타임아웃 격리**: 한 계좌의 타임아웃이 다른 계좌에 영향 없음
- **결과 수집**: `as_completed()`로 완료 순서대로 처리 (blocking 최소화)

---

## 3. 데이터 플로우 (Data Flow)

**Input**: 거래소 체결 응답 (`order_result`)
- exchange_trade_id, exchange_order_id
- execution_price, execution_quantity
- commission, is_maker, realized_pnl

**Process**:
1. 중복 체크 (exchange_order_id 기반)
2. TradeExecution 생성/업데이트
3. 성과 업데이트 Hook 실행
4. 자본 반영 Hook 실행 (realized_pnl이 있는 경우)

**Output**:
- TradeExecution 레코드
- DailyPerformance 업데이트
- StrategyAccount.allocated_capital 업데이트

**주요 의존성**:
- `order-tracking`: 체결 감지 연계
- `performance-tracking`: 성과 업데이트
- `capital-management`: 실현 손익 자본 반영

---

## 4. 주요 컴포넌트 (Components)

| 파일 | 역할 | 태그 | 핵심 메서드 |
|------|------|------|-------------|
| `trade_record.py` | 독립형 체결 기록 서비스 | `@FEAT:trade-execution @COMP:service @TYPE:core` | `record_execution()`, `get_executions_by_order()`, `get_execution_stats()` |
| `record_manager.py` | TradingService 통합 기록 관리 | `@FEAT:trade-execution @FEAT:order-tracking @COMP:service @TYPE:integration` | `create_trade_execution_record()`, `_trigger_performance_update()`, `_trigger_capital_pnl_reflection()` |
| `core.py` | 배치 거래 병렬 처리 | `@FEAT:trade-execution @COMP:service @TYPE:core` | `process_batch_trading_signal()`, `_execute_account_batch()` |
| `order_fill_monitor.py` | WebSocket 체결 감지 | `@FEAT:order-tracking @FEAT:trade-execution @COMP:service @TYPE:integration` | `on_order_update()` |
| `models.py` (TradeExecution) | 체결 데이터 모델 | `@FEAT:trade-execution @COMP:model @TYPE:core` | N/A |

### TradeRecordService (독립형)

**위치**: `/Users/binee/Desktop/quant/webserver/web_server/app/services/trade_record.py`

**주요 메서드**:
- `record_execution(execution_data)`: 체결 기록 (중복 체크 포함)
- `get_executions_by_order(exchange_order_id)`: 주문별 체결 조회 (부분 체결 추적)
- `get_executions_by_symbol(symbol, ...)`: 심볼별 체결 조회
- `get_execution_stats(strategy_account_id, ...)`: 체결 통계 집계
- `sync_with_trades(strategy_account_id)`: 레거시 Trade 테이블 동기화

### RecordManager (통합형)

**위치**: `/Users/binee/Desktop/quant/webserver/web_server/app/services/trading/record_manager.py`

**핵심 메서드**:
- `create_trade_execution_record(...)`: TradeExecution 생성 + 자동 Hook 실행
  - Hook 1: `_trigger_performance_update()` - 실시간 성과 재계산
  - Hook 2: `_trigger_capital_pnl_reflection()` - 실현 손익 자본 반영

**Hook 동작 방식**:
- **비침습적**: Hook 실패 시에도 체결 기록은 성공 처리
- **조건부 실행**: 자본 반영은 realized_pnl이 있을 때만 실행
- **로깅**: 모든 Hook 동작을 로그에 기록하여 추적 가능

### TradingService - 배치 거래 병렬 처리

**위치**: `/Users/binee/Desktop/quant/webserver/web_server/app/services/trading/core.py`

**핵심 메서드**:
- `process_batch_trading_signal(webhook_data, ...)`: 배치 거래 신호 처리
  - 계좌별 배치 주문 준비
  - ThreadPoolExecutor 기반 병렬 실행
  - as_completed()로 결과 수집

- `_execute_account_batch(...)`: 단일 계좌 배치 실행
  - 거래소 배치 API 호출
  - TradeExecution 레코드 생성
  - Hook 자동 실행

**병렬 처리 메커니즘**:
```python
max_workers = min(10, len(account_data))  # 계좌 수에 따라 워커 수 동적 결정
with ThreadPoolExecutor(max_workers=max_workers) as executor:
    futures = {
        executor.submit(execute_account_batch_in_context, ...): account_id
        for account_id, account_data in account_data.items()
    }

    # 각 계좌의 결과를 완료 순서대로 처리
    for future in as_completed(futures):
        account_id = futures[future]
        try:
            result = future.result()  # 각 계좌의 거래 결과
        except Exception as exc:
            logger.error(f"계좌 {account_id} 배치 처리 실패: {exc}")
```

**특징**:
- **워커 제한**: 동시 최대 10개 계좌 처리 (DB 부하 제어)
- **개별 타임아웃**: 각 계좌는 독립적인 타임아웃 처리
- **결과 격리**: 한 계좌의 실패가 다른 계좌에 영향 없음

---

## 5. 데이터 모델 (TradeExecution)

```python
# @FEAT:trade-execution @COMP:model @TYPE:core
class TradeExecution(db.Model):
    __tablename__ = 'trade_executions'

    # 핵심 필드
    exchange_trade_id       # 🔑 거래소 거래 ID (중복 방지 키)
    exchange_order_id       # 거래소 주문 ID (부분 체결 추적)
    execution_price         # 실제 체결가
    execution_quantity      # 실제 체결량
    commission              # 수수료
    commission_asset        # 수수료 자산 (USDT, BNB 등)
    is_maker                # Maker(True) / Taker(False)
    realized_pnl            # 실현 손익 (선물)
    market_type             # SPOT, FUTURES

    # 관계
    trade_id                # trades 테이블 연결 (optional)
    strategy_account_id     # 전략 계좌
```

**중요 필드**:
- **exchange_trade_id**: Binance `tradeId` 등, 체결별 고유 ID (중복 방지)
- **is_maker**: Maker(낮은 수수료) vs Taker(높은 수수료)
- **realized_pnl**: 포지션 청산 시 실현된 손익 (선물)

**인덱스**:
- `idx_trade_exec_symbol`: 심볼별 조회
- `idx_trade_exec_time`: 시간별 조회
- `idx_trade_exec_strategy`: 전략별 조회
- `idx_trade_exec_order_id`: 주문별 조회

---

## 6. 설계 결정 히스토리 (Design Decisions)

### 왜 Trade와 TradeExecution 두 개의 테이블?

**문제**: 기존 `Trade` 테이블은 주문 단위 집계만 제공, 부분 체결 추적 불가

**결정**: 체결 단위 상세 기록을 위한 `TradeExecution` 테이블 별도 생성

**근거**:
- 부분 체결 시 각 체결의 가격/수량이 다를 수 있음
- Maker/Taker 여부에 따라 수수료 차등 (정확한 수수료 추적 필요)
- 거래소 API 응답 구조와 일치 (각 체결은 고유 trade_id 보유)

**Trade 테이블 유지 이유**: 레거시 코드 호환성, 간단한 조회용

### 왜 자동 Hook 시스템?

**문제**: 체결 발생 시 성과 업데이트 및 자본 반영을 수동으로 호출하면 누락 위험

**결정**: `RecordManager`에 자동 Hook 시스템 구현

**근거**:
- 일관성: 모든 체결에 대해 자동으로 성과/자본 업데이트
- 비침습적: Hook 실패 시에도 체결 기록은 성공 (독립적 트랜잭션)
- 유지보수: 호출 코드에서 성과/자본 업데이트 로직 제거 가능

---

## 7. 주요 사용 사례 (Use Cases)

### 사례 1: 부분 체결 추적

```python
# 주문 O123456이 3번 체결됨
executions = trade_record_service.get_executions_by_order('O123456')

# 총 체결량 및 평균 가격 계산
total_qty = sum(e.execution_quantity for e in executions)
avg_price = sum(e.execution_price * e.execution_quantity for e in executions) / total_qty
```

### 사례 2: 체결 통계 조회

```python
stats = trade_record_service.get_execution_stats(
    strategy_account_id=1,
    start_date=datetime(2025, 1, 1)
)
# 결과: 총 체결 건수, 거래량, 수수료, 평균 체결가, 심볼별 분포 등
```

### 사례 3: 실시간 체결 기록 (RecordManager 사용)

```python
# TradingService.process_order_fill() 내부
execution_result = self.record_manager.create_trade_execution_record(
    strategy_account=strategy_account,
    order_result=order_result,
    symbol=symbol,
    side=side,
    order_type='LIMIT',
    realized_pnl=Decimal('100.5')
)
# 자동 실행: 성과 업데이트 + 실현 손익 자본 반영
```

### 사례 4: 배치 거래 병렬 처리

```python
# 웹훅 핸들러 또는 자동 거래 신호
webhook_data = {
    'signal_type': 'batch',
    'trading_signals': {
        'BTCUSDT': {'buy_weight': 0.3, 'sell_weight': 0.0},
        'ETHUSDT': {'buy_weight': 0.2, 'sell_weight': 0.1},
        'BNBUSDT': {'buy_weight': 0.0, 'sell_weight': 0.2}
    },
    'market_type': 'SPOT'
}

# ThreadPoolExecutor 기반 병렬 처리 (계좌 단위)
result = trading_service.process_batch_trading_signal(webhook_data)

# 결과 예시:
# {
#   'account_1': {'status': 'success', 'orders': 3, 'executions': 3},
#   'account_2': {'status': 'success', 'orders': 3, 'executions': 2},
#   'account_3': {'status': 'error', 'reason': 'timeout'}
# }
```

---

## 8. 검색 패턴 (Grep Patterns)

```bash
# 모든 trade-execution 코드
grep -r "@FEAT:trade-execution" --include="*.py"

# 핵심 로직만
grep -r "@FEAT:trade-execution" --include="*.py" | grep "@TYPE:core"

# 통합 코드 (다른 기능과 연관)
grep -r "@FEAT:trade-execution" --include="*.py" | grep "@TYPE:integration"

# 서비스 레이어
grep -r "@FEAT:trade-execution" --include="*.py" | grep "@COMP:service"

# trade-execution에 의존하는 코드
grep -r "@DEPS:trade-execution" --include="*.py"

# order-tracking과 통합 지점
grep -r "@FEAT:trade-execution" --include="*.py" | grep "@FEAT:order-tracking"
```

---

## 9. 유지보수 가이드

### 주의사항

1. **exchange_trade_id 필수**: 중복 방지를 위해 반드시 거래소 trade_id 전달
2. **Hook 비침습성**: `_trigger_*` Hook 메서드는 try-except로 래핑하여 실패 시에도 체결 기록 성공 유지
3. **인덱스 관리**: 대량 데이터 조회 시 인덱스 확인 (symbol, execution_time, strategy_account_id)
4. **트랜잭션 격리**: 동시 체결 발생 시 중복 방지를 위해 READ COMMITTED 이상 격리 수준 사용

### 확장 포인트

1. **통계 추가**: `get_execution_stats()`에 새로운 집계 지표 추가 가능
2. **Hook 확장**: `RecordManager`에 새로운 Hook 메서드 추가 (예: 알림, 로깅)
3. **거래소 확장**: `exchange_trade_id` 추출 로직을 거래소별로 분기 처리

### 트러블슈팅

**문제**: 체결 기록 중복
- **원인**: exchange_trade_id 미전달 또는 WebSocket/REST 동시 실행
- **해결**: exchange_trade_id 필수 전달, 중복 체크 로직 확인

**문제**: 성과 업데이트 미실행
- **원인**: `_trigger_performance_update()` Hook 실패
- **해결**: 로그 확인 (`grep "실시간 성과 업데이트" logs/app.log`)

**문제**: 실현 손익 자본 미반영
- **원인**: `_trigger_capital_pnl_reflection()` Hook 실패
- **해결**: 로그 확인 (`grep "실현 손익 자본 반영" logs/app.log`)

**문제**: 통계 조회 성능 저하
- **원인**: 인덱스 누락 또는 대량 데이터
- **해결**: 인덱스 생성, 조회 기간 제한 (최근 3개월 등)

---

## 10. 관련 문서

- [아키텍처 개요](../ARCHITECTURE.md)
- [주문 상태 추적](./order-tracking.md)
- [성과 추적 시스템](./performance-tracking.md)
- [자본 할당 관리](./capital-management.md)

---

*Last Updated: 2025-10-30*
*Version: 2.1.0 (Parallel Processing Added)*
