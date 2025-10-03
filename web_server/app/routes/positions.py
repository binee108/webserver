from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user

from app.constants import OrderStatus
from app.models import Strategy
from app.services.trading import trading_service as position_service
from app.services.strategy_service import strategy_service
from app.services.trading import trading_service as order_service

bp = Blueprint('positions', __name__, url_prefix='/api')

@bp.route('/positions/<int:position_id>/close', methods=['POST'])
@login_required
def close_position(position_id):
    """포지션 청산"""
    try:
        # position_service에서 트랜잭션을 완전히 관리
        result = position_service.close_position_by_id(position_id, current_user.id)
        
        if result.get('success'):
            current_app.logger.info(f'포지션 청산 완료: 포지션 ID {position_id} - 주문 ID: {result.get("order_id")}')
            return jsonify({
                'success': True,
                'message': '포지션이 성공적으로 청산되었습니다.',
                'order_id': result.get('order_id'),
                'filled_quantity': result.get('filled_quantity'),
                'average_price': result.get('average_price'),
                'realized_pnl': result.get('realized_pnl'),
                'fee': result.get('fee')
            })
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', '포지션 청산에 실패했습니다.')
            }), 400
            
    except Exception as e:
        current_app.logger.error(f'포지션 청산 오류: {str(e)}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/open-orders', methods=['GET'])
@login_required
def get_open_orders():
    """사용자의 모든 열린 주문 조회 (Service 계층 사용)"""
    try:
        # Service 계층을 통한 데이터 조회
        result = position_service.get_user_open_orders(current_user.id)
        
        if result.get('success'):
            current_app.logger.info(f'열린 주문 조회 완료: 사용자 {current_user.id}, {len(result.get("open_orders", []))}개 주문')
            return jsonify(result)
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', '데이터 조회에 실패했습니다.')
            }), 500
            
    except Exception as e:
        current_app.logger.error(f'열린 주문 조회 오류: {str(e)}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/open-orders/<string:order_id>/cancel', methods=['POST'])
@login_required
def cancel_open_order(order_id):
    """개별 주문 취소 (Service 계층 사용)"""
    try:
        # Service 계층을 통한 주문 취소
        result = order_service.cancel_order_by_user(order_id, current_user.id)
        
        if result.get('success'):
            current_app.logger.info(f'주문 취소 완료: 주문 ID {order_id}')
            return jsonify({
                'success': True,
                'message': '주문이 성공적으로 취소되었습니다.',
                'order_id': order_id,
                'symbol': result.get('symbol')
            })
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', '주문 취소에 실패했습니다.')
            }), 400
            
    except Exception as e:
        current_app.logger.error(f'주문 취소 오류: {str(e)}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/open-orders/cancel-all', methods=['POST'])
@login_required
def cancel_all_open_orders():
    """전체 또는 특정 조건의 주문 일괄 취소 (Service 계층 사용)"""
    try:
        # 안전한 JSON 파싱
        try:
            data = request.get_json() or {}
        except Exception as json_error:
            # JSON 파싱 실패시 빈 딕셔너리 사용
            current_app.logger.warning(f'JSON 파싱 실패, 빈 딕셔너리 사용: {str(json_error)}')
            data = {}
        
        strategy_id = data.get('strategy_id')
        if strategy_id is None:
            return jsonify({
                'success': False,
                'error': 'strategy_id가 필요합니다.'
            }), 400

        try:
            strategy_id = int(strategy_id)
        except (TypeError, ValueError):
            return jsonify({
                'success': False,
                'error': 'strategy_id 형식이 올바르지 않습니다.'
            }), 400

        strategy = Strategy.query.filter_by(id=strategy_id, user_id=current_user.id).first()
        if not strategy:
            return jsonify({
                'success': False,
                'error': '해당 전략에 대한 권한이 없습니다.'
            }), 403

        account_id = data.get('account_id')
        if account_id is not None:
            try:
                account_id = int(account_id)
            except (TypeError, ValueError):
                return jsonify({
                    'success': False,
                    'error': 'account_id 형식이 올바르지 않습니다.'
                }), 400

        # Service 계층을 통한 일괄 취소
        result = order_service.cancel_all_orders_by_user(
            user_id=current_user.id,
            strategy_id=strategy_id,
            account_id=account_id,
            symbol=data.get('symbol')
        )
        
        success_count = len(result.get('cancelled_orders', []))
        failed_count = len(result.get('failed_orders', []))
        current_app.logger.info(f'일괄 주문 취소 결과: 성공 {success_count}개, 실패 {failed_count}개')

        if result.get('success'):
            return jsonify(result)

        status_code = 207 if failed_count and success_count else 400
        return jsonify(result), status_code
            
    except Exception as e:
        current_app.logger.error(f'일괄 주문 취소 오류: {str(e)}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/positions-with-orders', methods=['GET'])
@login_required  
def get_positions_with_orders():
    """포지션과 열린 주문 통합 조회 (Service 계층 사용)"""
    try:
        current_app.logger.info(f'포지션/주문 통합 조회 요청: 사용자 {current_user.id}')
        
        # position_service의 통합 조회 함수 사용
        result = position_service.get_user_open_orders_with_positions(current_user.id)
        
        if result.get('success'):
            current_app.logger.info(f'포지션/주문 통합 조회 완료: 사용자 {current_user.id}')
            return jsonify(result)
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', '데이터 조회에 실패했습니다.')
            }), 500
            
    except Exception as e:
        current_app.logger.error(f'포지션/주문 통합 조회 오류: {str(e)}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/symbol/<string:symbol>/positions-orders', methods=['GET'])
@login_required
def get_symbol_positions_orders(symbol):
    """특정 심볼의 포지션과 열린 주문 조회 (Service 계층 사용)"""
    try:
        current_app.logger.info(f'심볼별 포지션/주문 조회 요청: 사용자 {current_user.id}, 심볼: {symbol}')
        
        # position_service의 심볼별 조회 함수 사용
        result = position_service.get_position_and_orders_by_symbol(current_user.id, symbol)
        
        if result.get('success'):
            current_app.logger.info(f'심볼별 포지션/주문 조회 완료: 사용자 {current_user.id}, 심볼: {symbol}')
            return jsonify(result)
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', '데이터 조회에 실패했습니다.')
            }), 500
            
    except Exception as e:
        current_app.logger.error(f'심볼별 포지션/주문 조회 오류: {str(e)}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/open-orders/status-update', methods=['POST'])
@login_required
def trigger_order_status_update():
    """열린 주문 상태 수동 업데이트 트리거 (Service 계층 사용)"""
    try:
        current_app.logger.info(f'수동 주문 상태 업데이트 요청: 사용자 {current_user.id}')
        
        # order_service를 통한 상태 업데이트
        result = order_service.update_open_orders_status()
        
        if result.get('success'):
            return jsonify({
                'success': True,
                'message': '주문 상태 업데이트가 완료되었습니다.',
                'processed_orders': result.get('processed_orders', 0),
                'filled_orders': result.get('filled_orders', 0),
                'cancelled_orders': result.get('cancelled_orders', 0)
            })
        else:
            return jsonify({
                'success': False,
                'error': '주문 상태 업데이트에 실패했습니다.'
            }), 500
            
    except Exception as e:
        current_app.logger.error(f'수동 주문 상태 업데이트 오류: {str(e)}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/events/stream')
@login_required
def event_stream():
    """실시간 포지션/주문 업데이트 이벤트 스트림 (SSE)"""
    try:
        current_app.logger.info(f'🔗 SSE 연결 요청 - 사용자: {current_user.id}, URL: /api/events/stream')
        
        from app.services.event_service import event_service
        
        # SSE 스트림 반환
        response = event_service.get_event_stream(current_user.id)
        current_app.logger.info(f'✅ SSE 스트림 생성 완료 - 사용자: {current_user.id}')
        return response
        
    except Exception as e:
        current_app.logger.error(f'이벤트 스트림 생성 실패 - 사용자: {current_user.id}, 오류: {str(e)}')
        # SSE 형식의 오류 메시지 반환
        from flask import Response
        return Response(
            f"data: {{'type': 'error', 'message': '{str(e)}'}}\n\n",
            mimetype='text/event-stream'
        )

@bp.route('/auth/check')
def check_auth():
    """로그인 상태 확인 API (SSE 연결 전 체크용)"""
    try:
        from flask_login import current_user
        
        if current_user.is_authenticated:
            return jsonify({
                'authenticated': True,
                'user_id': current_user.id,
                'username': current_user.username
            })
        else:
            return jsonify({
                'authenticated': False
            }), 401
            
    except Exception as e:
        current_app.logger.error(f'인증 상태 확인 실패: {str(e)}')
        return jsonify({
            'authenticated': False,
            'error': str(e)
        }), 500

@bp.route('/events/stats')
@login_required
def event_stats():
    """이벤트 서비스 통계 조회 (관리자용)"""
    try:
        from app.services.event_service import event_service
        
        # 관리자 권한 확인 (필요시)
        if not current_user.is_admin:
            return jsonify({
                'success': False,
                'error': '관리자 권한이 필요합니다.'
            }), 403
        
        stats = event_service.get_statistics()
        
        return jsonify({
            'success': True,
            'stats': stats
        })
        
    except Exception as e:
        current_app.logger.error(f'이벤트 통계 조회 실패: {str(e)}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/strategies/<int:strategy_id>/positions', methods=['GET'])
@login_required
def get_strategy_positions(strategy_id):
    """특정 전략의 포지션 조회 (동적 업데이트용)"""
    try:
        from app.models import Strategy, StrategyPosition, StrategyAccount
        from sqlalchemy.orm import joinedload
        
        # 전략 존재 확인
        strategy = Strategy.query.filter_by(id=strategy_id).first()
        if not strategy:
            return jsonify({
                'success': False,
                'error': '전략을 찾을 수 없습니다.'
            }), 404
        
        # 권한 확인: 소유자이거나, 해당 전략에 내 계좌가 연결되어 있어야 함
        from app.models import Account
        is_owner = (strategy.user_id == current_user.id)
        if not is_owner:
            has_subscription = StrategyAccount.query.join(Account).filter(
                StrategyAccount.strategy_id == strategy_id,
                Account.user_id == current_user.id
            ).count() > 0
            if not has_subscription:
                return jsonify({
                    'success': False,
                    'error': '접근 권한이 없습니다.'
                }), 403
        
        # 해당 전략의 활성 포지션만 조회 (항상 내 계좌 기준으로 제한)
        positions_query = StrategyPosition.query.join(StrategyAccount).join(Account).options(
            joinedload(StrategyPosition.strategy_account).joinedload(StrategyAccount.account)
        ).filter(
            StrategyAccount.strategy_id == strategy_id,
            Account.user_id == current_user.id,
            StrategyPosition.quantity != 0
        ).all()
        
        # StrategyPosition 객체들을 딕셔너리로 변환
        positions = []
        for pos in positions_query:
            position_dict = {
                'position_id': pos.id, # 'id' 대신 'position_id' 사용 (SSE 이벤트와 일치)
                'symbol': pos.symbol,
                'quantity': float(pos.quantity),
                'entry_price': float(pos.entry_price) if pos.entry_price else 0.0,
                'account': {
                    'name': pos.strategy_account.account.name if pos.strategy_account and pos.strategy_account.account else 'Unknown',
                    'exchange': pos.strategy_account.account.exchange if pos.strategy_account and pos.strategy_account.account else 'unknown'
                } if pos.strategy_account else None,
                'last_updated': pos.last_updated.isoformat() if pos.last_updated else None
            }
            positions.append(position_dict)
        
        current_app.logger.info(f'전략 {strategy_id} 포지션 조회 완료: {len(positions)}개')
        
        return jsonify({
            'success': True,
            'positions': positions,
            'total_count': len(positions)
        })
        
    except Exception as e:
        current_app.logger.error(f'전략 포지션 조회 실패: {str(e)}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500 

# 구독 전략용: 내 계좌의 열린 주문 조회
@bp.route('/strategies/<int:strategy_id>/my/open-orders', methods=['GET'])
@login_required
def get_my_strategy_open_orders(strategy_id):
    try:
        from app.models import Strategy, OpenOrder, StrategyAccount, Account
        from sqlalchemy.orm import joinedload

        strategy = Strategy.query.filter_by(id=strategy_id).first()
        if not strategy:
            return jsonify({'success': False, 'error': '전략을 찾을 수 없습니다.'}), 404

        open_orders = (
            OpenOrder.query
            .join(StrategyAccount)
            .join(Account)
            .options(
                joinedload(OpenOrder.strategy_account)
                .joinedload(StrategyAccount.account)
            )
            .filter(
                StrategyAccount.strategy_id == strategy_id,
                Account.user_id == current_user.id,
                OpenOrder.status.in_(OrderStatus.get_open_statuses())
            )
            .all()
        )

        orders = []
        for order in open_orders:
            orders.append({
                'order_id': order.exchange_order_id,  # 통일된 명명: order_id 사용
                'symbol': order.symbol,
                'side': order.side,
                'order_type': order.order_type,
                'price': float(order.price) if order.price is not None else None,
                'stop_price': float(order.stop_price) if order.stop_price is not None else None,
                'quantity': float(order.quantity) if order.quantity is not None else 0.0,
                'filled_quantity': float(order.filled_quantity) if order.filled_quantity is not None else 0.0,
                'status': order.status,
                'market_type': order.market_type,
                'created_at': order.created_at.isoformat() if order.created_at else None,
                'account_name': order.strategy_account.account.name if order.strategy_account and order.strategy_account.account else 'Unknown',
                'exchange': order.strategy_account.account.exchange if order.strategy_account and order.strategy_account.account else 'unknown',
                'account': {
                    'name': order.strategy_account.account.name if order.strategy_account and order.strategy_account.account else 'Unknown',
                    'exchange': order.strategy_account.account.exchange if order.strategy_account and order.strategy_account.account else 'unknown'
                } if order.strategy_account else None
            })

        return jsonify({'success': True, 'open_orders': orders, 'total_count': len(orders)})
    except Exception as e:
        current_app.logger.error(f'구독 전략 열린 주문 조회 실패: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 500