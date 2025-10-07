"""
크립토 거래소 기본 클래스

BaseExchange를 상속하여 크립토 특화 기능을 추가합니다.
"""

from app.exchanges.base import BaseExchange


class BaseCryptoExchange(BaseExchange):
    """
    크립토 거래소 공통 기능

    확장 포인트:
    - 레버리지 설정 (Futures)
    - 포지션 모드 설정 (단방향/양방향)
    - 마진 모드 설정 (격리/교차)
    """

    def __init__(self, api_key: str, secret: str, testnet: bool = False):
        super().__init__()
        self.api_key = api_key
        self.api_secret = secret
        self.testnet = testnet
