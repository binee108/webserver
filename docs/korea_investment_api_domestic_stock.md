# 한국투자증권 API - 국내주식

## 1. 주문 API

### 1.1 주식주문(현금)
- **Endpoint**: `POST /uapi/domestic-stock/v1/trading/order-cash`
- **tr_id**: `TTTC0802U` (매수), `TTTC0801U` (매도)

#### 요청
```json
{
  "CANO": "12345678",           // 종합계좌번호 앞 8자리
  "ACNT_PRDT_CD": "01",         // 계좌상품코드 뒤 2자리
  "PDNO": "005930",             // 종목코드 (6자리)
  "ORD_DVSN": "00",             // 주문구분: 00=지정가, 01=시장가
  "ORD_QTY": "10",              // 주문수량
  "ORD_UNPR": "70000",          // 주문단가 (시장가는 "0")
  "EXCG_ID_DVSN_CD": "",        // 거래소구분코드 (공란)
  "SLL_TYPE": "01",             // 매도유형: 01=보통, 02=유통융자상환
  "CNDT_PRIC": ""               // 조건가격 (공란)
}
```

#### 응답
```json
{
  "rt_cd": "0",
  "msg_cd": "MCA00000",
  "msg1": "주문이 완료되었습니다",
  "output": {
    "KRX_FWDG_ORD_ORGNO": "91252",      // 주문조직번호
    "ODNO": "0000117057",                // 주문번호
    "ORD_TMD": "121520"                  // 주문시각
  }
}
```

#### 주문구분 코드 (ORD_DVSN)
- `00`: 지정가
- `01`: 시장가
- `02`: 조건부지정가
- `03`: 최유리지정가
- `04`: 최우선지정가
- `05`: 장전 시간외
- `06`: 장후 시간외
- `07`: 시간외 단일가

---

### 1.2 주식주문(정정취소)
- **Endpoint**: `POST /uapi/domestic-stock/v1/trading/order-rvsecncl`
- **tr_id**: `TTTC0803U` (정정), `TTTC0804U` (취소)

#### 요청
```json
{
  "CANO": "12345678",
  "ACNT_PRDT_CD": "01",
  "KRX_FWDG_ORD_ORGNO": "91252",   // 원주문 조직번호
  "ORGN_ODNO": "0000117057",       // 원주문번호
  "ORD_DVSN": "00",                // 정정 시 새 주문구분
  "RVSE_CNCL_DVSN_CD": "01",       // 01=정정, 02=취소
  "ORD_QTY": "5",                  // 정정 시 새 수량 (취소는 "0")
  "ORD_UNPR": "71000",             // 정정 시 새 가격 (취소는 "0")
  "QTY_ALL_ORD_YN": "Y"            // 전량취소: Y, 일부취소: N
}
```

#### 응답
```json
{
  "rt_cd": "0",
  "msg_cd": "MCA00000",
  "msg1": "정정(취소)가 완료되었습니다",
  "output": {
    "KRX_FWDG_ORD_ORGNO": "91252",
    "ODNO": "0000117058",
    "ORD_TMD": "121535"
  }
}
```

---

## 2. 주문 조회 API

### 2.1 주식일별주문체결조회
- **Endpoint**: `GET /uapi/domestic-stock/v1/trading/inquire-daily-ccld`
- **tr_id**: `TTTC8001R` (실전), `VTTC8001R` (모의)

#### 요청 (Query String)
```
CANO=12345678
ACNT_PRDT_CD=01
INQR_STRT_DT=20241001      // 조회시작일자
INQR_END_DT=20241002       // 조회종료일자
SLL_BUY_DVSN_CD=00         // 00=전체, 01=매도, 02=매수
INQR_DVSN=00               // 00=역순, 01=정순
PDNO=                      // 종목코드 (전체 조회 시 공란)
CCLD_DVSN=00               // 00=전체, 01=체결, 02=미체결
ORD_GNO_BRNO=              // 주문채번지점번호
ODNO=                      // 주문번호
INQR_DVSN_3=00             // 00=전체, 01=현금, 02=융자
INQR_DVSN_1=               // 공란
CTX_AREA_FK100=            // 연속조회검색조건 (최초 공란)
CTX_AREA_NK100=            // 연속조회키 (최초 공란)
```

#### 응답
```json
{
  "rt_cd": "0",
  "msg_cd": "MCA00000",
  "msg1": "정상",
  "output1": [
    {
      "ord_dt": "20241002",           // 주문일자
      "ord_gno_brno": "06010",        // 주문채번지점번호
      "odno": "0000117057",           // 주문번호
      "orgn_odno": "0000000000",      // 원주문번호
      "ord_dvsn_name": "지정가",       // 주문구분명
      "sll_buy_dvsn_cd": "02",        // 매도매수구분: 01=매도, 02=매수
      "sll_buy_dvsn_cd_name": "매수",
      "pdno": "005930",               // 종목코드
      "prdt_name": "삼성전자",         // 종목명
      "ord_qty": "10",                // 주문수량
      "ord_unpr": "70000",            // 주문단가
      "ord_tmd": "121520",            // 주문시각
      "tot_ccld_qty": "10",           // 총체결수량
      "avg_prvs": "69950",            // 평균가
      "cncl_yn": "N",                 // 취소여부
      "tot_ccld_amt": "699500",       // 총체결금액
      "loan_dt": "",                  // 대출일자
      "ord_dvsn_cd": "00",            // 주문구분코드
      "cncl_cfrm_qty": "0",           // 취소확인수량
      "rmn_qty": "0",                 // 잔여수량
      "rjct_qty": "0",                // 거부수량
      "ccld_cndt_name": "체결",        // 체결조건명
      "infm_tmd": "121521",           // 통보시각
      "ctac_tlno": "",                // 연락전화번호
      "prdt_type_cd": "300",          // 상품유형코드
      "excg_dvsn_cd": "01"            // 거래소구분코드
    }
  ],
  "output2": {
    "tot_ord_qty": "10",              // 총주문수량
    "tot_ccld_qty": "10",             // 총체결수량
    "pchs_avg_pric": "69950",         // 매입평균가격
    "tot_ccld_amt": "699500",         // 총체결금액
    "prsm_tlex_smtl": "2098"          // 추정제비용합계
  },
  "ctx_area_fk100": "",               // 연속조회검색조건100
  "ctx_area_nk100": ""                // 연속조회키100
}
```

---

### 2.2 주식미체결내역조회
- **Endpoint**: `GET /uapi/domestic-stock/v1/trading/inquire-nccs`
- **tr_id**: `TTTC8036R`

#### 요청 (Query String)
```
CANO=12345678
ACNT_PRDT_CD=01
INQR_DVSN_1=0              // 0=조회순서
INQR_DVSN_2=0              // 0=전체
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
      "ord_gno_brno": "06010",
      "odno": "0000117060",
      "orgn_odno": "0000000000",
      "pdno": "000660",
      "prdt_name": "SK하이닉스",
      "ord_qty": "5",
      "ord_unpr": "130000",
      "ord_tmd": "135500",
      "tot_ccld_qty": "0",
      "rmn_qty": "5",               // 미체결수량
      "ord_dvsn_name": "지정가",
      "sll_buy_dvsn_cd_name": "매수"
    }
  ]
}
```

---

## 3. 잔고/계좌 조회 API

### 3.1 주식잔고조회
- **Endpoint**: `GET /uapi/domestic-stock/v1/trading/inquire-balance`
- **tr_id**: `TTTC8434R` (실전), `VTTC8434R` (모의)

#### 요청 (Query String)
```
CANO=12345678
ACNT_PRDT_CD=01
AFHR_FLPR_YN=N             // 시간외단일가여부
OFL_YN=                    // 오프라인여부
INQR_DVSN=01               // 조회구분: 01=대출일별, 02=종목별
UNPR_DVSN=01               // 단가구분: 01=기본
FUND_STTL_ICLD_YN=N        // 펀드결제분포함여부
FNCG_AMT_AUTO_RDPT_YN=N    // 융자금액자동상환여부
PRCS_DVSN=00               // 처리구분: 00=전일매매포함, 01=전일매매미포함
CTX_AREA_FK100=
CTX_AREA_NK100=
```

#### 응답
```json
{
  "rt_cd": "0",
  "output1": [
    {
      "pdno": "005930",              // 종목코드
      "prdt_name": "삼성전자",        // 종목명
      "trad_dvsn_name": "",          // 매매구분명
      "bfdy_buy_qty": "0",           // 전일매수수량
      "bfdy_sll_qty": "0",           // 전일매도수량
      "thdt_buyqty": "10",           // 금일매수수량
      "thdt_sll_qty": "0",           // 금일매도수량
      "hldg_qty": "10",              // 보유수량
      "ord_psbl_qty": "10",          // 주문가능수량
      "pchs_avg_pric": "69950.00",   // 매입평균가격
      "pchs_amt": "699500",          // 매입금액
      "prpr": "70100",               // 현재가
      "evlu_amt": "701000",          // 평가금액
      "evlu_pfls_amt": "1500",       // 평가손익금액
      "evlu_pfls_rt": "0.21",        // 평가손익율
      "evlu_erng_rt": "0.21",        // 평가수익률
      "loan_dt": "",                 // 대출일자
      "loan_amt": "0",               // 대출금액
      "stln_slng_chgs": "0",         // 대주매각대금
      "expd_dt": "",                 // 만기일자
      "fltt_rt": "0.00",             // 등락율
      "bfdy_cprs_icdc": "+150",      // 전일대비증감
      "item_mgna_rt_name": "",       // 종목증거금율명
      "grta_rt_name": "",            // 보증금율명
      "sbst_pric": "70100",          // 대용가격
      "stck_loan_unpr": "0.00"       // 주식대출단가
    }
  ],
  "output2": [
    {
      "dnca_tot_amt": "5000000",     // 예수금총금액
      "nxdy_excc_amt": "4298402",    // 익일정산금액
      "prvs_rcdl_excc_amt": "0",     // 가수도정산금액
      "cma_evlu_amt": "0",           // CMA평가금액
      "bfdy_buy_amt": "0",           // 전일매수금액
      "thdt_buy_amt": "699500",      // 금일매수금액
      "nxdy_auto_rdpt_amt": "0",     // 익일자동상환금액
      "bfdy_sll_amt": "0",           // 전일매도금액
      "thdt_sll_amt": "0",           // 금일매도금액
      "d2_auto_rdpt_amt": "0",       // D+2자동상환금액
      "bfdy_tlex_amt": "0",          // 전일제비용금액
      "thdt_tlex_amt": "2098",       // 금일제비용금액
      "tot_loan_amt": "0",           // 총대출금액
      "scts_evlu_amt": "701000",     // 유가평가금액
      "tot_evlu_amt": "5701000",     // 총평가금액
      "nass_amt": "5698902",         // 순자산금액
      "fncg_gld_auto_rdpt_yn": "N",  // 융자금자동상환여부
      "pchs_amt_smtl_amt": "699500", // 매입금액합계금액
      "evlu_amt_smtl_amt": "701000", // 평가금액합계금액
      "evlu_pfls_smtl_amt": "1500",  // 평가손익합계금액
      "tot_stln_slng_chgs": "0",     // 총대주매각대금
      "bfdy_tot_asst_evlu_amt": "5000000", // 전일총자산평가금액
      "asst_icdc_amt": "698902",     // 자산증감액
      "asst_icdc_erng_rt": "13.98"   // 자산증감수익률
    }
  ]
}
```

---

### 3.2 매수가능조회
- **Endpoint**: `GET /uapi/domestic-stock/v1/trading/inquire-psbl-order`
- **tr_id**: `TTTC8908R`

#### 요청 (Query String)
```
CANO=12345678
ACNT_PRDT_CD=01
PDNO=005930                // 종목코드
ORD_UNPR=70000             // 주문단가
ORD_DVSN=00                // 주문구분
CMA_EVLU_AMT_ICLD_YN=N     // CMA평가금액포함여부
OVRS_ICLD_YN=N             // 해외포함여부
```

#### 응답
```json
{
  "rt_cd": "0",
  "output": {
    "ord_psbl_cash": "4298402",      // 주문가능현금
    "ord_psbl_sbst": "0",            // 주문가능대용
    "ruse_psbl_amt": "0",            // 재사용가능금액
    "fund_rpch_chgs": "0",           // 펀드환매대금
    "psbl_qty_calc_unpr": "70000",   // 가능수량계산단가
    "nrcvb_buy_amt": "0",            // 미수없는매수금액
    "nrcvb_buy_qty": "61",           // 미수없는매수수량
    "max_buy_amt": "4298402",        // 최대매수금액
    "max_buy_qty": "61",             // 최대매수수량
    "cma_evlu_amt": "0",             // CMA평가금액
    "ovrs_re_use_amt_wcrc": "0",     // 해외재사용금액원화
    "ord_psbl_frcr_amt": "0.00"      // 주문가능외화금액
  }
}
```

---

### 3.3 예수금조회
- **Endpoint**: `GET /uapi/domestic-stock/v1/trading/inquire-deposit`
- **tr_id**: `TTTC3014R`

#### 요청
```
CANO=12345678
ACNT_PRDT_CD=01
INQR_DVSN_1=00             // 조회구분
INQR_DVSN_2=00
```

#### 응답
```json
{
  "rt_cd": "0",
  "output": {
    "prvs_rcdl_excc_amt": "0",       // 가수도정산금액
    "cma_evlu_amt": "0",             // CMA평가금액
    "tot_evlu_amt": "5701000",       // 총평가금액
    "nxdy_excc_amt": "4298402",      // 익일정산금액
    "dnca_tot_amt": "5000000",       // 예수금총금액
    "d2_auto_rdpt_amt": "0",         // D+2자동상환금액
    "d1_dncl_amt": "4298402",        // D+1예수금액
    "d2_dncl_amt": "4298402"         // D+2예수금액
  }
}
```

---

## 4. 시세조회 API

### 4.1 주식현재가
- **Endpoint**: `GET /uapi/domestic-stock/v1/quotations/inquire-price`
- **tr_id**: `FHKST01010100`

#### 요청 (Query String)
```
FID_COND_MRKT_DIV_CODE=J   // 시장분류코드: J=주식, ETF/ETN, ELW
FID_INPUT_ISCD=005930      // 종목코드
```

#### 응답
```json
{
  "rt_cd": "0",
  "output": {
    "stck_prpr": "70100",            // 주식현재가
    "prdy_vrss": "150",              // 전일대비
    "prdy_vrss_sign": "2",           // 전일대비부호: 1=상한, 2=상승, 3=보합, 4=하한, 5=하락
    "prdy_ctrt": "0.21",             // 전일대비율
    "stck_oprc": "69950",            // 시가
    "stck_hgpr": "70500",            // 고가
    "stck_lwpr": "69800",            // 저가
    "stck_mxpr": "90950",            // 상한가
    "stck_llam": "48950",            // 하한가
    "stck_sdpr": "69950",            // 기준가
    "wghn_avrg_stck_prc": "70050",   // 가중평균주식가격
    "hts_frgn_ehrt": "52.15",        // 외국인소진율
    "frgn_ntby_qty": "-512300",      // 외국인순매수수량
    "pgtr_ntby_qty": "85200",        // 프로그램순매수수량
    "pvt_scnd_dmrs_prc": "0",        // 피벗2차디저항가격
    "pvt_frst_dmrs_prc": "0",        // 피벗1차디저항가격
    "pvt_pont_val": "0",             // 피벗포인트값
    "pvt_frst_dmsp_prc": "0",        // 피벗1차디지지가격
    "pvt_scnd_dmsp_prc": "0",        // 피벗2차디지지가격
    "acml_vol": "12560000",          // 누적거래량
    "acml_tr_pbmn": "880500000000",  // 누적거래대금
    "seln_cntg_qty": "0",            // 매도호가잔량
    "shnu_cntg_qty": "0",            // 매수호가잔량
    "ntby_cntg_qty": "0",            // 순매수잔량
    "cttr": "0.18",                  // 체결강도
    "seln_cntg_smtn": "405000",      // 총매도수량
    "shnu_cntg_smtn": "562000",      // 총매수수량
    "ccld_dvsn": "1",                // 체결구분: 1=장중, 2=장전, 3=장후
    "shnu_rate": "57.56",            // 매수비율
    "prdy_vol_vrss_acml_vol_rate": "125.60", // 전일거래량대비등락율
    "oprc_rang_cont_yn": "N",        // 시가범위연장여부
    "cnnt_ascn_dynu": "1",           // 연속상승일수
    "hts_deal_qty_unit_val": "1",    // 매매수량단위
    "lstn_stcn": "5969783000",       // 상장주수
    "hts_avls": "418324983000000",   // 시가총액
    "per": "25.50",                  // PER
    "pbr": "1.45",                   // PBR
    "stac_month": "12",              // 결산월
    "vol_tnrt": "0.21",              // 거래량회전율
    "eps": "2750.00",                // EPS
    "bps": "48350.00",               // BPS
    "itewhol_loan_rmnd_ratem": "0.15" // 전체융자잔고비율
  }
}
```

---

### 4.2 주식호가
- **Endpoint**: `GET /uapi/domestic-stock/v1/quotations/inquire-asking-price`
- **tr_id**: `FHKST01010200`

#### 요청
```
FID_COND_MRKT_DIV_CODE=J
FID_INPUT_ISCD=005930
```

#### 응답
```json
{
  "rt_cd": "0",
  "output1": {
    "aspr_acpt_hour": "135530",      // 호가접수시각
    "askp1": "70200",                // 매도호가1
    "askp2": "70300",                // 매도호가2
    "askp3": "70400",
    "askp4": "70500",
    "askp5": "70600",
    "askp6": "70700",
    "askp7": "70800",
    "askp8": "70900",
    "askp9": "71000",
    "askp10": "71100",               // 매도호가10
    "bidp1": "70100",                // 매수호가1
    "bidp2": "70000",                // 매수호가2
    "bidp3": "69900",
    "bidp4": "69800",
    "bidp5": "69700",
    "bidp6": "69600",
    "bidp7": "69500",
    "bidp8": "69400",
    "bidp9": "69300",
    "bidp10": "69200",               // 매수호가10
    "askp_rsqn1": "1200",            // 매도호가잔량1
    "askp_rsqn2": "850",
    "askp_rsqn3": "1500",
    "askp_rsqn4": "2300",
    "askp_rsqn5": "1800",
    "askp_rsqn6": "950",
    "askp_rsqn7": "1200",
    "askp_rsqn8": "800",
    "askp_rsqn9": "1500",
    "askp_rsqn10": "2000",
    "bidp_rsqn1": "1500",            // 매수호가잔량1
    "bidp_rsqn2": "2200",
    "bidp_rsqn3": "1800",
    "bidp_rsqn4": "1300",
    "bidp_rsqn5": "2500",
    "bidp_rsqn6": "1100",
    "bidp_rsqn7": "1700",
    "bidp_rsqn8": "900",
    "bidp_rsqn9": "1400",
    "bidp_rsqn10": "1900",
    "total_askp_rsqn": "14100",      // 총매도호가잔량
    "total_bidp_rsqn": "16300",      // 총매수호가잔량
    "ovtm_total_askp_rsqn": "0",     // 시간외총매도호가잔량
    "ovtm_total_bidp_rsqn": "0",     // 시간외총매수호가잔량
    "antc_cnpr": "70100",            // 예상체결가
    "antc_cnqn": "5000",             // 예상체결량
    "antc_vol": "0",                 // 예상거래량
    "antc_cntg_vrss": "150",         // 예상체결대비
    "antc_cntg_vrss_sign": "2",      // 예상체결전일대비부호
    "antc_cntg_prdy_ctrt": "0.21",   // 예상체결전일대비율
    "acml_vol": "12560000",          // 누적거래량
    "total_askp_rsqn_icdc": "-2200", // 총매도호가잔량증감
    "total_bidp_rsqn_icdc": "1800",  // 총매수호가잔량증감
    "ovtm_total_askp_icdc": "0",     // 시간외총매도호가증감
    "ovtm_total_bidp_icdc": "0",     // 시간외총매수호가증감
    "stck_deal_cl_code": "01",       // 주식매매구분코드
    "stck_prpr": "70100",            // 주식현재가
    "prdy_vrss": "150",              // 전일대비
    "prdy_vrss_sign": "2",           // 전일대비부호
    "prdy_ctrt": "0.21"              // 전일대비율
  },
  "output2": {
    "askp_rsqn_icdc1": "-100",       // 매도호가잔량증감1
    "bidp_rsqn_icdc1": "200"         // 매수호가잔량증감1
    // ... 10단계까지
  }
}
```

---

### 4.3 주식일별시세
- **Endpoint**: `GET /uapi/domestic-stock/v1/quotations/inquire-daily-price`
- **tr_id**: `FHKST01010400`

#### 요청
```
FID_COND_MRKT_DIV_CODE=J
FID_INPUT_ISCD=005930
FID_PERIOD_DIV_CODE=D      // D=일, W=주, M=월
FID_ORG_ADJ_PRC=0          // 0=수정주가, 1=원주가
```

#### 응답
```json
{
  "rt_cd": "0",
  "output": [
    {
      "stck_bsop_date": "20241002",  // 영업일자
      "stck_oprc": "69950",          // 시가
      "stck_hgpr": "70500",          // 고가
      "stck_lwpr": "69800",          // 저가
      "stck_clpr": "70100",          // 종가
      "acml_vol": "12560000",        // 누적거래량
      "prdy_vrss_vol_rate": "125.60", // 전일대비거래량비율
      "prdy_vrss": "150",            // 전일대비
      "prdy_vrss_sign": "2",         // 전일대비부호
      "prdy_ctrt": "0.21",           // 전일대비율
      "hts_frgn_ehrt": "52.15",      // 외국인소진율
      "frgn_ntby_qty": "-512300",    // 외국인순매수수량
      "flng_cls_code": "00",         // 락구분코드
      "acml_prtt_rate": "0.00"       // 누적분할비율
    }
    // ... 최대 100개
  ]
}
```

---

## 5. 종목정보 API

### 5.1 종목기본정보조회
- **Endpoint**: `GET /uapi/domestic-stock/v1/quotations/inquire-basic-info`
- **tr_id**: `FHKST01010900`

#### 요청
```
FID_COND_MRKT_DIV_CODE=J
FID_INPUT_ISCD=005930
```

#### 응답
```json
{
  "rt_cd": "0",
  "output": {
    "pdno": "005930",                // 상품번호
    "prdt_type_cd": "300",           // 상품유형코드
    "prdt_name": "삼성전자",          // 상품명
    "prdt_name120": "삼성전자",
    "prdt_abrv_name": "삼성전자",     // 상품약어명
    "prdt_eng_name": "SamsungElec",  // 상품영문명
    "prdt_eng_name120": "Samsung Electronics Co., Ltd.",
    "std_pdno": "KR7005930003",      // 표준상품번호
    "shtn_pdno": "A005930",          // 단축상품번호
    "prdt_sale_stat_cd": "00",       // 상품판매상태코드
    "prdt_risk_grad_cd": "00",       // 상품위험등급코드
    "prdt_clsf_cd": "0101",          // 상품분류코드
    "prdt_clsf_name": "주권",         // 상품분류명
    "sale_strt_dt": "19880111",      // 판매시작일자
    "sale_end_dt": "99991231",       // 판매종료일자
    "wrap_asst_type_cd": "00",       // 랩자산유형코드
    "ivst_prdt_type_cd": "01",       // 투자상품유형코드
    "ivst_prdt_type_cd_name": "증권", // 투자상품유형코드명
    "frst_erlm_dt": "19750613"       // 최초등록일자
  }
}
```

---

## 6. 프로젝트 확장 시 고려사항

### 데이터 매핑
| 한투 필드 | 프로젝트 필드 | 설명 |
|----------|------------|------|
| CANO + ACNT_PRDT_CD | account_id | 계좌 식별자 |
| PDNO | symbol | 종목코드 |
| ODNO | order_id | 주문번호 |
| hldg_qty | quantity | 보유수량 |
| pchs_avg_pric | avg_price | 평균단가 |
| evlu_pfls_amt | unrealized_pnl | 평가손익 |

### 주문구분 매핑
| ORD_DVSN | ORDER_TYPE |
|----------|-----------|
| 00 | LIMIT |
| 01 | MARKET |
| 02 | CONDITIONAL_LIMIT |
| 03 | BEST_LIMIT |
| 05 | PRE_MARKET |
| 06 | AFTER_MARKET |

### 에러 처리
- **rt_cd="1"**: API 호출 실패 → msg1 확인
- **토큰 만료**: 401 에러 → 토큰 재발급 후 재시도
- **해시키 불일치**: hashkey 재생성 후 재시도
- **잔량 부족**: 매수가능조회 먼저 확인
