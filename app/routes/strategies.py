from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from app import db
from app.models import Strategy, Account, StrategyAccount, StrategyCapital
from app.services.capital_service import capital_service
from app.services.strategy_service import strategy_service, StrategyError

bp = Blueprint('strategies', __name__, url_prefix='/api')

@bp.route('/strategies', methods=['GET'])
@login_required
def get_strategies():
    """사용자의 전략 목록 조회"""
    try:
        strategies_data = strategy_service.get_strategies_by_user(current_user.id)
        
        return jsonify({
            'success': True,
            'strategies': strategies_data
        })
    except StrategyError as e:
        current_app.logger.error(f'전략 목록 조회 오류: {str(e)}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    except Exception as e:
        current_app.logger.error(f'전략 목록 조회 오류: {str(e)}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/strategies', methods=['POST'])
@login_required
def create_strategy():
    """새 전략 생성"""
    try:
        data = request.get_json()
        
        result = strategy_service.create_strategy(current_user.id, data)
        
        current_app.logger.info(f'새 전략 생성: {result["name"]} ({result["group_name"]}) - {result["market_type"]}')
        
        return jsonify({
            'success': True,
            'message': '전략이 성공적으로 생성되었습니다.',
            'strategy_id': result['strategy_id']
        })
        
    except StrategyError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
    except Exception as e:
        current_app.logger.error(f'전략 생성 오류: {str(e)}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/strategies/<int:strategy_id>', methods=['PUT'])
@login_required
def update_strategy(strategy_id):
    """전략 정보 수정"""
    try:
        strategy = Strategy.query.filter_by(id=strategy_id, user_id=current_user.id).first()
        if not strategy:
            return jsonify({
                'success': False,
                'error': '전략을 찾을 수 없습니다.'
            }), 404
        
        data = request.get_json()
        
        # 영향받은 계좌들 추적
        affected_accounts = set()
        
        # 전략 기본 정보 수정
        if data.get('name'):
            strategy.name = data['name']
        
        if 'description' in data:
            strategy.description = data['description']
        
        if 'is_active' in data:
            strategy.is_active = data['is_active']
        
        # market_type 수정 (검증 포함)
        if 'market_type' in data:
            market_type = data['market_type']
            if market_type not in ['spot', 'futures']:
                return jsonify({
                    'success': False,
                    'error': 'market_type은 "spot" 또는 "futures"만 가능합니다.'
                }), 400
            
            # market_type이 변경된 경우 연결된 계좌들의 자본 재할당 필요
            if strategy.market_type != market_type:
                strategy.market_type = market_type
                # 연결된 계좌들을 affected_accounts에 추가하여 나중에 재할당
                for sa in strategy.strategy_accounts:
                    affected_accounts.add(sa.account_id)
        
        # group_name 수정 (중복 확인)
        if data.get('group_name') and data['group_name'] != strategy.group_name:
            existing_strategy = Strategy.query.filter_by(group_name=data['group_name']).first()
            if existing_strategy:
                return jsonify({
                    'success': False,
                    'error': '이미 존재하는 그룹 이름입니다.'
                }), 400
            strategy.group_name = data['group_name']
        
        # 계좌 연결 정보 업데이트
        if 'accounts' in data:
            # 기존 연결된 계좌들 기록
            old_strategy_accounts = StrategyAccount.query.filter_by(strategy_id=strategy.id).all()
            for old_sa in old_strategy_accounts:
                affected_accounts.add(old_sa.account_id)
            
            # 기존 연결 삭제
            StrategyAccount.query.filter_by(strategy_id=strategy.id).delete()
            
            # 새 연결 추가
            for account_data in data['accounts']:
                account = Account.query.filter_by(
                    id=account_data['account_id'], 
                    user_id=current_user.id
                ).first()
                
                if not account:
                    db.session.rollback()
                    return jsonify({
                        'success': False,
                        'error': f'계좌 ID {account_data["account_id"]}를 찾을 수 없습니다.'
                    }), 400
                
                # max_symbols 유효성 검증
                max_symbols = account_data.get('max_symbols')
                if max_symbols is not None:
                    if not isinstance(max_symbols, int) or max_symbols <= 0:
                        db.session.rollback()
                        return jsonify({
                            'success': False,
                            'error': '최대 보유 심볼 수는 양의 정수여야 합니다.'
                        }), 400
                
                strategy_account = StrategyAccount(
                    strategy_id=strategy.id,
                    account_id=account.id,
                    weight=account_data.get('weight', 1.0),
                    leverage=account_data.get('leverage', 1.0),
                    max_symbols=max_symbols  # 🆕 최대 보유 심볼 수 설정
                )
                
                db.session.add(strategy_account)
                affected_accounts.add(account.id)
        
        db.session.commit()
        
        # 영향받은 계좌들에 대해 자본 재할당
        for account_id in affected_accounts:
            capital_service.auto_allocate_capital_for_account(account_id)
        
        current_app.logger.info(f'전략 정보 수정: {strategy.name} ({strategy.group_name})')
        
        return jsonify({
            'success': True,
            'message': '전략 정보가 성공적으로 수정되었습니다.'
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'전략 수정 오류: {str(e)}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/strategies/<int:strategy_id>/toggle', methods=['POST'])
@login_required
def toggle_strategy(strategy_id):
    """전략 활성화/비활성화 토글"""
    try:
        strategy = strategy_service.get_strategy_by_id(strategy_id, current_user.id)
        if not strategy:
            return jsonify({
                'success': False,
                'error': '전략을 찾을 수 없습니다.'
            }), 404
        
        # 상태 토글
        update_data = {'is_active': not strategy.is_active}
        result = strategy_service.update_strategy(strategy_id, current_user.id, update_data)
        
        status = '활성화' if result['is_active'] else '비활성화'
        current_app.logger.info(f'전략 {status}: {result["name"]}')
        
        return jsonify({
            'success': True,
            'message': f'전략이 {status}되었습니다.',
            'is_active': result['is_active']
        })
        
    except StrategyError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
    except Exception as e:
        current_app.logger.error(f'전략 상태 변경 오류: {str(e)}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/strategies/<int:strategy_id>', methods=['DELETE'])
@login_required
def delete_strategy(strategy_id):
    """전략 삭제"""
    try:
        success = strategy_service.delete_strategy(strategy_id, current_user.id)
        
        if success:
            current_app.logger.info(f'전략 삭제 완료: ID {strategy_id}')
            return jsonify({
                'success': True,
                'message': '전략이 성공적으로 삭제되었습니다.'
            })
        else:
            return jsonify({
                'success': False,
                'error': '전략 삭제에 실패했습니다.'
            }), 400
        
    except StrategyError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
    except Exception as e:
        current_app.logger.error(f'전략 삭제 오류: {str(e)}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/strategies/<int:strategy_id>', methods=['GET'])
@login_required
def get_strategy(strategy_id):
    """전략 정보 조회"""
    try:
        # 단일 전략 조회를 위해 기존 get_strategies_by_user 사용 후 필터링
        strategies_data = strategy_service.get_strategies_by_user(current_user.id)
        strategy_data = next((s for s in strategies_data if s['id'] == strategy_id), None)
        
        if not strategy_data:
            return jsonify({
                'success': False,
                'error': '전략을 찾을 수 없습니다.'
            }), 404
        
        return jsonify({
            'success': True,
            'strategy': strategy_data
        })
        
    except StrategyError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
    except Exception as e:
        current_app.logger.error(f'전략 조회 오류: {str(e)}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# 전략별 계좌 연결 관리 API
@bp.route('/strategies/<int:strategy_id>/accounts', methods=['GET'])
@login_required
def get_strategy_accounts(strategy_id):
    """전략에 연결된 계좌 목록 조회"""
    try:
        strategy = Strategy.query.filter_by(id=strategy_id, user_id=current_user.id).first()
        if not strategy:
            return jsonify({
                'success': False,
                'error': '전략을 찾을 수 없습니다.'
            }), 404
        
        accounts_data = []
        for sa in strategy.strategy_accounts:
            account_info = {
                'id': sa.account.id,
                'name': sa.account.name,
                'exchange': sa.account.exchange,
                'weight': sa.weight,
                'leverage': sa.leverage,
                'max_symbols': sa.max_symbols,
                'is_active': sa.account.is_active
            }
            
            # 할당된 자본 정보
            if sa.strategy_capital:
                account_info['allocated_capital'] = sa.strategy_capital.allocated_capital
                account_info['current_pnl'] = sa.strategy_capital.current_pnl
            else:
                account_info['allocated_capital'] = 0
                account_info['current_pnl'] = 0
            
            accounts_data.append(account_info)
        
        return jsonify({
            'success': True,
            'accounts': accounts_data
        })
        
    except Exception as e:
        current_app.logger.error(f'전략 계좌 목록 조회 오류: {str(e)}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/strategies/<int:strategy_id>/accounts', methods=['POST'])
@login_required
def connect_account_to_strategy(strategy_id):
    """전략에 계좌 연결"""
    try:
        data = request.get_json()
        
        result = strategy_service.connect_account_to_strategy(strategy_id, current_user.id, data)
        
        # 자본 배분 완료 후 업데이트된 전략 정보 조회
        strategies_data = strategy_service.get_strategies_by_user(current_user.id)
        updated_strategy = next((s for s in strategies_data if s['id'] == strategy_id), None)
        
        return jsonify({
            'success': True,
            'message': '계좌가 성공적으로 연결되었습니다.',
            'connection': result,
            'updated_strategy': updated_strategy
        })
        
    except StrategyError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
    except Exception as e:
        current_app.logger.error(f'계좌 연결 오류: {str(e)}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/strategies/<int:strategy_id>/accounts/<int:account_id>', methods=['DELETE'])
@login_required
def disconnect_strategy_account(strategy_id, account_id):
    """전략에서 계좌 연결 해제"""
    try:
        strategy = Strategy.query.filter_by(id=strategy_id, user_id=current_user.id).first()
        if not strategy:
            return jsonify({
                'success': False,
                'error': '전략을 찾을 수 없습니다.'
            }), 404
        
        # 연결 확인
        strategy_account = StrategyAccount.query.filter_by(
            strategy_id=strategy_id,
            account_id=account_id
        ).first()
        
        if not strategy_account:
            return jsonify({
                'success': False,
                'error': '연결된 계좌를 찾을 수 없습니다.'
            }), 404
        
        # 계좌 소유권 확인
        if strategy_account.account.user_id != current_user.id:
            return jsonify({
                'success': False,
                'error': '권한이 없습니다.'
            }), 403
        
        # 활성 포지션이 있는지 확인
        if hasattr(strategy_account, 'strategy_positions') and strategy_account.strategy_positions:
            active_positions = [pos for pos in strategy_account.strategy_positions if pos.quantity != 0]
            if active_positions:
                return jsonify({
                    'success': False,
                    'error': '활성 포지션이 있는 계좌는 연결 해제할 수 없습니다. 먼저 모든 포지션을 청산하세요.'
                }), 400
        
        account_name = strategy_account.account.name
        account_id = strategy_account.account_id
        db.session.delete(strategy_account)
        db.session.commit()
        
        # 해당 계좌의 남은 전략들에 대해 자본 재할당
        capital_service.auto_allocate_capital_for_account(account_id)
        
        # 자본 배분 완료 후 업데이트된 전략 정보 조회
        strategies_data = strategy_service.get_strategies_by_user(current_user.id)
        updated_strategy = next((s for s in strategies_data if s['id'] == strategy_id), None)
        
        current_app.logger.info(f'계좌 연결 해제: 전략 {strategy.name} - 계좌 {account_name}')
        
        return jsonify({
            'success': True,
            'message': '계좌 연결이 성공적으로 해제되었습니다.',
            'updated_strategy': updated_strategy
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'계좌 연결 해제 오류: {str(e)}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/strategies/<int:strategy_id>/accounts/<int:account_id>', methods=['PUT'])
@login_required
def update_strategy_account(strategy_id, account_id):
    """전략-계좌 연결 설정 업데이트"""
    try:
        data = request.get_json()
        data['account_id'] = account_id  # URL에서 account_id 가져와서 설정
        
        result = strategy_service.update_strategy_account(strategy_id, current_user.id, data)
        
        # 자본 배분 완료 후 업데이트된 전략 정보 조회
        strategies_data = strategy_service.get_strategies_by_user(current_user.id)
        updated_strategy = next((s for s in strategies_data if s['id'] == strategy_id), None)
        
        return jsonify({
            'success': True,
            'message': '계좌 설정이 성공적으로 업데이트되었습니다.',
            'connection': result,
            'updated_strategy': updated_strategy
        })
        
    except StrategyError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
    except Exception as e:
        current_app.logger.error(f'계좌 설정 업데이트 오류: {str(e)}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500 