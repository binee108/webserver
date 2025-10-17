# 한국투자증권 API - 인증 및 공통

## 개요

한국투자증권 오픈 API를 사용하기 위해서는 보안 인증 절차를 통해 접근 토큰(Access Token) 또는 접속키(Approval Key)를 발급받아야 합니다. 이 문서에서는 API 호출의 가장 기본이 되는 인증 및 공통 기능에 대해 설명합니다.

  - **REST API 방식**: `접근토큰`을 발급받아 API를 호출합니다.
  - **WebSocket API 방식**: `접근토큰` 발급 없이 `접속키`를 발급받아 실시간 통신에 사용합니다.

-----

## 1\. 접근토큰 발급 (OAuth 2.0)

계좌 거래 및 시세 조회를 위한 REST API를 사용하기 위해 OAuth 2.0 기반의 접근토큰을 발급받습니다.

### 기본 정보

| 항목 | 내용 |
| :--- | :--- |
| **Method** | `POST` |
| **URI** | `/oauth2/tokenP` |
| **API코드** | `[인증-001]` |
| **Content-Type**| `application/json` |
| **Domain** | **실전투자**: `https://openapi.koreainvestment.com:9443` <br> **모의투자**: `https://openapivts.koreainvestment.com:29443`|

### 요청 (Request)

#### Header

| 항목 | 타입 | 필수 여부 | 길이 | 설명 |
| :--- | :--- | :--- | :--- | :--- |
| `content-type` | String | Y | 30 | `application/json` |

#### Body

| 항목 | 타입 | 필수 여부 | 길이 | 설명 |
| :--- | :--- | :--- | :--- | :--- |
| `grant_type` | String | Y | 20 | `client_credentials` (고정값) |
| `appkey` | String | Y | 256 | 서비스 신청 시 발급받은 App Key |
| `appsecret` | String | Y | 256 | 서비스 신청 시 발급받은 App Secret |

##### 예시 (Request Body)

```json
{
    "grant_type": "client_credentials",
    "appkey": "발급받은 App Key",
    "appsecret": "발급받은 App Secret"
}
```

### 응답 (Response)

#### Body

| 항목 | 타입 | 필수 여부 | 길이 | 설명 |
| :--- | :--- | :--- | :--- | :--- |
| `access_token` | String | Y | 450 | 접근토큰 값 |
| `token_type` | String | Y | 20 | `Bearer` (고정값) |
| `expires_in` | Number | Y | 10 | 접근토큰 유효기간 (초) |
| `access_token_token_expired` | String | Y | 20 | 접근토큰 만료일시 (YYYY-MM-DD hh:mm:ss) |
| `msg_cd` | String | Y | 3 | 응답코드 (성공: `O0001`, 실패: `E0002` 등) |
| `msg1` | String | Y | 100 | 응답메시지 |

##### 예시 (Response Body)

```json
{
    "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9...",
    "token_type": "Bearer",
    "expires_in": 86400,
    "access_token_token_expired": "2025-10-05 12:30:00",
    "msg_cd": "O0001",
    "msg1": "SUCCESS"
}
```

**※ 참고 사항**

  * 접근토큰의 유효기간은 **24시간**입니다. (1일 1회 발급 원칙)
  * 갱신 발급 주기는 **6시간**입니다. (6시간 이내 재요청 시 기존 발급 토큰으로 응답)
  * 발급된 접근토큰은 이후 모든 REST API 요청 시 **Header**의 `authorization` 항목에 `Bearer {ACCESS_TOKEN}` 형식으로 담아 전송해야 합니다.

-----

## 2\. 접근토큰 폐기

발급받은 접근토큰을 강제로 만료시킵니다.

### 기본 정보

| 항목 | 내용 |
| :--- | :--- |
| **Method** | `POST` |
| **URI** | `/oauth2/revokeP` |
| **API코드** | `[인증-002]` |
| **Content-Type**| `application/json` |
| **Domain** | **실전투자**: `https://openapi.koreainvestment.com:9443` <br> **모의투자**: `https://openapivts.koreainvestment.com:29443`|

### 요청 (Request)

#### Header

| 항목 | 타입 | 필수 여부 | 길이 | 설명 |
| :--- | :--- | :--- | :--- | :--- |
| `content-type` | String | Y | 30 | `application/json` |

#### Body

| 항목 | 타입 | 필수 여부 | 길이 | 설명 |
| :--- | :--- | :--- | :--- | :--- |
| `appkey` | String | Y | 256 | 서비스 신청 시 발급받은 App Key |
| `appsecret` | String | Y | 256 | 서비스 신청 시 발급받은 App Secret |
| `token` | String | Y | 450 | 폐기할 접근토큰 |

##### 예시 (Request Body)

```json
{
    "appkey": "발급받은 App Key",
    "appsecret": "발급받은 App Secret",
    "token": "폐기할 접근토큰 값"
}
```

### 응답 (Response)

#### Body

| 항목 | 타입 | 필수 여부 | 길이 | 설명 |
| :--- | :--- | :--- | :--- | :--- |
| `msg_cd` | String | Y | 3 | 응답코드 |
| `msg1` | String | Y | 100 | 응답메시지 |

##### 예시 (Response Body)

```json
{
    "msg_cd": "O0013",
    "msg1": "Token Revoke is Success"
}
```

-----

## 3\. Hashkey 생성

주문, 예약주문 등 중요 데이터의 위변조 방지를 위해 API 요청 시 Hashkey를 생성하여 사용합니다.

### 생성 규칙

`SHA256` 알고리즘을 사용하여 요청 메시지의 주요 항목들을 조합한 문자열을 해시화합니다.

### 생성 절차

1.  API 요청 Body의 모든 `Key:Value`를 문자열로 조합합니다.
2.  이 문자열을 `App Key`, `App Secret`, `요청 URL`과 함께 조합합니다.
3.  조합된 최종 문자열을 `SHA256`으로 해시하여 `Base64`로 인코딩합니다.

### 요청 예시 (국내주식주문)

#### Request Body

```json
{
    "CANO": "계좌번호 앞 8자리",
    "ACNT_PRDT_CD": "계좌번호 뒤 2자리",
    "PDNO": "005930",
    "ORD_DVSN": "01",
    "ORD_QTY": "10",
    "ORD_UNPR": "80000"
}
```

#### Hashkey 생성 절차 (의사 코드)

```
// 1. 요청 데이터를 문자열로 조합
request_data = "CANO=계좌번호 앞 8자리|ACNT_PRDT_CD=계좌번호 뒤 2자리|PDNO=005930|ORD_DVSN=01|ORD_QTY=10|ORD_UNPR=80000"

// 2. 최종 문자열 생성
data_to_hash = APP_KEY + "|" + APP_SECRET + "|" + request_data

// 3. SHA256 해시 및 Base64 인코딩
hashkey = base64_encode(sha256(data_to_hash))
```

  * 생성된 Hashkey는 API 요청 시 **Header**의 `hashkey` 항목에 담아 전송합니다.

-----

## 4\. 실시간 접속키 발급 (WebSocket)

시세, 체결 등의 데이터를 실시간으로 수신하기 위한 웹소켓 접속키(approval\_key)를 발급받습니다.

### 기본 정보

| 항목 | 내용 |
| :--- | :--- |
| **Method** | `POST` |
| **URI** | `/oauth2/Approval` |
| **API코드** | `[실시간-000]` |
| **Content-Type**| `application/json` |
| **Domain** | **실전투자**: `https://openapi.koreainvestment.com:9443` <br> **모의투자**: `https://openapivts.koreainvestment.com:29443`|

### 요청 (Request)

#### Header

| 항목 | 타입 | 필수 여부 | 길이 | 설명 |
| :--- | :--- | :--- | :--- | :--- |
| `content-type` | String | Y | 30 | `application/json` |

#### Body

| 항목 | 타입 | 필수 여부 | 길이 | 설명 |
| :--- | :--- | :--- | :--- | :--- |
| `grant_type` | String | Y | 20 | `client_credentials` (고정값) |
| `appkey` | String | Y | 256 | 서비스 신청 시 발급받은 App Key |
| `secretkey` | String | Y | 256 | 서비스 신청 시 발급받은 App Secret |

##### 예시 (Request Body)

```json
{
    "grant_type": "client_credentials",
    "appkey": "발급받은 App Key",
    "secretkey": "발급받은 App Secret"
}
```

### 응답 (Response)

#### Body

| 항목 | 타입 | 필수 여부 | 길이 | 설명 |
| :--- | :--- | :--- | :--- | :--- |
| `approval_key` | String | Y | 450 | 웹소켓 접속키 |
| `msg_cd` | String | Y | 3 | 응답코드 |
| `msg1` | String | Y | 100 | 응답메시지 |

##### 예시 (Response Body)

```json
{
    "approval_key": "4a71...9f-4f72-9b0f-d23...",
    "msg_cd": "O0001",
    "msg1": "SUCCESS"
}
```

**※ 참고 사항**

  * 발급된 `approval_key`는 웹소켓 접속 시 사용되며, 유효기간은 없습니다.
  * 웹소켓 접속 주소
      * **실전투자**: `ws://ops.koreainvestment.com:21000`
      * **모의투자**: `ws://ops.koreainvestment.com:31000`