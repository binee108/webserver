# 한국투자증권 API - 국내선물옵션

## 1. 주문 API

### 1.1 주문 (신규/청산)
- **Endpoint**: `POST /uapi/domestic-futureoption/v1/trading/order`
- **tr_id**: `OTFM1411U`

#### 요청
```json
{
  "CANO": "12345678",
  "ACNT_PRDT_CD": "01",
  "ODER_NO": "",                     // 신규: 공란, 청산: 기존주문번호
  "FUTU_DVSN_CD": "01",              // 01=선물, 02=옵션
  "PRDT_CD": "101TC000",             // 종목코드 (예: KOSPI200선물)
  "SLL_BUY_DVSN_CD": "01",           // 01=매도, 02=매수
  "ODER_DVSN": "00",                 // 00=지정가, 01=시장가
  "ODER_QTY": "1",                   // 주문수량 (계약수)
  "ODER_UNPR": "305.50",             // 주문단가
  "SLCT_TYPE_CD": "00",              // 00=신규, 01=청산
  "EXCG_DVSN_CD": "01",              // 01=KRX
  "CALL_PUT_DVSN_CD": ""             // 옵션: 01=Call, 02=Put
}
```

#### 응답
```json
{
  "rt_cd": "0",
  "output": {
    "KRX_FWDG_ORD_ORGNO": "00001",
    "ODNO": "FO0000123456",
    "ORD_TMD": "093015"
  }
}
```

#### 주의사항
- **SLCT_TYPE_CD**: 00=신규 (포지션 오픈), 01=청산 (포지션 종료)
- **계약수**: 주식과 달리 1계약 = 25만원(KOSPI200 기준)
- **증거금**: 별도 증거금 계산 필요

---

### 1.2 정정/취소주문
- **Endpoint**: `POST /uapi/domestic-futureoption/v1/trading/order-revise` (정정)
- **Endpoint**: `POST /uapi/domestic-futureoption/v1/trading/order-cancel` (취소)
- **tr_id**: `OTFM1412U` (정정), `OTFM1413U` (취소)

#### 요청 (정정)
```json
{
  "CANO": "12345678",
  "ACNT_PRDT_CD": "01",
  "ORGN_ODNO": "FO0000123456",       // 원주문번호
  "ODER_DVSN": "00",
  "ODER_QTY": "2",                   // 새 수량
  "ODER_UNPR": "306.00",             // 새 가격
  "EXCG_DVSN_CD": "01"
}
```

#### 요청 (취소)
```json
{
  "CANO": "12345678",
  "ACNT_PRDT_CD": "01",
  "ORGN_ODNO": "FO0000123456",
  "ODER_QTY": "1",                   // 취소수량 (전량: 원주문수량)
  "EXCG_DVSN_CD": "01"
}
```

---

## 2. 주문 조회 API

### 2.1 당일주문내역조회
- **Endpoint**: `GET /uapi/domestic-futureoption/v1/trading/inquire-order`
- **tr_id**: `OTFM3001R`

#### 요청
```
CANO=12345678
ACNT_PRDT_CD=01
INQR_STRT_DT=20241002
INQR_END_DT=20241002
SLL_BUY_DVSN_CD=00                // 00=전체, 01=매도, 02=매수
INQR_DVSN=00                      // 00=역순, 01=정순
FUTU_DVSN_CD=01                   // 01=선물, 02=옵션
CTX_AREA_FK100=
CTX_AREA_NK100=
```

#### 응답
```json
{
  "rt_cd": "0",
  "output1": [
    {
      "ord_dt": "20241002",
      "odno": "FO0000123456",
      "orgn_odno": "",
      "prdt_cd": "101TC000",
      "prdt_name": "KOSPI200선물 202412",
      "sll_buy_dvsn_cd": "02",           // 01=매도, 02=매수
      "ord_qty": "1",                    // 주문수량
      "ord_unpr": "305.50",              // 주문단가
      "ccld_qty": "1",                   // 체결수량
      "ccld_unpr": "305.45",             // 체결단가
      "rmn_qty": "0",                    // 미체결수량
      "futu_dvsn_cd": "01",              // 01=선물, 02=옵션
      "slct_type_cd": "00",              // 00=신규, 01=청산
      "ord_tmd": "093015"
    }
  ]
}
```

---

### 2.2 미체결내역조회
- **Endpoint**: `GET /uapi/domestic-futureoption/v1/trading/inquire-nccs`
- **tr_id**: `OTFM3002R`

#### 요청/응답: 당일주문내역조회와 동일, rmn_qty > 0인 건만 반환

---

## 3. 잔고 조회 API

### 3.1 미결제내역조회 (잔고)
- **Endpoint**: `GET /uapi/domestic-futureoption/v1/trading/inquire-balance`
- **tr_id**: `OTFM3003R`

#### 요청
```
CANO=12345678
ACNT_PRDT_CD=01
FUTU_DVSN_CD=01                   // 01=선물, 02=옵션
INQR_DVSN_1=00
CTX_AREA_FK100=
CTX_AREA_NK100=
```

#### 응답
```json
{
  "rt_cd": "0",
  "output1": [
    {
      "prdt_cd": "101TC000",
      "prdt_name": "KOSPI200선물 202412",
      "sll_buy_dvsn_cd": "02",           // 01=매도(Short), 02=매수(Long)
      "unsttl_qty": "1",                 // 미결제수량 (포지션)
      "bfdy_cprs_icdc": "+1",            // 전일대비증감 (포지션)
      "thdt_buy_ccld_qty": "1",          // 금일매수체결수량
      "thdt_sll_ccld_qty": "0",          // 금일매도체결수량
      "avg_buy_unpr": "305.45",          // 평균매수단가
      "now_pric": "306.50",              // 현재가
      "evlu_pfls_amt": "262500",         // 평가손익금액 (1계약 = 250,000원 * (306.50-305.45))
      "evlu_pfls_rt": "0.34",            // 평가손익율
      "fncc_amt": "7636250",             // 위탁증거금액
      "avrg_buy_amt": "76362500",        // 평균매수금액
      "nxdy_setl_pric": "305.80",        // 익일정산가격
      "buy_unpr": "305.45"               // 매수단가
    }
  ],
  "output2": {
    "dnca_tot_amt": "10000000",          // 예수금총액
    "nxdy_excc_amt": "2363750",          // 익일정산금액
    "tot_evlu_pfls_amt": "262500",       // 총평가손익금액
    "pchs_amt_smtl": "76362500",         // 매입금액합계
    "evlu_amt_smtl": "76625000",         // 평가금액합계
    "tot_evlu_amt": "12363750"           // 총평가금액
  }
}
```

---

### 3.2 주문가능금액조회
- **Endpoint**: `GET /uapi/domestic-futureoption/v1/trading/inquire-psbl-order`
- **tr_id**: `OTFM3004R`

#### 요청
```
CANO=12345678
ACNT_PRDT_CD=01
PRDT_CD=101TC000
ODER_UNPR=306.00
FUTU_DVSN_CD=01
SLL_BUY_DVSN_CD=02
```

#### 응답
```json
{
  "rt_cd": "0",
  "output": {
    "ord_psbl_cash": "2363750",          // 주문가능현금
    "max_ord_psbl_qty": "3",             // 최대주문가능수량 (계약)
    "fncc_ord_psbl_amt": "7091250",      // 위탁주문가능금액
    "fncc_ord_psbl_qty": "3"             // 위탁주문가능수량
  }
}
```

---

## 4. 시세조회 API

### 4.1 현재가
- **Endpoint**: `GET /uapi/domestic-futureoption/v1/quotations/inquire-price`
- **tr_id**: `FHPFO01010100`

#### 요청
```
FID_COND_MRKT_DIV_CODE=F         // F=선물, O=옵션
FID_INPUT_ISCD=101TC000
```

#### 응답
```json
{
  "rt_cd": "0",
  "output": {
    "stck_prpr": "306.50",               // 현재가
    "prdy_vrss": "1.00",                 // 전일대비
    "prdy_vrss_sign": "2",               // 전일대비부호
    "prdy_ctrt": "0.33",                 // 전일대비율
    "stck_oprc": "305.80",               // 시가
    "stck_hgpr": "307.20",               // 고가
    "stck_lwpr": "305.50",               // 저가
    "stck_mxpr": "335.50",               // 상한가
    "stck_llam": "275.50",               // 하한가
    "stck_sdpr": "305.50",               // 기준가(정산가)
    "acml_vol": "125000",                // 누적거래량
    "acml_tr_pbmn": "38281250000",       // 누적거래대금
    "optn_type": "",                     // 옵션타입 (선물: 공란)
    "exer_pric": "0",                    // 행사가격 (선물: 0)
    "last_sttl_pric": "305.50"           // 전일정산가
  }
}
```

---

### 4.2 호가
- **Endpoint**: `GET /uapi/domestic-futureoption/v1/quotations/inquire-asking-price`
- **tr_id**: `FHPFO01010200`

#### 요청/응답: 국내주식과 유사, 10단계 호가

---

### 4.3 일별시세
- **Endpoint**: `GET /uapi/domestic-futureoption/v1/quotations/inquire-daily-price`
- **tr_id**: `FHPFO01010400`

#### 요청/응답: 국내주식과 유사, 일/주/월봉 제공

---

## 5. 종목정보 API

### 5.1 종목기본정보조회
- **Endpoint**: `GET /uapi/domestic-futureoption/v1/quotations/inquire-basic-info`
- **tr_id**: `FHPFO01010900`

#### 요청
```
FID_COND_MRKT_DIV_CODE=F
FID_INPUT_ISCD=101TC000
```

#### 응답
```json
{
  "rt_cd": "0",
  "output": {
    "pdno": "101TC000",
    "prdt_name": "KOSPI200선물 202412",
    "futu_dvsn_cd": "01",                // 01=선물, 02=옵션
    "last_deal_day": "20241212",         // 최종거래일
    "setl_mmdd": "20241214",             // 결제월일
    "optn_type": "",                     // 옵션타입
    "exer_pric": "0",                    // 행사가격
    "undl_pdno": "KOSPI200",             // 기초자산
    "mult_val": "250000",                // 계약승수 (1포인트당)
    "min_hoga_qot_unit": "0.05"          // 최소호가단위
  }
}
```

---

## 6. 프로젝트 확장 시 고려사항

### 포지션 관리
| 구분 | 주식 | 선물옵션 |
|------|------|---------|
| 방향성 | 매수만 가능 | Long/Short 양방향 |
| 잔고 | hldg_qty | unsttl_qty (미결제약정) |
| 손익 | 평가금액 - 매입금액 | (현재가 - 진입가) × 계약승수 |
| 청산 | 매도 주문 | 반대 포지션 주문 |

### 데이터 매핑
| 한투 필드 | 프로젝트 필드 | 설명 |
|----------|------------|------|
| PRDT_CD | symbol | 종목코드 |
| sll_buy_dvsn_cd | position_side | 01=Short, 02=Long |
| unsttl_qty | quantity | 미결제수량 (계약) |
| avg_buy_unpr | entry_price | 진입가격 |
| now_pric | current_price | 현재가 |
| evlu_pfls_amt | unrealized_pnl | 평가손익 |
| SLCT_TYPE_CD | order_action | 00=OPEN, 01=CLOSE |

### 계약승수 및 증거금
- **KOSPI200 선물**: 1포인트 = 250,000원
- **미니 KOSPI200 선물**: 1포인트 = 50,000원
- **증거금**: 거래소 공시 증거금율 적용 (예: 10~15%)
- **손익 계산**: (현재가 - 진입가) × 계약수 × 승수

### 만기일 관리
- **최종거래일**: 매월 두 번째 목요일
- **정산일**: 최종거래일 익 영업일
- **자동 롤오버**: 만기 전 자동 청산 로직 필요
- **알림**: 만기 1주일 전 사용자 알림

### 에러 처리
- **증거금 부족**: 주문가능금액조회 먼저 확인
- **만기일 도래**: 거래 불가 에러 처리
- **청산 실패**: 반대 포지션 보유 시 에러
- **호가 단위**: 최소호가단위 준수
