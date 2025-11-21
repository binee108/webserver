"""
Tests for WebSocket Context Helper

This module tests the WebSocketContextHelper that provides message-specific
database session management for WebSocket operations.

@FEAT:websocket-context-helper @COMP:service @TYPE:helper @DEPS:db-session-management
"""

import pytest
import asyncio
import logging
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Optional, Any, Callable

# Import the module we're going to create (this will fail initially)
try:
    from web_server.app.services.websocket_context_helper import WebSocketContextHelper
except ImportError:
    WebSocketContextHelper = None


class TestWebSocketContextHelper:
    """Test WebSocketContextHelper functionality."""

    @pytest.mark.asyncio
    async def test_websocket_context_helper_creation(self):
        """Test WebSocketContextHelper can be created with Flask app."""
        if WebSocketContextHelper is None:
            pytest.skip("WebSocketContextHelper not implemented yet")

        # Arrange
        mock_app = Mock()

        # Act
        helper = WebSocketContextHelper(mock_app)

        # Assert
        assert helper is not None
        assert helper.app == mock_app

    @pytest.mark.asyncio
    async def test_execute_with_db_context_basic_functionality(self):
        """Test basic database context execution functionality."""
        if WebSocketContextHelper is None:
            pytest.skip("WebSocketContextHelper not implemented yet")

        # Arrange
        mock_app = Mock()
        helper = WebSocketContextHelper(mock_app)
        mock_func = AsyncMock(return_value="test_result")

        # Mock app_context to behave like Flask's app context
        mock_app_context_manager = Mock()
        mock_app_context_manager.__enter__ = Mock(return_value=None)
        mock_app_context_manager.__exit__ = Mock(return_value=None)
        mock_app.app_context = Mock(return_value=mock_app_context_manager)

        # Act
        result = await helper.execute_with_db_context(mock_func, "arg1", kwarg1="value1")

        # Assert
        assert result == "test_result"
        mock_func.assert_called_once_with("arg1", kwarg1="value1")
        mock_app.app_context.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_with_db_context_handles_exceptions(self):
        """Test database context execution handles exceptions properly."""
        if WebSocketContextHelper is None:
            pytest.skip("WebSocketContextHelper not implemented yet")

        # Arrange
        mock_app = Mock()
        helper = WebSocketContextHelper(mock_app)
        test_error = ValueError("Test error")
        mock_func = AsyncMock(side_effect=test_error)

        # Mock app_context
        mock_app_context_manager = Mock()
        mock_app_context_manager.__enter__ = Mock(return_value=None)
        mock_app_context_manager.__exit__ = Mock(return_value=None)
        mock_app.app_context = Mock(return_value=mock_app_context_manager)

        # Act & Assert
        with pytest.raises(ValueError, match="Test error"):
            await helper.execute_with_db_context(mock_func)

        # Ensure app context is still called even when function fails
        mock_app.app_context.assert_called_once()

    @pytest.mark.asyncio
    async def test_message_specific_session_isolation(self):
        """Test that each message gets its own database session."""
        if WebSocketContextHelper is None:
            pytest.skip("WebSocketContextHelper not implemented yet")

        # Arrange
        mock_app = Mock()
        helper = WebSocketContextHelper(mock_app)
        call_count = 0

        async def track_call():
            nonlocal call_count
            call_count += 1
            return f"call_{call_count}"

        # Mock app_context with different session tracking
        contexts_called = []

        def mock_app_context():
            mock_context = Mock()
            mock_context.__enter__ = Mock(return_value=f"session_{len(contexts_called)}")
            mock_context.__exit__ = Mock(return_value=None)
            contexts_called.append(mock_context)
            return mock_context

        mock_app.app_context = Mock(side_effect=mock_app_context)

        # Act
        result1 = await helper.execute_with_db_context(track_call)
        result2 = await helper.execute_with_db_context(track_call)

        # Assert
        assert result1 == "call_1"
        assert result2 == "call_2"
        assert call_count == 2
        # Verify separate app contexts were created
        assert len(contexts_called) == 2

    @pytest.mark.asyncio
    async def test_connection_pool_monitoring(self):
        """Test connection pool monitoring functionality."""
        if WebSocketContextHelper is None:
            pytest.skip("WebSocketContextHelper not implemented yet")

        # Arrange
        mock_app = Mock()
        helper = WebSocketContextHelper(mock_app)

        # Mock SQLAlchemy engine with pool status
        mock_engine = Mock()
        mock_pool = Mock()
        mock_pool.size = lambda: 5
        mock_pool.checked_in = lambda: 3
        mock_pool.checked_out = lambda: 2
        mock_engine.pool = mock_pool

        # Mock the app's database engine
        mock_app.extensions = {}
        mock_app.extensions['sqlalchemy'] = Mock()
        mock_app.extensions['sqlalchemy'].engine = mock_engine

        # Act
        pool_status = helper.get_connection_pool_status()

        # Assert
        assert pool_status is not None
        assert 'size' in pool_status
        assert 'checked_in' in pool_status
        assert 'checked_out' in pool_status
        assert pool_status['size'] == 5
        assert pool_status['checked_in'] == 3
        assert pool_status['checked_out'] == 2

    @pytest.mark.asyncio
    async def test_async_context_manager_interface(self):
        """Test WebSocketContextHelper as async context manager."""
        if WebSocketContextHelper is None:
            pytest.skip("WebSocketContextHelper not implemented yet")

        # Arrange
        mock_app = Mock()
        mock_func = AsyncMock(return_value="context_result")

        # Mock app_context
        mock_app_context_manager = Mock()
        mock_app_context_manager.__enter__ = Mock(return_value=None)
        mock_app_context_manager.__exit__ = Mock(return_value=None)
        mock_app.app_context = Mock(return_value=mock_app_context_manager)

        # Act
        async with WebSocketContextHelper(mock_app) as helper:
            result = await helper.execute_with_db_context(mock_func)

        # Assert
        assert result == "context_result"
        mock_func.assert_called_once()

    @pytest.mark.asyncio
    async def test_logging_and_error_reporting(self):
        """Test proper logging and error reporting."""
        if WebSocketContextHelper is None:
            pytest.skip("WebSocketContextHelper not implemented yet")

        # Arrange
        mock_app = Mock()
        helper = WebSocketContextHelper(mock_app)
        test_error = RuntimeError("Test runtime error")
        mock_func = AsyncMock(side_effect=test_error)

        # Mock app_context
        mock_app_context_manager = Mock()
        mock_app_context_manager.__enter__ = Mock(return_value=None)
        mock_app_context_manager.__exit__ = Mock(return_value=None)
        mock_app.app_context = Mock(return_value=mock_app_context_manager)

        # Mock logger at module level
        with patch.object(helper, '_logger') as mock_logger:
            # Act & Assert
            with pytest.raises(RuntimeError, match="Test runtime error"):
                await helper.execute_with_db_context(mock_func)

            # Verify error was logged
            mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_concurrent_message_processing(self):
        """Test concurrent message processing with separate sessions."""
        if WebSocketContextHelper is None:
            pytest.skip("WebSocketContextHelper not implemented yet")

        # Arrange
        mock_app = Mock()
        helper = WebSocketContextHelper(mock_app)

        async def process_message(message_id: str):
            await asyncio.sleep(0.1)  # Simulate async work
            return f"processed_{message_id}"

        # Mock app_context for each concurrent call
        def mock_app_context():
            mock_context = Mock()
            mock_context.__enter__ = Mock(return_value=None)
            mock_context.__exit__ = Mock(return_value=None)
            return mock_context

        mock_app.app_context = Mock(side_effect=mock_app_context)

        # Act - Run multiple messages concurrently
        messages = ["msg1", "msg2", "msg3", "msg4", "msg5"]
        tasks = [
            helper.execute_with_db_context(process_message, msg)
            for msg in messages
        ]
        results = await asyncio.gather(*tasks)

        # Assert
        expected_results = [f"processed_{msg}" for msg in messages]
        assert results == expected_results
        # Verify each call got its own app context
        assert mock_app.app_context.call_count == len(messages)

    @pytest.mark.asyncio
    async def test_resource_cleanup_validation(self):
        """Test that database sessions are properly cleaned up."""
        if WebSocketContextHelper is None:
            pytest.skip("WebSocketContextHelper not implemented yet")

        # Arrange
        mock_app = Mock()
        helper = WebSocketContextHelper(mock_app)

        # Track context cleanup
        cleanup_called = []

        def create_mock_context():
            mock_context = Mock()
            mock_context.__enter__ = Mock(return_value=None)

            def mock_exit(*args):
                cleanup_called.append(True)
                return None

            mock_context.__exit__ = Mock(side_effect=mock_exit)
            return mock_context

        mock_app.app_context = Mock(side_effect=create_mock_context)
        mock_func = AsyncMock(return_value="cleanup_test")

        # Act
        result = await helper.execute_with_db_context(mock_func)

        # Assert
        assert result == "cleanup_test"
        assert len(cleanup_called) == 1
        mock_func.assert_called_once()

    @pytest.mark.asyncio
    async def test_integration_with_existing_codebase_patterns(self):
        """Test compatibility with existing codebase patterns."""
        if WebSocketContextHelper is None:
            pytest.skip("WebSocketContextHelper not implemented yet")

        # Arrange - Simulate pattern from order_fill_monitor.py
        mock_app = Mock()
        helper = WebSocketContextHelper(mock_app)

        # Mock Account.query.get() pattern used in existing code
        mock_account = Mock()
        mock_account.id = 123
        mock_account.exchange = "BINANCE"

        async def get_account_with_context(account_id: int):
            """Simulate existing pattern: with app.app_context(): Account.query.get(account_id)"""
            # This would normally use the app context to access the database
            if account_id == 123:
                return mock_account
            return None

        # Mock app_context
        mock_app_context_manager = Mock()
        mock_app_context_manager.__enter__ = Mock(return_value=None)
        mock_app_context_manager.__exit__ = Mock(return_value=None)
        mock_app.app_context = Mock(return_value=mock_app_context_manager)

        # Act
        result = await helper.execute_with_db_context(get_account_with_context, 123)

        # Assert
        assert result is not None
        assert result.id == 123
        assert result.exchange == "BINANCE"

    @pytest.mark.asyncio
    async def test_websocket_context_error_handling(self):
        """Test WebSocketContextError exception class."""
        from web_server.app.services.websocket_context_helper import WebSocketContextError

        # Test exception creation and inheritance
        error = WebSocketContextError("Test error")
        assert str(error) == "Test error"
        assert isinstance(error, Exception)

    def test_websocket_context_helper_initialization_validation(self):
        """Test WebSocketContextHelper initialization with validation."""
        if WebSocketContextHelper is None:
            pytest.skip("WebSocketContextHelper not implemented yet")

        # Test with None app - should raise WebSocketContextError
        with pytest.raises(Exception) as exc_info:
            WebSocketContextHelper(None)

        # Verify the error message
        assert "Flask app 인스턴스가 필요합니다" in str(exc_info.value)

        # Test with valid app
        mock_app = Mock()
        helper = WebSocketContextHelper(mock_app)
        assert helper.app == mock_app
        assert helper._logger is not None

    @pytest.mark.asyncio
    async def test_execute_with_invalid_function(self):
        """Test execute_with_db_context with invalid function."""
        if WebSocketContextHelper is None:
            pytest.skip("WebSocketContextHelper not implemented yet")

        # Arrange
        mock_app = Mock()
        helper = WebSocketContextHelper(mock_app)

        # Act & Assert
        with pytest.raises(Exception) as exc_info:
            await helper.execute_with_db_context(None)

        assert "유효한 함수가 필요합니다" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_connection_pool_status_detailed_cases(self):
        """Test connection pool status with detailed scenarios."""
        if WebSocketContextHelper is None:
            pytest.skip("WebSocketContextHelper not implemented yet")

        # Arrange
        mock_app = Mock()
        helper = WebSocketContextHelper(mock_app)

        # Test case 1: No SQLAlchemy extension
        mock_app.extensions = {}
        status = helper.get_connection_pool_status()
        assert status['status'] == 'unavailable'
        assert 'reason' in status

        # Test case 2: SQLAlchemy extension but no engine
        mock_app.extensions = {'sqlalchemy': Mock()}
        del mock_app.extensions['sqlalchemy'].engine
        status = helper.get_connection_pool_status()
        assert status['status'] == 'unavailable'
        assert 'reason' in status

        # Test case 3: Engine but no pool
        mock_engine = Mock()
        del mock_engine.pool
        mock_app.extensions['sqlalchemy'].engine = mock_engine
        status = helper.get_connection_pool_status()
        assert status['status'] == 'unavailable'
        assert 'reason' in status

        # Test case 4: Healthy pool with utilization
        mock_pool = Mock()
        mock_pool.size.return_value = 10
        mock_pool.checked_in.return_value = 7
        mock_pool.checked_out.return_value = 3
        mock_engine.pool = mock_pool
        status = helper.get_connection_pool_status()
        assert status['status'] == 'healthy'
        assert status['size'] == 10
        assert status['checked_in'] == 7
        assert status['checked_out'] == 3
        assert status['utilization'] == 0.3

    @pytest.mark.asyncio
    async def test_async_context_manager_with_exceptions(self):
        """Test async context manager behavior with exceptions."""
        if WebSocketContextHelper is None:
            pytest.skip("WebSocketContextHelper not implemented yet")

        # Arrange
        mock_app = Mock()
        test_exception = ValueError("Test exception")

        # Act & Assert
        with pytest.raises(ValueError, match="Test exception"):
            async with WebSocketContextHelper(mock_app) as helper:
                raise test_exception

    @pytest.mark.asyncio
    async def test_message_context_error_handling(self):
        """Test message_context error handling."""
        if WebSocketContextHelper is None:
            pytest.skip("WebSocketContextHelper not implemented yet")

        # Arrange
        mock_app = Mock()
        helper = WebSocketContextHelper(mock_app)
        mock_app.app_context = Mock(side_effect=RuntimeError("Context error"))

        # Act & Assert
        with pytest.raises(RuntimeError, match="Context error"):
            async with helper.message_context():
                pass

    def test_connection_health_validation_edge_cases(self):
        """Test connection health validation with edge cases."""
        if WebSocketContextHelper is None:
            pytest.skip("WebSocketContextHelper not implemented yet")

        # Arrange
        mock_app = Mock()
        helper = WebSocketContextHelper(mock_app)

        # Test case 1: Unhealthy status
        mock_app.extensions = {}
        assert helper.validate_connection_health() is False

        # Test case 2: 95% utilization - should be unhealthy
        mock_engine = Mock()
        mock_pool = Mock()
        mock_pool.size.return_value = 20
        mock_pool.checked_in.return_value = 1
        mock_pool.checked_out.return_value = 19  # 95% utilization
        mock_engine.pool = mock_pool
        mock_app.extensions = {'sqlalchemy': Mock()}
        mock_app.extensions['sqlalchemy'].engine = mock_engine

        with patch.object(helper, '_logger') as mock_logger:
            assert helper.validate_connection_health() is False
            mock_logger.warning.assert_called_once()

        # Test case 3: 50% utilization - should be healthy
        mock_pool.checked_out.return_value = 10  # 50% utilization
        assert helper.validate_connection_health() is True

    @pytest.mark.asyncio
    async def test_safe_execute_with_retry_validation(self):
        """Test safe_execute_with_retry with input validation."""
        if WebSocketContextHelper is None:
            pytest.skip("WebSocketContextHelper not implemented yet")

        # Arrange
        mock_app = Mock()
        helper = WebSocketContextHelper(mock_app)

        # Act & Assert - invalid function
        with pytest.raises(Exception) as exc_info:
            await helper.safe_execute_with_retry(None)

        assert "유효한 함수가 필요합니다" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_safe_execute_with_retry_actual_retry_logic(self):
        """Test safe_execute_with_retry actual retry mechanism."""
        if WebSocketContextHelper is None:
            pytest.skip("WebSocketContextHelper not implemented yet")

        # Arrange
        mock_app = Mock()
        helper = WebSocketContextHelper(mock_app)
        call_count = 0

        async def failing_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:  # Fail first 2 attempts
                raise ConnectionError("Connection failed")
            return "success"

        # Mock app_context and connection health validation
        mock_app_context_manager = Mock()
        mock_app_context_manager.__enter__ = Mock(return_value=None)
        mock_app_context_manager.__exit__ = Mock(return_value=None)
        mock_app.app_context = Mock(return_value=mock_app_context_manager)

        # Mock validate_connection_health to always return True
        with patch.object(helper, 'validate_connection_health', return_value=True):
            with patch.object(helper, '_logger') as mock_logger:

                # Act
                result = await helper.safe_execute_with_retry(
                    failing_function, max_retries=3, retry_delay=0.01
                )

        # Assert
        assert result == "success"
        assert call_count == 3
        # Verify warning logs for failed attempts
        warning_calls = [call for call in mock_logger.warning.call_args_list
                        if "실행 실패" in str(call)]
        assert len(warning_calls) == 2  # 2 failures, then success

    @pytest.mark.asyncio
    async def test_safe_execute_with_retry_exhaustion(self):
        """Test safe_execute_with_retry when all retries are exhausted."""
        if WebSocketContextHelper is None:
            pytest.skip("WebSocketContextHelper not implemented yet")

        # Arrange
        mock_app = Mock()
        helper = WebSocketContextHelper(mock_app)

        async def always_failing_function():
            raise RuntimeError("Always fails")

        # Mock app_context and connection health validation
        mock_app_context_manager = Mock()
        mock_app_context_manager.__enter__ = Mock(return_value=None)
        mock_app_context_manager.__exit__ = Mock(return_value=None)
        mock_app.app_context = Mock(return_value=mock_app_context_manager)

        with patch.object(helper, 'validate_connection_health', return_value=True):
            with patch.object(helper, '_logger') as mock_logger:

                # Act & Assert
                with pytest.raises(Exception) as exc_info:
                    await helper.safe_execute_with_retry(
                        always_failing_function, max_retries=2, retry_delay=0.01
                    )

                # Assert
                assert "재시도 실패" in str(exc_info.value)
                assert "Always fails" in str(exc_info.value)

                # Verify error log for final failure
                error_calls = [call for call in mock_logger.error.call_args_list
                             if "실행 실패" in str(call)]
                assert len(error_calls) == 1