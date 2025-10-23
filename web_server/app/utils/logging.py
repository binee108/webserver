# @FEAT:background-log-tagging @COMP:util @TYPE:helper
"""
백그라운드 작업 로깅 유틸리티

백그라운드 작업의 로그를 일관되게 포맷팅하기 위한 헬퍼 함수를 제공합니다.
모든 백그라운드 작업은 format_background_log()를 사용하여 태그를 포함한
로그를 남겨야 하며, 이를 통해 admin/system 페이지에서 작업별 로그를
명확하게 필터링할 수 있습니다.

Usage:
    from app.utils.logging import format_background_log
    from app.constants import BackgroundJobTag

    logger.info(format_background_log(BackgroundJobTag.AUTO_REBAL, "작업 시작"))
    # Output: [AUTO_REBAL] 작업 시작

태그 목록: app/constants.py의 BackgroundJobTag 참조

@FEAT:background-log-tagging @COMP:util @TYPE:helper
"""
from app.constants import BackgroundJobTag


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
