"""
한국투자증권 API 어댑터

BaseSecuritiesExchange를 상속하여 한국투자증권 REST API를 구현합니다.
"""

import logging
import hashlib
import base64
import aiohttp
from typing import Dict, List, Optional, Any
from decimal import Decimal
from datetime import datetime, timedelta

from .base import BaseSecuritiesExchange
from .models import StockOrder, StockBalance, StockPosition, StockQuote
from .exceptions import (
    AuthenticationError,
    NetworkError,
    InvalidOrder,
    OrderNotFound,
    InsufficientBalance,
    MarketClosed
)

logger = logging.getLogger(__name__)


class KoreaInvestmentExchange(BaseSecuritiesExchange):
    """
    한국투자증권 API 어댑터

    특징:
    - OAuth 2.0 기반 인증 (24시간 유효)
    - SHA256 해시키를 사용한 주문 보안
    - 실전투자/모의투자 환경 분리
    """

    # API 도메인
    DOMAIN_REAL = 'https://openapi.koreainvestment.com:9443'
    DOMAIN_VIRTUAL = 'https://openapivts.koreainvestment.com:29443'

    def __init__(self, account: 'Account'):
        super().__init__(account)

        # 설정 로드
        config = account.securities_config
        self.appkey = config.get('appkey')
        self.appsecret = config.get('appsecret')
        self.account_number = config.get('account_number')  # "12345678-01" 형식
        self.is_virtual = config.get('is_virtual', False)  # 모의투자 여부

        # 도메인 설정
        self.base_url = self.DOMAIN_VIRTUAL if self.is_virtual else self.DOMAIN_REAL

        # 유효성 검증
        if not self.appkey or not self.appsecret:
            raise ValueError(f"한투 계좌 설정 누락: appkey, appsecret 필요 (account_id={account.id})")
        if not self.account_number or '-' not in self.account_number:
            raise ValueError(f"계좌번호 형식 오류: '계좌번호8자리-상품코드2자리' 형식 필요 (account_id={account.id})")

        # 계좌번호 분리
        self.cano, self.acnt_prdt_cd = self.account_number.split('-')

        logger.info(f"✅ 한국투자증권 어댑터 초기화 (계좌: {self.cano[-4:]}, 모의: {self.is_virtual})")

    # ========================================
    # OAuth 인증
    # ========================================

    async def authenticate(self) -> Dict[str, Any]:
        """
        OAuth 토큰 발급

        API: [인증-001] POST /oauth2/tokenP

        Returns:
            {
                'access_token': str,
                'token_type': str,  # 'Bearer'
                'expires_in': int,  # 86400 (24시간)
                'expires_at': datetime
            }

        Raises:
            AuthenticationError: 인증 실패
        """
        url = f"{self.base_url}/oauth2/tokenP"
        headers = {
            'content-type': 'application/json'
        }
        body = {
            'grant_type': 'client_credentials',
            'appkey': self.appkey,
            'appsecret': self.appsecret
        }

        logger.info(f"🔑 한투 OAuth 토큰 발급 요청 (account_id={self.account.id})")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=body, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    data = await response.json()

                    # 에러 응답 처리
                    if data.get('msg_cd') != 'O0001':
                        error_msg = data.get('msg1', 'Unknown error')
                        logger.error(f"❌ 한투 OAuth 실패: {data.get('msg_cd')} - {error_msg}")
                        raise AuthenticationError(
                            f"한투 토큰 발급 실패: {error_msg}",
                            code=data.get('msg_cd'),
                            response=data
                        )

                    # 성공 응답 파싱
                    access_token = data['access_token']
                    expires_in = data['expires_in']
                    expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

                    logger.info(f"✅ 한투 OAuth 성공 (만료: {expires_at}, 유효기간: {expires_in}초)")

                    return {
                        'access_token': access_token,
                        'token_type': data.get('token_type', 'Bearer'),
                        'expires_in': expires_in,
                        'expires_at': expires_at
                    }

        except aiohttp.ClientError as e:
            logger.error(f"❌ 한투 OAuth 네트워크 에러: {e}")
            raise NetworkError(f"한투 OAuth 네트워크 에러: {e}")
        except KeyError as e:
            logger.error(f"❌ 한투 OAuth 응답 파싱 실패: {e}, data={data}")
            raise AuthenticationError(f"한투 OAuth 응답 형식 오류: 필수 필드 {e} 누락")

    async def refresh_token(self) -> Dict[str, Any]:
        """
        OAuth 토큰 갱신

        한투 API는 6시간 이내 재요청 시 기존 토큰을 반환하므로,
        실제로는 authenticate()와 동일하게 동작합니다.

        Returns:
            authenticate()와 동일한 포맷
        """
        logger.info(f"🔄 한투 토큰 갱신 (실제로는 재발급, account_id={self.account.id})")
        return await self.authenticate()

    # ========================================
    # 해시키 생성 (주문 API 보안)
    # ========================================

    async def generate_hashkey(self, data: Dict[str, Any]) -> str:
        """
        SHA256 해시키 생성 (로컬 생성)

        주문 API 위변조 방지를 위해 요청 데이터를 SHA256 해시하여 Base64 인코딩합니다.

        생성 절차:
        1. 요청 Body의 모든 Key:Value를 정렬하여 문자열로 조합
        2. App Key + App Secret + 데이터 조합
        3. SHA256 해시 및 Base64 인코딩

        Args:
            data: 주문 요청 Body (JSON 딕셔너리)

        Returns:
            str: Base64 인코딩된 해시키

        Raises:
            NetworkError: 해시키 생성 중 오류 발생

        Example:
            >>> body = {"CANO": "12345678", "PDNO": "005930"}
            >>> hashkey = await exchange.generate_hashkey(body)
            >>> print(len(hashkey))  # Base64 문자열 (44자)
        """
        try:
            # 1. 요청 데이터를 정렬된 문자열로 조합
            # Key-Value 쌍을 알파벳 순으로 정렬하여 일관성 보장
            sorted_items = sorted(data.items())
            data_str = '|'.join([f"{k}={v}" for k, v in sorted_items])

            # 2. App Key + App Secret + 데이터 조합
            # 형식: "appkey|appsecret|key1=value1|key2=value2|..."
            combined = f"{self.appkey}|{self.appsecret}|{data_str}"

            # 3. SHA256 해시 생성
            hash_obj = hashlib.sha256(combined.encode('utf-8'))

            # 4. Base64 인코딩
            hashkey = base64.b64encode(hash_obj.digest()).decode('utf-8')

            logger.debug(f"🔐 해시키 생성 성공 (입력: {len(data)}개 필드, 출력: {len(hashkey)}자)")
            return hashkey

        except Exception as e:
            logger.error(f"❌ 해시키 생성 실패: {e}")
            raise NetworkError(f"해시키 생성 중 오류 발생: {e}")

    # ========================================
    # 국내주식 주문
    # ========================================

    async def create_stock_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: int,
        price: Optional[Decimal] = None,
        **params
    ) -> StockOrder:
        """
        국내주식 주문 생성

        API: [1.1 주식주문(현금)] POST /uapi/domestic-stock/v1/trading/order-cash

        Args:
            symbol: 종목코드 (6자리, ETN은 7자리)
            side: 'BUY' or 'SELL'
            order_type: 'LIMIT' or 'MARKET'
            quantity: 주문수량
            price: 주문단가 (LIMIT 필수, MARKET은 None)

        Returns:
            StockOrder: 주문 정보

        Raises:
            AuthenticationError: 인증 실패
            InvalidOrder: 잘못된 주문 파라미터
            InsufficientBalance: 잔액 부족
            NetworkError: 네트워크 에러
        """
        # 1. 토큰 자동 갱신
        token = await self.ensure_token()

        # 2. 파라미터 검증
        if order_type not in ('LIMIT', 'MARKET'):
            raise InvalidOrder(f"지원하지 않는 주문구분: {order_type} (LIMIT, MARKET만 가능)")

        if order_type == 'LIMIT' and price is None:
            raise InvalidOrder("LIMIT 주문은 price가 필수입니다")

        if side not in ('BUY', 'SELL'):
            raise InvalidOrder(f"잘못된 side: {side} (BUY, SELL만 가능)")

        # 3. 주문구분 코드 매핑
        ord_dvsn_map = {
            'LIMIT': '00',   # 지정가
            'MARKET': '01'   # 시장가
        }
        ord_dvsn = ord_dvsn_map[order_type]

        # 4. 주문단가 설정 (시장가는 "0")
        ord_unpr = str(int(price)) if order_type == 'LIMIT' and price else "0"

        # 5. tr_id 선택 (매수/매도, 실전/모의)
        if self.is_virtual:
            tr_id = 'VTTC0012U' if side == 'BUY' else 'VTTC0011U'
        else:
            tr_id = 'TTTC0012U' if side == 'BUY' else 'TTTC0011U'

        # 6. 요청 Body 생성
        body = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "PDNO": symbol,
            "ORD_DVSN": ord_dvsn,
            "ORD_QTY": str(quantity),
            "ORD_UNPR": ord_unpr
        }

        # 7. 해시키 생성
        hashkey = await self.generate_hashkey(body)

        # 8. API 요청 전송
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/order-cash"
        headers = {
            'content-type': 'application/json',
            'authorization': f'Bearer {token}',
            'appkey': self.appkey,
            'appsecret': self.appsecret,
            'tr_id': tr_id,
            'hashkey': hashkey
        }

        logger.info(f"📤 한투 주문 생성 요청: {side} {order_type} {symbol} {quantity}주 @{ord_unpr}")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=body, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    data = await response.json()

                    # 9. 에러 응답 처리
                    rt_cd = data.get('rt_cd')
                    msg_cd = data.get('msg_cd')
                    msg1 = data.get('msg1', 'Unknown error')

                    if rt_cd != '0':
                        logger.error(f"❌ 한투 주문 실패: rt_cd={rt_cd}, msg_cd={msg_cd}, msg={msg1}")

                        # 에러 유형별 예외 분류
                        if 'token' in msg1.lower() or 'auth' in msg1.lower():
                            raise AuthenticationError(f"한투 주문 인증 실패: {msg1}", code=msg_cd, response=data)
                        elif '잔고' in msg1 or '부족' in msg1 or 'insufficient' in msg1.lower():
                            raise InsufficientBalance(f"한투 주문 잔액 부족: {msg1}", code=msg_cd, response=data)
                        elif '파라미터' in msg1 or 'parameter' in msg1.lower() or '형식' in msg1:
                            raise InvalidOrder(f"한투 주문 파라미터 오류: {msg1}", code=msg_cd, response=data)
                        else:
                            raise InvalidOrder(f"한투 주문 실패: {msg1}", code=msg_cd, response=data)

                    # 10. 성공 응답 확인
                    if msg_cd != 'MCA00000':
                        logger.warning(f"⚠️ 한투 주문 비정상 응답: msg_cd={msg_cd}, msg={msg1}")

                    # 11. StockOrder 모델 변환
                    output1 = data.get('output1', {})
                    order_id = output1.get('ODNO', '')
                    order_time = output1.get('ORD_TMD', '')

                    logger.info(f"✅ 한투 주문 성공: 주문번호={order_id}, 주문시각={order_time}")

                    # 12. 요청 파라미터와 함께 StockOrder 생성
                    stock_order = StockOrder.from_kis_response(
                        data,
                        symbol=symbol,
                        side=side,
                        order_type=order_type,
                        quantity=quantity,
                        price=price
                    )

                    return stock_order

        except aiohttp.ClientError as e:
            logger.error(f"❌ 한투 주문 네트워크 에러: {e}")
            raise NetworkError(f"한투 주문 네트워크 에러: {e}")
        except KeyError as e:
            logger.error(f"❌ 한투 주문 응답 파싱 실패: {e}, data={data}")
            raise InvalidOrder(f"한투 주문 응답 형식 오류: 필수 필드 {e} 누락")

    async def cancel_stock_order(self, order_id: str, symbol: str) -> bool:
        """
        국내주식 주문 취소

        API: [1.2 주식주문(정정취소)] POST /uapi/domestic-stock/v1/trading/order-rvsecncl

        Args:
            order_id: 한투 주문번호 (ODNO)
            symbol: 종목코드

        Returns:
            bool: 취소 성공 시 True

        Raises:
            AuthenticationError: 인증 실패
            InvalidOrder: 취소 불가능한 주문
            OrderNotFound: 존재하지 않는 주문
            NetworkError: 네트워크 에러

        Note:
            - 한투 API는 취소 시 KRX_FWDG_ORD_ORGNO (주문조직번호)가 필요함
            - fetch_order()로 조직번호를 조회하여 취소하도록 구현
        """
        # 1. 토큰 자동 갱신
        token = await self.ensure_token()

        # 2. 주문 조회하여 KRX_FWDG_ORD_ORGNO 획득
        try:
            order = await self.fetch_order(order_id, symbol)
            krx_org_no = order.raw_data.get('output1', {}).get('ord_gno_brno', '') if order.raw_data else ''
            logger.debug(f"주문조직번호 조회: {krx_org_no}")
        except OrderNotFound:
            logger.error(f"❌ 취소할 주문을 찾을 수 없음 (주문번호: {order_id})")
            raise
        except Exception as e:
            logger.warning(f"⚠️ 주문 조회 실패, 조직번호 없이 취소 시도: {e}")
            krx_org_no = ""

        # 3. tr_id 선택 (실전/모의)
        tr_id = 'VTTC0013U' if self.is_virtual else 'TTTC0013U'

        # 4. 요청 Body 생성
        body = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "KRX_FWDG_ORD_ORGNO": krx_org_no,  # 주문조직번호
            "ORGN_ODNO": order_id,              # 원주문번호
            "ORD_DVSN": "00",                   # 주문구분 (취소 시 의미 없음)
            "RVSE_CNCL_DVSN_CD": "02",          # 정정취소구분: 02=취소
            "ORD_QTY": "0",                     # 주문수량 (취소는 "0")
            "ORD_UNPR": "0",                    # 주문단가 (취소는 "0")
            "QTY_ALL_ORD_YN": "Y"               # 잔량전부주문여부 (Y=전량)
        }

        # 5. 해시키 생성
        hashkey = await self.generate_hashkey(body)

        # 6. API 요청 전송
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/order-rvsecncl"
        headers = {
            'content-type': 'application/json',
            'authorization': f'Bearer {token}',
            'appkey': self.appkey,
            'appsecret': self.appsecret,
            'tr_id': tr_id,
            'hashkey': hashkey
        }

        logger.info(f"🗑️ 한투 주문 취소 요청: 주문번호={order_id}, 종목={symbol}")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=body, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    data = await response.json()

                    # 7. 에러 응답 처리
                    rt_cd = data.get('rt_cd')
                    msg_cd = data.get('msg_cd')
                    msg1 = data.get('msg1', 'Unknown error')

                    if rt_cd != '0':
                        logger.error(f"❌ 한투 주문 취소 실패: rt_cd={rt_cd}, msg_cd={msg_cd}, msg={msg1}")

                        # 에러 유형별 예외 분류
                        if 'token' in msg1.lower() or 'auth' in msg1.lower():
                            raise AuthenticationError(f"한투 취소 인증 실패: {msg1}", code=msg_cd, response=data)
                        elif '존재' in msg1 or '없' in msg1 or 'not found' in msg1.lower():
                            raise OrderNotFound(f"한투 취소 실패 (주문 없음): {msg1}", order_id=order_id, response=data)
                        elif '취소' in msg1 or '불가' in msg1 or 'cannot' in msg1.lower():
                            raise InvalidOrder(f"한투 취소 불가: {msg1}", code=msg_cd, response=data)
                        else:
                            raise InvalidOrder(f"한투 취소 실패: {msg1}", code=msg_cd, response=data)

                    # 8. 성공 응답 확인
                    if msg_cd != 'MCA00000':
                        logger.warning(f"⚠️ 한투 취소 비정상 응답: msg_cd={msg_cd}, msg={msg1}")

                    output1 = data.get('output1', {})
                    cancel_order_id = output1.get('ODNO', '')

                    logger.info(f"✅ 한투 주문 취소 성공: 원주문번호={order_id}, 취소주문번호={cancel_order_id}")

                    return True

        except aiohttp.ClientError as e:
            logger.error(f"❌ 한투 취소 네트워크 에러: {e}")
            raise NetworkError(f"한투 취소 네트워크 에러: {e}")
        except KeyError as e:
            logger.error(f"❌ 한투 취소 응답 파싱 실패: {e}, data={data}")
            raise InvalidOrder(f"한투 취소 응답 형식 오류: 필수 필드 {e} 누락")

    async def fetch_order(self, order_id: str, symbol: str) -> StockOrder:
        """
        국내주식 주문 상세 조회

        API: [2.1] GET /uapi/domestic-stock/v1/trading/inquire-daily-ccld

        Args:
            order_id: 한투 주문번호 (ODNO)
            symbol: 종목코드

        Returns:
            StockOrder: 주문 정보

        Raises:
            OrderNotFound: 주문이 없는 경우
        """
        # 토큰 자동 갱신
        token = await self.ensure_token()

        # tr_id 설정 (실전/모의투자)
        tr_id = 'VTTC0081R' if self.is_virtual else 'TTTC0081R'

        # 오늘 날짜
        today = datetime.now().strftime('%Y%m%d')

        # Query String 파라미터
        params = {
            'CANO': self.cano,
            'ACNT_PRDT_CD': self.acnt_prdt_cd,
            'INQR_STRT_DT': today,
            'INQR_END_DT': today,
            'SLL_BUY_DVSN_CD': '00',  # 전체 (매수/매도)
            'INQR_DVSN': '00',  # 역순
            'PDNO': symbol,  # 종목코드
            'CCLD_NCCS_DVSN': '00',  # 전체 (체결/미체결)
            'ORD_GNO_BRNO': '',  # 주문채번지점번호 (공란)
            'ODNO': order_id,  # 주문번호
            'INQR_DVSN_3': '00',  # 전체 (현금/융자)
            'INQR_DVSN_1': '',  # 공란
            'CTX_AREA_FK100': '',  # 연속조회 (최초 공란)
            'CTX_AREA_NK100': ''   # 연속조회키 (최초 공란)
        }

        # 헤더 구성 (GET 요청은 hashkey 불필요)
        headers = {
            'content-type': 'application/json',
            'authorization': f'Bearer {token}',
            'appkey': self.appkey,
            'appsecret': self.appsecret,
            'tr_id': tr_id
        }

        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-daily-ccld"

        logger.info(f"📋 주문 조회 요청 (주문번호: {order_id}, 종목: {symbol})")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    data = await response.json()

                    # 에러 응답 처리
                    if data.get('rt_cd') != '0':
                        error_msg = data.get('msg1', 'Unknown error')
                        logger.error(f"❌ 주문 조회 실패: {data.get('msg_cd')} - {error_msg}")
                        raise NetworkError(f"주문 조회 실패: {error_msg}", response=data)

                    # output1 배열에서 해당 주문 찾기
                    orders = data.get('output1', [])
                    if not orders:
                        logger.error(f"❌ 주문 없음 (주문번호: {order_id})")
                        raise OrderNotFound(f"주문을 찾을 수 없습니다 (주문번호: {order_id})")

                    # 첫 번째 주문 반환 (ODNO로 필터링했으므로 1개만 존재)
                    order_data = orders[0]
                    order = StockOrder.from_kis_response(order_data)

                    logger.info(f"✅ 주문 조회 성공 (주문번호: {order.order_id}, 상태: {order.status})")
                    return order

        except aiohttp.ClientError as e:
            logger.error(f"❌ 주문 조회 네트워크 에러: {e}")
            raise NetworkError(f"주문 조회 네트워크 에러: {e}")

    async def fetch_open_orders(self, symbol: Optional[str] = None) -> List[StockOrder]:
        """
        미체결 주문 조회

        API: [2.1] GET /uapi/domestic-stock/v1/trading/inquire-daily-ccld

        Args:
            symbol: 종목코드 (None이면 전체 조회)

        Returns:
            List[StockOrder]: 미체결 주문 리스트
        """
        # 토큰 자동 갱신
        token = await self.ensure_token()

        # tr_id 설정 (실전/모의투자)
        tr_id = 'VTTC0081R' if self.is_virtual else 'TTTC0081R'

        # 오늘 날짜
        today = datetime.now().strftime('%Y%m%d')

        # Query String 파라미터
        params = {
            'CANO': self.cano,
            'ACNT_PRDT_CD': self.acnt_prdt_cd,
            'INQR_STRT_DT': today,
            'INQR_END_DT': today,
            'SLL_BUY_DVSN_CD': '00',  # 전체 (매수/매도)
            'INQR_DVSN': '00',  # 역순
            'PDNO': symbol if symbol else '',  # 종목코드 (전체는 공란)
            'CCLD_NCCS_DVSN': '02',  # 미체결만
            'ORD_GNO_BRNO': '',  # 주문채번지점번호 (공란)
            'ODNO': '',  # 주문번호 (전체 조회 시 공란)
            'INQR_DVSN_3': '00',  # 전체 (현금/융자)
            'INQR_DVSN_1': '',  # 공란
            'CTX_AREA_FK100': '',  # 연속조회 (최초 공란)
            'CTX_AREA_NK100': ''   # 연속조회키 (최초 공란)
        }

        # 헤더 구성
        headers = {
            'content-type': 'application/json',
            'authorization': f'Bearer {token}',
            'appkey': self.appkey,
            'appsecret': self.appsecret,
            'tr_id': tr_id
        }

        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-daily-ccld"

        logger.info(f"📋 미체결 주문 조회 요청 (종목: {symbol or '전체'})")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    data = await response.json()

                    # 에러 응답 처리
                    if data.get('rt_cd') != '0':
                        error_msg = data.get('msg1', 'Unknown error')
                        logger.error(f"❌ 미체결 주문 조회 실패: {data.get('msg_cd')} - {error_msg}")
                        raise NetworkError(f"미체결 주문 조회 실패: {error_msg}", response=data)

                    # output1 배열을 StockOrder 리스트로 변환
                    orders = []
                    for item in data.get('output1', []):
                        order = StockOrder.from_kis_response(item)
                        orders.append(order)

                    logger.info(f"✅ 미체결 주문 조회 성공 (총 {len(orders)}개)")
                    return orders

        except aiohttp.ClientError as e:
            logger.error(f"❌ 미체결 주문 조회 네트워크 에러: {e}")
            raise NetworkError(f"미체결 주문 조회 네트워크 에러: {e}")

    # ========================================
    # 잔고/포지션 조회
    # ========================================

    async def fetch_balance(self, currency: str = 'KRW') -> StockBalance:
        """
        현금 잔고 조회

        API: [3.1] GET /uapi/domestic-stock/v1/trading/inquire-balance

        Args:
            currency: 통화 (KRW 고정)

        Returns:
            StockBalance: 잔고 정보
        """
        # 토큰 자동 갱신
        token = await self.ensure_token()

        # tr_id 설정 (실전/모의투자)
        tr_id = 'VTTC8434R' if self.is_virtual else 'TTTC8434R'

        # Query String 파라미터
        params = {
            'CANO': self.cano,
            'ACNT_PRDT_CD': self.acnt_prdt_cd,
            'AFHR_FLPR_YN': 'N',  # 시간외단일가여부
            'OFL_YN': '',  # 오프라인여부
            'INQR_DVSN': '02',  # 조회구분: 01=대출일별, 02=종목별
            'UNPR_DVSN': '01',  # 단가구분: 01=기본
            'FUND_STTL_ICLD_YN': 'N',  # 펀드결제분포함여부
            'FNCG_AMT_AUTO_RDPT_YN': 'N',  # 융자금액자동상환여부
            'PROC_DVSN': '00',  # 처리구분: 00=전일매매포함
            'CTX_AREA_FK100': '',
            'CTX_AREA_NK100': ''
        }

        # 헤더 구성
        headers = {
            'content-type': 'application/json',
            'authorization': f'Bearer {token}',
            'appkey': self.appkey,
            'appsecret': self.appsecret,
            'tr_id': tr_id
        }

        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-balance"

        logger.info(f"💰 잔고 조회 요청")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    data = await response.json()

                    # 에러 응답 처리
                    if data.get('rt_cd') != '0':
                        error_msg = data.get('msg1', 'Unknown error')
                        logger.error(f"❌ 잔고 조회 실패: {data.get('msg_cd')} - {error_msg}")
                        raise NetworkError(f"잔고 조회 실패: {error_msg}", response=data)

                    # output2 (계좌 요약 정보)
                    output2 = data.get('output2', [{}])[0] if data.get('output2') else {}

                    # 총 평가금액
                    tot_evlu_amt = Decimal(output2.get('tot_evlu_amt', '0'))
                    # 예수금 총액 (현금)
                    dnca_tot_amt = Decimal(output2.get('dnca_tot_amt', '0'))
                    # 익일정산금액 (주문가능금액)
                    nxdy_excc_amt = Decimal(output2.get('nxdy_excc_amt', '0'))
                    # 매입금액 합계
                    pchs_amt_smtl = Decimal(output2.get('pchs_amt_smtl_amt', '0'))
                    # 평가금액 합계
                    evlu_amt_smtl = Decimal(output2.get('evlu_amt_smtl_amt', '0'))
                    # 평가손익 합계
                    evlu_pfls_smtl = Decimal(output2.get('evlu_pfls_smtl_amt', '0'))

                    # output1 (보유 종목 리스트)
                    positions = []
                    for item in data.get('output1', []):
                        position = StockPosition(
                            symbol=item.get('pdno', ''),
                            symbol_name=item.get('prdt_name', ''),
                            quantity=int(item.get('hldg_qty', '0')),
                            avg_price=Decimal(item.get('pchs_avg_pric', '0')),
                            current_price=Decimal(item.get('prpr', '0')),
                            purchase_amount=Decimal(item.get('pchs_amt', '0')),
                            evaluation_amount=Decimal(item.get('evlu_amt', '0')),
                            unrealized_pnl=Decimal(item.get('evlu_pfls_amt', '0')),
                            profit_loss_rate=Decimal(item.get('evlu_pfls_rt', '0'))
                        )
                        positions.append(position)

                    # StockBalance 생성
                    balance = StockBalance(
                        total_balance=tot_evlu_amt,
                        available_balance=nxdy_excc_amt,
                        total_purchase_amount=pchs_amt_smtl,
                        total_evaluation_amount=evlu_amt_smtl,
                        total_profit_loss=evlu_pfls_smtl,
                        positions=positions
                    )

                    logger.info(f"✅ 잔고 조회 성공 (총 평가: {tot_evlu_amt:,}, 주문가능: {nxdy_excc_amt:,}, 보유 종목: {len(positions)}개)")
                    return balance

        except aiohttp.ClientError as e:
            logger.error(f"❌ 잔고 조회 네트워크 에러: {e}")
            raise NetworkError(f"잔고 조회 네트워크 에러: {e}")

    async def fetch_positions(self, symbol: Optional[str] = None) -> List[StockPosition]:
        """
        보유 종목 조회

        API: [3.1] GET /uapi/domestic-stock/v1/trading/inquire-balance

        Args:
            symbol: 종목코드 (None이면 전체 조회)

        Returns:
            List[StockPosition]: 보유 종목 리스트
        """
        # fetch_balance에서 positions를 추출하여 반환
        balance = await self.fetch_balance()
        positions = balance.positions

        # symbol 필터링
        if symbol:
            positions = [p for p in positions if p.symbol == symbol]
            logger.info(f"📊 보유 종목 조회 성공 (종목: {symbol}, 수량: {len(positions)}개)")
        else:
            logger.info(f"📊 보유 종목 조회 성공 (전체 {len(positions)}개)")

        return positions

    # ========================================
    # 시세 조회
    # ========================================

    async def fetch_quote(self, symbol: str) -> StockQuote:
        """
        현재가 조회

        API: [4.1] GET /uapi/domestic-stock/v1/quotations/inquire-price

        Args:
            symbol: 종목코드

        Returns:
            StockQuote: 현재가 정보
        """
        # 토큰 자동 갱신
        token = await self.ensure_token()

        # tr_id 설정 (시세 조회는 실전/모의투자 구분 없음)
        tr_id = 'FHKST01010100'

        # Query String 파라미터
        params = {
            'FID_COND_MRKT_DIV_CODE': 'J',  # 시장분류코드: J=주식/ETF/ETN
            'FID_INPUT_ISCD': symbol  # 종목코드
        }

        # 헤더 구성
        headers = {
            'content-type': 'application/json',
            'authorization': f'Bearer {token}',
            'appkey': self.appkey,
            'appsecret': self.appsecret,
            'tr_id': tr_id
        }

        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"

        logger.info(f"📈 현재가 조회 요청 (종목: {symbol})")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    data = await response.json()

                    # 에러 응답 처리
                    if data.get('rt_cd') != '0':
                        error_msg = data.get('msg1', 'Unknown error')
                        logger.error(f"❌ 현재가 조회 실패: {data.get('msg_cd')} - {error_msg}")
                        raise NetworkError(f"현재가 조회 실패: {error_msg}", response=data)

                    # output (시세 정보)
                    output = data.get('output', {})

                    # 현재가
                    stck_prpr = Decimal(output.get('stck_prpr', '0'))
                    # 전일대비
                    prdy_vrss = Decimal(output.get('prdy_vrss', '0'))
                    # 전일대비율
                    prdy_ctrt = Decimal(output.get('prdy_ctrt', '0'))
                    # 시가
                    stck_oprc = Decimal(output.get('stck_oprc', '0'))
                    # 고가
                    stck_hgpr = Decimal(output.get('stck_hgpr', '0'))
                    # 저가
                    stck_lwpr = Decimal(output.get('stck_lwpr', '0'))
                    # 누적거래량
                    acml_vol = int(output.get('acml_vol', '0'))

                    # StockQuote 생성
                    quote = StockQuote(
                        symbol=symbol,
                        current_price=stck_prpr,
                        change_amount=prdy_vrss,
                        change_rate=prdy_ctrt,
                        open_price=stck_oprc,
                        high_price=stck_hgpr,
                        low_price=stck_lwpr,
                        volume=acml_vol,
                        timestamp=datetime.now()
                    )

                    logger.info(f"✅ 현재가 조회 성공 (종목: {symbol}, 현재가: {stck_prpr:,})")
                    return quote

        except aiohttp.ClientError as e:
            logger.error(f"❌ 현재가 조회 네트워크 에러: {e}")
            raise NetworkError(f"현재가 조회 네트워크 에러: {e}")
