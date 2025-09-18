"""
거래소 연결 관리 서비스
CCXT 인스턴스 생성 및 연결 관리
"""

import ccxt
import logging
from typing import Dict, Any, Optional
from app.models import Account
from app.constants import Exchange

logger = logging.getLogger(__name__)


class ExchangeConnectionService:
    """거래소 연결 및 인스턴스 관리 서비스"""

    def __init__(self):
        self._exchange_instances = {}  # {account_id: exchange_instance}

    def get_exchange_instance(self, account: Account) -> Optional[Any]:
        """
        계정에 대한 거래소 인스턴스 반환
        캐싱된 인스턴스가 있으면 재사용, 없으면 새로 생성
        """
        try:
            account_id = account.id

            # 캐싱된 인스턴스가 있는지 확인
            if account_id in self._exchange_instances:
                return self._exchange_instances[account_id]

            # 새 인스턴스 생성
            exchange_instance = self._create_exchange_instance(account)
            if exchange_instance:
                self._exchange_instances[account_id] = exchange_instance
                logger.info(f"✅ 거래소 인스턴스 생성 완료: {account.exchange} (account_id: {account_id})")

            return exchange_instance

        except Exception as e:
            logger.error(f"❌ 거래소 인스턴스 생성 실패 - account_id: {account.id}, exchange: {account.exchange}, error: {e}")
            return None

    def _create_exchange_instance(self, account: Account) -> Optional[Any]:
        """
        CCXT 거래소 인스턴스 생성
        """
        try:
            exchange_name = account.exchange.lower()

            # 지원되는 거래소 확인
            if exchange_name not in ccxt.exchanges:
                logger.error(f"지원되지 않는 거래소: {exchange_name}")
                return None

            # 거래소 클래스 가져오기
            exchange_class = getattr(ccxt, exchange_name)

            # 인스턴스 생성 설정
            config = {
                'apiKey': account.api_key,
                'secret': account.secret_key,
                'sandbox': False,  # 프로덕션 모드
                'enableRateLimit': True,  # rate limiting 활성화
                'timeout': 30000,  # 30초 타임아웃
            }

            # 거래소별 특별 설정
            if exchange_name == 'binance':
                config.update({
                    'options': {
                        'defaultType': 'spot',  # 기본은 현물
                        'recvWindow': 10000,
                    }
                })
            elif exchange_name == 'bybit':
                config.update({
                    'options': {
                        'defaultType': 'spot',
                    }
                })
            elif exchange_name == 'okx':
                config.update({
                    'options': {
                        'defaultType': 'spot',
                    }
                })

            # 인스턴스 생성
            exchange_instance = exchange_class(config)

            # 연결 테스트
            if self._test_connection(exchange_instance, account):
                return exchange_instance
            else:
                logger.error(f"거래소 연결 테스트 실패: {exchange_name}")
                return None

        except Exception as e:
            logger.error(f"거래소 인스턴스 생성 중 오류: {e}")
            return None

    def _test_connection(self, exchange_instance: Any, account: Account) -> bool:
        """
        거래소 연결 테스트
        """
        try:
            # 간단한 API 호출로 연결 테스트
            balance = exchange_instance.fetch_balance()
            if balance is not None:
                logger.debug(f"거래소 연결 테스트 성공: {account.exchange}")
                return True
            else:
                logger.error(f"거래소 연결 테스트 실패 (잔고 조회 실패): {account.exchange}")
                return False

        except Exception as e:
            logger.error(f"거래소 연결 테스트 중 오류: {account.exchange}, error: {e}")
            return False

    def clear_instance(self, account_id: int):
        """특정 계정의 거래소 인스턴스 제거"""
        if account_id in self._exchange_instances:
            del self._exchange_instances[account_id]
            logger.info(f"거래소 인스턴스 제거: account_id {account_id}")

    def clear_all_instances(self):
        """모든 거래소 인스턴스 제거"""
        self._exchange_instances.clear()
        logger.info("모든 거래소 인스턴스 제거 완료")

    def get_connection_stats(self) -> Dict[str, Any]:
        """연결 상태 통계"""
        return {
            'active_connections': len(self._exchange_instances),
            'connected_accounts': list(self._exchange_instances.keys())
        }

    def refresh_instance(self, account: Account) -> Optional[Any]:
        """거래소 인스턴스 강제 새로고침"""
        # 기존 인스턴스 제거
        if account.id in self._exchange_instances:
            del self._exchange_instances[account.id]

        # 새 인스턴스 생성
        return self.get_exchange_instance(account)


# 싱글톤 인스턴스
exchange_connection_service = ExchangeConnectionService()