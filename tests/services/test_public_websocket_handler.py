"""
PublicWebSocketHandler TDD 테스트

실시간 가격 데이터를 위한 Public WebSocket 핸들러 TDD 테스트

@FEAT:websocket-integration @COMP:public-websocket @TYPE:price-data
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from dataclasses import dataclass
from typing import Dict, Any, List, Optional

# 타겟 클래스 import
from app.services.websocket.public_websocket_handler import PublicWebSocketHandler
from app.services.websocket.models import PriceQuote


class TestPublicWebSocketHandler:
    """PublicWebSocketHandler TDD 테스트"""

    def setup_method(self):
        """각 테스트 전 설정"""
        self.mock_manager = Mock()
        self.mock_manager.app = Mock()

    def test_public_websocket_handler_initialization(self):
        """
        GREEN: PublicWebSocketHandler 초기화 테스트

        PublicWebSocketHandler가 올바르게 초기화되어야 함:
        - 거래소 이름 설정
        - 심볼 목록 초기화
        - 데이터 캐시 초기화
        - 연결 상태 초기화
        """
        # Arrange: 테스트를 위한 설정
        exchange = "binance"
        symbols = ["BTCUSDT", "ETHUSDT"]

        # Act: PublicWebSocketHandler 생성
        from app.services.websocket.public_websocket_handler import PublicWebSocketHandler
        handler = PublicWebSocketHandler(exchange=exchange, symbols=symbols)

        # Assert: 초기화 확인
        assert handler.exchange == exchange
        assert set(handler.symbols) == set(symbols)
        assert isinstance(handler.price_cache, dict)
        assert handler.is_connected == False
        assert handler.connection_state.value == "disconnected"
        assert len(handler.symbol_subscriptions) == 0

    @pytest.mark.asyncio
    async def test_binance_public_connection_creation(self):
        """
        GREEN: Binance Public WebSocket 연결 생성 테스트

        Binance Public WebSocket에 연결하여 실시간 가격 데이터 수신:
        - WebSocket 연결 생성
        - 심볼별 구독 요청
        - 데이터 파싱 및 정규화
        """
        # Arrange: 테스트 설정
        from app.services.websocket.public_websocket_handler import PublicWebSocketHandler

        # Mock websockets.connect
        with patch('websockets.connect', new_callable=AsyncMock) as mock_connect:
            mock_ws = AsyncMock()
            mock_connect.return_value = mock_ws
            mock_ws.__aiter__.return_value = iter([])  # 빈 메시지 루프

            # Act: Binance Public 연결 생성
            handler = PublicWebSocketHandler(exchange="binance", symbols=["BTCUSDT"])
            await handler.connect()

            # Assert: 연결 생성 확인
            assert handler.is_connected == True
            assert "BTCUSDT" in handler.subscriptions
            mock_connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_bybit_public_connection_creation(self):
        """
        GREEN: Bybit Public WebSocket 연결 생성 테스트

        Bybit Public WebSocket에 연결하여 실시간 가격 데이터 수신:
        - WebSocket 연결 생성
        - 심볼별 구독 요청
        - 데이터 파싱 및 정규화
        """
        # Arrange: 테스트 설정
        from app.services.websocket.public_websocket_handler import PublicWebSocketHandler

        # Mock websockets.connect
        with patch('websockets.connect', new_callable=AsyncMock) as mock_connect:
            mock_ws = AsyncMock()
            mock_connect.return_value = mock_ws
            mock_ws.__aiter__.return_value = iter([])  # 빈 메시지 루프

            # Act: Bybit Public 연결 생성
            handler = PublicWebSocketHandler(exchange="bybit", symbols=["BTCUSDT"])
            await handler.connect()

            # Assert: 연결 생성 확인
            assert handler.is_connected == True
            assert "BTCUSDT" in handler.subscriptions
            mock_connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_price_data_normalization(self):
        """
        GREEN: 가격 데이터 정규화 테스트

        거래소별 다른 형식의 가격 데이터를 표준 PriceQuote 형식으로 변환:
        - Binance ticker 데이터 정규화
        - Bybit ticker 데이터 정규화
        - 일관된 데이터 형식 보장
        """
        # Arrange: 테스트 설정
        from app.services.websocket.public_websocket_handler import PublicWebSocketHandler

        # Binance 형식 데이터
        binance_data = {
            "e": "24hrTicker",
            "E": 1234567890000,
            "s": "BTCUSDT",
            "c": "50000.00",
            "v": "1000.50"
        }

        # Bybit 형식 데이터
        bybit_data = {
            "topic": "tickers",
            "data": [{
                "symbol": "BTCUSDT",
                "lastPrice": "50000.00",
                "volume24h": "1000.50",
                "turnover24h": "50000000"
            }]
        }

        # Test Binance normalization
        binance_handler = PublicWebSocketHandler(exchange="binance", symbols=["BTCUSDT"])
        normalized = await binance_handler.normalize_price_data(binance_data)

        # Assert: Binance 정규화 결과 확인
        assert isinstance(normalized, PriceQuote)
        assert normalized.exchange == "binance"
        assert normalized.symbol == "BTCUSDT"
        assert normalized.price == 50000.00
        assert normalized.volume == 1000.50

        # Test Bybit normalization
        bybit_handler = PublicWebSocketHandler(exchange="bybit", symbols=["BTCUSDT"])
        normalized_bybit = await bybit_handler.normalize_price_data(bybit_data)

        # Assert: Bybit 정규화 결과 확인
        assert isinstance(normalized_bybit, PriceQuote)
        assert normalized_bybit.exchange == "bybit"
        assert normalized_bybit.symbol == "BTCUSDT"
        assert normalized_bybit.price == 50000.00
        assert normalized_bybit.volume == 1000.50

    @pytest.mark.asyncio
    async def test_price_caching_and_retrieval(self):
        """
        GREEN: 가격 데이터 캐싱 테스트

        수신된 가격 데이터를 캐시하고 빠르게 조회:
        - 최신 가격 데이터 캐싱
        - 심볼별 데이터 조회
        - 캐시 만료 시간 관리
        """
        # Arrange: 테스트 설정
        from app.services.websocket.public_websocket_handler import PublicWebSocketHandler

        handler = PublicWebSocketHandler(exchange="binance", symbols=["BTCUSDT"])
        test_quote = PriceQuote(
            exchange="binance",
            symbol="BTCUSDT",
            price=50000.0,
            timestamp=1234567890000,
            volume=1000.5
        )

        # Act: 가격 데이터 캐싱
        await handler.cache_price_data(test_quote)

        # Assert: 캐싱 확인
        cached_data = handler.get_latest_price("BTCUSDT")
        assert cached_data is not None
        assert cached_data.exchange == test_quote.exchange
        assert cached_data.symbol == test_quote.symbol
        assert cached_data.price == test_quote.price
        assert cached_data.volume == test_quote.volume

    @pytest.mark.asyncio
    async def test_subscription_management(self):
        """
        GREEN: 구독 관리 테스트

        심볼 구독 추가 및 해지 관리:
        - 새로운 심볼 구독
        - 기존 심볼 구독 해지
        - 구독 상태 추적
        """
        # Arrange: 테스트 설정
        from app.services.websocket.public_websocket_handler import PublicWebSocketHandler

        handler = PublicWebSocketHandler(exchange="binance", symbols=["BTCUSDT"])

        # Mock websockets.connect for subscription operations
        with patch('websockets.connect', new_callable=AsyncMock) as mock_connect:
            mock_ws = AsyncMock()
            mock_connect.return_value = mock_ws
            mock_ws.__aiter__.return_value = iter([])  # 빈 메시지 루프

            # Connect first
            await handler.connect()
            mock_ws.reset_mock()

            # Act: 구독 관리
            await handler.add_subscription("ETHUSDT")
            await handler.remove_subscription("BTCUSDT")

            # Assert: 구독 상태 확인
            assert "ETHUSDT" in handler.symbols
            assert "BTCUSDT" not in handler.symbols

    @pytest.mark.asyncio
    async def test_error_handling_and_reconnection(self):
        """
        GREEN: 에러 처리 및 재연결 테스트

        WebSocket 연결 실패 및 복구 처리:
        - 연결 실패 시 재시도 로직
        - 네트워크 오류 처리
        - 일시적 연결 끊김 복구
        """
        # Arrange: 테스트 설정
        from app.services.websocket.public_websocket_handler import PublicWebSocketHandler

        handler = PublicWebSocketHandler(exchange="binance", symbols=["BTCUSDT"])

        # Mock 연결 실패
        with patch('websockets.connect', side_effect=Exception("Connection failed")):
            # Act: 연결 시도
            with pytest.raises(Exception, match="Connection failed"):
                await handler.connect()

            # Assert: 에러 상태 확인
            assert handler.is_connected == False
            assert handler.connection_state.value == "error"

    @pytest.mark.asyncio
    async def test_performance_and_memory_efficiency(self):
        """
        GREEN: 성능 및 메모리 효율성 테스트

        실시간 데이터 처리의 성능 및 메모리 효율성 검증:
        - 대량 가격 데이터 처리
        - 메모리 사용량 제어
        - 지연 시간 측정
        """
        # Arrange: 테스트 설정
        from app.services.websocket.public_websocket_handler import PublicWebSocketHandler

        handler = PublicWebSocketHandler(exchange="binance", symbols=["BTCUSDT"])

        # 대량 가격 데이터 생성
        test_quotes = []
        for i in range(1000):
            quote = PriceQuote(
                exchange="binance",
                symbol="BTCUSDT",
                price=50000.0 + i,
                timestamp=1234567890000 + i
            )
            test_quotes.append(quote)

        # Act: 대량 데이터 처리 (성능 측정)
        import time
        start_time = time.time()

        for quote in test_quotes:
            await handler.cache_price_data(quote)

        end_time = time.time()
        processing_time = end_time - start_time

        # Assert: 성능 기준 확인
        assert processing_time < 1.0  # 1초 이내 처리
        assert len(handler.price_cache) <= 100  # 캐시 크기 제한

    @pytest.mark.asyncio
    async def test_multi_exchange_support(self):
        """
        GREEN: 다중 거래소 지원 테스트

        여러 거래소 동시 지원 기능 검증:
        - Binance와 Bybit 동시 구독
        - 데이터 소스 구분
        - 연결 관리 분리
        """
        # Arrange: 테스트 설정
        from app.services.websocket.public_websocket_handler import PublicWebSocketHandler

        # Act: 다중 거래소 핸들러 생성
        binance_handler = PublicWebSocketHandler(exchange="binance", symbols=["BTCUSDT"])
        bybit_handler = PublicWebSocketHandler(exchange="bybit", symbols=["BTCUSDT"])

        # Assert: 핸들러 분리 확인
        assert binance_handler.exchange == "binance"
        assert bybit_handler.exchange == "bybit"
        assert binance_handler != bybit_handler

    def test_unified_websocket_manager_integration(self):
        """
        GREEN: UnifiedWebSocketManager 통합 테스트

        UnifiedWebSocketManager와의 연동 검증:
        - 핸들러 등록 기능
        - 연결 생성 위임
        - 상태 동기화
        """
        # Arrange: 테스트 설정
        from app.services.websocket.public_websocket_handler import PublicWebSocketHandler
        from app.services.unified_websocket_manager import UnifiedWebSocketManager

        # Mock Flask 앱
        mock_app = Mock()
        manager = UnifiedWebSocketManager(mock_app)

        # Act: 핸들러 등록
        handler = PublicWebSocketHandler(exchange="binance", symbols=["BTCUSDT"])
        manager.register_exchange_handler("binance", handler)  # 핸들러로 등록

        # Assert: 등록 확인
        assert "binance" in manager.exchange_handlers
        assert manager.exchange_handlers["binance"] == handler