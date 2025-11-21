# WebSocket Context Helper

> **Feature**: `@FEAT:websocket-context-helper` `@COMP:service` `@TYPE:helper` `@DEPS:db-session-management`

## 개요

WebSocket Context Helper는 WebSocket 연결에서 메시지별 데이터베이스 세션 관리를 제공하는 서비스입니다. 각 WebSocket 메시지가 자체 데이터베이스 컨텍스트를 갖도록 하여 장기간 살아있는 Flask 앱 컨텍스트로 인한 연결 풀 고갈을 방지합니다.

## 주요 기능

### 1. 메시지별 DB 세션 관리
- 각 WebSocket 메시지가 독립적인 데이터베이스 컨텍스트 보유
- Flask 앱 컨텍스트 자동 생성 및 정리
- 연결 풀 고갈 방지

### 2. 비동기 컨텍스트 관리
- 재사용 가능한 비동기 데이터베이스 작업 헬퍼
- `async with` 구문 지원
- 자동 자원 정리

### 3. 연결 풀 모니터링
- 실시간 연결 풀 상태 조회
- 풀 활용률 모니터링
- 건강 상태 검증

### 4. 안정성 기능
- 재시도 로직 포함 실행
- 적절한 예외 처리 및 로깅
- 연결 상태 유효성 검사

## 아키텍처

### 클래스 구조
```
WebSocketContextHelper
├── execute_with_db_context()     # 메인 실행 메소드
├── message_context()             # 컨텍스트 관리자
├── safe_execute_with_retry()     # 재시도 로직 포함 실행
├── get_connection_pool_status()  # 연결 풀 상태 조회
├── validate_connection_health()  # 연결 건강 상태 검증
└── __aenter__ / __aexit__()      # 비동기 컨텍스트 관리
```

### 의존성
- **Flask**: 앱 컨텍스트 관리
- **SQLAlchemy**: 데이터베이스 연결 풀 접근
- **asyncio**: 비동기 실행 지원

## 사용법

### 기본 사용법
```python
from web_server.app.services.websocket_context_helper import WebSocketContextHelper

# 헬퍼 인스턴스 생성
helper = WebSocketContextHelper(app)

# 메시지 처리 함수 정의
async def process_message(data):
    # 데이터베이스 작업 수행
    with db.session() as session:
        # 메시지 처리 로직
        result = session.query(Model).filter_by(id=data['id']).first()
        return result

# 데이터베이스 컨텍스트와 함께 실행
result = await helper.execute_with_db_context(process_message, message_data)
```

### 컨텍스트 관리자 사용
```python
# 자동 정리 포함 사용법
async with WebSocketContextHelper(app) as helper:
    result = await helper.execute_with_db_context(process_message, data)
    # 자원이 자동으로 정리됨
```

### 메시지 컨텍스트 사용
```python
# 대안 컨텍스트 관리자 인터페이스
async with helper.message_context():
    # 데이터베이스 작업 수행
    result = await process_websocket_message(message)
```

### 재시도 로직 포함 실행
```python
# 연결 문제에 대한 자동 재시도
result = await helper.safe_execute_with_retry(
    process_message,
    message_data,
    max_retries=3,
    retry_delay=1.0
)
```

### 연결 풀 모니터링
```python
# 연결 풀 상태 조회
status = helper.get_connection_pool_status()
print(f"Pool size: {status['size']}")
print(f"Checked out: {status['checked_out']}")
print(f"Utilization: {status['utilization']:.1%}")

# 연결 건강 상태 검증
is_healthy = helper.validate_connection_health()
if not is_healthy:
    logger.warning("Connection pool is not healthy")
```

## 통합 가이드

### WebSocket 핸들러에서의 사용
```python
async def handle_websocket_message(websocket, message):
    """WebSocket 메시지 처리 핸들러"""
    helper = WebSocketContextHelper(current_app)

    try:
        # 메시지별 데이터베이스 컨텍스트로 실행
        result = await helper.execute_with_db_context(
            process_trading_message,
            message
        )

        # 결과 전송
        await websocket.send_json(result)

    except WebSocketContextError as e:
        # 컨텍스트 관련 오류 처리
        logger.error(f"WebSocket context error: {e}")
        await websocket.send_json({
            'error': 'Processing failed',
            'details': str(e)
        })
    except Exception as e:
        # 기타 오류 처리
        logger.error(f"Message processing error: {e}")
        await websocket.send_json({
            'error': 'Unexpected error'
        })
```

### 여러 WebSocket 연결 관리
```python
class WebSocketManager:
    def __init__(self, app):
        self.app = app
        self.connections = []
        self.context_helper = WebSocketContextHelper(app)

    async def broadcast_to_all(self, message):
        """모든 연결에 메시지 브로드캐스트"""
        results = []

        for websocket in self.connections:
            try:
                # 각 연결은 독립적인 컨텍스트에서 처리
                result = await self.context_helper.execute_with_db_context(
                    self.process_message_for_connection,
                    websocket,
                    message
                )
                results.append(result)

            except Exception as e:
                logger.error(f"Broadcast failed for connection: {e}")

        return results
```

## 성능 특성

### 자원 관리
- **연결 풀 활용**: SQLAlchemy 연결 풀 효율적 사용
- **자동 정리**: 컨텍스트 종료 시 자원 자동 해제
- **메모리 최적화**: 불필요한 Flask 컨텍스트 유지 방지

### 성능 측정
- 테스트 커버리지: 93%
- 20개 테스트 실행 시간: 0.43초
- 연결 풀 활용률 모니터링 지원

### 확장성
- **동시성 지원**: 여러 WebSocket 메시지 동시 처리
- **수평 확장**: 다중 프로세스 환경에서 안정적 동작
- **모니터링**: 연결 풀 상태 실시간 모니터링

## 오류 처리

### 주요 예외 타입
- **WebSocketContextError**: 컨텍스트 관련 기본 예외
- **ValueError**: 잘못된 파라미터 전달 시
- **RuntimeError**: 데이터베이스 연결 문제 시

### 오류 처리 예시
```python
try:
    result = await helper.execute_with_db_context(process_message, data)
except WebSocketContextError as e:
    # 컨텍스트 관련 오류
    logger.error(f"Context error: {e}")
    # 재시도 또는 연결 종료 로직
except Exception as e:
    # 기타 예외 처리
    logger.error(f"Unexpected error: {e}")
    # 적절한 에러 응답 전송
```

## 모니터링 및 디버깅

### 로깅
```python
# DEBUG 레벨: 상세한 컨텍스트 실행 정보
logger.debug(f"Executing function {func.__name__} in DB context")

# WARNING 레벨: 연결 풀 상태 경고
logger.warning(f"Connection pool almost exhausted: {utilization:.1%}")

# ERROR 레벨: 실행 오류
logger.error(f"Database context execution error: {str(e)}")
```

### 상태 모니터링
```python
# 정기적인 연결 풀 상태 확인
async def monitor_connection_pool():
    helper = WebSocketContextHelper(app)

    while True:
        status = helper.get_connection_pool_status()
        if status['status'] != 'healthy':
            send_alert(f"Connection pool unhealthy: {status}")

        await asyncio.sleep(60)  # 1분마다 확인
```

## 관련 기능

- **db-session-management**: 데이터베이스 세션 관리 기반
- **websocket-architectural-fixes**: WebSocket 아키텍처 개선
- **health-monitoring**: 시스템 건강 상태 모니터링

## 테스트

### 단위 테스트
```python
# 컨텍스트 실행 테스트
async def test_execute_with_db_context():
    helper = WebSocketContextHelper(app)

    async def test_func(data):
        return data * 2

    result = await helper.execute_with_db_context(test_func, 5)
    assert result == 10
```

### 통합 테스트
```python
# WebSocket 통합 테스트
async def test_websocket_integration():
    helper = WebSocketContextHelper(app)

    # 실제 WebSocket 메시지 처리 시뮬레이션
    result = await helper.execute_with_db_context(
        process_websocket_message,
        test_message_data
    )

    assert result['status'] == 'success'
```

## 배포 및 운영

### 환경 설정
- Flask 앱 인스턴스 필수
- SQLAlchemy 데이터베이스 설정 필요
- 로깅 레벨 권장: INFO (운영), DEBUG (개발)

### 모니터링 추천
- 연결 풀 활용률: 80% 미만 유지
- 오류 발생률: 1% 미만 목표
- 응답 시간: 100ms 미만 목표