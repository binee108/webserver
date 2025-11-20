"""
WebSocket State Tracking GREEN Tests - Verify the Fix Works

This test file verifies that the enhanced state tracking system properly
addresses the issues exposed in the RED tests.

@FEAT:websocket-state-tracking @COMP:service @TYPE:testing
"""

import asyncio
import pytest
import time
from unittest.mock import AsyncMock, Mock, patch
from app.services.websocket_manager import WebSocketManager, WebSocketConnection, ConnectionState


class MockAccount:
    def __init__(self):
        self.id = 12345
        self._exchange = 'BINANCE'
        self.api_key = 'test_api_key'

    @property
    def exchange(self):
        return 'BINANCE'


class TestWebSocketStateTrackingGreen:
    """Tests for @FEAT:websocket-state-tracking GREEN phase"""

    @pytest.fixture
    def mock_app(self):
        app = Mock()
        app.app_context.return_value.__enter__ = Mock()
        app.app_context.return_value.__exit__ = Mock()
        return app

    @pytest.fixture
    def websocket_manager(self, mock_app):
        manager = WebSocketManager(mock_app)
        manager.start()
        yield manager
        if manager._running:
            manager.stop()

    @pytest.mark.asyncio
    async def test_enhanced_state_tracking_works(self, websocket_manager):
        """
        GREEN TEST: Verify enhanced state tracking functionality
        """
        connection = WebSocketConnection(12345, 'BINANCE', Mock())

        # ✅ SUCCESS: Proper state enum instead of boolean
        assert hasattr(connection, 'state')
        assert connection.state == ConnectionState.DISCONNECTED  # Initial state
        assert isinstance(connection.state, ConnectionState)

        # ✅ SUCCESS: Backward compatibility with boolean
        assert hasattr(connection, 'is_connected')
        assert connection.is_connected is False  # False for DISCONNECTED state

        # ✅ SUCCESS: State transitions work properly
        connection.set_state(ConnectionState.CONNECTING)
        assert connection.state == ConnectionState.CONNECTING
        assert connection.is_connected is False  # Still False for CONNECTING

        connection.set_state(ConnectionState.CONNECTED)
        assert connection.state == ConnectionState.CONNECTED
        assert connection.is_connected is True  # True only for CONNECTED state

        print("✅ SUCCESS: Enhanced state tracking with proper enum works")

    @pytest.mark.asyncio
    async def test_state_transition_validation(self, websocket_manager):
        """
        GREEN TEST: Verify state transition validation works
        """
        connection = WebSocketConnection(12345, 'BINANCE', Mock())

        # ✅ SUCCESS: Valid transitions work
        connection.set_state(ConnectionState.CONNECTING)  # DISCONNECTED -> CONNECTING
        assert connection.state == ConnectionState.CONNECTING

        connection.set_state(ConnectionState.CONNECTED)   # CONNECTING -> CONNECTED
        assert connection.state == ConnectionState.CONNECTED

        connection.set_state(ConnectionState.DISCONNECTING)  # CONNECTED -> DISCONNECTING
        assert connection.state == ConnectionState.DISCONNECTING

        connection.set_state(ConnectionState.DISCONNECTED)    # DISCONNECTING -> DISCONNECTED
        assert connection.state == ConnectionState.DISCONNECTED

        # ✅ SUCCESS: Invalid transitions are handled gracefully
        connection.set_state(ConnectionState.CONNECTED)  # Reset to connected
        connection.set_state(ConnectionState.CONNECTING)  # CONNECTED -> CONNECTING (invalid)
        # Should transition to ERROR state instead
        assert connection.state == ConnectionState.ERROR

        print("✅ SUCCESS: State transition validation works properly")

    @pytest.mark.asyncio
    async def test_connection_health_metadata_available(self, websocket_manager):
        """
        GREEN TEST: Verify connection health metadata is available
        """
        connection = WebSocketConnection(12345, 'BINANCE', Mock())

        # ✅ SUCCESS: Essential health metadata available
        required_metadata = [
            'state_changed_time', 'connection_attempt_count',
            'last_ping_time', 'last_message_time', 'last_error',
            'connection_start_time', 'bytes_received', 'bytes_sent'
        ]

        for metadata in required_metadata:
            assert hasattr(connection, metadata), f"Missing metadata: {metadata}"

        # ✅ SUCCESS: Health metadata can be updated
        current_time = time.time()
        connection.update_health_metadata(
            ping_time=current_time,
            message_time=current_time,
            bytes_received=1024,
            bytes_sent=512
        )

        assert connection.last_ping_time == current_time
        assert connection.last_message_time == current_time
        assert connection.bytes_received == 1024
        assert connection.bytes_sent == 512

        print("✅ SUCCESS: Connection health metadata properly implemented")

    @pytest.mark.asyncio
    async def test_real_time_state_validation(self, websocket_manager):
        """
        GREEN TEST: Verify real-time state validation capabilities
        """
        connection = WebSocketConnection(12345, 'BINANCE', Mock())

        # ✅ SUCCESS: Health validation works
        # Initially disconnected - should be unhealthy
        assert connection.is_healthy() is False

        # Set to connected state
        connection.set_state(ConnectionState.CONNECTED)
        assert connection.is_healthy() is True

        # Simulate old ping time - should be unhealthy
        old_time = time.time() - 120  # 2 minutes ago
        connection.update_health_metadata(ping_time=old_time)
        assert connection.is_healthy() is False

        # Update with recent ping time - should be healthy again
        current_time = time.time()
        connection.update_health_metadata(ping_time=current_time)
        assert connection.is_healthy() is True

        print("✅ SUCCESS: Real-time state validation works properly")

    @pytest.mark.asyncio
    async def test_connection_info_monitoring(self, websocket_manager):
        """
        GREEN TEST: Verify connection information for monitoring
        """
        connection = WebSocketConnection(12345, 'BINANCE', Mock())
        connection.set_state(ConnectionState.CONNECTED)
        connection.update_health_metadata(ping_time=time.time())
        connection.subscribed_symbols.add('BTCUSDT')
        connection.subscribed_symbols.add('ETHUSDT')

        # ✅ SUCCESS: Connection info provides comprehensive data
        info = connection.get_connection_info()

        assert info['account_id'] == 12345
        assert info['exchange'] == 'BINANCE'
        assert info['state'] == 'connected'
        assert info['connection_attempt_count'] == 0  # Connected directly
        assert info['subscribed_symbols_count'] == 2
        assert 'is_healthy' in info
        assert 'last_ping_time' in info
        assert 'state_changed_time' in info

        print("✅ SUCCESS: Connection monitoring information available")

    @pytest.mark.asyncio
    async def test_connect_account_with_state_tracking(self, websocket_manager):
        """
        GREEN TEST: Verify connect_account method uses new state tracking
        """
        mock_account = MockAccount()
        mock_handler = AsyncMock()
        mock_handler.connect.return_value = None  # Success

        # Mock Account.query.get
        mock_query = Mock()
        mock_query.get.return_value = mock_account

        mock_account_query = Mock()
        mock_account_query.query = mock_query

        with patch('app.services.websocket_manager.Account', mock_account_query):
            with patch.dict('sys.modules', {
                'app.services.exchanges.binance_websocket': Mock(BinanceWebSocket=Mock(return_value=mock_handler))
            }):
                # Connect account - should go through proper state transitions
                result = await websocket_manager.connect_account(12345)

                assert result is True
                assert 12345 in websocket_manager.connections

                connection = websocket_manager.connections[12345]
                assert connection.state == ConnectionState.CONNECTED
                assert connection.is_connected is True
                assert connection.connection_attempt_count >= 1

        print("✅ SUCCESS: connect_account properly integrated with state tracking")