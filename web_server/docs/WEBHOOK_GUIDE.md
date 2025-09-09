# 웹훅 사용 가이드

암호화폐 자동 거래 시스템의 웹훅 기능 사용법을 설명합니다.

## 목차
1. [웹훅 시스템 개요](#웹훅-시스템-개요)
2. [엔드포인트 정보](#엔드포인트-정보)
3. [단일 주문 웹훅](#단일-주문-웹훅)
4. [배치 주문 웹훅](#배치-주문-웹훅)
5. [주문 취소 웹훅](#주문-취소-웹훅)
6. [응답 형식](#응답-형식)
7. [테스트 방법](#테스트-방법)
8. [트러블슈팅](#트러블슈팅)

## 웹훅 시스템 개요

외부 서비스(TradingView, 자체 봇 등)에서 거래 신호를 자동으로 전송받아 거래를 실행하는 기능입니다.

### 주요 기능
- **단일/배치 주문**: 하나 또는 여러 개의 주문을 동시에 처리
- **Rate Limit 관리**: 거래소별 제한을 자동으로 준수
- **다중 계좌 지원**: 하나의 신호로 여러 계좌에서 병렬 거래
- **주문 취소**: 특정 조건에서 미체결 주문 선택적 취소

### 지원 거래소
- **Binance** (현물, 선물)
- **Bybit** (현물, 선물)
- **OKX** (현물, 선물)

## 엔드포인트 정보

### URL
```
POST https://your-domain.com/api/webhook
```

### 헤더
```
Content-Type: application/json
```

### 인증
웹훅 토큰 필수. 프로필 페이지에서 토큰을 생성하여 `token` 필드에 포함해주세요.

## 단일 주문 웹훅

### 필수 필드

| 필드명 | 타입 | 설명 | 예시 |
|--------|------|------|------|
| `group_name` | String | 전략 그룹명 | "my_strategy" |
| `token` | String | 웹훅 토큰 | "your_webhook_token" |
| `exchange` | String | 거래소 | "BINANCE", "BYBIT", "OKX" |
| `market_type` | String | 시장 타입 | "SPOT", "FUTURES" |
| `currency` | String | 결제 통화 | "USDT", "BUSD" |
| `symbol` | String | 거래 심볼 | "BTCUSDT" |
| `order_type` | String | 주문 타입 | "MARKET", "LIMIT", "STOP_LIMIT", "STOP_MARKET" |
| `side` | String | 거래 방향 | "buy", "sell", "long", "short" |

### 선택 필드

| 필드명 | 타입 | 설명 | 기본값 | 예시 |
|--------|------|------|-------|------|
| `price` | Number | 주문 가격 (LIMIT 주문시) | None | 45000, 3200.5 |
| `stop_price` | Number | 스탑 가격 (STOP 주문시) | None | 44000 |
| `qty_per` | Number | 수량 비율 (%) | 100 | 50, 25 |

### 예시

#### 시장가 매수
```json
{
  "group_name": "my_strategy",
  "token": "your_webhook_token",
  "exchange": "BINANCE",
  "market_type": "FUTURES",
  "currency": "USDT",
  "symbol": "BTCUSDT",
  "order_type": "MARKET",
  "side": "buy",
  "qty_per": 10
}
```

#### 지정가 매도
```json
{
  "group_name": "my_strategy",
  "token": "your_webhook_token",
  "exchange": "BINANCE",
  "market_type": "FUTURES",
  "currency": "USDT",
  "symbol": "BTCUSDT",
  "order_type": "LIMIT",
  "side": "sell",
  "price": 105000,
  "qty_per": 50
}
```

#### STOP LIMIT 주문
```json
{
  "group_name": "my_strategy",
  "token": "your_webhook_token",
  "exchange": "BINANCE",
  "market_type": "FUTURES",
  "currency": "USDT",
  "symbol": "BTCUSDT",
  "order_type": "STOP_LIMIT",
  "side": "sell",
  "price": 105000,
  "stop_price": 104000,
  "qty_per": 25
}
```

## 배치 주문 웹훅

동일한 거래소/시장타입/심볼에서 가격과 수량만 다른 여러 주문을 한 번에 처리할 수 있습니다.

### 배치 주문 포맷

**공통 필드**: 단일 주문과 동일하되 `price`, `qty_per` 제외
**orders 배열**: 각 주문의 `price`, `qty_per` (및 선택적으로 `stop_price`) 포함

### 예시

#### LIMIT 배치 주문
```json
{
  "group_name": "my_strategy",
  "token": "your_webhook_token",
  "exchange": "BINANCE",
  "market_type": "FUTURES",
  "currency": "USDT",
  "symbol": "BTCUSDT",
  "order_type": "LIMIT",
  "side": "buy",
  "orders": [
    {"price": 78000, "qty_per": 3},
    {"price": 77000, "qty_per": 4},
    {"price": 76000, "qty_per": 5}
  ]
}
```

#### STOP_LIMIT 배치 주문
```json
{
  "group_name": "my_strategy",
  "token": "your_webhook_token",
  "exchange": "BINANCE",
  "market_type": "FUTURES",
  "currency": "USDT",
  "symbol": "BTCUSDT",
  "order_type": "STOP_LIMIT",
  "side": "sell",
  "orders": [
    {"price": 105000, "stop_price": 104000, "qty_per": 10},
    {"price": 107000, "stop_price": 106000, "qty_per": 15}
  ]
}
```

### 배치 주문 특징
- **Rate Limit 자동 관리**: 거래소별 제한에 맞춰 지연 시간 자동 적용
- **순차 실행**: 계좌 내에서는 순차적으로 주문 실행
- **병렬 처리**: 여러 계좌 간에는 병렬로 처리
- **독립적 트랜잭션**: 각 계좌별로 독립적인 커밋/롤백

## 주문 취소 웹훅

미체결 주문을 선택적으로 취소합니다.

### 필수 필드
| 필드명 | 타입 | 설명 | 예시 |
|--------|------|------|------|
| `group_name` | String | 전략 그룹명 | "my_strategy" |
| `token` | String | 웹훅 토큰 | "your_webhook_token" |
| `order_type` | String | 고정값 | "CANCEL_ALL_ORDER" |

### 선택 필드 (필터링)
| 필드명 | 타입 | 설명 | 기본값 |
|--------|------|------|-------|
| `exchange` | String | 특정 거래소만 취소 | 전체 |
| `market_type` | String | 특정 마켓만 취소 | 전체 |
| `symbol` | String | 특정 심볼만 취소 | 전체 |

### 예시

#### 전체 주문 취소
```json
{
  "group_name": "my_strategy",
  "token": "your_webhook_token",
  "order_type": "CANCEL_ALL_ORDER"
}
```

#### 특정 심볼만 취소
```json
{
  "group_name": "my_strategy",
  "token": "your_webhook_token",
  "order_type": "CANCEL_ALL_ORDER",
  "symbol": "BTCUSDT"
}
```

## 응답 형식

### 단일 주문 성공 응답
```json
{
  "success": true,
  "message": "웹훅 처리 성공",
  "result": {
    "action": "trading_signal",
    "strategy": "my_strategy",
    "results": [
      {
        "account_id": 1,
        "account_name": "Main Account",
        "exchange": "binance",
        "success": true,
        "order_id": "12345",
        "quantity": 0.002,
        "order_price": 80000.0,
        "status": "PENDING"
      }
    ],
    "summary": {
      "total_accounts": 1,
      "executed_accounts": 1,
      "successful_trades": 1,
      "failed_trades": 0
    }
  }
}
```

### 배치 주문 성공 응답
```json
{
  "success": true,
  "message": "웹훅 처리 성공",
  "result": {
    "action": "batch_trading_signal",
    "strategy": "my_strategy",
    "symbol": "BTCUSDT",
    "total_orders": 3,
    "accounts": [
      {
        "account_id": 1,
        "account_name": "Main Account",
        "exchange": "binance",
        "successful_orders": 3,
        "failed_orders": 0,
        "orders": [
          {
            "order_index": 0,
            "order_id": "12345",
            "requested_price": 78000,
            "requested_qty_per": 3.0,
            "success": true
          }
        ]
      }
    ],
    "summary": {
      "total_accounts": 1,
      "executed_accounts": 1,
      "successful_accounts": 1,
      "total_orders_successful": 3,
      "total_orders_failed": 0
    }
  }
}
```

### 오류 응답
```json
{
  "success": false,
  "error": "필수 필드 누락: exchange"
}
```

## 테스트 방법

### curl 명령어 예시

#### 단일 LIMIT 주문 테스트
```bash
curl -k -X POST https://your-domain.com/api/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "group_name": "test1",
    "exchange": "BINANCE",
    "market_type": "FUTURES",
    "currency": "USDT",
    "symbol": "BTCUSDT",
    "order_type": "LIMIT",
    "side": "buy",
    "price": "80000",
    "qty_per": 5,
    "token": "your_webhook_token"
  }'
```

#### 배치 LIMIT 주문 테스트
```bash
curl -k -X POST https://your-domain.com/api/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "group_name": "test1",
    "exchange": "BINANCE",
    "market_type": "FUTURES",
    "currency": "USDT",
    "symbol": "BTCUSDT",
    "order_type": "LIMIT",
    "side": "buy",
    "orders": [
      {"price": 78000, "qty_per": 3},
      {"price": 77000, "qty_per": 4},
      {"price": 76000, "qty_per": 5}
    ],
    "token": "your_webhook_token"
  }'
```

#### 배치 STOP_LIMIT 주문 테스트
```bash
curl -k -X POST https://your-domain.com/api/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "group_name": "test1",
    "exchange": "BINANCE",
    "market_type": "FUTURES",
    "currency": "USDT",
    "symbol": "BTCUSDT",
    "order_type": "STOP_LIMIT",
    "side": "sell",
    "orders": [
      {"price": 105000, "stop_price": 104000, "qty_per": 10},
      {"price": 107000, "stop_price": 106000, "qty_per": 15}
    ],
    "token": "your_webhook_token"
  }'
```

#### 주문 취소 테스트
```bash
curl -k -X POST https://your-domain.com/api/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "group_name": "test1",
    "order_type": "CANCEL_ALL_ORDER",
    "token": "your_webhook_token"
  }'
```

### Python 테스트 스크립트
```python
import requests

def test_webhook(data):
    url = "https://your-domain.com/api/webhook"
    headers = {"Content-Type": "application/json"}
    
    response = requests.post(url, headers=headers, json=data, verify=False)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")

# 배치 주문 테스트
test_webhook({
    "group_name": "test1",
    "exchange": "BINANCE",
    "market_type": "FUTURES",
    "currency": "USDT",
    "symbol": "BTCUSDT",
    "order_type": "LIMIT",
    "side": "buy",
    "orders": [
        {"price": 78000, "qty_per": 3},
        {"price": 77000, "qty_per": 4}
    ],
    "token": "your_webhook_token"
})
```

## 트러블슈팅

### 자주 발생하는 오류

#### "필수 필드 누락: [field_name]"
- **원인**: 필수 필드 누락
- **해결**: 모든 필수 필드 포함 확인

#### "활성 전략을 찾을 수 없습니다"
- **원인**: `group_name`이 잘못되었거나 전략 비활성화
- **해결**: 전략 관리에서 `group_name` 확인 및 전략 활성화

#### "웹훅 토큰이 유효하지 않습니다"
- **원인**: 잘못된 또는 만료된 토큰
- **해결**: 프로필에서 새 토큰 생성

#### "전략에 연결된 계좌가 없습니다"
- **원인**: 전략에 거래소 계좌가 연결되지 않음
- **해결**: 전략-계정 연결 메뉴에서 계좌 연결

### 로그 확인 방법
1. **서버 로그**: `logs/app.log` 파일 확인
2. **웹훅 로그**: 데이터베이스의 `webhook_logs` 테이블
3. **거래 내역**: 웹 인터페이스에서 주문 실행 여부 확인

### 디버깅 팁
- **배치 주문**: 개별 주문별 성공/실패 상태를 `orders` 배열에서 확인
- **Rate Limit**: 로그에서 지연 시간이 적절히 적용되었는지 확인
- **필드 표준화**: 대소문자나 필드명 변형은 자동으로 처리됨

---
*이 문서는 실제 코드 구현을 기반으로 작성되었습니다.*