"""
거래소별 데이터 정규화 전략 모듈

각 거래소의 데이터 형식을 표준 PriceQuote 형식으로 변환하는 전략 패턴 구현

@FEAT:websocket-integration @COMP:data-normalizer @TYPE:strategy-pattern
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import time

from .models import PriceQuote


class DataNormalizer(ABC):
    """데이터 정규화 추상 기본 클래스"""

    @abstractmethod
    def normalize(self, data: Dict[str, Any]) -> Optional[PriceQuote]:
        """
        거래소별 데이터를 PriceQuote 형식으로 정규화

        Args:
            data: 거래소별 원본 데이터

        Returns:
            Optional[PriceQuote]: 정규화된 가격 데이터
        """
        pass


class BinanceDataNormalizer(DataNormalizer):
    """Binance 데이터 정규화 전략"""

    def normalize(self, data: Dict[str, Any]) -> Optional[PriceQuote]:
        """Binance 24hrTicker 데이터 정규화"""
        try:
            if data.get('e') != '24hrTicker':
                return None

            return PriceQuote(
                exchange="binance",
                symbol=data.get('s'),
                price=float(data.get('c', 0)),
                timestamp=data.get('E', int(time.time() * 1000)),
                volume=float(data.get('v', 0)),
                change_24h=float(data.get('P', 0))
            )
        except (ValueError, TypeError, KeyError) as e:
            # 정규화 실패 시 None 반환
            return None


class BybitDataNormalizer(DataNormalizer):
    """Bybit 데이터 정규화 전략"""

    def normalize(self, data: Dict[str, Any]) -> Optional[PriceQuote]:
        """Bybit tickers 데이터 정규화"""
        try:
            if data.get('topic') != 'tickers':
                return None

            ticker_data = data.get('data', [])
            if not ticker_data:
                return None

            item = ticker_data[0] if isinstance(ticker_data, list) else ticker_data

            return PriceQuote(
                exchange="bybit",
                symbol=item.get('symbol'),
                price=float(item.get('lastPrice', 0)),
                timestamp=int(time.time() * 1000),  # Bybit는 타임스탬프가 없어 현재 시간 사용
                volume=float(item.get('volume24h', 0)),
                change_24h=float(item.get('turnover24h', 0))  # 24시간 변화율은 turnover24h로 대체
            )
        except (ValueError, TypeError, KeyError, IndexError) as e:
            # 정규화 실패 시 None 반환
            return None


class DataNormalizerFactory:
    """데이터 정규화 팩토리 클래스"""

    _normalizers = {
        'binance': BinanceDataNormalizer(),
        'bybit': BybitDataNormalizer(),
    }

    @classmethod
    def get_normalizer(cls, exchange: str) -> Optional[DataNormalizer]:
        """
        거래소별 데이터 정규화기 반환

        Args:
            exchange: 거래소 이름

        Returns:
            Optional[DataNormalizer]: 데이터 정규화기
        """
        return cls._normalizers.get(exchange.lower())

    @classmethod
    def register_normalizer(cls, exchange: str, normalizer: DataNormalizer) -> None:
        """
        새로운 데이터 정규화기 등록

        Args:
            exchange: 거래소 이름
            normalizer: 데이터 정규화기
        """
        cls._normalizers[exchange.lower()] = normalizer

    @classmethod
    def get_supported_exchanges(cls) -> list[str]:
        """
        지원하는 거래소 목록 반환

        Returns:
            list[str]: 지원하는 거래소 이름 목록
        """
        return list(cls._normalizers.keys())