from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from app.services.account_service import account_service, AccountError

bp = Blueprint('accounts', __name__, url_prefix='/api')

@bp.route('/accounts', methods=['GET'])
@login_required
def get_accounts():
    """사용자의 계좌 목록 조회"""
    try:
        accounts_data = account_service.get_accounts_by_user(current_user.id)
        
        return jsonify({
            'success': True,
            'accounts': accounts_data
        })
    except AccountError as e:
        current_app.logger.error(f'계좌 목록 조회 오류: {str(e)}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    except Exception as e:
        current_app.logger.error(f'계좌 목록 조회 오류: {str(e)}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/accounts', methods=['POST'])
@login_required
def create_account():
    """새 계좌 생성"""
    try:
        # JSON 또는 form 데이터 처리
        if request.is_json:
            data = request.get_json()
        else:
            data = {
                'name': request.form.get('name'),
                'exchange': request.form.get('exchange'),
                'public_api': request.form.get('public_api'),  # HTML form의 public_api를 직접 사용
                'secret_api': request.form.get('secret_api'),  # HTML form의 secret_api를 직접 사용
                'passphrase': request.form.get('passphrase', '')
            }
        
        result = account_service.create_account(current_user.id, data)
        
        current_app.logger.info(f'새 계좌 생성: {result["name"]} ({result["exchange"]})')
        
        return jsonify({
            'success': True,
            'message': '계좌가 성공적으로 생성되었습니다.',
            'account_id': result['account_id']
        })
        
    except AccountError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
    except Exception as e:
        current_app.logger.error(f'계좌 생성 오류: {str(e)}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/accounts/<int:account_id>', methods=['GET'])
@login_required
def get_account(account_id):
    """개별 계좌 정보 조회"""
    try:
        account = account_service.get_account_by_id(account_id, current_user.id)
        if not account:
            return jsonify({
                'success': False,
                'error': '계좌를 찾을 수 없습니다.'
            }), 404
        
        # 보안상 민감한 정보는 제외하고 반환
        account_data = {
            'id': account.id,
            'name': account.name,
            'exchange': account.exchange,
            'public_api': account.public_api,  # 수정 시 전체 키가 필요
            'passphrase': account.passphrase if account.passphrase else '',  # passphrase 포함
            'is_active': account.is_active,
            'is_testnet': account.is_testnet,  # 테스트넷 여부
            'created_at': account.created_at.isoformat(),
            'updated_at': account.updated_at.isoformat() if account.updated_at else None
        }
        
        return jsonify({
            'success': True,
            'account': account_data
        })
        
    except AccountError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
    except Exception as e:
        current_app.logger.error(f'계좌 정보 조회 오류: {str(e)}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/accounts/<int:account_id>', methods=['PUT'])
@login_required
def update_account(account_id):
    """계좌 정보 수정"""
    try:
        data = request.get_json()
        
        result = account_service.update_account(account_id, current_user.id, data)
        
        current_app.logger.info(f'계좌 수정: {result["name"]} (ID: {result["account_id"]})')
        
        return jsonify({
            'success': True,
            'message': '계좌 정보가 성공적으로 수정되었습니다.',
            'account': result
        })
        
    except AccountError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
    except Exception as e:
        current_app.logger.error(f'계좌 수정 오류: {str(e)}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/accounts/<int:account_id>', methods=['DELETE'])
@login_required
def delete_account(account_id):
    """계좌 삭제"""
    try:
        success = account_service.delete_account(account_id, current_user.id)
        
        if success:
            current_app.logger.info(f'계좌 삭제 완료: ID {account_id}')
            return jsonify({
                'success': True,
                'message': '계좌가 성공적으로 삭제되었습니다.'
            })
        else:
            return jsonify({
                'success': False,
                'error': '계좌 삭제에 실패했습니다.'
            }), 400
        
    except AccountError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
    except Exception as e:
        current_app.logger.error(f'계좌 삭제 오류: {str(e)}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/accounts/<int:account_id>/test', methods=['POST'])
@login_required
def test_account_connection(account_id):
    """계좌 연결 테스트"""
    try:
        result = account_service.test_account_connection(account_id, current_user.id)
        
        return jsonify(result)
        
    except AccountError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
    except Exception as e:
        current_app.logger.error(f'계좌 연결 테스트 오류: {str(e)}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/accounts/<int:account_id>/balance', methods=['GET'])
@login_required
def get_account_balance(account_id):
    """계좌 잔고 조회"""
    try:
        balance_data = account_service.get_account_balance(account_id, current_user.id)
        
        return jsonify({
            'success': True,
            'balance': balance_data
        })
        
    except AccountError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
    except Exception as e:
        current_app.logger.error(f'계좌 잔고 조회 오류: {str(e)}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500 