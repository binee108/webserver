from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user

from app.services.dashboard_service import dashboard_service, DashboardError

bp = Blueprint('dashboard', __name__, url_prefix='/api')

@bp.route('/dashboard/stats', methods=['GET'])
@login_required
def get_dashboard_stats():
    """대시보드 통계 데이터 조회"""
    try:
        stats = dashboard_service.get_user_dashboard_stats(current_user.id)
        
        return jsonify({
            'success': True,
            'stats': stats
        })
        
    except DashboardError as e:
        current_app.logger.error(f'대시보드 통계 조회 오류: {str(e)}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    except Exception as e:
        current_app.logger.error(f'대시보드 통계 조회 시스템 오류: {str(e)}')
        return jsonify({
            'success': False,
            'error': '시스템 오류가 발생했습니다.'
        }), 500

@bp.route('/dashboard/recent-trades', methods=['GET'])
@login_required
def get_recent_trades():
    """최근 거래 내역 조회"""
    try:
        limit = request.args.get('limit', 10, type=int)
        
        trades = dashboard_service.get_user_recent_trades(current_user.id, limit)
        
        return jsonify({
            'success': True,
            'trades': trades
        })
        
    except DashboardError as e:
        current_app.logger.error(f'최근 거래 내역 조회 오류: {str(e)}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    except Exception as e:
        current_app.logger.error(f'최근 거래 내역 조회 시스템 오류: {str(e)}')
        return jsonify({
            'success': False,
            'error': '시스템 오류가 발생했습니다.'
        }), 500 