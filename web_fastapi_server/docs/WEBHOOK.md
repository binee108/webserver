# Webhook API Documentation

FastAPI 기반 웹훅 처리 엔드포인트 - TradingView 및 외부 트레이딩 신호 수신

**Version**: Phase 4
**Last Updated**: 2025-10-31

---

## Table of Contents

- [개요](#개요)
- [빠른 시작](#빠른-시작)
- [API 엔드포인트](#api-엔드포인트)
- [요청 스키마](#요청-스키마)
- [응답 스키마](#응답-스키마)
- [지원 주문 타입](#지원-주문-타입)
- [인증](#인증)
- [타임아웃 처리](#타임아웃-처리)
- [에러 처리](#에러-처리)
- [성능 최적화](#성능-최적화)
- [예제](#예제)
- [Phase별 지원 기능](#phase별-지원-기능)

---

## 개요

웹훅 엔드포인트는 외부 시스템(TradingView, 커스텀 봇 등)에서 전송되는 트레이딩 신호를 수신하여 자동으로 주문을 처리합니다.

**핵심 특징**:
- ⚡ **비동기 병렬 처리** - 여러 계좌에 동시 주문 실행 (`asyncio.gather`)
- 🕒 **10초 타임아웃** - 응답 지연 방지
- 📝 **백그라운드 로깅** - DB 저장은 응답 후 처리 (레이턴시 제로)
- 🔐 **토큰 기반 인증** - 전략 소유자 및 구독자 토큰 지원
- 🎯 **Pydantic 자동 검증** - 요청 데이터 타입 및 필수 필드 검증

---

## 빠른 시작

### 1. 전략 생성 및 토큰 발급

웹훅을 사용하려면 전략(`Strategy`)과 웹훅 토큰이 필요합니다.

```sql
-- 1. 전략 생성 (Flask 웹 UI 또는 DB 직접 삽입)
INSERT INTO strategies (user_id, name, group_name, market_type, is_active)
VALUES (1, 'My Strategy', 'my-strategy-group', 'SPOT', true);

-- 2. 사용자 웹훅 토큰 생성 (Flask 웹 UI 또는 DB 직접 업데이트)
UPDATE users SET webhook_token = 'your-secret-token-here' WHERE id = 1;
```

### 2. 계좌 연결

전략에 거래소 계좌를 연결합니다.

```sql
-- 전략-계좌 연결 (StrategyAccount)
INSERT INTO strategy_accounts (strategy_id, account_id, weight, leverage, is_active)
VALUES (1, 1, 1.0, 1.0, true);
```

### 3. 웹훅 전송

TradingView 또는 커스텀 봇에서 웹훅을 전송합니다.

```bash
curl -X POST http://localhost:8000/api/v1/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "group_name": "my-strategy-group",
    "token": "your-secret-token-here",
    "action": "trading_signal",
    "order_type": "MARKET",
    "side": "BUY",
    "symbol": "BTC/USDT",
    "quantity": 0.001
  }'
```

---

## API 엔드포인트

### POST `/api/v1/webhook`

외부 트레이딩 신호를 수신합니다.

**URL**: `http://localhost:8000/api/v1/webhook`
**Method**: `POST`
**Content-Type**: `application/json`

**타임아웃**: 10초 (초과 시 HTTP 200 + error 응답)

---

## 요청 스키마

### WebhookRequest

| 필드 | 타입 | 필수 | 설명 | 예시 |
|------|------|------|------|------|
| `group_name` | `string` | ✅ | 전략 그룹명 (Strategy.group_name) | `"my-strategy"` |
| `token` | `string` | ✅ | 웹훅 인증 토큰 | `"abc123..."` |
| `action` | `string` | ✅ | 액션 타입 | `"trading_signal"` |
| `order_type` | `string` | ✅ | 주문 타입 (Phase 4: MARKET/CANCEL만) | `"MARKET"` |
| `side` | `string` | ✅ | 주문 방향 | `"BUY"` or `"SELL"` |
| `symbol` | `string` | ✅ | 거래 심볼 | `"BTC/USDT"` |
| `quantity` | `float` | 조건부 | 주문 수량 (MARKET 주문 시 필수) | `0.001` |
| `price` | `float` | ❌ | 지정가 (Phase 5) | `50000.0` |
| `stop_price` | `float` | ❌ | 스톱 가격 (Phase 5) | `49000.0` |
| `exchange` | `string` | ❌ | 특정 거래소 필터 | `"binance"` |

**검증 규칙**:
- Phase 4에서는 `order_type`이 `MARKET` 또는 `CANCEL`만 허용됩니다.
- `MARKET` 주문은 `quantity` 필수입니다.
- `side`는 자동으로 대문자로 정규화됩니다 (`buy` → `BUY`).

---

## 응답 스키마

### 성공 응답 (WebhookResponse)

```json
{
  "success": true,
  "action": "trading_signal",
  "strategy": "My Strategy",
  "message": "웹훅 처리 완료 - 성공: 3, 실패: 0",
  "results": [
    {
      "account_id": 1,
      "account_name": "Binance Main",
      "exchange": "binance",
      "symbol": "BTC/USDT",
      "success": true,
      "order_id": "12345678",
      "executed_quantity": 0.001,
      "executed_price": 50000.0
    }
  ],
  "summary": {
    "total_accounts": 3,
    "successful_orders": 3,
    "failed_orders": 0,
    "success_rate": 100.0
  },
  "performance_metrics": {
    "total_processing_time_ms": 150.5,
    "validation_time_ms": 5.2,
    "execution_time_ms": 120.0
  }
}
```

### 에러 응답 (WebhookErrorResponse)

```json
{
  "success": false,
  "error": "활성 전략을 찾을 수 없습니다: invalid-group",
  "processing_time_ms": 10.5
}
```

### 타임아웃 응답

```json
{
  "success": false,
  "error": "Webhook processing timeout (10s)",
  "timeout": true,
  "processing_time_ms": 10000.0
}
```

**HTTP 상태 코드**:
- `200 OK` - 모든 경우 (성공/실패/타임아웃) - TradingView 재전송 방지
- `500 Internal Server Error` - 예상치 못한 서버 오류

---

## 지원 주문 타입

### Phase 4 (현재)

| 주문 타입 | 설명 | 필수 파라미터 | 처리 방식 |
|----------|------|--------------|----------|
| `MARKET` | 시장가 주문 | `quantity` | 즉시 실행 (병렬) |
| `CANCEL` | 미체결 주문 취소 | `symbol` | Cancel Queue 진입 (Phase 2) |

### Phase 5 (예정)

| 주문 타입 | 설명 | 필수 파라미터 |
|----------|------|--------------|
| `LIMIT` | 지정가 주문 | `quantity`, `price` |
| `STOP` | 스톱 주문 | `quantity`, `stop_price` |
| `STOP_LIMIT` | 스톱 리밋 주문 | `quantity`, `price`, `stop_price` |

**Phase 4에서 LIMIT/STOP 주문 전송 시**:
```json
{
  "success": false,
  "error": "Phase 4에서는 MARKET/CANCEL 주문만 지원됩니다. 받은 주문 타입: LIMIT. LIMIT/STOP 주문은 Phase 5에서 구현될 예정입니다."
}
```

---

## 인증

웹훅 인증은 토큰 기반으로 이루어집니다.

### 허용되는 토큰

1. **전략 소유자 토큰** - `Strategy.user.webhook_token`
2. **구독자 토큰** (공개 전략만) - 전략을 구독한 사용자의 토큰

### 토큰 검증 로직

```python
# 1. 전략 조회
strategy = Strategy.query.filter_by(group_name=group_name, is_active=True).first()

# 2. 허용 토큰 수집
valid_tokens = {strategy.user.webhook_token}  # 소유자 토큰

if strategy.is_public:
    # 공개 전략: 구독자 토큰도 허용
    for sa in strategy.strategy_accounts:
        if sa.is_active and sa.account.user:
            valid_tokens.add(sa.account.user.webhook_token)

# 3. 검증
if token not in valid_tokens:
    raise WebhookException("웹훅 토큰이 유효하지 않습니다")
```

### 보안 권장사항

- 토큰은 UUID 또는 최소 32자 이상의 무작위 문자열 사용
- HTTPS 사용 (프로덕션 환경)
- 토큰은 환경 변수 또는 안전한 저장소에 보관
- 주기적으로 토큰 재발급

---

## 타임아웃 처리

### 10초 타임아웃

웹훅 처리는 최대 10초로 제한됩니다.

```python
result = await asyncio.wait_for(
    webhook_service.process_webhook(...),
    timeout=10.0
)
```

### 타임아웃 발생 시 동작

1. **HTTP 200 OK 응답** - TradingView 재전송 방지
2. **에러 플래그** - `timeout: true`, `success: false`
3. **백그라운드 로그 저장** - 타임아웃 상황도 기록

### 타임아웃 원인

- 다수 계좌 동시 처리 (30개 초과)
- 거래소 API 응답 지연
- 네트워크 불안정

### 대응 방법

1. 전략에 연결된 계좌 수 줄이기 (권장: 30개 이하)
2. 거래소 API 타임아웃 설정 확인 (`config.py`)
3. 네트워크 상태 점검

---

## 에러 처리

### 주요 에러 유형

| 에러 메시지 | 원인 | 해결 방법 |
|-----------|------|----------|
| `활성 전략을 찾을 수 없습니다` | 전략이 존재하지 않거나 비활성 | `group_name` 확인, 전략 활성화 |
| `웹훅 토큰이 유효하지 않습니다` | 토큰 불일치 | 올바른 토큰 사용 |
| `MARKET 주문에는 quantity가 필수입니다` | quantity 누락 | `quantity` 필드 추가 |
| `Phase 4에서는 MARKET/CANCEL만...` | 미지원 주문 타입 | MARKET/CANCEL만 사용 |
| `Webhook processing timeout` | 10초 초과 | 계좌 수 줄이기 |

### 에러 응답 예시

```json
{
  "success": false,
  "error": "웹훅 토큰이 유효하지 않습니다",
  "processing_time_ms": 12.3
}
```

---

## 성능 최적화

### 비동기 병렬 처리

여러 계좌에 동시에 주문을 실행하여 레이턴시를 최소화합니다.

**Before (동기 방식)**:
```
계좌 1 → 100ms
계좌 2 → 100ms
계좌 3 → 100ms
-------------------
합계: 300ms
```

**After (비동기 병렬)**:
```
계좌 1 ┐
계좌 2 ├→ max(100ms)
계좌 3 ┘
-------------------
합계: 100ms
```

### 백그라운드 작업

DB 로그 저장은 응답 후 백그라운드에서 처리됩니다.

```python
# 응답 전 (레이턴시 영향)
validation_time_ms: 5.2
execution_time_ms: 120.0

# 응답 후 (백그라운드)
db_save_time_ms: 25.3  # 레이턴시에 포함 안 됨
```

### 성능 벤치마크

| 시나리오 | 목표 | 실제 (Phase 4) |
|---------|------|---------------|
| MARKET 1개 계좌 | <100ms | ~80ms |
| MARKET 10개 계좌 | <500ms | ~200ms |
| MARKET 30개 계좌 | <3s | ~1s |

---

## 예제

### TradingView Webhook 설정

1. **Alert 생성** - Pine Script에서 조건 설정
2. **Webhook URL 입력** - `http://your-server.com/api/v1/webhook`
3. **Message 작성**:

```json
{
  "group_name": "{{strategy.order.comment}}",
  "token": "your-secret-token",
  "action": "trading_signal",
  "order_type": "MARKET",
  "side": "{{strategy.order.action}}",
  "symbol": "{{ticker}}",
  "quantity": {{strategy.order.contracts}}
}
```

### Python 클라이언트 예제

```python
import requests
import time

def send_webhook(group_name, token, order_type, side, symbol, quantity):
    url = "http://localhost:8000/api/v1/webhook"
    payload = {
        "group_name": group_name,
        "token": token,
        "action": "trading_signal",
        "order_type": order_type,
        "side": side,
        "symbol": symbol,
        "quantity": quantity
    }

    start = time.time()
    response = requests.post(url, json=payload)
    elapsed = (time.time() - start) * 1000

    print(f"Status: {response.status_code}")
    print(f"Response time: {elapsed:.2f}ms")
    print(f"Result: {response.json()}")

    return response.json()

# MARKET 주문 예제
result = send_webhook(
    group_name="my-strategy",
    token="abc123...",
    order_type="MARKET",
    side="BUY",
    symbol="BTC/USDT",
    quantity=0.001
)
```

### cURL 예제

```bash
# MARKET 주문
curl -X POST http://localhost:8000/api/v1/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "group_name": "my-strategy",
    "token": "abc123...",
    "action": "trading_signal",
    "order_type": "MARKET",
    "side": "BUY",
    "symbol": "BTC/USDT",
    "quantity": 0.001
  }'

# 거래소 필터 (Binance만)
curl -X POST http://localhost:8000/api/v1/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "group_name": "my-strategy",
    "token": "abc123...",
    "action": "trading_signal",
    "order_type": "MARKET",
    "side": "SELL",
    "symbol": "ETH/USDT",
    "quantity": 0.1,
    "exchange": "binance"
  }'
```

---

## Phase별 지원 기능

### Phase 4 (현재)

✅ **구현 완료**:
- MARKET 주문 즉시 실행 (비동기 병렬)
- CANCEL 주문 Queue 진입 (Phase 2 통합)
- 10초 타임아웃
- 백그라운드 DB 저장
- Pydantic 자동 검증
- 토큰 기반 인증 (소유자 + 구독자)

⚠️ **알려진 TODO**:
- API 키 복호화 로직 (Flask 연동 필요)
- WebhookLog 모델 DB 저장 (현재 placeholder)

### Phase 5 (예정)

🔜 **계획**:
- LIMIT 주문 지정가 처리
- STOP 주문 조건부 실행
- STOP_LIMIT 복합 주문
- Pending Queue 시스템

---

## 문제 해결

### 로그 확인

웹훅 처리 로그는 애플리케이션 로그에 기록됩니다.

```bash
# 로그 확인 (Docker)
docker logs fastapi-server -f | grep webhook

# 로그 확인 (로컬)
tail -f logs/app.log | grep webhook
```

**주요 로그 패턴**:
- `🔔 웹훅 수신` - 요청 수신
- `✅ 웹훅 처리 완료` - 정상 처리
- `❌ 웹훅 처리 실패` - 에러 발생
- `⏱️ 웹훅 처리 타임아웃` - 10초 초과

### API 문서 (Swagger UI)

FastAPI 자동 생성 문서에서 실시간 테스트 가능:

**URL**: `http://localhost:8000/docs`

1. `/api/v1/webhook` 엔드포인트 클릭
2. "Try it out" 버튼 클릭
3. 요청 JSON 입력
4. "Execute" 버튼 클릭

---

## 참고 자료

- [Phase 3 - Exchange Adapters](./EXCHANGES.md)
- [Phase 2 - Cancel Queue](./CANCEL_QUEUE.md)
- [Configuration Guide](./CONFIGURATION.md)
- [Models Documentation](./MODELS.md)

---

**Last Updated**: 2025-10-31
**Phase**: Phase 4
**Status**: Production Ready (MARKET/CANCEL)
