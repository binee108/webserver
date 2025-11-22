"""
WebSocket 모델 테스트

PriceQuote, ConnectionMetrics 등 WebSocket 관련 데이터 모델 테스트

@FEAT:websocket-integration @COMP:websocket-models @TYPE:test
"""

import pytest
import time
from app.services.websocket.models import PriceQuote, ConnectionState, ConnectionMetrics


class TestPriceQuote:
    """PriceQuote 모델 테스트"""

    def test_price_quote_creation(self):
        """PriceQuote 생성 테스트"""
        # Arrange & Act
        quote = PriceQuote(
            exchange="binance",
            symbol="BTCUSDT",
            price=50000.0,
            timestamp=int(time.time() * 1000),
            volume=1000.5,
            change_24h=2.5
        )

        # Assert
        assert quote.exchange == "binance"
        assert quote.symbol == "BTCUSDT"
        assert quote.price == 50000.0
        assert quote.volume == 1000.5
        assert quote.change_24h == 2.5

    def test_price_quote_to_dict(self):
        """PriceQuote 딕셔너리 변환 테스트"""
        # Arrange
        quote = PriceQuote(
            exchange="bybit",
            symbol="ETHUSDT",
            price=3000.0,
            timestamp=1234567890000
        )

        # Act
        result = quote.to_dict()

        # Assert
        expected = {
            'exchange': 'bybit',
            'symbol': 'ETHUSDT',
            'price': 3000.0,
            'timestamp': 1234567890000,
            'volume': None,
            'change_24h': None
        }
        assert result == expected

    def test_price_quote_is_stale(self):
        """PriceQuote 신선도 확인 테스트"""
        # Arrange
        old_timestamp = int((time.time() - 120) * 1000)  # 2분 전
        fresh_timestamp = int((time.time() - 30) * 1000)  # 30초 전

        old_quote = PriceQuote(
            exchange="binance",
            symbol="BTCUSDT",
            price=50000.0,
            timestamp=old_timestamp
        )

        fresh_quote = PriceQuote(
            exchange="binance",
            symbol="BTCUSDT",
            price=50000.0,
            timestamp=fresh_timestamp
        )

        # Act & Assert
        assert old_quote.is_stale(60) == True  # 2분 전 데이터는 60초 기준으로 신선하지 않음
        assert fresh_quote.is_stale(60) == False  # 30초 전 데이터는 60초 기준으로 신선함
        assert fresh_quote.is_stale(20) == True  # 30초 전 데이터는 20초 기준으로 신선하지 않음

    def test_price_quote_str_representation(self):
        """PriceQuote 문자열 표현 테스트"""
        # Arrange
        quote = PriceQuote(
            exchange="binance",
            symbol="BTCUSDT",
            price=50000.0,
            timestamp=1234567890000
        )

        # Act & Assert
        expected = "PriceQuote(binance:BTCUSDT=$50000.00)"
        assert str(quote) == expected


class TestConnectionState:
    """ConnectionState 열거형 테스트"""

    def test_connection_state_values(self):
        """ConnectionState 값 확인 테스트"""
        assert ConnectionState.DISCONNECTED.value == "disconnected"
        assert ConnectionState.CONNECTING.value == "connecting"
        assert ConnectionState.CONNECTED.value == "connected"
        assert ConnectionState.ERROR.value == "error"


class TestConnectionMetrics:
    """ConnectionMetrics 모델 테스트"""

    def test_connection_metrics_initialization(self):
        """ConnectionMetrics 초기화 테스트"""
        # Arrange & Act
        metrics = ConnectionMetrics()

        # Assert
        assert metrics.messages_received == 0
        assert metrics.messages_processed == 0
        assert metrics.errors_count == 0
        assert metrics.reconnect_count == 0
        assert metrics.last_message_time is None
        assert metrics.processing_time_total == 0.0
        assert metrics.cache_hits == 0
        assert metrics.cache_misses == 0

    def test_success_rate_calculation(self):
        """성공률 계산 테스트"""
        # Arrange
        metrics = ConnectionMetrics()

        # Act & Assert - 초기 상태
        assert metrics.success_rate == 1.0

        # Act & Assert - 정상 처리
        metrics.messages_received = 10
        metrics.messages_processed = 8
        assert metrics.success_rate == 0.8

        # Act & Assert - 전체 실패
        metrics.messages_processed = 0
        assert metrics.success_rate == 0.0

    def test_average_processing_time(self):
        """평균 처리 시간 계산 테스트"""
        # Arrange
        metrics = ConnectionMetrics()

        # Act & Assert - 초기 상태
        assert metrics.average_processing_time == 0.0

        # Act & Assert - 처리 시간 기록
        metrics.messages_processed = 5
        metrics.processing_time_total = 2.5  # 총 2.5초
        assert metrics.average_processing_time == 0.5  # 평균 0.5초

    def test_cache_hit_rate(self):
        """캐시 히트율 계산 테스트"""
        # Arrange
        metrics = ConnectionMetrics()

        # Act & Assert - 초기 상태
        assert metrics.cache_hit_rate == 0.0

        # Act & Assert - 캐시 사용
        metrics.cache_hits = 80
        metrics.cache_misses = 20
        assert metrics.cache_hit_rate == 0.8  # 80% 히트율

        # Act & Assert - 캐시 미사용
        metrics.cache_hits = 0
        metrics.cache_misses = 100
        assert metrics.cache_hit_rate == 0.0  # 0% 히트율

    def test_to_dict(self):
        """ConnectionMetrics 딕셔너리 변환 테스트"""
        # Arrange
        metrics = ConnectionMetrics()
        metrics.messages_received = 100
        metrics.messages_processed = 95
        metrics.errors_count = 2
        metrics.reconnect_count = 1
        metrics.last_message_time = time.time()
        metrics.processing_time_total = 5.0
        metrics.cache_hits = 80
        metrics.cache_misses = 20

        # Act
        result = metrics.to_dict()

        # Assert
        expected_keys = [
            'messages_received', 'messages_processed', 'errors_count',
            'reconnect_count', 'last_message_time', 'success_rate',
            'average_processing_time', 'cache_hit_rate'
        ]
        assert all(key in result for key in expected_keys)
        assert result['messages_received'] == 100
        assert result['success_rate'] == 0.95
        assert result['average_processing_time'] == 0.05263157894736842
        assert result['cache_hit_rate'] == 0.8