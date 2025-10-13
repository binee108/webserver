"""
헬스체크 엔드포인트

@FEAT:health-monitoring @COMP:route @TYPE:core
Health check endpoints for system monitoring and orchestration platforms.
"""
from flask import Blueprint, jsonify
from app import db
from datetime import datetime

health_bp = Blueprint('health', __name__)

# @FEAT:health-monitoring @COMP:route @TYPE:core
@health_bp.route('/health', methods=['GET'])
def health_check():
    """
    시스템 헬스체크 엔드포인트
    - 기본 Flask 앱 상태
    - 데이터베이스 연결 상태
    - 현재 시간 정보
    """
    try:
        # 데이터베이스 연결 테스트
        from sqlalchemy import text
        db.session.execute(text('SELECT 1'))
        db_status = "healthy"
    except Exception as e:
        db_status = f"error: {str(e)}"

    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'database': db_status,
        'service': 'trading-system'
    }), 200

# @FEAT:health-monitoring @COMP:route @TYPE:core
@health_bp.route('/health/ready', methods=['GET'])
def readiness_check():
    """
    서비스 준비상태 확인
    - 데이터베이스 연결 필수
    - 모든 필수 서비스 준비 확인
    """
    try:
        # 데이터베이스 연결 테스트
        from sqlalchemy import text
        db.session.execute(text('SELECT 1'))

        # 필요시 추가 서비스 체크 (Redis, 외부 API 등)
        return jsonify({
            'status': 'ready',
            'timestamp': datetime.utcnow().isoformat(),
            'checks': {
                'database': 'ok'
            }
        }), 200

    except Exception as e:
        return jsonify({
            'status': 'not_ready',
            'timestamp': datetime.utcnow().isoformat(),
            'error': str(e)
        }), 503

# @FEAT:health-monitoring @COMP:route @TYPE:core
@health_bp.route('/health/live', methods=['GET'])
def liveness_check():
    """
    서비스 활성상태 확인 (간단한 응답)
    """
    return jsonify({
        'status': 'alive',
        'timestamp': datetime.utcnow().isoformat()
    }), 200
