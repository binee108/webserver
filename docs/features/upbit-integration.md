# Upbit 거래소 통합 가이드

## 개요

Upbit(업비트)는 대한민국 최대 암호화폐 거래소로, 본 시스템에서는 KRW(원화) 마켓 기반 현물 거래를 지원합니다. 이 문서는 Upbit 계정 등록부터 웹훅 주문 실행까지 전체 통합 과정을 다룹니다.

### 지원 기능

✅ **지원하는 기능**:
- 현물(Spot) 거래
- KRW 마켓 전용
- LIMIT(지정가) 주문
- MARKET(시장가) 주문
- 배치 주문 (순차 처리)
- 미체결 주문 조회/취소
- 잔액 조회
- WebSocket 실시간 가격

❌ **미지원 기능**:
- Testnet (실서버 API만 사용 가능)
- 선물(Futures) 거래
- STOP_LIMIT, STOP_MARKET 주문
- 배치 API (순차 폴백 방식 사용)
- BTC, USDT 마켓

### 제약사항

| 항목 | 제약 내용 |
|------|----------|
| **마켓** | KRW 마켓만 지원 |
| **최소 주문금액** | 5,000 KRW |
| **가격 단위** | 정수 (소수점 없음) |
| **Rate Limit** | 초당 8회, 분당 600회 |
| **Testnet** | 미지원 (실서버만) |
| **배치 API** | 미지원 (순차 처리) |

---

## Upbit 특징

### 거래소 정보

- **지역**: 대한민국 (국내 1위)
- **기준 통화**: KRW (원화)
- **거래 타입**: 현물 거래만
- **운영 환경**: 실서버만 (테스트넷 없음)

### API 특성

#### 인증 방식
- **알고리즘**: JWT (JSON Web Token)
  - 서명: HS256 (HMAC-SHA256)
  - 쿼리 해시: SHA512
- **구조**:
  ```json
  {
    "access_key": "YOUR_ACCESS_KEY",
    "nonce": "uuid4",
    "query_hash": "sha512(query_string)",
    "query_hash_alg": "SHA512"
  }
  ```

#### Rate Limiting
- **분당 제한**: 600회
- **초당 제한**: 8회
- **구현 방식**: `asyncio.Lock()` 기반 순차 실행
- **안전 마진**: 55% (초당 약 4.4회 실행)

#### 배치 주문 성능
Upbit는 배치 API를 제공하지 않으므로 순차 처리합니다:
- **16개 주문**: 약 3.6초 소요
- **처리 간격**: 각 주문 간 0.125초 딜레이 (1/8초)
- **동시성 제어**: `asyncio.Lock()`으로 완전 순차 실행

### 지원 주문 타입

| 주문 타입 | 지원 | 비고 |
|-----------|------|------|
| `LIMIT` | ✅ | 지정가 주문 |
| `MARKET` | ✅ | 시장가 주문 (즉시 체결) |
| `STOP_LIMIT` | ❌ | Upbit 미지원 |
| `STOP_MARKET` | ❌ | Upbit 미지원 |
| `CANCEL_ALL_ORDER` | ✅ | 전체 주문 취소 |

⚠️ **주의**: STOP 주문이 필요한 경우 Binance 등 다른 거래소 사용 필요

---

## API 키 발급 방법

### 1. Upbit 웹사이트 로그인
1. [Upbit 홈페이지](https://upbit.com) 접속
2. 로그인 또는 회원가입

### 2. Open API 관리 페이지 이동
1. 우측 상단 **마이페이지** 클릭
2. 좌측 메뉴 **Open API 관리** 선택

### 3. API 키 발급
1. **Open API 키 발급** 버튼 클릭
2. 본인 인증 (OTP 또는 SMS)

### 4. 권한 설정
필요한 권한만 선택하세요:

| 권한 | 설명 | 필수 여부 |
|------|------|-----------|
| **자산 조회** | 잔액 확인 | ✅ 필수 |
| **주문 조회** | 미체결 주문 확인 | ✅ 필수 |
| **주문하기** | 주문 생성/취소 | ✅ 필수 |
| **입출금** | 입금/출금 | ❌ 비활성화 권장 |

⚠️ **보안 권고**: 입출금 권한은 절대 활성화하지 마세요!

### 5. API 키 복사
- **Access Key**: 긴 문자열 (예: `abcdef123456...`)
- **Secret Key**: 한 번만 표시됨 → 안전한 곳에 보관

⚠️ **중요**: Secret Key는 발급 시 한 번만 표시됩니다. 복사하여 안전하게 보관하세요.

### 6. IP 화이트리스트 설정 (권장)
1. **IP 주소 등록** 활성화
2. 서버 IP 추가
3. 불필요한 IP에서의 접근 차단

---

## 계좌 등록 방법

### 웹 UI를 통한 등록

#### 1. 계좌 추가 페이지 이동
- 상단 메뉴 **계정 관리** → **새 계정 추가**

#### 2. 정보 입력
| 필드 | 값 | 설명 |
|------|-----|------|
| **Exchange** | `UPBIT` | 대문자로 정확히 입력 |
| **Account Type** | `CRYPTO` | 암호화폐 계정 |
| **Market Type** | `SPOT` | 현물 거래 |
| **API Key** | Access Key | Upbit에서 발급받은 Access Key |
| **API Secret** | Secret Key | Upbit에서 발급받은 Secret Key |
| **Is Testnet** | ❌ 체크 안 함 | Testnet 미지원 |

#### 3. 저장 및 검증
- **저장** 버튼 클릭
- 시스템이 자동으로 API 연결 테스트 수행
- 성공 메시지 확인

### CLI를 통한 등록 (선택사항)

```bash
# 계정 등록 CLI 실행
python -m web_server.app.cli.accounts add-account

# 대화형 입력:
# Exchange: UPBIT
# Account Type: CRYPTO
# Market Type: SPOT
# API Key: [Access Key]
# API Secret: [Secret Key]
# Is Testnet: no
```

---

## 전략 연동

### 1. 전략 관리 페이지 이동
- 상단 메뉴 **전략 관리**

### 2. 전략 선택
- 기존 전략 선택 또는 신규 전략 생성

### 3. 계좌 연동
1. 전략 상세 페이지에서 **계정 연동** 탭 클릭
2. **계정 추가** 버튼 클릭
3. Upbit 계좌 선택
4. 설정 입력:
   - **가중치**: 자본 배분 비율 (예: 50%)
   - **최대 포지션 수**: 동시 보유 가능한 심볼 수
5. **저장** 버튼 클릭

### 4. 연동 확인
- 전략 대시보드에서 연동된 계좌 목록 확인
- 잔액 정보 자동 표시

---

## 심볼 형식

### 표준 형식 (웹훅 요청)
**형식**: `BASE/QUOTE` (슬래시 포함)

**예시**:
- `BTC/KRW` - 비트코인/원화
- `ETH/KRW` - 이더리움/원화
- `XRP/KRW` - 리플/원화
- `ADA/KRW` - 카르다노/원화

### Upbit API 형식 (내부 변환)
**형식**: `QUOTE-BASE` (하이픈 사용, 순서 반대)

**자동 변환**:
- `BTC/KRW` → `KRW-BTC`
- `ETH/KRW` → `KRW-ETH`

⚠️ **주의**: 웹훅 요청 시 표준 형식(`BTC/KRW`)만 사용하세요. 시스템이 자동으로 Upbit 형식으로 변환합니다.

### 응답 형식
API 응답은 다시 표준 형식으로 변환됩니다:
- Upbit API: `KRW-BTC`
- 시스템 응답: `BTC/KRW`

### 지원 심볼

주요 암호화폐 (KRW 마켓):
- **비트코인**: `BTC/KRW`
- **이더리움**: `ETH/KRW`
- **리플**: `XRP/KRW`
- **카르다노**: `ADA/KRW`
- **솔라나**: `SOL/KRW`
- **도지코인**: `DOGE/KRW`
- **폴카닷**: `DOT/KRW`

전체 지원 심볼은 Upbit 거래소에서 확인하세요.

---

## 웹훅 사용 예시

### 1. LIMIT 주문 생성

#### 매수 지정가
```bash
curl -k -s -X POST https://your-server/api/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "group_name": "my_strategy",
    "symbol": "BTC/KRW",
    "order_type": "LIMIT",
    "side": "buy",
    "price": "50000000",
    "qty_per": 5,
    "token": "your_webhook_token"
  }'
```

**설명**:
- 5천만 원에 매수 지정가 주문
- `qty_per`: 5% (전략 자본의 5%)
- 체결되지 않으면 미체결 주문으로 남음

#### 매도 지정가
```bash
curl -k -s -X POST https://your-server/api/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "group_name": "my_strategy",
    "symbol": "BTC/KRW",
    "order_type": "LIMIT",
    "side": "sell",
    "price": "120000000",
    "qty_per": 5,
    "token": "your_webhook_token"
  }'
```

**설명**:
- 1억 2천만 원에 매도 지정가 주문
- 보유 중인 BTC의 5%를 매도

### 2. MARKET 주문

#### 시장가 매수
```bash
curl -k -s -X POST https://your-server/api/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "group_name": "my_strategy",
    "symbol": "BTC/KRW",
    "order_type": "MARKET",
    "side": "buy",
    "qty_per": 5,
    "token": "your_webhook_token"
  }'
```

⚠️ **주의**:
- MARKET 주문은 즉시 체결됩니다
- 테스트 시 소액으로 진행하세요 (`qty_per`: 0.01 ~ 1%)
- 슬리피지 발생 가능

#### 시장가 매도
```bash
curl -k -s -X POST https://your-server/api/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "group_name": "my_strategy",
    "symbol": "BTC/KRW",
    "order_type": "MARKET",
    "side": "sell",
    "qty_per": 5,
    "token": "your_webhook_token"
  }'
```

### 3. 주문 취소

#### 심볼별 전체 취소
```bash
curl -k -s -X POST https://your-server/api/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "group_name": "my_strategy",
    "symbol": "BTC/KRW",
    "order_type": "CANCEL_ALL_ORDER",
    "token": "your_webhook_token"
  }'
```

**결과**: BTC/KRW 심볼의 모든 미체결 주문 취소

#### 특정 방향만 취소
```bash
curl -k -s -X POST https://your-server/api/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "group_name": "my_strategy",
    "symbol": "BTC/KRW",
    "side": "buy",
    "order_type": "CANCEL_ALL_ORDER",
    "token": "your_webhook_token"
  }'
```

**결과**: BTC/KRW 매수 주문만 취소, 매도 주문은 유지

### 4. 포지션 청산 (qty_per=-100)

#### 롱 포지션 100% 청산
```bash
curl -k -s -X POST https://your-server/api/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "group_name": "my_strategy",
    "symbol": "BTC/KRW",
    "order_type": "MARKET",
    "side": "sell",
    "qty_per": -100,
    "token": "your_webhook_token"
  }'
```

**설명**:
- `qty_per=-100`: 전체 포지션 청산
- 보유 중인 BTC를 시장가로 전량 매도
- 포지션이 없으면 에러 반환

### 5. 배치 주문

#### 래더 전략 (단계별 매수)
```bash
curl -k -s -X POST https://your-server/api/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "group_name": "ladder_strategy",
    "symbol": "BTC/KRW",
    "token": "your_webhook_token",
    "orders": [
      {
        "order_type": "CANCEL_ALL_ORDER"
      },
      {
        "side": "buy",
        "order_type": "LIMIT",
        "price": "95000000",
        "qty_per": 3
      },
      {
        "side": "buy",
        "order_type": "LIMIT",
        "price": "94000000",
        "qty_per": 5
      },
      {
        "side": "buy",
        "order_type": "LIMIT",
        "price": "93000000",
        "qty_per": 7
      }
    ]
  }'
```

**처리 순서** (자동 정렬):
1. `CANCEL_ALL_ORDER` - 기존 주문 취소
2. `LIMIT` (9,500만 원) - 3% 매수
3. `LIMIT` (9,400만 원) - 5% 매수
4. `LIMIT` (9,300만 원) - 7% 매수

**소요 시간**: 약 0.5초 (4개 주문 × 0.125초)

---

## Rate Limiting

### 제한 사항
Upbit API는 다음과 같은 Rate Limit을 적용합니다:

| 제한 유형 | 제한 값 |
|-----------|---------|
| **초당 요청** | 8회 |
| **분당 요청** | 600회 |
| **가중치** | 없음 |

### 시스템 구현 방식

#### 완전 순차 실행
```python
# asyncio.Lock()으로 한 번에 1개만 실행
async with _order_lock:
    await asyncio.sleep(0.125)  # 1/8초 = 125ms
    await execute_order()
```

**특징**:
- **동시성**: 완전 순차 (Lock 사용)
- **딜레이**: 각 주문 간 0.125초
- **실제 속도**: 초당 약 4.4회 (안전 마진 55%)

#### 성능 예시

| 주문 수 | 예상 소요 시간 |
|---------|---------------|
| 1개 | 0.15초 |
| 4개 | 0.5초 |
| 8개 | 1.0초 |
| 16개 | 2.0초 |
| 32개 | 4.0초 |

### Rate Limit 초과 시
**에러 코드**: `429 Too Many Requests`

**대응 방안**:
- 시스템이 자동으로 딜레이를 적용하므로 초과 가능성 낮음
- 수동 API 호출 시 주의 필요
- 에러 발생 시 1분 대기 후 재시도

---

## 제약사항 및 주의사항

### 1. Testnet 미지원
**문제점**:
- Upbit는 테스트 환경을 제공하지 않음
- 모든 주문이 실제 거래로 실행됨

**대응 방안**:
- 최소 금액으로 테스트 (5,000 KRW)
- 지정가 주문으로 미체결 유도 (현재가보다 멀리 설정)
- 테스트 후 즉시 취소

**예시**:
```bash
# 안전한 테스트 주문 (미체결 유도)
# 현재가 1억 원일 때 5천만 원에 매수 지정
curl -k -s -X POST https://your-server/api/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "group_name": "test_strategy",
    "symbol": "BTC/KRW",
    "order_type": "LIMIT",
    "side": "buy",
    "price": "50000000",
    "qty_per": 0.01,
    "token": "your_webhook_token"
  }'
```

### 2. 최소 주문금액 (5,000 KRW)
**규칙**:
- 모든 주문은 5,000 KRW 이상이어야 함
- `주문금액 = 가격 × 수량`

**예시**:
```python
# ✅ 정상: 5,000 KRW 이상
price = 50,000,000  # 5천만 원
quantity = 0.0001   # 0.0001 BTC
amount = 50,000,000 * 0.0001 = 5,000 KRW  # OK

# ❌ 오류: 5,000 KRW 미만
price = 50,000,000
quantity = 0.00005  # 너무 적음
amount = 50,000,000 * 0.00005 = 2,500 KRW  # ERROR
```

**에러 메시지**:
```
"주문 금액이 최소 주문 금액(5,000 KRW) 이상이어야 합니다."
```

### 3. 배치 API 미지원
**제약**:
- Binance의 `batchOrders` 같은 배치 API 없음
- 모든 주문을 순차적으로 처리

**구현 방식**:
```python
# 순차 폴백 (Sequential Fallback)
for order in orders:
    await asyncio.sleep(0.125)  # Rate Limit 준수
    await execute_order(order)
```

**영향**:
- 대량 주문 시 시간 소요 증가
- 16개 주문: 약 2초 소요
- 실시간성이 중요한 경우 주문 수 최소화 권장

### 4. KRW 마켓 전용
**지원 마켓**:
- ✅ KRW (원화) 마켓만
- ❌ BTC, USDT 마켓 미지원

**가격 단위**:
- **KRW**: 정수 (소수점 없음)
  - `"price": "50000000"` ✅
  - `"price": "50000000.50"` ❌

**잘못된 심볼**:
```bash
# ❌ 오류: BTC 마켓 (미지원)
"symbol": "ETH/BTC"

# ✅ 정상: KRW 마켓
"symbol": "ETH/KRW"
```

### 5. 주문 타입 제한
**지원하지 않는 타입**:
- `STOP_LIMIT`
- `STOP_MARKET`
- `TRAILING_STOP`
- `OCO` (One-Cancels-Other)

**대안**:
- 손절/익절이 필요한 경우:
  1. Binance 등 STOP 주문 지원 거래소 사용
  2. 또는 별도 모니터링 스크립트 구현

---

## 가격 호가 단위

KRW 마켓의 호가 단위는 가격대별로 다릅니다:

| 가격대 | 호가 단위 | 예시 |
|--------|----------|------|
| **200만 원 이상** | 1,000원 | 2,001,000원 → 2,002,000원 |
| **100만 ~ 200만 원** | 500원 | 1,000,500원 → 1,001,000원 |
| **50만 ~ 100만 원** | 100원 | 500,100원 → 500,200원 |
| **10만 ~ 50만 원** | 50원 | 100,050원 → 100,100원 |
| **10만 원 미만** | 1원 | 99,999원 → 100,000원 |

### 호가 단위 적용 예시

```python
# 주문 가격이 호가 단위에 맞지 않으면 Upbit API가 에러 반환
# 시스템에서 자동으로 호가 단위에 맞춰 반올림/내림 처리

# 예시 1: 가격 2,500,000원 (250만 원)
# 호가 단위: 1,000원
"price": "2500000"  # ✅ OK
"price": "2500500"  # ❌ ERROR (호가 단위 위반)

# 예시 2: 가격 150,000원 (15만 원)
# 호가 단위: 50원
"price": "150000"  # ✅ OK
"price": "150050"  # ✅ OK
"price": "150025"  # ❌ ERROR (호가 단위 위반)
```

⚠️ **주의**: 웹훅에서 전송하는 가격은 호가 단위를 준수해야 합니다. 시스템이 자동 조정하지 않습니다.

---

## 문제 해결

### 문제 1: "지원되지 않는 거래소" 에러

**증상**:
```json
{
  "error": "지원되지 않는 거래소: upbit"
}
```

**원인**: Exchange 필드 오타 또는 소문자 입력

**해결**:
- `UPBIT` 정확히 입력 (대문자)
- 앞뒤 공백 제거
- 복사-붙여넣기 권장

---

### 문제 2: "Testnet 미지원" 에러

**증상**:
```json
{
  "error": "Upbit does not support testnet"
}
```

**원인**: 계정 등록 시 "Is Testnet" 체크박스 선택됨

**해결**:
1. 계정 관리 페이지 이동
2. Upbit 계정 편집
3. **Is Testnet** 체크 해제
4. 저장

---

### 문제 3: "심볼을 찾을 수 없음" 에러

**증상**:
```json
{
  "error": "Invalid market code: BTCKRW"
}
```

**원인**: 심볼 형식 오류

**잘못된 형식**:
- `"BTCKRW"` (슬래시 없음)
- `"KRW-BTC"` (Upbit API 형식)
- `"BTC-KRW"` (하이픈 사용)

**올바른 형식**:
- `"BTC/KRW"` ✅ (슬래시 포함)

**해결**:
```bash
# ❌ 잘못된 웹훅
curl -X POST https://your-server/api/webhook \
  -d '{"symbol": "BTCKRW", ...}'

# ✅ 올바른 웹훅
curl -X POST https://your-server/api/webhook \
  -d '{"symbol": "BTC/KRW", ...}'
```

---

### 문제 4: "최소 주문금액 미달" 에러

**증상**:
```json
{
  "error": "주문 금액이 최소 주문 금액(5,000 KRW) 이상이어야 합니다."
}
```

**원인**: 주문 금액이 5,000 KRW 미만

**확인 방법**:
```python
주문 금액 = 가격 × 수량
예: 50,000,000 × 0.00005 = 2,500 KRW  # ❌ 미달
```

**해결**:
1. 수량 증가: `qty_per` 증가
2. 또는 다른 심볼 선택 (낮은 가격대)

**예시**:
```bash
# ❌ 오류: 2,500 KRW
curl -X POST https://your-server/api/webhook \
  -d '{
    "symbol": "BTC/KRW",
    "price": "50000000",
    "qty_per": 0.0001
  }'

# ✅ 정상: 10,000 KRW
curl -X POST https://your-server/api/webhook \
  -d '{
    "symbol": "BTC/KRW",
    "price": "50000000",
    "qty_per": 0.0004
  }'
```

---

### 문제 5: Rate Limit 초과 (429 에러)

**증상**:
```json
{
  "error": "Too many requests"
}
```

**원인**: API 호출 과다 (초당 8회 초과)

**해결**:
1. 시스템이 자동으로 딜레이 적용
2. 수동 API 호출 시 간격 조절
3. 1분 대기 후 재시도

**예방**:
- 배치 주문 권장 (자동 Rate Limit 관리)
- 수동 호출 시 0.125초 이상 간격

---

### 문제 6: JWT 인증 오류

**증상**:
```json
{
  "error": "JWT verification failed"
}
```

**원인**:
- API Key 또는 Secret Key 오류
- 특수문자 복사 오류

**해결**:
1. Upbit에서 API Key 재확인
2. 앞뒤 공백 제거
3. 특수문자 정확히 복사
4. 필요 시 API Key 재발급

---

### 문제 7: "잔액 부족" 에러

**증상**:
```json
{
  "error": "insufficient balance"
}
```

**원인**: KRW 잔액 부족

**확인 방법**:
1. Upbit 앱/웹에서 잔액 확인
2. 시스템 대시보드에서 잔액 조회

**해결**:
- Upbit에 KRW 입금
- 또는 `qty_per` 감소

---

## 로그 확인

### 실시간 로그 모니터링

```bash
# Upbit 관련 로그만 필터링
tail -f /Users/binee/Desktop/quant/webserver/web_server/logs/app.log | grep -E "(Upbit|UPBIT)"

# 에러만 확인
tail -f /Users/binee/Desktop/quant/webserver/web_server/logs/app.log | grep -E "(ERROR|CRITICAL)" | grep -i upbit

# 주문 실행 로그
tail -f /Users/binee/Desktop/quant/webserver/web_server/logs/app.log | grep "배치 주문"
```

### 정상 로그 예시

#### 초기화
```
✅ Upbit 거래소 초기화
✅ upbit 거래소 인스턴스 생성 - Testnet: False
```

#### 주문 생성
```
🔄 심볼 변환: BTC/KRW → KRW-BTC
🔍 Upbit API 호출: /v1/orders
🔍 주문 파라미터: {'market': 'KRW-BTC', 'side': 'bid', 'ord_type': 'limit', 'price': '50000000', 'volume': '0.001'}
🔍 Upbit API 응답: {'uuid': 'abc-123-def', 'side': 'bid', 'state': 'wait', ...}
✅ Upbit 배치 주문 [0] 성공: order_id=abc-123-def, symbol=BTC/KRW
```

#### 배치 주문
```
📦 Upbit 배치 주문 시작: 3건 (Rate Limit: 초당 8회)
✅ Upbit 배치 주문 [0] 성공: order_id=uuid-1, symbol=BTC/KRW
✅ Upbit 배치 주문 [1] 성공: order_id=uuid-2, symbol=BTC/KRW
✅ Upbit 배치 주문 [2] 성공: order_id=uuid-3, symbol=BTC/KRW
📦 Upbit 배치 주문 완료: 3/3 성공, 소요시간: 0.45초 (평균 0.150초/주문), implementation=SEQUENTIAL_FALLBACK
```

### 에러 로그 예시

#### API 키 오류
```
❌ Upbit API 에러 [401]: Invalid access key
❌ Upbit API 요청 실패: Upbit API Error [401]: Invalid access key
```

#### 심볼 오류
```
❌ Upbit API 에러 [400]: Invalid market code: BTCKRW
```

#### 최소 주문금액 미달
```
❌ Upbit API 에러 [400]: 주문 금액이 최소 주문 금액(5,000 KRW) 이상이어야 합니다.
```

---

## 성능 최적화

### 캐싱
시스템은 다음 데이터를 캐싱하여 성능을 향상시킵니다:

| 데이터 | TTL | 용도 |
|--------|-----|------|
| **마켓 정보** | 5분 | 심볼 검증 |
| **가격 정보** | 1초 | 실시간 가격 조회 |

### 배치 주문 최적화
- 순차 처리로 Rate Limit 준수
- 주문 우선순위 자동 정렬
- 실패한 주문은 재시도하지 않음 (결과에 포함)

---

## 참고 자료

### 공식 문서
- [Upbit API 공식 문서](https://docs.upbit.com)
- [Upbit Open API 가이드](https://docs.upbit.com/docs/getting-started)
- [마켓 코드 조회](https://docs.upbit.com/reference/market-전체-종목-조회)
- [주문하기 API](https://docs.upbit.com/reference/order-주문하기)

### 프로젝트 내부
- **구현 파일**: `/Users/binee/Desktop/quant/webserver/web_server/app/exchanges/crypto/upbit.py`
- **팩토리**: `/Users/binee/Desktop/quant/webserver/web_server/app/exchanges/crypto/factory.py`
- **메타데이터**: `/Users/binee/Desktop/quant/webserver/web_server/app/exchanges/metadata.py`

### 관련 문서
- [웹훅 메시지 포맷 가이드](/Users/binee/Desktop/quant/webserver/docs/webhook_message_format.md)
- [거래소 통합 가이드](/Users/binee/Desktop/quant/webserver/docs/features/exchange-integration.md)
- [FEATURE CATALOG](/Users/binee/Desktop/quant/webserver/docs/FEATURE_CATALOG.md)

---

**최종 업데이트**: 2025-10-12
**작성자**: documentation-manager agent
**버전**: 1.0
