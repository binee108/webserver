# @FEAT:exchange-integration @COMP:exchange @TYPE:config
"""
증권 거래소 팩토리

계좌 정보를 기반으로 적절한 증권사 어댑터를 생성합니다.
"""

import logging
from typing import Optional

from app.constants import Exchange, AccountType
from .base import BaseSecuritiesExchange
from .korea_investment import KoreaInvestmentExchange

logger = logging.getLogger(__name__)


class SecuritiesExchangeFactory:
    """
    증권 거래소 팩토리 (플러그인 구조)

    특징:
    - 계좌(Account) 기반 인스턴스 생성
    - 증권사별 어댑터 매핑
    - 확장 용이 (새 증권사 추가 시 _EXCHANGE_CLASSES만 수정)

    사용 예시:
        account = Account.query.get(1)  # 한투 계좌
        exchange = SecuritiesExchangeFactory.create(account)
        order = await exchange.create_stock_order('005930', 'BUY', 'LIMIT', 10, Decimal('70000'))
    """

    # 증권사 클래스 매핑 (확장 시 여기에만 추가)
    _EXCHANGE_CLASSES = {
        Exchange.KIS: KoreaInvestmentExchange,  # 한국투자증권 ✅
        # Exchange.KIWOOM: KiwoomExchange,        # 추후 구현
        # Exchange.LS: LSExchange,                # 추후 구현
        # Exchange.EBEST: EBestExchange,          # 추후 구현
    }

    @classmethod
    def create(cls, account: 'Account') -> BaseSecuritiesExchange:
        """
        증권 거래소 인스턴스 생성

        Args:
            account (Account): 증권 계좌 모델 (DB)

        Returns:
            BaseSecuritiesExchange: 증권사별 어댑터 인스턴스

        Raises:
            ValueError: 지원되지 않는 증권사
            ValueError: CRYPTO 계좌로 호출 시도

        Examples:
            >>> account = Account.query.filter_by(exchange='KIS').first()
            >>> exchange = SecuritiesExchangeFactory.create(account)
            >>> isinstance(exchange, KoreaInvestmentExchange)
            True
        """

        # 1. 계좌 타입 검증
        if AccountType.is_crypto(account.account_type):
            raise ValueError(
                f"SecuritiesExchangeFactory는 증권 계좌만 처리합니다. "
                f"account_id={account.id}, type={account.account_type}"
            )

        # 2. 증권사 지원 여부 확인
        exchange_name = account.exchange
        if exchange_name not in cls._EXCHANGE_CLASSES:
            supported = list(cls._EXCHANGE_CLASSES.keys())
            raise ValueError(
                f"지원되지 않는 증권사: {exchange_name}. "
                f"지원 목록: {supported if supported else '(아직 구현 전)'}"
            )

        # 3. 인스턴스 생성
        exchange_class = cls._EXCHANGE_CLASSES[exchange_name]
        logger.info(f"✅ {exchange_name} 증권사 어댑터 생성 (account_id={account.id})")
        return exchange_class(account)

    @classmethod
    def is_supported(cls, exchange_name: str) -> bool:
        """
        지원되는 증권사인지 확인

        Args:
            exchange_name: 증권사 이름 (예: 'KIS', 'KIWOOM')

        Returns:
            bool: 지원 여부
        """
        return exchange_name in cls._EXCHANGE_CLASSES

    @classmethod
    def list_exchanges(cls) -> list:
        """
        지원되는 증권사 목록 반환

        Returns:
            list: 증권사 이름 목록 (예: ['KIS', 'KIWOOM'])
        """
        return list(cls._EXCHANGE_CLASSES.keys())

    @classmethod
    def create_default_client(cls, exchange_name: str) -> Optional[BaseSecuritiesExchange]:
        """
        API 키 없이 기본 증권 거래소 클라이언트를 생성합니다.

        Args:
            exchange_name: 거래소 이름 (대문자, 예: 'KIS')

        Returns:
            BaseSecuritiesExchange: 기본 클라이언트 또는 None
        """
        try:
            # 지원 증권사 검증
            if exchange_name not in cls._EXCHANGE_CLASSES:
                logger.warning(f"지원되지 않는 증권사: {exchange_name}")
                return None

            # 기본 클라이언트 생성 (계좌 없이)
            exchange_class = cls._EXCHANGE_CLASSES[exchange_name]

            # 대부분의 증권사 클라이언트는 계좌 정보 필요
            # 기본 모드로 생성 또는 None 반환
            try:
                # 계좌 없이 생성 시도 (지원하는 경우)
                client = exchange_class(account=None)
                logger.debug(f"✅ {exchange_name} 기본 클라이언트 생성 성공")
                return client
            except Exception:
                # 계좌 없이 생성 불가 시 None 반환
                logger.debug(f"⚠️  {exchange_name} 기본 클라이언트 생성 불가 (계좌 필요)")
                return None

        except Exception as e:
            logger.warning(f"기본 증권 클라이언트 생성 실패 ({exchange_name}): {e}")
            return None
