# 웹훅 메시지 포맷

## 기본 구조

### 웹훅 URL
```
POST https://your-domain.com/api/webhook
Content-Type: application/json
```

### 필수 필드

| 필드 | 타입 | 설명 | 예시 |
|------|------|------|------|
| `group_name` | String | 전략 식별자 | `"my_strategy"` |
| `token` | String | 웹훅 인증 토큰 | `"abc123..."` |
| `symbol` | String | 거래 심볼 | `"BTC/USDT"`, `"005930"` |
| `order_type` | String | 주문 타입 | `"MARKET"`, `"LIMIT"` |
| `side` | String | 거래 방향 | `"buy"`, `"sell"` |
| `qty_per` | Number | 수량 (크립토: %, 증권: 주) | `10`, `-100` (청산), `200` (레버리지) |

### 주문 타입별 추가 필드

| order_type | 추가 필수 필드 |
|------------|---------------|
| `LIMIT` | `price` |
| `STOP_MARKET` | `stop_price` |
| `STOP_LIMIT` | `price`, `stop_price` |
| `CANCEL_ALL_ORDER` | (side 선택적) |

### 시스템 제한

**타임아웃**: 10초
- 웹훅 처리는 **10초 제한**이 적용됩니다
- 10초 내에 처리되지 않으면 타임아웃 응답 반환
- 배치 주문은 **30개 제한** (10초 안전 마진 확보)

**타임아웃 발생 시 응답**:
```json
{
  "success": false,
  "error": "Webhook processing timeout (10s)",
  "timeout": true,
  "processing_time_ms": 10000,
  "message": "웹훅 타임아웃"
}
```

> ⚠️ **중요**: 타임아웃 발생 시에도 **HTTP 200 OK**로 응답합니다. 이는 TradingView 등 외부 시스템의 자동 재전송을 방지하기 위함입니다.

> 💡 **부분 실행**: 배치 주문에서 타임아웃 발생 시, 완료된 주문은 유지되고 미완료 주문만 실패 처리됩니다.

### 심볼 포맷

**크립토**: `COIN/CURRENCY` (슬래시 필수)
- 예시: `"BTC/USDT"`, `"ETH/KRW"`

**증권**: 거래소별 종목코드
- 국내주식: `"005930"` (삼성전자)
- 해외주식: `"AAPL"`, `"TSLA"`

---

## 웹훅 예시

### 1. 시장가 매수
```json
{
  "group_name": "my_strategy",
  "symbol": "BTC/USDT",
  "order_type": "MARKET",
  "side": "buy",
  "qty_per": 10,
  "token": "your_webhook_token"
}
```

### 2. 지정가 매도
```json
{
  "group_name": "my_strategy",
  "symbol": "BTC/USDT",
  "order_type": "LIMIT",
  "side": "sell",
  "price": "130000",
  "qty_per": 10,
  "token": "your_webhook_token"
}
```

### 3. 손절 주문 (STOP_LIMIT)
```json
{
  "group_name": "my_strategy",
  "symbol": "BTC/USDT",
  "order_type": "STOP_LIMIT",
  "side": "sell",
  "price": "94000",
  "stop_price": "95000",
  "qty_per": 10,
  "token": "your_webhook_token"
}
```
**설명**: BTC 가격이 $95,000 이하로 떨어지면 $94,000에 매도

### 4. 포지션 100% 청산
```json
{
  "group_name": "my_strategy",
  "symbol": "BTC/USDT",
  "order_type": "MARKET",
  "side": "sell",
  "qty_per": -100,
  "token": "your_webhook_token"
}
```
**설명**: `qty_per: -100`은 전체 포지션 청산 (롱/숏 자동 판단)

### 5. 심볼별 주문 취소
```json
{
  "group_name": "my_strategy",
  "symbol": "BTC/USDT",
  "order_type": "CANCEL_ALL_ORDER",
  "token": "your_webhook_token"
}
```
**설명**: BTC/USDT 심볼의 모든 미체결 주문 취소

### 6. 특정 방향만 취소
```json
{
  "group_name": "my_strategy",
  "symbol": "BTC/USDT",
  "side": "buy",
  "order_type": "CANCEL_ALL_ORDER",
  "token": "your_webhook_token"
}
```
**설명**: BTC/USDT 매수 주문만 취소 (매도 주문은 유지)

---

## 배치 주문

### 구조
```json
{
  "group_name": "전략명",
  "symbol": "BTC/USDT",
  "token": "인증토큰",
  "orders": [
    {"order_type": "주문1"},
    {"order_type": "주문2"}
  ]
}
```

### 폴백 정책
- **상위 레벨 폴백**: `symbol`만 (각 주문에서 생략 가능)
- **각 주문 필수**: `order_type`, `side`, `qty_per`, `price` (타입별)

### 자동 우선순위 정렬

배치 주문은 2단계로 처리됩니다:

**1단계 (고우선순위 - 즉시 실행)**
- MARKET (시장가)
- CANCEL_ALL_ORDER (주문 취소)

**2단계 (저우선순위 - 이후 실행)**
- LIMIT (지정가)
- STOP_MARKET
- STOP_LIMIT

> 💡 **처리 방식**: 1단계 주문이 모두 완료된 후 2단계 주문이 실행됩니다. 각 단계는 독립적으로 처리되어 한 단계의 실패가 다른 단계에 영향을 주지 않습니다.

### 예시: 기존 주문 취소 후 재생성
```json
{
  "group_name": "ladder_strategy",
  "symbol": "BTC/USDT",
  "token": "your_webhook_token",
  "orders": [
    {
      "order_type": "CANCEL_ALL_ORDER"
    },
    {
      "side": "buy",
      "order_type": "LIMIT",
      "price": "105000",
      "qty_per": 5
    },
    {
      "side": "buy",
      "order_type": "LIMIT",
      "price": "104000",
      "qty_per": 10
    }
  ]
}
```
**처리 순서**: CANCEL → LIMIT(105000) → LIMIT(104000)

---

## 주요 에러

### 토큰 검증 실패
```json
{"error": "웹훅 토큰이 유효하지 않습니다", "status": 401}
```
→ 전략 설정에서 token 확인

### 심볼 포맷 오류
```json
{"error": "잘못된 심볼 포맷입니다: 'BTCUSDT'", "status": 400}
```
→ `BTCUSDT` → `BTC/USDT` (슬래시 추가)

### 필수 파라미터 누락
```json
{"error": "LIMIT 주문에는 price가 필수입니다", "status": 400}
```
→ order_type에 맞는 필드 추가

### 포지션 청산 실패
```json
{"error": "청산할 포지션이 없습니다.", "status": 400}
```
→ qty_per=-100은 포지션이 있을 때만 사용 가능

---

## FAQ

**Q. qty_per=-100은 무엇인가요?**
A. 현재 포지션을 100% 청산하는 특수 값입니다. 롱 포지션이면 전체 매도, 숏 포지션이면 전체 매수로 자동 변환됩니다.

**Q. CANCEL_ALL_ORDER에서 side는 왜 선택적인가요?**
A. side를 지정하면 해당 방향 주문만 취소됩니다. 생략하면 매수/매도 모두 취소됩니다.

**Q. 배치 주문에서 symbol을 각 주문마다 다르게 할 수 있나요?**
A. 아니오. 현재는 상위 레벨 symbol만 폴백 지원하므로, 한 번에 하나의 심볼만 처리 가능합니다.

**Q. exchange나 market_type을 지정해야 하나요?**
A. 아니오. 전략(group_name)에 연동된 모든 계좌에서 자동으로 주문이 실행됩니다.

**Q. 타임아웃이 발생하면 어떻게 되나요?**
A. 10초 타임아웃 발생 시에도 HTTP 200 OK로 응답합니다. 완료된 주문은 유지되고, 미완료 주문만 실패 처리됩니다. 응답의 `timeout: true` 필드로 타임아웃 여부를 확인할 수 있습니다.

**Q. qty_per를 100 이상으로 설정할 수 있나요?**
A. 네. Futures 거래에서 레버리지를 활용하는 경우 100% 이상 설정이 가능합니다. 예를 들어, qty_per=200, leverage=10이면 할당 자본의 20배 포지션을 보유하게 됩니다. 거래소의 레버리지 한도와 증거금 요구사항이 적용됩니다.

---

## 테스트 방법

### curl 테스트
```bash
curl -k -X POST https://your-domain.com/api/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "group_name": "test_strategy",
    "symbol": "BTC/USDT",
    "order_type": "LIMIT",
    "side": "buy",
    "price": "90000",
    "qty_per": 5,
    "token": "your_test_token"
  }'
```

### 로그 확인
```bash
tail -f /web_server/logs/app.log
```

---

## 보안 주의사항

1. **Token 노출 방지**: GitHub, 메신저 등에 token 공유 금지
2. **HTTPS 사용**: 프로덕션 환경에서 필수
3. **환경 변수 권장**: token을 코드에 하드코딩하지 말 것

---

**최종 업데이트**: 2025-11-07 (문서 정확성 검증 완료)
**버전**: 2.0 (통합 웹훅)
