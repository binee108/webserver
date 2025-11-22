"""
WebSocketConnectorFactory 테스트

팩토리 패턴 기반 WebSocket 커넥터 생성 및 관리 기능 테스트

@FEAT:websocket-integration @COMP:websocket-factory @TYPE:factory
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from app.services.websocket.connectors.websocket_connector_factory import WebSocketConnectorFactory
from app.services.websocket.config import WebSocketConfigManager


class TestWebSocketConnectorFactory:
    """WebSocketConnectorFactory 테스트 클래스"""

    def test_factory_initializes_with_default_config_manager(self):
        """
        WebSocketConnectorFactory가 기본 설정 관리자로 초기화되는지 테스트

        Given:
            - 팩토리를 기본 생성자로 호출

        When:
            - WebSocketConnectorFactory() 생성

        Then:
            - 팩토리 인스턴스가 생성되어야 함
            - 기본 WebSocketConfigManager가 설정되어야 함
        """
        # Act
        factory = WebSocketConnectorFactory()

        # Assert
        assert factory is not None
        assert factory.config_manager is not None
        assert isinstance(factory.config_manager, WebSocketConfigManager)

    def test_factory_initializes_with_custom_config_manager(self):
        """
        WebSocketConnectorFactory가 커스텀 설정 관리자로 초기화되는지 테스트

        Given:
            - 커스텀 WebSocketConfigManager 인스턴스

        When:
            - WebSocketConnectorFactory(custom_config_manager) 생성

        Then:
            - 팩토리 인스턴스가 생성되어야 함
            - 커스텀 설정 관리자가 설정되어야 함
        """
        # Arrange
        custom_config = WebSocketConfigManager()
        custom_config.set_custom_config("test_key", "test_value")

        # Act
        factory = WebSocketConnectorFactory(custom_config)

        # Assert
        assert factory is not None
        assert factory.config_manager is custom_config
        assert factory.config_manager.get_custom_config("test_key") == "test_value"

    def test_get_supported_connectors_returns_all_supported_types(self):
        """
        get_supported_connectors()가 지원하는 모든 커넥터 타입을 반환하는지 테스트

        Given:
            - 초기화된 WebSocketConnectorFactory 인스턴스

        When:
            - get_supported_connectors() 호출

        Then:
            - 지원하는 커넥터 타입 목록이 반환되어야 함
            - 필수 커넥터 타입이 포함되어야 함 (BinancePublic, BinancePrivate, BybitPublic, BybitPrivate)
        """
        # Arrange
        factory = WebSocketConnectorFactory()

        # Act
        supported_connectors = factory.get_supported_connectors()

        # Assert
        assert supported_connectors is not None
        assert isinstance(supported_connectors, list)
        assert "BinancePublicConnector" in supported_connectors
        assert "BinancePrivateConnector" in supported_connectors
        assert "BybitPublicConnector" in supported_connectors
        assert "BybitPrivateConnector" in supported_connectors

    def test_create_connector_creates_binance_public_connector(self):
        """
        create_connector()가 Binance Public 커넥터를 생성하는지 테스트

        Given:
            - 초기화된 WebSocketConnectorFactory 인스턴스
            - 커넥터 타입 "BinancePublicConnector"

        When:
            - create_connector("BinancePublicConnector") 호출

        Then:
            - BinancePublicConnector 인스턴스가 생성되어야 함
            - 올바른 타입의 커넥터가 반환되어야 함
            - 커넥터가 필요한 설정을 가져야 함
        """
        # Arrange
        factory = WebSocketConnectorFactory()

        # Act
        connector = factory.create_connector("BinancePublicConnector")

        # Assert
        assert connector is not None
        assert connector.__class__.__name__ == "BinancePublicConnector"
        assert hasattr(connector, 'exchange')
        assert connector.exchange == "binance"
        assert hasattr(connector, 'connection_type')
        assert connector.connection_type.value == "price_feed"

    def test_create_connector_creates_binance_private_connector(self):
        """
        create_connector()가 Binance Private 커넥터를 생성하는지 테스트

        Given:
            - 초기화된 WebSocketConnectorFactory 인스턴스
            - 커넥터 타입 "BinancePrivateConnector"

        When:
            - create_connector("BinancePrivateConnector") 호출

        Then:
            - BinancePrivateConnector 인스턴스가 생성되어야 함
            - 올바른 타입의 커넥터가 반환되어야 함
            - 커넥터가 필요한 설정을 가져야 함
        """
        # Arrange
        factory = WebSocketConnectorFactory()

        # Act
        connector = factory.create_connector("BinancePrivateConnector")

        # Assert
        assert connector is not None
        assert connector.__class__.__name__ == "BinancePrivateConnector"
        assert hasattr(connector, 'exchange')
        assert connector.exchange == "binance"
        assert hasattr(connector, 'connection_type')
        assert connector.connection_type.value == "order_execution"

    def test_create_connector_creates_bybit_public_connector(self):
        """
        create_connector()가 Bybit Public 커넥터를 생성하는지 테스트

        Given:
            - 초기화된 WebSocketConnectorFactory 인스턴스
            - 커넥터 타입 "BybitPublicConnector"

        When:
            - create_connector("BybitPublicConnector") 호출

        Then:
            - BybitPublicConnector 인스턴스가 생성되어야 함
            - 올바른 타입의 커넥터가 반환되어야 함
            - 커넥터가 필요한 설정을 가져야 함
        """
        # Arrange
        factory = WebSocketConnectorFactory()

        # Act
        connector = factory.create_connector("BybitPublicConnector")

        # Assert
        assert connector is not None
        assert connector.__class__.__name__ == "BybitPublicConnector"
        assert hasattr(connector, 'exchange')
        assert connector.exchange == "bybit"
        assert hasattr(connector, 'connection_type')
        assert connector.connection_type.value == "price_feed"

    def test_create_connector_creates_bybit_private_connector(self):
        """
        create_connector()가 Bybit Private 커넥터를 생성하는지 테스트

        Given:
            - 초기화된 WebSocketConnectorFactory 인스턴스
            - 커넥터 타입 "BybitPrivateConnector"

        When:
            - create_connector("BybitPrivateConnector") 호출

        Then:
            - BybitPrivateConnector 인스턴스가 생성되어야 함
            - 올바른 타입의 커넥터가 반환되어야 함
            - 커넥터가 필요한 설정을 가져야 함
        """
        # Arrange
        factory = WebSocketConnectorFactory()

        # Act
        connector = factory.create_connector("BybitPrivateConnector")

        # Assert
        assert connector is not None
        assert connector.__class__.__name__ == "BybitPrivateConnector"
        assert hasattr(connector, 'exchange')
        assert connector.exchange == "bybit"
        assert hasattr(connector, 'connection_type')
        assert connector.connection_type.value == "order_execution"

    def test_create_connector_with_unsupported_type_raises_error(self):
        """
        create_connector()가 지원하지 않는 커넥터 타입에 대해 에러를 발생시키는지 테스트

        Given:
            - 초기화된 WebSocketConnectorFactory 인스턴스
            - 지원하지 않는 커넥터 타입

        When:
            - create_connector("UnsupportedConnector") 호출

        Then:
            - ValueError가 발생해야 함
            - 에러 메시지에 지원되지 않는 타입 정보가 포함되어야 함
        """
        # Arrange
        factory = WebSocketConnectorFactory()

        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            factory.create_connector("UnsupportedConnector")

        assert "Unsupported connector type" in str(exc_info.value)
        assert "UnsupportedConnector" in str(exc_info.value)

    def test_create_connector_with_invalid_parameters_raises_error(self):
        """
        create_connector()가 유효하지 않은 파라미터에 대해 에러를 발생시키는지 테스트

        Given:
            - 초기화된 WebSocketConnectorFactory 인스턴스
            - 유효하지 않은 파라미터

        When:
            - create_connector(None) 호출
            - create_connector("") 호출

        Then:
            - ValueError가 발생해야 함
        """
        # Arrange
        factory = WebSocketConnectorFactory()

        # Act & Assert
        with pytest.raises(ValueError):
            factory.create_connector(None)

        with pytest.raises(ValueError):
            factory.create_connector("")

    def test_get_connector_pool_info_returns_pool_statistics(self):
        """
        get_connector_pool_info()가 커넥터 풀 통계를 반환하는지 테스트

        Given:
            - 초기화된 WebSocketConnectorFactory 인스턴스

        When:
            - get_connector_pool_info() 호출

        Then:
            - 커넥터 풀 통계 정보가 반환되어야 함
            - 활성 커넥터 수, 유휴 커넥터 수, 총 커넥터 수가 포함되어야 함
        """
        # Arrange
        factory = WebSocketConnectorFactory()

        # Act
        pool_info = factory.get_connector_pool_info()

        # Assert
        assert pool_info is not None
        assert isinstance(pool_info, dict)
        assert "active_connectors" in pool_info
        assert "idle_connectors" in pool_info
        assert "total_connectors" in pool_info
        assert "max_pool_size" in pool_info

    def test_factory_cleanup_releases_resources(self):
        """
        팩토리 cleanup()이 리소스를 정리하는지 테스트

        Given:
            - 커넥터가 생성된 WebSocketConnectorFactory 인스턴스

        When:
            - cleanup() 호출

        Then:
            - 모든 커넥터 연결이 종료되어야 함
            - 리소스가 정리되어야 함
        """
        # Arrange
        factory = WebSocketConnectorFactory()
        connector1 = factory.create_connector("BinancePublicConnector")
        connector2 = factory.create_connector("BybitPublicConnector")

        # Act
        factory.cleanup()

        # Assert
        pool_info = factory.get_connector_pool_info()
        assert pool_info["total_connectors"] == 0
        assert pool_info["active_connectors"] == 0

    def test_connector_reuse_uses_existing_connections(self):
        """
        커넥터 재사용이 기존 연결을 사용하는지 테스트

        Given:
            - WebSocketConnectorFactory 인스턴스
            - 동일한 타입의 커넥터 요청

        When:
            - 동일한 타입으로 여러 커넥터 생성

        Then:
            - 기존 연결이 재사용되어야 함
            - 새로운 연결이 불필요하게 생성되지 않아야 함
        """
        # Arrange
        factory = WebSocketConnectorFactory()

        # Act
        connector1 = factory.create_connector("BinancePublicConnector")
        connector2 = factory.create_connector("BinancePublicConnector")

        # Assert
        # 동일한 연결을 공유해야 함 (풀링 동작)
        pool_info = factory.get_connector_pool_info()
        assert pool_info["total_connectors"] == 1  # 하나의 연결만 생성됨
        assert pool_info["active_connectors"] == 1

    @pytest.mark.asyncio
    async def test_async_connector_creation_works(self):
        """
        비동기 커넥터 생성이 올바르게 작동하는지 테스트

        Given:
            - 초기화된 WebSocketConnectorFactory 인스턴스

        When:
            - async_create_connector() 호출

        Then:
            - 비동기적으로 커넥터가 생성되어야 함
            - 생성된 커넥터가 유효해야 함
        """
        # Arrange
        factory = WebSocketConnectorFactory()

        # Act
        connector = await factory.async_create_connector("BinancePublicConnector")

        # Assert
        assert connector is not None
        assert connector.__class__.__name__ == "BinancePublicConnector"

    def test_factory_registers_custom_connectors(self):
        """
        팩토리가 커스텀 커넥터를 등록하는지 테스트

        Given:
            - WebSocketConnectorFactory 인스턴스
            - 커스텀 커넥터 클래스

        When:
            - register_custom_connector() 호출

        Then:
            - 커스텀 커넥터가 등록되어야 함
            - 지원되는 커넥터 목록에 포함되어야 함
        """
        # Arrange
        factory = WebSocketConnectorFactory()

        # Define a custom connector class for testing
        class CustomTestConnector:
            def __init__(self):
                self.exchange = "custom"
                self.connection_type = "test"

        # Act
        factory.register_custom_connector("CustomTestConnector", CustomTestConnector)

        # Assert
        supported_connectors = factory.get_supported_connectors()
        assert "CustomTestConnector" in supported_connectors

        # Verify it can be created
        connector = factory.create_connector("CustomTestConnector")
        assert isinstance(connector, CustomTestConnector)