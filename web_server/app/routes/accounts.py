# @FEAT:account-management @COMP:route @TYPE:core
"""
Account Management Routes

계좌 CRUD, 연결 테스트, 잔고 조회 API 엔드포인트
"""
from datetime import datetime
from flask import Blueprint, request, current_app
from flask_login import login_required, current_user
from app.services.security import security_service as account_service
from app.services.security import SecurityError as AccountError
from app.utils.response_formatter import (
    create_success_response,
    create_error_response,
    ErrorCode,
    exception_to_error_response
)

bp = Blueprint('accounts', __name__, url_prefix='/api')

# @FEAT:account-management @COMP:route @TYPE:core
@bp.route('/accounts', methods=['GET'])
@login_required
def get_accounts():
    """사용자의 계좌 목록 조회"""
    try:
        accounts_data = account_service.get_accounts_by_user(current_user.id)

        return create_success_response(
            data={'accounts': accounts_data},
            message='계좌 목록을 성공적으로 조회했습니다.'
        )

    except AccountError as e:
        current_app.logger.error(f'계좌 목록 조회 오류: {str(e)}')
        return create_error_response(
            error_code=ErrorCode.BUSINESS_LOGIC_ERROR,
            message='계좌 목록 조회 중 오류가 발생했습니다.',
            details=str(e)
        )
    except Exception as e:
        current_app.logger.error(f'계좌 목록 조회 오류: {str(e)}')
        return exception_to_error_response(e)

# @FEAT:account-management @COMP:route @TYPE:core
@bp.route('/accounts', methods=['POST'])
@login_required
def create_account():
    """새 계좌 생성"""
    try:
        # JSON 또는 form 데이터 처리
        if request.is_json:
            data = request.get_json()
            if not data:
                return create_error_response(
                    error_code=ErrorCode.INVALID_JSON,
                    message='유효하지 않은 JSON 데이터입니다.'
                )
        else:
            data = {
                'name': request.form.get('name'),
                'exchange': request.form.get('exchange'),
                'public_api': request.form.get('public_api'),
                'secret_api': request.form.get('secret_api'),
                'passphrase': request.form.get('passphrase', '')
            }

        # 필수 필드 검증
        required_fields = ['name', 'exchange', 'public_api', 'secret_api']
        missing_fields = [field for field in required_fields if not data.get(field)]

        if missing_fields:
            return create_error_response(
                error_code=ErrorCode.MISSING_REQUIRED_FIELD,
                message='필수 필드가 누락되었습니다.',
                field_errors={field: f'{field} 필드는 필수입니다.' for field in missing_fields}
            )

        result = account_service.create_account(current_user.id, data)

        # result 성공 여부 확인 후 처리
        if result.get('success', False):
            current_app.logger.info(f'새 계좌 생성: {result["name"]} ({result["exchange"]})')

            response_data = {'account_id': result['account_id']}
            if result.get('balance_snapshot'):
                response_data['balance_snapshot'] = result['balance_snapshot']
            if result.get('balance_error'):
                response_data['balance_error'] = result['balance_error']

            if result.get('balance_error'):
                current_app.logger.warning(
                    '계좌 %s 잔고 초기화 중 경고: %s',
                    result['account_id'],
                    result['balance_error']
                )

            return create_success_response(
                data=response_data,
                message='계좌가 성공적으로 생성되었습니다.'
            )
        else:
            current_app.logger.error(f'계좌 생성 실패: {result.get("error", "알 수 없는 오류")}')
            return create_error_response(
                error_code=ErrorCode.BUSINESS_VALIDATION_ERROR,
                message=result.get('error', '계좌 생성 중 오류가 발생했습니다.')
            )

    except AccountError as e:
        return create_error_response(
            error_code=ErrorCode.BUSINESS_LOGIC_ERROR,
            message='계좌 생성 중 오류가 발생했습니다.',
            details=str(e)
        )
    except Exception as e:
        current_app.logger.error(f'계좌 생성 오류: {str(e)}')
        return exception_to_error_response(e)

# @FEAT:account-management @COMP:route @TYPE:core
@bp.route('/accounts/<int:account_id>', methods=['GET'])
@login_required
def get_account(account_id):
    """개별 계좌 정보 조회"""
    try:
        account = account_service.get_account_by_id(account_id, current_user.id)
        if not account:
            return create_error_response(
                error_code=ErrorCode.ACCOUNT_NOT_FOUND,
                message='계좌를 찾을 수 없습니다.'
            )

        # API 키를 복호화하여 마스킹해서 반환
        def mask_api_key(api_key: str) -> str:
            """API 키를 마스킹하여 일부만 표시"""
            if not api_key or len(api_key) < 8:
                return ""
            return api_key[:4] + "*" * (len(api_key) - 8) + api_key[-4:]

        # 복호화된 API 키 가져오기 (models.py의 property 사용)
        decrypted_public_api = account.api_key

        account_data = {
            'id': account.id,
            'name': account.name,
            'exchange': account.exchange,
            'public_api': mask_api_key(decrypted_public_api),
            'public_api_full': decrypted_public_api,  # 편집용 전체 키 (프론트엔드에서 필요 시)
            'passphrase': account.passphrase if account.passphrase else '',
            'is_active': account.is_active,
            'is_testnet': account.is_testnet,
            'created_at': account.created_at.isoformat(),
            'updated_at': account.updated_at.isoformat() if account.updated_at else None
        }

        return create_success_response(
            data={'account': account_data},
            message='계좌 정보를 성공적으로 조회했습니다.'
        )

    except AccountError as e:
        return create_error_response(
            error_code=ErrorCode.BUSINESS_LOGIC_ERROR,
            message='계좌 정보 조회 중 오류가 발생했습니다.',
            details=str(e)
        )
    except Exception as e:
        current_app.logger.error(f'계좌 정보 조회 오류: {str(e)}')
        return exception_to_error_response(e)

# @FEAT:account-management @COMP:route @TYPE:core
@bp.route('/accounts/<int:account_id>', methods=['PUT'])
@login_required
def update_account(account_id):
    """계좌 정보 수정"""
    try:
        data = request.get_json()

        if not data:
            return create_error_response(
                error_code=ErrorCode.INVALID_JSON,
                message='유효하지 않은 JSON 데이터입니다.'
            )

        # Phase 4: 계좌 비활성화 시 연결된 모든 전략의 SSE 종료
        if 'is_active' in data and not data['is_active']:
            from app.models import Account, StrategyAccount
            from app.services.event_service import event_service

            account = Account.query.get(account_id)
            if account and account.user_id == current_user.id:
                # 해당 계좌가 연결된 모든 활성 전략 찾기
                strategy_accounts = StrategyAccount.query.filter_by(
                    account_id=account_id,
                    is_active=True
                ).all()

                total_cleaned = 0
                for sa in strategy_accounts:
                    cleaned = event_service.disconnect_client(
                        current_user.id,
                        sa.strategy_id,
                        reason='account_deactivated'
                    )
                    total_cleaned += cleaned

                if total_cleaned > 0:
                    current_app.logger.info(
                        f"계좌 {account_id} 비활성화 - 총 {total_cleaned}개 SSE 종료"
                    )

        result = account_service.update_account(account_id, current_user.id, data)

        # result 성공 여부 확인 후 처리
        if result.get('success', False):
            current_app.logger.info(f'계좌 수정: {result["name"]} (ID: {result["account_id"]})')
            return create_success_response(
                data={'account': result},
                message='계좌 정보가 성공적으로 수정되었습니다.'
            )
        else:
            current_app.logger.error(f'계좌 수정 실패: {result.get("error", "알 수 없는 오류")}')
            return create_error_response(
                error_code=ErrorCode.BUSINESS_VALIDATION_ERROR,
                message=result.get('error', '계좌 수정 중 오류가 발생했습니다.')
            )

    except AccountError as e:
        return create_error_response(
            error_code=ErrorCode.BUSINESS_LOGIC_ERROR,
            message='계좌 수정 중 오류가 발생했습니다.',
            details=str(e)
        )
    except Exception as e:
        current_app.logger.error(f'계좌 수정 오류: {str(e)}')
        return exception_to_error_response(e)

# @FEAT:account-management @COMP:route @TYPE:core
@bp.route('/accounts/<int:account_id>', methods=['DELETE'])
@login_required
def delete_account(account_id):
    """계좌 삭제"""
    try:
        success = account_service.delete_account(account_id, current_user.id)

        if success:
            current_app.logger.info(f'계좌 삭제 완료: ID {account_id}')
            return create_success_response(
                message='계좌가 성공적으로 삭제되었습니다.'
            )
        else:
            return create_error_response(
                error_code=ErrorCode.BUSINESS_LOGIC_ERROR,
                message='계좌 삭제에 실패했습니다.'
            )

    except AccountError as e:
        return create_error_response(
            error_code=ErrorCode.BUSINESS_LOGIC_ERROR,
            message='계좌 삭제 중 오류가 발생했습니다.',
            details=str(e)
        )
    except Exception as e:
        current_app.logger.error(f'계좌 삭제 오류: {str(e)}')
        return exception_to_error_response(e)

# @FEAT:account-management @COMP:route @TYPE:core
@bp.route('/accounts/<int:account_id>/test', methods=['POST'])
@login_required
def test_account_connection(account_id):
    """계좌 연결 테스트"""
    try:
        result = account_service.test_account_connection(account_id, current_user.id)

        # 서비스에서 반환하는 result가 이미 표준 형식인지 확인
        if isinstance(result, dict) and 'success' in result:
            if result.get('success'):
                payload = {k: v for k, v in result.items() if k != 'success'}
                return create_success_response(
                    data=payload,
                    message='계좌 연결 테스트가 성공했습니다.'
                )
            else:
                return create_error_response(
                    error_code=ErrorCode.EXCHANGE_ERROR,
                    message=result.get('error', '계좌 연결 테스트에 실패했습니다.'),
                    details=result
                )
        else:
            # 레거시 응답 처리
            return create_success_response(
                data=result,
                message='계좌 연결 테스트가 완료되었습니다.'
            )

    except AccountError as e:
        return create_error_response(
            error_code=ErrorCode.BUSINESS_LOGIC_ERROR,
            message='계좌 연결 테스트 중 오류가 발생했습니다.',
            details=str(e)
        )
    except Exception as e:
        current_app.logger.error(f'계좌 연결 테스트 오류: {str(e)}')
        return exception_to_error_response(e)

# @FEAT:account-management @COMP:route @TYPE:core
@bp.route('/accounts/<int:account_id>/balance', methods=['GET'])
@login_required
def get_account_balance(account_id):
    """계좌 잔고 조회"""
    try:
        balance_data = account_service.get_account_balance(account_id, current_user.id)

        return create_success_response(
            data={'balance': balance_data},
            message='계좌 잔고를 성공적으로 조회했습니다.'
        )

    except AccountError as e:
        current_app.logger.error(f'계좌 잔고 조회 실패: {str(e)}')
        return create_error_response(
            error_code=ErrorCode.FORBIDDEN,
            message=str(e),
            details=None
        )
    except Exception as e:
        current_app.logger.error(f'계좌 잔고 조회 중 오류 발생: {str(e)}')
        return create_error_response(
            error_code=ErrorCode.INTERNAL_SERVER_ERROR,
            message='계좌 잔고 조회 중 오류가 발생했습니다.',
            details=str(e)
        )
