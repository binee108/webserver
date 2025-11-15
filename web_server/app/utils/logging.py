# @FEAT:background-log-tagging @COMP:util @TYPE:helper
"""
백그라운드 작업 로깅 유틸리티

이 모듈은 백그라운드 작업의 로그를 일관되게 포맷팅하는 함수를 제공합니다.
모든 백그라운드 작업은 format_background_log()를 사용하거나
@tag_background_logger 데코레이터를 사용하여 태그를 포함한 로그를 남겨야 합니다.

Usage:
    # 방법 1: 함수 직접 호출
    from app.utils.logging import format_background_log
    from app.constants import BackgroundJobTag

    logger.info(format_background_log(BackgroundJobTag.AUTO_REBAL, "작업 시작"))
    # Output: [AUTO_REBAL] 작업 시작

    # 방법 2: 데코레이터 사용 (권장 - 백그라운드 작업)
    @tag_background_logger(BackgroundJobTag.AUTO_REBAL)
    def my_background_job(app):
        app.logger.info("작업 시작")  # 자동: [AUTO_REBAL] 작업 시작

@FEAT:background-log-tagging @COMP:util @TYPE:helper
"""
import contextvars
from functools import wraps
from app.constants import BackgroundJobTag

# Thread-local storage for background job tags
_current_tag = contextvars.ContextVar('background_job_tag', default=None)


def format_background_log(tag: BackgroundJobTag, message: str) -> str:
    """백그라운드 작업 로그 포맷팅

    태그와 메시지를 결합하여 일관된 형식의 로그를 생성합니다.
    이 함수는 모든 백그라운드 작업의 로깅에서 사용되어야 하며,
    로그 메시지는 [TAG] 형식으로 시작하게 됩니다.

    Args:
        tag (BackgroundJobTag): 백그라운드 작업 태그 상수
                                (BackgroundJobTag.AUTO_REBAL 등)
        message (str): 로그 메시지 (예: "작업 시작", "캐시 업데이트 완료")

    Returns:
        str: 태그가 포함된 포맷팅된 로그 메시지
             형식: "[TAG_NAME] message"

    Examples:
        >>> format_background_log(BackgroundJobTag.AUTO_REBAL, "작업 시작")
        "[AUTO_REBAL] 작업 시작"

        >>> format_background_log(BackgroundJobTag.PRICE_CACHE, "캐시 업데이트 완료")
        "[PRICE_CACHE] 캐시 업데이트 완료"

    Note:
        이 함수는 순수 문자열 포맷팅만 수행합니다.
        실제 로깅은 logger.info(), logger.debug() 등에서 수행하세요.
    """
    return f"{tag} {message}"


class TaggedLogger:
    """
    태그가 자동으로 적용되는 Thread-Safe Logger 래퍼

    Flask의 logger를 투명하게 래핑하여 모든 로그 호출에
    백그라운드 작업 태그를 자동으로 추가합니다.

    contextvars를 사용하여 스레드별로 독립적인 태그를 적용하므로
    동시 실행되는 여러 백그라운드 작업 간 태그 혼선이 발생하지 않습니다.

    Args:
        original_logger: Flask app.logger 인스턴스

    Features:
        - Python varargs 지원: logger.debug('msg %s %s', arg1, arg2) 동작
        - Thread-safe: 동시 실행 작업 간 태그 혼합 없음
        - 기존 코드 호환: 단일 message 인자도 정상 작동

    Example:
        app.logger = TaggedLogger(app.logger)

        # Context 내에서 태그 자동 적용
        with _current_tag.set(BackgroundJobTag.AUTO_REBAL):
            app.logger.info("작업 시작")  # 출력: [AUTO_REBAL] 작업 시작
            app.logger.debug("진행 %d/%d", 5, 10)  # 출력: [AUTO_REBAL] 진행 5/10

    @FEAT:background-log-tagging @COMP:util @TYPE:helper
    """
    def __init__(self, original_logger):
        self._logger = original_logger

    def debug(self, message: str, *args, **kwargs):
        """DEBUG 레벨 로그에 태그 적용 (varargs 지원)"""
        tag = _current_tag.get()
        if tag:
            # varargs가 있으면 포맷팅 먼저 수행
            if args:
                formatted_message = message % args
            else:
                formatted_message = message
            self._logger.debug(format_background_log(tag, formatted_message), **kwargs)
        else:
            # 태그 없으면 원본 logger 동작
            self._logger.debug(message, *args, **kwargs)

    def info(self, message: str, *args, **kwargs):
        """INFO 레벨 로그에 태그 적용 (varargs 지원)"""
        tag = _current_tag.get()
        if tag:
            if args:
                formatted_message = message % args
            else:
                formatted_message = message
            self._logger.info(format_background_log(tag, formatted_message), **kwargs)
        else:
            self._logger.info(message, *args, **kwargs)

    def warning(self, message: str, *args, **kwargs):
        """WARNING 레벨 로그에 태그 적용 (varargs 지원)"""
        tag = _current_tag.get()
        if tag:
            if args:
                formatted_message = message % args
            else:
                formatted_message = message
            self._logger.warning(format_background_log(tag, formatted_message), **kwargs)
        else:
            self._logger.warning(message, *args, **kwargs)

    def error(self, message: str, *args, **kwargs):
        """ERROR 레벨 로그에 태그 적용 (varargs 지원)"""
        tag = _current_tag.get()
        if tag:
            if args:
                formatted_message = message % args
            else:
                formatted_message = message
            self._logger.error(format_background_log(tag, formatted_message), **kwargs)
        else:
            self._logger.error(message, *args, **kwargs)

    def exception(self, message: str, *args, **kwargs):
        """EXCEPTION 레벨 로그에 태그 적용 (스택 트레이스 포함, varargs 지원)"""
        tag = _current_tag.get()
        if tag:
            if args:
                formatted_message = message % args
            else:
                formatted_message = message
            self._logger.exception(format_background_log(tag, formatted_message), **kwargs)
        else:
            self._logger.exception(message, *args, **kwargs)


def tag_background_logger(tag: BackgroundJobTag):
    """
    백그라운드 작업 함수에 로그 태그를 자동으로 적용하는 Thread-Safe 데코레이터

    이 데코레이터를 백그라운드 작업 함수에 적용하면, 함수 내 모든
    app.logger 호출에 지정된 태그가 자동으로 추가됩니다.

    contextvars를 사용하여 스레드별로 독립적인 태그를 관리하므로
    동시 실행되는 여러 백그라운드 작업 간 태그 혼선이 발생하지 않습니다.

    Args:
        tag: 적용할 BackgroundJobTag

    Returns:
        데코레이터 함수

    Usage:
        @tag_background_logger(BackgroundJobTag.AUTO_REBAL)
        def auto_rebalance_all_accounts():
            app = get_flask_app()
            app.logger.info('🔄 작업 시작')  # 자동: [AUTO_REBAL] 🔄 작업 시작
            app.logger.debug('진행 %d/%d', 5, 10)  # varargs 지원
            # ... 로직 ...
            app.logger.info('✅ 작업 완료')  # 자동: [AUTO_REBAL] ✅ 작업 완료

    Features:
        - Thread-safe: 동시 실행 작업 간 태그 혼합 없음
        - Python varargs 지원: logger.debug('msg %s', arg) 동작
        - 예외 발생 시에도 태그 자동 복원 (finally 블록)
        - @wraps로 원본 함수 메타데이터 보존 (디버깅 용이)

    Note:
        - Phase 2: SQLAlchemyJobStore pickle 직렬화 호환성을 위해 함수 시그니처 변경
        - 함수 형태: 파라미터 없는 func() 형태 (get_flask_app()으로 앱 조회)
        - 기존 func(app) 패턴은 Phase 1에서 사용됨 (pickle 비호환)

    Technical Details:
        - contextvars.ContextVar를 사용한 thread-local 태그 저장
        - 각 스레드는 독립적인 태그 컨텍스트 유지
        - APScheduler 환경에서 동시 실행 작업 간 격리 보장

    @FEAT:background-log-tagging @COMP:util @TYPE:helper
    """
    def decorator(func):
        @wraps(func)
        def wrapper():
            # Thread-local 컨텍스트에 태그 설정
            token = _current_tag.set(tag)
            try:
                return func()
            finally:
                # 예외 발생 시에도 태그 복원 보장
                _current_tag.reset(token)
        return wrapper
    return decorator
