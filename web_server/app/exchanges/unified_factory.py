"""
통합 거래소 팩토리 (Crypto + Securities)

Account 모델 기반으로 적절한 거래소 어댑터를 자동 선택합니다.
"""

import logging
from typing import Union

from app.models import Account
from app.constants import AccountType, Exchange

logger = logging.getLogger(__name__)


class UnifiedExchangeFactory:
    """
    통합 거래소 팩토리

    특징:
    - Account.account_type에 따라 Crypto/Securities Factory 자동 분기
    - 단일 진입점으로 모든 거래소 어댑터 생성
    - 타입 안전성 보장

    사용 예시:
        # Crypto 계좌
        account = Account.query.filter_by(exchange='BINANCE').first()
        exchange = UnifiedExchangeFactory.create(account)
        # → BinanceExchange 반환

        # Securities 계좌
        account = Account.query.filter_by(exchange='KIS').first()
        exchange = UnifiedExchangeFactory.create(account)
        # → KoreaInvestmentExchange 반환
    """

    @staticmethod
    def create(account: Account):
        """
        계좌 타입에 따라 적절한 거래소 어댑터 생성

        Args:
            account: Account 모델 (DB)

        Returns:
            BaseCryptoExchange 또는 BaseSecuritiesExchange 인스턴스

        Raises:
            ValueError: 지원하지 않는 계좌 타입
            ValueError: 지원하지 않는 거래소
        """
        if not account:
            raise ValueError("Account 객체가 필요합니다")

        account_type = account.account_type

        # 1. Crypto 거래소
        if AccountType.is_crypto(account_type):
            from .crypto.factory import CryptoExchangeFactory

            logger.info(f"🔹 Crypto Factory 호출 (exchange={account.exchange}, account_id={account.id})")
            return CryptoExchangeFactory.create(
                exchange_name=account.exchange.lower(),
                api_key=account.api_key,
                secret=account.api_secret,
                testnet=account.is_testnet
            )

        # 2. Securities 거래소
        elif AccountType.is_securities(account_type):
            from .securities.factory import SecuritiesExchangeFactory

            logger.info(f"🔹 Securities Factory 호출 (exchange={account.exchange}, account_id={account.id})")
            return SecuritiesExchangeFactory.create(account)

        # 3. 알 수 없는 타입
        else:
            raise ValueError(
                f"지원하지 않는 계좌 타입: {account_type}. "
                f"지원 목록: {AccountType.VALID_TYPES}"
            )

    @staticmethod
    def list_exchanges(account_type: str = None) -> dict:
        """
        사용 가능한 거래소 목록 조회

        Args:
            account_type: 'CRYPTO' 또는 'STOCK' (None이면 전체)

        Returns:
            dict: 거래소 목록
        """
        from .crypto.factory import CryptoExchangeFactory
        from .securities.factory import SecuritiesExchangeFactory

        if account_type == AccountType.CRYPTO:
            return {'crypto': CryptoExchangeFactory.list_exchanges()}
        elif account_type == AccountType.STOCK:
            return {'securities': SecuritiesExchangeFactory.list_exchanges()}
        else:
            return {
                'crypto': CryptoExchangeFactory.list_exchanges(),
                'securities': SecuritiesExchangeFactory.list_exchanges()
            }

    @staticmethod
    def is_supported(exchange_name: str, account_type: str) -> bool:
        """
        특정 거래소 지원 여부 확인

        Args:
            exchange_name: 거래소 이름
            account_type: 계좌 타입 ('CRYPTO' 또는 'STOCK')

        Returns:
            bool: 지원 여부
        """
        from .crypto.factory import CryptoExchangeFactory
        from .securities.factory import SecuritiesExchangeFactory

        if AccountType.is_crypto(account_type):
            return CryptoExchangeFactory.is_supported(exchange_name.lower())
        elif AccountType.is_securities(account_type):
            return SecuritiesExchangeFactory.is_supported(exchange_name)
        else:
            return False
