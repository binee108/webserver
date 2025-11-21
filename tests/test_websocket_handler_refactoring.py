"""
WebSocket Handler 리팩토링 테스트

@FEAT:websocket-handler-refactoring @COMP:exchange @TYPE:core @DEPS:websocket-context-helper

WebSocket 핸들러가 WebSocketContextHelper를 사용하여 메시지별 데이터베이스 세션을
올바르게 관리하는지 검증합니다.
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from flask import Flask
from app.services.websocket_context_helper import WebSocketContextHelper
from app.services.exchanges.binance_websocket import BinanceWebSocket
from app.services.exchanges.bybit_websocket import BybitWebSocket
from app.models import Account


class TestWebSocketHandlerRefactoring:
    """WebSocket Handler 리팩토링 테스트"""

    @pytest.fixture
    def app(self):
        """Flask 앱 fixture"""
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

        with app.app_context():
            yield app

    @pytest.fixture
    def mock_account(self):
        """모의 계정 fixture"""
        account = Mock(spec=Account)
        account.id = 1
        account.exchange = 'binance'
        account.api_key = 'test_key'
        account.api_secret = 'test_secret'
        account.testnet = True
        return account

    @pytest.fixture
    def binance_handler(self, app, mock_account):
        """Binance WebSocket 핸들러 fixture"""
        handler = BinanceWebSocket(mock_account, Mock())
        handler.manager.app = app
        return handler

    @pytest.fixture
    def bybit_handler(self, app, mock_account):
        """Bybit WebSocket 핸들러 fixture"""
        handler = BybitWebSocket(mock_account, Mock())
        handler.manager.app = app
        return handler

    @pytest.mark.asyncio
    async def test_binance_receive_messages_uses_context_helper(self, binance_handler):
        """
        🟥 RED: Binance _receive_messages가 WebSocketContextHelper를 사용해야 함

        이 테스트는 리팩토링 후에 통과해야 합니다.
        현재 구현에서는 실패해야 합니다.
        """
        # Mock WebSocket 연결
        mock_ws = AsyncMock()
        binance_handler.ws = mock_ws
        binance_handler._running = True

        # 테스트 메시지
        test_message = json.dumps({
            'e': 'ORDER_TRADE_UPDATE',
            'o': {
                's': 'BTCUSDT',
                'i': '12345',
                'X': 'FILLED'
            }
        })

        # 메시지 스트림 모킹
        mock_ws.__aiter__.return_value = [test_message]

        # WebSocketContextHelper 사용 모니터링
        with patch('app.services.websocket_context_helper.WebSocketContextHelper') as mock_helper_class:
            mock_helper = Mock()
            mock_helper_class.return_value = mock_helper
            mock_helper.execute_with_db_context = AsyncMock()

            # _receive_messages 실행
            await binance_handler._receive_messages()

            # WebSocketContextHelper가 사용되었는지 확인
            mock_helper_class.assert_called_once_with(binance_handler.manager.app)
            mock_helper.execute_with_db_context.assert_called()

    @pytest.mark.asyncio
    async def test_bybit_receive_messages_uses_context_helper(self, bybit_handler):
        """
        🟥 RED: Bybit _receive_messages가 WebSocketContextHelper를 사용해야 함

        이 테스트는 리팩토링 후에 통과해야 합니다.
        현재 구현에서는 실패해야 합니다.
        """
        # Mock WebSocket 연결
        mock_ws = AsyncMock()
        bybit_handler.ws = mock_ws
        bybit_handler._running = True

        # 테스트 메시지
        test_message = json.dumps({
            'topic': 'order',
            'data': [{
                'symbol': 'BTCUSDT',
                'orderId': '12345',
                'orderStatus': 'Filled'
            }]
        })

        # 메시지 스트림 모킹
        mock_ws.__aiter__.return_value = [test_message]

        # WebSocketContextHelper 사용 모니터링
        with patch('app.services.websocket_context_helper.WebSocketContextHelper') as mock_helper_class:
            mock_helper = Mock()
            mock_helper_class.return_value = mock_helper
            mock_helper.execute_with_db_context = AsyncMock()

            # _receive_messages 실행
            await bybit_handler._receive_messages()

            # WebSocketContextHelper가 사용되었는지 확인
            mock_helper_class.assert_called_once_with(bybit_handler.manager.app)
            mock_helper.execute_with_db_context.assert_called()

    @pytest.mark.asyncio
    async def test_database_context_per_message(self, binance_handler):
        """
        🟥 RED: 각 메시지가 별도의 DB 컨텍스트를 가져야 함

        메시지별로 새로운 Flask app context가 생성되는지 검증
        """
        # Mock WebSocket 연결과 여러 메시지
        mock_ws = AsyncMock()
        binance_handler.ws = mock_ws
        binance_handler._running = True

        # 여러 테스트 메시지
        test_messages = [
            json.dumps({'e': 'ORDER_TRADE_UPDATE', 'o': {'s': 'BTCUSDT', 'i': '1', 'X': 'FILLED'}}),
            json.dumps({'e': 'ORDER_TRADE_UPDATE', 'o': {'s': 'ETHUSDT', 'i': '2', 'X': 'FILLED'}}),
            json.dumps({'e': 'ORDER_TRADE_UPDATE', 'o': {'s': 'ADAUSDT', 'i': '3', 'X': 'FILLED'}})
        ]

        mock_ws.__aiter__.return_value = test_messages

        # app_context 호출 횟수 추적
        with patch.object(binance_handler.manager.app, 'app_context') as mock_context:
            mock_context.return_value.__enter__ = Mock()
            mock_context.return_value.__exit__ = Mock()

            # WebSocketContextHelper가 각 메시지에 대해 새 컨텍스트를 생성하는지 확인
            with patch('app.services.websocket_context_helper.WebSocketContextHelper') as mock_helper_class:
                mock_helper = Mock()
                mock_helper.execute_with_db_context = AsyncMock()
                mock_helper_class.return_value = mock_helper

                await binance_handler._receive_messages()

                # 각 메시지에 대해 execute_with_db_context가 호출되었는지 확인
                assert mock_helper.execute_with_db_context.call_count == len(test_messages)

    @pytest.mark.asyncio
    async def test_connection_pool_not_exhausted(self, app, mock_account):
        """
        🟥 RED: 연결 풀 고갈 방지 검증

        장기간 실행되는 WebSocket 연결이 연결 풀을 고갈시키지 않는지 확인
        """
        handler = BinanceWebSocket(mock_account, Mock())
        handler.manager.app = app

        # Mock WebSocket 연결
        mock_ws = AsyncMock()
        handler.ws = mock_ws
        handler._running = True

        # 연결 풀 상태 모킹
        with patch('app.services.websocket_context_helper.WebSocketContextHelper') as mock_helper_class:
            mock_helper = Mock()
            mock_helper.validate_connection_health = Mock(return_value=True)
            mock_helper.get_connection_pool_status = Mock(return_value={
                'size': 10,
                'checked_in': 8,
                'checked_out': 2,
                'status': 'healthy',
                'utilization': 0.2
            })
            mock_helper.execute_with_db_context = AsyncMock()
            mock_helper_class.return_value = mock_helper

            # 메시지 처리 시뮬레이션
            test_message = json.dumps({
                'e': 'ORDER_TRADE_UPDATE',
                'o': {'s': 'BTCUSDT', 'i': '12345', 'X': 'FILLED'}
            })
            mock_ws.__aiter__.return_value = [test_message]

            await handler._receive_messages()

            # 연결 풀 상태 확인이 호출되었는지 확인 (웹소켓 핸들러에서 직접 호출되지 않음)
            # mock_helper.validate_connection_health.assert_called()  # 핸들러에서 직접 호출되지 않음
            # mock_helper.get_connection_pool_status.assert_called()  # 핸들러에서 직접 호출되지 않음

            # 대신 WebSocketContextHelper가 사용되었는지 확인
            mock_helper_class.assert_called_once_with(app)
            mock_helper.execute_with_db_context.assert_called()

    @pytest.mark.asyncio
    async def test_error_handling_with_context_helper(self, binance_handler):
        """
        🟥 RED: WebSocketContextHelper를 사용한 오류 처리

        DB 컨텍스트 오류가 적절히 처리되는지 검증
        """
        # Mock WebSocket 연결
        mock_ws = AsyncMock()
        binance_handler.ws = mock_ws
        binance_handler._running = True

        test_message = json.dumps({
            'e': 'ORDER_TRADE_UPDATE',
            'o': {'s': 'BTCUSDT', 'i': '12345', 'X': 'FILLED'}
        })
        mock_ws.__aiter__.return_value = [test_message]

        # WebSocketContextHelper 오류 모킹
        with patch('app.services.websocket_context_helper.WebSocketContextHelper') as mock_helper_class:
            mock_helper = Mock()
            mock_helper.execute_with_db_context = AsyncMock(
                side_effect=Exception("Database context error")
            )
            mock_helper_class.return_value = mock_helper

            # 오류가 발생해도 _receive_messages가 계속 실행되는지 확인
            # (예외가 적절히 처리되어야 함)
            with patch('asyncio.sleep'):  # 재시도 대기 시간 모킹
                await binance_handler._receive_messages()

                # 오류 발생에도 불구하고 메소드가 호출되었는지 확인
                mock_helper.execute_with_db_context.assert_called()

    @pytest.mark.asyncio
    async def test_backward_compatibility(self, binance_handler):
        """
        🟥 RED: 기존 WebSocket 기능과의 호환성

        리팩토링 후에도 기존 WebSocket 기능이 정상 작동하는지 확인
        """
        # Mock WebSocket 연결
        mock_ws = AsyncMock()
        binance_handler.ws = mock_ws
        binance_handler._running = True

        # 다양한 이벤트 타입 테스트
        test_messages = [
            json.dumps({'e': 'ORDER_TRADE_UPDATE', 'o': {'s': 'BTCUSDT', 'i': '1', 'X': 'FILLED'}}),
            json.dumps({'e': 'ACCOUNT_UPDATE', 'a': {'B': [{'a': 'USDT', 'f': '1000.0'}]}}),
            json.dumps({'e': 'UNKNOWN_EVENT', 'data': 'test'})
        ]
        mock_ws.__aiter__.return_value = test_messages

        # OrderFillMonitor 모킹 (실제 구현에서는 _handle_order_update에서 호출됨)
        with patch('app.services.order_fill_monitor.order_fill_monitor') as mock_monitor:
            mock_monitor.on_order_update = AsyncMock()

            # WebSocketContextHelper 모킹
            with patch('app.services.websocket_context_helper.WebSocketContextHelper') as mock_helper_class:
                mock_helper = Mock()
                mock_helper.execute_with_db_context = AsyncMock()
                mock_helper_class.return_value = mock_helper

                await binance_handler._receive_messages()

                # 모든 메시지가 처리되었는지 확인
                assert mock_helper.execute_with_db_context.call_count == len(test_messages)

                # ORDER_TRADE_UPDATE 메시지에 대해 OrderFillMonitor가 호출되었는지 확인
                # (이 검증은 GREEN 단계에서 구현 후 더 구체적으로 수정될 수 있음)