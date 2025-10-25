"""
Dashboard API Routes

@FEAT:api-gateway @FEAT:analytics @COMP:route @TYPE:core
Provides dashboard statistics and recent trades data for authenticated users.
"""

from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user

from app.services.analytics import analytics_service as dashboard_service
from app.services.analytics import AnalyticsError as DashboardError

bp = Blueprint('dashboard', __name__, url_prefix='/api')

# @FEAT:api-gateway @FEAT:analytics @COMP:route @TYPE:core
@bp.route('/dashboard/stats', methods=['GET'])
@login_required
def get_dashboard_stats():
    """대시보드 통계 데이터 조회"""
    try:
        # 통합된 get_user_dashboard_stats 메서드 사용
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

# @FEAT:api-gateway @FEAT:analytics @COMP:route @TYPE:core
@bp.route('/dashboard/recent-trades', methods=['GET'])
@login_required
def get_recent_trades():
    """최근 거래 내역 조회 (페이지네이션 지원)"""
    try:
        limit = request.args.get('limit', 20, type=int)
        offset = request.args.get('offset', 0, type=int)

        # 보안: limit 최대값 제한
        limit = min(limit, 100)

        trades = dashboard_service.get_user_recent_trades(
            current_user.id,
            limit=limit,
            offset=offset
        )

        return jsonify({
            'success': True,
            'trades': trades,
            'limit': limit,
            'offset': offset,
            'has_more': len(trades) == limit  # 더 있는지 여부
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
