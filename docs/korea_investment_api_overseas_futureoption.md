# 한국투자증권 API - 해외선물옵션

## 1. 주문 API

### 1.1 주문 (신규/청산)
- **Endpoint**: `POST /uapi/overseas-futureoption/v1/trading/order`
- **tr_id**: `OTFM3001U`

#### 요청
```json
{
  "CANO": "12345678",
  "ACNT_PRDT_CD": "01",
  "OVRS_FUTR_FX_PDNO": "ESZ4",       // 종목코드 (예: ES=S&P500선물, 월물코드)
  "SLL_BUY_DVSN_CD": "02",           // 01=매도(Short), 02=매수(Long)
  "PRIC_DVSN_CD": "1",               // 1=지정가, 2=시장가, 3=STOP, 4=S/L
  "FM_LIMIT_ORD_PRIC": "4500.00",    // 지정가 주문가격
  "FM_STOP_ORD_PRIC": "0.00",        // STOP 주문가격 (STOP 시)
  "FM_ORD_QTY": "1",                 // 주문수량 (계약수)
  "CCLD_CNDT_CD": "0"                // 체결조건: 0=없음, 1=IOC, 2=FOK
}
```

#### 응답
```json
{
  "rt_cd": "0",
  "output": {
    "odno": "OF0000123456",          // 주문번호
    "ord_tmd": "213015"              // 주문시각
  }
}
```

---

### 1.2 정정/취소주문
- **Endpoint**: `POST /uapi/overseas-futureoption/v1/trading/order-revise` (정정)
- **Endpoint**: `POST /uapi/overseas-futureoption/v1/trading/order-cancel` (취소)
- **tr_id**: `OTFM3002U` (정정), `OTFM3003U` (취소)

#### 요청 (정정)
```json
{
  "CANO": "12345678",
  "ACNT_PRDT_CD": "01",
  "OVRS_FUTR_FX_PDNO": "ESZ4",
  "ORGN_ODNO": "OF0000123456",       // 원주문번호
  "PRIC_DVSN_CD": "1",
  "FM_LIMIT_ORD_PRIC": "4510.00",    // 새 가격
  "FM_ORD_QTY": "2",                 // 새 수량
  "CCLD_CNDT_CD": "0"
}
```

#### 요청 (취소)
```json
{
  "CANO": "12345678",
  "ACNT_PRDT_CD": "01",
  "OVRS_FUTR_FX_PDNO": "ESZ4",
  "ORGN_ODNO": "OF0000123456",
  "FM_ORD_QTY": "1"                  // 취소수량
}
```

---

## 2. 주문 조회 API

### 2.1 당일주문내역조회
- **Endpoint**: `GET /uapi/overseas-futureoption/v1/trading/inquire-order`
- **tr_id**: `OTFM3004R`

#### 요청
```
CANO=12345678
ACNT_PRDT_CD=01
INQR_STRT_DT=20241002
INQR_END_DT=20241002
SLL_BUY_DVSN_CD=00                // 00=전체, 01=매도, 02=매수
CCLD_NCCS_DVSN=00                 // 00=전체, 01=체결, 02=미체결
CTX_AREA_FK100=
CTX_AREA_NK100=
```

#### 응답
```json
{
  "rt_cd": "0",
  "output": [
    {
      "ord_dt": "20241002",
      "odno": "OF0000123456",
      "orgn_odno": "",
      "ovrs_futr_fx_pdno": "ESZ4",
      "prdt_name": "E-MINI S&P500 DEC24",
      "sll_buy_dvsn_cd": "02",           // 01=매도, 02=매수
      "ord_qty": "1",
      "ord_unpr": "4500.00",
      "ccld_qty": "1",                   // 체결수량
      "ccld_unpr": "4502.50",            // 체결가격
      "nccs_qty": "0",                   // 미체결수량
      "ord_tmd": "213015",
      "pric_dvsn_cd": "1",               // 가격구분
      "ccld_cndt_cd": "0"                // 체결조건
    }
  ]
}
```

---

## 3. 잔고 조회 API

### 3.1 미결제내역조회 (잔고)
- **Endpoint**: `GET /uapi/overseas-futureoption/v1/trading/inquire-balance`
- **tr_id**: `OTFM3005R`

#### 요청
```
CANO=12345678
ACNT_PRDT_CD=01
OVRS_EXCG_CD=CME                  // CME, EUREX, HKEX 등
CTX_AREA_FK100=
CTX_AREA_NK100=
```

#### 응답
```json
{
  "rt_cd": "0",
  "output1": [
    {
      "ovrs_futr_fx_pdno": "ESZ4",
      "prdt_name": "E-MINI S&P500 DEC24",
      "sll_buy_dvsn_cd": "02",           // 01=Short, 02=Long
      "unsttl_qty": "1",                 // 미결제수량 (포지션)
      "avg_buy_unpr": "4502.50",         // 평균진입가
      "now_pric": "4550.00",             // 현재가
      "frcr_evlu_pfls_amt": "2375.00",   // 평가손익 (USD)
      "evlu_pfls_rt": "5.28",            // 평가손익율
      "wcrc_evlu_pfls_amt": "3168750",   // 평가손익 (원화)
      "ovrs_excg_cd": "CME",
      "tr_crcy_cd": "USD",               // 거래통화
      "exch_rt": "1335.00",              // 환율
      "fncc_amt_smtl": "5402812",        // 증거금합계
      "mult_val": "50",                  // 계약승수 (1포인트당 $50)
      "last_deal_day": "20241219"        // 최종거래일
    }
  ],
  "output2": {
    "frcr_pchs_amt_smtl": "225125.00",   // 매입금액합계 (USD)
    "tot_evlu_pfls_amt": "2375.00",      // 총평가손익 (USD)
    "wcrc_tot_evlu_pfls": "3168750",     // 총평가손익 (원화)
    "tot_evlu_amt": "227500.00",         // 총평가금액 (USD)
    "wcrc_evlu_amt_smtl": "303712500"    // 평가금액합계 (원화)
  }
}
```

---

### 3.2 주문가능금액조회
- **Endpoint**: `GET /uapi/overseas-futureoption/v1/trading/inquire-psbl-order`
- **tr_id**: `OTFM3006R`

#### 요청
```
CANO=12345678
ACNT_PRDT_CD=01
OVRS_FUTR_FX_PDNO=ESZ4
FM_ORD_UNPR=4550.00
SLL_BUY_DVSN_CD=02
OVRS_EXCG_CD=CME
TR_CRCY_CD=USD
```

#### 응답
```json
{
  "rt_cd": "0",
  "output": {
    "frcr_ord_psbl_amt": "50000.00",     // 주문가능금액 (USD)
    "max_ord_psbl_qty": "9",             // 최대주문가능수량 (계약)
    "wcrc_ord_psbl_amt": "66750000",     // 주문가능금액 (원화)
    "fncc_ord_psbl_qty": "9"             // 증거금기준 주문가능수량
  }
}
```

---

## 4. 시세조회 API

### 4.1 현재가
- **Endpoint**: `GET /uapi/overseas-futureoption/v1/quotations/inquire-price`
- **tr_id**: `HHDFS76410000`

#### 요청
```
AUTH=
EXCD=CME                          // CME, EUREX, HKEX, SGX 등
SYMB=ESZ4                         // 종목코드 (월물코드 포함)
```

#### 응답
```json
{
  "rt_cd": "0",
  "output": {
    "rsym": "ESZ4",
    "zdiv": "2",                         // 소수점자리수
    "base": "4500.00",                   // 기준가(전일정산가)
    "last": "4550.00",                   // 현재가
    "sign": "2",                         // 대비부호
    "diff": "50.00",                     // 전일대비
    "rate": "1.11",                      // 등락률
    "tvol": "1250000",                   // 당일거래량
    "tamt": "5700000000",                // 당일거래대금
    "ordy": "4505.00",                   // 시가
    "ghpr": "4560.00",                   // 고가
    "glpr": "4500.00",                   // 저가
    "h52p": "4850.00",                   // 52주최고가
    "l52p": "4100.00",                   // 52주최저가
    "expi_dt": "20241219",               // 만기일
    "mult_val": "50",                    // 계약승수
    "min_tick": "0.25",                  // 최소호가단위
    "open_intr": "2500000"               // 미결제약정 (OI)
  }
}
```

---

### 4.2 호가
- **Endpoint**: `GET /uapi/overseas-futureoption/v1/quotations/inquire-asking-price`
- **tr_id**: `HHDFS76420000`

#### 요청/응답: 해외주식과 유사, 5단계 호가

---

### 4.3 일별시세
- **Endpoint**: `GET /uapi/overseas-futureoption/v1/quotations/inquire-daily-price`
- **tr_id**: `HHDFS76430000`

#### 요청/응답: 해외주식과 유사, 일/주/월봉 제공

---

## 5. 종목정보 API

### 5.1 종목기본정보조회
- **Endpoint**: `GET /uapi/overseas-futureoption/v1/quotations/inquire-basic-info`
- **tr_id**: `HHDFS76440000`

#### 요청
```
AUTH=
EXCD=CME
SYMB=ESZ4
```

#### 응답
```json
{
  "rt_cd": "0",
  "output": {
    "symb": "ESZ4",
    "prdt_name": "E-MINI S&P500 DEC24",
    "exch_name": "CME",
    "futu_optn_dvsn": "F",               // F=선물, O=옵션
    "undl_pdno": "SP500",                // 기초자산
    "expi_dt": "20241219",               // 만기일
    "last_deal_day": "20241219",         // 최종거래일
    "mult_val": "50",                    // 계약승수
    "min_tick": "0.25",                  // 최소호가단위
    "tick_val": "12.50",                 // 틱가치 (1틱당 $12.50)
    "tr_crcy_cd": "USD",
    "trad_strt_hour": "230000",          // 한국시간 거래시작
    "trad_end_hour": "060000",           // 한국시간 거래종료
    "init_mrgn_rt": "0.10",              // 개시증거금율
    "maint_mrgn_rt": "0.08"              // 유지증거금율
  }
}
```

---

## 6. 프로젝트 확장 시 고려사항

### 거래소 코드 매핑
| OVRS_EXCG_CD | 거래소 | 주요 상품 | 통화 | 시간대(KST) |
|--------------|--------|----------|------|------------|
| CME | 시카고상품 | ES(S&P500), NQ(나스닥) | USD | 23:00-06:00 |
| EUREX | 유렉스 | FDAX(DAX), FESX(유로스탁스) | EUR | 16:00-06:00 |
| HKEX | 홍콩 | HSI(항셍지수) | HKD | 09:45-00:30 |
| SGX | 싱가포르 | CN(중국A50) | USD | 09:00-02:00 |

### 포지션 관리 (국내선물과 동일)
| 구분 | 주식 | 선물옵션 |
|------|------|---------|
| 방향성 | 매수만 | Long/Short 양방향 |
| 잔고 | 수량 | unsttl_qty (미결제약정) |
| 손익 | (현재가-매입가)×수량 | (현재가-진입가)×계약×승수 |
| 청산 | 매도 주문 | 반대 포지션 주문 |

### 데이터 매핑
| 한투 필드 | 프로젝트 필드 | 설명 |
|----------|------------|------|
| OVRS_FUTR_FX_PDNO | symbol | 종목코드 (월물포함) |
| OVRS_EXCG_CD | exchange | 거래소코드 |
| sll_buy_dvsn_cd | position_side | 01=Short, 02=Long |
| unsttl_qty | quantity | 미결제수량 |
| avg_buy_unpr | entry_price | 진입가격 |
| now_pric | current_price | 현재가 |
| frcr_evlu_pfls_amt | unrealized_pnl_usd | 평가손익(USD) |
| wcrc_evlu_pfls_amt | unrealized_pnl_krw | 평가손익(원화) |

### 계약승수 및 증거금
- **E-MINI S&P500(ES)**: 1포인트 = $50
- **E-MINI NASDAQ(NQ)**: 1포인트 = $20
- **FDAX(독일DAX)**: 1포인트 = €25
- **HSI(항셍지수)**: 1포인트 = HK$50
- **증거금**: 거래소별 개시/유지 증거금율 적용
- **손익 계산**: (현재가 - 진입가) × 계약수 × 승수 × 환율

### 환율 및 통화
- **실시간 환율**: 평가손익 계산 시 적용
- **다중 통화**: USD, EUR, HKD 등 지원
- **원화 환산**: `wcrc_*` 필드 활용
- **환 리스크**: 외화 포지션 환율 변동 고려

### 만기일 관리
- **월물코드**: ESZ4 → ES(종목) + Z(12월) + 4(2024년)
- **최종거래일**: 거래소별 상이
- **롤오버**: 만기 전 차월물로 이동
- **알림**: 만기 1주일 전 사용자 알림

### 거래시간 관리
- **24시간 거래**: 시차 고려 필요
- **서머타임**: 미국/유럽 서머타임 적용
- **휴장일**: 각 거래소별 휴장일 확인
- **야간 주문**: 한국 시간 기준 야간 거래 지원

### 에러 처리
- **증거금 부족**: 주문가능금액조회 먼저 확인
- **만기일 도래**: 거래 불가 에러 처리
- **거래시간 외**: 시장 오픈 시간 확인
- **환율 변동**: 원화 환산 손익 재계산
- **호가 단위**: 최소 틱 단위 준수
