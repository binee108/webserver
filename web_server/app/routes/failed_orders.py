"""
실패한 주문 관리 API 엔드포인트

@FEAT:immediate-order-execution @COMP:route @TYPE:core

사용자가 웹 UI에서 실패한 주문을 조회, 재시도, 제거할 수 있도록
RESTful API 엔드포인트를 제공합니다.

엔드포인트:
- GET /api/failed-orders: 목록 조회 (필터: strategy_account_id, symbol)
- POST /api/failed-orders/<int:failed_order_id>/retry: 재시도
- DELETE /api/failed-orders/<int:failed_order_id>: 제거

권한 검증:
- 모든 엔드포인트는 @login_required 적용
- FailedOrder → StrategyAccount → Strategy → User 체인 확인
- 현재 사용자 소유의 FailedOrder만 접근 가능
"""
from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user
from app.models import FailedOrder, StrategyAccount, Account
from app.services.trading.failed_order_manager import failed_order_manager
from sqlalchemy.orm import joinedload

# @FEAT:immediate-order-execution @COMP:route @TYPE:core
failed_orders_bp = Blueprint('failed_orders', __name__)


# @FEAT:immediate-order-execution @COMP:route @TYPE:core
@failed_orders_bp.route('/api/failed-orders', methods=['GET'])
@login_required
def get_failed_orders():
    """
    실패한 주문 목록 조회 (status='pending_retry'만 반환)

    Query parameters:
    - strategy_account_id (int, optional): 전략 계정 ID 필터
    - symbol (str, optional): 심볼 필터 (예: "BTC/USDT")

    Returns:
        200: {
            'success': True,
            'orders': [
                {
                    'id': 1,
                    'strategy_account_id': 1,
                    'symbol': 'BTC/USDT',
                    'side': 'BUY',
                    'order_type': 'LIMIT',
                    'quantity': '0.1',
                    'price': '50000',
                    'stop_price': None,
                    'market_type': 'SPOT',
                    'reason': '잔고 부족',
                    'exchange_error': 'Insufficient balance',
                    'retry_count': 0,
                    'status': 'pending_retry',
                    'created_at': '2025-10-29T10:00:00',
                    'updated_at': '2025-10-29T10:00:00'
                }
            ]
        }
        401: {'success': False, 'error': 'Unauthorized'}
        500: {'success': False, 'error': 'Internal server error'}
    """
    try:
        # Query parameters (optional)
        strategy_account_id = request.args.get('strategy_account_id', type=int)
        symbol = request.args.get('symbol', type=str)

        # 1. 현재 사용자의 모든 StrategyAccount ID 조회
        # StrategyAccount → Strategy → User 체인 확인
        user_strategy_account_ids = (
            StrategyAccount.query
            .join(StrategyAccount.strategy)
            .filter_by(user_id=current_user.id)
            .with_entities(StrategyAccount.id)
            .all()
        )
        user_strategy_account_ids = [sa_id[0] for sa_id in user_strategy_account_ids]

        if not user_strategy_account_ids:
            # 사용자가 소유한 StrategyAccount가 없음
            return jsonify({'success': True, 'orders': []})

        # 2. FailedOrderManager를 통한 조회
        failed_orders = failed_order_manager.get_failed_orders(
            strategy_account_id=strategy_account_id,
            symbol=symbol
        )

        # 3. 사용자 소유 StrategyAccount에 속한 주문만 필터링
        filtered_orders = [
            fo for fo in failed_orders
            if fo.strategy_account_id in user_strategy_account_ids
        ]

        # 4. 응답 데이터 구성
        orders = []
        for fo in filtered_orders:
            orders.append({
                'id': fo.id,
                'strategy_account_id': fo.strategy_account_id,
                'symbol': fo.symbol,
                'side': fo.side,
                'order_type': fo.order_type,
                'quantity': str(fo.quantity),  # Decimal → str (JSON 직렬화)
                'price': str(fo.price) if fo.price else None,
                'stop_price': str(fo.stop_price) if fo.stop_price else None,
                'market_type': fo.market_type,
                'reason': fo.reason,
                'exchange_error': fo.exchange_error,
                'retry_count': fo.retry_count,
                'status': fo.status,
                'created_at': fo.created_at.isoformat() if fo.created_at else None,
                'updated_at': fo.updated_at.isoformat() if fo.updated_at else None
            })

        return jsonify({'success': True, 'orders': orders})

    except Exception as e:
        current_app.logger.error(f'실패 주문 조회 실패: {str(e)}')
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


# @FEAT:immediate-order-execution @COMP:route @TYPE:core
@failed_orders_bp.route('/api/failed-orders/<int:failed_order_id>/retry', methods=['POST'])
@login_required
def retry_failed_order(failed_order_id):
    """
    실패한 주문 재시도

    Args:
        failed_order_id (int): 재시도할 FailedOrder의 ID

    Returns:
        200: {
            'success': True,
            'order_id': 'BINANCE_ORDER_12345',
            'message': '재시도 성공'
        }
        400: {
            'success': False,
            'error': '최대 재시도 횟수(5회)를 초과했습니다'
        }
        403: {'success': False, 'error': '권한이 없습니다'}
        404: {'success': False, 'error': '주문을 찾을 수 없습니다'}
        500: {'success': False, 'error': 'Internal server error'}
    """
    try:
        # 1. FailedOrder 조회 (존재 여부 확인)
        failed_order = (
            FailedOrder.query
            .options(
                joinedload(FailedOrder.strategy_account)
                .joinedload(StrategyAccount.strategy)
            )
            .filter_by(id=failed_order_id)
            .first()
        )

        if not failed_order:
            return jsonify({'success': False, 'error': '주문을 찾을 수 없습니다'}), 404

        # 2. 권한 검증: FailedOrder → StrategyAccount → Strategy → User 체인
        if not failed_order.strategy_account or not failed_order.strategy_account.strategy:
            current_app.logger.error(
                f'FailedOrder {failed_order_id} 권한 체크 실패: '
                f'strategy_account 또는 strategy 누락'
            )
            return jsonify({'success': False, 'error': '권한이 없습니다'}), 403

        if failed_order.strategy_account.strategy.user_id != current_user.id:
            return jsonify({'success': False, 'error': '권한이 없습니다'}), 403

        # 3. FailedOrderManager를 통한 재시도
        result = failed_order_manager.retry_failed_order(failed_order_id)

        if result['success']:
            return jsonify({
                'success': True,
                'order_id': result.get('order_id'),
                'message': '재시도 성공'
            })
        else:
            # 실패 원인에 따라 적절한 HTTP 상태 코드 반환
            error_msg = result.get('error', 'Unknown error')

            # 최대 재시도 횟수 초과
            if 'Maximum retry count exceeded' in error_msg:
                return jsonify({'success': False, 'error': error_msg}), 400

            # 기타 실패 (잔고 부족, API 오류 등)
            return jsonify({'success': False, 'error': error_msg}), 400

    except Exception as e:
        current_app.logger.error(f'실패 주문 재시도 실패: {str(e)}')
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


# @FEAT:immediate-order-execution @COMP:route @TYPE:core
@failed_orders_bp.route('/api/failed-orders/<int:failed_order_id>', methods=['DELETE'])
@login_required
def delete_failed_order(failed_order_id):
    """
    실패한 주문 제거 (사용자 수동 제거)

    Args:
        failed_order_id (int): 제거할 FailedOrder의 ID

    Returns:
        200: {
            'success': True,
            'message': '주문이 제거되었습니다'
        }
        403: {'success': False, 'error': '권한이 없습니다'}
        404: {'success': False, 'error': '주문을 찾을 수 없습니다'}
        500: {'success': False, 'error': 'Internal server error'}

    Notes:
        - CSRF Protection: Flask-WTF CSRFProtect가 자동으로 DELETE 요청 검증
        - JavaScript에서 X-CSRFToken 헤더 전송 필요 (Phase 7에서 구현)
    """
    try:
        # 1. FailedOrder 조회 (존재 여부 확인)
        failed_order = (
            FailedOrder.query
            .options(
                joinedload(FailedOrder.strategy_account)
                .joinedload(StrategyAccount.strategy)
            )
            .filter_by(id=failed_order_id)
            .first()
        )

        if not failed_order:
            return jsonify({'success': False, 'error': '주문을 찾을 수 없습니다'}), 404

        # 2. 권한 검증: FailedOrder → StrategyAccount → Strategy → User 체인
        if not failed_order.strategy_account or not failed_order.strategy_account.strategy:
            current_app.logger.error(
                f'FailedOrder {failed_order_id} 권한 체크 실패: '
                f'strategy_account 또는 strategy 누락'
            )
            return jsonify({'success': False, 'error': '권한이 없습니다'}), 403

        if failed_order.strategy_account.strategy.user_id != current_user.id:
            return jsonify({'success': False, 'error': '권한이 없습니다'}), 403

        # 3. FailedOrderManager를 통한 제거
        success = failed_order_manager.remove_failed_order(failed_order_id)

        if success:
            return jsonify({
                'success': True,
                'message': '주문이 제거되었습니다'
            })
        else:
            # remove_failed_order는 FailedOrder를 찾지 못하면 False 반환
            # 하지만 위에서 이미 존재 여부를 확인했으므로 이 경로는 드물게 발생
            return jsonify({'success': False, 'error': '주문 제거 실패'}), 500

    except Exception as e:
        current_app.logger.error(f'실패 주문 제거 실패: {str(e)}')
        return jsonify({'success': False, 'error': 'Internal server error'}), 500
