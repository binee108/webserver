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

| Phase | 구성 요소 | 설명 | 파일 | 상태 |
|-------|----------|------|------|------|
| **Phase 1** | FailedOrder 모델 | DB 스키마 정의 (market_type 추가) | models.py:833-868 | ✅ |
| **Phase 2** | FailedOrderManager | 비즈니스 로직, 캐시, API 키 마스킹 | failed_order_manager.py | ✅ |
| **Phase 3** | retry_failed_order() | 재시도 로직 + 배치주문 API 통합 | failed_order_manager.py | ✅ |
| **Phase 4** | Webhook 즉시 실행 | 큐 제거, 즉시 호출, 타임아웃 처리 | webhook.py | ✅ |
| **Phase 5** | 큐 인프라 제거 | PendingOrder/QueueManager 완전 제거 | pending_order.py | ✅ |
| **Phase 6** | API 엔드포인트 | REST API 3개 + 권한 검증 | failed_orders.py | ✅ |
| **Phase 7** | Frontend UI | 관리 화면 (목록/재시도/제거) | failed_orders.js/css, positions.html | ✅ |

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

## 데이터베이스 마이그레이션

### Phase 1 초기화 (2025-10-27)

**파일**: `web_server/migrations/20251027_create_failed_orders_table.py`

초기 테이블 생성:
```sql
CREATE TABLE failed_orders (
    id SERIAL PRIMARY KEY,
    strategy_account_id INTEGER NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    side VARCHAR(10) NOT NULL,  -- BUY/SELL
    order_type VARCHAR(20) NOT NULL,  -- LIMIT/MARKET
    quantity NUMERIC(20, 8) NOT NULL,
    price NUMERIC(20, 8),
    stop_price NUMERIC(20, 8),
    market_type VARCHAR(10) NOT NULL,  -- SPOT/FUTURES
    reason VARCHAR(100) NOT NULL,
    exchange_error TEXT,
    order_params JSON NOT NULL,
    status VARCHAR(20) DEFAULT 'pending_retry',
    retry_count INTEGER DEFAULT 0,
    webhook_id VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (strategy_account_id) REFERENCES strategy_accounts(id)
);
```

### Phase 6 스키마 마이그레이션 (2025-10-30)

**파일**: `web_server/migrations/20251030_migrate_failed_orders_schema.py`

**목적**: 기존 legacy 스키마에서 Phase 1-3 최종 설계로 전환

**마이그레이션 단계**:
1. 신규 컬럼 추가 (nullable=True로 안전성 확보)
2. 기존 데이터 마이그레이션 (order_payload JSON 파싱 → 개별 컬럼)
3. NOT NULL 제약조건 추가 (필수 필드만)
4. 구 컬럼 제거 (user_id, pending_order_id, failure_reason, etc.)
5. 인덱스 재생성 (strategy_account_id+symbol, status+created_at, retry_count)

**변경 내용**:
- `failure_reason` → `reason` (간결화)
- `error_message` → `exchange_error` (명명 통일)
- `order_payload` → `order_params` (의미 명확화)
- 구 컬럼 완전 제거 (user_id, account_id, pending_order_id, etc.)

**주의사항**:
- 이 마이그레이션은 자동 롤백 지원 (`downgrade()` 함수 제공)
- 100개 이상 데이터 있을 경우 성능 영향 가능 (5-10분 소요)

---

## Phase 1-3: Backend Core

### FailedOrder 모델

**파일**: `web_server/app/models.py` (Lines 833-868)

```python
class FailedOrder(db.Model):
    __tablename__ = 'failed_orders'

    # 주문 파라미터
    symbol = db.Column(db.String(50), nullable=False)
    side = db.Column(db.String(10), nullable=False)  # BUY/SELL
    order_type = db.Column(db.String(20), nullable=False)  # LIMIT/MARKET
    quantity = db.Column(db.Numeric(20, 8), nullable=False)
    price = db.Column(db.Numeric(20, 8), nullable=True)  # LIMIT 가격
    stop_price = db.Column(db.Numeric(20, 8), nullable=True)  # STOP 가격
    market_type = db.Column(db.String(10), nullable=False)  # SPOT, FUTURES (Phase 1 신규)

    # 실패 정보
    reason = db.Column(db.String(100), nullable=False)  # 실패 이유 (간결한 요약)
    exchange_error = db.Column(db.Text, nullable=True)  # 거래소 에러 메시지 (API 키 마스킹됨)
    order_params = db.Column(db.JSON, nullable=False)  # 재시도용 전체 파라미터 (Symbol, side, quantity 등)

    # 재시도 관리
    status = db.Column(db.String(20), default='pending_retry', nullable=False)  # pending_retry, removed
    retry_count = db.Column(db.Integer, default=0, nullable=False)  # 재시도 횟수

    # 메타데이터
    webhook_id = db.Column(db.String(100), nullable=True)  # 웹훅 추적용 ID
    created_at = db.Column(db.DateTime, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False)

    # 관계 설정
    strategy_account = db.relationship('StrategyAccount', backref='failed_orders')

    # 인덱스 최적화
    __table_args__ = (
        db.Index('idx_failed_strategy_symbol', 'strategy_account_id', 'symbol'),
        db.Index('idx_failed_status', 'status', 'created_at'),
        db.Index('idx_failed_retry', 'retry_count'),
    )
```

**태그**: `@FEAT:immediate-order-execution @COMP:model @TYPE:core`

**Phase 1 주요 변경사항** (2025-10-30):
- `market_type` 필드 추가 (SPOT/FUTURES 구분)
- `order_params` JSON 필드 확대 (재시도 시 전체 파라미터 저장)
- `price`, `stop_price` nullable로 변경 (MARKET 주문은 가격 없음)
- `reason` 길이 제한 (100자로 간결화)
- `exchange_error` nullable로 변경 (민감 정보 마스킹 처리)

### FailedOrderManager

**파일**: `web_server/app/services/trading/failed_order_manager.py`

**아키텍처**: PostgreSQL + 메모리 캐시 이중화로 빠른 조회 제공

**핵심 메서드**:
```python
def save_failed_order(order_data, reason, exchange_error=None):
    """주문 실패 시 FailedOrder 테이블에 저장
    - exchange_error에서 API 키 마스킹 (정규식으로 민감정보 제거)
    - 메모리 캐시 동시성 보호 (threading.Lock 사용)
    - 캐시 최대 크기 제한 (1000개 이상 시 처리 필요)
    """

def get_failed_orders(strategy_account_id=None, symbol=None, status='pending_retry'):
    """실패 주문 목록 조회 (필터링 지원)
    - DB 쿼리 + 메모리 캐시 확인
    - 성능 최적화: idx_failed_strategy_symbol, idx_failed_status 인덱스 활용
    """

def retry_failed_order(failed_order_id):
    """재시도 로직 (최대 5회 제한)
    - ExchangeService.create_batch_orders()로 실제 거래소 호출
    - StrategyAccount 권한 검증
    - retry_count < 5 체크
    - 시스템 오류 시 retry_count 미소비 (트랜잭션 롤백)
    """

def remove_failed_order(failed_order_id):
    """실패 주문 제거 (soft delete)
    - status = 'removed'로 변경 (하드 삭제 아님)
    - 감사(Audit) 추적 가능
    """

def _sanitize_exchange_error(error_text):
    """거래소 에러 메시지에서 민감 정보 제거
    - API 키 패턴 마스킹 (abc123*** 형태)
    - 최대 500자로 제한
    - 로그 추적 가능성 유지
    """
```

**태그**: `@FEAT:immediate-order-execution @COMP:service @TYPE:core`

**Phase 2-3 주요 기능** (2025-10-27):
- **배치주문 API 통합**: ExchangeService.create_batch_orders() 호출
- **트랜잭션 경계 명확화**: 예외 시 롤백 + retry_count 재증가 방지
- **API 키 마스킹**: 정규식으로 민감정보 자동 제거 (보안 강화)

---

## Phase 4-5: Webhook Integration

### Webhook 즉시 실행

**파일**: `web_server/app/routes/webhook.py`

**변경 내용**:
```python
# 기존 (Queue 방식)
pending_order = create_pending_order(...)
db.session.add(pending_order)
db.session.commit()

# 신규 (Immediate 방식 + 타임아웃 처리)
try:
    # threading.Timer로 5초 타임아웃 설정
    # 타임아웃 시 FailedOrder 자동 저장 + 웹훅 응답 반환
    exchange_order = place_order_directly_with_timeout(...)
    return jsonify({'success': True, 'order_id': exchange_order.id})
except OrderExecutionError as e:
    failed_order_manager.save_failed_order(order_data, str(e))
    return jsonify({'success': False, 'error': str(e)}), 400
except TimeoutError:
    failed_order_manager.save_failed_order(order_data, 'Execution timeout (5s)')
    return jsonify({'success': False, 'error': 'Order execution timeout'}), 408
```

**Phase 4 주요 개선** (2025-10-23):
- **타임아웃 처리**: threading.Timer로 5초 제한, 초과 시 FailedOrder 저장
- **웹훅 응답 보장**: 거래소 지연 상관없이 빠른 응답 (408 또는 200)
- **대기 시간 0초**: 즉시 실행으로 거래소 수행 시간만 소요

**태그**: `@FEAT:immediate-order-execution @COMP:route @TYPE:core @DEPS:failed-order-manager`

### 큐 인프라 제거

**파일**: `web_server/app/models.py` (PendingOrder 제거)

**제거된 컴포넌트** (Phase 5, 2025-10-23):
- `PendingOrder` 모델 (DB 테이블)
- `OrderQueueManager` 서비스
- `queue_rebalancer.py` 스케줄러 (APScheduler 작업)
- 모든 큐 관련 백그라운드 작업 제거

**영향도**:
- 주문 대기열 정책 제거 (우선순위, 동적 재정렬 등 사용 불가)
- 메모리 사용량 감소 (큐 저장 불필요)
- DB 테이블 2개 감소 (pending_orders, queue_states)

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

**Request**:
- No body required
- CSRF 토큰 필수: `X-CSRF-Token` 헤더 또는 `csrf_token` 폼 파라미터

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

**Response (403 Forbidden)**:
```json
{
  "success": false,
  "error": "The CSRF token is missing"
}
```

**Security**:
- Flask-WTF CSRFProtect 자동 검증
- 권한 체인 검증 (User → Strategy → StrategyAccount → FailedOrder)
- 현재 사용자 소유 계정만 접근 가능

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
**Status**: ✅ Production Ready (Phase 1-7 Complete)

## 변경 이력 (최근 30일)

| 날짜 | 내용 | 파일 |
|------|------|------|
| 2025-10-30 | 마이그레이션 추가 (20251030_migrate_failed_orders_schema.py) | migrations/ |
| 2025-10-30 | Model 업데이트 (market_type, order_params 확대) | models.py |
| 2025-10-27 | Phase 1-3 완료 (FailedOrder 모델, FailedOrderManager, 재시도 로직) | multiple |
| 2025-10-23 | Phase 4-5 완료 (Webhook 즉시 실행, 큐 인프라 제거, 타임아웃 처리) | webhook.py, models.py |
| 2025-10-22 | Phase 6 완료 (API 엔드포인트 3개 + 권한 검증) | failed_orders.py |
| 2025-10-21 | Phase 7 완료 (Frontend UI: 목록/재시도/제거) | failed_orders.js, positions.html |
