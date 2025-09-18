"""
보안 권한 검증 서비스
서비스 간 호출 및 리소스 접근 권한 검증
"""

import logging
from typing import Dict, Any, Optional, List
from functools import wraps
from flask import g, request
from flask_login import current_user
from app.models import Account, User
from app import db

logger = logging.getLogger(__name__)


class SecurityService:
    """통합 보안 권한 검증 서비스"""

    def __init__(self):
        self.service_permissions = {
            'exchange_service': ['create_order', 'cancel_order', 'fetch_balance'],
            'trading_service': ['execute_trade', 'stop_trade'],
            'position_service': ['update_position', 'close_position'],
            'order_service': ['create_order', 'cancel_order']
        }

    def validate_account_access(self, account: Account, user_id: int) -> bool:
        """
        계정 접근 권한 검증

        Args:
            account: 접근하려는 계정
            user_id: 요청하는 사용자 ID

        Returns:
            bool: 접근 권한 여부
        """
        try:
            if not account:
                logger.warning(f"계정 접근 검증 실패: 계정이 None - 사용자 ID: {user_id}")
                return False

            if not user_id:
                logger.warning(f"계정 접근 검증 실패: 사용자 ID가 None - 계정 ID: {account.id}")
                return False

            # 계정 소유권 확인
            if account.user_id != user_id:
                logger.warning(f"계정 접근 권한 없음 - 계정 ID: {account.id}, 소유자: {account.user_id}, 요청자: {user_id}")
                return False

            # 계정 활성화 상태 확인
            if not account.is_active:
                logger.warning(f"비활성화된 계정 접근 시도 - 계정 ID: {account.id}, 사용자 ID: {user_id}")
                return False

            logger.debug(f"계정 접근 권한 확인됨 - 계정 ID: {account.id}, 사용자 ID: {user_id}")
            return True

        except Exception as e:
            logger.error(f"계정 접근 권한 검증 중 오류: {e}")
            return False

    def validate_trading_permission(self, account: Account, symbol: str, user_id: int) -> bool:
        """
        거래 권한 검증

        Args:
            account: 거래에 사용할 계정
            symbol: 거래 심볼
            user_id: 요청하는 사용자 ID

        Returns:
            bool: 거래 권한 여부
        """
        try:
            # 기본 계정 접근 권한 확인
            if not self.validate_account_access(account, user_id):
                return False

            # 사용자 활성화 상태 확인
            user = User.query.get(user_id)
            if not user or not user.is_active:
                logger.warning(f"비활성화된 사용자의 거래 시도 - 사용자 ID: {user_id}")
                return False

            # 테스트넷 계정은 추가 제한 없음
            if account.is_testnet:
                logger.debug(f"테스트넷 거래 권한 확인됨 - 계정 ID: {account.id}, 심볼: {symbol}")
                return True

            # 메인넷 거래의 경우 추가 검증 (필요시 확장)
            logger.debug(f"거래 권한 확인됨 - 계정 ID: {account.id}, 심볼: {symbol}, 사용자 ID: {user_id}")
            return True

        except Exception as e:
            logger.error(f"거래 권한 검증 중 오류: {e}")
            return False

    def validate_service_permission(self, service_name: str, operation: str,
                                   context: Optional[Dict] = None,
                                   require_authentication: bool = True) -> bool:
        """
        서비스 간 호출 권한 검증 - 강화된 인증 요구

        Args:
            service_name: 호출하려는 서비스명
            operation: 수행하려는 작업
            context: 추가 컨텍스트 정보
            require_authentication: 인증 필수 여부 (기본값: True)

        Returns:
            bool: 권한 여부
        """
        try:
            # 허용된 서비스 확인
            if service_name not in self.service_permissions:
                logger.warning(f"허용되지 않은 서비스 호출: {service_name}")
                return False

            # 허용된 작업 확인
            allowed_operations = self.service_permissions[service_name]
            if operation not in allowed_operations:
                logger.warning(f"허용되지 않은 작업: {service_name}.{operation}")
                return False

            # 내부 서비스 호출 허용 목록 (인증 불필요)
            internal_services = {'health_check', 'system_monitor', 'batch_processor', 'migration_monitor'}
            if not require_authentication and service_name in internal_services:
                logger.debug(f"내부 서비스 호출 허용: {service_name}.{operation}")
                return True

            # 🔒 강화된 인증 검증
            if require_authentication:
                # Flask 컨텍스트 확인
                from flask import has_request_context
                if not has_request_context():
                    logger.warning(f"비정상적인 컨텍스트에서 서비스 호출: {service_name}.{operation}")
                    return False

                # 사용자 인증 상태 강제 확인
                if not hasattr(current_user, 'id') or not current_user.is_authenticated:
                    logger.warning(f"인증되지 않은 서비스 호출 시도: {service_name}.{operation}")
                    return False

                # 사용자 활성화 상태 확인
                user = User.query.get(current_user.id)
                if not user or not user.is_active:
                    logger.warning(f"비활성화된 사용자의 서비스 호출: {current_user.id}")
                    return False

            logger.debug(f"서비스 권한 확인됨 - 서비스: {service_name}, 작업: {operation}")
            return True

        except Exception as e:
            logger.error(f"서비스 권한 검증 중 오류: {e}")
            return False

    def get_user_accounts(self, user_id: int) -> List[Account]:
        """
        사용자의 접근 가능한 계정 목록 조회

        Args:
            user_id: 사용자 ID

        Returns:
            List[Account]: 접근 가능한 계정 목록
        """
        try:
            accounts = Account.query.filter_by(user_id=user_id, is_active=True).all()
            logger.debug(f"사용자 {user_id}의 활성 계정 {len(accounts)}개 조회됨")
            return accounts

        except Exception as e:
            logger.error(f"사용자 계정 조회 중 오류: {e}")
            return []

    def log_security_event(self, event_type: str, details: Dict[str, Any]):
        """
        보안 이벤트 로깅 - Flask 컨텍스트 안전 처리

        Args:
            event_type: 이벤트 유형 (access_denied, permission_granted 등)
            details: 상세 정보
        """
        try:
            # Flask 컨텍스트 안전 확인
            from flask import has_request_context
            from datetime import datetime

            log_data = {
                'event_type': event_type,
                'timestamp': datetime.utcnow().isoformat(),
                **details
            }

            # 사용자 정보 안전 추출
            try:
                if hasattr(current_user, 'id') and current_user.is_authenticated:
                    log_data['user_id'] = current_user.id
            except RuntimeError:
                log_data['user_id'] = 'context_unavailable'

            # Request 정보 안전 추출
            if has_request_context():
                try:
                    log_data['ip_address'] = request.remote_addr
                    log_data['user_agent'] = request.headers.get('User-Agent')
                    log_data['endpoint'] = request.endpoint
                    log_data['method'] = request.method
                except Exception as e:
                    log_data['request_error'] = str(e)
            else:
                log_data['context'] = 'no_request_context'

            if event_type == 'access_denied':
                logger.warning(f"🚫 보안 이벤트: {log_data}")
            else:
                logger.info(f"🔐 보안 이벤트: {log_data}")

        except Exception as e:
            # 최후의 안전망
            logger.error(f"보안 이벤트 로깅 중 치명적 오류: {e}")
            logger.warning(f"🚫 [FALLBACK] 보안 이벤트 [{event_type}]: {details.get('reason', 'unknown')}")


# 전역 보안 서비스 인스턴스
security_service = SecurityService()


# === 데코레이터 함수들 ===

def require_account_access(account_param='account', allow_multiple=False):
    """
    계정 접근 권한이 필요한 메서드에 적용하는 데코레이터 - 다중 계정 지원

    Args:
        account_param: Account 객체가 전달되는 파라미터명
        allow_multiple: 다중 계정 허용 여부
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                # Account 객체 찾기 (단일 또는 다중)
                accounts = []

                if account_param in kwargs:
                    account_value = kwargs[account_param]
                    if isinstance(account_value, list):
                        if not allow_multiple:
                            raise ValueError(f"다중 계정이 허용되지 않는 함수: {func.__name__}")
                        accounts = [acc for acc in account_value if isinstance(acc, Account)]
                    elif isinstance(account_value, Account):
                        accounts = [account_value]

                # args에서 Account 객체 찾기
                if not accounts:
                    for arg in args:
                        if isinstance(arg, Account):
                            accounts = [arg]
                            break
                        elif isinstance(arg, list) and allow_multiple:
                            accounts = [item for item in arg if isinstance(item, Account)]
                            if accounts:
                                break

                if not accounts:
                    security_service.log_security_event('access_denied', {
                        'reason': 'account_not_found',
                        'function': func.__name__
                    })
                    raise ValueError(f"Account 객체를 찾을 수 없습니다: {func.__name__}")

                # 현재 사용자 ID 확인
                user_id = None
                if hasattr(current_user, 'id') and current_user.is_authenticated:
                    user_id = current_user.id

                if not user_id:
                    security_service.log_security_event('access_denied', {
                        'reason': 'user_not_authenticated',
                        'function': func.__name__,
                        'account_count': len(accounts)
                    })
                    raise ValueError(f"인증되지 않은 사용자: {func.__name__}")

                # 모든 계정에 대한 권한 검증
                unauthorized_accounts = []
                for account in accounts:
                    if not security_service.validate_account_access(account, user_id):
                        unauthorized_accounts.append(account.id)

                if unauthorized_accounts:
                    security_service.log_security_event('access_denied', {
                        'reason': 'multi_account_access_denied',
                        'function': func.__name__,
                        'unauthorized_accounts': unauthorized_accounts,
                        'user_id': user_id
                    })
                    raise PermissionError(f"다음 계정들에 대한 접근 권한 없음: {unauthorized_accounts}")

                # 모든 권한 확인됨
                security_service.log_security_event('permission_granted', {
                    'function': func.__name__,
                    'account_ids': [acc.id for acc in accounts],
                    'user_id': user_id,
                    'multi_account': len(accounts) > 1
                })

                return func(*args, **kwargs)

            except (ValueError, PermissionError):
                raise  # 권한 관련 예외는 다시 발생
            except Exception as e:
                logger.error(f"다중 계정 접근 권한 데코레이터 오류 ({func.__name__}): {e}")
                raise

        return wrapper
    return decorator


def require_trading_permission(account_param='account', symbol_param='symbol'):
    """
    거래 권한이 필요한 메서드에 적용하는 데코레이터

    Args:
        account_param: Account 객체가 전달되는 파라미터명
        symbol_param: 거래 심볼이 전달되는 파라미터명
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                # Account 객체와 symbol 찾기
                account = kwargs.get(account_param)
                symbol = kwargs.get(symbol_param, 'UNKNOWN')

                if not account:
                    security_service.log_security_event('access_denied', {
                        'reason': 'trading_account_not_found',
                        'function': func.__name__
                    })
                    raise ValueError(f"거래 계정을 찾을 수 없습니다: {func.__name__}")

                # 현재 사용자 ID 확인
                user_id = None
                if hasattr(current_user, 'id') and current_user.is_authenticated:
                    user_id = current_user.id

                if not user_id:
                    security_service.log_security_event('access_denied', {
                        'reason': 'trading_user_not_authenticated',
                        'function': func.__name__,
                        'account_id': account.id,
                        'symbol': symbol
                    })
                    raise ValueError(f"인증되지 않은 사용자의 거래 시도: {func.__name__}")

                # 거래 권한 검증
                if not security_service.validate_trading_permission(account, symbol, user_id):
                    security_service.log_security_event('access_denied', {
                        'reason': 'trading_permission_denied',
                        'function': func.__name__,
                        'account_id': account.id,
                        'symbol': symbol,
                        'user_id': user_id
                    })
                    raise PermissionError(f"거래 권한이 없습니다: {func.__name__}")

                # 권한 확인됨, 원래 함수 실행
                security_service.log_security_event('permission_granted', {
                    'function': func.__name__,
                    'account_id': account.id,
                    'symbol': symbol,
                    'user_id': user_id,
                    'action': 'trading'
                })
                return func(*args, **kwargs)

            except (ValueError, PermissionError):
                raise  # 권한 관련 예외는 다시 발생
            except Exception as e:
                logger.error(f"거래 권한 데코레이터 오류 ({func.__name__}): {e}")
                raise

        return wrapper
    return decorator