from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from app import db
from app.models import Strategy, Account, StrategyAccount, StrategyCapital
from app.services.analytics import analytics_service as capital_service
from app.services.strategy_service import strategy_service, StrategyError
from app.constants import MarketType
from app.utils.response_formatter import (
    create_success_response, 
    create_error_response, 
    ErrorCode, 
    exception_to_error_response
)

bp = Blueprint('strategies', __name__, url_prefix='/api')

@bp.route('/strategies', methods=['GET'])
@login_required
def get_strategies():
    """사용자의 전략 목록 조회"""
    try:
        strategies_data = strategy_service.get_strategies_by_user(current_user.id)
        
        return create_success_response(
            data={'strategies': strategies_data},
            message='전략 목록을 성공적으로 조회했습니다.'
        )
    except StrategyError as e:
        current_app.logger.error(f'전략 목록 조회 오류: {str(e)}')
        return create_error_response(
            error_code=ErrorCode.BUSINESS_LOGIC_ERROR,
            message='전략 목록 조회 중 오류가 발생했습니다.',
            details=str(e)
        )
    except Exception as e:
        current_app.logger.error(f'전략 목록 조회 오류: {str(e)}')
        return exception_to_error_response(e)

@bp.route('/strategies/accessibles', methods=['GET'])
@login_required
def get_accessible_strategies():
    """내가 소유하거나 구독 중인 전략 목록 조회"""
    try:
        strategies_data = strategy_service.get_accessible_strategies(current_user.id)
        return create_success_response(
            data={'strategies': strategies_data},
            message='접근 가능한 전략 목록을 성공적으로 조회했습니다.'
        )
    except StrategyError as e:
        return create_error_response(
            error_code=ErrorCode.BUSINESS_LOGIC_ERROR,
            message='접근 가능한 전략 목록 조회 중 오류가 발생했습니다.',
            details=str(e)
        )
    except Exception as e:
        current_app.logger.error(f'접근 가능한 전략 목록 조회 오류: {str(e)}')
        return exception_to_error_response(e)

@bp.route('/strategies/public', methods=['GET'])
@login_required
def list_public_strategies():
    """공개 전략 목록 조회(기본 정보만)"""
    try:
        from app.models import Strategy
        strategies = Strategy.query.filter_by(is_public=True, is_active=True).all()
        items = [
            {
                'id': s.id,
                'name': s.name,
                'description': s.description,
                'market_type': s.market_type,
                'created_at': s.created_at.isoformat()
            } for s in strategies
        ]
        return create_success_response(
            data={'strategies': items},
            message='공개 전략 목록을 성공적으로 조회했습니다.'
        )
    except Exception as e:
        current_app.logger.error(f'공개 전략 목록 조회 오류: {str(e)}')
        return exception_to_error_response(e)

@bp.route('/strategies/public/<int:strategy_id>', methods=['GET'])
@login_required
def get_public_strategy(strategy_id):
    """공개 전략 상세 조회(정의 정보만, 타 사용자 계좌 비공개)"""
    try:
        from app.models import Strategy
        strategy = Strategy.query.filter_by(id=strategy_id, is_public=True, is_active=True).first()
        if not strategy:
            return create_error_response(
                error_code=ErrorCode.STRATEGY_NOT_FOUND,
                message='전략을 찾을 수 없습니다.'
            )
        item = {
            'id': strategy.id,
            'name': strategy.name,
            'description': strategy.description,
            'market_type': strategy.market_type,
            'created_at': strategy.created_at.isoformat()
        }
        return create_success_response(
            data={'strategy': item},
            message='공개 전략 정보를 성공적으로 조회했습니다.'
        )
    except Exception as e:
        current_app.logger.error(f'공개 전략 상세 조회 오류: {str(e)}')
        return exception_to_error_response(e)

@bp.route('/strategies/<int:strategy_id>/subscribe', methods=['POST'])
@login_required
def subscribe_strategy(strategy_id):
    """공개 전략 구독(내 계좌 연결)"""
    try:
        data = request.get_json()
        result = strategy_service.subscribe_to_strategy(strategy_id, current_user.id, data)
        # 최신 전략 데이터 반환(접근 가능한 전략 목록에서)
        strategies_data = strategy_service.get_accessible_strategies(current_user.id)
        updated_strategy = next((s for s in strategies_data if s['id'] == strategy_id), None)
        return create_success_response(
            data={'connection': result, 'updated_strategy': updated_strategy},
            message='구독이 완료되었습니다.'
        )
    except StrategyError as e:
        return create_error_response(
            error_code=ErrorCode.BUSINESS_LOGIC_ERROR,
            message='공개 전략 구독 중 오류가 발생했습니다.',
            details=str(e)
        )
    except Exception as e:
        current_app.logger.error(f'공개 전략 구독 오류: {str(e)}')
        return exception_to_error_response(e)

@bp.route('/strategies/<int:strategy_id>/subscribe/<int:account_id>', methods=['DELETE'])
@login_required
def unsubscribe_strategy(strategy_id, account_id):
    """공개 전략 구독 해제(내 계좌 연결 해제)"""
    try:
        success = strategy_service.unsubscribe_from_strategy(strategy_id, current_user.id, account_id)
        if not success:
            return create_error_response(
                error_code=ErrorCode.BUSINESS_LOGIC_ERROR,
                message='구독 해제에 실패했습니다.'
            )
        strategies_data = strategy_service.get_accessible_strategies(current_user.id)
        updated_strategy = next((s for s in strategies_data if s['id'] == strategy_id), None)
        return create_success_response(
            data={'updated_strategy': updated_strategy},
            message='구독이 해제되었습니다.'
        )
    except StrategyError as e:
        return create_error_response(
            error_code=ErrorCode.BUSINESS_LOGIC_ERROR,
            message='공개 전략 구독 해제 중 오류가 발생했습니다.',
            details=str(e)
        )
    except Exception as e:
        current_app.logger.error(f'공개 전략 구독 해제 오류: {str(e)}')
        return exception_to_error_response(e)

@bp.route('/strategies', methods=['POST'])
@login_required
def create_strategy():
    """새 전략 생성"""
    try:
        data = request.get_json()
        
        result = strategy_service.create_strategy(current_user.id, data)
        
        current_app.logger.info(f'새 전략 생성: {result["name"]} ({result["group_name"]}) - {result["market_type"]}')
        
        return create_success_response(
            data={'strategy_id': result['strategy_id']},
            message='전략이 성공적으로 생성되었습니다.'
        )
        
    except StrategyError as e:
        return create_error_response(
            error_code=ErrorCode.BUSINESS_VALIDATION_ERROR,
            message='전략 생성 중 오류가 발생했습니다.',
            details=str(e)
        )
    except Exception as e:
        current_app.logger.error(f'전략 생성 오류: {str(e)}')
        return exception_to_error_response(e)

@bp.route("/strategies/<int:strategy_id>", methods=["PUT"])
@login_required
def update_strategy(strategy_id):
    """전략 정보 수정 - 경쟁 조건 방지를 위한 데이터베이스 잠금 적용"""
    try:
        # 전략 조회
        strategy = Strategy.query.filter_by(id=strategy_id, user_id=current_user.id).first()
        if not strategy:
            return create_error_response(
                error_code=ErrorCode.STRATEGY_NOT_FOUND,
                message="전략을 찾을 수 없습니다."
            )

        data = request.get_json()

        # 영향받은 계좌들 추적
        affected_accounts = set()

        # 전략 기본 정보 수정
        if data.get("name"):
            strategy.name = data["name"]

        if "description" in data:
            strategy.description = data["description"]

        if "is_active" in data:
            strategy.is_active = data["is_active"]

        # market_type 수정 (검증 포함)
        if "market_type" in data:
            market_type = data["market_type"].upper() if isinstance(data["market_type"], str) else data["market_type"]
            if not MarketType.is_valid(market_type):
                return create_error_response(
                    error_code=ErrorCode.BUSINESS_VALIDATION_ERROR,
                    message=f"market_type은 {MarketType.VALID_TYPES}만 가능합니다."
                )

            # market_type이 변경된 경우 연결된 계좌들의 자본 재할당 필요
            if strategy.market_type != market_type:
                strategy.market_type = market_type
                # 연결된 계좌들을 affected_accounts에 추가하여 나중에 재할당
                for sa in strategy.strategy_accounts:
                    affected_accounts.add(sa.account_id)

        # group_name 수정 (중복 확인)
        if data.get("group_name") and data["group_name"] != strategy.group_name:
            existing_strategy = Strategy.query.filter_by(group_name=data["group_name"]).first()
            if existing_strategy:
                return create_error_response(
                    error_code=ErrorCode.BUSINESS_VALIDATION_ERROR,
                    message="이미 존재하는 그룹 이름입니다."
                )
            strategy.group_name = data["group_name"]

        # is_public 수정 (소유자만)
        if "is_public" in data:
            new_public = bool(data["is_public"])
            # 공개 -> 비공개로 바뀌는 경우, 소유자 외 구독 연결 비활성화
            if strategy.is_public and not new_public:
                deactivated = 0
                for sa in strategy.strategy_accounts:
                    if sa.account.user_id != current_user.id and sa.is_active:
                        sa.is_active = False
                        deactivated += 1
                current_app.logger.info(f"공개 전략 비공개 전환: 구독 연결 {deactivated}개 비활성화")
            strategy.is_public = new_public

        # 계좌 연결 정보 업데이트
        if "accounts" in data:
            # 기존 연결된 계좌들 기록
            old_strategy_accounts = StrategyAccount.query.filter_by(strategy_id=strategy.id).all()
            for old_sa in old_strategy_accounts:
                affected_accounts.add(old_sa.account_id)

            # 기존 연결 삭제
            StrategyAccount.query.filter_by(strategy_id=strategy.id).delete()

            # 새 연결 추가
            for account_data in data["accounts"]:
                account = Account.query.filter_by(
                    id=account_data["account_id"],
                    user_id=current_user.id
                ).first()

                if not account:
                    return create_error_response(
                        error_code=ErrorCode.ACCOUNT_NOT_FOUND,
                        message=f"계좌 ID {account_data.get('account_id')}를 찾을 수 없습니다."
                    )

                # max_symbols 유효성 검증
                max_symbols = account_data.get("max_symbols")
                if max_symbols is not None:
                    if not isinstance(max_symbols, int) or max_symbols <= 0:
                        return create_error_response(
                            error_code=ErrorCode.BUSINESS_VALIDATION_ERROR,
                            message="최대 보유 심볼 수는 양의 정수여야 합니다."
                        )

                strategy_account = StrategyAccount(
                    strategy_id=strategy.id,
                    account_id=account.id,
                    weight=account_data.get("weight", 1.0),
                    leverage=account_data.get("leverage", 1.0),
                    max_symbols=max_symbols
                )

                db.session.add(strategy_account)
                affected_accounts.add(account.id)

        # 변경사항 커밋
        db.session.commit()
        
        # 영향받은 계좌들에 대해 자본 재할당
        for account_id in affected_accounts:
            capital_service.auto_allocate_capital_for_account(account_id)
        
        current_app.logger.info(f"전략 정보 수정: {strategy.name} ({strategy.group_name})")
        
        return create_success_response(
            message="전략 정보가 성공적으로 수정되었습니다."
        )
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"전략 수정 오류: {str(e)}")
        return exception_to_error_response(e)

@bp.route('/strategies/<int:strategy_id>/toggle', methods=['POST'])
@login_required
def toggle_strategy(strategy_id):
    """전략 활성화/비활성화 토글"""
    try:
        strategy = strategy_service.get_strategy_by_id(strategy_id, current_user.id)
        if not strategy:
            return create_error_response(
                error_code=ErrorCode.STRATEGY_NOT_FOUND,
                message='전략을 찾을 수 없습니다.'
            )
        
        # 상태 토글
        update_data = {'is_active': not strategy.is_active}
        result = strategy_service.update_strategy(strategy_id, current_user.id, update_data)
        
        status = '활성화' if result['is_active'] else '비활성화'
        current_app.logger.info(f'전략 {status}: {result["name"]}')
        
        return create_success_response(
            data={'is_active': result['is_active']},
            message=f'전략이 {status}되었습니다.'
        )
        
    except StrategyError as e:
        return create_error_response(
            error_code=ErrorCode.BUSINESS_LOGIC_ERROR,
            message='전략 상태 변경 중 오류가 발생했습니다.',
            details=str(e)
        )
    except Exception as e:
        current_app.logger.error(f'전략 상태 변경 오류: {str(e)}')
        return exception_to_error_response(e)

@bp.route('/strategies/<int:strategy_id>', methods=['DELETE'])
@login_required
def delete_strategy(strategy_id):
    """전략 삭제"""
    try:
        success = strategy_service.delete_strategy(strategy_id, current_user.id)
        
        if success:
            current_app.logger.info(f'전략 삭제 완료: ID {strategy_id}')
            return create_success_response(
                message='전략이 성공적으로 삭제되었습니다.'
            )
        else:
            return create_error_response(
                error_code=ErrorCode.BUSINESS_LOGIC_ERROR,
                message='전략 삭제에 실패했습니다.'
            )
        
    except StrategyError as e:
        return create_error_response(
            error_code=ErrorCode.BUSINESS_LOGIC_ERROR,
            message='전략 삭제 중 오류가 발생했습니다.',
            details=str(e)
        )
    except Exception as e:
        current_app.logger.error(f'전략 삭제 오류: {str(e)}')
        return exception_to_error_response(e)

@bp.route('/strategies/<int:strategy_id>', methods=['GET'])
@login_required
def get_strategy(strategy_id):
    """전략 정보 조회"""
    try:
        # 단일 전략 조회를 위해 기존 get_strategies_by_user 사용 후 필터링
        strategies_data = strategy_service.get_strategies_by_user(current_user.id)
        strategy_data = next((s for s in strategies_data if s['id'] == strategy_id), None)
        
        if not strategy_data:
            return create_error_response(
                error_code=ErrorCode.STRATEGY_NOT_FOUND,
                message='전략을 찾을 수 없습니다.'
            )
        
        return create_success_response(
            data={'strategy': strategy_data},
            message='전략 정보를 성공적으로 조회했습니다.'
        )
        
    except StrategyError as e:
        return create_error_response(
            error_code=ErrorCode.BUSINESS_LOGIC_ERROR,
            message='전략 조회 중 오류가 발생했습니다.',
            details=str(e)
        )
    except Exception as e:
        current_app.logger.error(f'전략 조회 오류: {str(e)}')
        return exception_to_error_response(e)

# 전략별 계좌 연결 관리 API
@bp.route('/strategies/<int:strategy_id>/accounts', methods=['GET'])
@login_required
def get_strategy_accounts(strategy_id):
    """전략에 연결된 계좌 목록 조회"""
    try:
        strategy = Strategy.query.filter_by(id=strategy_id, user_id=current_user.id).first()
        if not strategy:
            return create_error_response(
                error_code=ErrorCode.STRATEGY_NOT_FOUND,
                message='전략을 찾을 수 없습니다.'
            )
        
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
        
        return create_success_response(
            data={'accounts': accounts_data},
            message='전략 계좌 목록을 성공적으로 조회했습니다.'
        )
        
    except Exception as e:
        current_app.logger.error(f'전략 계좌 목록 조회 오류: {str(e)}')
        return exception_to_error_response(e)

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
        
        return create_success_response(
            data={'connection': result, 'updated_strategy': updated_strategy},
            message='계좌가 성공적으로 연결되었습니다.'
        )
        
    except StrategyError as e:
        return create_error_response(
            error_code=ErrorCode.BUSINESS_LOGIC_ERROR,
            message='계좌 연결 중 오류가 발생했습니다.',
            details=str(e)
        )
    except Exception as e:
        current_app.logger.error(f'계좌 연결 오류: {str(e)}')
        return exception_to_error_response(e)

@bp.route('/strategies/<int:strategy_id>/accounts/<int:account_id>', methods=['DELETE'])
@login_required
def disconnect_strategy_account(strategy_id, account_id):
    """전략에서 계좌 연결 해제"""
    try:
        strategy = Strategy.query.filter_by(id=strategy_id, user_id=current_user.id).first()
        if not strategy:
            return create_error_response(
                error_code=ErrorCode.STRATEGY_NOT_FOUND,
                message='전략을 찾을 수 없습니다.'
            )
        
        # 연결 확인
        strategy_account = StrategyAccount.query.filter_by(
            strategy_id=strategy_id,
            account_id=account_id
        ).first()
        
        if not strategy_account:
            return create_error_response(
                error_code=ErrorCode.RESOURCE_NOT_FOUND,
                message='연결된 계좌를 찾을 수 없습니다.'
            )
        
        # 계좌 소유권 확인
        if strategy_account.account.user_id != current_user.id:
            return create_error_response(
                error_code=ErrorCode.ACCESS_DENIED,
                message='권한이 없습니다.'
            )
        
        # 활성 포지션이 있는지 확인
        if hasattr(strategy_account, 'strategy_positions') and strategy_account.strategy_positions:
            active_positions = [pos for pos in strategy_account.strategy_positions if pos.quantity != 0]
            if active_positions:
                return create_error_response(
                    error_code=ErrorCode.BUSINESS_VALIDATION_ERROR,
                    message='활성 포지션이 있는 계좌는 연결 해제할 수 없습니다. 먼저 모든 포지션을 청산하세요.'
                )
        
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
        
        return create_success_response(
            data={'updated_strategy': updated_strategy},
            message='계좌 연결이 성공적으로 해제되었습니다.'
        )
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'계좌 연결 해제 오류: {str(e)}')
        return exception_to_error_response(e)

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
        
        return create_success_response(
            data={'connection': result, 'updated_strategy': updated_strategy},
            message='계좌 설정이 성공적으로 업데이트되었습니다.'
        )
        
    except StrategyError as e:
        return create_error_response(
            error_code=ErrorCode.BUSINESS_LOGIC_ERROR,
            message='계좌 설정 업데이트 중 오류가 발생했습니다.',
            details=str(e)
        )
    except Exception as e:
        current_app.logger.error(f'계좌 설정 업데이트 오류: {str(e)}')
        return exception_to_error_response(e)
