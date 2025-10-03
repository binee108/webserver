# 한국투자증권 API - 인증 및 공통

## 1. OAuth2 토큰 발급

### 접근토큰 발급(P)
- **Endpoint**: `POST /oauth2/tokenP`
- **용도**: API 사용을 위한 액세스 토큰 발급

#### 요청
```json
{
  "grant_type": "client_credentials",
  "appkey": "{발급받은_APP_KEY}",
  "appsecret": "{발급받은_APP_SECRET}"
}
```

#### 응답
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "access_token_token_expired": "2024-10-03 12:30:45",
  "token_type": "Bearer",
  "expires_in": 86400
}
```

#### 주요 정보
- **유효기간**: 24시간
- **재발급 조건**: 6시간 경과 후 재발급 가능 (6시간 내 요청 시 동일 토큰 반환)
- **Rate Limit**: 5분당 1회 (2023-10-27 기준)
- **사용법**: HTTP Header에 `Authorization: Bearer {access_token}` 추가

---

## 2. HashKey 생성

### Hashkey 생성
- **Endpoint**: `POST /uapi/hashkey`
- **용도**: POST 방식 주문 API 호출 시 보안 검증용 해시값 생성

#### 요청 Header
```
Authorization: Bearer {access_token}
appkey: {APP_KEY}
appsecret: {APP_SECRET}
```

#### 요청 Body
```json
{
  "CANO": "12345678",
  "ACNT_PRDT_CD": "01",
  "PDNO": "005930",
  "ORD_DVSN": "00",
  "ORD_QTY": "10",
  "ORD_UNPR": "70000"
}
```
*주문 시 전송할 JSON 데이터를 그대로 전송*

#### 응답
```json
{
  "HASH": "3a8f9c2e1b4d7a5e9c8f2b1d4a7e5c9f8b2e1d4a"
}
```

#### 사용법
- 주문/정정/취소 등 POST 요청 시 Header에 `hashkey: {HASH}` 추가
- **주의**: GET 요청에는 불필요

---

## 3. 웹소켓 접속키

### 실시간(웹소켓) 접속키 발급
- **Endpoint**: `POST /oauth2/Approval`
- **용도**: 웹소켓 실시간 시세 연결용 승인키

#### 요청
```json
{
  "grant_type": "client_credentials",
  "appkey": "{APP_KEY}",
  "secretkey": "{APP_SECRET}"
}
```

#### 응답
```json
{
  "approval_key": "a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5p6"
}
```

#### 주요 정보
- **유효기간**: 60초 (발급 후 60초 내 웹소켓 연결 필요)
- **사용법**: 웹소켓 연결 시 헤더에 포함
- **갱신**: 연결 후 주기적 갱신 필요

---

## 4. 공통 요청 구조

### HTTP Header (필수)
```
Authorization: Bearer {access_token}
Content-Type: application/json; charset=utf-8
appkey: {APP_KEY}
appsecret: {APP_SECRET}
tr_id: {거래ID}
```

### HTTP Header (POST 요청 시 추가)
```
hashkey: {생성된_HASH}
```

### 거래ID(tr_id) 예시
| API | 매수 tr_id | 매도 tr_id |
|-----|-----------|-----------|
| 국내주식 현금주문 | TTTC0802U | TTTC0801U |
| 국내주식 신용주문 | TTTC0852U | TTTC0851U |
| 해외주식 주문 (미국) | TTTS1002U | TTTS1001U |
| 주식현재가 | FHKST01010100 | - |
| 주식잔고조회 | TTTC8434R | - |

*실전투자와 모의투자는 tr_id가 다름 (실전: T, 모의: V)*

---

## 5. 공통 응답 구조

### 성공 응답
```json
{
  "rt_cd": "0",
  "msg_cd": "MCA00000",
  "msg1": "정상처리 되었습니다",
  "output": {
    // API별 상이한 응답 데이터
  },
  "output1": [
    // API별 배열 데이터 (선택)
  ],
  "output2": {
    // API별 추가 데이터 (선택)
  }
}
```

### 실패 응답
```json
{
  "rt_cd": "1",
  "msg_cd": "EGW00123",
  "msg1": "해당 종목은 거래정지 종목입니다"
}
```

### 응답 코드
- `rt_cd`: "0" (성공), "1" (실패)
- `msg_cd`: 상세 에러 코드
- `msg1`: 사용자 표시 메시지

---

## 6. 웹소켓 구조

### 연결 정보
- **URL**: `wss://ops.koreainvestment.com:21000` (실전)
- **URL**: `wss://ops.koreainvestment.com:31000` (모의)
- **프로토콜**: WSS (WebSocket Secure)

### 구독 요청 메시지
```json
{
  "header": {
    "approval_key": "{승인키}",
    "custtype": "P",
    "tr_type": "1",
    "content-type": "utf-8"
  },
  "body": {
    "input": {
      "tr_id": "H0STCNT0",
      "tr_key": "005930"
    }
  }
}
```

### tr_type
- `"1"`: 등록 (구독)
- `"2"`: 해제 (구독 취소)

---

## 7. 크립토 거래소 vs 한국투자증권 비교

| 구분 | 크립토 거래소 | 한국투자증권 |
|-----|-------------|------------|
| **인증** | API Key/Secret 직접 사용 | OAuth2 토큰 (24시간) |
| **보안** | HMAC Signature | HashKey + OAuth2 |
| **웹소켓 인증** | API Key 직접 전송 | Approval Key (60초) |
| **토큰 갱신** | 불필요 | 6시간마다 권장 |
| **거래ID** | 없음 | API별 고유 tr_id |
| **계좌 구분** | 단일 API Key | CANO + ACNT_PRDT_CD |

---

## 8. 구현 시 핵심 사항

### 인증 플로우
```
1. OAuth2 토큰 발급 (/oauth2/tokenP)
   └─> 24시간 유효, 메모리/DB 캐싱

2. [POST 요청 시] HashKey 생성 (/uapi/hashkey)
   └─> 요청 Body로 해시 생성

3. API 호출
   └─> Header에 토큰 + hashkey 포함

4. [실시간 필요 시] Approval Key 발급 (/oauth2/Approval)
   └─> 60초 내 웹소켓 연결
```

### 토큰 관리 전략
1. **자동 갱신**: 토큰 만료 6시간 전 재발급
2. **에러 처리**: 401 에러 시 자동 재발급 후 재시도
3. **환경 분리**: 실전/모의 토큰 별도 관리

### HashKey 처리
1. **매 요청 생성**: POST 요청마다 새로 생성
2. **캐싱 불필요**: 재사용 불가
3. **에러 처리**: 해시 불일치 시 재생성 후 재시도

### 계좌번호 처리
- **CANO**: 종합계좌번호 앞 8자리
- **ACNT_PRDT_CD**: 계좌상품코드 뒤 2자리
- 예: `12345678-01` → CANO=`12345678`, ACNT_PRDT_CD=`01`
