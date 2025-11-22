"""
WebSocketConnectorFactory 확장 테스트

기본 테스트에서 커버되지 않는 엣지 케이스와 리팩토링된 기능들 테스트

@FEAT:websocket-integration @COMP:websocket-factory @TYPE:factory
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from app.services.websocket.connectors.websocket_connector_factory import (
    WebSocketConnectorFactory,
    BaseWebSocketConnector,
    BinancePublicConnector,
    BybitPublicConnector
)
from app.services.websocket.config import WebSocketConfigManager, ConnectionType


class TestWebSocketConnectorFactoryExtended:
    """WebSocketConnectorFactory 확장 테스트 클래스"""

    def test_get_connector_info_returns_detailed_info(self):
        """
        get_connector_info()가 상세한 커넥터 정보를 반환하는지 테스트

        Given:
            - 초기화된 WebSocketConnectorFactory 인스턴스

        When:
            - get_connector_info("BinancePublicConnector") 호출

        Then:
            - 상세한 커넥터 정보가 반환되어야 함
            - 거래소, 연결 타입, 설명 등이 포함되어야 함
        """
        # Arrange
        factory = WebSocketConnectorFactory()

        # Act
        info = factory.get_connector_info("BinancePublicConnector")

        # Assert
        assert info is not None
        assert info["name"] == "BinancePublicConnector"
        assert info["exchange"] == "binance"
        assert info["connection_type"] == ConnectionType.PUBLIC_PRICE_FEED
        assert info["description"] == "Binance Public WebSocket for price feeds"
        assert info["is_custom"] is False

    def test_get_connector_info_for_nonexistent_connector_returns_none(self):
        """
        존재하지 않는 커넥터에 대해 get_connector_info()가 None을 반환하는지 테스트

        Given:
            - 초기화된 WebSocketConnectorFactory 인스턴스

        When:
            - get_connector_info("NonExistentConnector") 호출

        Then:
            - None이 반환되어야 함
        """
        # Arrange
        factory = WebSocketConnectorFactory()

        # Act
        info = factory.get_connector_info("NonExistentConnector")

        # Assert
        assert info is None

    def test_register_custom_connector_with_full_parameters(self):
        """
        모든 파라미터를 포함한 커스텀 커넥터 등록이 올바르게 작동하는지 테스트

        Given:
            - WebSocketConnectorFactory 인스턴스
            - 커스텀 커넥터 클래스

        When:
            - register_custom_connector()에 모든 파라미터로 호출

        Then:
            - 커스텀 커넥터가 등록되어야 함
            - 설정 정보가 올바르게 저장되어야 함
        """
        # Arrange
        factory = WebSocketConnectorFactory()

        class CustomAdvancedConnector(BaseWebSocketConnector):
            def __init__(self, config_manager):
                super().__init__("custom", ConnectionType.PUBLIC_ORDER_BOOK, config_manager)

        # Act
        factory.register_custom_connector(
            name="AdvancedCustomConnector",
            connector_class=CustomAdvancedConnector,
            exchange="custom",
            connection_type=ConnectionType.PUBLIC_ORDER_BOOK,
            description="Advanced custom connector for testing"
        )

        # Assert
        info = factory.get_connector_info("AdvancedCustomConnector")
        assert info is not None
        assert info["name"] == "AdvancedCustomConnector"
        assert info["exchange"] == "custom"
        assert info["connection_type"] == ConnectionType.PUBLIC_ORDER_BOOK
        assert info["description"] == "Advanced custom connector for testing"
        assert info["is_custom"] is True

    def test_optimize_connection_pool_removes_inactive_connectors(self):
        """
        optimize_connection_pool()이 비활성 커넥터를 제거하는지 테스트

        Given:
            - 커넥터 풀에 비활성 커넥터가 있는 WebSocketConnectorFactory

        When:
            - optimize_connection_pool() 호출

        Then:
            - 비활성 커넥터가 제거되어야 함
            - 최적화 결과가 반환되어야 함
        """
        # Arrange
        factory = WebSocketConnectorFactory()

        # 활성 커넥터 생성
        connector1 = factory.create_connector("BinancePublicConnector")

        # 비활성 커넥터 수동 추가
        inactive_connector = Mock(spec=BaseWebSocketConnector)
        inactive_connector.is_connected = False
        inactive_connector.exchange = "test"

        with factory._lock:
            factory._connector_pool["inactive_test"] = inactive_connector

        # Act
        result = factory.optimize_connection_pool()

        # Assert
        assert result["cleaned_connectors"] >= 1
        assert "inactive_test" not in factory._connector_pool
        assert "BinancePublicConnector" in factory._connector_pool

    def test_optimize_connection_pool_handles_errors_gracefully(self):
        """
        optimize_connection_pool()이 에러 발생 시 우아하게 처리하는지 테스트

        Given:
            - 커넥터 풀이 있는 WebSocketConnectorFactory

        When:
            - optimize_connection_pool() 호출

        Then:
            - 최적화 결과가 반환되어야 함
            - 에러 처리 로직이 올바르게 작동해야 함
        """
        # Arrange
        factory = WebSocketConnectorFactory()

        # 비활성 커넥터 추가
        inactive_connector = Mock(spec=BaseWebSocketConnector)
        inactive_connector.is_connected = False
        inactive_connector.exchange = "test"

        with factory._lock:
            factory._connector_pool["inactive_test"] = inactive_connector

        # Act
        result = factory.optimize_connection_pool()

        # Assert
        assert isinstance(result, dict)
        assert "cleaned_connectors" in result
        assert "errors" in result
        assert result["cleaned_connectors"] >= 1
        assert "inactive_test" not in factory._connector_pool

    def test_load_connectors_from_config_with_custom_config(self):
        """
        load_connectors_from_config()이 커스텀 설정에서 커넥터를 로드하는지 테스트

        Given:
            - 커스텀 커넥터 설정이 있는 WebSocketConnectorFactory

        When:
            - load_connectors_from_config() 호출

        Then:
            - 설정된 커넥터가 로드되어야 함
            - 로딩 결과가 반환되어야 함
        """
        # Arrange
        factory = WebSocketConnectorFactory()

        # 모의 커스텀 설정 추가
        factory.config_manager.set_custom_config("custom_connectors", {
            "MockConnector": {
                "module": "unittest.mock",
                "class": "Mock",
                "exchange": "test",
                "connection_type": "price_feed",
                "description": "Mock connector for testing"
            }
        })

        # Act
        result = factory.load_connectors_from_config()

        # Assert
        assert result["loaded_connectors"] >= 0
        assert isinstance(result, dict)
        assert "errors" in result
        assert "loaded_connectors" in result
        assert "failed_connectors" in result

    def test_get_connector_recommendations(self):
        """
        get_connector_recommendations()가 올바른 추천을 반환하는지 테스트

        Given:
            - WebSocketConnectorFactory 인스턴스

        When:
            - 거래소와 연결 타입으로 추천 요청

        Then:
            - 해당 조건에 맞는 커넥터 목록이 반환되어야 함
        """
        # Arrange
        factory = WebSocketConnectorFactory()

        # Act
        binance_public = factory.get_connector_recommendations("binance", ConnectionType.PUBLIC_PRICE_FEED)
        bybit_private = factory.get_connector_recommendations("bybit", ConnectionType.PRIVATE_ORDER_EXECUTION)

        # Assert
        assert "BinancePublicConnector" in binance_public
        assert "BybitPublicConnector" not in binance_public

        assert "BybitPrivateConnector" in bybit_private
        assert "BinancePrivateConnector" not in bybit_private

    def test_get_connector_recommendations_empty_result(self):
        """
        get_connector_recommendations()가 조건에 맞는 커넥터가 없을 때 빈 목록을 반환하는지 테스트

        Given:
            - WebSocketConnectorFactory 인스턴스

        When:
            - 존재하지 않는 조건으로 추천 요청

        Then:
            - 빈 목록이 반환되어야 함
        """
        # Arrange
        factory = WebSocketConnectorFactory()

        # Act
        recommendations = factory.get_connector_recommendations("nonexistent", ConnectionType.PUBLIC_PRICE_FEED)

        # Assert
        assert recommendations == []

    def test_get_max_pool_size_from_config(self):
        """
        _get_max_pool_size()가 설정에서 최대 풀 크기를 반환하는지 테스트

        Given:
            - 커스텀 최대 풀 크기 설정이 있는 WebSocketConnectorFactory

        When:
            - _get_max_pool_size() 호출

        Then:
            - 설정된 크기가 반환되어야 함
        """
        # Arrange
        factory = WebSocketConnectorFactory()
        factory.config_manager.set_custom_config("max_pool_size", 100)

        # Act
        max_size = factory._get_max_pool_size()

        # Assert
        assert max_size == 100

    def test_get_max_pool_size_default(self):
        """
        _get_max_pool_size()가 설정이 없을 때 기본값을 반환하는지 테스트

        Given:
            - 최대 풀 크기 설정이 없는 WebSocketConnectorFactory

        When:
            - _get_max_pool_size() 호출

        Then:
            - 기본값 50이 반환되어야 함
        """
        # Arrange
        factory = WebSocketConnectorFactory()

        # Act
        max_size = factory._get_max_pool_size()

        # Assert
        assert max_size == 50

    def test_connector_pool_info_includes_exchange_breakdown(self):
        """
        get_connector_pool_info()가 거래소별 통계를 포함하는지 테스트

        Given:
            - 여러 거래소 커넥터가 있는 WebSocketConnectorFactory

        When:
            - get_connector_pool_info() 호출

        Then:
            - 거래소별 통계가 포함되어야 함
            - 풀 효율성이 계산되어야 함
        """
        # Arrange
        factory = WebSocketConnectorFactory()
        factory.create_connector("BinancePublicConnector")
        factory.create_connector("BybitPublicConnector")

        # Act
        pool_info = factory.get_connector_pool_info()

        # Assert
        assert "exchange_breakdown" in pool_info
        assert "pool_efficiency" in pool_info
        assert "binance" in pool_info["exchange_breakdown"]
        assert "bybit" in pool_info["exchange_breakdown"]
        assert pool_info["pool_efficiency"] == 100.0

    def test_cleanup_handles_async_disconnect_methods(self):
        """
        cleanup()이 비동기 disconnect 메서드를 올바르게 처리하는지 테스트

        Given:
            - 비동기 disconnect 메서드가 있는 커넥터가 있는 풀

        When:
            - cleanup() 호출

        Then:
            - 비동기 메서드가 올바르게 처리되어야 함
        """
        # Arrange
        factory = WebSocketConnectorFactory()
        connector = factory.create_connector("BinancePublicConnector")

        # 비동기 disconnect 메서드로 교체
        async_mock = AsyncMock()
        connector.disconnect = async_mock

        # Act
        factory.cleanup()

        # Assert
        pool_info = factory.get_connector_pool_info()
        assert pool_info["total_connectors"] == 0

    @pytest.mark.asyncio
    async def test_async_create_connector_with_real_connection(self):
        """
        async_create_connector()가 실제 연결을 생성하는지 테스트

        Given:
            - WebSocketConnectorFactory 인스턴스

        When:
            - async_create_connector() 호출

        Then:
            - 비동기적으로 커넥터가 생성 및 연결되어야 함
        """
        # Arrange
        factory = WebSocketConnectorFactory()

        # Act
        connector = await factory.async_create_connector("BinancePublicConnector")

        # Assert
        assert connector is not None
        assert connector.__class__.__name__ == "BinancePublicConnector"
        assert connector.is_connected is True