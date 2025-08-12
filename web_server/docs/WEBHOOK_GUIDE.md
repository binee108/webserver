# 웹훅 사용 가이드

이 문서는 암호화폐 자동 거래 시스템의 웹훅 기능을 사용하는 방법을 설명합니다.
**실제 코드 구현을 기반으로 작성되었습니다.**

## 목차
1. [웹훅 시스템 개요](#웹훅-시스템-개요)
2. [엔드포인트 정보](#엔드포인트-정보)
3. [거래 신호 웹훅](#거래-신호-웹훅)
4. [주문 취소 웹훅](#주문-취소-웹훅)
5. [응답 형식](#응답-형식)
6. [TradingView 연동](#tradingview-연동)
7. [테스트 방법](#테스트-방법)
8. [트러블슈팅](#트러블슈팅)
9. [보안 고려사항](#보안-고려사항)

## 웹훅 시스템 개요

웹훅(Webhook)은 외부 서비스(TradingView, 자체 봇 등)에서 거래 신호나 명령을 자동으로 전송받아 거래를 실행하는 기능입니다.

### 주요 기능
- **거래 신호 처리**: 매수/매도 신호를 받아 자동으로 주문 실행
- **주문 취소**: 특정 조건에서 모든 미체결 주문 취소
- **다중 계정 지원**: 하나의 신호로 여러 거래소 계정에서 병렬 거래
- **유연한 포맷**: 다양한 필드명 형식 지원 (대소문자 구별 없음)
- **최대 심볼 제한**: 계정별 동시 거래 심볼 수 제한 기능

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
현재 웹훅 엔드포인트는 공개되어 있으며 별도 인증이 없습니다. 
보안을 위해 웹훅 URL을 외부에 노출하지 않도록 주의하세요.

## 거래 신호 웹훅

### 필수 필드

| 필드명 | 타입 | 설명 | 예시 |
|--------|------|------|------|
| `group_name` | String | 전략 그룹명 (전략 생성 시 설정) | "my_strategy" |
| `exchange` | String | 거래소 | "BINANCE", "BYBIT", "OKX" |
| `market_type` | String | 시장 타입 | "SPOT", "FUTURES" |
| `currency` | String | 결제 통화 | "USDT", "BUSD" |
| `symbol` | String | 거래 심볼 | "BTCUSDT" |
| `orderType` | String | 주문 타입 | "MARKET", "LIMIT" |
| `side` | String | 거래 방향 | "buy", "sell", "long", "short" |

### 선택 필드

| 필드명 | 타입 | 설명 | 기본값 | 예시 |
|--------|------|------|-------|------|
| `price` | Number | 주문 가격 (LIMIT 주문시만 사용) | None | 45000, 3200.5 |
| `qty_per` | Number | 계정당 수량 비율 (%) | 100 | 50, 25 |

### 중요한 제약사항
- **price 필드는 숫자만 지원**: `45000`, `3200.5` 등은 가능하지만 `"limit:45000"` 같은 문자열 형식은 **지원하지 않습니다**.
- **모든 필수 필드 누락 불가**: 하나라도 누락되면 오류가 발생합니다.

### 필드명 유연성
시스템이 자동으로 인식하는 필드명 변형:
- `platform` → `exchange`
- `order_type`, `ordertype` → `orderType`
- 모든 필드명은 대소문자 구별 없이 처리됩니다

### 자동 표준화
- `orderType`: 대문자로 변환 (MARKET, LIMIT)
- `side`: 소문자로 변환 (buy, sell, long, short)
- `exchange`: 대문자로 변환 (BINANCE, BYBIT, OKX)
- `market_type`: 대문자로 변환 (SPOT, FUTURES)
- `currency`: 대문자로 변환 (USDT, BUSD)

### 거래 신호 예시

#### 기본 시장가 매수
```json
{
    "group_name": "my_btc_strategy",
    "exchange": "BINANCE",
    "market_type": "SPOT",
    "currency": "USDT",
    "symbol": "BTCUSDT",
    "orderType": "MARKET",
    "side": "buy"
}
```

#### 지정가 매도 (50% 수량)
```json
{
    "group_name": "my_btc_strategy",
    "exchange": "BINANCE", 
    "market_type": "SPOT",
    "currency": "USDT",
    "symbol": "BTCUSDT",
    "orderType": "LIMIT",
    "side": "sell",
    "price": 45000,
    "qty_per": 50
}
```

#### 선물 롱 포지션 진입
```json
{
    "group_name": "futures_strategy",
    "exchange": "BINANCE",
    "market_type": "FUTURES", 
    "currency": "USDT",
    "symbol": "BTCUSDT",
    "orderType": "MARKET",
    "side": "long",
    "qty_per": 25
}
```

#### 필드명 유연성 예시 (모두 동일하게 처리됨)
```json
{
    "GROUP_NAME": "test_strategy",
    "Platform": "binance",
    "Market_Type": "spot", 
    "Currency": "usdt",
    "Symbol": "BTCUSDT",
    "order_type": "market",
    "Side": "BUY"
}
```

## 주문 취소 웹훅

미체결 주문을 선택적으로 취소하는 특수 웹훅입니다. 전략, 거래소, 마켓, 심볼별로 세분화하여 취소할 수 있습니다.

### 필수 필드
| 필드명 | 타입 | 설명 | 예시 |
|--------|------|------|------|
| `group_name` | String | 전략 그룹명 | "my_strategy" |
| `orderType` | String | 주문 타입 (고정값) | "CANCEL_ALL_ORDER" |

### 선택 필드 (필터링)
| 필드명 | 타입 | 설명 | 기본값 | 예시 |
|--------|------|------|-------|------|
| `exchange` | String | 특정 거래소만 취소 | 전체 | "BINANCE", "BYBIT", "OKX" |
| `market_type` | String | 특정 마켓 타입만 취소 | 전체 | "SPOT", "FUTURES" |
| `currency` | String | 특정 통화만 (향후 확장용) | 전체 | "USDT" |
| `symbol` | String | 특정 심볼만 취소 | 전체 | "BTCUSDT" |

### 필터링 동작 방식
- 필터 조건을 지정하지 않으면 전략의 모든 주문을 취소합니다
- 여러 필터를 조합하면 AND 조건으로 적용됩니다
- 예: `exchange="BINANCE"` + `symbol="BTCUSDT"` = Binance 거래소의 BTCUSDT 주문만 취소

### 주문 취소 예시

#### 전체 주문 취소 (기존 방식)
```json
{
    "group_name": "my_strategy",
    "orderType": "CANCEL_ALL_ORDER"
}
```

#### 특정 거래소의 모든 주문 취소
```json
{
    "group_name": "my_strategy",
    "orderType": "CANCEL_ALL_ORDER",
    "exchange": "BINANCE"
}
```

#### 특정 심볼의 주문만 취소
```json
{
    "group_name": "my_strategy",
    "orderType": "CANCEL_ALL_ORDER",
    "symbol": "BTCUSDT"
}
```

#### 특정 마켓의 주문만 취소
```json
{
    "group_name": "my_strategy",
    "orderType": "CANCEL_ALL_ORDER",
    "market_type": "FUTURES"
}
```

#### 복합 필터링: 특정 거래소+마켓+심볼
```json
{
    "group_name": "my_strategy",
    "orderType": "CANCEL_ALL_ORDER",
    "exchange": "BINANCE",
    "market_type": "FUTURES",
    "symbol": "BTCUSDT"
}
```

## 응답 형식

### 성공 응답 (거래 신호)
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
                "account_name": "Binance Main",
                "exchange": "BINANCE",
                "success": true,
                "order_id": "12345",
                "message": "주문 성공",
                "quantity": 0.001,
                "order_price": 45000,
                "filled_price": 44990,
                "status": "FILLED"
            }
        ],
        "summary": {
            "total_accounts": 3,
            "executed_accounts": 2,
            "successful_trades": 1,
            "failed_trades": 1,
            "inactive_accounts": 1
        }
    }
}
```

### 성공 응답 (주문 취소)
```json
{
    "success": true,
    "message": "웹훅 처리 성공",
    "result": {
        "action": "cancel_all_orders",
        "strategy": "my_strategy",
        "market_type": "SPOT",
        "results": [
            {
                "account_id": 1,
                "account_name": "Binance Main",
                "exchange": "BINANCE",
                "cancelled_orders": 3,
                "failed_orders": 0,
                "success": true,
                "message": "주문 취소 완료"
            }
        ],
        "summary": {
            "total_accounts": 2,
            "processed_accounts": 2,
            "successful_accounts": 2,
            "total_cancelled_orders": 5
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

### 일반적인 오류 메시지
- `"필수 필드 누락: [field_name]"`
- `"활성 전략을 찾을 수 없습니다: [group_name]"`
- `"전략에 연결된 계좌가 없습니다: [group_name]"`
- `"Content-Type must be application/json"`
- `"No JSON data provided"`

### HTTP 상태 코드
- `200`: 성공
- `400`: 잘못된 요청 (필수 필드 누락, 데이터 형식 오류)
- `500`: 서버 내부 오류

## TradingView 연동

### 기본 Pine Script 예시
```pinescript
//@version=5
strategy("Webhook Strategy", overlay=true)

// 전략 설정
group_name = "my_strategy"

// 매수 조건
long_condition = ta.crossover(ta.sma(close, 10), ta.sma(close, 20))
if (long_condition)
    strategy.entry("Long", strategy.long)
    webhook_message = '{"group_name":"' + group_name + '","exchange":"BINANCE","market_type":"SPOT","currency":"USDT","symbol":"{{ticker}}","orderType":"MARKET","side":"buy"}'
    alert(webhook_message, alert.freq_once_per_bar)

// 매도 조건  
short_condition = ta.crossunder(ta.sma(close, 10), ta.sma(close, 20))
if (short_condition)
    strategy.close("Long")
    webhook_message = '{"group_name":"' + group_name + '","exchange":"BINANCE","market_type":"SPOT","currency":"USDT","symbol":"{{ticker}}","orderType":"MARKET","side":"sell"}'
    alert(webhook_message, alert.freq_once_per_bar)
```

### 고급 Pine Script (지정가 주문)
```pinescript
//@version=5
strategy("Advanced Webhook Strategy", overlay=true)

// 전략 설정
group_name = "advanced_strategy"
qty_percentage = 50

// 매수 신호
long_condition = ta.crossover(ta.sma(close, 9), ta.sma(close, 21))
if (long_condition)
    strategy.entry("Long", strategy.long)
    webhook_message = '{"group_name":"' + group_name + '","exchange":"BINANCE","market_type":"SPOT","currency":"USDT","symbol":"{{ticker}}","orderType":"MARKET","side":"buy","qty_per":' + str.tostring(qty_percentage) + '}'
    alert(webhook_message, alert.freq_once_per_bar)

// 지정가 매도 신호
short_condition = ta.crossunder(ta.sma(close, 9), ta.sma(close, 21))
if (short_condition)
    strategy.close("Long")
    limit_price = close * 1.02
    webhook_message = '{"group_name":"' + group_name + '","exchange":"BINANCE","market_type":"SPOT","currency":"USDT","symbol":"{{ticker}}","orderType":"LIMIT","side":"sell","price":' + str.tostring(limit_price) + ',"qty_per":' + str.tostring(qty_percentage) + '}'
    alert(webhook_message, alert.freq_once_per_bar)
```

## 테스트 방법

### 1. curl을 사용한 테스트

#### Linux/macOS
```bash
# 1. 시장가 매수 (5% 수량)
curl -X POST https://your-domain.com/api/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "group_name": "test_strategy",
    "exchange": "BINANCE",
    "market_type": "FUTURES",
    "currency": "USDT",
    "symbol": "BTCUSDT.P",
    "orderType": "MARKET",
    "side": "buy",
    "qty_per": 5
  }'

# 2. 지정가 매수 (5% 수량, 현재가보다 1% 낮은 가격)
curl -X POST https://your-domain.com/api/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "group_name": "test_strategy",
    "exchange": "BINANCE",
    "market_type": "FUTURES",
    "currency": "USDT", 
    "symbol": "BTCUSDT.P",
    "orderType": "LIMIT",
    "side": "buy",
    "price": 94000,
    "qty_per": 5
  }'

# 3. 시장가 매도 (포지션 전량)
curl -X POST https://your-domain.com/api/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "group_name": "test_strategy",
    "exchange": "BINANCE",
    "market_type": "FUTURES",
    "currency": "USDT",
    "symbol": "BTCUSDT.P",
    "orderType": "MARKET",
    "side": "sell",
    "qty_per": 100
  }'

# 4. 지정가 매도 (포지션 전량, 현재가보다 1% 높은 가격)
curl -X POST https://your-domain.com/api/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "group_name": "test_strategy",
    "exchange": "BINANCE",
    "market_type": "FUTURES",
    "currency": "USDT",
    "symbol": "BTCUSDT.P",
    "orderType": "LIMIT",
    "side": "sell",
    "price": 96000,
    "qty_per": 100
  }'

# 5. 전체 주문 취소
curl -X POST https://your-domain.com/api/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "group_name": "test_strategy",
    "orderType": "CANCEL_ALL_ORDER"
  }'

# 6. 특정 거래소 주문만 취소
curl -X POST https://your-domain.com/api/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "group_name": "test_strategy",
    "exchange": "BINANCE",
    "orderType": "CANCEL_ALL_ORDER"
  }'

# 7. 특정 심볼 주문만 취소
curl -X POST https://your-domain.com/api/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "group_name": "test_strategy",
    "symbol": "BTCUSDT",
    "orderType": "CANCEL_ALL_ORDER"
  }'

# 8. 복합 필터: 특정 거래소+마켓+심볼 주문 취소
curl -X POST https://your-domain.com/api/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "group_name": "test_strategy",
    "exchange": "BINANCE",
    "market_type": "FUTURES",
    "symbol": "BTCUSDT",
    "orderType": "CANCEL_ALL_ORDER"
  }'
```

#### Windows (Command Prompt)
```cmd
REM 1. 시장가 매수 (5% 수량)
curl -X POST https://your-domain.com/api/webhook ^
  -H "Content-Type: application/json" ^
  -d "{\"group_name\":\"test_strategy\",\"exchange\":\"BINANCE\",\"market\":\"FUTURE\",\"currency\":\"USDT\",\"symbol\":\"BTCUSDT.P\",\"orderType\":\"MARKET\",\"side\":\"buy\",\"qty_per\":5}"

REM 2. 지정가 매수 (5% 수량)
curl -X POST https://your-domain.com/api/webhook ^
  -H "Content-Type: application/json" ^
  -d "{\"group_name\":\"test_strategy\",\"exchange\":\"BINANCE\",\"market\":\"FUTURE\",\"currency\":\"USDT\",\"symbol\":\"BTCUSDT.P\",\"orderType\":\"LIMIT\",\"side\":\"buy\",\"price\":94000,\"qty_per\":5}"

REM 3. 시장가 매도 (포지션 전량)
curl -X POST https://your-domain.com/api/webhook ^
  -H "Content-Type: application/json" ^
  -d "{\"group_name\":\"test_strategy\",\"exchange\":\"BINANCE\",\"market\":\"FUTURE\",\"currency\":\"USDT\",\"symbol\":\"BTCUSDT.P\",\"orderType\":\"MARKET\",\"side\":\"sell\",\"qty_per\":100}"

REM 4. 지정가 매도 (포지션 전량)
curl -X POST https://your-domain.com/api/webhook ^
  -H "Content-Type: application/json" ^
  -d "{\"group_name\":\"test_strategy\",\"exchange\":\"BINANCE\",\"market\":\"FUTURE\",\"currency\":\"USDT\",\"symbol\":\"BTCUSDT.P\",\"orderType\":\"LIMIT\",\"side\":\"sell\",\"price\":96000,\"qty_per\":100}"

REM 5. 전체 주문 취소
curl -X POST https://your-domain.com/api/webhook ^
  -H "Content-Type: application/json" ^
  -d "{\"group_name\":\"test_strategy\",\"orderType\":\"CANCEL_ALL_ORDER\"}"
```

#### Windows (PowerShell)
```powershell
# 1. 시장가 매수 (5% 수량)
curl -X POST https://your-domain.com/api/webhook `
  -H "Content-Type: application/json" `
  -d '{"group_name":"test_strategy","exchange":"BINANCE","market":"FUTURE","currency":"USDT","symbol":"BTCUSDT.P","orderType":"MARKET","side":"buy","qty_per":5}'

# 2. 지정가 매수 (5% 수량)
curl -X POST https://your-domain.com/api/webhook `
  -H "Content-Type: application/json" `
  -d '{"group_name":"test_strategy","exchange":"BINANCE","market":"FUTURE","currency":"USDT","symbol":"BTCUSDT.P","orderType":"LIMIT","side":"buy","price":94000,"qty_per":5}'

# 3. 시장가 매도 (포지션 전량)
curl -X POST https://your-domain.com/api/webhook `
  -H "Content-Type: application/json" `
  -d '{"group_name":"test_strategy","exchange":"BINANCE","market":"FUTURE","currency":"USDT","symbol":"BTCUSDT.P","orderType":"MARKET","side":"sell","qty_per":100}'

# 4. 지정가 매도 (포지션 전량)
curl -X POST https://your-domain.com/api/webhook `
  -H "Content-Type: application/json" `
  -d '{"group_name":"test_strategy","exchange":"BINANCE","market":"FUTURE","currency":"USDT","symbol":"BTCUSDT.P","orderType":"LIMIT","side":"sell","price":96000,"qty_per":100}'

# 5. 전체 주문 취소
curl -X POST https://your-domain.com/api/webhook `
  -H "Content-Type: application/json" `
  -d '{"group_name":"test_strategy","orderType":"CANCEL_ALL_ORDER"}'
```

#### 파일을 사용한 테스트 (모든 OS 공통)
JSON 파일을 생성하여 더 쉽게 테스트할 수 있습니다:

**market_buy.json**
```json
{
  "group_name": "test_strategy",
  "exchange": "BINANCE",
  "market_type": "FUTURES",
  "currency": "USDT",
  "symbol": "BTCUSDT.P",
  "orderType": "MARKET",
  "side": "buy",
  "qty_per": 5
}
```

**limit_sell.json**
```json
{
  "group_name": "test_strategy",
  "exchange": "BINANCE",
  "market_type": "FUTURES",
  "currency": "USDT",
  "symbol": "BTCUSDT.P",
  "orderType": "LIMIT",
  "side": "sell",
  "price": 96000,
  "qty_per": 100
}
```

**파일 사용 명령어:**
```bash
# Linux/macOS/Windows
curl -X POST https://your-domain.com/api/webhook \
  -H "Content-Type: application/json" \
  -d @market_buy.json

curl -X POST https://your-domain.com/api/webhook \
  -H "Content-Type: application/json" \
  -d @limit_sell.json
```

### 2. Python 테스트 스크립트
```python
import requests

def test_webhook(data):
    url = "https://your-domain.com/api/webhook"
    headers = {"Content-Type": "application/json"}
    
    response = requests.post(url, headers=headers, json=data)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")

# 시장가 매수 테스트
test_webhook({
    "group_name": "test_strategy",
    "exchange": "BINANCE",
    "market_type": "SPOT",
    "currency": "USDT", 
    "symbol": "BTCUSDT",
    "orderType": "MARKET",
    "side": "buy"
})

# 필수 필드 누락 테스트 (오류 확인)
test_webhook({
    "group_name": "test_strategy",
    "symbol": "BTCUSDT",
    "side": "buy"
    # exchange, market, currency, orderType 누락
})
```

## 트러블슈팅

### 자주 발생하는 오류

#### 1. "필수 필드 누락: exchange"
- **원인**: 필수 필드가 누락됨
- **해결**: 모든 필수 필드 포함 확인
- **필수 필드**: `group_name`, `exchange`, `market`, `currency`, `symbol`, `orderType`, `side`

#### 2. "활성 전략을 찾을 수 없습니다"
- **원인**: `group_name`이 잘못되었거나 전략이 비활성화됨
- **해결**: 전략 관리에서 `group_name` 확인 및 전략 활성화

#### 3. "전략에 연결된 계좌가 없습니다"
- **원인**: 전략에 거래소 계좌가 연결되지 않음
- **해결**: 전략-계정 연결 메뉴에서 계좌 연결

#### 4. price 필드 관련 오류
- **원인**: `"limit:45000"` 같은 잘못된 형식 사용
- **해결**: 숫자만 사용 (예: `45000`, `3200.5`)

#### 5. "최대 심볼 수 제한으로 스킵된 주문"
- **원인**: 계정이 동시 거래 가능한 심볼 수 제한에 도달
- **해결**: 기존 포지션 정리 또는 계정별 최대 심볼 수 증가

### 로그 확인 방법
1. **서버 로그**: `logs/app.log` 파일 확인
2. **웹훅 로그**: 데이터베이스의 `webhook_logs` 테이블
3. **거래 내역**: 포지션 메뉴에서 실제 주문 실행 여부 확인

### 디버깅 팁
- **상세 로그**: 모든 웹훅 요청과 응답이 로그에 기록됩니다
- **병렬 처리**: 여러 계정에서 동시에 거래가 실행되므로 각 계정별 결과를 개별 확인
- **필드 표준화**: 대소문자나 필드명 변형은 자동으로 처리되므로 값 자체에 오류가 없는지 확인

## 보안 고려사항

### 1. 웹훅 URL 보호
- 웹훅 URL을 외부에 노출하지 마세요
- 가능하면 VPN이나 방화벽으로 접근 제한
- HTTPS 사용 필수

### 2. 입력값 검증
- 시스템이 기본적인 필드 검증을 하지만 신뢰할 수 있는 소스에서만 웹훅 수신
- 의심스러운 요청은 로그에서 모니터링

### 3. 계정 보안
- 거래소 API 키는 거래 권한만 부여 (출금 권한 제거)
- IP 화이트리스트 설정 권장
- 정기적인 API 키 교체

### 4. 모니터링
- 텔레그램 알림을 통한 실시간 거래 모니터링
- 예상치 못한 거래 발생 시 즉시 대응
- 웹훅 로그 정기 검토

## 추가 정보

### 관련 문서
- [프로젝트 개요](PROJECT_OVERVIEW.md)
- [API 문서](POSITIONS_AND_ORDERS_API.md)
- [설치 가이드](SETUP_GUIDE.md)

### 지원
- GitHub Issues: 문제 신고 및 기능 요청
- 로그 파일: 상세한 오류 분석을 위해 `logs/app.log` 첨부

---
*이 문서는 실제 코드 구현을 정확히 분석하여 작성되었습니다. 모든 예시와 설명은 실제 작동하는 코드를 기반으로 합니다.*