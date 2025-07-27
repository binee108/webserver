# 포지션 & 열린 주문 관리 API 문서

포지션 페이지에서 열린 주문을 확인하고 관리할 수 있는 API 엔드포인트들을 설명합니다.

## 📋 API 엔드포인트 목록

### 1. 포지션 관리

#### 1.1 포지션 청산
```http
POST /api/positions/{position_id}/close
```

**설명**: 특정 포지션을 시장가로 청산합니다.

**권한**: 로그인 필요, 포지션 소유자만 가능

**응답 예시**:
```json
{
    "success": true,
    "message": "포지션이 성공적으로 청산되었습니다.",
    "order_id": "123456789",
    "filled_quantity": 1.5,
    "average_price": 50000.0,
    "realized_pnl": 150.0,
    "fee": 2.5
}
```

### 2. 열린 주문 조회

#### 2.1 사용자의 모든 열린 주문 조회
```http
GET /api/open-orders
```

**설명**: 현재 사용자의 모든 열린 주문을 조회합니다.

**권한**: 로그인 필요

**응답 예시**:
```json
{
    "success": true,
    "open_orders": [
        {
            "id": 1,
            "exchange_order_id": "987654321",
            "symbol": "BTCUSDT",
            "side": "buy",
            "quantity": 0.1,
            "price": 45000.0,
            "filled_quantity": 0.0,
            "status": "OPEN",
            "market_type": "spot",
            "created_at": "2024-01-01T12:00:00",
            "strategy": {
                "id": 1,
                "name": "BTC 전략",
                "group_name": "btc_strategy",
                "market_type": "spot"
            },
            "account": {
                "id": 1,
                "name": "바이낸스 계좌 1",
                "exchange": "BINANCE"
            },
            "strategy_account_id": 1
        }
    ],
    "total_count": 1
}
```

### 3. 통합 조회

#### 3.1 포지션과 열린 주문 통합 조회
```http
GET /api/positions-with-orders
```

**설명**: 사용자의 모든 포지션과 열린 주문을 심볼별로 그룹화하여 조회합니다.

**권한**: 로그인 필요

**응답 예시**:
```json
{
    "success": true,
    "symbol_data": {
        "BTCUSDT": {
            "positions": [
                {
                    "id": 1,
                    "quantity": 0.5,
                    "entry_price": 48000.0,
                    "last_updated": "2024-01-01T12:00:00",
                    "strategy": {...},
                    "account": {...}
                }
            ],
            "open_orders": [
                {
                    "id": 1,
                    "exchange_order_id": "987654321",
                    "side": "buy",
                    "quantity": 0.1,
                    "price": 45000.0,
                    "filled_quantity": 0.0,
                    "status": "OPEN",
                    "market_type": "spot",
                    "created_at": "2024-01-01T12:00:00",
                    "strategy": {...},
                    "account": {...}
                }
            ],
            "total_position_value": 24000.0,
            "total_order_value": 4500.0
        }
    },
    "summary": {
        "total_positions": 1,
        "total_open_orders": 1,
        "active_symbols": 1,
        "total_position_value": 24000.0,
        "total_order_value": 4500.0
    }
}
```

#### 3.2 특정 심볼의 포지션과 열린 주문 조회
```http
GET /api/symbol/{symbol}/positions-orders
```

**설명**: 특정 심볼에 대한 포지션과 열린 주문을 상세 조회합니다.

**권한**: 로그인 필요

**URL 파라미터**:
- `symbol`: 조회할 심볼 (예: BTCUSDT)

**응답 예시**:
```json
{
    "success": true,
    "symbol": "BTCUSDT",
    "positions": [...],
    "open_orders": [...],
    "summary": {
        "total_positions": 2,
        "total_open_orders": 3,
        "net_position": 0.8,
        "long_position": 1.2,
        "short_position": 0.4,
        "avg_long_price": 48500.0,
        "avg_short_price": 47000.0,
        "pending_buy_orders": 0.5,
        "pending_sell_orders": 0.3
    }
}
```

### 4. 주문 취소

#### 4.1 개별 주문 취소
```http
POST /api/open-orders/{order_id}/cancel
```

**설명**: 특정 열린 주문을 취소합니다.

**권한**: 로그인 필요, 주문 소유자만 가능

**URL 파라미터**:
- `order_id`: 취소할 주문의 거래소 주문 ID

**응답 예시**:
```json
{
    "success": true,
    "message": "주문이 성공적으로 취소되었습니다.",
    "order_id": "987654321",
    "symbol": "BTCUSDT"
}
```

#### 4.2 일괄 주문 취소
```http
POST /api/open-orders/cancel-all
```

**설명**: 조건에 맞는 모든 열린 주문을 일괄 취소합니다.

**권한**: 로그인 필요

**요청 본문** (선택사항):
```json
{
    "account_id": 1,      // 특정 계좌의 주문만 취소
    "symbol": "BTCUSDT",  // 특정 심볼의 주문만 취소
    "strategy_id": 1      // 특정 전략의 주문만 취소
}
```

**응답 예시**:
```json
{
    "success": true,
    "message": "총 5개 주문 중 4개 취소 성공, 1개 실패",
    "cancelled_orders": [
        {
            "order_id": "123456789",
            "symbol": "BTCUSDT",
            "side": "buy",
            "quantity": 0.1,
            "price": 45000.0
        }
    ],
    "failed_orders": [
        {
            "order_id": "987654321",
            "symbol": "ETHUSDT",
            "error": "Order not found"
        }
    ],
    "total_processed": 5,
    "filter_conditions": ["계좌 ID: 1"]
}
```

### 5. 이벤트 스트리밍

#### 5.1 실시간 이벤트 스트림
```http
GET /api/events/stream
```

**설명**: Server-Sent Events(SSE)를 통해 실시간 포지션 및 주문 업데이트를 스트리밍합니다.

**권한**: 로그인 필요

**이벤트 타입**:
- `position_update`: 포지션 업데이트
- `order_update`: 주문 상태 변경
- `trade_executed`: 거래 체결
- `error`: 오류 발생

**응답 형식**: Server-Sent Events
```
event: position_update
data: {"position_id": 1, "symbol": "BTCUSDT", "quantity": 0.5, "unrealized_pnl": 150.0}

event: order_update
data: {"order_id": "123456", "status": "FILLED", "filled_quantity": 0.1}
```

#### 5.2 이벤트 통계
```http
GET /api/events/stats
```

**설명**: 현재 활성 이벤트 스트림 연결 상태를 조회합니다.

**권한**: 로그인 필요

**응답 예시**:
```json
{
    "success": true,
    "stats": {
        "active_connections": 5,
        "total_events_sent": 1250,
        "uptime_seconds": 3600,
        "last_event_time": "2024-01-01T12:30:00"
    }
}
```

### 6. 시스템 관리

#### 6.1 주문 상태 수동 업데이트
```http
POST /api/open-orders/status-update
```

**설명**: 시스템의 모든 열린 주문 상태를 수동으로 업데이트합니다.

**권한**: 로그인 필요

**응답 예시**:
```json
{
    "success": true,
    "message": "주문 상태 업데이트가 완료되었습니다.",
    "processed_orders": 10,
    "filled_orders": 2,
    "cancelled_orders": 1
}
```

## 🎨 프론트엔드 사용 예시

### HTML 템플릿 사용
위에서 생성한 `templates/positions_with_orders.html` 파일을 사용하여 완전한 UI를 구현할 수 있습니다.

### JavaScript API 호출 예시

```javascript
// 포지션과 주문 데이터 로드
async function loadPositionsAndOrders() {
    try {
        const response = await fetch('/api/positions-with-orders');
        const data = await response.json();
        
        if (data.success) {
            // 데이터 렌더링
            renderData(data);
        }
    } catch (error) {
        console.error('Error:', error);
    }
}

// 주문 취소
async function cancelOrder(orderId) {
    try {
        const response = await fetch(`/api/open-orders/${orderId}/cancel`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await response.json();
        
        if (data.success) {
            alert('주문이 취소되었습니다.');
            loadPositionsAndOrders(); // 데이터 재로드
        }
    } catch (error) {
        console.error('Error:', error);
    }
}

// 포지션 청산
async function closePosition(positionId) {
    try {
        const response = await fetch(`/api/positions/${positionId}/close`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await response.json();
        
        if (data.success) {
            alert('포지션이 청산되었습니다.');
            loadPositionsAndOrders(); // 데이터 재로드
        }
    } catch (error) {
        console.error('Error:', error);
    }
}

// 실시간 이벤트 스트림 연결
function connectEventStream() {
    const eventSource = new EventSource('/api/events/stream');
    
    eventSource.addEventListener('position_update', (event) => {
        const data = JSON.parse(event.data);
        updatePositionUI(data);
    });
    
    eventSource.addEventListener('order_update', (event) => {
        const data = JSON.parse(event.data);
        updateOrderUI(data);
    });
    
    eventSource.addEventListener('error', (event) => {
        console.error('Event stream error:', event);
        eventSource.close();
        // 5초 후 재연결
        setTimeout(connectEventStream, 5000);
    });
}
```

## 🔐 권한 및 보안

- 모든 엔드포인트는 로그인이 필요합니다 (`@login_required`)
- 사용자는 자신의 포지션과 주문만 조회/관리할 수 있습니다
- 데이터베이스 쿼리에 사용자 ID 필터가 적용됩니다
- 트랜잭션 관리를 통해 데이터 일관성을 보장합니다

## 🚀 확장 가능성

이 API 구조는 다음과 같은 기능 확장이 가능합니다:

1. **실시간 업데이트**: WebSocket 연동으로 실시간 데이터 업데이트
2. **고급 필터링**: 더 세부적인 조건으로 주문/포지션 필터링
3. **일괄 작업**: 여러 포지션을 한 번에 청산하는 기능
4. **알림 시스템**: 주문 체결이나 포지션 변경 시 알림
5. **차트 통합**: 포지션과 주문을 차트에 오버레이 표시

## 📝 주의사항

- 주문 취소나 포지션 청산은 되돌릴 수 없는 작업입니다
- 시장 상황에 따라 주문 취소가 실패할 수 있습니다
- 대량 일괄 취소 시 일부 주문은 실패할 수 있습니다
- 모든 작업은 로그에 기록되며 감사 추적이 가능합니다 