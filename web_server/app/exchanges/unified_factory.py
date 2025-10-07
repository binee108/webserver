"""
크립토/증권 통합 거래소 팩토리

계좌 타입에 따라 적절한 거래소 어댑터를 생성합니다.
"""

import logging
from typing import Union

from app.constants import AccountType

logger = logging.getLogger(__name__)


class UnifiedExchangeFactory:
    """
    크립토/증권 통합 팩토리

    특징:
    - 계좌 타입 기반 자동 라우팅
    - 크립토: ExchangeFactory → BaseExchange
    - 증권: SecuritiesFactory → BaseSecuritiesExchange

    사용 예시:
        account = Account.query.get(1)
        exchange = UnifiedExchangeFactory.create_exchange(account)
        # account.account_type에 따라 자동으로 적절한 거래소 반환
    """

    @classmethod
    def create_exchange(cls, account: 'Account') -> Union['BaseExchange', 'BaseSecuritiesExchange']:
        """
        통합 거래소 인스턴스 생성

        Args:
            account (Account): 계좌 모델 (DB)

        Returns:
            Union[BaseExchange, BaseSecuritiesExchange]: 거래소 어댑터

        Raises:
            ValueError: 계좌 정보가 유효하지 않을 때

        Examples:
            >>> # 크립토 계좌
            >>> crypto_account = Account.query.filter_by(account_type='CRYPTO').first()
            >>> exchange = UnifiedExchangeFactory.create_exchange(crypto_account)
            >>> isinstance(exchange, BaseExchange)
            True

            >>> # 증권 계좌
            >>> securities_account = Account.query.filter_by(account_type='STOCK').first()
            >>> exchange = UnifiedExchangeFactory.create_exchange(securities_account)
            >>> isinstance(exchange, BaseSecuritiesExchange)
            True
        """
        if not account:
            raise ValueError("계좌 정보가 제공되지 않았습니다.")

        # 1. 계좌 타입 판별
        if AccountType.is_crypto(account.account_type):
            # 크립토 거래소 - Account에서 필요한 정보 추출하여 ExchangeFactory에 전달
            from app.exchanges.factory import ExchangeFactory

            logger.debug(
                f"🔀 크립토 거래소 생성 "
                f"(account_id={account.id}, type={account.account_type}, exchange={account.exchange})"
            )

            # Account에서 복호화된 API 키 가져오기 (프로퍼티 사용)
            api_key = account.api_key      # @property로 복호화 및 캐싱
            secret = account.api_secret    # @property로 복호화 및 캐싱

            return ExchangeFactory.create_exchange(
                exchange_name=account.exchange,
                api_key=api_key,
                secret=secret,
                testnet=account.is_testnet
            )
        else:
            # 증권 거래소 - Account 객체 전체를 SecuritiesFactory에 전달
            from app.securities.factory import SecuritiesFactory

            logger.debug(
                f"🔀 증권 거래소 생성 "
                f"(account_id={account.id}, type={account.account_type}, exchange={account.exchange})"
            )

            return SecuritiesFactory.create_exchange(account)

    @classmethod
    def is_crypto_account(cls, account: 'Account') -> bool:
        """
        크립토 계좌 여부 확인

        Args:
            account (Account): 계좌 모델

        Returns:
            bool: 크립토 계좌 여부
        """
        if not account:
            return False
        return AccountType.is_crypto(account.account_type)

    @classmethod
    def is_securities_account(cls, account: 'Account') -> bool:
        """
        증권 계좌 여부 확인

        Args:
            account (Account): 계좌 모델

        Returns:
            bool: 증권 계좌 여부
        """
        if not account:
            return False
        return not AccountType.is_crypto(account.account_type)
