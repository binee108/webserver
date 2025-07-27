from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user

from app.services.position_service import position_service
from app.services.strategy_service import strategy_service
from app.services.order_service import order_service

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
        
        # Service 계층을 통한 일괄 취소
        result = order_service.cancel_all_orders_by_user(
            user_id=current_user.id,
            account_id=data.get('account_id'),
            symbol=data.get('symbol'),
            strategy_id=data.get('strategy_id')
        )
        
        if result.get('success'):
            success_count = len(result.get('cancelled_orders', []))
            failed_count = len(result.get('failed_orders', []))
            current_app.logger.info(f'일괄 주문 취소 완료: 성공 {success_count}개, 실패 {failed_count}개')
            
            return jsonify(result)
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', '일괄 취소에 실패했습니다.')
            }), 400
            
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
        from app.services.event_service import event_service
        
        current_app.logger.info(f'사용자 {current_user.id} 이벤트 스트림 연결 요청')
        
        # SSE 스트림 반환
        return event_service.get_event_stream(current_user.id)
        
    except Exception as e:
        current_app.logger.error(f'이벤트 스트림 생성 실패 - 사용자: {current_user.id}, 오류: {str(e)}')
        # SSE 형식의 오류 메시지 반환
        from flask import Response
        return Response(
            f"data: {{'type': 'error', 'message': '{str(e)}'}}\n\n",
            mimetype='text/event-stream'
        )

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