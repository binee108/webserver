# @FEAT:strategy-management @COMP:route @TYPE:core
"""
전략 관리 API 라우트

전략 CRUD, 계좌 연결, 공개 전략 구독, 성과 조회 등을 제공하는 REST API 엔드포인트
"""
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload
from app import db
from app.models import Strategy, Account, StrategyAccount, StrategyCapital, StrategyPosition, OpenOrder
from app.services.analytics import analytics_service as capital_service
from app.services.strategy_service import strategy_service, StrategyError
from app.services.trading import trading_service
from app.constants import MarketType
from app.utils.response_formatter import (
    create_success_response,
    create_error_response,
    ErrorCode,
    exception_to_error_response
)

bp = Blueprint('strategies', __name__, url_prefix='/api')

# @FEAT:strategy-management @COMP:route @TYPE:core
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

# @FEAT:strategy-management @COMP:route @TYPE:core
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

# @FEAT:strategy-management @COMP:route @TYPE:core
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

# @FEAT:strategy-management @COMP:route @TYPE:core
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

# @FEAT:strategy-management @COMP:route @TYPE:core
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
            error_code=ErrorCode.INVALID_PARAMETER,
            message='공개 전략 구독 중 오류가 발생했습니다.',
            details=str(e)
        )
    except Exception as e:
        current_app.logger.error(f'공개 전략 구독 오류: {str(e)}')
        return exception_to_error_response(e)

# @FEAT:strategy-management @COMP:route @TYPE:core
# @FEAT:strategy-subscription-safety @COMP:route @TYPE:core
@bp.route('/strategies/<int:strategy_id>/subscribe/<int:account_id>', methods=['DELETE'])
@login_required
def unsubscribe_strategy(strategy_id, account_id):
    """공개 전략 구독 해제(내 계좌 연결 해제)

    Query Parameters:
        force (bool): true일 경우 활성 포지션/주문 강제 청산 후 해제
    """
    try:
        # 쿼리 파라미터에서 force 추출
        force = request.args.get('force', 'false').lower() == 'true'

        success = strategy_service.unsubscribe_from_strategy(
            strategy_id, current_user.id, account_id, force=force
        )
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

# @FEAT:strategy-management @COMP:route @TYPE:core
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

# @FEAT:strategy-management @COMP:route @TYPE:core
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
            # Phase 3: 비활성화 시 SSE 클라이언트 정리
            if strategy.is_active and not data["is_active"]:  # 활성 -> 비활성으로 변경
                from app.services.event_service import event_service
                cleaned_count = event_service.cleanup_strategy_clients(strategy_id)
                current_app.logger.info(
                    f"전략 {strategy_id} 비활성화 - SSE 클라이언트 {cleaned_count}개 정리됨"
                )
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

        # @FEAT:strategy-subscription-safety @COMP:route @TYPE:core
        # is_public 수정 (소유자만)
        if "is_public" in data:
            new_public = bool(data["is_public"])

            # 공개 -> 비공개로 바뀌는 경우
            if strategy.is_public and not new_public:
                from app.services.event_service import event_service

                # ✅ Phase 1: 전체 데이터 미리 로드 (N+1 쿼리 최적화)
                strategy = Strategy.query.options(
                    joinedload(Strategy.strategy_accounts)
                    .joinedload(StrategyAccount.strategy_positions),
                    joinedload(Strategy.strategy_accounts)
                    .joinedload(StrategyAccount.account)
                ).filter_by(id=strategy_id).first()

                deactivated = 0
                total_sse_cleaned = 0
                failed_cleanups = []

                for sa in strategy.strategy_accounts:
                    if sa.account.user_id != current_user.id and sa.is_active:
                        try:
                            # ✅ 1. 먼저 비활성화 (웹훅 차단) - Race Condition 방지
                            sa.is_active = False
                            db.session.flush()  # DB 즉시 반영

                            # ✅ 2. 미체결 주문 취소
                            cancel_result = trading_service.order_manager.cancel_all_orders_by_user(
                                user_id=sa.account.user_id,
                                strategy_id=strategy_id,
                                account_id=sa.account.id
                            )

                            # 취소 실패 추적
                            if cancel_result.get('failed_orders'):
                                for failed in cancel_result['failed_orders']:
                                    failed_cleanups.append({
                                        'account': sa.account.name,
                                        'type': 'order_cancellation',
                                        'symbol': failed.get('symbol'),
                                        'order_id': failed.get('order_id'),
                                        'reason': failed.get('error')
                                    })

                            # ✅ 3. 남은 OpenOrder 확인 (방어적 검증)
                            remaining_orders = OpenOrder.query.filter_by(
                                strategy_account_id=sa.id
                            ).filter(OpenOrder.status.in_(['OPEN', 'PARTIALLY_FILLED', 'NEW'])).all()

                            if remaining_orders:
                                current_app.logger.error(
                                    f"주문 취소 후에도 OpenOrder {len(remaining_orders)}개 남음: "
                                    f"strategy_account_id={sa.id}"
                                )

                                for order in remaining_orders:
                                    failed_cleanups.append({
                                        'account': sa.account.name,
                                        'type': 'remaining_order',
                                        'symbol': order.symbol,
                                        'order_id': order.exchange_order_id,
                                        'quantity': str(order.quantity)
                                    })

                            # ✅ 4. 활성 포지션 청산
                            positions = [pos for pos in sa.strategy_positions if pos.quantity != 0]

                            for position in positions:
                                try:
                                    close_result = trading_service.position_manager.close_position_by_id(
                                        position_id=position.id,
                                        user_id=sa.account.user_id
                                    )

                                    if not close_result.get('success'):
                                        failed_cleanups.append({
                                            'account': sa.account.name,
                                            'type': 'position_close',
                                            'symbol': position.symbol,
                                            'quantity': str(position.quantity),
                                            'reason': close_result.get('error', 'Unknown error')
                                        })
                                except Exception as e:
                                    current_app.logger.error(f"포지션 청산 오류: {e}", exc_info=True)
                                    failed_cleanups.append({
                                        'account': sa.account.name,
                                        'type': 'position_close_exception',
                                        'symbol': position.symbol,
                                        'reason': str(e)
                                    })

                            # ✅ 5. SSE 연결 종료
                            cleaned = event_service.disconnect_client(
                                sa.account.user_id,
                                strategy_id,
                                reason='permission_revoked'
                            )
                            total_sse_cleaned += cleaned
                            deactivated += 1

                        except Exception as e:
                            current_app.logger.error(f"구독자 정리 오류 (account={sa.account.name}): {e}", exc_info=True)
                            failed_cleanups.append({
                                'account': sa.account.name,
                                'type': 'cleanup_exception',
                                'reason': str(e)
                            })

                # ✅ 6. 실패 시 텔레그램 알림 (Best-Effort)
                # TODO: 텔레그램 서비스 구현 후 활성화
                # if failed_cleanups:
                #     try:
                #         from app.services.telegram_service import send_message_to_user
                #
                #         # 실패한 계좌 수 (중복 제거)
                #         failed_accounts = set(f['account'] for f in failed_cleanups)
                #
                #         message = (
                #             f"⚠️ 전략 비공개 전환 완료 (일부 실패)\n\n"
                #             f"전략: {strategy.name}\n"
                #             f"청산 실패 계좌: {len(failed_accounts)}개\n\n"
                #             f"실패 내역:\n"
                #         )
                #
                #         for failure in failed_cleanups:
                #             message += f"- {failure['account']}: {failure['type']}\n"
                #             if 'symbol' in failure:
                #                 message += f"  심볼: {failure['symbol']}\n"
                #             if 'reason' in failure:
                #                 message += f"  오류: {failure['reason']}\n"
                #
                #         message += "\n관리자가 수동으로 해당 계좌의 포지션을 확인하고 청산해야 합니다."
                #
                #         send_message_to_user(
                #             user_id=current_user.id,
                #             message=message
                #         )
                #
                #     except Exception as e:
                #         current_app.logger.error(f"텔레그램 알림 발송 실패: {e}")
                #         # 알림 실패해도 계속 진행

                # 로그 기록
                if failed_cleanups:
                    current_app.logger.warning(
                        f"공개 전략 비공개 전환 (일부 실패): 구독 연결 {deactivated}개 비활성화, "
                        f"SSE {total_sse_cleaned}개 종료, 실패 {len(failed_cleanups)}건\n"
                        f"실패 상세: {failed_cleanups}"
                    )
                else:
                    current_app.logger.info(
                        f"공개 전략 비공개 전환: 구독 연결 {deactivated}개 비활성화, "
                        f"SSE {total_sse_cleaned}개 종료, 실패 {len(failed_cleanups)}건"
                    )

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

# @FEAT:strategy-subscription-safety @COMP:route @TYPE:core
@bp.route('/strategies/<int:strategy_id>/subscribe/<int:account_id>/status', methods=['GET'])
@login_required
def get_subscription_status(strategy_id: int, account_id: int):
    """
    구독 상태 조회 API

    구독 해제 전 프론트엔드에서 경고 메시지를 표시하기 위한 상태 정보를 반환합니다.

    Args:
        strategy_id: 전략 ID
        account_id: 계좌 ID

    Returns:
        JSON: {
            success: true,
            data: {
                active_positions: int,  # quantity != 0인 포지션 개수
                open_orders: int,       # 미체결 주문 개수
                symbols: list,          # 영향받는 심볼 목록 (정렬)
                is_active: bool         # 구독 활성 상태
            }
        }

    Errors:
        403: 계좌 소유자가 아님 (접근 권한 없음)
        404: 구독 정보를 찾을 수 없음
        500: 서버 오류

    Example:
        GET /api/strategies/123/subscribe/456/status

        Response:
        {
            "success": true,
            "data": {
                "active_positions": 2,
                "open_orders": 3,
                "symbols": ["BTC/USDT", "ETH/USDT"],
                "is_active": true
            }
        }
    """
    try:
        # Step 1: Account 소유권 먼저 확인 (보안: 가벼운 쿼리로 권한 검증)
        account = Account.query.filter_by(id=account_id).first()
        if not account or account.user_id != current_user.id:
            # 보안: 계좌 없음과 권한 없음을 구분하지 않음 (정보 은닉)
            return create_error_response(
                error_code=ErrorCode.ACCESS_DENIED,
                message='접근 권한이 없습니다.'
            )

        # Step 2: 권한 확인 후 StrategyAccount 조회 (성능: 권한 없는 요청은 expensive loading 전에 차단)
        strategy_account = StrategyAccount.query.options(
            joinedload(StrategyAccount.strategy_positions)
            # Note: account는 이미 조회했으므로 joinedload 불필요
        ).filter_by(
            strategy_id=strategy_id,
            account_id=account_id
        ).first()

        if not strategy_account:
            return create_error_response(
                error_code=ErrorCode.RESOURCE_NOT_FOUND,
                message='구독 정보를 찾을 수 없습니다.'
            )

        # Step 3: 활성 포지션 필터링 (quantity != 0만)
        active_positions = [pos for pos in strategy_account.strategy_positions if pos.quantity != 0]

        # Step 4: 미체결 주문 조회
        # OpenOrder 가능 상태: OPEN, PARTIALLY_FILLED, NEW, CANCELLED, FILLED
        # 미체결로 간주: OPEN, PARTIALLY_FILLED, NEW
        open_orders = OpenOrder.query.filter_by(
            strategy_account_id=strategy_account.id
        ).filter(OpenOrder.status.in_(['OPEN', 'PARTIALLY_FILLED', 'NEW'])).all()

        # Step 5: 심볼 목록 추출 (중복 제거, 정렬)
        symbols = set()
        for pos in active_positions:
            symbols.add(pos.symbol)
        for order in open_orders:
            symbols.add(order.symbol)
        symbols = sorted(list(symbols))

        # Step 6: 디버그 로깅 (선택사항)
        current_app.logger.debug(
            f"구독 상태 조회 완료 - strategy_id={strategy_id}, account_id={account_id}, "
            f"활성_포지션={len(active_positions)}, 미체결_주문={len(open_orders)}"
        )

        # Step 7: 응답 반환
        return create_success_response(data={
            'active_positions': len(active_positions),
            'open_orders': len(open_orders),
            'symbols': symbols,
            'is_active': strategy_account.is_active
        })

    except Exception as e:
        current_app.logger.error(
            f"구독 상태 조회 오류 - strategy_id={strategy_id}, account_id={account_id}: {e}",
            exc_info=True
        )
        return create_error_response(
            error_code=ErrorCode.INTERNAL_SERVER_ERROR,
            message='구독 상태 조회 중 오류가 발생했습니다.'
        )

# @FEAT:strategy-management @COMP:route @TYPE:core
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

        # Phase 3: 비활성화 전 SSE 클라이언트 정리
        if strategy.is_active:  # 활성 -> 비활성으로 변경 시
            from app.services.event_service import event_service
            cleaned_count = event_service.cleanup_strategy_clients(strategy_id)
            current_app.logger.info(
                f"전략 {strategy_id} 비활성화 - SSE 클라이언트 {cleaned_count}개 정리됨"
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

# @FEAT:strategy-management @COMP:route @TYPE:core
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

# @FEAT:strategy-management @COMP:route @TYPE:core
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
# @FEAT:strategy-management @COMP:route @TYPE:core
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

# @FEAT:strategy-management @COMP:route @TYPE:core
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
            error_code=ErrorCode.INVALID_PARAMETER,
            message='계좌 연결 중 오류가 발생했습니다.',
            details=str(e)
        )
    except Exception as e:
        current_app.logger.error(f'계좌 연결 오류: {str(e)}')
        return exception_to_error_response(e)

# @FEAT:strategy-management @COMP:route @TYPE:core
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

        # Phase 4: 계좌 소유자의 SSE 연결 강제 종료
        affected_user_id = strategy_account.account.user_id
        account_name = strategy_account.account.name
        account_id_value = strategy_account.account_id

        # 삭제 전 SSE 클라이언트 정리
        from app.services.event_service import event_service
        cleaned = event_service.disconnect_client(
            affected_user_id,
            strategy_id,
            reason='permission_revoked'
        )
        if cleaned > 0:
            current_app.logger.info(
                f"StrategyAccount 삭제 - 사용자 {affected_user_id} SSE {cleaned}개 종료"
            )

        db.session.delete(strategy_account)
        db.session.commit()

        # 해당 계좌의 남은 전략들에 대해 자본 재할당
        capital_service.auto_allocate_capital_for_account(account_id_value)

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

# @FEAT:strategy-management @COMP:route @TYPE:core
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


# ============================================================
# Phase 3.3: 전략 성과 조회 API 엔드포인트
# ============================================================

# @FEAT:strategy-management @FEAT:analytics @COMP:route @TYPE:core
@bp.route('/strategies/<int:strategy_id>/performance/roi', methods=['GET'])
@login_required
def get_strategy_roi(strategy_id):
    """
    전략의 ROI 및 손익 분석 조회

    Query Parameters:
        - days (optional): 분석 기간 (일 단위). 지정하지 않으면 전체 기간

    Returns:
        {
            "success": true,
            "data": {
                "roi": 12.5,
                "total_pnl": 1250.50,
                "invested_capital": 10000.0,
                "profit_factor": 1.67,
                "avg_win": 75.30,
                "avg_loss": -45.20
            }
        }
    """
    try:
        from app.services.performance_tracking import performance_tracking_service

        # 권한 확인
        strategy = Strategy.query.get(strategy_id)
        if not strategy:
            return create_error_response(
                error_code=ErrorCode.STRATEGY_NOT_FOUND,
                message='전략을 찾을 수 없습니다.'
            )

        if strategy.user_id != current_user.id:
            return create_error_response(
                error_code=ErrorCode.PERMISSION_DENIED,
                message='해당 전략에 접근할 권한이 없습니다.'
            )

        # Query 파라미터 파싱
        days = request.args.get('days', type=int)

        # ROI 계산
        roi_data = performance_tracking_service.calculate_roi(
            strategy_id=strategy_id,
            days=days
        )

        return create_success_response(
            data=roi_data,
            message='ROI 조회에 성공했습니다.'
        )

    except Exception as e:
        current_app.logger.error(f'ROI 조회 오류: {str(e)}')
        return exception_to_error_response(e)


# @FEAT:strategy-management @FEAT:analytics @COMP:route @TYPE:core
@bp.route('/strategies/<int:strategy_id>/performance/summary', methods=['GET'])
@login_required
def get_strategy_performance_summary(strategy_id):
    """
    전략의 성과 요약 조회

    Query Parameters:
        - days (optional): 분석 기간 (일 단위, 기본값: 30)

    Returns:
        {
            "success": true,
            "data": {
                "period_days": 30,
                "total_return": 12.5,
                "total_pnl": 1250.50,
                "avg_daily_pnl": 41.68,
                "best_day": 250.00,
                "worst_day": -150.00,
                "total_trades": 45,
                "avg_win_rate": 65.5,
                "max_drawdown": -8.2
            }
        }
    """
    try:
        from app.services.performance_tracking import performance_tracking_service

        # 권한 확인
        strategy = Strategy.query.get(strategy_id)
        if not strategy:
            return create_error_response(
                error_code=ErrorCode.STRATEGY_NOT_FOUND,
                message='전략을 찾을 수 없습니다.'
            )

        if strategy.user_id != current_user.id:
            return create_error_response(
                error_code=ErrorCode.PERMISSION_DENIED,
                message='해당 전략에 접근할 권한이 없습니다.'
            )

        # Query 파라미터 파싱 (기본값: 30일)
        days = request.args.get('days', default=30, type=int)

        # 성과 요약 조회
        summary = performance_tracking_service.get_performance_summary(
            strategy_id=strategy_id,
            days=days
        )

        return create_success_response(
            data=summary,
            message='성과 요약 조회에 성공했습니다.'
        )

    except Exception as e:
        current_app.logger.error(f'성과 요약 조회 오류: {str(e)}')
        return exception_to_error_response(e)


# @FEAT:strategy-management @FEAT:analytics @COMP:route @TYPE:core
@bp.route('/strategies/<int:strategy_id>/performance/daily', methods=['GET'])
@login_required
def get_strategy_daily_performance(strategy_id):
    """
    전략의 일일 성과 조회

    Query Parameters:
        - date (optional): 조회할 날짜 (YYYY-MM-DD 형식). 지정하지 않으면 오늘

    Returns:
        {
            "success": true,
            "data": {
                "date": "2025-10-03",
                "daily_return": 0.5,
                "cumulative_return": 12.5,
                "daily_pnl": 50.00,
                "cumulative_pnl": 1250.50,
                "total_trades": 5,
                "winning_trades": 3,
                "losing_trades": 2,
                "win_rate": 60.0,
                "sharpe_ratio": 1.5,
                "sortino_ratio": 2.1,
                "volatility": 0.8,
                "max_drawdown": -5.2
            }
        }
    """
    try:
        from app.services.performance_tracking import performance_tracking_service
        from datetime import datetime, date

        # 권한 확인
        strategy = Strategy.query.get(strategy_id)
        if not strategy:
            return create_error_response(
                error_code=ErrorCode.STRATEGY_NOT_FOUND,
                message='전략을 찾을 수 없습니다.'
            )

        if strategy.user_id != current_user.id:
            return create_error_response(
                error_code=ErrorCode.PERMISSION_DENIED,
                message='해당 전략에 접근할 권한이 없습니다.'
            )

        # Query 파라미터 파싱
        date_str = request.args.get('date')
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else date.today()

        # 일일 성과 조회
        performance = performance_tracking_service.calculate_daily_performance(
            strategy_id=strategy_id,
            target_date=target_date
        )

        if not performance:
            return create_error_response(
                error_code=ErrorCode.DATA_NOT_FOUND,
                message='해당 날짜의 성과 데이터가 없습니다.'
            )

        # 응답 데이터 구성
        data = {
            'date': performance.date.isoformat(),
            'daily_return': performance.daily_return,
            'cumulative_return': performance.cumulative_return,
            'daily_pnl': performance.daily_pnl,
            'cumulative_pnl': performance.cumulative_pnl,
            'total_trades': performance.total_trades,
            'winning_trades': performance.winning_trades,
            'losing_trades': performance.losing_trades,
            'win_rate': performance.win_rate,
            'sharpe_ratio': performance.sharpe_ratio,
            'sortino_ratio': performance.sortino_ratio,
            'volatility': performance.volatility,
            'max_drawdown': performance.max_drawdown
        }

        return create_success_response(
            data=data,
            message='일일 성과 조회에 성공했습니다.'
        )

    except ValueError as e:
        return create_error_response(
            error_code=ErrorCode.INVALID_REQUEST,
            message='날짜 형식이 올바르지 않습니다. (YYYY-MM-DD 형식 사용)',
            details=str(e)
        )
    except Exception as e:
        current_app.logger.error(f'일일 성과 조회 오류: {str(e)}')
        return exception_to_error_response(e)
