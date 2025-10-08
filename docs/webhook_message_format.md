# 웹훅 메시지 포맷 가이드

## 📋 목차
- [개요](#개요)
- [기본 구조](#기본-구조)
- [마켓별 심볼 포맷](#마켓별-심볼-포맷)
- [웹훅 예시 코드 (10개)](#웹훅-예시-코드-10개)
- [웹훅 시나리오 테스트 (45개)](#웹훅-시나리오-테스트-45개)
- [에러 메시지 명세](#에러-메시지-명세)
- [FAQ](#faq)
- [참고 사항](#참고-사항)

---

## 개요

### 웹훅 시스템 소개
본 웹훅 시스템은 **TradingView**, **자동 트레이딩 봇**, **외부 신호 제공자** 등에서 HTTP POST 요청을 통해 자동 매매를 실행할 수 있도록 설계된 통합 인터페이스입니다.

**웹훅 URL:**
```
https://your-domain.com/api/webhook
```

**지원하는 마켓 타입:**
- `SPOT`: 크립토 현물 거래 (Binance, Upbit 등)
- `FUTURES`: 크립토 선물 거래 (Binance Futures, Bybit 등)
- `DOMESTIC_STOCK`: 국내주식 (한국투자증권 등)
- `OVERSEAS_STOCK`: 해외주식 (미국, 일본, 중국 등)
- `DOMESTIC_FUTUREOPTION`: 국내선물옵션 (KOSPI200 선물/옵션 등)
- `OVERSEAS_FUTUREOPTION`: 해외선물옵션 (CME, Eurex 등)

### 주요 특징

#### 1. 통합 인터페이스
- **모든 마켓에서 동일한 필드명 사용**: `symbol`, `side`, `order_type`, `qty_per` 등
- **일관된 메시지 구조**: 크립토든 증권이든 동일한 JSON 구조
- **자동 타입 추론**: `market_type`과 `exchange`는 전략 설정에서 자동 결정
- **멀티 Exchange 지원**: 하나의 전략이 여러 거래소 계좌를 동시 사용 가능

#### 2. 전략 기반 라우팅 (Strategy-Based Routing)
```
웹훅 메시지 → group_name → Strategy 조회 → market_type, exchange 자동 결정 → 적절한 거래소 API 호출
```

**이점:**
- 웹훅 메시지 간소화 (필수 필드 최소화)
- 데이터 일관성 유지 (Single Source of Truth)
- 사용자 오입력 방지 (전략과 웹훅 불일치 차단)

#### 3. 멀티 Exchange 지원

웹훅 메시지에 `exchange` 필드를 지정하지 않습니다.
대신 Strategy에 연동된 **모든 계좌**에서 자동으로 주문이 실행됩니다.

**동작 방식:**
```
Strategy (전략)
  ↓ 연동 계좌 (StrategyAccount)
  ├─ Binance 계좌 → Binance에서 주문 실행
  ├─ Bybit 계좌 → Bybit에서 주문 실행
  └─ Upbit 계좌 → Upbit에서 주문 실행

웹훅 1개 → 연동된 모든 거래소에 동시 주문 ✅
```

**장점:**
- 여러 거래소에 동시 주문 가능
- 계좌 추가/제거만으로 거래소 변경 가능
- 웹훅 메시지 단순화

**주의사항:**
- Strategy에 같은 거래소 계좌가 2개 있으면 2번 주문됨
- 계좌 관리 시 중복 방지 필요

#### 4. 유연한 확장성
- **params 객체**: 마켓별 특수 파라미터 지원
- **배치 주문**: 여러 주문을 한 번에 실행
- **하위 호환성**: 기존 크립토 웹훅 100% 지원

---

## 기본 구조

### 필수 필드

| 필드명 | 타입 | 설명 | 예시 |
|--------|------|------|------|
| `group_name` | String | 전략 식별자 (전략 설정에서 market_type, exchange 자동 결정) | `"my_strategy"` |
| `token` | String | 웹훅 인증 토큰 (전략별 고유 토큰) | `"abc123..."` |
| `symbol` | String | 거래 심볼 (마켓별 형식 상이) | `"BTC/USDT"`, `"005930"` |
| `side` | String | 거래 방향 (`BUY`, `SELL`, `buy`, `sell`, `long`, `short` 허용) | `"BUY"` |
| `order_type` | String | 주문 타입 (`MARKET`, `LIMIT`, `STOP_LIMIT` 등) | `"LIMIT"` |
| `qty_per` | Number | 수량 비율 (%) 또는 절대 수량 | `10` (크립토), `100` (증권) |

### 선택적 필드

| 필드명 | 타입 | 설명 | 사용 시점 |
|--------|------|------|----------|
| `price` | Number | 지정가 (limit price) | `LIMIT`, `STOP_LIMIT` 주문 시 필수 |
| `stop_price` | Number | 스탑 가격 (stop trigger price) | `STOP_MARKET`, `STOP_LIMIT` 주문 시 필수 |
| `currency` | String | 기준 통화 (크립토 전용) | 크립토 거래 시 권장 (`USDT`, `KRW` 등) |
| `params` | Object | 마켓별 추가 파라미터 (증권/선물옵션용) | 해외주식, 선물옵션 특수 파라미터 |

### 금지된 필드 (Deprecated)

> ⚠️ **2025-10-07부터 제거됨 (Hard Break)**: 다음 필드들은 더 이상 사용할 수 없습니다.

- ❌ `exchange`: **완전히 제거됨** - Strategy 연동 모든 계좌에서 자동 주문 실행
- ❌ `market_type`: Strategy.market_type에서 자동 결정됨
- ❌ `platform`: `exchange`의 대체 필드명 (동일하게 금지)

> 💡 **중요**: `exchange` 필드는 더 이상 지원되지 않습니다. 웹훅 메시지는 거래소를 지정하지 않으며,
> Strategy에 연동된 **모든 계좌**에서 자동으로 주문이 실행됩니다. 이를 통해 멀티 exchange 동시 거래가 가능합니다.

**에러 예시:**
```json
{
  "error": "웹훅 메시지에 더 이상 사용되지 않는 필드가 포함되어 있습니다: market_type, exchange. 해당 필드들을 제거하세요. market_type은 전략 설정에서, exchange는 연동된 계좌에서 자동으로 결정됩니다."
}
```

### 필드별 상세 설명

#### `group_name` (전략 식별자)
- **역할**: 어떤 전략의 주문인지 식별
- **전략 설정 기반 자동 결정**:
  - `Strategy.market_type` → 마켓 타입 결정 (SPOT, FUTURES, DOMESTIC_STOCK 등)
  - `Strategy.strategy_accounts` → 연동된 계좌 조회
  - `Account.exchange` → 거래소 결정 (BINANCE, KIS 등)
- **보안**: 전략마다 고유한 `token`으로 보호

#### `symbol` (거래 심볼)
- **마켓별 형식 차이**:
  - 크립토: `BTC/USDT` (슬래시 필수, 엄격한 검증)
  - 증권: 다양한 형식 허용 (유연한 검증, 거래소 API에 최종 검증 위임)
- **자동 변환**: 시스템이 거래소별 형식으로 자동 변환
  - `BTC/USDT` → Binance: `BTCUSDT`, Upbit: `KRW-BTC`
- **상세 포맷**: [마켓별 심볼 포맷](#마켓별-심볼-포맷) 참고

#### `side` (거래 방향)
- **허용 값**:
  - `BUY`, `buy`, `long` → 매수 (롱 포지션 진입)
  - `SELL`, `sell`, `short` → 매도 (숏 포지션 진입 또는 청산)
- **자동 표준화**: 시스템이 대문자로 변환 (`BUY`, `SELL`)

#### `order_type` (주문 타입)
- **공통 주문 타입** (크립토 + 증권):
  - `MARKET`: 시장가 주문 (즉시 체결)
  - `LIMIT`: 지정가 주문 (price 필수)
  - `STOP_MARKET`: 스탑 마켓 주문 (stop_price 필수)
  - `STOP_LIMIT`: 스탑 리밋 주문 (price, stop_price 필수)
  - `CANCEL_ALL_ORDER`: 모든 미체결 주문 취소
- **증권 전용 주문 타입** (국내주식):
  - `CONDITIONAL_LIMIT`: 조건부 지정가 (한투)
  - `BEST_LIMIT`: 최유리 지정가 (한투)
  - `PRE_MARKET`: 시간외 단일가 (장전)
  - `AFTER_MARKET`: 시간외 종가 (장후)

#### `qty_per` (수량 비율 또는 절대 수량)
- **크립토**:
  - 양수: 계좌 자본의 N% 사용 (예: `10` = 10%)
  - `-100`: 현재 포지션 100% 청산 (롱/숏 자동 판단)
- **증권**:
  - 절대 수량 (주식 수) (예: `100` = 100주)
  - 단, 국내주식은 최소 1주 단위, 해외주식은 종목별 상이

#### `params` (확장 파라미터)
- **용도**: 마켓별 특수 파라미터 전달
- **구조**: JSON 객체 (key-value)
- **사용 예시**:
  - 해외주식: `"exchange_code": "NASD"`, `"currency": "USD"`
  - 국내선물옵션: `"position_action": "OPEN"`, `"option_type": "CALL"`
  - 해외선물옵션: `"contract_month": "Z4"`, `"exchange_timezone": "America/Chicago"`

---

## 마켓별 심볼 포맷

### 크립토 (엄격한 검증)

#### SPOT/FUTURES 마켓
- **표준 형식**: `COIN/CURRENCY` (슬래시 필수)
- **예시**:
  - ✅ `"BTC/USDT"` (Bitcoin / Tether)
  - ✅ `"ETH/USDT"` (Ethereum / Tether)
  - ✅ `"BTC/KRW"` (Bitcoin / Korean Won, Upbit)
  - ✅ `"SOL/USDT"` (Solana / Tether)
  - ❌ `"BTCUSDT"` (슬래시 누락 - 에러 발생, 자동 교정 제안)
  - ❌ `"KRW-BTC"` (Upbit 형식 - 에러 발생, 자동 교정 제안)

**검증 로직**:
- 슬래시(`/`) 포함 여부 확인
- `COIN/CURRENCY` 구조 검증
- 공백 및 특수문자 제거
- 잘못된 형식 → 자동 교정 제안 (예: `BTCUSDT` → `BTC/USDT`)

**에러 메시지 예시**:
```json
{
  "error": "잘못된 심볼 포맷입니다: 'BTCUSDT'. 올바른 형식: 'BTC/USDT' (COIN/CURRENCY 형식 사용)"
}
```

---

### 증권 (유연한 검증)

> 증권 심볼은 거래소마다 다양한 형식을 사용하므로, 기본적인 **안전성 검증**만 수행하고 **거래소 API에서 최종 검증**합니다.

#### 검증 규칙 (공통)
- **허용 문자**: 영문(A-Z), 숫자(0-9), 마침표(`.`), 하이픈(`-`), 언더스코어(`_`)
- **최대 길이**: 30자 (ReDoS 공격 방지)
- **금지 사항**: SQL Injection, XSS 공격 패턴 차단 (예: `'; DROP TABLE--`)

#### 국내주식 (DOMESTIC_STOCK)
- **형식**: 6자리 숫자 또는 국가코드 포함
- **예시**: `"005930"` (삼성전자), `"KR005930"`, `"123456A"` (ETN), `"Q500001"` (ETF)

#### 해외주식 (OVERSEAS_STOCK)
- **형식**: 티커 심볼 (영문 또는 숫자)
- **예시**: `"AAPL"` (Apple), `"BRK.A"`, `"BRK.B"`, `"9988"` (Alibaba, HKEX), `"0700"` (Tencent)

#### 국내선물옵션 (DOMESTIC_FUTUREOPTION)
- **형식**: 종목코드 (8자리 영숫자)
- **예시**: `"101TC000"` (KOSPI200 선물), `"KR4101C3000"`, `"201PC260"` (KOSPI200 풋옵션)

#### 해외선물옵션 (OVERSEAS_FUTUREOPTION)
- **형식**: 월물 코드 포함 (거래소별 상이)
- **예시**: `"ESZ4"` (E-mini S&P 500, Dec 2024), `"NQH5"` (E-mini NASDAQ, Mar 2025), `"CL-DEC24"` (Crude Oil)

---

## 웹훅 예시 코드 (10개)

### 1. 크립토 SPOT 시장가 매수 (기본 예시)
```json
{
  "group_name": "my_strategy",
  "currency": "USDT",
  "symbol": "BTC/USDT",
  "order_type": "MARKET",
  "side": "buy",
  "qty_per": 10,
  "token": "your_webhook_token"
}
```
**설명**: Binance SPOT 마켓에서 계좌 자본의 10%로 BTC 시장가 매수

---

### 2. 크립토 SPOT 지정가 매도
```json
{
  "group_name": "my_strategy",
  "currency": "USDT",
  "symbol": "BTC/USDT",
  "order_type": "LIMIT",
  "side": "sell",
  "price": "130000",
  "qty_per": 10,
  "token": "your_webhook_token"
}
```
**설명**: BTC를 $130,000에 지정가 매도 주문 (익절 목표가)

---

### 3. 크립토 FUTURES STOP_LIMIT 주문
```json
{
  "group_name": "futures_strategy",
  "currency": "USDT",
  "symbol": "BTC/USDT",
  "order_type": "STOP_LIMIT",
  "side": "sell",
  "price": "94000",
  "stop_price": "95000",
  "qty_per": 10,
  "token": "your_webhook_token"
}
```
**설명**: BTC 가격이 $95,000 이하로 떨어지면 $94,000에 지정가 매도 주문 생성 (손절)

---

### 4. 크립토 포지션 100% 청산 (qty_per=-100)
```json
{
  "group_name": "futures_strategy",
  "currency": "USDT",
  "symbol": "BTC/USDT",
  "order_type": "MARKET",
  "side": "sell",
  "qty_per": -100,
  "token": "your_webhook_token"
}
```
**설명**: BTC 롱 포지션 100% 시장가 청산 (롱/숏 자동 판단)

---

### 5. 크립토 모든 주문 취소
```json
{
  "group_name": "my_strategy",
  "currency": "USDT",
  "symbol": "BTC/USDT",
  "order_type": "CANCEL_ALL_ORDER",
  "token": "your_webhook_token"
}
```
**설명**: BTC/USDT 심볼의 모든 미체결 주문 취소 (다른 심볼은 유지)

---

### 6. 국내주식 LIMIT 주문
```json
{
  "group_name": "kospi_strategy",
  "symbol": "005930",
  "order_type": "LIMIT",
  "side": "buy",
  "price": "70000",
  "qty_per": 100,
  "token": "your_webhook_token"
}
```
**설명**: 삼성전자(005930) 70,000원에 지정가 매수 100주

---

### 7. 해외주식 MARKET 주문 (params 사용)
```json
{
  "group_name": "nasdaq_strategy",
  "symbol": "AAPL",
  "order_type": "MARKET",
  "side": "buy",
  "qty_per": 10,
  "token": "your_webhook_token",
  "params": {
    "exchange_code": "NASD",
    "currency": "USD"
  }
}
```
**설명**: Apple(AAPL) 10주 시장가 매수 (NASDAQ, USD)

---

### 8. 국내선물옵션 LIMIT 주문 (params 사용)
```json
{
  "group_name": "kfutures_strategy",
  "symbol": "101TC000",
  "order_type": "LIMIT",
  "side": "buy",
  "price": "320.50",
  "qty_per": 2,
  "token": "your_webhook_token",
  "params": {
    "position_action": "OPEN"
  }
}
```
**설명**: KOSPI200 선물 320.50pt에 지정가 매수 2계약 (신규 진입)

---

### 9. 해외선물옵션 MARKET 주문 (params 사용)
```json
{
  "group_name": "cme_strategy",
  "symbol": "ESZ4",
  "order_type": "MARKET",
  "side": "buy",
  "qty_per": 1,
  "token": "your_webhook_token",
  "params": {
    "exchange_code": "CME",
    "contract_month": "Z4",
    "currency": "USD"
  }
}
```
**설명**: E-mini S&P 500 (December 2024) 1계약 시장가 매수 (CME)

---

### 10. 배치 주문 예시 (orders 배열)

> ⚠️ **Breaking Change (2025-10-08)**: 배치 주문 포맷이 변경되었습니다.
> - 공통 필드를 상위 레벨로 이동 (`symbol`, `currency`, `token`, `group_name`)
> - 각 주문의 `order_type` 필수
> - 자동 우선순위 정렬 (MARKET > CANCEL > LIMIT > STOP)

#### 새로운 배치 주문 구조
- **상위 레벨**: 모든 주문에 공통으로 적용되는 필드
  - `group_name`: 전략 식별자 (필수)
  - `symbol`: 거래 심볼 (필수)
  - `currency`: 기준 통화 (크립토 권장)
  - `token`: 웹훅 인증 토큰 (필수)
- **orders 배열**: 개별 주문 정의
  - `order_type`: 주문 타입 (필수)
  - `side`: 거래 방향 (선택적, CANCEL 제외 필수)
  - `price`: 지정가 (선택적, LIMIT 타입 시 필수)
  - `qty_per`: 수량 비율 (선택적, CANCEL 제외 필수)
  - `stop_price`: 스탑 가격 (선택적, STOP 타입 시 필수)
  - `params`: 마켓별 추가 파라미터 (선택적)

#### 배치 주문 처리 순서
배치 주문은 다음 우선순위로 자동 정렬됩니다:
1. **MARKET** - 시장가 주문 (우선순위 1, 최우선)
2. **CANCEL, CANCEL_ALL_ORDER** - 주문 취소 (우선순위 2)
3. **LIMIT, BEST_LIMIT, PRE_MARKET, AFTER_MARKET** - 지정가 주문 (우선순위 3)
4. **STOP_MARKET** - 스탑 시장가 (우선순위 4)
5. **STOP_LIMIT** - 스탑 지정가 (우선순위 5)
6. **CONDITIONAL_LIMIT** - 조건부 지정가 (우선순위 6)

**처리 방식:**
- 사용자가 전송한 순서와 관계없이 위 우선순위에 따라 자동 정렬
- 같은 우선순위 내에서는 전송 순서 유지
- 예: LIMIT → MARKET → CANCEL 순서로 전송해도, MARKET → CANCEL → LIMIT 순으로 처리

#### 기본 예시 (동일 심볼)
```json
{
  "group_name": "multi_order_strategy",
  "symbol": "BTC/USDT",
  "currency": "USDT",
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
**설명**:
- BTC/USDT의 모든 기존 주문 취소
- $105,000에 매수 지정가 주문 (5% 자본 사용)
- $104,000에 매수 지정가 주문 (10% 자본 사용)
- 처리 순서: CANCEL_ALL_ORDER → LIMIT (105000) → LIMIT (104000)

#### 확장 예시 (8개 LIMIT 주문)
```json
{
  "group_name": "ladder_strategy",
  "symbol": "BTC/USDT",
  "currency": "USDT",
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
      "qty_per": 5
    },
    {
      "side": "buy",
      "order_type": "LIMIT",
      "price": "103000",
      "qty_per": 5
    },
    {
      "side": "buy",
      "order_type": "LIMIT",
      "price": "102000",
      "qty_per": 5
    },
    {
      "side": "sell",
      "order_type": "LIMIT",
      "price": "108000",
      "qty_per": 5
    },
    {
      "side": "sell",
      "order_type": "LIMIT",
      "price": "109000",
      "qty_per": 5
    },
    {
      "side": "sell",
      "order_type": "LIMIT",
      "price": "110000",
      "qty_per": 5
    },
    {
      "side": "sell",
      "order_type": "LIMIT",
      "price": "111000",
      "qty_per": 5
    }
  ]
}
```
**설명**:
- 기존 주문 취소 후 양방향 사다리 주문 생성
- 매수: $102k ~ $105k (4단계)
- 매도: $108k ~ $111k (4단계)
- 각 주문마다 5% 자본 사용

#### 우선순위 혼합 예시
```json
{
  "group_name": "complex_strategy",
  "symbol": "BTC/USDT",
  "currency": "USDT",
  "token": "your_webhook_token",
  "orders": [
    {
      "side": "buy",
      "order_type": "LIMIT",
      "price": "105000",
      "qty_per": 10
    },
    {
      "side": "buy",
      "order_type": "MARKET",
      "qty_per": 5
    },
    {
      "order_type": "CANCEL_ALL_ORDER"
    },
    {
      "side": "sell",
      "order_type": "STOP_LIMIT",
      "price": "94000",
      "stop_price": "95000",
      "qty_per": 10
    }
  ]
}
```
**실제 처리 순서:**
1. MARKET buy (우선순위 1) - 즉시 5% 매수 체결
2. CANCEL_ALL_ORDER (우선순위 2) - 기존 주문 취소
3. LIMIT buy at 105000 (우선순위 3) - 지정가 매수 주문
4. STOP_LIMIT sell (우선순위 5) - 손절 주문

**참고:** 전송 순서 (LIMIT → MARKET → CANCEL → STOP_LIMIT)와 무관하게 우선순위대로 처리

#### 기존 포맷 (Deprecated)
```json
{
  "group_name": "old_format",
  "currency": "USDT",
  "token": "...",
  "orders": [
    {
      "symbol": "BTC/USDT",  // ❌ 개별 주문에 symbol (더 이상 지원 안함)
      "side": "buy",
      "order_type": "MARKET",
      "qty_per": 10
    }
  ]
}
```
**경고:** 이 형식은 더 이상 지원되지 않습니다. 공통 필드는 상위 레벨로 이동해야 합니다.

---

## 웹훅 시나리오 테스트 (45개)

### 크립토 거래 시나리오 (15개)

1. **BTC/USDT SPOT market buy** - qty_per=10, currency=USDT
2. **ETH/USDT SPOT market sell** - qty_per=5, currency=USDT
3. **BTC/USDT SPOT limit buy** - price=90000, qty_per=10, currency=USDT
4. **ETH/USDT SPOT limit sell** - price=3500, qty_per=20, currency=USDT
5. **BTC/USDT SPOT stop_market sell** - stop_price=95000, qty_per=10, currency=USDT
6. **BTC/USDT FUTURES market long** - qty_per=20, currency=USDT
7. **ETH/USDT FUTURES market short** - qty_per=15, currency=USDT
8. **BTC/USDT FUTURES limit long** - price=92000, qty_per=20, currency=USDT
9. **BTC/USDT FUTURES limit short** - price=105000, qty_per=15, currency=USDT
10. **BTC/USDT FUTURES stop_market long close** - stop_price=90000, qty_per=20, side=sell, currency=USDT
11. **BTC/USDT FUTURES stop_market short close** - stop_price=105000, qty_per=15, side=buy, currency=USDT
12. **BTC/USDT FUTURES position 100% close** - qty_per=-100, side=sell, order_type=MARKET, currency=USDT
13. **BTC/KRW Upbit market buy** - qty_per=10, currency=KRW
14. **ETH/USDT cancel specific symbol** - order_type=CANCEL_ALL_ORDER, symbol=ETH/USDT
15. **All symbols cancel** - order_type=CANCEL_ALL_ORDER (symbol 생략)

---

### 국내주식 거래 시나리오 (10개)

1. **005930 (삼성전자) market buy** - qty=100, order_type=MARKET, side=buy
2. **005930 (삼성전자) market sell** - qty=50, order_type=MARKET, side=sell
3. **005930 (삼성전자) limit buy** - price=70000, qty=100, order_type=LIMIT, side=buy
4. **005930 (삼성전자) limit sell** - price=75000, qty=100, order_type=LIMIT, side=sell
5. **005930 conditional_limit buy** - price=72000, qty=100, order_type=CONDITIONAL_LIMIT, side=buy
6. **005930 best_limit buy** - qty=100, order_type=BEST_LIMIT, side=buy
7. **005930 pre_market buy** - price=71000, qty=100, order_type=PRE_MARKET, side=buy
8. **005930 after_market sell** - price=73000, qty=100, order_type=AFTER_MARKET, side=sell
9. **069500 (KODEX 200 ETF) market buy** - qty=50, order_type=MARKET, side=buy
10. **000660 (SK하이닉스) limit sell** - price=140000, qty=20, order_type=LIMIT, side=sell

---

### 해외주식 거래 시나리오 (10개)

1. **AAPL market buy** - qty=10, params={exchange_code:NASD, currency:USD}
2. **TSLA limit buy** - price=250.50, qty=5, params={exchange_code:NYSE, currency:USD}
3. **MSFT market sell** - qty=8, params={exchange_code:NASD, currency:USD}
4. **BRK.B limit sell** - price=420.00, qty=3, params={exchange_code:NYSE, currency:USD}
5. **NVDA stop_limit sell** - price=480.00, stop_price=485.00, qty=5, params={exchange_code:NASD, currency:USD}
6. **9988 (Alibaba HKEX) market buy** - qty=20, params={exchange_code:SEHK, currency:HKD}
7. **7203 (Toyota TSE) market buy** - qty=100, params={exchange_code:TSE, currency:JPY}
8. **VNM (Vinamilk) limit buy** - price=85000, qty=50, params={exchange_code:HCM, currency:VND}
9. **SAP (Frankfurt) market buy** - qty=5, params={exchange_code:XETRA, currency:EUR}
10. **BP (LSE) limit buy** - price=5.50, qty=100, params={exchange_code:LSE, currency:GBP}

---

### 국내선물옵션 시나리오 (5개)

1. **101TC000 (KOSPI200 선물) market buy** - qty=1, params={position_action:OPEN}
2. **101TC000 limit buy** - price=320.50, qty=2, params={position_action:OPEN}
3. **101TC000 market sell close** - qty=2, side=sell, params={position_action:CLOSE}
4. **201PC260 (KOSPI200 풋옵션) limit buy** - price=5.00, qty=10, params={option_type:PUT, strike_price:260.00}
5. **201CA320 (KOSPI200 콜옵션) market sell** - qty=5, params={option_type:CALL, strike_price:320.00}

---

### 해외선물옵션 시나리오 (5개)

1. **ESZ4 (E-mini S&P 500) market buy** - qty=1, params={exchange_code:CME, contract_month:Z4, currency:USD}
2. **NQH5 (E-mini NASDAQ) limit buy** - price=16500.00, qty=1, params={exchange_code:CME, contract_month:H5, currency:USD}
3. **CL-DEC24 (WTI Crude Oil) market buy** - qty=1, params={exchange_code:NYMEX, contract_month:DEC24, currency:USD}
4. **GCZ24 (Gold) limit buy** - price=2050.00, qty=1, params={exchange_code:COMEX, contract_month:Z4, currency:USD}
5. **6E_Z4 (Euro FX) market sell** - qty=1, params={exchange_code:CME, contract_month:Z4, currency:USD}

---

## 에러 메시지 명세

### 1. 웹훅 검증 에러

#### 토큰 검증 실패
```json
{
  "error": "웹훅 토큰이 유효하지 않습니다",
  "status": 401
}
```
**원인**: 잘못된 token 또는 전략과 token 불일치
**해결**: 전략 설정에서 올바른 token 확인

#### 토큰 누락
```json
{
  "error": "웹훅 토큰이 필요합니다",
  "status": 400
}
```
**원인**: token 필드 누락
**해결**: 웹훅 메시지에 token 추가

#### 전략 없음
```json
{
  "error": "전략을 찾을 수 없습니다: unknown_strategy",
  "status": 404
}
```
**원인**: group_name에 해당하는 전략이 DB에 없음
**해결**: 웹 UI에서 전략 생성 또는 group_name 수정

---

### 2. 심볼 포맷 에러

#### 크립토 심볼 슬래시 누락
```json
{
  "error": "잘못된 심볼 포맷입니다: 'BTCUSDT'. 올바른 형식: 'BTC/USDT' (COIN/CURRENCY 형식 사용)",
  "status": 400
}
```
**원인**: 크립토 심볼에 슬래시(`/`) 누락
**해결**: `BTCUSDT` → `BTC/USDT`

#### 증권 심볼 포맷 오류
```json
{
  "error": "국내주식 심볼 형식이 올바르지 않습니다 (예: 005930, KR005930, 123456A). 영문, 숫자, 마침표(.), 하이픈(-), 언더스코어(_)만 사용 가능합니다.",
  "status": 400
}
```
**원인**: 금지된 특수문자 사용 또는 심볼 길이 초과
**해결**: 허용된 문자만 사용 (영문, 숫자, `.`, `-`, `_`)

---

### 3. 필수 파라미터 누락

#### LIMIT 주문에 price 누락
```json
{
  "error": "LIMIT 주문에는 price가 필수입니다",
  "status": 400
}
```
**원인**: order_type=LIMIT인데 price 필드 없음
**해결**: price 필드 추가

#### STOP_LIMIT 주문에 stop_price 누락
```json
{
  "error": "STOP_LIMIT 주문에는 stop_price가 필수입니다",
  "status": 400
}
```
**원인**: order_type=STOP_LIMIT인데 stop_price 필드 없음
**해결**: stop_price 및 price 필드 추가

#### STOP_MARKET 주문에 stop_price 누락
```json
{
  "error": "STOP_MARKET 주문에는 stop_price가 필수입니다",
  "status": 400
}
```
**원인**: order_type=STOP_MARKET인데 stop_price 필드 없음
**해결**: stop_price 필드 추가

---

### 4. 금지된 필드 사용 에러 (Hard Break)

#### market_type, exchange 사용 시도
```json
{
  "error": "웹훅 메시지에 더 이상 사용되지 않는 필드가 포함되어 있습니다: market_type, exchange. 해당 필드들을 제거하세요. market_type은 전략 설정에서, exchange는 연동된 계좌에서 자동으로 결정됩니다.",
  "status": 400
}
```
**원인**: 2025-10-07부터 제거된 필드 사용
**해결**: market_type, exchange 필드 제거 (group_name만으로 자동 결정)

---

### 5. 거래소 API 에러

#### Binance STOP 주문 가격 규칙 위반
```json
{
  "error": "Binance API 오류: stop price must be above current price for buy orders",
  "status": 500
}
```
**원인**: 매수 STOP_LIMIT 주문에서 stop_price가 현재가보다 낮음
**해결**: stop_price를 현재가보다 높게 설정

#### 한투 주문 시간 제한
```json
{
  "error": "한투 API 오류: 장중에만 시장가 주문이 가능합니다 (09:00-15:30)",
  "status": 500
}
```
**원인**: 장 시간 외 MARKET 주문 시도
**해결**: 장중 시간에 재시도 또는 PRE_MARKET/AFTER_MARKET 사용

#### 한투 종목 거래 정지
```json
{
  "error": "한투 API 오류: 해당 종목은 거래가 정지되었습니다",
  "status": 500
}
```
**원인**: 상장폐지, 정리매매, 거래정지 종목
**해결**: 정상 거래 가능한 종목으로 변경

---

### 6. 포지션 청산 에러

#### 청산할 포지션 없음 (qty_per=-100)
```json
{
  "error": "청산할 롱 포지션이 없습니다",
  "status": 400
}
```
**원인**: qty_per=-100 사용했지만 해당 심볼 포지션 없음
**해결**: 포지션 보유 확인 또는 일반 매도 주문 사용

---

### 7. 주문 취소 에러

#### 취소할 주문 없음
```json
{
  "success": true,
  "message": "취소할 미체결 주문이 없습니다",
  "cancelled_orders": 0
}
```
**설명**: 에러가 아닌 정상 응답 (이미 모든 주문 체결/취소됨)

---

### 8. 배치 주문 에러

#### 배치 주문 내 심볼 포맷 오류
```json
{
  "error": "배치 주문 2번째 심볼 포맷 오류: 'ETHUSDT'. 올바른 형식: 'ETH/USDT' (COIN/CURRENCY 형식 사용)",
  "status": 400
}
```
**원인**: orders 배열 내 2번째 주문의 심볼 포맷 오류
**해결**: 해당 주문의 심볼을 표준 형식으로 수정

---

### 9. 계좌 연동 에러

#### 전략에 연동된 계좌 없음
```json
{
  "error": "전략에 연동된 계좌가 없습니다",
  "status": 400
}
```
**원인**: Strategy.strategy_accounts가 비어있음
**해결**: 웹 UI에서 계좌 연동

#### 증권 계좌 토큰 만료
```json
{
  "error": "한투 access token이 만료되었습니다. 재인증이 필요합니다.",
  "status": 401
}
```
**원인**: OAuth token 만료 (유효기간 24시간)
**해결**: 웹 UI에서 한투 재인증 (자동 갱신 실패 시)

---

### 10. 파라미터 검증 에러

#### MARKET 주문에 price 포함 (경고)
```json
{
  "warning": "MARKET 주문에서 price는 무시됩니다",
  "order_id": "12345..."
}
```
**설명**: 에러가 아닌 경고 (주문은 정상 실행, price 무시됨)

---

## FAQ

### Q1: market_type과 exchange를 왜 웹훅에서 제거했나요?

**A**: 데이터 일관성과 사용자 편의성을 위해 제거했습니다.

**이전 방식 (Deprecated)**:
```json
{
  "group_name": "my_strategy",
  "exchange": "BINANCE",      // 사용자가 직접 입력
  "market_type": "FUTURES",   // 사용자가 직접 입력
  "symbol": "BTC/USDT",
  ...
}
```

**문제점**:
- 전략 설정과 웹훅 메시지가 불일치할 수 있음
- 사용자 오입력 발생 (SPOT 전략인데 FUTURES 입력)
- 데이터 중복 (전략 DB에도 저장, 웹훅에도 전달)

**현재 방식 (2025-10-07 이후)**:
```json
{
  "group_name": "my_strategy",  // 전략만 지정
  "symbol": "BTC/USDT",
  ...
}
```

**이점**:
- Single Source of Truth: Strategy 테이블이 유일한 정보원
- 오입력 방지: 전략 설정과 자동 일치
- 간소화: 필수 필드 감소

---

### Q2: currency 필드는 언제 필요한가요?

**A**: 크립토 거래 시 권장하며, 증권 거래 시 params에 포함 가능합니다.

**크립토 (권장)**:
```json
{
  "group_name": "binance_spot",
  "currency": "USDT",  // 기준 통화
  "symbol": "BTC/USDT",
  ...
}
```

**증권 (params 사용)**:
```json
{
  "group_name": "nasdaq_strategy",
  "symbol": "AAPL",
  "params": {
    "currency": "USD"  // params 내부
  },
  ...
}
```

**생략 가능한 경우**:
- 전략 설정에 기본 통화 지정된 경우
- 단일 통화만 사용하는 거래소 (예: Upbit KRW)

---

### Q3: 심볼 포맷이 틀리면 어떻게 되나요?

**A**: 마켓 타입에 따라 다르게 처리됩니다.

**크립토 (엄격한 검증)**:
- 에러 발생 + 자동 교정 제안
- 예: `BTCUSDT` → `"올바른 형식: 'BTC/USDT'"`

**증권 (유연한 검증)**:
- 기본 안전성 검증만 수행
- 거래소 API에서 최종 검증
- 잘못된 심볼 → 거래소 API 에러 반환

---

### Q4: qty_per=-100은 어떻게 작동하나요?

**A**: 현재 포지션을 100% 청산하는 특수 값입니다.

**롱 포지션 청산**:
```json
{
  "symbol": "BTC/USDT",
  "side": "sell",
  "qty_per": -100  // 전체 롱 포지션 매도
}
```

**숏 포지션 청산**:
```json
{
  "symbol": "BTC/USDT",
  "side": "buy",
  "qty_per": -100  // 전체 숏 포지션 커버
}
```

**자동 판단**:
- 시스템이 현재 포지션 방향 자동 인식
- 포지션 수량 자동 계산 (qty_per=-100 → 실제 수량 변환)

**포지션 없을 때**:
- 에러 발생: `"청산할 롱 포지션이 없습니다"`

---

### Q5: 배치 주문은 어떻게 사용하나요?

**A**: orders 배열에 여러 주문을 담아 한 번에 전송합니다.

**새로운 포맷 (2025-10-08 이후):**
```json
{
  "group_name": "multi_order_strategy",
  "symbol": "BTC/USDT",
  "currency": "USDT",
  "token": "...",
  "orders": [
    {"order_type": "CANCEL_ALL_ORDER"},
    {"side": "buy", "order_type": "LIMIT", "price": "105000", "qty_per": 5},
    {"side": "buy", "order_type": "LIMIT", "price": "104000", "qty_per": 10}
  ]
}
```

**주요 변경사항:**
- ✅ 공통 필드 (`symbol`, `currency`) 상위 레벨로 이동
- ✅ 각 주문의 `order_type` 필수
- ✅ 자동 우선순위 정렬 (MARKET > CANCEL > LIMIT > STOP)

**이점**:
- 한 번의 HTTP 요청으로 다중 주문
- 포트폴리오 리밸런싱 편리
- OCO 주문 (익절+손절) 동시 설정 가능
- 사다리 주문 (ladder order) 간편 설정
- 우선순위 자동 정렬로 안전한 실행 순서 보장

---

### Q6: STOP 주문 타입은 어떻게 사용하나요?

**A**: stop_price를 트리거 가격으로 사용합니다.

**STOP_MARKET (손절 매도)**:
```json
{
  "order_type": "STOP_MARKET",
  "side": "sell",
  "stop_price": "95000"  // $95k 이하 떨어지면 시장가 매도
}
```

**STOP_LIMIT (지정가 손절)**:
```json
{
  "order_type": "STOP_LIMIT",
  "side": "sell",
  "price": "94000",      // 매도 지정가
  "stop_price": "95000"  // $95k 이하 떨어지면 $94k 지정가 주문 생성
}
```

**주의사항**:
- 매수 STOP: stop_price > 현재가 (상향 돌파 시 매수)
- 매도 STOP: stop_price < 현재가 (하향 돌파 시 매도)

---

### Q7: params 객체는 언제 사용하나요?

**A**: 마켓별 특수 파라미터가 필요할 때 사용합니다.

**해외주식 (거래소 코드)**:
```json
{
  "symbol": "AAPL",
  "params": {
    "exchange_code": "NASD",  // NASDAQ
    "currency": "USD"
  }
}
```

**국내선물옵션 (신규/청산 구분)**:
```json
{
  "symbol": "101TC000",
  "params": {
    "position_action": "OPEN"  // 신규 진입
  }
}
```

**해외선물옵션 (월물 코드)**:
```json
{
  "symbol": "ESZ4",
  "params": {
    "contract_month": "Z4",  // December 2024
    "exchange_code": "CME"
  }
}
```

---

### Q8: 증권 주문은 크립토와 어떻게 다른가요?

**A**: 주요 차이점은 다음과 같습니다.

| 항목 | 크립토 | 증권 |
|------|--------|------|
| **qty_per** | % 비율 (10 = 10%) | 절대 수량 (100 = 100주) |
| **심볼 검증** | 엄격 (슬래시 필수) | 유연 (거래소 API 위임) |
| **주문 타입** | MARKET, LIMIT, STOP | + CONDITIONAL_LIMIT, BEST_LIMIT 등 |
| **거래 시간** | 24/7 | 장중 시간 제한 (09:00-15:30 등) |
| **params** | currency 주로 사용 | exchange_code, currency 등 |

---

### Q9: 한투 주문 타입 코드는 어떻게 매핑되나요?

**A**: 시스템이 자동으로 변환합니다.

| 웹훅 order_type | 한투 국내주식 코드 | 한투 해외주식 코드 |
|-----------------|-------------------|-------------------|
| MARKET | '01' (시장가) | '01' |
| LIMIT | '00' (지정가) | '00' |
| CONDITIONAL_LIMIT | '02' (조건부지정가) | - |
| BEST_LIMIT | '03' (최유리지정가) | - |
| PRE_MARKET | '05' (시간외단일가) | - |
| AFTER_MARKET | '06' (시간외종가) | - |

**사용 예시**:
```json
{
  "symbol": "005930",
  "order_type": "BEST_LIMIT",  // 자동 변환 → '03'
  "side": "buy",
  "qty_per": 100
}
```

---

### Q10: 하위 호환성은 어떻게 유지되나요?

**A**: 기존 크립토 웹훅은 100% 지원됩니다.

**기존 방식 (여전히 작동)**:
```json
{
  "group_name": "old_strategy",
  "currency": "USDT",
  "symbol": "BTC/USDT",
  "order_type": "MARKET",
  "side": "buy",
  "qty_per": 10,
  "token": "..."
}
```

**권장하지 않는 필드 (무시됨, 경고 없음)**:
- `exchange`: 무시 (Account.exchange 사용)
- `market_type`: 무시 (Strategy.market_type 사용)

**2025-10-07 이후 Hard Break**:
- 위 필드 사용 시 에러 발생
- 제거 필요

---

## 참고 사항

### 보안 주의사항

#### 1. Token 노출 방지
- ⚠️ **절대 GitHub, Slack 등에 token 공유 금지**
- 환경 변수 사용 권장 (예: `TOKEN=${WEBHOOK_TOKEN}`)
- TradingView 알림 설정 시 URL에 token 직접 포함하지 말 것

**안전한 방법**:
```json
{
  "token": "{{env.WEBHOOK_TOKEN}}"
}
```

#### 2. HTTPS 사용 필수
- HTTP 사용 시 token 평문 노출
- 프로덕션 환경에서 반드시 HTTPS 인증서 설정

#### 3. IP 화이트리스트 (선택사항)
- 특정 IP만 웹훅 허용 (예: TradingView IP 대역)
- Cloudflare WAF 활용

---

### 테스트 방법

#### 1. curl 테스트
```bash
curl -k -s -X POST https://your-domain.com/api/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "group_name": "test_strategy",
    "currency": "USDT",
    "symbol": "BTC/USDT",
    "order_type": "LIMIT",
    "side": "buy",
    "price": "90000",
    "qty_per": 5,
    "token": "your_test_token"
  }' | python -m json.tool
```

#### 2. Postman 테스트
- Method: `POST`
- URL: `https://your-domain.com/api/webhook`
- Headers: `Content-Type: application/json`
- Body: Raw JSON

#### 3. TradingView 테스트
- 알림 설정 → 웹훅 URL 입력
- 테스트 알림 전송 (가격 조건 임시 설정)
- 로그 확인: `/web_server/logs/app.log`

---

### 로그 확인 방법

#### 실시간 로그 모니터링
```bash
tail -f /Users/binee/Desktop/quant/webserver/web_server/logs/app.log
```

#### 웹훅 수신 확인
```
[INFO] 웹훅 수신: {'group_name': 'my_strategy', 'symbol': 'BTC/USDT', ...}
```

#### 주문 생성 확인
```
[INFO] Binance SPOT 주문 생성 성공: order_id=12345...
```

#### 에러 확인
```
[ERROR] 웹훅 처리 실패: 잘못된 심볼 포맷입니다: 'BTCUSDT'
```

---

### 관련 문서 링크

- **CLAUDE.md**: 프로젝트 개발 가이드라인
  - 경로: `/Users/binee/Desktop/quant/webserver/CLAUDE.md`
  - 내용: RCE 예방, 데이터 구조 일관성, 웹훅 테스트 시나리오

- **task_plan.md**: 통합 웹훅 구현 계획
  - 경로: `/Users/binee/Desktop/quant/webserver/docs/task_plan.md`
  - 내용: Phase별 작업 내역, 설계 원칙, 마이그레이션 가이드

- **README.md**: 프로젝트 전체 문서
  - 경로: `/Users/binee/Desktop/quant/webserver/README.md`
  - 내용: 시스템 아키텍처, API 명세, 설치 가이드

---

### 개발자 연락처

- **프로젝트**: Quant Trading System
- **버전**: 2.0 (통합 웹훅 지원)
- **최종 업데이트**: 2025-10-07
- **문의**: 시스템 관리자에게 문의

---

## 변경 이력

### 2025-10-08
- **Breaking Change**: `exchange` 필드 완전 제거
  - Strategy 연동 모든 계좌에서 자동 주문 실행
  - 멀티 exchange 지원 (Binance + Bybit + Upbit 동시 사용 가능)
- **Breaking Change**: 배치 주문 포맷 변경
  - 공통 필드를 상위 레벨로 이동 (`symbol`, `currency`, `token`, `group_name`)
  - 각 주문의 `order_type` 필수화
  - 자동 우선순위 정렬 도입 (MARKET > CANCEL > LIMIT > STOP)
- **문서**: 배치 주문 섹션 대폭 확장 (기본/확장/우선순위 혼합 예시 추가)
- **문서**: 멀티 exchange 지원 설명 추가 (개요, 기본 구조, FAQ)
- **FAQ**: 배치 주문 사용법 업데이트

### 2025-10-07
- **Hard Break**: `market_type`, `exchange` 필드 제거
- **추가**: 증권 마켓 타입 지원 (국내주식, 해외주식, 선물옵션)
- **개선**: 심볼 검증 로직 (크립토 엄격, 증권 유연)
- **신규**: params 객체 지원
- **문서**: 웹훅 예시 55개 → 10개 예시 코드 + 45개 시나리오로 재구성

### 2025-01-01 (이전)
- 초기 크립토 웹훅 시스템 구축
- SPOT, FUTURES 마켓 지원
- Binance, Upbit, Bybit 거래소 연동

---

## 라이선스

본 웹훅 시스템은 내부 사용 전용입니다. 무단 복제 및 배포를 금지합니다.
