# @FEAT:capital-management @COMP:route @TYPE:core
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


# @FEAT:capital-management @COMP:route @TYPE:core
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


# @FEAT:capital-management @COMP:route @TYPE:core
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


# @FEAT:capital-management @COMP:route @TYPE:validation
@bp.route('/api/capital/rebalance-status/<int:account_id>', methods=['GET'])
@login_required
def get_rebalance_status(account_id):
    """
    Phase 5: 특정 계좌의 리밸런싱 가능 여부 조회

    Args:
        account_id: 계좌 ID

    Returns:
        JSON: 리밸런싱 상태 정보
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

        # 리밸런싱 상태 조회
        status = capital_allocation_service.should_rebalance(account_id=account_id)

        return jsonify({
            'success': True,
            'data': {
                'account_id': account_id,
                'account_name': account.name,
                'should_rebalance': status['should_rebalance'],
                'reason': status['reason'],
                'has_positions': status['has_positions'],
                'last_rebalance_at': status['last_rebalance_at'].isoformat() if status['last_rebalance_at'] else None,
                'time_since_last_hours': status['time_since_last']
            }
        })

    except Exception as e:
        logger.error(f"리밸런싱 상태 조회 실패: {e}")
        return jsonify({
            'success': False,
            'error': f'서버 오류: {str(e)}'
        }), 500


# @FEAT:capital-management @COMP:route @TYPE:core
@bp.route('/api/capital/auto-rebalance-all', methods=['POST'])
@login_required
@csrf.exempt
def trigger_auto_rebalance():
    """
    Phase 5: 모든 계좌 자동 리밸런싱 수동 트리거

    리밸런싱 조건을 확인하고, 조건 충족 시에만 재배분 실행

    Returns:
        JSON: 리밸런싱 결과
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
                    'rebalanced': 0,
                    'skipped': 0,
                    'message': '활성 계좌가 없습니다'
                }
            })

        rebalanced_count = 0
        skipped_count = 0
        results = []

        for account in accounts:
            try:
                # 리밸런싱 조건 확인
                check_result = capital_allocation_service.should_rebalance(
                    account_id=account.id,
                    min_interval_hours=1  # 최소 1시간 간격
                )

                if not check_result['should_rebalance']:
                    results.append({
                        'account_id': account.id,
                        'account_name': account.name,
                        'rebalanced': False,
                        'reason': check_result['reason']
                    })
                    skipped_count += 1
                    continue

                # 리밸런싱 실행
                rebalance_result = capital_allocation_service.recalculate_strategy_capital(
                    account_id=account.id,
                    use_live_balance=True
                )

                results.append({
                    'account_id': account.id,
                    'account_name': account.name,
                    'rebalanced': True,
                    'total_capital': rebalance_result.get('total_capital'),
                    'allocations_count': len(rebalance_result.get('allocations', []))
                })
                rebalanced_count += 1

            except Exception as e:
                logger.error(f"계좌 {account.id} 자동 리밸런싱 실패: {e}")
                results.append({
                    'account_id': account.id,
                    'account_name': account.name,
                    'rebalanced': False,
                    'error': str(e)
                })
                skipped_count += 1

        return jsonify({
            'success': True,
            'data': {
                'total_accounts': len(accounts),
                'rebalanced': rebalanced_count,
                'skipped': skipped_count,
                'results': results
            }
        })

    except Exception as e:
        logger.error(f"자동 리밸런싱 트리거 실패: {e}")
        return jsonify({
            'success': False,
            'error': f'서버 오류: {str(e)}'
        }), 500
