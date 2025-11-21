"""
WebSocket Handler AttributeError Fix Tests

@FEAT:websocket-handler-refactoring @COMP:exchange @TYPE:core @DEPS:websocket-context-helper

Tests to verify that WebSocket handlers properly access Flask app through manager
instead of trying to access self.app directly.
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch
from flask import Flask

# Note: We'll fix the imports later when the code is fixed
# For now, we'll test the concept


class TestWebSocketAttributeError:
    """Tests to verify AttributeError fix for WebSocket handlers"""

    @pytest.fixture
    def app(self):
        """Flask app fixture"""
        app = Flask(__name__)
        app.config['TESTING'] = True
        return app

    @pytest.fixture
    def mock_account(self):
        """Mock account fixture"""
        account = Mock()
        account.id = 1
        account.api_key = 'test_key'
        account.api_secret = 'test_secret'
        account.exchange = 'binance'
        return account

    @pytest.fixture
    def mock_manager(self, app):
        """Mock WebSocket manager with Flask app"""
        manager = Mock()
        manager.app = app
        manager.auto_reconnect = AsyncMock()
        return manager

    @pytest.mark.asyncio
    async def test_binance_websocket_access_app_through_manager(self, app, mock_account, mock_manager):
        """
        🟥 RED: BinanceWebSocket should access app via self.manager.app, not self.app

        This test will fail until we fix the WebSocket handlers to use manager.app
        """
        # Import here to avoid import errors before the fix
        from app.services.exchanges.binance_websocket import BinanceWebSocket

        handler = BinanceWebSocket(mock_account, mock_manager)

        # Verify the handler has manager but not direct app access
        assert hasattr(handler, 'manager')
        assert not hasattr(handler, 'app')

        # Verify we can access app through manager
        assert handler.manager.app is app

        # Test that WebSocketContextHelper can be created with manager.app
        from app.services.websocket_context_helper import WebSocketContextHelper

        # This should work - using manager.app
        helper = WebSocketContextHelper(handler.manager.app)
        assert helper.app is app

    @pytest.mark.asyncio
    async def test_bybit_websocket_access_app_through_manager(self, app, mock_account, mock_manager):
        """
        🟥 RED: BybitWebSocket should access app via self.manager.app, not self.app

        This test will fail until we fix the WebSocket handlers to use manager.app
        """
        # Import here to avoid import errors before the fix
        from app.services.exchanges.bybit_websocket import BybitWebSocket

        handler = BybitWebSocket(mock_account, mock_manager)

        # Verify the handler has manager but not direct app access
        assert hasattr(handler, 'manager')
        assert not hasattr(handler, 'app')

        # Verify we can access app through manager
        assert handler.manager.app is app

        # Test that WebSocketContextHelper can be created with manager.app
        from app.services.websocket_context_helper import WebSocketContextHelper

        # This should work - using manager.app
        helper = WebSocketContextHelper(handler.manager.app)
        assert helper.app is app

    @pytest.mark.asyncio
    async def test_receive_messages_should_not_fail_with_attribute_error(self, app, mock_account, mock_manager):
        """
        🟥 RED: _receive_messages should not fail due to AttributeError on self.app

        This test verifies that the _receive_messages method can properly access
        the Flask app through the manager without AttributeError.
        """
        from app.services.exchanges.binance_websocket import BinanceWebSocket
        from app.services.websocket_context_helper import WebSocketContextHelper

        handler = BinanceWebSocket(mock_account, mock_manager)

        # Mock WebSocket connection
        mock_ws = AsyncMock()
        handler.ws = mock_ws
        handler._running = True

        # Simulate a test message
        test_message = json.dumps({
            'e': 'ORDER_TRADE_UPDATE',
            'o': {
                's': 'BTCUSDT',
                'i': '12345',
                'X': 'FILLED'
            }
        })

        # Configure mock WebSocket to return the test message and then stop
        mock_ws.__aiter__.return_value = [test_message]

        # This should work without AttributeError when we fix the handlers
        with patch('app.services.websocket_context_helper.WebSocketContextHelper') as mock_helper_class:
            mock_helper = Mock()
            mock_helper.execute_with_db_context = AsyncMock()
            mock_helper_class.return_value = mock_helper

            # Call _receive_messages - this should not fail with AttributeError
            try:
                await handler._receive_messages()
                print("✅ _receive_messages completed without AttributeError")

                # Verify that WebSocketContextHelper was called with the correct app
                mock_helper_class.assert_called_once_with(app)
                mock_helper.execute_with_db_context.assert_called()

            except AttributeError as e:
                if "'app'" in str(e):
                    pytest.fail(f"AttributeError occurred when accessing app: {e}")
                else:
                    # Some other AttributeError - re-raise
                    raise