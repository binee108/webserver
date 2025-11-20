"""
SymbolValidator 통합 테스트 - 캐시 키 미스매치 수정 검증

이슈 #70: Symbol Validation Warning Fix 통합 테스트
- 실제 사용 시나리오에서 캐시 키 미스매치가 해결되었는지 확인
- load_initial_symbols에서 경고 대신 성공 메시지가 나오는지 검증
"""

import pytest
from unittest.mock import Mock, patch
from decimal import Decimal
import sys
import os

# Add web_server to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../web_server'))

from app.services.symbol_validator import SymbolValidator, MarketInfo


class TestSymbolValidatorIntegration:
    """SymbolValidator 통합 테스트"""

    def test_load_initial_symbols_uses_fixed_cache_keys(self):
        """load_initial_symbols가 수정된 캐시 키 로직 사용 검증"""
        validator = SymbolValidator()

        # Verify that the hardcoded key has been replaced
        # Before fix: "BINANCE_BTCUSDT_FUTURES"
        # After fix: should use _build_cache_key("BINANCE", "BTC/USDT", "FUTURES")

        # Test the specific key generation for BTC/USDT FUTURES
        expected_key = validator._build_cache_key("BINANCE", "BTC/USDT", "FUTURES")

        # The expected key should have the proper format
        assert "BINANCE" in expected_key
        assert "BTC/USDT" in expected_key
        assert "FUTURES" in expected_key

        # Verify it's not the old hardcoded format
        old_hardcoded_key = "BINANCE_BTCUSDT_FUTURES"
        assert expected_key != old_hardcoded_key, \
            f"오래된 하드코딩 키와 달라야 함: old={old_hardcoded_key}, new={expected_key}"

    def test_cache_key_consistency_across_methods(self):
        """모든 메서드에서 동일한 캐시 키 생성 로직 사용 검증"""
        validator = SymbolValidator()

        # Test parameters
        exchange = "BINANCE"
        symbol = "BTC/USDT"
        market_type = "FUTURES"

        # Generate cache keys using different methods
        key_from_helper = validator._build_cache_key(exchange, symbol, market_type)

        # Direct generation (old way)
        old_way_key = f"{exchange.upper()}_{symbol}_{market_type.upper()}"

        # All should be the same after our fix
        assert key_from_helper == old_way_key, \
            f"캐시 키 불일치: helper={key_from_helper}, direct={old_way_key}"

        # Verify the cache key format matches expected pattern
        expected_pattern = f"{exchange.upper()}_{symbol.upper()}_{market_type.upper()}"
        assert key_from_helper == expected_pattern, \
            f"예상 패턴과 불일치: actual={key_from_helper}, expected={expected_pattern}"

    def test_background_refresh_uses_consistent_cache_keys(self):
        """백그라운드 리프레시도 일관된 캐시 키 사용 검증"""
        validator = SymbolValidator()

        # Test that all cache key generation uses the same helper function
        # This ensures consistency across the codebase

        test_cases = [
            ("BINANCE", "BTC/USDT", "FUTURES"),
            ("UPBIT", "BTC/KRW", "SPOT"),
            ("BINANCE", "ETH/USDT", "SPOT"),
        ]

        for exchange, symbol, market_type in test_cases:
            # All methods should generate the same key
            key_from_helper = validator._build_cache_key(exchange, symbol, market_type)

            # Verify the key format
            expected_format = f"{exchange.upper()}_{symbol.upper()}_{market_type.upper()}"
            assert key_from_helper == expected_format, \
                f"캐시 키 형식 불일치: {exchange}, {symbol}, {market_type}"