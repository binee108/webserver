# Immediate Order Execution

**Feature Tag**: `@FEAT:immediate-order-execution`
**Status**: ✅ Active (Phase 1-7 Complete)
**Version**: 1.0.0

## 개요

웹훅으로 수신한 주문을 큐에 적재하지 않고 **즉시 거래소 API로 실행**하는 시스템입니다. 실패한 주문은 `FailedOrder` 모델에 저장되며, 사용자가 UI에서 재시도하거나 제거할 수 있습니다.

**핵심 변경사항**:
- 기존 `PendingOrder` 큐 시스템 제거
- 주문 수신 즉시 거래소 실행 (대기 시간 0초)
- 실패 주문 관리 UI (재시도/제거 기능)

---

## 아키텍처

### Phase별 구현 내역

| Phase | 구성 요소 | 설명 | Lines | 상태 |
|-------|----------|------|-------|------|
| **Phase 1** | FailedOrder 모델 | DB 스키마 정의 | models.py:833-866 | ✅ |
| **Phase 2** | FailedOrderManager | 비즈니스 로직 | failed_order_manager.py:1-200 | ✅ |
| **Phase 3** | retry_failed_order() | 재시도 로직 | failed_order_manager.py:120-165 | ✅ |
| **Phase 4** | Webhook 즉시 실행 | 큐 제거, 즉시 호출 | webhook.py:150-200 | ✅ |
| **Phase 5** | 큐 인프라 제거 | 불필요한 코드 정리 | pending_order.py | ✅ |
| **Phase 6** | API 엔드포인트 | REST API 3개 | failed_orders.py:1-263 | ✅ |
| **Phase 7** | Frontend UI | 관리 화면 | failed_orders.js/css, positions.html | ✅ |

### 데이터 흐름

```
Webhook Request
    ↓
Token Validation
    ↓
Strategy Lookup
    ↓
Order Execution (Immediate) ← 즉시 실행
    ├─ Success → Return 200 OK
    └─ Failure → Save to FailedOrder
                     ↓
                 User Views in UI (/positions)
                     ↓
                 Retry (POST /api/failed-orders/{id}/retry)
                   or
                 Remove (DELETE /api/failed-orders/{id})
```

---

## Phase 1-3: Backend Core

### FailedOrder 모델

**파일**: `web_server/app/models.py` (Lines 833-866)

```python
class FailedOrder(db.Model):
    __tablename__ = 'failed_orders'

    # 주문 파라미터
    symbol = db.Column(db.String(50), nullable=False)
    side = db.Column(db.String(10), nullable=False)  # BUY/SELL
    order_type = db.Column(db.String(20), nullable=False)  # LIMIT/MARKET
    quantity = db.Column(db.Numeric(20, 8), nullable=False)
    price = db.Column(db.Numeric(20, 8))  # LIMIT only
    stop_price = db.Column(db.Numeric(20, 8))  # STOP orders

    # 실패 정보
    reason = db.Column(db.Text, nullable=False)  # 실패 이유
    exchange_error = db.Column(db.Text)  # 거래소 에러 메시지
    retry_count = db.Column(db.Integer, default=0)

    # 상태
    status = db.Column(db.String(20), default='pending_retry')
```

**태그**: `@FEAT:immediate-order-execution @COMP:model @TYPE:core`

### FailedOrderManager

**파일**: `web_server/app/services/trading/failed_order_manager.py`

**핵심 메서드**:
```python
def save_failed_order(order_data, reason, exchange_error=None):
    """주문 실패 시 FailedOrder 테이블에 저장"""

def get_failed_orders(strategy_account_id=None, symbol=None, status='pending_retry'):
    """실패 주문 목록 조회 (필터링 지원)"""

def retry_failed_order(failed_order_id):
    """재시도 로직 (최대 5회 제한)"""

def remove_failed_order(failed_order_id):
    """실패 주문 제거 (soft delete)"""
```

**태그**: `@FEAT:immediate-order-execution @COMP:service @TYPE:core`

---

## Phase 4-5: Webhook Integration

### Webhook 즉시 실행

**파일**: `web_server/app/routes/webhook.py` (Lines 150-200)

**변경 내용**:
```python
# 기존 (Queue 방식)
pending_order = create_pending_order(...)
db.session.add(pending_order)
db.session.commit()

# 신규 (Immediate 방식)
try:
    exchange_order = place_order_directly(...)  # 즉시 실행
    return jsonify({'success': True, 'order_id': exchange_order.id})
except OrderExecutionError as e:
    failed_order_manager.save_failed_order(order_data, str(e))
    return jsonify({'success': False, 'error': str(e)}), 400
```

**태그**: `@FEAT:immediate-order-execution @COMP:route @TYPE:core @DEPS:failed-order-manager`

### 큐 인프라 제거

**파일**: `web_server/app/models.py` (PendingOrder 제거)

**제거된 컴포넌트**:
- `PendingOrder` 모델
- `QueueManager` 서비스
- 큐 재정렬 스케줄러 (APScheduler 작업)

---

## Phase 6: API Endpoints

**파일**: `web_server/app/routes/failed_orders.py` (263 lines)

### 1. GET `/api/failed-orders`

**목적**: 실패 주문 목록 조회

**Query Parameters**:
- `strategy_account_id` (int, optional): 전략 계정 필터
- `symbol` (str, optional): 심볼 필터 (예: BTC/USDT)

**Response (200 OK)**:
```json
{
  "success": true,
  "orders": [
    {
      "id": 1,
      "symbol": "BTC/USDT",
      "side": "BUY",
      "order_type": "LIMIT",
      "quantity": "0.1",
      "price": "50000",
      "reason": "잔고 부족",
      "exchange_error": "Insufficient balance",
      "retry_count": 2,
      "status": "pending_retry",
      "created_at": "2025-10-29T10:00:00"
    }
  ]
}
```

**Security**:
- `@login_required` 데코레이터
- 권한 체인 검증: FailedOrder → StrategyAccount → Strategy → User

**태그**: `@FEAT:immediate-order-execution @COMP:route @TYPE:core`

### 2. POST `/api/failed-orders/<id>/retry`

**목적**: 실패 주문 재시도

**Request**: No body required

**Response (200 OK)**:
```json
{
  "success": true,
  "order_id": "12345678"  // 거래소 주문 ID
}
```

**Response (400 Bad Request)**:
```json
{
  "success": false,
  "error": "최대 재시도 횟수(5회)를 초과했습니다"
}
```

**Security**:
- CSRF 토큰 검증 (Flask-WTF CSRFProtect)
- 권한 체인 검증

**태그**: `@FEAT:immediate-order-execution @COMP:route @TYPE:core @DEPS:failed-order-manager`

### 3. DELETE `/api/failed-orders/<id>`

**목적**: 실패 주문 제거 (soft delete)

**Request**: No body required

**Response (200 OK)**:
```json
{
  "success": true,
  "message": "주문이 제거되었습니다"
}
```

**Security**:
- CSRF 토큰 검증 (자동)
- 권한 체인 검증
- Confirm 대화상자 (프론트엔드)

**태그**: `@FEAT:immediate-order-execution @COMP:route @TYPE:core @DEPS:failed-order-manager`

---

## Phase 7: Frontend UI

### JavaScript 모듈

**파일**: `web_server/app/static/js/failed_orders.js` (416 lines)

**핵심 함수**:
```javascript
// 1. 목록 로드
async function loadFailedOrders(filters = {}) {
    // GET /api/failed-orders 호출
    // renderFailedOrders() 호출
}

// 2. 테이블 렌더링
function renderFailedOrders(orders) {
    // innerHTML로 테이블 생성
    // retry_count >= 5 → 버튼 비활성화
}

// 3. 재시도 버튼
async function retryFailedOrder(failedOrderId) {
    if (!confirm("이 주문을 재시도하시겠습니까?")) return;
    // POST /api/failed-orders/{id}/retry
    // Toast 알림
    // loadFailedOrders() 재호출
}

// 4. 제거 버튼
async function removeFailedOrder(failedOrderId) {
    if (!confirm("이 주문을 영구 삭제하시겠습니까?")) return;
    // DELETE /api/failed-orders/{id}
    // Toast 알림
    // loadFailedOrders() 재호출
}

// 5. 필터 적용
function filterFailedOrders() {
    const strategyAccountId = document.getElementById('filter-strategy').value;
    const symbol = document.getElementById('filter-symbol').value;
    loadFailedOrders({ strategy_account_id: strategyAccountId, symbol });
}
```

**보안 기능**:
- `escapeHtml()`: XSS 방지
- `getCsrfToken()`: CSRF 토큰 자동 포함
- Confirm 대화상자: 실수 방지

**태그**: `@FEAT:immediate-order-execution @COMP:ui @TYPE:core @DEPS:toast.js`

### CSS 스타일

**파일**: `web_server/app/static/css/failed_orders.css` (342 lines)

**주요 컴포넌트**:
- `.failed-orders-section`: 카드 컨테이너
- `.failed-orders-table`: 테이블 스타일 (hover 효과)
- `.badge-buy`, `.badge-sell`: 매수/매도 배지 (초록/빨강)
- `.btn-retry`, `.btn-remove`: 액션 버튼 (초록/빨강)
- `.retry-count-badge`: 재시도 횟수 배지 (오렌지, "2/5" 형태)

**반응형 디자인**:
- 768px (태블릿): 일부 컬럼 숨김
- 480px (모바일): 가격, 시각 컬럼 숨김

**태그**: `@FEAT:immediate-order-execution @COMP:style @TYPE:ui`

### HTML 템플릿

**파일**: `web_server/app/templates/positions.html` (Lines 295-348)

**구조**:
```html
<section class="failed-orders-section">
    <h2>실패된 주문</h2>

    <!-- 필터 -->
    <div class="filters">
        <select id="filter-strategy">...</select>
        <input id="filter-symbol" placeholder="예: BTC/USDT">
        <button onclick="filterFailedOrders()">검색</button>
    </div>

    <!-- 테이블 -->
    <table class="failed-orders-table">
        <thead>
            <tr>
                <th>심볼</th>
                <th>방향</th>
                <th>타입</th>
                <th>수량</th>
                <th>가격</th>
                <th>실패 이유</th>
                <th>거래소 에러</th>
                <th>생성 시각</th>
                <th>액션</th>
            </tr>
        </thead>
        <tbody id="failed-orders-tbody">
            <!-- JavaScript로 동적 생성 -->
        </tbody>
    </table>
</section>

<!-- 스크립트 로드 (순서 중요) -->
<script src="/static/js/toast.js"></script>
<script src="/static/js/failed_orders.js"></script>
<link rel="stylesheet" href="/static/css/failed_orders.css">
```

---

## 사용 방법

### 1. 웹훅으로 주문 전송

```bash
curl -X POST http://localhost:5000/api/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "token": "your-token",
    "symbol": "BTC/USDT",
    "side": "BUY",
    "order_type": "LIMIT",
    "quantity": 0.1,
    "price": 50000
  }'
```

**성공 시**:
```json
{
  "success": true,
  "order_id": "12345678"
}
```

**실패 시** (예: 잔고 부족):
```json
{
  "success": false,
  "error": "Insufficient balance"
}
```
→ `FailedOrder` 테이블에 자동 저장

### 2. 실패 주문 확인

**UI 접근**: `http://localhost:5000/positions` → "실패된 주문" 섹션

**필터 기능**:
- 전략 계정 선택
- 심볼 입력 (예: BTC/USDT)
- "검색" 버튼 클릭

### 3. 재시도 또는 제거

- **재시도 버튼**: 주문을 다시 실행 (최대 5회 제한)
- **제거 버튼**: 주문을 영구 삭제 (확인 대화상자)

---

## 트러블슈팅

### 문제 1: API 500 Error (Database Schema Mismatch)

**증상**:
```
GET /api/failed-orders → 500 Internal Server Error
ERROR: column failed_orders.quantity does not exist
```

**원인**: 데이터베이스 스키마가 Phase 1-3 모델과 동기화되지 않음

**해결책**:
```bash
# Option A: Development 환경 (자동 동기화)
python run.py restart

# Option B: Production 환경 (마이그레이션)
flask db migrate -m "Add FailedOrder schema"
flask db upgrade

# Option C: Manual SQL
docker exec -i webserver_app psql -U trader -d trading_system << 'EOF'
ALTER TABLE failed_orders ADD COLUMN quantity NUMERIC(20, 8) NOT NULL DEFAULT 0;
ALTER TABLE failed_orders ADD COLUMN reason TEXT NOT NULL DEFAULT '알 수 없는 오류';
ALTER TABLE failed_orders ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'pending_retry';
EOF
```

### 문제 2: 재시도 버튼 클릭 시 "최대 재시도 횟수 초과" 에러

**증상**: Toast 알림: "최대 재시도 횟수(5회)를 초과했습니다"

**원인**: `retry_count >= 5`인 주문

**해결책**:
1. **UI 확인**: 재시도 버튼이 비활성화되어야 함
2. **데이터베이스 확인**:
   ```sql
   SELECT id, symbol, retry_count FROM failed_orders WHERE retry_count >= 5;
   ```
3. **수동 재설정** (필요 시):
   ```sql
   UPDATE failed_orders SET retry_count = 0 WHERE id = {order_id};
   ```

### 문제 3: CSRF Token 에러 (403 Forbidden)

**증상**:
```
POST /api/failed-orders/1/retry → 403 Forbidden
"The CSRF token is missing"
```

**원인**: `<meta name="csrf-token">` 태그 누락

**해결책**:
```html
<!-- base.html 또는 positions.html의 <head> 섹션에 추가 -->
<meta name="csrf-token" content="{{ csrf_token() }}">
```

---

## 알려진 제한사항

1. **재시도 제한**: 최대 5회까지만 재시도 가능
2. **필터링**: 현재 전략 계정과 심볼만 지원 (날짜 범위 필터 미지원)
3. **배치 작업**: 여러 주문 동시 재시도/제거 미지원
4. **실시간 업데이트**: SSE 미통합 (수동 새로고침 필요)

---

## 향후 계획

### Phase 8 (예정): Advanced Features
- [ ] 배치 작업 (다중 선택 재시도/제거)
- [ ] SSE 통합 (실시간 업데이트)
- [ ] 날짜 범위 필터
- [ ] CSV 내보내기
- [ ] 재시도 스케줄링 (특정 시간에 재시도)

### Phase 9 (예정): Analytics
- [ ] 실패 주문 통계 (심볼별, 이유별)
- [ ] 성공률 대시보드
- [ ] 알림 설정 (실패 주문 발생 시 텔레그램)

---

## 관련 문서

- [Webhook Order Processing](webhook-order-processing.md) - 웹훅 수신 및 토큰 검증
- [Order Queue System](order-queue-system.md) - 구 큐 시스템 (Phase 5에서 제거됨)
- [Toast UI](toast-ui.md) - Toast 알림 시스템

---

## 검색 패턴

**코드 검색**:
```bash
# 모든 immediate-order-execution 코드 찾기
grep -r "@FEAT:immediate-order-execution" --include="*.py" --include="*.js" --include="*.css"

# Phase별 코드 찾기
grep -r "@FEAT:immediate-order-execution" --include="*.py" | grep "@TYPE:core"  # 핵심 로직
grep -r "@FEAT:immediate-order-execution" --include="*.js"  # 프론트엔드

# 의존성 확인
grep -r "@DEPS:failed-order-manager" --include="*.py"
```

---

**Last Updated**: 2025-10-30
**Maintainer**: Phase 1-7 Development Team
**Status**: ✅ Production Ready (Frontend UI Complete)
