# @FEAT:framework @COMP:util @TYPE:helper
"""
로깅 보안 유틸리티
민감정보 자동 탐지 및 마스킹
"""

import re
import logging
import json
from typing import Any, Dict, List, Optional, Union
from functools import lru_cache
from datetime import datetime
import threading

# 민감정보 탐지 패턴들
SENSITIVE_PATTERNS = {
    'CRITICAL': {
        'api_key': re.compile(r'(["\']?(?:api_?key|apikey|access_?key)["\']?\s*[:=]\s*["\']?)([a-zA-Z0-9]{20,})["\']?', re.IGNORECASE),
        'secret_key': re.compile(r'(["\']?(?:secret_?key|secretkey|private_?key)["\']?\s*[:=]\s*["\']?)([a-zA-Z0-9+/]{20,})["\']?', re.IGNORECASE),
        'password': re.compile(r'(["\']?password["\']?\s*[:=]\s*["\']?)([^"\']{4,})["\']?', re.IGNORECASE),
    },
    'HIGH': {
        'webhook_token': re.compile(r'(["\']?(?:webhook_?token|token)["\']?\s*[:=]\s*["\']?)([a-zA-Z0-9_-]{16,})["\']?', re.IGNORECASE),
        'bearer_token': re.compile(r'(Bearer\s+)([a-zA-Z0-9._-]{20,})', re.IGNORECASE),
        'telegram_token': re.compile(r'(["\']?(?:telegram_?(?:bot_)?token|bot_?token)["\']?\s*[:=]\s*["\']?)(\d{8,}:[a-zA-Z0-9_-]{35})["\']?', re.IGNORECASE),
    },
    'MEDIUM': {
        'user_id': re.compile(r'(["\']?user_?id["\']?\s*[:=]\s*["\']?)(\d{1,10})["\']?', re.IGNORECASE),
        'telegram_chat_id': re.compile(r'(["\']?(?:chat_?id|telegram_?id)["\']?\s*[:=]\s*["\']?)(-?\d{8,})["\']?', re.IGNORECASE),
        'account_id': re.compile(r'(["\']?account_?id["\']?\s*[:=]\s*["\']?)(\d{1,10})["\']?', re.IGNORECASE),
    },
    'LOW': {
        'price': re.compile(r'(["\']?(?:price|amount|quantity|value)["\']?\s*[:=]\s*["\']?)(\d+\.?\d*)["\']?', re.IGNORECASE),
        'ip_address': re.compile(r'(\b(?:ip|address)\s*[:=]\s*["\']?)(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})["\']?', re.IGNORECASE),
    }
}


class LoggingSecurity:
    """로깅 보안 관리자"""

    def __init__(self):
        self.cache = {}
        self.cache_lock = threading.Lock()
        self.max_cache_size = 1000
        self.masking_enabled = True

    @lru_cache(maxsize=100)
    def _get_mask_pattern(self, sensitivity: str, length: int) -> str:
        """민감도와 길이에 따른 마스킹 패턴 반환"""
        if sensitivity == 'CRITICAL':
            return '****'
        elif sensitivity == 'HIGH':
            if length <= 8:
                return '****'
            return f"{length//4*'*'}{'*'*(length-length//4)}"  # 전체의 3/4 마스킹
        elif sensitivity == 'MEDIUM':
            if length <= 4:
                return '*'*length
            if length <= 8:
                return f"{str(length)[0]}{'*'*(length-2)}{str(length)[-1]}" if length > 2 else '*'*length
            return f"{str(length)[:2]}{'*'*(length-4)}{str(length)[-2:]}"
        elif sensitivity == 'LOW':
            if length <= 6:
                return '*'*max(1, length//2)
            return f"{str(length)[:length//3]}{'*'*(length//3)}"
        return '*'*min(4, length)

    def _mask_value(self, value: str, sensitivity: str = 'HIGH') -> str:
        """값 마스킹"""
        if not value or not self.masking_enabled:
            return value

        cache_key = f"{sensitivity}:{hash(value)}"

        with self.cache_lock:
            if cache_key in self.cache:
                return self.cache[cache_key]

            # 캐시 크기 제한
            if len(self.cache) >= self.max_cache_size:
                # 오래된 항목 1/3 제거
                items_to_remove = len(self.cache) // 3
                for key in list(self.cache.keys())[:items_to_remove]:
                    del self.cache[key]

        masked_value = self._get_mask_pattern(sensitivity, len(value))

        with self.cache_lock:
            self.cache[cache_key] = masked_value

        return masked_value

    def mask_sensitive_info(self, text: str) -> str:
        """텍스트에서 민감정보 자동 탐지 및 마스킹"""
        if not text or not self.masking_enabled:
            return text

        # 문자열로 변환
        if not isinstance(text, str):
            text = str(text)

        masked_text = text

        # 민감도별로 패턴 적용
        for sensitivity, patterns in SENSITIVE_PATTERNS.items():
            for pattern_name, pattern in patterns.items():
                def mask_match(match):
                    prefix = match.group(1) if match.lastindex >= 1 else ''
                    sensitive_part = match.group(2) if match.lastindex >= 2 else match.group(0)

                    # CRITICAL 레벨은 완전 마스킹
                    if sensitivity == 'CRITICAL':
                        return f"{prefix}****"

                    # HIGH 레벨은 앞 4자리만 표시
                    elif sensitivity == 'HIGH':
                        if len(sensitive_part) <= 8:
                            return f"{prefix}****"
                        return f"{prefix}{sensitive_part[:4]}****"

                    # MEDIUM 레벨은 앞뒤 일부 표시
                    elif sensitivity == 'MEDIUM':
                        if len(sensitive_part) <= 4:
                            return f"{prefix}****"
                        elif len(sensitive_part) <= 8:
                            return f"{prefix}{sensitive_part[0]}***{sensitive_part[-1]}"
                        return f"{prefix}{sensitive_part[:2]}***{sensitive_part[-2:]}"

                    # LOW 레벨은 부분 마스킹
                    else:
                        if len(sensitive_part) <= 6:
                            return f"{prefix}{sensitive_part[:len(sensitive_part)//2]}***"
                        return f"{prefix}{sensitive_part[:len(sensitive_part)//3]}***"

                masked_text = pattern.sub(mask_match, masked_text)

        return masked_text

    def safe_log_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """딕셔너리 데이터의 안전한 로깅 버전 생성"""
        if not isinstance(data, dict):
            return self.mask_sensitive_info(str(data))

        safe_data = {}
        for key, value in data.items():
            # 키 이름으로 민감도 판단
            key_lower = key.lower()

            if any(sensitive_key in key_lower for sensitive_key in ['api', 'secret', 'password', 'key']):
                safe_data[key] = '****'
            elif any(sensitive_key in key_lower for sensitive_key in ['token']):
                if isinstance(value, str) and len(value) > 8:
                    safe_data[key] = f"{value[:4]}****"
                else:
                    safe_data[key] = '****'
            elif isinstance(value, dict):
                safe_data[key] = self.safe_log_dict(value)
            elif isinstance(value, list):
                safe_data[key] = [self.safe_log_dict(item) if isinstance(item, dict) else self.mask_sensitive_info(str(item)) for item in value]
            else:
                safe_data[key] = self.mask_sensitive_info(str(value)) if value is not None else None

        return safe_data

    def format_safe_message(self, message: str, *args, **kwargs) -> str:
        """안전한 로그 메시지 포맷팅"""
        try:
            # args가 있는 경우 안전하게 포맷팅
            if args:
                safe_args = []
                for arg in args:
                    if isinstance(arg, dict):
                        safe_args.append(self.safe_log_dict(arg))
                    else:
                        safe_args.append(self.mask_sensitive_info(str(arg)))
                message = message % tuple(safe_args)

            # kwargs가 있는 경우 안전하게 포맷팅
            if kwargs:
                safe_kwargs = self.safe_log_dict(kwargs)
                message = message.format(**safe_kwargs)

            return self.mask_sensitive_info(message)
        except Exception as e:
            # 포맷팅 실패 시 원본 메시지에 마스킹만 적용
            return self.mask_sensitive_info(str(message))


class SecureLogger:
    """안전한 로거 래퍼"""

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.security = LoggingSecurity()
        self._original_logger = logger

    def _log(self, level: int, message: str, *args, **kwargs):
        """안전한 로깅 실행"""
        try:
            # 메시지 안전하게 처리
            safe_message = self.security.format_safe_message(message, *args)

            # extra 정보가 있다면 안전하게 처리
            extra = kwargs.pop('extra', {})
            if extra:
                safe_extra = self.security.safe_log_dict(extra)
                kwargs['extra'] = safe_extra

            # 로깅 실행
            self.logger.log(level, safe_message, **kwargs)

        except Exception as e:
            # 로깅 실패 시 최소한의 정보라도 기록
            self.logger.error(f"로깅 보안 처리 중 오류: {e}")
            self.logger.log(level, "[MASKED] 민감정보 마스킹 중 오류 발생")

    def debug(self, message: str, *args, **kwargs):
        """DEBUG 레벨 안전 로깅"""
        self._log(logging.DEBUG, message, *args, **kwargs)

    def info(self, message: str, *args, **kwargs):
        """INFO 레벨 안전 로깅"""
        self._log(logging.INFO, message, *args, **kwargs)

    def warning(self, message: str, *args, **kwargs):
        """WARNING 레벨 안전 로깅"""
        self._log(logging.WARNING, message, *args, **kwargs)

    def error(self, message: str, *args, **kwargs):
        """ERROR 레벨 안전 로깅"""
        self._log(logging.ERROR, message, *args, **kwargs)

    def critical(self, message: str, *args, **kwargs):
        """CRITICAL 레벨 안전 로깅"""
        self._log(logging.CRITICAL, message, *args, **kwargs)

    def log_security_event(self, event_type: str, details: Dict[str, Any]):
        """보안 이벤트 전용 로깅"""
        safe_details = self.security.safe_log_dict(details)
        self.info(f"🔐 보안 이벤트 [{event_type}]: {safe_details}")

    def log_api_call(self, endpoint: str, method: str, params: Dict[str, Any] = None, response: Dict[str, Any] = None):
        """API 호출 전용 로깅"""
        log_data = {
            'endpoint': endpoint,
            'method': method,
            'timestamp': datetime.utcnow().isoformat()
        }

        if params:
            log_data['params'] = self.security.safe_log_dict(params)

        if response:
            log_data['response'] = self.security.safe_log_dict(response)

        self.info(f"📡 API 호출: {log_data}")

    def __getattr__(self, name):
        """다른 logger 메서드들은 원본 logger로 위임"""
        return getattr(self._original_logger, name)


# 전역 보안 유틸리티
_security_instance = LoggingSecurity()

def get_secure_logger(name: str) -> SecureLogger:
    """모듈별 안전한 로거 반환"""
    original_logger = logging.getLogger(name)
    return SecureLogger(original_logger)

def mask_sensitive_info(text: str) -> str:
    """단순 민감정보 마스킹 함수"""
    return _security_instance.mask_sensitive_info(text)

def safe_log_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """딕셔너리 안전 로깅 함수"""
    return _security_instance.safe_log_dict(data)

# 기존 logger를 안전한 logger로 교체하는 유틸리티
def wrap_existing_logger(logger: logging.Logger) -> SecureLogger:
    """기존 logger를 SecureLogger로 래핑"""
    return SecureLogger(logger)
