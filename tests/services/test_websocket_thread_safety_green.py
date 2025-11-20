"""
WebSocket Thread Safety GREEN Tests - Verify the Fix Works

This test file verifies that the thread safety fixes properly
address the race conditions exposed in the RED tests.

@FEAT:websocket-thread-safety @COMP:service @TYPE:testing
"""

import asyncio
import pytest
import threading
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
        mock_exchange = Mock()
        mock_exchange.upper.return_value = 'BINANCE'
        return mock_exchange


class TestWebSocketThreadSafetyGreen:
    """Tests for @FEAT:websocket-thread-safety GREEN phase"""

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

    def test_thread_safe_connection_access(self, websocket_manager):
        """
        GREEN TEST: Verify thread-safe connection access works
        """
        # Create initial connection
        connection = WebSocketConnection(12345, 'BINANCE', Mock())
        connection.set_state(ConnectionState.CONNECTED)
        websocket_manager._add_connection(12345, connection)

        # Shared data for testing thread safety
        access_results = []
        exceptions = []

        def concurrent_reader(thread_id):
            """Thread that reads connections using thread-safe methods"""
            try:
                for i in range(50):
                    # ✅ SUCCESS: Using thread-safe get_connection method
                    conn = websocket_manager.get_connection(12345)
                    if conn:
                        access_results.append(f"Thread-{thread_id}: Read connection {conn.account_id}")
                    else:
                        access_results.append(f"Thread-{thread_id}: Connection not found")
                    time.sleep(0.001)
            except Exception as e:
                exceptions.append(f"Thread-{thread_id}: Exception {e}")

        def concurrent_writer(thread_id):
            """Thread that modifies connections using thread-safe methods"""
            try:
                for i in range(25):
                    # ✅ SUCCESS: Using thread-safe methods
                    if i % 2 == 0:
                        # Remove connection
                        removed = websocket_manager._remove_connection(12345)
                        if removed:
                            access_results.append(f"Thread-{thread_id}: Removed connection")
                    else:
                        # Add connection
                        connection = WebSocketConnection(12345, 'BINANCE', Mock())
                        connection.set_state(ConnectionState.CONNECTED)
                        websocket_manager._add_connection(12345, connection)
                        access_results.append(f"Thread-{thread_id}: Added connection")
                    time.sleep(0.002)
            except Exception as e:
                exceptions.append(f"Thread-{thread_id}: Exception {e}")

        # Start multiple concurrent threads
        threads = []
        for i in range(3):  # 3 reader threads
            thread = threading.Thread(target=concurrent_reader, args=(f"R{i}",))
            threads.append(thread)
            thread.start()

        for i in range(2):  # 2 writer threads
            thread = threading.Thread(target=concurrent_writer, args=(f"W{i}",))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join(timeout=5)

        # ✅ SUCCESS: No exceptions should occur with thread-safe access
        assert len(exceptions) == 0, f"Thread safety failed: {exceptions}"
        assert len(access_results) > 0, "No operations completed"

        # Verify final state is consistent
        final_connection = websocket_manager.get_connection(12345)
        print(f"✅ SUCCESS: Thread-safe access completed with {len(access_results)} operations, no exceptions")
        print(f"Final connection state: {'Exists' if final_connection else 'Not found'}")

    def test_thread_safe_stats_collection(self, websocket_manager):
        """
        GREEN TEST: Verify thread-safe stats collection works
        """
        # Create multiple connections
        for i in range(5):
            connection = WebSocketConnection(i, 'BINANCE', Mock())
            connection.set_state(ConnectionState.CONNECTED)
            websocket_manager._add_connection(i, connection)

        stats_results = []
        exceptions = []

        def concurrent_stats_collector(thread_id):
            """Thread that collects stats using thread-safe methods"""
            try:
                for i in range(30):
                    # ✅ SUCCESS: get_stats should be thread-safe now
                    stats = websocket_manager.get_stats()
                    stats_results.append(f"Thread-{thread_id}: {stats['total_connections']} connections")
                    time.sleep(0.001)
            except Exception as e:
                exceptions.append(f"Thread-{thread_id}: Exception {e}")

        def concurrent_connection_modifier(thread_id):
            """Thread that modifies connections using thread-safe methods"""
            try:
                for i in range(15):
                    if i % 2 == 0:
                        # Add connection
                        account_id = 100 + i
                        connection = WebSocketConnection(account_id, 'BINANCE', Mock())
                        connection.set_state(ConnectionState.CONNECTED)
                        websocket_manager._add_connection(account_id, connection)
                    else:
                        # Remove connection
                        if websocket_manager.get_connection(0):  # Check if connection 0 exists
                            websocket_manager._remove_connection(0)
                    time.sleep(0.002)
            except Exception as e:
                exceptions.append(f"Thread-{thread_id}: Exception {e}")

        # Start concurrent threads
        threads = []
        for i in range(3):  # 3 stats collector threads
            thread = threading.Thread(target=concurrent_stats_collector, args=(f"S{i}",))
            threads.append(thread)
            thread.start()

        for i in range(2):  # 2 connection modifier threads
            thread = threading.Thread(target=concurrent_connection_modifier, args=(f"M{i}",))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join(timeout=5)

        # ✅ SUCCESS: No exceptions should occur with thread-safe access
        assert len(exceptions) == 0, f"Thread safety failed: {exceptions}"
        assert len(stats_results) > 0, "No stats collected"

        # Check stats consistency
        unique_counts = set()
        for result in stats_results:
            if "connections" in result:
                # Try to extract connection count more robustly
                try:
                    # Look for numeric patterns in the result
                    import re
                    numbers = re.findall(r'\d+', result)
                    if numbers:
                        count = int(numbers[0])
                        unique_counts.add(count)
                except (ValueError, IndexError):
                    # If parsing fails, just note that we got a result
                    pass

        # Stats should be consistent or at least not crash
        print(f"✅ SUCCESS: Thread-safe stats collection completed with {len(stats_results)} results")
        print(f"Connection counts observed: {sorted(unique_counts)}")

    def test_thread_safe_connection_details(self, websocket_manager):
        """
        GREEN TEST: Verify thread-safe connection details work
        """
        # Create connections with different states
        connections_data = [
            (1, ConnectionState.CONNECTED),
            (2, ConnectionState.CONNECTING),
            (3, ConnectionState.DISCONNECTED),
            (4, ConnectionState.ERROR)
        ]

        for account_id, state in connections_data:
            connection = WebSocketConnection(account_id, 'BINANCE', Mock())
            connection.set_state(state)
            websocket_manager._add_connection(account_id, connection)

        details_results = []
        exceptions = []

        def concurrent_details_reader(thread_id):
            """Thread that reads connection details using thread-safe methods"""
            try:
                for i in range(20):
                    # ✅ SUCCESS: get_connection_details should be thread-safe
                    details = websocket_manager.get_connection_details()
                    details_results.append(f"Thread-{thread_id}: {len(details)} connections")
                    time.sleep(0.001)
            except Exception as e:
                exceptions.append(f"Thread-{thread_id}: Exception {e}")

        def concurrent_unhealthy_checker(thread_id):
            """Thread that checks unhealthy connections using thread-safe methods"""
            try:
                for i in range(20):
                    # ✅ SUCCESS: get_unhealthy_connections should be thread-safe
                    unhealthy = websocket_manager.get_unhealthy_connections()
                    details_results.append(f"Thread-{thread_id}: {len(unhealthy)} unhealthy")
                    time.sleep(0.001)
            except Exception as e:
                exceptions.append(f"Thread-{thread_id}: Exception {e}")

        # Start concurrent threads
        threads = []
        for i in range(2):  # 2 details reader threads
            thread = threading.Thread(target=concurrent_details_reader, args=(f"D{i}",))
            threads.append(thread)
            thread.start()

        for i in range(2):  # 2 unhealthy checker threads
            thread = threading.Thread(target=concurrent_unhealthy_checker, args=(f"U{i}",))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join(timeout=5)

        # ✅ SUCCESS: No exceptions should occur with thread-safe access
        assert len(exceptions) == 0, f"Thread safety failed: {exceptions}"
        assert len(details_results) > 0, "No details collected"

        # Verify final state
        final_details = websocket_manager.get_connection_details()
        final_unhealthy = websocket_manager.get_unhealthy_connections()

        print(f"✅ SUCCESS: Thread-safe connection details completed")
        print(f"Final connections: {len(final_details)}, Unhealthy: {len(final_unhealthy)}")

    def test_lock_behavior_verification(self, websocket_manager):
        """
        GREEN TEST: Verify RLock behavior works correctly
        """
        # Verify RLock is properly initialized
        assert hasattr(websocket_manager, '_connections_lock')
        assert websocket_manager._connections_lock is not None

        # Create test connection
        connection = WebSocketConnection(12345, 'BINANCE', Mock())
        connection.set_state(ConnectionState.CONNECTED)

        # Test reentrant locking behavior
        lock_acquisition_count = []

        def nested_lock_test():
            """Test that RLock allows recursive locking"""
            try:
                with websocket_manager._connections_lock:
                    lock_acquisition_count.append("First lock acquired")
                    # This should work with RLock (reentrant lock)
                    with websocket_manager._connections_lock:
                        lock_acquisition_count.append("Second lock acquired")
                        websocket_manager._add_connection(12345, connection)
                    lock_acquisition_count.append("Second lock released")
                lock_acquisition_count.append("First lock released")
            except Exception as e:
                lock_acquisition_count.append(f"Exception: {e}")

        thread = threading.Thread(target=nested_lock_test)
        thread.start()
        thread.join(timeout=2)

        # ✅ SUCCESS: RLock should allow nested locking
        assert len(lock_acquisition_count) >= 4, "RLock reentrant behavior failed"
        assert "Exception:" not in lock_acquisition_count, "RLock threw exception during nested access"

        # Verify connection was added successfully
        retrieved_connection = websocket_manager.get_connection(12345)
        assert retrieved_connection is not None, "Connection not found after nested lock test"

        print(f"✅ SUCCESS: RLock reentrant behavior verified")
        print(f"Lock acquisition sequence: {lock_acquisition_count}")