"""
증권 거래소 팩토리

계좌 정보를 기반으로 적절한 증권사 어댑터를 생성합니다.
"""

import logging
from typing import Optional

from app.constants import Exchange
from app.securities.base import BaseSecuritiesExchange
from app.securities.korea_investment import KoreaInvestmentExchange

logger = logging.getLogger(__name__)


class SecuritiesFactory:
    """
    증권 거래소 팩토리 (플러그인 구조)

    특징:
    - 계좌(Account) 기반 인스턴스 생성
    - 증권사별 어댑터 매핑
    - 확장 용이 (새 증권사 추가 시 _EXCHANGE_CLASSES만 수정)

    사용 예시:
        account = Account.query.get(1)  # 한투 계좌
        exchange = SecuritiesFactory.create_exchange(account)
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
    def create_exchange(cls, account: 'Account') -> BaseSecuritiesExchange:
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
            >>> exchange = SecuritiesFactory.create_exchange(account)
            >>> isinstance(exchange, KoreaInvestmentExchange)
            True
        """
        from app.constants import AccountType

        # 1. 계좌 타입 검증
        if AccountType.is_crypto(account.account_type):
            raise ValueError(
                f"SecuritiesFactory는 증권 계좌만 처리합니다. "
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
    def get_supported_exchanges(cls) -> list:
        """
        지원되는 증권사 목록 반환

        Returns:
            list: 증권사 이름 목록 (예: ['KIS', 'KIWOOM'])
        """
        return list(cls._EXCHANGE_CLASSES.keys())
