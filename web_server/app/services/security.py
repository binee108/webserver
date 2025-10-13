"""
통합 보안 서비스

Security + Account 관련 모든 기능 통합
1인 사용자를 위한 단순하고 안전한 보안 관리 서비스입니다.
"""

import logging
import secrets
import threading
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta, date
from decimal import Decimal

from flask import request, session, current_app
from flask_login import current_user
from werkzeug.security import generate_password_hash, check_password_hash

from sqlalchemy.orm import selectinload

from app import db
from app.models import User, Account, UserSession, DailyAccountSummary
from app.constants import MarketType
from app.services.exchange import exchange_service
from app.security.encryption import encrypt_value, decrypt_value, is_likely_legacy_hash

logger = logging.getLogger(__name__)


class SecurityError(Exception):
    """보안 관련 오류"""
    pass


class SecurityService:
    """
    통합 보안 서비스

    기존 서비스들 통합:
    - security_service.py
    - account_service.py (부분)
    """

    def __init__(self):
        self.failed_login_attempts = {}
        self.blocked_ips = set()
        self.max_failed_attempts = 5
        self.block_duration = 3600  # 1시간
        logger.info("✅ 통합 보안 서비스 초기화 완료")

    # === 인증 관련 ===

    def authenticate_user(self, username: str, password: str) -> Dict[str, Any]:
        """사용자 인증"""
        try:
            # IP 블록 확인
            client_ip = self._get_client_ip()
            if self._is_ip_blocked(client_ip):
                return {
                    'success': False,
                    'error': 'IP가 차단되었습니다. 나중에 다시 시도해주세요.',
                    'blocked': True
                }

            # 사용자 조회
            user = User.query.filter_by(username=username).first()
            if not user:
                self._record_failed_login(client_ip)
                return {
                    'success': False,
                    'error': '잘못된 사용자명 또는 비밀번호입니다.',
                    'attempts_left': self._get_attempts_left(client_ip)
                }

            # 비밀번호 확인
            if not check_password_hash(user.password_hash, password):
                self._record_failed_login(client_ip)
                return {
                    'success': False,
                    'error': '잘못된 사용자명 또는 비밀번호입니다.',
                    'attempts_left': self._get_attempts_left(client_ip)
                }

            # 성공 시 실패 기록 삭제
            self._clear_failed_login(client_ip)

            # 사용자 세션 생성
            session_token = self._create_user_session(user)

            return {
                'success': True,
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'is_admin': user.is_admin
                },
                'session_token': session_token
            }

        except Exception as e:
            logger.error(f"사용자 인증 실패: {e}")
            return {
                'success': False,
                'error': '인증 중 오류가 발생했습니다.'
            }

    def _create_user_session(self, user: User) -> str:
        """사용자 세션 생성"""
        session_token = secrets.token_urlsafe(32)

        # 기존 세션 무효화
        UserSession.query.filter_by(user_id=user.id).delete()

        # 새 세션 생성
        user_session = UserSession(
            user_id=user.id,
            session_token=session_token,
            ip_address=self._get_client_ip(),
            user_agent=request.headers.get('User-Agent', ''),
            expires_at=datetime.utcnow() + timedelta(days=30)
        )

        db.session.add(user_session)
        db.session.commit()

        return session_token

    def validate_session(self, session_token: str) -> Optional[User]:
        """세션 토큰 검증"""
        try:
            user_session = UserSession.query.filter_by(session_token=session_token).first()

            if not user_session:
                return None

            # 만료 확인
            if user_session.expires_at < datetime.utcnow():
                db.session.delete(user_session)
                db.session.commit()
                return None

            # 세션 갱신
            user_session.last_accessed = datetime.utcnow()
            db.session.commit()

            return user_session.user

        except Exception as e:
            logger.error(f"세션 검증 실패: {e}")
            return None

    def logout_user(self, session_token: str) -> bool:
        """사용자 로그아웃"""
        try:
            user_session = UserSession.query.filter_by(session_token=session_token).first()
            if user_session:
                db.session.delete(user_session)
                db.session.commit()
            return True
        except Exception as e:
            logger.error(f"로그아웃 실패: {e}")
            return False

    # === 권한 관리 ===

    def check_permission(self, user: User, action: str, resource: str = None) -> bool:
        """권한 확인"""
        # 관리자는 모든 권한
        if user.is_admin:
            return True

        # 일반 사용자 권한 규칙
        user_permissions = {
            'view_dashboard': True,
            'manage_strategies': True,
            'manage_accounts': True,
            'view_orders': True,
            'create_orders': True,
            'cancel_orders': True,
            'view_positions': True,
            'manage_settings': False,  # 관리자만
            'view_logs': False,  # 관리자만
            'manage_users': False  # 관리자만
        }

        return user_permissions.get(action, False)

    def require_permission(self, action: str, resource: str = None) -> bool:
        """권한 필수 확인 (데코레이터용)"""
        if not current_user.is_authenticated:
            return False

        return self.check_permission(current_user, action, resource)

    # === 계정 관리 ===

    # @FEAT:account-management @COMP:service @TYPE:core
    def get_user_accounts(self, user_id: int) -> List[Account]:
        """사용자 계정 목록 조회"""
        try:
            logger.info(f"계정 목록 조회 시작: user_id={user_id}")

            # 입력 검증
            if not isinstance(user_id, int) or user_id <= 0:
                logger.error(f"잘못된 user_id: {user_id}")
                raise ValueError(f"유효하지 않은 사용자 ID: {user_id}")

            # 데이터베이스 쿼리 실행 (일일 요약 eager loading)
            accounts = (
                Account.query
                .options(selectinload(Account.daily_summaries))
                .filter_by(user_id=user_id)
                .all()
            )
            logger.info(f"계정 목록 조회 완료: user_id={user_id}, 계정 수={len(accounts)}")

            return accounts

        except ValueError as ve:
            logger.error(f"입력 검증 실패: {ve}")
            raise  # ValueError는 다시 발생시켜 호출자에게 전달
        except Exception as e:
            logger.error(f"데이터베이스 조회 실패: user_id={user_id}, error={str(e)}, type={type(e).__name__}")
            # 데이터베이스 연결 문제 등 복구 불가능한 오류는 빈 리스트 반환
            return []

    # @FEAT:account-management @COMP:service @TYPE:core
    def get_accounts_by_user(self, user_id: int) -> List[Dict[str, Any]]:
        """사용자 계정 목록 조회 (딕셔너리 형태로 반환)"""
        try:
            logger.info(f"계정 딕셔너리 변환 시작: user_id={user_id}")

            # 계정 목록 조회
            accounts = self.get_user_accounts(user_id)
            if not accounts:
                logger.info(f"사용자 계정이 없습니다: user_id={user_id}")
                return []

            result = []
            for account in accounts:
                try:
                    # 각 계정 데이터 안전하게 변환
                    account_dict = {
                        'id': account.id,
                        'name': account.name or '',  # None 값 처리
                        'exchange': account.exchange or '',  # None 값 처리
                        'is_active': bool(account.is_active),  # 안전한 boolean 변환
                        'is_testnet': bool(account.is_testnet),  # 안전한 boolean 변환
                        'created_at': account.created_at.isoformat() if account.created_at else None,
                        'updated_at': account.updated_at.isoformat() if account.updated_at else None
                    }

                    latest_summary = None
                    if account.daily_summaries:
                        latest_summary = max(account.daily_summaries, key=lambda s: s.date)

                    if latest_summary:
                        account_dict['latest_balance'] = float(latest_summary.ending_balance or 0.0)
                        account_dict['latest_balance_date'] = latest_summary.date.isoformat()
                    else:
                        account_dict['latest_balance'] = None
                        account_dict['latest_balance_date'] = None

                    result.append(account_dict)
                    logger.debug(f"계정 변환 완료: account_id={account.id}, name={account.name}")

                except Exception as ae:
                    logger.error(f"계정 데이터 변환 실패: account_id={getattr(account, 'id', 'unknown')}, error={str(ae)}")
                    # 개별 계정 변환 실패해도 다른 계정들은 처리 계속
                    continue

            logger.info(f"계정 딕셔너리 변환 완료: user_id={user_id}, 성공={len(result)}개")
            return result

        except ValueError as ve:
            # 입력 검증 오류는 호출자에게 전달
            logger.error(f"입력 검증 오류: {ve}")
            raise
        except Exception as e:
            logger.error(f"계정 목록 변환 실패: user_id={user_id}, error={str(e)}, type={type(e).__name__}")
            # 예상치 못한 오류 발생 시에만 빈 리스트 반환
            return []

    # @FEAT:account-management @COMP:service @TYPE:helper
    def _convert_balance_map(self, balance_map: Dict[str, Any]) -> Tuple[List[Dict[str, float]], Decimal]:
        """잔고 데이터 맵을 프론트엔드 친화적인 형태로 변환"""
        processed: List[Dict[str, float]] = []
        total_balance = Decimal('0')

        if not balance_map:
            return processed, total_balance

        for asset, balance in balance_map.items():
            try:
                if hasattr(balance, 'free') and hasattr(balance, 'locked'):
                    free = Decimal(balance.free)
                    locked = Decimal(balance.locked)
                elif isinstance(balance, dict):
                    free = Decimal(str(balance.get('free', '0')))
                    locked = Decimal(str(balance.get('locked', '0')))
                else:
                    logger.debug(f"알 수 없는 잔고 형식: asset={asset}, value={balance}")
                    continue

                total = free + locked
                if total <= 0:
                    continue

                processed.append({
                    'asset': asset,
                    'free': float(free),
                    'locked': float(locked),
                    'total': float(total)
                })
                total_balance += total

            except Exception as e:
                logger.warning(f"잔고 데이터 변환 실패: asset={asset}, error={e}")
                continue

        processed.sort(key=lambda item: item['total'], reverse=True)
        return processed, total_balance

    # @FEAT:account-management @COMP:service @TYPE:helper
    def _record_balance_snapshot(self, account: Account, total_balance: Decimal, spot_balance: Decimal = None, futures_balance: Decimal = None) -> DailyAccountSummary:
        """일일 계좌 요약 테이블에 잔고 스냅샷 저장"""
        today = date.today()
        summary = DailyAccountSummary.query.filter_by(account_id=account.id, date=today).first()

        total_float = float(total_balance)
        spot_float = float(spot_balance) if spot_balance is not None else 0.0
        futures_float = float(futures_balance) if futures_balance is not None else 0.0

        if summary is None:
            summary = DailyAccountSummary(
                account_id=account.id,
                date=today,
                starting_balance=total_float,
                ending_balance=total_float,
                spot_balance=spot_float,
                futures_balance=futures_float,
                total_pnl=0.0,
                realized_pnl=0.0,
                unrealized_pnl=0.0,
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=0.0,
                max_drawdown=0.0,
                total_volume=0.0,
                total_fees=0.0
            )
            db.session.add(summary)
        else:
            if summary.starting_balance == 0:
                summary.starting_balance = total_float
            summary.ending_balance = total_float
            summary.spot_balance = spot_float
            summary.futures_balance = futures_float

        return summary

    # @FEAT:account-management @FEAT:exchange-integration @COMP:service @TYPE:integration
    def _collect_account_balances(self, account: Account, persist: bool = True) -> Dict[str, Any]:
        """거래소에서 잔고를 조회하고 필요 시 저장"""
        if not account:
            raise SecurityError('계정을 찾을 수 없습니다.')

        snapshots = []
        aggregate_total = Decimal('0')
        spot_total = Decimal('0')
        futures_total = Decimal('0')
        errors: List[str] = []

        market_types = [
            (MarketType.SPOT_LOWER, 'spot'),
            (MarketType.FUTURES_LOWER, 'futures')
        ]

        for market_key, market_label in market_types:
            try:
                balance_result = exchange_service.fetch_balance(account, market_key)
            except Exception as e:
                logger.error(f"잔고 조회 중 예외 발생: account_id={account.id}, market={market_key}, error={e}")
                errors.append(f"{market_label}: {str(e)}")
                continue

            if not balance_result.get('success'):
                errors.append(f"{market_label}: {balance_result.get('error', '알 수 없는 오류')}")
                continue

            processed, market_total = self._convert_balance_map(balance_result.get('balance'))

            if not processed:
                logger.debug(f"잔고 데이터가 없어 건너뜀: account_id={account.id}, market={market_key}")
                continue

            snapshots.append({
                'market_type': market_key,
                'total_balance': float(market_total),
                'balances': processed
            })
            aggregate_total += market_total

            # Track separate spot and futures balances
            if market_key == MarketType.SPOT_LOWER:
                spot_total = market_total
            elif market_key == MarketType.FUTURES_LOWER:
                futures_total = market_total

        if not snapshots:
            error_message = '잔고 조회에 실패했습니다.'
            if errors:
                error_message += ' ' + '; '.join(errors)
            raise SecurityError(error_message)

        if persist:
            self._record_balance_snapshot(account, aggregate_total, spot_total, futures_total)
            account.updated_at = datetime.utcnow()

        return {
            'total_balance': float(aggregate_total),
            'market_summaries': snapshots,
            'snapshot_at': datetime.utcnow().isoformat() + 'Z'
        }

    # @FEAT:account-management @COMP:service @TYPE:core
    def get_account_by_id(self, account_id: int, user_id: int) -> Optional[Account]:
        """ID로 계정 조회"""
        try:
            return Account.query.filter_by(id=account_id, user_id=user_id).first()
        except Exception as e:
            logger.error(f"계정 조회 실패: {e}")
            return None

    # @FEAT:account-management @COMP:service @TYPE:core @DEPS:exchange-integration
    def test_account_connection(self, account_id: int, user_id: int) -> Dict[str, Any]:
        """계정 연결 테스트 및 잔고 스냅샷 저장"""
        try:
            account = self.get_account_by_id(account_id, user_id)
            if not account:
                return {
                    'success': False,
                    'error': '계정을 찾을 수 없습니다.'
                }

            is_valid, error_message = self._validate_api_credentials(account)
            if not is_valid:
                return {
                    'success': False,
                    'error': error_message
                }

            balance_snapshot = self._collect_account_balances(account, persist=True)
            db.session.commit()

            return {
                'success': True,
                'message': '계정 연결이 정상입니다.',
                'exchange': account.exchange,
                'is_testnet': account.is_testnet,
                **balance_snapshot
            }
        except SecurityError as se:
            logger.error(f"계정 연결 테스트 실패: {se}")
            db.session.rollback()
            return {
                'success': False,
                'error': str(se)
            }
        except Exception as e:
            logger.error(f"계정 연결 테스트 중 예외 발생: {e}")
            db.session.rollback()
            return {
                'success': False,
                'error': '계정 연결 테스트 중 오류가 발생했습니다.'
            }

    # @FEAT:account-management @COMP:service @TYPE:core @DEPS:exchange-integration
    def get_account_balance(self, account_id: int, user_id: int) -> Dict[str, Any]:
        """계정 잔고 조회"""
        account = self.get_account_by_id(account_id, user_id)
        if not account:
            raise SecurityError('계정을 찾을 수 없습니다.')

        is_valid, error_message = self._validate_api_credentials(account)
        if not is_valid:
            raise SecurityError(error_message)

        balance_snapshot = self._collect_account_balances(account, persist=False)
        return balance_snapshot

    # @FEAT:account-management @COMP:service @TYPE:helper
    def refresh_account_balance_async(self, account_id: int) -> None:
        """계좌 잔고 갱신을 비동기로 스케줄링"""
        try:
            app = current_app._get_current_object()
        except RuntimeError:
            logger.warning('어플리케이션 컨텍스트가 없어 잔고 갱신을 스킵합니다.')
            return

        thread = threading.Thread(
            target=self._refresh_account_balance_task,
            args=(app, account_id),
            daemon=True
        )
        thread.start()

    # @FEAT:account-management @COMP:service @TYPE:helper
    def _refresh_account_balance_task(self, app, account_id: int) -> None:
        """백그라운드에서 계좌 잔고를 갱신하는 작업"""
        with app.app_context():
            account = Account.query.get(account_id)
            if not account:
                logger.warning(f'잔고 갱신 실패: 계정 {account_id}를 찾을 수 없습니다.')
                return

            try:
                self._collect_account_balances(account, persist=True)
                db.session.commit()
                logger.info(f'계정 {account_id} 잔고 갱신 완료 (비동기)')
            except SecurityError as se:
                db.session.rollback()
                logger.error(f'계정 {account_id} 잔고 갱신 실패: {se}')
            except Exception as e:
                db.session.rollback()
                logger.error(f'계정 {account_id} 잔고 갱신 중 예외 발생: {e}')

    # @FEAT:account-management @COMP:service @TYPE:core
    def create_account(self, user_id: int, account_data: Dict[str, Any]) -> Dict[str, Any]:
        """거래소 계정 생성"""
        try:
            # 데이터 검증 - public_api/secret_api 필드명 사용
            required_fields = ['name', 'exchange', 'public_api', 'secret_api']
            for field in required_fields:
                if not account_data.get(field):
                    return {
                        'success': False,
                        'error': f'{field} 필드가 필요합니다.'
                    }

            # API 키 암호화 (실제로는 더 강력한 암호화 사용)
            encrypted_public_api = self._encrypt_api_key(account_data['public_api'])
            encrypted_secret_api = self._encrypt_api_key(account_data['secret_api'])

            # 계정 생성
            account = Account(
                user_id=user_id,
                name=account_data['name'],
                exchange=account_data['exchange'],
                public_api=encrypted_public_api,
                secret_api=encrypted_secret_api,
                passphrase=account_data.get('passphrase', ''),
                is_testnet=account_data.get('is_testnet', False),
                is_active=account_data.get('is_active', True)
            )

            db.session.add(account)
            db.session.commit()

            balance_snapshot = None
            balance_error: Optional[str] = None

            # 계좌 생성 직후 잔고를 조회하여 요약 데이터를 준비한다
            try:
                # 새 트랜잭션 컨텍스트에서 잔고 조회 및 저장
                db.session.refresh(account)
                balance_snapshot = self._collect_account_balances(account, persist=True)
                db.session.commit()
            except SecurityError as se:
                db.session.rollback()
                balance_snapshot = None
                balance_error = str(se)
                logger.warning(
                    "계좌 %s(%s) 잔고 초기화 실패: %s",
                    account.id,
                    account.exchange,
                    se
                )
            except Exception as e:
                db.session.rollback()
                balance_snapshot = None
                balance_error = '계좌 잔고 초기화 중 오류가 발생했습니다.'
                logger.error(
                    "계좌 %s(%s) 잔고 초기화 중 예외 발생: %s",
                    account.id,
                    account.exchange,
                    e
                )

            return {
                'success': True,
                'account_id': account.id,
                'name': account.name,
                'exchange': account.exchange,
                'message': '계정이 성공적으로 생성되었습니다.',
                'balance_snapshot': balance_snapshot,
                'balance_error': balance_error
            }

        except Exception as e:
            db.session.rollback()
            logger.error(f"계정 생성 실패: {e}")
            raise SecurityError(f"계정 생성 중 오류가 발생했습니다: {str(e)}")

    # @FEAT:account-management @COMP:service @TYPE:core
    def update_account(self, account_id: int, user_id: int, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """계정 정보 수정"""
        try:
            account = Account.query.filter_by(id=account_id, user_id=user_id).first()
            if not account:
                return {
                    'success': False,
                    'error': '계정을 찾을 수 없습니다.'
                }

            # 업데이트 가능한 필드들
            updatable_fields = ['name', 'is_testnet', 'is_active', 'passphrase']

            for field in updatable_fields:
                if field in update_data:
                    setattr(account, field, update_data[field])

            # API 키 업데이트 (별도 처리)
            if 'public_api' in update_data and update_data['public_api']:
                account.public_api = self._encrypt_api_key(update_data['public_api'])

            if 'secret_api' in update_data and update_data['secret_api']:
                account.secret_api = self._encrypt_api_key(update_data['secret_api'])

            # API 키가 변경된 경우 캐시 무효화
            if 'public_api' in update_data or 'secret_api' in update_data:
                from app.models import Account
                Account.clear_cache(account.id)

                # ExchangeService 클라이언트 캐시도 무효화
                exchange_service.invalidate_account_cache(account.id)

            db.session.commit()

            return {
                'success': True,
                'account_id': account.id,
                'name': account.name,
                'exchange': account.exchange,
                'message': '계정이 성공적으로 수정되었습니다.'
            }

        except Exception as e:
            db.session.rollback()
            logger.error(f"계정 수정 실패: {e}")
            raise SecurityError(f"계정 수정 중 오류가 발생했습니다: {str(e)}")

    # @FEAT:account-management @COMP:service @TYPE:core
    def delete_account(self, account_id: int, user_id: int) -> bool:
        """계정 삭제"""
        try:
            account = Account.query.filter_by(id=account_id, user_id=user_id).first()
            if not account:
                return False

            db.session.delete(account)
            db.session.commit()
            return True

        except Exception as e:
            db.session.rollback()
            logger.error(f"계정 삭제 실패: {e}")
            raise SecurityError(f"계정 삭제 중 오류가 발생했습니다: {str(e)}")

    # === 보안 유틸리티 ===

    # @FEAT:account-management @COMP:service @TYPE:helper
    def _encrypt_api_key(self, api_key: str) -> str:
        """API 키 암호화"""
        return encrypt_value(api_key)

    # @FEAT:account-management @COMP:service @TYPE:helper
    def _decrypt_api_key(self, stored_value: str) -> str:
        """저장된 API 키 복호화"""
        return decrypt_value(stored_value)

    # @FEAT:account-management @COMP:service @TYPE:validation
    def _validate_api_credentials(self, account: Account) -> Tuple[bool, Optional[str]]:
        """저장된 API 자격 증명이 사용 가능한지 검증"""
        if not account.public_api or not account.secret_api:
            return False, 'API 키가 설정되어 있지 않습니다. 계좌 정보를 다시 저장해 주세요.'

        if is_likely_legacy_hash(account.public_api) or is_likely_legacy_hash(account.secret_api):
            return False, '이 계좌는 레거시 형식으로 저장된 API 키를 사용하고 있습니다. 계좌 정보를 다시 저장해 주세요.'

        if not account.api_key or not account.api_secret:
            return False, 'API 키를 복호화할 수 없습니다. 계좌 정보를 다시 저장해 주세요.'

        return True, None

    def _get_client_ip(self) -> str:
        """클라이언트 IP 주소 조회"""
        if request.headers.get('X-Forwarded-For'):
            return request.headers.get('X-Forwarded-For').split(',')[0]
        elif request.headers.get('X-Real-IP'):
            return request.headers.get('X-Real-IP')
        else:
            return request.remote_addr or '127.0.0.1'

    def _is_ip_blocked(self, ip: str) -> bool:
        """IP 차단 확인"""
        if ip in self.blocked_ips:
            return True

        # 실패 횟수 확인
        failure_info = self.failed_login_attempts.get(ip, {})
        if failure_info.get('count', 0) >= self.max_failed_attempts:
            # 차단 시간 확인
            block_time = failure_info.get('block_time')
            if block_time and datetime.now().timestamp() - block_time < self.block_duration:
                return True
            else:
                # 차단 시간 만료, 기록 삭제
                self._clear_failed_login(ip)

        return False

    def _record_failed_login(self, ip: str):
        """로그인 실패 기록"""
        current_time = datetime.now().timestamp()

        if ip not in self.failed_login_attempts:
            self.failed_login_attempts[ip] = {'count': 0, 'first_attempt': current_time}

        self.failed_login_attempts[ip]['count'] += 1
        self.failed_login_attempts[ip]['last_attempt'] = current_time

        # 최대 실패 횟수 도달 시 차단
        if self.failed_login_attempts[ip]['count'] >= self.max_failed_attempts:
            self.failed_login_attempts[ip]['block_time'] = current_time
            logger.warning(f"IP {ip} 차단됨: {self.max_failed_attempts}회 로그인 실패")

    def _clear_failed_login(self, ip: str):
        """로그인 실패 기록 삭제"""
        if ip in self.failed_login_attempts:
            del self.failed_login_attempts[ip]

    def _get_attempts_left(self, ip: str) -> int:
        """남은 시도 횟수"""
        failure_info = self.failed_login_attempts.get(ip, {})
        return max(0, self.max_failed_attempts - failure_info.get('count', 0))

    def get_security_stats(self) -> Dict[str, Any]:
        """보안 통계"""
        return {
            'failed_login_attempts': len(self.failed_login_attempts),
            'blocked_ips': len(self.blocked_ips),
            'max_failed_attempts': self.max_failed_attempts,
            'block_duration_hours': self.block_duration / 3600
        }


# 싱글톤 인스턴스
security_service = SecurityService()
