"""
WebSocket 설정 모듈 테스트

설정 관리, 거래소별 설정 등 테스트

@FEAT:websocket-integration @COMP:websocket-config @TYPE:test
"""

import pytest
from app.services.websocket.config import (
    WebSocketConfig, ExchangeConfig, WebSocketConfigManager,
    ConnectionType
)


class TestWebSocketConfig:
    """WebSocketConfig 기본 설정 테스트"""

    def test_default_values(self):
        """기본 설정값 확인 테스트"""
        # Arrange & Act
        config = WebSocketConfig()

        # Assert
        assert config.RECONNECT_DELAY == 5.0
        assert config.MAX_RECONNECT_ATTEMPTS == 10
        assert config.CACHE_EXPIRE_TIME == 60
        assert config.MAX_CACHE_SIZE == 100
        assert config.MESSAGE_BUFFER_SIZE == 1000
        assert config.PROCESSING_TIMEOUT == 10.0
        assert config.HEARTBEAT_INTERVAL == 30


class TestExchangeConfig:
    """ExchangeConfig 거래소 설정 테스트"""

    def test_get_binance_ws_url(self):
        """Binance WebSocket URL 조회 테스트"""
        # Act
        url = ExchangeConfig.get_ws_url("binance")

        # Assert
        assert url == "wss://stream.binance.com:9443/ws"

    def test_get_binance_testnet_ws_url(self):
        """Binance Testnet WebSocket URL 조회 테스트"""
        # Act
        url = ExchangeConfig.get_ws_url("binance", testnet=True)

        # Assert
        assert url == "wss://testnet.binance.vision/ws"

    def test_get_bybit_ws_url(self):
        """Bybit WebSocket URL 조회 테스트"""
        # Act
        url = ExchangeConfig.get_ws_url("bybit")

        # Assert
        assert url == "wss://stream.bybit.com/v5/public/linear"

    def test_get_bybit_testnet_ws_url(self):
        """Bybit Testnet WebSocket URL 조회 테스트"""
        # Act
        url = ExchangeConfig.get_ws_url("bybit", testnet=True)

        # Assert
        assert url == "wss://stream-testnet.bybit.com/v5/public/linear"

    def test_get_unsupported_exchange_url(self):
        """지원하지 않는 거래소 URL 조회 테스트"""
        # Act & Assert
        with pytest.raises(ValueError, match="지원하지 않는 거래소: unsupported"):
            ExchangeConfig.get_ws_url("unsupported")

    def test_case_insensitive_exchange_name(self):
        """대소문자 구분 없는 거래소 이름 테스트"""
        # Act & Assert
        assert ExchangeConfig.get_ws_url("BINANCE") == ExchangeConfig.get_ws_url("binance")
        assert ExchangeConfig.get_ws_url("Bybit") == ExchangeConfig.get_ws_url("bybit")


class TestWebSocketConfigManager:
    """WebSocketConfigManager 설정 관리자 테스트"""

    def setup_method(self):
        """각 테스트 전 설정"""
        self.manager = WebSocketConfigManager()

    def test_get_config(self):
        """설정 조회 테스트"""
        # Act
        config = self.manager.get_config()

        # Assert
        assert isinstance(config, WebSocketConfig)
        assert config.RECONNECT_DELAY == 5.0
        assert config.MAX_CACHE_SIZE == 100

    def test_set_custom_config(self):
        """사용자 정의 설정 추가 테스트"""
        # Arrange
        custom_key = "custom_setting"
        custom_value = {"timeout": 30, "retries": 5}

        # Act
        self.manager.set_custom_config(custom_key, custom_value)
        retrieved_value = self.manager.get_custom_config(custom_key)

        # Assert
        assert retrieved_value == custom_value

    def test_get_custom_config_default(self):
        """존재하지 않는 사용자 정의 설정 조회 테스트"""
        # Arrange
        non_existent_key = "non_existent_setting"
        default_value = "default"

        # Act
        result = self.manager.get_custom_config(non_existent_key, default_value)

        # Assert
        assert result == default_value

    def test_get_custom_config_none(self):
        """존재하지 않는 설정 기본값 없이 조회 테스트"""
        # Act
        result = self.manager.get_custom_config("non_existent")

        # Assert
        assert result is None

    def test_is_exchange_supported(self):
        """거래소 지원 여부 확인 테스트"""
        # Act & Assert
        assert self.manager.is_exchange_supported("binance") == True
        assert self.manager.is_exchange_supported("bybit") == True
        assert self.manager.is_exchange_supported("unsupported") == False
        assert self.manager.is_exchange_supported("BINANCE") == True  # 대소문자 구분 없음

    def test_get_exchange_config_ws_url(self):
        """거래소 WebSocket URL 설정 조회 테스트"""
        # Act & Assert
        binance_url = self.manager.get_exchange_config("binance", "ws_url")
        assert binance_url == "wss://stream.binance.com:9443/ws"

        bybit_url = self.manager.get_exchange_config("bybit", "ws_url")
        assert bybit_url == "wss://stream.bybit.com/v5/public/linear"

    def test_get_exchange_config_max_connections(self):
        """거래소 최대 연결 수 설정 조회 테스트"""
        # Act & Assert
        binance_max = self.manager.get_exchange_config("binance", "max_connections")
        assert binance_max == 10

        bybit_max = self.manager.get_exchange_config("bybit", "max_connections")
        assert bybit_max == 10

    def test_get_exchange_config_rate_limit(self):
        """거래소 Rate Limit 설정 조회 테스트"""
        # Act & Assert
        binance_rate = self.manager.get_exchange_config("binance", "rate_limit")
        assert binance_rate == 5

        bybit_rate = self.manager.get_exchange_config("bybit", "rate_limit")
        assert bybit_rate == 5

    def test_get_unsupported_exchange_config(self):
        """지원하지 않는 거래소 설정 조회 테스트"""
        # Act
        result = self.manager.get_exchange_config("unsupported", "ws_url")

        # Assert
        assert result is None

    def test_get_unknown_config_type(self):
        """알 수 없는 설정 타입 조회 테스트"""
        # Act
        result = self.manager.get_exchange_config("binance", "unknown_config")

        # Assert
        assert result is None


class TestConnectionType:
    """ConnectionType 연결 유형 테스트"""

    def test_connection_type_values(self):
        """ConnectionType 값 확인 테스트"""
        assert ConnectionType.PUBLIC_PRICE_FEED.value == "price_feed"
        assert ConnectionType.PRIVATE_ORDER_EXECUTION.value == "order_execution"
        assert ConnectionType.PUBLIC_ORDER_BOOK.value == "order_book"
        assert ConnectionType.PRIVATE_POSITION_UPDATE.value == "position_update"

    def test_connection_type_count(self):
        """ConnectionType 개수 확인 테스트"""
        # 4가지 연결 유형이 있어야 함
        connection_types = list(ConnectionType)
        assert len(connection_types) == 4