from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from app.services.capital_service import capital_service
from app.services.strategy_service import strategy_service, StrategyError

bp = Blueprint('capital', __name__, url_prefix='/api')

@bp.route('/strategies/capital', methods=['POST'])
@login_required
def manage_strategy_capital():
    """전략 자본 관리"""
    try:
        data = request.get_json()
        
        # 자동 할당 모드인지 확인
        if data.get('auto_allocate'):
            # 전략 확인
            strategy = strategy_service.get_strategy_by_id(data['strategy_id'], current_user.id)
            if not strategy:
                return jsonify({
                    'success': False,
                    'error': '전략을 찾을 수 없습니다.'
                }), 404
            
            # 전략에 연결된 모든 계좌에 대해 자동 할당 실행
            success_count = 0
            for strategy_account in strategy.strategy_accounts:
                if capital_service.auto_allocate_capital_for_account(strategy_account.account_id):
                    success_count += 1
            
            if success_count > 0:
                return jsonify({
                    'success': True,
                    'message': f'{success_count}개 계좌에 자본이 자동 할당되었습니다.'
                })
            else:
                return jsonify({
                    'success': False,
                    'error': '자동 자본 할당에 실패했습니다.'
                }), 400
        
        # 기존 수동 할당 로직
        # 입력 데이터 검증
        required_fields = ['strategy_id', 'currency', 'allocated_amount']
        for field in required_fields:
            if not data.get(field):
                return jsonify({
                    'success': False,
                    'error': f'{field} 필드가 필요합니다.'
                }), 400
        
        # 전략 확인
        strategy = strategy_service.get_strategy_by_id(data['strategy_id'], current_user.id)
        if not strategy:
            return jsonify({
                'success': False,
                'error': '전략을 찾을 수 없습니다.'
            }), 404
        
        # capital_service를 통해 자본 할당 처리
        result = capital_service.allocate_capital(
            strategy_id=data['strategy_id'],
            currency=data['currency'],
            allocated_amount=data['allocated_amount'],
            user_id=current_user.id
        )
        
        if result.get('success'):
            return jsonify({
                'success': True,
                'message': '자본이 성공적으로 할당되었습니다.',
                'allocation': result.get('allocation')
            })
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', '자본 할당에 실패했습니다.')
            }), 400
        
    except StrategyError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
    except Exception as e:
        current_app.logger.error(f'자본 관리 오류: {str(e)}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500 