"""
단순화된 거래소 어댑터 팩토리 서비스

1인 사용자를 위한 단순한 거래소 어댑터 팩토리입니다.
복잡한 어댑터 레이어를 제거하고 직접적인 구조로 변경되었습니다.
"""

import logging
from typing import Dict, Any, Optional
from app.models import Account
from app.constants import Exchange

logger = logging.getLogger(__name__)


class ExchangeAdapterFactory:
    """단순화된 거래소 어댑터 팩토리"""

    def __init__(self):
        # 단순한 Native 팩토리만 사용
        try:
            from app.exchanges.factory import exchange_factory
            self.factory = exchange_factory
            logger.info("✅ 단순화된 거래소 팩토리 초기화 완료")
        except ImportError as e:
            logger.error(f"❌ 거래소 팩토리 import 실패: {e}")
            self.factory = None

    def get_adapter(self, account: Account) -> Optional[Any]:
        """
        계정 정보로부터 거래소 어댑터 생성

        Args:
            account: 계정 정보

        Returns:
            거래소 인스턴스 (Native Binance)
        """
        if not self.factory:
            logger.error("❌ 거래소 팩토리가 초기화되지 않음")
            return None

        try:
            # Binance만 지원
            if account.exchange.lower() == 'binance':
                return self.factory.create_binance(
                    api_key=account.api_key,
                    secret=account.api_secret,
                    testnet=account.is_testnet
                )
            else:
                logger.error(f"❌ 지원되지 않는 거래소: {account.exchange}")
                return None

        except Exception as e:
            logger.error(f"❌ 거래소 어댑터 생성 실패: {e}")
            return None

    def is_available(self) -> bool:
        """팩토리 사용 가능 여부"""
        return self.factory is not None

    def get_supported_exchanges(self) -> list:
        """지원되는 거래소 목록"""
        if self.factory:
            return self.factory.get_supported_exchanges()
        return []


# 싱글톤 인스턴스
exchange_adapter_factory = ExchangeAdapterFactory()