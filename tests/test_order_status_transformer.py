# @FEAT:order-status-standardization @COMP:transformer @TYPE:standardization
"""
OrderStatusTransformer 클래스 TDD 테스트

거래소별 주문 상태를 표준 상태로 변환하는 로직을 테스트합니다.
"""

import pytest
from web_server.app.constants import StandardOrderStatus
from web_server.app.exchanges.transformers.order_status_transformer import OrderStatusTransformer


class TestOrderStatusTransformer:
    """OrderStatusTransformer 클래스 테스트"""

    def test_transform_binance_statuses(self):
        """Binance 주문 상태 변환 테스트"""
        transformer = OrderStatusTransformer()

        # 기본 상태들
        assert transformer.transform('NEW', 'BINANCE') == StandardOrderStatus.NEW
        assert transformer.transform('PARTIALLY_FILLED', 'BINANCE') == StandardOrderStatus.PARTIALLY_FILLED
        assert transformer.transform('FILLED', 'BINANCE') == StandardOrderStatus.FILLED

        # 취소 상태들
        assert transformer.transform('CANCELED', 'BINANCE') == StandardOrderStatus.CANCELLED
        assert transformer.transform('CANCELLED', 'BINANCE') == StandardOrderStatus.CANCELLED

        # 에러 상태들
        assert transformer.transform('REJECTED', 'BINANCE') == StandardOrderStatus.REJECTED
        assert transformer.transform('EXPIRED', 'BINANCE') == StandardOrderStatus.EXPIRED

    def test_transform_upbit_statuses(self):
        """Upbit 주문 상태 변환 테스트"""
        transformer = OrderStatusTransformer()

        # 기본 상태들
        assert transformer.transform('wait', 'UPBIT') == StandardOrderStatus.OPEN
        assert transformer.transform('watch', 'UPBIT') == StandardOrderStatus.OPEN  # 호환성
        assert transformer.transform('done', 'UPBIT') == StandardOrderStatus.FILLED
        assert transformer.transform('completed', 'UPBIT') == StandardOrderStatus.FILLED  # 호환성

        # 취소 상태
        assert transformer.transform('cancel', 'UPBIT') == StandardOrderStatus.CANCELLED
        assert transformer.transform('cancelled', 'UPBIT') == StandardOrderStatus.CANCELLED  # 호환성

    def test_transform_bithumb_statuses(self):
        """Bithumb 주문 상태 변환 테스트"""
        transformer = OrderStatusTransformer()

        # 기본 상태들
        assert transformer.transform('bid', 'BITHUMB') == StandardOrderStatus.OPEN
        assert transformer.transform('ask', 'BITHUMB') == StandardOrderStatus.OPEN
        assert transformer.transform('fill', 'BITHUMB') == StandardOrderStatus.FILLED
        assert transformer.transform('complete', 'BITHUMB') == StandardOrderStatus.FILLED

        # 취소 상태
        assert transformer.transform('cancel', 'BITHUMB') == StandardOrderStatus.CANCELLED

    def test_transform_bybit_statuses(self):
        """Bybit 주문 상태 변환 테스트"""
        transformer = OrderStatusTransformer()

        # 기본 상태들
        assert transformer.transform('Created', 'BYBIT') == StandardOrderStatus.NEW
        assert transformer.transform('New', 'BYBIT') == StandardOrderStatus.OPEN
        assert transformer.transform('PartiallyFilled', 'BYBIT') == StandardOrderStatus.PARTIALLY_FILLED
        assert transformer.transform('Filled', 'BYBIT') == StandardOrderStatus.FILLED

        # 취소 상태들
        assert transformer.transform('Cancelled', 'BYBIT') == StandardOrderStatus.CANCELLED
        assert transformer.transform('Canceled', 'BYBIT') == StandardOrderStatus.CANCELLED

        # 에러 상태
        assert transformer.transform('Rejected', 'BYBIT') == StandardOrderStatus.REJECTED

    def test_transform_unknown_exchange(self):
        """알 수 없는 거래소 상태 변환 테스트"""
        transformer = OrderStatusTransformer()

        # 알 수 없는 거래소는 원본 상태를 그대로 반환
        assert transformer.transform('UNKNOWN_STATUS', 'UNKNOWN_EXCHANGE') == 'UNKNOWN_STATUS'
        assert transformer.transform('NEW', 'UNKNOWN_EXCHANGE') == 'NEW'

    def test_transform_unknown_status(self):
        """알 수 없는 상태 변환 테스트"""
        transformer = OrderStatusTransformer()

        # 알 수 없는 상태는 원본을 그대로 반환
        assert transformer.transform('UNKNOWN_STATUS', 'BINANCE') == 'UNKNOWN_STATUS'
        assert transformer.transform('UNKNOWN_STATUS', 'UPBIT') == 'UNKNOWN_STATUS'

    def test_transform_with_none_inputs(self):
        """None 입력 처리 테스트"""
        transformer = OrderStatusTransformer()

        # None 입력 처리
        assert transformer.transform(None, 'BINANCE') is None
        assert transformer.transform('NEW', None) == 'NEW'
        assert transformer.transform(None, None) is None

        # 빈 문자열 처리
        assert transformer.transform('', 'BINANCE') == ''
        assert transformer.transform('NEW', '') == 'NEW'

    def test_transform_case_insensitive_exchange(self):
        """거래소 이름 대소문자 무시 처리 테스트"""
        transformer = OrderStatusTransformer()

        # 소문자 거래소 이름
        assert transformer.transform('NEW', 'binance') == StandardOrderStatus.NEW
        assert transformer.transform('wait', 'upbit') == StandardOrderStatus.OPEN
        assert transformer.transform('Created', 'bybit') == StandardOrderStatus.NEW

        # 혼합 대소문자
        assert transformer.transform('NEW', 'Binance') == StandardOrderStatus.NEW
        assert transformer.transform('wait', 'Upbit') == StandardOrderStatus.OPEN

    def test_get_supported_exchanges(self):
        """지원되는 거래소 목록 반환 테스트"""
        transformer = OrderStatusTransformer()

        supported_exchanges = transformer.get_supported_exchanges()

        # 주요 거래소들이 포함되어 있는지 확인
        assert 'BINANCE' in supported_exchanges
        assert 'UPBIT' in supported_exchanges
        assert 'BITHUMB' in supported_exchanges
        assert 'BYBIT' in supported_exchanges

    def test_is_supported_exchange(self):
        """지원되는 거래소인지 확인 테스트"""
        transformer = OrderStatusTransformer()

        # 지원되는 거래소들
        assert transformer.is_supported_exchange('BINANCE') is True
        assert transformer.is_supported_exchange('UPBIT') is True
        assert transformer.is_supported_exchange('BITHUMB') is True
        assert transformer.is_supported_exchange('BYBIT') is True

        # 대소문자 무시
        assert transformer.is_supported_exchange('binance') is True
        assert transformer.is_supported_exchange('Upbit') is True

        # 지원되지 않는 거래소
        assert transformer.is_supported_exchange('UNKNOWN') is False
        assert transformer.is_supported_exchange('INVALID') is False
        assert transformer.is_supported_exchange(None) is False
        assert transformer.is_supported_exchange('') is False