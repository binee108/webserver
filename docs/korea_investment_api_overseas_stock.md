# 한국투자증권 API - 해외주식

## 1. 주문 API

### 1.1 해외주식주문
- **Endpoint**: `POST /uapi/overseas-stock/v1/trading/order`
- **tr_id**: 거래소별 상이 (아래 표 참조)

#### 거래소별 tr_id (실전투자)
| 거래소 | 코드 | 매수 | 매도 |
|--------|------|------|------|
| 미국 나스닥 | NASD | TTTT1002U | TTTT1006U |
| 미국 뉴욕 | NYSE | TTTT1002U | TTTT1006U |
| 미국 아멕스 | AMEX | TTTT1002U | TTTT1006U |
| 홍콩 | SEHK | TTTS1002U | TTTS1001U |
| 중국 상해 | SHAA | TTTS0202U | TTTS1005U |
| 중국 심천 | SZAA | TTTS0305U | TTTS0304U |
| 일본 | TKSE | TTTS0308U | TTTS0307U |
| 베트남 하노이 | HASE | TTTS0311U | TTTS0310U |
| 베트남 호치민 | VNSE | TTTS0311U | TTTS0310U |

**※ 모의투자**: 실전투자 TR_ID의 첫 글자 'T'를 'V'로 변경 (예: TTTT1002U → VTTT1002U)

#### 요청 (미국 기준)
```json
{
  "CANO": "12345678",
  "ACNT_PRDT_CD": "01",
  "OVRS_EXCG_CD": "NASD",        // 거래소: NASD, NYSE, AMEX, SEHK, TSE 등
  "PDNO": "AAPL",                // 종목코드 (티커)
  "ORD_QTY": "10",               // 주문수량
  "OVRS_ORD_UNPR": "150.50",     // 주문단가 (시장가는 "0")
  "ORD_SVR_DVSN_CD": "0",        // 주문서버구분: 0=해외, 1=홍콩
  "ORD_DVSN": "00",              // 00=지정가, 01=시장가
  "CTAC_TLNO": "",               // 연락전화번호
  "MGCO_APTM_ODNO": ""           // 운용사지정주문번호
}
```

#### 응답
```json
{
  "rt_cd": "0",
  "msg_cd": "MCA00000",
  "output": {
    "KRX_FWDG_ORD_ORGNO": "",
    "ODNO": "US0000123456",      // 주문번호
    "ORD_TMD": "093015"
  }
}
```

---

### 1.2 해외주식정정취소주문
- **Endpoint**: `POST /uapi/overseas-stock/v1/trading/order-rvsecncl`
- **tr_id**: `TTTS1006U` (정정), `TTTS1004U` (취소)

#### 요청
```json
{
  "CANO": "12345678",
  "ACNT_PRDT_CD": "01",
  "OVRS_EXCG_CD": "NASD",
  "PDNO": "AAPL",
  "ORGN_ODNO": "US0000123456",   // 원주문번호
  "RVSE_CNCL_DVSN_CD": "02",     // 01=정정, 02=취소
  "ORD_QTY": "0",                // 취소: "0", 정정: 새 수량
  "OVRS_ORD_UNPR": "0",          // 취소: "0", 정정: 새 가격
  "CTAC_TLNO": "",
  "MGCO_APTM_ODNO": "",
  "ORD_DVSN": "00"
}
```

---

## 2. 주문 조회 API

### 2.1 해외주식당일주문내역조회
- **Endpoint**: `GET /uapi/overseas-stock/v1/trading/inquire-order`
- **tr_id**: `TTTS3018R`

#### 요청
```
CANO=12345678
ACNT_PRDT_CD=01
OVRS_EXCG_CD=NASD
SORT_SQN=DS                    // DS=역순, AS=정순
CTX_AREA_FK200=
CTX_AREA_NK200=
```

#### 응답
```json
{
  "rt_cd": "0",
  "output": [
    {
      "ord_dt": "20241002",
      "ord_gno_brno": "00001",
      "odno": "US0000123456",
      "orgn_odno": "",
      "pdno": "AAPL",
      "prdt_name": "APPLE INC",
      "ft_ord_qty": "10",            // 주문수량
      "ft_ord_unpr3": "150.50",      // 주문단가
      "ft_ccld_qty": "10",           // 체결수량
      "ft_ccld_unpr3": "150.45",     // 체결단가
      "ft_ccld_amt3": "1504.50",     // 체결금액
      "nccs_qty": "0",               // 미체결수량
      "prdt_type_cd": "512",
      "ord_tmd": "093015",
      "ord_dvsn_name": "지정가",
      "sll_buy_dvsn_cd": "02",       // 01=매도, 02=매수
      "rvse_cncl_dvsn": "0"          // 정정취소구분
    }
  ]
}
```

---

### 2.2 해외주식미체결내역조회
- **Endpoint**: `GET /uapi/overseas-stock/v1/trading/inquire-nccs`
- **tr_id**: `TTTS3035R`

#### 요청
```
CANO=12345678
ACNT_PRDT_CD=01
OVRS_EXCG_CD=NASD
SORT_SQN=DS
CTX_AREA_FK200=
CTX_AREA_NK200=
```

#### 응답: 주식일별주문체결조회와 동일, nccs_qty > 0인 건만 반환

---

## 3. 잔고/계좌 조회 API

### 3.1 해외주식잔고조회
- **Endpoint**: `GET /uapi/overseas-stock/v1/trading/inquire-balance`
- **tr_id**: `TTTS3012R` (미국), `TTTS3039R` (아시아/유럽)

#### 요청
```
CANO=12345678
ACNT_PRDT_CD=01
OVRS_EXCG_CD=NASD
TR_CRCY_CD=USD                 // 거래통화: USD, JPY, HKD 등
CTX_AREA_FK200=
CTX_AREA_NK200=
```

#### 응답
```json
{
  "rt_cd": "0",
  "output1": [
    {
      "cano": "12345678",
      "acnt_prdt_cd": "01",
      "pdno": "AAPL",
      "prdt_name": "APPLE INC",
      "frcr_pchs_amt1": "1504.50",   // 외화매입금액
      "ovrs_cblc_qty": "10",         // 잔고수량
      "ord_psbl_qty": "10",          // 주문가능수량
      "frcr_buy_amt_smtl1": "1504.50", // 매입금액합계
      "ovrs_stck_evlu_amt": "1550.00", // 평가금액
      "frcr_evlu_pfls_amt": "45.50",   // 평가손익
      "evlu_pfls_rt": "3.02",          // 평가손익율
      "ovrs_item_acqs_unpr": "150.45", // 취득단가
      "now_pric2": "155.00",           // 현재가
      "tr_crcy_cd": "USD",             // 거래통화코드
      "ovrs_excg_cd": "NASD"
    }
  ],
  "output2": {
    "frcr_pchs_amt1": "1504.50",       // 외화매입금액
    "ovrs_rlzt_pfls_amt": "0.00",      // 실현손익
    "ovrs_tot_pfls": "45.50",          // 총손익
    "rlzt_erng_rt": "0.00",            // 실현수익률
    "tot_evlu_pfls_amt": "45.50",      // 총평가손익
    "tot_pftrt": "3.02",               // 총수익률
    "frcr_buy_amt_smtl1": "1504.50",   // 매입금액합계
    "ovrs_rlzt_pfls_amt2": "0.00",     // 실현손익2
    "frcr_buy_amt_smtl2": "1504.50"    // 매입금액합계2
  }
}
```

---

### 3.2 해외주식예수금조회
- **Endpoint**: `GET /uapi/overseas-stock/v1/trading/inquire-deposit`
- **tr_id**: `TTTS3007R`

#### 요청
```
CANO=12345678
ACNT_PRDT_CD=01
OVRS_EXCG_CD=NASD
TR_CRCY_CD=USD
```

#### 응답
```json
{
  "rt_cd": "0",
  "output": {
    "frcr_dncl_amt_2": "10000.00",     // 외화예수금
    "frcr_ord_psbl_amt1": "8495.50",   // 주문가능금액
    "frcr_evlu_tota": "11550.00",      // 평가총액
    "tot_dncl_amt": "13000000"         // 원화예수금(환산)
  }
}
```

---

### 3.3 해외주식매수가능조회
- **Endpoint**: `GET /uapi/overseas-stock/v1/trading/inquire-psbl-order`
- **tr_id**: `TTTS3013R`

#### 요청
```
CANO=12345678
ACNT_PRDT_CD=01
OVRS_EXCG_CD=NASD
PDNO=AAPL
OVRS_ORD_UNPR=155.00
TR_CRCY_CD=USD
FT_ORD_QTY=1
```

#### 응답
```json
{
  "rt_cd": "0",
  "output": {
    "max_ord_psbl_qty": "54",          // 최대주문가능수량
    "ord_psbl_frcr_amt": "8495.50",    // 주문가능외화금액
    "ovrs_max_ord_psbl_qty": "54",     // 해외최대주문가능수량
    "max_ord_psbl_qty_org": "54"       // 원최대주문가능수량
  }
}
```

---

## 4. 시세조회 API

### 4.1 해외주식현재가조회
- **Endpoint**: `GET /uapi/overseas-stock/v1/quotations/inquire-price`
- **tr_id**: `HHDFS00000300`

#### 요청
```
AUTH=                          // 공란
EXCD=NAS                       // 거래소: NAS, NYS, AMS, HKS, SHS, SZS, TSE 등
SYMB=AAPL                      // 종목코드(티커)
```

#### 응답
```json
{
  "rt_cd": "0",
  "output": {
    "rsym": "AAPL",              // 종목코드
    "zdiv": "1",                 // 소수점자리수
    "base": "150.00",            // 기준가
    "pvol": "85420000",          // 전일거래량
    "last": "155.00",            // 현재가
    "sign": "2",                 // 대비부호: 1=상한, 2=상승, 3=보합, 4=하한, 5=하락
    "diff": "5.00",              // 전일대비
    "rate": "3.33",              // 등락률
    "tvol": "42500000",          // 당일거래량
    "tamt": "6562500000",        // 당일거래대금
    "ordy": "150.00",            // 시가
    "ghpr": "156.50",            // 고가
    "glpr": "154.20",            // 저가
    "uplp": "195.00",            // 상한가
    "dnlp": "105.00",            // 하한가
    "h52p": "200.50",            // 52주최고가
    "h52d": "20240315",          // 52주최고가일
    "l52p": "120.30",            // 52주최저가
    "l52d": "20230815",          // 52주최저가일
    "perx": "28.5",              // PER
    "pbrx": "7.2",               // PBR
    "epsx": "5.44",              // EPS
    "bpsx": "21.53",             // BPS
    "shar": "16000000000",       // 상장주식수
    "mcap": "2480000000000",     // 시가총액
    "tomv": "42500000",          // 당일거래량
    "t_xprc": "155.00",          // 시간외단일가
    "t_xdff": "0.00",            // 시간외등락
    "t_xrat": "0.00",            // 시간외등락률
    "t_xsgn": "3",               // 시간외부호
    "t_xvol": "0"                // 시간외거래량
  }
}
```

---

### 4.2 해외주식호가조회
- **Endpoint**: `GET /uapi/overseas-stock/v1/quotations/inquire-asking-price`
- **tr_id**: `HHDFS76240000`

#### 요청
```
AUTH=
EXCD=NAS
SYMB=AAPL
```

#### 응답
```json
{
  "rt_cd": "0",
  "output": {
    "rsym": "AAPL",
    "zdiv": "1",
    "bass": "150.00",
    "last": "155.00",
    "askp1": "155.05",           // 매도호가1
    "askp2": "155.10",
    "askp3": "155.15",
    "askp4": "155.20",
    "askp5": "155.25",
    "bidp1": "154.95",           // 매수호가1
    "bidp2": "154.90",
    "bidp3": "154.85",
    "bidp4": "154.80",
    "bidp5": "154.75",
    "askp_rsqn1": "850",         // 매도호가잔량1
    "askp_rsqn2": "1200",
    "askp_rsqn3": "950",
    "askp_rsqn4": "1500",
    "askp_rsqn5": "800",
    "bidp_rsqn1": "1300",        // 매수호가잔량1
    "bidp_rsqn2": "1100",
    "bidp_rsqn3": "1450",
    "bidp_rsqn4": "900",
    "bidp_rsqn5": "1250"
  }
}
```

---

### 4.3 해외주식일별시세조회
- **Endpoint**: `GET /uapi/overseas-stock/v1/quotations/inquire-daily-price`
- **tr_id**: `HHDFS76240000`

#### 요청
```
AUTH=
EXCD=NAS
SYMB=AAPL
GUBN=0                         // 0=일, 1=주, 2=월
BYMD=20241002                  // 조회기준일자
MODP=1                         // 0=수정주가, 1=원주가
```

#### 응답
```json
{
  "rt_cd": "0",
  "output2": [
    {
      "xymd": "20241002",        // 일자
      "clos": "155.00",          // 종가
      "sign": "2",               // 대비부호
      "diff": "5.00",            // 대비
      "rate": "3.33",            // 등락률
      "open": "150.00",          // 시가
      "high": "156.50",          // 고가
      "low": "154.20",           // 저가
      "tvol": "42500000",        // 거래량
      "tamt": "6562500000"       // 거래대금
    }
    // ... 최대 100개
  ]
}
```

---

## 5. 거래시간/야간거래 API

### 5.1 해외주식야간주문가능여부조회
- **Endpoint**: `GET /uapi/overseas-stock/v1/quotations/inquire-night-available`
- **tr_id**: `TTTO1120R`

#### 요청
```
OVRS_EXCG_CD=NASD
```

#### 응답
```json
{
  "rt_cd": "0",
  "output": {
    "ovrs_excg_cd": "NASD",
    "ovrs_excg_cd_name": "나스닥",
    "night_yn": "Y",             // 야간주문가능여부
    "std_dt": "20241002",
    "std_tm": "093000"
  }
}
```

---

### 5.2 해외주식시장별거래가능시간조회
- **Endpoint**: `GET /uapi/overseas-stock/v1/quotations/inquire-mkt-hours`
- **tr_id**: `OTFM1411R`

#### 요청
```
OVRS_EXCG_CD=NASD
```

#### 응답
```json
{
  "rt_cd": "0",
  "output": [
    {
      "ovrs_excg_cd": "NASD",
      "ovrs_excg_cd_name": "나스닥",
      "trad_strt_hour": "230000",  // 한국시간 거래시작
      "trad_end_hour": "060000",   // 한국시간 거래종료
      "prdy_day_yn": "N",
      "hldy_yn": "N"               // 휴장여부
    }
  ]
}
```

---

## 6. 프로젝트 확장 시 고려사항

### 거래소 코드 매핑
| OVRS_EXCG_CD | 거래소 | 통화 | 시간대 |
|--------------|--------|------|--------|
| NASD | 나스닥 | USD | 23:30-06:00 KST |
| NYSE | 뉴욕증권 | USD | 23:30-06:00 KST |
| AMEX | 아멕스 | USD | 23:30-06:00 KST |
| SEHK | 홍콩증권 | HKD | 10:30-17:00 KST |
| TSE | 도쿄증권 | JPY | 09:00-15:30 KST |
| SHS | 상하이 | CNY | 10:30-16:00 KST |

### 데이터 매핑
| 한투 필드 | 프로젝트 필드 | 설명 |
|----------|------------|------|
| OVRS_EXCG_CD | exchange | 거래소코드 |
| PDNO | symbol | 종목코드(티커) |
| TR_CRCY_CD | currency | 거래통화 |
| ft_ccld_qty | filled_qty | 체결수량 |
| ft_ccld_unpr3 | filled_price | 체결가격 |
| ovrs_cblc_qty | quantity | 잔고수량 |
| frcr_evlu_pfls_amt | unrealized_pnl | 평가손익 |

### 환율 처리
- 외화 금액은 원화로 환산 필요
- 실시간 환율 API 또는 고정 환율 적용
- `frcr_*` (외화) vs `tot_*` (원화) 필드 구분

### 에러 처리
- **야간거래**: 시간 확인 후 주문
- **통화 불일치**: TR_CRCY_CD 검증
- **거래소 휴장**: hldy_yn 확인
