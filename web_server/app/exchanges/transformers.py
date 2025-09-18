#!/usr/bin/env python3
"""
Data Transformation Pipeline

데이터 변환 및 정규화 파이프라인
- 심볼 형식 변환 (BTCUSDT ↔ BTC/USDT)
- 데이터 타입 변환 (Decimal ↔ float)
- 응답 포맷 정규화
- CCXT 호환성 보장
"""

import re
import logging
from typing import Dict, Any, Optional, List, Union, Callable
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from dataclasses import dataclass
from abc import ABC, abstractmethod
import json

logger = logging.getLogger(__name__)

@dataclass
class TransformationContext:
    """변환 컨텍스트"""
    source_exchange: str
    target_format: str  # 'ccxt', 'custom', 'internal'
    market_type: str = "spot"
    preserve_precision: bool = True
    validate_output: bool = True

class DataTransformer(ABC):
    """데이터 변환기 기본 클래스"""
    
    @abstractmethod
    def transform(self, data: Any, context: TransformationContext) -> Any:
        """데이터 변환"""
        pass
    
    @abstractmethod
    def can_handle(self, data_type: str, context: TransformationContext) -> bool:
        """변환 가능 여부 확인"""
        pass

class SymbolTransformer(DataTransformer):
    """심볼 형식 변환기"""
    
    # 거래소별 심볼 패턴
    EXCHANGE_PATTERNS = {
        'binance': {
            'spot': r'^([A-Z0-9]+)(USDT|BTC|ETH|BNB)$',
            'futures': r'^([A-Z0-9]+)(USDT)$'
        },
        'okx': {
            'spot': r'^([A-Z0-9]+)[-]([A-Z0-9]+)$',
            'futures': r'^([A-Z0-9]+)[-]([A-Z0-9]+)[-]([A-Z0-9]+)$'
        }
    }
    
    # CCXT 표준 패턴
    CCXT_PATTERN = r'^([A-Z0-9]+)[/]([A-Z0-9]+)(?:[:]([A-Z0-9]+))?$'
    
    def can_handle(self, data_type: str, context: TransformationContext) -> bool:
        return data_type in ['symbol', 'trading_pair']
    
    def transform(self, symbol: str, context: TransformationContext) -> str:
        """심볼 변환
        
        Args:
            symbol: 원본 심볼 (예: 'BTCUSDT', 'BTC/USDT', 'BTC-USDT')
            context: 변환 컨텍스트
        """
        if not isinstance(symbol, str):
            return symbol
        
        try:
            # 타겟 형식에 따른 변환
            if context.target_format == 'ccxt':
                return self._to_ccxt_format(symbol, context)
            elif context.target_format == 'custom':
                return self._to_exchange_format(symbol, context)
            else:
                return symbol
                
        except Exception as e:
            logger.warning(f"⚠️ 심볼 변환 실패 ({symbol}): {e}")
            return symbol
    
    def _to_ccxt_format(self, symbol: str, context: TransformationContext) -> str:
        """CCXT 표준 형식으로 변환 (BTC/USDT)"""
        # 이미 CCXT 형식이면 그대로 반환
        if '/' in symbol:
            return symbol
        
        # 거래소별 패턴으로 파싱
        exchange = context.source_exchange.lower()
        market_type = context.market_type.lower()
        
        if exchange in self.EXCHANGE_PATTERNS:
            pattern = self.EXCHANGE_PATTERNS[exchange].get(market_type)
            if pattern:
                match = re.match(pattern, symbol.upper())
                if match:
                    if market_type == 'futures' and len(match.groups()) >= 3:
                        # Futures: BTC-USD-SWAP -> BTC/USD:SWAP
                        return f"{match.group(1)}/{match.group(2)}:{match.group(3)}"
                    else:
                        # Spot: BTCUSDT -> BTC/USDT
                        return f"{match.group(1)}/{match.group(2)}"
        
        # 기본 변환 로직 (USDT 기준)
        if symbol.endswith('USDT') and len(symbol) > 4:
            base = symbol[:-4]
            return f"{base}/USDT"
        elif symbol.endswith('BTC') and len(symbol) > 3:
            base = symbol[:-3]
            return f"{base}/BTC"
        elif symbol.endswith('ETH') and len(symbol) > 3:
            base = symbol[:-3] 
            return f"{base}/ETH"
        
        return symbol
    
    def _to_exchange_format(self, symbol: str, context: TransformationContext) -> str:
        """거래소 네이티브 형식으로 변환"""
        exchange = context.source_exchange.lower()
        
        if exchange == 'binance':
            # CCXT -> Binance: BTC/USDT -> BTCUSDT
            if '/' in symbol:
                parts = symbol.split('/')
                if len(parts) >= 2:
                    base_quote = parts[1].split(':')[0]  # BTC/USDT:USDT -> USDT
                    return f"{parts[0]}{base_quote}"
            return symbol
        
        elif exchange == 'okx':
            # CCXT -> OKX: BTC/USDT -> BTC-USDT  
            if '/' in symbol:
                return symbol.replace('/', '-').replace(':', '-')
            return symbol
        
        return symbol
    
    def get_supported_formats(self, exchange: str) -> List[str]:
        """지원하는 심볼 형식 목록"""
        formats = ['ccxt_standard']  # BTC/USDT
        
        if exchange.lower() == 'binance':
            formats.extend(['binance_native'])  # BTCUSDT
        elif exchange.lower() == 'okx':
            formats.extend(['okx_native'])  # BTC-USDT
        
        return formats

class NumericTransformer(DataTransformer):
    """수치 데이터 변환기"""
    
    def can_handle(self, data_type: str, context: TransformationContext) -> bool:
        return data_type in ['price', 'quantity', 'volume', 'amount', 'balance', 'pnl']
    
    def transform(self, value: Any, context: TransformationContext) -> Union[float, Decimal, None]:
        """수치 변환
        
        Args:
            value: 원본 값 (str, int, float, Decimal, None)
            context: 변환 컨텍스트
        """
        if value is None or value == '':
            return None
        
        try:
            # 타겟 형식에 따른 변환
            if context.target_format == 'ccxt':
                # CCXT는 float 사용
                return float(value)
            elif context.target_format == 'custom':
                # 커스텀은 Decimal 사용 (정밀도 보존)
                if context.preserve_precision:
                    return Decimal(str(value))
                else:
                    return float(value)
            else:
                # 내부 형식은 Decimal 사용
                return Decimal(str(value))
                
        except (ValueError, InvalidOperation, TypeError) as e:
            logger.warning(f"⚠️ 수치 변환 실패 ({value}): {e}")
            return None
    
    def format_precision(self, value: Union[float, Decimal], precision: int) -> str:
        """정밀도에 맞춘 포맷팅"""
        if value is None:
            return "0"
        
        if isinstance(value, Decimal):
            # Decimal의 경우 정확한 포맷팅
            format_str = f"{{:.{precision}f}}"
            return format_str.format(float(value))
        else:
            # float의 경우 반올림
            format_str = f"{{:.{precision}f}}"
            return format_str.format(value)

class TimestampTransformer(DataTransformer):
    """타임스탬프 변환기"""
    
    def can_handle(self, data_type: str, context: TransformationContext) -> bool:
        return data_type in ['timestamp', 'datetime', 'time']
    
    def transform(self, timestamp: Any, context: TransformationContext) -> Any:
        """타임스탬프 변환"""
        if timestamp is None:
            return None
        
        try:
            if context.target_format == 'ccxt':
                # CCXT: 밀리초 타임스탬프 + ISO 문자열
                if isinstance(timestamp, datetime):
                    ms_timestamp = int(timestamp.timestamp() * 1000)
                    iso_string = timestamp.isoformat() + 'Z'
                    return {'timestamp': ms_timestamp, 'datetime': iso_string}
                elif isinstance(timestamp, (int, float)):
                    # 이미 타임스탬프인 경우
                    if timestamp > 1e12:  # 밀리초
                        dt = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
                    else:  # 초
                        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                    return {
                        'timestamp': int(timestamp if timestamp > 1e12 else timestamp * 1000),
                        'datetime': dt.isoformat().replace('+00:00', 'Z')
                    }
                elif isinstance(timestamp, str):
                    # ISO 문자열을 파싱
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    return {
                        'timestamp': int(dt.timestamp() * 1000),
                        'datetime': timestamp
                    }
                    
            elif context.target_format == 'custom':
                # 커스텀: datetime 객체
                if isinstance(timestamp, datetime):
                    return timestamp
                elif isinstance(timestamp, (int, float)):
                    if timestamp > 1e12:  # 밀리초
                        return datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
                    else:  # 초
                        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
                elif isinstance(timestamp, str):
                    return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            
            return timestamp
            
        except Exception as e:
            logger.warning(f"⚠️ 타임스탬프 변환 실패 ({timestamp}): {e}")
            return timestamp

class StatusTransformer(DataTransformer):
    """상태 값 변환기"""
    
    # 상태 매핑 테이블
    STATUS_MAPPINGS = {
        'order_status': {
            # Binance -> CCXT
            'NEW': 'open',
            'PARTIALLY_FILLED': 'open', 
            'FILLED': 'closed',
            'CANCELED': 'canceled',
            'PENDING_CANCEL': 'canceling',
            'REJECTED': 'rejected',
            'EXPIRED': 'expired',
            # CCXT -> Internal
            'open': 'PENDING',
            'closed': 'FILLED',
            'canceled': 'CANCELED'
        }
    }
    
    def can_handle(self, data_type: str, context: TransformationContext) -> bool:
        return data_type in ['order_status', 'position_status', 'account_status']
    
    def transform(self, status: str, context: TransformationContext) -> str:
        """상태 변환"""
        if not isinstance(status, str):
            return status
        
        data_type = context.target_format  # 간소화
        
        # 매핑 테이블에서 변환
        mapping_key = data_type if data_type in self.STATUS_MAPPINGS else 'order_status'
        mapping = self.STATUS_MAPPINGS.get(mapping_key, {})
        
        return mapping.get(status.upper(), status)

class ResponseTransformer(DataTransformer):
    """응답 구조 변환기"""
    
    def can_handle(self, data_type: str, context: TransformationContext) -> bool:
        return data_type in ['ticker', 'balance', 'order', 'position', 'market']
    
    def transform(self, data: Dict[str, Any], context: TransformationContext) -> Dict[str, Any]:
        """응답 구조 변환"""
        if not isinstance(data, dict):
            return data
        
        try:
            if context.target_format == 'ccxt':
                return self._to_ccxt_response(data, context)
            elif context.target_format == 'custom':
                return self._to_custom_response(data, context)
            else:
                return data
                
        except Exception as e:
            logger.error(f"❌ 응답 변환 실패: {e}")
            return data
    
    def _to_ccxt_response(self, data: Dict[str, Any], context: TransformationContext) -> Dict[str, Any]:
        """CCXT 표준 응답 형식으로 변환"""
        # 구현 생략 (실제로는 각 데이터 타입별로 상세 구현)
        return data
    
    def _to_custom_response(self, data: Dict[str, Any], context: TransformationContext) -> Dict[str, Any]:
        """커스텀 응답 형식으로 변환"""
        # 구현 생략 (실제로는 각 데이터 타입별로 상세 구현)
        return data

class TransformationPipeline:
    """데이터 변환 파이프라인"""
    
    def __init__(self):
        self.transformers: List[DataTransformer] = [
            SymbolTransformer(),
            NumericTransformer(), 
            TimestampTransformer(),
            StatusTransformer(),
            ResponseTransformer()
        ]
        self._transformation_cache: Dict[str, Any] = {}
    
    def register_transformer(self, transformer: DataTransformer):
        """변환기 등록"""
        self.transformers.append(transformer)
        logger.info(f"🔧 변환기 등록: {transformer.__class__.__name__}")
    
    def transform(
        self,
        data: Any,
        data_type: str,
        context: TransformationContext,
        use_cache: bool = True
    ) -> Any:
        """데이터 변환 실행"""
        
        # 캐시 확인
        if use_cache:
            cache_key = self._get_cache_key(data, data_type, context)
            if cache_key in self._transformation_cache:
                return self._transformation_cache[cache_key]
        
        # 적절한 변환기 찾기
        transformer = self._find_transformer(data_type, context)
        if not transformer:
            logger.debug(f"🔍 적절한 변환기 없음: {data_type}")
            return data
        
        try:
            # 변환 실행
            result = transformer.transform(data, context)
            
            # 검증 (옵션)
            if context.validate_output:
                self._validate_output(result, data_type, context)
            
            # 캐시 저장
            if use_cache and cache_key:
                self._transformation_cache[cache_key] = result
            
            logger.debug(f"🔄 데이터 변환 완료: {data_type} ({context.target_format})")
            return result
            
        except Exception as e:
            logger.error(f"❌ 변환 실행 실패 ({data_type}): {e}")
            return data
    
    def _find_transformer(self, data_type: str, context: TransformationContext) -> Optional[DataTransformer]:
        """적절한 변환기 찾기"""
        for transformer in self.transformers:
            if transformer.can_handle(data_type, context):
                return transformer
        return None
    
    def _get_cache_key(self, data: Any, data_type: str, context: TransformationContext) -> Optional[str]:
        """캐시 키 생성"""
        try:
            data_str = str(data) if not isinstance(data, dict) else json.dumps(data, sort_keys=True)
            if len(data_str) > 1000:  # 너무 큰 데이터는 캐시하지 않음
                return None
                
            return f"{data_type}_{context.target_format}_{hash(data_str)}"
        except:
            return None
    
    def _validate_output(self, result: Any, data_type: str, context: TransformationContext):
        """출력 검증"""
        # 기본적인 타입 검증
        if data_type == 'symbol' and not isinstance(result, str):
            raise ValueError(f"심볼은 문자열이어야 함: {type(result)}")
        
        if data_type in ['price', 'quantity'] and result is not None:
            if not isinstance(result, (int, float, Decimal)):
                raise ValueError(f"수치 데이터는 숫자 타입이어야 함: {type(result)}")
    
    def batch_transform(
        self,
        data_list: List[Any],
        data_type: str,
        context: TransformationContext
    ) -> List[Any]:
        """배치 변환"""
        results = []
        for data in data_list:
            result = self.transform(data, data_type, context)
            results.append(result)
        
        logger.debug(f"📦 배치 변환 완료: {len(data_list)}개 ({data_type})")
        return results
    
    def clear_cache(self):
        """캐시 정리"""
        cache_size = len(self._transformation_cache)
        self._transformation_cache.clear()
        logger.info(f"🧹 변환 캐시 정리: {cache_size}개")
    
    def get_stats(self) -> Dict[str, Any]:
        """변환 통계"""
        return {
            'registered_transformers': len(self.transformers),
            'transformer_types': [t.__class__.__name__ for t in self.transformers],
            'cache_size': len(self._transformation_cache)
        }

# 전역 파이프라인 인스턴스
transformation_pipeline = TransformationPipeline()

# 편의 함수들
def transform_symbol(symbol: str, source_exchange: str, target_format: str = 'ccxt') -> str:
    """심볼 변환 (편의 함수)"""
    context = TransformationContext(
        source_exchange=source_exchange,
        target_format=target_format
    )
    return transformation_pipeline.transform(symbol, 'symbol', context)

def transform_price(price: Any, target_format: str = 'ccxt', preserve_precision: bool = True) -> Any:
    """가격 변환 (편의 함수)"""
    context = TransformationContext(
        source_exchange='binance',  # 기본값
        target_format=target_format,
        preserve_precision=preserve_precision
    )
    return transformation_pipeline.transform(price, 'price', context)

def transform_order_status(status: str, target_format: str = 'ccxt') -> str:
    """주문 상태 변환 (편의 함수)"""
    context = TransformationContext(
        source_exchange='binance',
        target_format=target_format
    )
    return transformation_pipeline.transform(status, 'order_status', context)