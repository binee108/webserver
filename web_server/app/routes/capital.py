"""
자본 배분 관련 라우트
"""

from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user

from app import csrf
from app.models import Account
from app.services.capital_service import capital_allocation_service, CapitalAllocationError
from app.utils.logging_security import get_secure_logger

logger = get_secure_logger(__name__)

bp = Blueprint('capital', __name__)


@bp.route('/api/capital/reallocate/<int:account_id>', methods=['POST'])
@login_required
@csrf.exempt
def reallocate_account_capital(account_id):
    """
    특정 계좌의 전략별 자본을 재배분합니다.

    Args:
        account_id: 계좌 ID

    Query Parameters:
        use_live: 실시간 잔고 조회 여부 (true/false, 기본값: false)

    Returns:
        JSON: 재배분 결과
    """
    try:
        # 계좌 소유권 검증
        account = Account.query.get(account_id)
        if not account:
            return jsonify({
                'success': False,
                'error': '계좌를 찾을 수 없습니다'
            }), 404

        if account.user_id != current_user.id:
            return jsonify({
                'success': False,
                'error': '권한이 없습니다'
            }), 403

        # 실시간 조회 옵션
        use_live = request.args.get('use_live', 'false').lower() == 'true'

        # 자본 재배분 실행
        result = capital_allocation_service.recalculate_strategy_capital(
            account_id=account_id,
            use_live_balance=use_live
        )

        return jsonify({
            'success': True,
            'data': result
        })

    except CapitalAllocationError as e:
        logger.error(f"자본 재배분 실패: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
    except Exception as e:
        logger.error(f"자본 재배분 중 예외 발생: {e}")
        return jsonify({
            'success': False,
            'error': f'서버 오류: {str(e)}'
        }), 500


@bp.route('/api/capital/reallocate-all', methods=['POST'])
@login_required
@csrf.exempt
def reallocate_all_accounts():
    """
    현재 사용자의 모든 계좌에 대해 전략별 자본을 재배분합니다.

    Query Parameters:
        use_live: 실시간 잔고 조회 여부 (true/false, 기본값: false)

    Returns:
        JSON: 재배분 결과 목록
    """
    try:
        # 사용자의 모든 활성 계좌 조회
        accounts = Account.query.filter_by(
            user_id=current_user.id,
            is_active=True
        ).all()

        if not accounts:
            return jsonify({
                'success': True,
                'data': {
                    'total_accounts': 0,
                    'results': [],
                    'message': '활성 계좌가 없습니다'
                }
            })

        # 실시간 조회 옵션
        use_live = request.args.get('use_live', 'false').lower() == 'true'

        # 각 계좌별 재배분 실행
        results = []
        successful = 0
        failed = 0

        for account in accounts:
            try:
                result = capital_allocation_service.recalculate_strategy_capital(
                    account_id=account.id,
                    use_live_balance=use_live
                )
                results.append({
                    'success': True,
                    'account_id': account.id,
                    'account_name': account.name,
                    'result': result
                })
                successful += 1
            except Exception as e:
                logger.error(f"계좌 {account.id} 재배분 실패: {e}")
                results.append({
                    'success': False,
                    'account_id': account.id,
                    'account_name': account.name,
                    'error': str(e)
                })
                failed += 1

        return jsonify({
            'success': True,
            'data': {
                'total_accounts': len(accounts),
                'successful': successful,
                'failed': failed,
                'results': results
            }
        })

    except Exception as e:
        logger.error(f"전체 재배분 중 예외 발생: {e}")
        return jsonify({
            'success': False,
            'error': f'서버 오류: {str(e)}'
        }), 500
