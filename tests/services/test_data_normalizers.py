"""
데이터 정규화기 테스트

거래소별 데이터 정규화 전략 테스트

@FEAT:websocket-integration @COMP:data-normalizer @TYPE:test
"""

import pytest
import time
from app.services.websocket.data_normalizers import (
    BinanceDataNormalizer, BybitDataNormalizer, DataNormalizerFactory
)
from app.services.websocket.models import PriceQuote


class TestBinanceDataNormalizer:
    """BinanceDataNormalizer 테스트"""

    def setup_method(self):
        """각 테스트 전 설정"""
        self.normalizer = BinanceDataNormalizer()

    def test_normalize_valid_ticker_data(self):
        """유효한 Binance ticker 데이터 정규화 테스트"""
        # Arrange
        binance_data = {
            "e": "24hrTicker",
            "E": 1234567890000,
            "s": "BTCUSDT",
            "c": "50000.00",
            "v": "1000.50",
            "P": "2.5"
        }

        # Act
        result = self.normalizer.normalize(binance_data)

        # Assert
        assert isinstance(result, PriceQuote)
        assert result.exchange == "binance"
        assert result.symbol == "BTCUSDT"
        assert result.price == 50000.00
        assert result.volume == 1000.50
        assert result.change_24h == 2.5
        assert result.timestamp == 1234567890000

    def test_normalize_missing_fields(self):
        """누락된 필드가 있는 Binance 데이터 정규화 테스트"""
        # Arrange
        binance_data = {
            "e": "24hrTicker",
            "E": 1234567890000,
            "s": "BTCUSDT",
            "c": "50000.00"
            # v, P 필드 누락
        }

        # Act
        result = self.normalizer.normalize(binance_data)

        # Assert
        assert isinstance(result, PriceQuote)
        assert result.price == 50000.00
        assert result.volume == 0.0  # 기본값
        assert result.change_24h == 0.0  # 기본값

    def test_normalize_invalid_event_type(self):
        """잘못된 이벤트 타입 데이터 정규화 테스트"""
        # Arrange
        invalid_data = {
            "e": "depthUpdate",  # 잘못된 이벤트 타입
            "E": 1234567890000,
            "s": "BTCUSDT",
            "c": "50000.00"
        }

        # Act
        result = self.normalizer.normalize(invalid_data)

        # Assert
        assert result is None

    def test_normalize_malformed_data(self):
        """형식이 잘못된 Binance 데이터 정규화 테스트"""
        # Arrange
        malformed_data = {
            "e": "24hrTicker",
            "E": 1234567890000,
            "s": "BTCUSDT",
            "c": "invalid_price"  # 잘못된 가격 형식
        }

        # Act
        result = self.normalizer.normalize(malformed_data)

        # Assert
        assert result is None


class TestBybitDataNormalizer:
    """BybitDataNormalizer 테스트"""

    def setup_method(self):
        """각 테스트 전 설정"""
        self.normalizer = BybitDataNormalizer()

    def test_normalize_valid_ticker_data(self):
        """유효한 Bybit ticker 데이터 정규화 테스트"""
        # Arrange
        bybit_data = {
            "topic": "tickers",
            "data": [{
                "symbol": "BTCUSDT",
                "lastPrice": "50000.00",
                "volume24h": "1000.50",
                "turnover24h": "50000000"
            }]
        }

        # Act
        result = self.normalizer.normalize(bybit_data)

        # Assert
        assert isinstance(result, PriceQuote)
        assert result.exchange == "bybit"
        assert result.symbol == "BTCUSDT"
        assert result.price == 50000.00
        assert result.volume == 1000.50
        assert result.change_24h == 50000000.0
        # 타임스탬프는 현재 시간으로 설정됨
        assert abs(time.time() * 1000 - result.timestamp) < 1000  # 1초 이내 차이

    def test_normalize_multiple_tickers(self):
        """여러 ticker가 있는 Bybit 데이터 정규화 테스트"""
        # Arrange
        bybit_data = {
            "topic": "tickers",
            "data": [
                {
                    "symbol": "BTCUSDT",
                    "lastPrice": "50000.00",
                    "volume24h": "1000.50"
                },
                {
                    "symbol": "ETHUSDT",
                    "lastPrice": "3000.00",
                    "volume24h": "2000.00"
                }
            ]
        }

        # Act
        result = self.normalizer.normalize(bybit_data)

        # Assert - 첫 번째 ticker만 정규화
        assert isinstance(result, PriceQuote)
        assert result.symbol == "BTCUSDT"
        assert result.price == 50000.00

    def test_normalize_missing_data_field(self):
        """data 필드가 없는 Bybit 데이터 정규화 테스트"""
        # Arrange
        invalid_data = {
            "topic": "tickers"
            # data 필드 누락
        }

        # Act
        result = self.normalizer.normalize(invalid_data)

        # Assert
        assert result is None

    def test_normalize_empty_data_field(self):
        """data 필드가 비어있는 Bybit 데이터 정규화 테스트"""
        # Arrange
        invalid_data = {
            "topic": "tickers",
            "data": []
        }

        # Act
        result = self.normalizer.normalize(invalid_data)

        # Assert
        assert result is None

    def test_normalize_invalid_topic(self):
        """잘못된 topic이 있는 Bybit 데이터 정규화 테스트"""
        # Arrange
        invalid_data = {
            "topic": "orderbook",
            "data": [{
                "symbol": "BTCUSDT",
                "lastPrice": "50000.00"
            }]
        }

        # Act
        result = self.normalizer.normalize(invalid_data)

        # Assert
        assert result is None

    def test_normalize_malformed_price(self):
        """가격 형식이 잘못된 Bybit 데이터 정규화 테스트"""
        # Arrange
        malformed_data = {
            "topic": "tickers",
            "data": [{
                "symbol": "BTCUSDT",
                "lastPrice": "invalid_price",
                "volume24h": "1000.50"
            }]
        }

        # Act
        result = self.normalizer.normalize(malformed_data)

        # Assert
        assert result is None


class TestDataNormalizerFactory:
    """DataNormalizerFactory 테스트"""

    def test_get_binance_normalizer(self):
        """Binance 정규화기 조회 테스트"""
        # Act
        normalizer = DataNormalizerFactory.get_normalizer("binance")

        # Assert
        assert isinstance(normalizer, BinanceDataNormalizer)

    def test_get_bybit_normalizer(self):
        """Bybit 정규화기 조회 테스트"""
        # Act
        normalizer = DataNormalizerFactory.get_normalizer("bybit")

        # Assert
        assert isinstance(normalizer, BybitDataNormalizer)

    def test_get_unsupported_exchange_normalizer(self):
        """지원하지 않는 거래소 정규화기 조회 테스트"""
        # Act
        normalizer = DataNormalizerFactory.get_normalizer("unsupported")

        # Assert
        assert normalizer is None

    def test_case_insensitive_exchange_name(self):
        """대소문자 구분 없는 거래소 이름 테스트"""
        # Act & Assert
        assert DataNormalizerFactory.get_normalizer("BINANCE") is not None
        assert DataNormalizerFactory.get_normalizer("Bybit") is not None
        assert DataNormalizerFactory.get_normalizer("BINANCE") == DataNormalizerFactory.get_normalizer("binance")

    def test_get_supported_exchanges(self):
        """지원하는 거래소 목록 조회 테스트"""
        # Act
        exchanges = DataNormalizerFactory.get_supported_exchanges()

        # Assert
        assert isinstance(exchanges, list)
        assert "binance" in exchanges
        assert "bybit" in exchanges

    def test_register_custom_normalizer(self):
        """사용자 정의 정규화기 등록 테스트"""
        # Arrange
        from app.services.websocket.data_normalizers import DataNormalizer
        from app.services.websocket.models import PriceQuote

        class CustomNormalizer(DataNormalizer):
            def normalize(self, data):
                return PriceQuote(
                    exchange="custom",
                    symbol=data.get("symbol"),
                    price=float(data.get("price", 0)),
                    timestamp=int(time.time() * 1000)
                )

        # Act
        DataNormalizerFactory.register_normalizer("custom", CustomNormalizer())
        normalizer = DataNormalizerFactory.get_normalizer("custom")

        # Assert
        assert normalizer is not None
        assert isinstance(normalizer, CustomNormalizer)

        # 테스트 데이터 정규화
        test_data = {"symbol": "TEST", "price": "1000.00"}
        result = normalizer.normalize(test_data)
        assert result.exchange == "custom"
        assert result.symbol == "TEST"
        assert result.price == 1000.00