# @FEAT:framework @COMP:util @TYPE:helper
"""
표준화된 API 응답 포맷터
일관된 응답 구조 및 에러 처리
"""

from typing import Dict, Any, Optional, Union, List
from flask import jsonify
from datetime import datetime
import uuid


class ErrorCode:
    """표준 에러 코드 상수"""

    # 일반적인 에러 (1000번대)
    UNKNOWN_ERROR = "E1000"
    INTERNAL_SERVER_ERROR = "E1001"
    SERVICE_UNAVAILABLE = "E1002"
    TIMEOUT_ERROR = "E1003"

    # 요청 관련 에러 (2000번대)
    BAD_REQUEST = "E2000"
    INVALID_JSON = "E2001"
    MISSING_REQUIRED_FIELD = "E2002"
    INVALID_PARAMETER = "E2003"
    INVALID_FORMAT = "E2004"

    # 인증/권한 에러 (3000번대)
    UNAUTHORIZED = "E3000"
    FORBIDDEN = "E3001"
    ACCESS_DENIED = "E3002"
    INVALID_TOKEN = "E3003"
    TOKEN_EXPIRED = "E3004"
    ACCOUNT_ACCESS_DENIED = "E3005"
    TRADING_PERMISSION_DENIED = "E3006"

    # 리소스 관련 에러 (4000번대)
    NOT_FOUND = "E4000"
    RESOURCE_NOT_FOUND = "E4001"
    USER_NOT_FOUND = "E4002"
    ACCOUNT_NOT_FOUND = "E4003"
    STRATEGY_NOT_FOUND = "E4004"

    # 비즈니스 로직 에러 (5000번대)
    BUSINESS_LOGIC_ERROR = "E5000"
    TRADING_ERROR = "E5001"
    INSUFFICIENT_BALANCE = "E5002"
    INVALID_ORDER = "E5003"
    MARKET_CLOSED = "E5004"
    RATE_LIMIT_EXCEEDED = "E5005"
    EXCHANGE_ERROR = "E5006"
    WEBHOOK_PROCESSING_ERROR = "E5007"

    # 검증 에러 (6000번대)
    VALIDATION_ERROR = "E6000"
    SCHEMA_VALIDATION_ERROR = "E6001"
    BUSINESS_VALIDATION_ERROR = "E6002"
    DATA_INTEGRITY_ERROR = "E6003"


class ErrorType:
    """에러 타입 분류"""

    SYSTEM = "system"
    BUSINESS = "business"
    VALIDATION = "validation"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    RESOURCE = "resource"


# 에러 코드와 HTTP 상태 코드 매핑
ERROR_HTTP_STATUS_MAPPING = {
    # 1000번대: 서버 에러 (500)
    ErrorCode.UNKNOWN_ERROR: 500,
    ErrorCode.INTERNAL_SERVER_ERROR: 500,
    ErrorCode.SERVICE_UNAVAILABLE: 503,
    ErrorCode.TIMEOUT_ERROR: 504,

    # 2000번대: 클라이언트 에러 (400)
    ErrorCode.BAD_REQUEST: 400,
    ErrorCode.INVALID_JSON: 400,
    ErrorCode.MISSING_REQUIRED_FIELD: 400,
    ErrorCode.INVALID_PARAMETER: 400,
    ErrorCode.INVALID_FORMAT: 400,

    # 3000번대: 인증/권한 에러 (401, 403)
    ErrorCode.UNAUTHORIZED: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.ACCESS_DENIED: 403,
    ErrorCode.INVALID_TOKEN: 401,
    ErrorCode.TOKEN_EXPIRED: 401,
    ErrorCode.ACCOUNT_ACCESS_DENIED: 403,
    ErrorCode.TRADING_PERMISSION_DENIED: 403,

    # 4000번대: 리소스 에러 (404)
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.RESOURCE_NOT_FOUND: 404,
    ErrorCode.USER_NOT_FOUND: 404,
    ErrorCode.ACCOUNT_NOT_FOUND: 404,
    ErrorCode.STRATEGY_NOT_FOUND: 404,

    # 5000번대: 비즈니스 로직 에러 (422)
    ErrorCode.BUSINESS_LOGIC_ERROR: 422,
    ErrorCode.TRADING_ERROR: 422,
    ErrorCode.INSUFFICIENT_BALANCE: 422,
    ErrorCode.INVALID_ORDER: 422,
    ErrorCode.MARKET_CLOSED: 422,
    ErrorCode.RATE_LIMIT_EXCEEDED: 429,
    ErrorCode.EXCHANGE_ERROR: 422,
    ErrorCode.WEBHOOK_PROCESSING_ERROR: 422,

    # 6000번대: 검증 에러 (422)
    ErrorCode.VALIDATION_ERROR: 422,
    ErrorCode.SCHEMA_VALIDATION_ERROR: 422,
    ErrorCode.BUSINESS_VALIDATION_ERROR: 422,
    ErrorCode.DATA_INTEGRITY_ERROR: 422,
}

# 에러 코드와 타입 매핑
ERROR_TYPE_MAPPING = {
    ErrorCode.UNKNOWN_ERROR: ErrorType.SYSTEM,
    ErrorCode.INTERNAL_SERVER_ERROR: ErrorType.SYSTEM,
    ErrorCode.SERVICE_UNAVAILABLE: ErrorType.SYSTEM,
    ErrorCode.TIMEOUT_ERROR: ErrorType.SYSTEM,

    ErrorCode.BAD_REQUEST: ErrorType.VALIDATION,
    ErrorCode.INVALID_JSON: ErrorType.VALIDATION,
    ErrorCode.MISSING_REQUIRED_FIELD: ErrorType.VALIDATION,
    ErrorCode.INVALID_PARAMETER: ErrorType.VALIDATION,
    ErrorCode.INVALID_FORMAT: ErrorType.VALIDATION,

    ErrorCode.UNAUTHORIZED: ErrorType.AUTHENTICATION,
    ErrorCode.FORBIDDEN: ErrorType.AUTHORIZATION,
    ErrorCode.ACCESS_DENIED: ErrorType.AUTHORIZATION,
    ErrorCode.INVALID_TOKEN: ErrorType.AUTHENTICATION,
    ErrorCode.TOKEN_EXPIRED: ErrorType.AUTHENTICATION,
    ErrorCode.ACCOUNT_ACCESS_DENIED: ErrorType.AUTHORIZATION,
    ErrorCode.TRADING_PERMISSION_DENIED: ErrorType.AUTHORIZATION,

    ErrorCode.NOT_FOUND: ErrorType.RESOURCE,
    ErrorCode.RESOURCE_NOT_FOUND: ErrorType.RESOURCE,
    ErrorCode.USER_NOT_FOUND: ErrorType.RESOURCE,
    ErrorCode.ACCOUNT_NOT_FOUND: ErrorType.RESOURCE,
    ErrorCode.STRATEGY_NOT_FOUND: ErrorType.RESOURCE,

    ErrorCode.BUSINESS_LOGIC_ERROR: ErrorType.BUSINESS,
    ErrorCode.TRADING_ERROR: ErrorType.BUSINESS,
    ErrorCode.INSUFFICIENT_BALANCE: ErrorType.BUSINESS,
    ErrorCode.INVALID_ORDER: ErrorType.BUSINESS,
    ErrorCode.MARKET_CLOSED: ErrorType.BUSINESS,
    ErrorCode.RATE_LIMIT_EXCEEDED: ErrorType.BUSINESS,
    ErrorCode.EXCHANGE_ERROR: ErrorType.BUSINESS,
    ErrorCode.WEBHOOK_PROCESSING_ERROR: ErrorType.BUSINESS,

    ErrorCode.VALIDATION_ERROR: ErrorType.VALIDATION,
    ErrorCode.SCHEMA_VALIDATION_ERROR: ErrorType.VALIDATION,
    ErrorCode.BUSINESS_VALIDATION_ERROR: ErrorType.VALIDATION,
    ErrorCode.DATA_INTEGRITY_ERROR: ErrorType.VALIDATION,
}


class ResponseFormatter:
    """API 응답 포맷터"""

    @staticmethod
    def success(data: Any = None, message: str = "Success", meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """성공 응답 생성"""
        response = {
            "success": True,
            "message": message,
            "data": data,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "request_id": str(uuid.uuid4())[:8]
        }

        if meta:
            response["meta"] = meta

        return response

    @staticmethod
    def error(
        error_code: str,
        message: str,
        details: Optional[Union[str, Dict[str, Any], List[str]]] = None,
        field_errors: Optional[Dict[str, str]] = None,
        request_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """에러 응답 생성"""

        response = {
            "success": False,
            "error": {
                "code": error_code,
                "type": ERROR_TYPE_MAPPING.get(error_code, ErrorType.SYSTEM),
                "message": message,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "request_id": request_id or str(uuid.uuid4())[:8]
            }
        }

        if details:
            response["error"]["details"] = details

        if field_errors:
            response["error"]["field_errors"] = field_errors

        return response

    @staticmethod
    def paginated_success(
        data: List[Any],
        page: int,
        per_page: int,
        total: int,
        message: str = "Success"
    ) -> Dict[str, Any]:
        """페이지네이션이 포함된 성공 응답"""
        meta = {
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "total_pages": (total + per_page - 1) // per_page,
                "has_next": page * per_page < total,
                "has_prev": page > 1
            }
        }

        return ResponseFormatter.success(data=data, message=message, meta=meta)


def create_response(success: bool = True, **kwargs) -> tuple:
    """Flask Response 튜플 생성 (JSON, HTTP Status Code)"""

    if success:
        response_data = ResponseFormatter.success(**kwargs)
        return jsonify(response_data), 200
    else:
        error_code = kwargs.get('error_code', ErrorCode.UNKNOWN_ERROR)
        response_data = ResponseFormatter.error(**kwargs)
        http_status = ERROR_HTTP_STATUS_MAPPING.get(error_code, 500)
        return jsonify(response_data), http_status


def create_error_response(
    error_code: str,
    message: str,
    details: Optional[Union[str, Dict[str, Any], List[str]]] = None,
    field_errors: Optional[Dict[str, str]] = None
) -> tuple:
    """에러 응답 생성 단축 함수"""

    response_data = ResponseFormatter.error(
        error_code=error_code,
        message=message,
        details=details,
        field_errors=field_errors
    )

    http_status = ERROR_HTTP_STATUS_MAPPING.get(error_code, 500)
    return jsonify(response_data), http_status


def create_success_response(
    data: Any = None,
    message: str = "Success",
    meta: Optional[Dict[str, Any]] = None
) -> tuple:
    """성공 응답 생성 단축 함수"""

    response_data = ResponseFormatter.success(data=data, message=message, meta=meta)
    return jsonify(response_data), 200


# 예외를 표준 응답으로 변환하는 함수들
def exception_to_error_response(exception: Exception) -> tuple:
    """예외를 표준 에러 응답으로 변환"""

    # 권한 관련 예외
    if isinstance(exception, PermissionError):
        return create_error_response(
            error_code=ErrorCode.ACCESS_DENIED,
            message="접근 권한이 없습니다",
            details=str(exception)
        )

    # 값 오류
    elif isinstance(exception, ValueError):
        return create_error_response(
            error_code=ErrorCode.INVALID_PARAMETER,
            message="잘못된 매개변수입니다",
            details=str(exception)
        )

    # 키 오류 (리소스 없음)
    elif isinstance(exception, KeyError):
        return create_error_response(
            error_code=ErrorCode.RESOURCE_NOT_FOUND,
            message="요청한 리소스를 찾을 수 없습니다",
            details=str(exception)
        )

    # 파일 없음
    elif isinstance(exception, FileNotFoundError):
        return create_error_response(
            error_code=ErrorCode.RESOURCE_NOT_FOUND,
            message="파일을 찾을 수 없습니다",
            details=str(exception)
        )

    # 기타 모든 예외
    else:
        return create_error_response(
            error_code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="내부 서버 오류가 발생했습니다",
            details=str(exception)
        )


# 레거시 응답 형식 호환성 함수들
def legacy_success_response(data: Any = None, message: str = "Success") -> Dict[str, Any]:
    """기존 형식의 성공 응답 (호환성용)"""
    return {
        "success": True,
        "message": message,
        "data": data
    }


def legacy_error_response(error: str, details: Optional[str] = None) -> Dict[str, Any]:
    """기존 형식의 에러 응답 (호환성용)"""
    response = {
        "success": False,
        "error": error
    }

    if details:
        response["details"] = details

    return response


# 레거시 관련 함수들은 제거됨 - 신규 형식만 사용
