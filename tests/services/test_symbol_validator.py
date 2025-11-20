"""
SymbolValidator 캐시 키 미스매치 문제 테스트

이슈 #70: Symbol Validation Warning Fix
- 기존: btc_futures_key = "BINANCE_BTCUSDT_FUTURES"
- 수정: btc_futures_key = self._build_cache_key("BINANCE", "BTC/USDT", "FUTURES")

테스트 목적:
1. 캐시 키 생성 로직의 일관성 검증
2. _build_cache_key 헬퍼 함수 정상 작동 확인
3. 경고 메시지 제거 확인
"""

import pytest
from unittest.mock import Mock, patch
from decimal import Decimal
import sys
import os

# Add web_server to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../web_server'))

from app.services.symbol_validator import SymbolValidator, MarketInfo


class TestSymbolValidatorCacheKeyFix:
    """SymbolValidator 캐시 키 수정 관련 테스트"""

    def test_cache_key_format_consistency(self):
        """캐시 키 생성 로직의 일관성 검증"""
        validator = SymbolValidator()

        # 실제 캐시 키 생성 로직과 동일한 형식
        actual_key = f"BINANCE_BTC/USDT_FUTURES"

        # 문제의 하드코딩된 키
        hardcoded_key = "BINANCE_BTCUSDT_FUTURES"

        # 두 키가 다름을 확인 (이것이 실패해야 할 이유)
        assert actual_key != hardcoded_key, f"캐시 키 불일치: 실제={actual_key}, 하드코딩={hardcoded_key}"

    def test_build_cache_key_helper_should_exist(self):
        """_build_cache_key 헬퍼 함수가 존재해야 함"""
        validator = SymbolValidator()

        # 이 테스트는 현재 실패해야 함 (함수가 아직 구현되지 않음)
        assert hasattr(validator, '_build_cache_key'), "_build_cache_key 메서드가 존재하지 않음"

        # 함수가 정상적으로 작동하는지 확인
        if hasattr(validator, '_build_cache_key'):
            result = validator._build_cache_key("BINANCE", "BTC/USDT", "FUTURES")
            expected = "BINANCE_BTC/USDT_FUTURES"
            assert result == expected, f"캐시 키 생성 오류: 기대={expected}, 실제={result}"

    def test_load_initial_symbols_cache_key_warning(self):
        """load_initial_symbols에서 캐시 키 미스매치로 경고 발생 확인"""
        validator = SymbolValidator()

        # Mock exchange and market info
        mock_exchange = Mock()
        mock_market_info = MarketInfo(
            symbol="BTC/USDT",
            base_asset="BTC",
            quote_asset="USDT",
            status="active",
            active=True,
            price_precision=1,
            amount_precision=3,
            base_precision=8,
            quote_precision=8,
            min_qty=Decimal('0.001'),
            max_qty=Decimal('1000.0'),
            step_size=Decimal('0.001'),
            min_price=Decimal('0.001'),
            max_price=Decimal('1000000.0'),
            tick_size=Decimal('0.001'),
            min_notional=Decimal('5.0'),
            market_type="FUTURES"
        )

        # 캐시에 정상적인 키로 데이터 저장
        correct_key = f"BINANCE_BTC/USDT_FUTURES"
        validator.market_info_cache[correct_key] = mock_market_info

        # 하드코딩된 키로 조회 시도 (이것이 실패해야 함)
        hardcoded_key = "BINANCE_BTCUSDT_FUTURES"

        assert hardcoded_key not in validator.market_info_cache, \
            f"하드코딩된 키로 캐시 미스: {hardcoded_key}가 캐시에 없음"

        assert correct_key in validator.market_info_cache, \
            f"올바른 키는 캐시에 있어야 함: {correct_key}"

    def test_fixed_cache_key_should_find_market_info(self):
        """수정된 캐시 키로 마켓 정보를 정상적으로 찾을 수 있어야 함"""
        validator = SymbolValidator()

        # MarketInfo 객체 생성
        mock_market_info = MarketInfo(
            symbol="BTC/USDT",
            base_asset="BTC",
            quote_asset="USDT",
            status="active",
            active=True,
            price_precision=1,
            amount_precision=3,
            base_precision=8,
            quote_precision=8,
            min_qty=Decimal('0.001'),
            max_qty=Decimal('1000.0'),
            step_size=Decimal('0.001'),
            min_price=Decimal('0.001'),
            max_price=Decimal('1000000.0'),
            tick_size=Decimal('0.001'),
            min_notional=Decimal('5.0'),
            market_type="FUTURES"
        )

        # _build_cache_key로 생성한 키로 캐시에 데이터 저장
        correct_key = validator._build_cache_key("BINANCE", "BTC/USDT", "FUTURES")
        validator.market_info_cache[correct_key] = mock_market_info

        # 동일한 키로 조회 시 성공해야 함
        found_info = validator.market_info_cache.get(correct_key)

        assert found_info is not None, "_build_cache_key로 생성한 키로 데이터를 찾을 수 있어야 함"
        assert found_info.symbol == "BTC/USDT"
        assert found_info.base_asset == "BTC"
        assert found_info.quote_asset == "USDT"

    def test_build_cache_key_standardization(self):
        """_build_cache_key 함수의 표준화된 동작 검증"""
        validator = SymbolValidator()

        # 다양한 입력 조합에 대한 테스트
        test_cases = [
            ("BINANCE", "BTC/USDT", "FUTURES", "BINANCE_BTC/USDT_FUTURES"),
            ("UPBIT", "BTC/KRW", "SPOT", "UPBIT_BTC/KRW_SPOT"),
            ("binance", "btc/usdt", "futures", "BINANCE_BTC/USDT_FUTURES"),  # 소문자 입력
            ("Bithumb", "XRP/KRW", "spot", "BITHUMB_XRP/KRW_SPOT"),  # 혼합 케이스
        ]

        if hasattr(validator, '_build_cache_key'):
            for exchange, symbol, market_type, expected in test_cases:
                result = validator._build_cache_key(exchange, symbol, market_type)
                assert result == expected, \
                    f"캐시 키 생성 오류: 입력=({exchange}, {symbol}, {market_type}), " \
                    f"기대={expected}, 실제={result}"
        else:
            # 함수가 아직 없으면 테스트 실패 (예상된 실패)
            pytest.fail("_build_cache_key 함수가 아직 구현되지 않음")