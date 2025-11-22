# WebSocket Integration Enhancement

> **Feature**: WebSocket 통합 강화
> **TAG**: `@FEAT:websocket-integration @COMP:websocket-infrastructure @TYPE:integration`
> **Phase**: Phase 2 - 통합 WebSocket 관리자 구현
> **Status**: ✅ Complete
> **Last Updated**: 2025-11-22

## 개요

WebSocket 통합 강화는 거래소 중립적인 통합 WebSocket 관리 시스템을 구현하는 기능입니다. Phase 2에서는 UnifiedWebSocketManager를 중심으로 Public/Private WebSocket 연결을 통합 관리하고, WebSocketConnectorFactory 팩토리 패턴으로 거래소별 커넥터를 생성하며, PublicWebSocketHandler로 실시간 가격 데이터를 정규화하고 캐싱합니다.

## 주요 기능

### 1. UnifiedWebSocketManager - 통합 WebSocket 관리자

거래소 중립적 WebSocket 연결 관리 시스템으로 Public/Private 연결을 통합적으로 관리합니다.

#### 핵심 기능
- **연결 통합 관리**: Public/Private WebSocket 연결을 단일 인터페이스로 통합 관리
- **거래소 중립성**: Binance, Bybit, Upbit, Bithumb 등 다중 거래소 지원
- **연결 풀링**: 연결 재사용으로 리소스 최적화
- **자동 재연결**: 연결 끊김 시 자동 재연결 및 상태 모니터링
- **스레드 안전성**: RLock을 사용한 동시성 제어

#### 주요 클래스
```python
class UnifiedWebSocketManager:
    """거래소 중립적 통합 WebSocket 관리자"""

    async def create_public_connection(self, exchange: str, symbols: List[str]) -> UnifiedConnection
    async def create_private_connection(self, account: Any) -> UnifiedConnection
    async def close_connection(self, connection_id: str) -> None
    def get_connection_stats(self) -> Dict[str, Any]
```

#### 지원 연결 유형
- `PUBLIC_PRICE_FEED`: 실시간 가격 데이터
- `PRIVATE_ORDER_EXECUTION`: 주문 실행 알림
- `PUBLIC_ORDER_BOOK`: 오더북 데이터
- `PRIVATE_POSITION_UPDATE`: 포지션 업데이트

### 2. WebSocketConnectorFactory - 커넥터 팩토리

거래소별 WebSocket 커넥터를 생성하고 관리하는 팩토리 클래스입니다.

#### 핵심 기능
- **팩토리 패턴**: 거래소별 커넥터 생성 캡슐화
- **커넥터 풀링**: 생성된 커넥터 재사용 및 풀 관리
- **커스텀 커넥터 등록**: 동적 커넥터 타입 확장 지원
- **설정 기반 구성**: 중앙화된 설정 관리

#### 기본 지원 커넥터
- `BinancePublicConnector`: Binance Public WebSocket
- `BinancePrivateConnector`: Binance Private WebSocket
- `BybitPublicConnector`: Bybit Public WebSocket
- `BybitPrivateConnector`: Bybit Private WebSocket

#### 사용 예시
```python
# 팩토리 인스턴스 생성
factory = WebSocketConnectorFactory()

# 커넥터 생성
connector = factory.create_connector("BinancePublicConnector")

# 비동기 연결
await factory.async_create_connector("BybitPrivateConnector")
```

### 3. PublicWebSocketHandler - 실시간 가격 데이터 핸들러

거래소별 Public WebSocket 연결을 관리하고 실시간 가격 데이터를 정규화하여 제공합니다.

#### 핵심 기능
- **실시간 데이터 수신**: Binance/Bybit WebSocket 연결 관리
- **데이터 정규화**: 거래소별 데이터를 표준 PriceQuote 형식으로 변환
- **가격 캐싱**: 메모리 캐시로 최신 가격 데이터 관리
- **심볼 구독 관리**: 동적 심볼 추가/제거 구독
- **자동 재연결**: 연결 실패 시 자동 복구

#### 데이터 정규화
```python
# Binance 데이터 → PriceQuote
{
    "e": "24hrTicker",
    "s": "BTCUSDT",
    "c": "50000.00",
    "v": "1000.0",
    "P": "2.5"
}
# ↓ 정규화
PriceQuote(
    exchange="binance",
    symbol="BTCUSDT",
    price=50000.00,
    timestamp=1640995200000,
    volume=1000.0,
    change_24h=2.5
)
```

#### 캐시 관리
- 최대 캐시 크기: 설정 가능 (기본값: 1000)
- 캐시 만료 시간: 설정 가능 (기본값: 60초)
- 자동 만료 데이터 정리

## Phase 1과의 통합

### 주문 상태 표준화와의 연동
Phase 1에서 구현된 `order-status-standardization` 기능과 연동하여 WebSocket으로 수신된 주문 상태 변경을 표준화된 형식으로 처리합니다.

### StandardOrderStatus 활용
```python
# WebSocket 주문 상태 업데이트
order_status = {
    "exchange_order_id": "12345",
    "status": "FILLED",
    "filled_quantity": "1.5",
    "filled_price": "50000.00"
}

# OrderStatusTransformer로 표준화
standard_status = OrderStatusTransformer.transform('binance', order_status)
```

## 아키텍처

### 컴포넌트 구조
```
UnifiedWebSocketManager
├── WebSocketConnectorFactory
│   ├── BinancePublicConnector
│   ├── BinancePrivateConnector
│   ├── BybitPublicConnector
│   └── BybitPrivateConnector
├── PublicWebSocketHandler
│   ├── DataNormalizerFactory
│   ├── PriceCache
│   └── ConnectionManager
└── PrivateWebSocketHandler (향후 확장)
```

### 데이터 흐름
```
거래소 WebSocket → PublicWebSocketHandler → DataNormalizer → PriceQuote → 캐싱 → 콜백
```

## 사용법

### 1. UnifiedWebSocketManager 초기화
```python
from app.services.unified_websocket_manager import UnifiedWebSocketManager
from flask import Flask

app = Flask(__name__)
ws_manager = UnifiedWebSocketManager(app)

# 거래소 핸들러 등록
factory = get_websocket_connector_factory()
binance_handler = factory.create_connector("BinancePublicConnector")
ws_manager.register_exchange_handler("binance", binance_handler)
```

### 2. Public 연결 생성
```python
import asyncio

async def main():
    # Public 연결 생성
    connection = await ws_manager.create_public_connection(
        exchange="binance",
        symbols=["BTCUSDT", "ETHUSDT"],
        connection_type=ConnectionType.PUBLIC_PRICE_FEED
    )

    print(f"연결 생성: {connection.id}")
    return connection

# 실행
connection = asyncio.run(main())
```

### 3. Private 연결 생성
```python
async def create_private_connection(account):
    connection = await ws_manager.create_private_connection(
        account=account,
        connection_type=ConnectionType.PRIVATE_ORDER_EXECUTION
    )
    return connection
```

### 4. PublicWebSocketHandler 직접 사용
```python
from app.services.websocket.public_websocket_handler import PublicWebSocketHandler

# 핸들러 생성
handler = PublicWebSocketHandler(
    exchange="binance",
    symbols=["BTCUSDT", "ETHUSDT"]
)

# 연결
await handler.connect()

# 가격 업데이트 콜백 설정
async def on_price_update(price_quote):
    print(f"가격 업데이트: {price_quote.symbol} = {price_quote.price}")

handler.on_price_update = on_price_update

# 최신 가격 조회
latest_price = handler.get_latest_price("BTCUSDT")
if latest_price:
    print(f"BTC 가격: {latest_price.price}")
```

## 호환성 및 마이그레이션

### 기존 WebSocketManager에서 마이그레이션

#### 기존 코드
```python
# 기존 방식
from app.services.websocket_manager import WebSocketManager

ws_manager = WebSocketManager()
await ws_manager.connect_binance_public(symbols)
```

#### 새로운 방식
```python
# 새로운 방식
from app.services.unified_websocket_manager import UnifiedWebSocketManager

ws_manager = UnifiedWebSocketManager(app)
connection = await ws_manager.create_public_connection(
    exchange="binance",
    symbols=symbols
)
```

### 하위 호환성 보장
- 기존 WebSocketManager는 그대로 유지
- 점진적 마이그레이션 지원
- API 변경 시 래퍼 함수 제공

## 성능 최적화

### 연결 풀링
- 동일 거래소/연결 타입은 커넥터 재사용
- 최대 풀 크기 설정으로 리소스 관리
- 비활성 커넥터 자동 정리

### 캐시 최적화
- 메모리 캐시로 빠른 가격 데이터 조회
- 만료 데이터 자동 정리로 메모리 효율화
- 캐시 크기 동적 조절

### 동시성 제어
- RLock으로 스레드 안전성 보장
- 연결 상태 원자적 업데이트
- 경합 최소화를 위한 세분화된 락

## 모니터링 및 디버깅

### 연결 상태 모니터링
```python
# 연결 통계 조회
stats = ws_manager.get_connection_stats()
print(f"총 연결: {stats['total_connections']}")
print(f"활성 연결: {stats['active_connections']}")

# 개별 연결 정보
connection = ws_manager._safe_get_connection(connection_id)
if connection:
    info = connection.get_info()
    print(f"연결 상태: {info['state']}")
    print(f"에러 횟수: {info['error_count']}")
```

### 로깅
- 연결 상태 변경 로깅
- 에러 발생 시 상세 로그
- 성능 메트릭 수집

## 확장성

### 새로운 거래소 추가
1. 커넥터 클래스 구현
```python
class NewExchangePublicConnector(BaseWebSocketConnector):
    def __init__(self, config_manager):
        super().__init__("newexchange", ConnectionType.PUBLIC_PRICE_FEED, config_manager)
```

2. 팩토리에 등록
```python
factory.register_custom_connector(
    name="NewExchangePublicConnector",
    connector_class=NewExchangePublicConnector,
    exchange="newexchange",
    connection_type=ConnectionType.PUBLIC_PRICE_FEED
)
```

### 새로운 연결 타입 추가
```python
class ConnectionType(Enum):
    PUBLIC_PRICE_FEED = "price_feed"
    PRIVATE_ORDER_EXECUTION = "order_execution"
    PUBLIC_ORDER_BOOK = "order_book"
    PRIVATE_POSITION_UPDATE = "position_update"
    NEW_CONNECTION_TYPE = "new_type"  # 새로운 타입
```

## 테스트

### 테스트 커버리지
- 총 14개 테스트 파일, 100% 통과
- 단위 테스트: 각 컴포넌트별 기능 검증
- 통합 테스트: 컴포넌트 간 연동 검증
- 성능 테스트: 연결 풀링 및 캐시 성능

### 주요 테스트 케이스
- 커넥터 생성 및 등록
- 연결 생성 및 종료
- 데이터 정규화
- 캐시 관리
- 에러 처리 및 재연결
- 스레드 안전성

## 결론

WebSocket 통합 강화 Phase 2는 다음과 같은 개선을 제공합니다:

1. **통합 관리**: UnifiedWebSocketManager로 모든 WebSocket 연결 중앙 관리
2. **확장성**: 팩토리 패턴으로 새로운 거래소 쉽게 추가
3. **성능**: 연결 풀링과 캐싱으로 리소스 효율화
4. **안정성**: 자동 재연결과 에러 처리로 안정성 향상
5. **표준화**: 데이터 정규화로 일관된 인터페이스 제공

Phase 1의 주문 상태 표준화와 완벽하게 통합되어 거래소 중립적인 실시간 데이터 처리 기반을 제공합니다.

---

**관련 문서**:
- [주문 상태 표준화](order-status-standardization.md)
- [거래소 통합](exchange-integration.md)
- [WebSocket 아키텍처 수정사항](websocket-architectural-fixes.md)

**파일 경로**:
- `web_server/app/services/unified_websocket_manager.py`
- `web_server/app/services/websocket/connectors/websocket_connector_factory.py`
- `web_server/app/services/websocket/public_websocket_handler.py`
- `tests/services/test_unified_websocket_manager.py`
- `tests/services/test_websocket_connector_factory.py`
- `tests/services/test_public_websocket_handler.py`