# @FEAT:exchange-integration @COMP:exchange @TYPE:config
"""
통합 거래소 팩토리 (Crypto + Securities)

Account 모델 기반으로 적절한 거래소 어댑터를 자동 선택합니다.
"""

import logging
from typing import Union, TYPE_CHECKING

from app.models import Account
from app.constants import AccountType, Exchange

# 순환 참조 방지를 위한 TYPE_CHECKING
if TYPE_CHECKING:
    from .crypto.base import BaseCryptoExchange
    from .securities.base import BaseSecuritiesExchange

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
    def create(account: Account) -> Union['BaseCryptoExchange', 'BaseSecuritiesExchange']:
        """
        계좌 타입에 따라 적절한 거래소 어댑터 생성

        Args:
            account (Account): Account 모델 인스턴스 (DB)

        Returns:
            Union[BaseCryptoExchange, BaseSecuritiesExchange]:
                - Crypto 계좌 → BaseCryptoExchange 서브클래스
                - Securities 계좌 → BaseSecuritiesExchange 서브클래스

        Raises:
            ValueError: account가 None인 경우
            ValueError: account에 필수 속성이 없는 경우
            ValueError: 지원하지 않는 계좌 타입 (AccountType.VALID_TYPES 참조)
            ValueError: 지원하지 않는 거래소 (팩토리별 지원 목록 참조)

        Examples:
            >>> # Crypto 계좌 - BinanceExchange 반환
            >>> account = Account.query.filter_by(exchange='BINANCE', account_type='CRYPTO').first()
            >>> exchange = UnifiedExchangeFactory.create(account)
            >>> isinstance(exchange, BaseCryptoExchange)
            True

            >>> # Securities 계좌 - KoreaInvestmentExchange 반환
            >>> account = Account.query.filter_by(exchange='KIS', account_type='STOCK').first()
            >>> exchange = UnifiedExchangeFactory.create(account)
            >>> isinstance(exchange, BaseSecuritiesExchange)
            True
        """
        # 1. Account 객체 검증
        if not account:
            raise ValueError(
                "UnifiedExchangeFactory.create()는 Account 객체가 필요합니다. "
                "None이 전달되었습니다."
            )

        # 2. 필수 속성 검증
        if not hasattr(account, 'account_type'):
            raise ValueError(
                f"Account 객체에 account_type 속성이 없습니다. "
                f"account_id={getattr(account, 'id', 'N/A')}"
            )

        if not hasattr(account, 'exchange'):
            raise ValueError(
                f"Account 객체에 exchange 속성이 없습니다. "
                f"account_id={getattr(account, 'id', 'N/A')}"
            )

        account_type = account.account_type

        # 3. Crypto 거래소
        if AccountType.is_crypto(account_type):
            from .crypto.factory import CryptoExchangeFactory

            logger.info(
                f"🔹 Crypto Factory 호출: "
                f"account_id={account.id}, exchange={account.exchange}, "
                f"account_type={account_type}, testnet={account.is_testnet}"
            )
            return CryptoExchangeFactory.create(
                exchange_name=account.exchange.lower(),
                api_key=account.api_key,
                secret=account.api_secret,
                testnet=account.is_testnet
            )

        # 4. Securities 거래소
        elif AccountType.is_securities(account_type):
            from .securities.factory import SecuritiesExchangeFactory

            logger.info(
                f"🔹 Securities Factory 호출: "
                f"account_id={account.id}, exchange={account.exchange}, "
                f"account_type={account_type}"
            )
            return SecuritiesExchangeFactory.create(account)

        # 5. 알 수 없는 타입
        else:
            raise ValueError(
                f"지원하지 않는 계좌 타입입니다: {account_type}. "
                f"지원 목록: {AccountType.VALID_TYPES}. "
                f"account_id={account.id}, exchange={account.exchange}"
            )

    @staticmethod
    def list_exchanges(account_type: str = None) -> dict:
        """
        사용 가능한 거래소 목록 조회

        Args:
            account_type (str, optional): 계좌 타입 필터
                - AccountType.CRYPTO ('CRYPTO'): 크립토 거래소만 조회
                - AccountType.STOCK ('STOCK'): 증권 거래소만 조회
                - None: 전체 거래소 조회 (기본값)

        Returns:
            dict: 거래소 목록
                - account_type='CRYPTO': {'crypto': ['binance', 'upbit', ...]}
                - account_type='STOCK': {'securities': ['KIS', ...]}
                - account_type=None: {'crypto': [...], 'securities': [...]}

        Examples:
            >>> # 크립토 거래소만 조회
            >>> UnifiedExchangeFactory.list_exchanges(AccountType.CRYPTO)
            {'crypto': ['binance', 'upbit']}

            >>> # 전체 거래소 조회
            >>> UnifiedExchangeFactory.list_exchanges()
            {'crypto': ['binance', 'upbit'], 'securities': ['KIS']}
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
            exchange_name (str): 거래소 이름
                - Crypto: 'binance', 'upbit', 'bybit', 'okx' (소문자)
                - Securities: 'KIS', 'KIWOOM', 'LS', 'EBEST' (대문자)
            account_type (str): 계좌 타입
                - AccountType.CRYPTO ('CRYPTO')
                - AccountType.STOCK ('STOCK')

        Returns:
            bool: 지원 여부
                - True: 해당 계좌 타입에서 거래소 지원
                - False: 미지원 또는 잘못된 account_type

        Examples:
            >>> # Crypto 거래소 확인
            >>> UnifiedExchangeFactory.is_supported('binance', AccountType.CRYPTO)
            True

            >>> # Securities 거래소 확인
            >>> UnifiedExchangeFactory.is_supported('KIS', AccountType.STOCK)
            True

            >>> # 미지원 거래소
            >>> UnifiedExchangeFactory.is_supported('unknown', AccountType.CRYPTO)
            False
        """
        from .crypto.factory import CryptoExchangeFactory
        from .securities.factory import SecuritiesExchangeFactory

        if AccountType.is_crypto(account_type):
            return CryptoExchangeFactory.is_supported(exchange_name.lower())
        elif AccountType.is_securities(account_type):
            return SecuritiesExchangeFactory.is_supported(exchange_name)
        else:
            return False
