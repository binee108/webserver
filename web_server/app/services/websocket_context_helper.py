"""
WebSocket 컨텍스트 헬퍼

@FEAT:websocket-context-helper @COMP:service @TYPE:helper @DEPS:db-session-management

WebSocket 연결을 위한 메시지별 데이터베이스 세션 관리를 제공합니다.
각 WebSocket 메시지가 자체 데이터베이스 컨텍스트를 갖도록 하여,
장기간 살아있는 Flask 앱 컨텍스트로 인한 연결 풀 고갈을 방지합니다.

주요 기능:
- 메시지별 DB 세션: 각 메시지가 자체 데이터베이스 컨텍스트 보유
- 비동기 컨텍스트 관리자: 재사용 가능한 비동기 데이터베이스 작업 헬퍼
- 자원 정리: 자동 세션 정리 및 연결 해제
- 오류 처리: 적절한 예외 처리 및 로깅
- 연결 풀 모니터링: 데이터베이스 연결 풀 상태 추적
"""

import logging
import asyncio
from typing import Optional, Any, Callable, Dict, Union, Awaitable
from contextlib import asynccontextmanager
from flask import Flask

logger = logging.getLogger(__name__)


class WebSocketContextError(Exception):
    """WebSocket 컨텍스트 관련 오류"""
    pass


# @FEAT:websocket-context-helper @COMP:service @TYPE:helper @DEPS:db-session-management
class WebSocketContextHelper:
    """
    WebSocket 컨텍스트 헬퍼

    WebSocket 작업을 위한 메시지별 데이터베이스 세션 관리를 제공합니다.
    적절한 자원 정리와 연결 풀 고갈 방지를 보장합니다.

    사용 예시:
        ```python
        # 기본 사용법
        helper = WebSocketContextHelper(app)
        result = await helper.execute_with_db_context(process_message, data)

        # 컨텍스트 관리자 사용법
        async with WebSocketContextHelper(app) as helper:
            result = await helper.execute_with_db_context(process_message, data)

        # 재시도 로직 포함
        result = await helper.safe_execute_with_retry(
            process_message, data, max_retries=3
        )
        ```
    """

    def __init__(self, app: Flask):
        """
        WebSocket 컨텍스트 헬퍼 초기화

        Args:
            app: Flask 애플리케이션 인스턴스

        Raises:
            WebSocketContextError: Flask 앱이 유효하지 않은 경우
        """
        if app is None:
            raise WebSocketContextError("Flask app 인스턴스가 필요합니다")

        self.app = app
        self._logger = logger

    async def execute_with_db_context(
        self,
        func: Callable[..., Awaitable[Any]],
        *args,
        **kwargs
    ) -> Any:
        """
        데이터베이스 컨텍스트와 함께 함수 실행

        이 메소드는 각 메시지 실행을 위해 새로운 Flask 앱 컨텍스트를 생성하여
        메시지별 데이터베이스 세션 관리를 제공합니다.

        Args:
            func: 데이터베이스 컨텍스트와 함께 실행할 비동기 함수
            *args: func에 전달할 위치 인수
            **kwargs: func에 전달할 키워드 인수

        Returns:
            func 실행 결과

        Raises:
            WebSocketContextError: 컨텍스트 실행 중 오류 발생 시
            Exception: func에서 발생한 모든 예외 전파
        """
        if not callable(func):
            raise WebSocketContextError("유효한 함수가 필요합니다")

        try:
            # 이 특정 메시지를 위한 새 Flask 앱 컨텍스트 생성
            with self.app.app_context():
                # 적절한 데이터베이스 컨텍스트와 함께 함수 실행
                self._logger.debug(f"데이터베이스 컨텍스트에서 함수 실행: {func.__name__}")
                result = await func(*args, **kwargs)
                return result

        except Exception as e:
            self._logger.error(f"데이터베이스 컨텍스트 실행 중 오류 발생: {str(e)}")
            # 호출자가 처리할 수 있도록 예외 재발생
            raise

    def get_connection_pool_status(self) -> Dict[str, Union[int, str]]:
        """
        현재 연결 풀 상태 조회

        Returns:
            연결 풀 메트릭을 포함하는 딕셔너리:
            - size: 총 풀 크기
            - checked_in: 체크인된 연결 수
            - checked_out: 체크아웃된 연결 수
            - status: 풀 상태 (healthy, unavailable, error)
        """
        try:
            # Flask 앱에서 SQLAlchemy 엔진 조회
            sqlalchemy_ext = self.app.extensions.get('sqlalchemy')
            if not sqlalchemy_ext:
                return {
                    'size': 0,
                    'checked_in': 0,
                    'checked_out': 0,
                    'status': 'unavailable',
                    'reason': 'SQLAlchemy 확장을 찾을 수 없음'
                }

            engine = getattr(sqlalchemy_ext, 'engine', None)
            if not engine:
                return {
                    'size': 0,
                    'checked_in': 0,
                    'checked_out': 0,
                    'status': 'unavailable',
                    'reason': 'SQLAlchemy 엔진을 찾을 수 없음'
                }

            if hasattr(engine, 'pool'):
                pool = engine.pool

                return {
                    'size': pool.size(),
                    'checked_in': pool.checked_in(),
                    'checked_out': pool.checked_out(),
                    'status': 'healthy',
                    'utilization': pool.checked_out() / pool.size() if pool.size() > 0 else 0
                }
            else:
                return {
                    'size': 0,
                    'checked_in': 0,
                    'checked_out': 0,
                    'status': 'unavailable',
                    'reason': '연결 풀을 찾을 수 없음'
                }

        except Exception as e:
            self._logger.warning(f"연결 풀 상태 조회 실패: {str(e)}")
            return {
                'size': 0,
                'checked_in': 0,
                'checked_out': 0,
                'status': 'error',
                'error': str(e)
            }

    async def __aenter__(self) -> 'WebSocketContextHelper':
        """
        비동기 컨텍스트 관리자 진입

        Returns:
            컨텍스트 관리자 프로토콜을 위한 자기 자신
        """
        self._logger.debug("WebSocket 컨텍스트 헬퍼 시작")
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """
        비동기 컨텍스트 관리자 종료

        Args:
            exc_type: 예외 타입 (있는 경우)
            exc_val: 예외 값 (있는 경우)
            exc_tb: 예외 추적 (있는 경우)
        """
        if exc_type:
            self._logger.warning(f"WebSocket 컨텍스트에서 예외 발생: {exc_val}")
        else:
            self._logger.debug("WebSocket 컨텍스트 헬퍼 정상 종료")
        # 필요한 경우 정리 로직 수행
        pass

    @asynccontextmanager
    async def message_context(self):
        """
        메시지별 데이터베이스 컨텍스트 생성

        메시지별 데이터베이스 작업을 위한 대안 인터페이스로
        비동기 컨텍스트 관리자를 사용합니다.

        Yields:
            메시지 처리를 위한 데이터베이스 컨텍스트
        """
        try:
            with self.app.app_context():
                yield self
        except Exception as e:
            self._logger.error(f"메시지 컨텍스트 오류: {str(e)}")
            raise

    def validate_connection_health(self) -> bool:
        """
        연결 풀 상태 유효성 검사

        Returns:
            연결 풀이 건강하면 True, 그렇지 않으면 False
        """
        status = self.get_connection_pool_status()

        if status['status'] != 'healthy':
            return False

        # 풀 고갈 여부 확인
        utilization = status.get('utilization', 0)
        if utilization >= 0.9:  # 90% 이상 사용 시 경고
            self._logger.warning(
                f"연결 풀 거의 고갈: {status['checked_out']}/{status['size']} "
                f"({utilization:.1%})"
            )
            return False

        return True

    async def safe_execute_with_retry(
        self,
        func: Callable[..., Awaitable[Any]],
        max_retries: int = 3,
        retry_delay: float = 1.0,
        *args,
        **kwargs
    ) -> Any:
        """
        연결 문제에 대한 재시도 로직을 포함한 안전한 함수 실행

        Args:
            func: 실행할 비동기 함수
            max_retries: 최대 재시도 횟수
            retry_delay: 재시도 간 지연 시간 (초)
            *args: func에 대한 위치 인수
            **kwargs: func에 대한 키워드 인수

        Returns:
            func 실행 결과

        Raises:
            WebSocketContextError: 모든 재시도 실패 시 마지막 예외
        """
        if not callable(func):
            raise WebSocketContextError("유효한 함수가 필요합니다")

        last_exception = None

        for attempt in range(max_retries + 1):
            try:
                # 실행 전 연결 상태 확인
                if attempt > 0:
                    if not self.validate_connection_health():
                        self._logger.warning(
                            f"연결 풀 상태 불량, 재시도 {attempt} 전 대기"
                        )
                        await asyncio.sleep(retry_delay)

                return await self.execute_with_db_context(func, *args, **kwargs)

            except Exception as e:
                last_exception = e
                if attempt < max_retries:
                    self._logger.warning(
                        f"실행 실패 (시도 {attempt + 1}/{max_retries + 1}): {str(e)}"
                    )
                    await asyncio.sleep(retry_delay)
                else:
                    self._logger.error(
                        f"{max_retries + 1}번 시도 후 실행 실패: {str(e)}"
                    )

        raise WebSocketContextError(f"재시도 실패: {str(last_exception)}") from last_exception