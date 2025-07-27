from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from datetime import datetime
from app import db

bp = Blueprint('system', __name__, url_prefix='/api')

@bp.route('/system/health', methods=['GET'])
def health_check():
    """시스템 헬스 체크 엔드포인트"""
    try:
        # 데이터베이스 연결 확인
        from sqlalchemy import text
        db.session.execute(text('SELECT 1'))
        db_status = 'healthy'
    except Exception as e:
        current_app.logger.error(f'데이터베이스 연결 오류: {str(e)}')
        db_status = 'unhealthy'
    
    # 텔레그램 서비스 상태 확인
    try:
        from app.services.telegram_service import telegram_service
        telegram_status = 'enabled' if telegram_service.is_enabled() else 'disabled'
    except Exception:
        telegram_status = 'error'
    
    return jsonify({
        'status': 'healthy' if db_status == 'healthy' else 'unhealthy',
        'timestamp': datetime.utcnow().isoformat(),
        'version': '1.0.0',
        'services': {
            'database': db_status,
            'telegram': telegram_status
        }
    })

@bp.route('/system/test-telegram', methods=['POST'])
@login_required
def test_telegram():
    """텔레그램 연결 테스트 엔드포인트"""
    try:
        if not current_user.is_admin:
            return jsonify({
                'success': False,
                'error': '관리자 권한이 필요합니다.'
            }), 403
        
        from app.services.telegram_service import telegram_service
        result = telegram_service.test_connection()
        return jsonify(result), 200 if result['success'] else 400
    except Exception as e:
        current_app.logger.error(f'텔레그램 테스트 오류: {str(e)}')
        return jsonify({
            'success': False,
            'message': f'텔레그램 테스트 실패: {str(e)}'
        }), 500

@bp.route('/system/scheduler-status', methods=['GET'])
@login_required
def get_scheduler_status():
    """APScheduler 작업 상태 조회 (개선된 버전)"""
    try:
        from app import scheduler
        
        if not current_user.is_admin:
            return jsonify({
                'success': False,
                'error': '관리자 권한이 필요합니다.'
            }), 403
        
        # 스케줄러 상태
        scheduler_running = scheduler.running if scheduler else False
        
        # 등록된 작업 목록
        jobs = []
        if scheduler and scheduler_running:
            for job in scheduler.get_jobs():
                jobs.append({
                    'id': job.id,
                    'name': job.name,
                    'next_run_time': job.next_run_time.isoformat() if job.next_run_time else None,
                    'trigger': str(job.trigger),
                    'func_name': job.func.__name__ if hasattr(job.func, '__name__') else str(job.func)
                })
        
        # 추가 상태 정보
        status_info = {
            'is_running': scheduler_running,
            'jobs_count': len(jobs),
            'jobs': jobs,
            'last_check': datetime.utcnow().isoformat()
        }
        
        return jsonify({
            'success': True,
            'scheduler_running': scheduler_running,
            'status': status_info
        })
        
    except Exception as e:
        current_app.logger.error(f'스케줄러 상태 조회 오류: {str(e)}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/system/scheduler-control', methods=['POST'])
@login_required
def control_scheduler():
    """APScheduler 작업 제어 (시작/중지/재시작)"""
    try:
        from app import scheduler
        
        if not current_user.is_admin:
            return jsonify({
                'success': False,
                'error': '관리자 권한이 필요합니다.'
            }), 403
        
        data = request.get_json()
        action = data.get('action')  # 'start', 'stop', 'restart'
        
        if action == 'start':
            if not scheduler.running:
                scheduler.start()
                message = 'APScheduler가 시작되었습니다.'
            else:
                message = 'APScheduler가 이미 실행 중입니다.'
                
        elif action == 'stop':
            if scheduler.running:
                scheduler.shutdown(wait=False)
                message = 'APScheduler가 중지되었습니다.'
            else:
                message = 'APScheduler가 이미 중지되어 있습니다.'
                
        elif action == 'restart':
            if scheduler.running:
                scheduler.shutdown(wait=False)
            scheduler.start()
            message = 'APScheduler가 재시작되었습니다.'
            
        else:
            return jsonify({
                'success': False,
                'error': '유효하지 않은 액션입니다. (start, stop, restart 중 선택)'
            }), 400
        
        current_app.logger.info(f'스케줄러 제어: {action} - {message}')
        
        return jsonify({
            'success': True,
            'message': message,
            'scheduler_running': scheduler.running
        })
        
    except Exception as e:
        current_app.logger.error(f'스케줄러 제어 오류: {str(e)}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/system/trigger-job', methods=['POST'])
@login_required
def trigger_job():
    """특정 백그라운드 작업 수동 실행"""
    try:
        from app import scheduler
        from app.services.order_service import order_service
        from app.services.position_service import position_service
        from app.services.analytics_service import analytics_service
        from app.services.telegram_service import telegram_service
        
        if not current_user.is_admin:
            return jsonify({
                'success': False,
                'error': '관리자 권한이 필요합니다.'
            }), 403
        
        data = request.get_json()
        job_type = data.get('job_type')  # 'update_orders', 'calculate_pnl', 'daily_summary'
        
        if job_type == 'update_orders':
            order_service.update_open_orders_status()
            message = '미체결 주문 상태 업데이트가 완료되었습니다.'
            
        elif job_type == 'calculate_pnl':
            position_service.calculate_unrealized_pnl()
            message = '미실현 손익 계산이 완료되었습니다.'
            
        elif job_type == 'daily_summary':
            # 모든 계정에 대한 일일 요약 생성 (예시로 첫 번째 계정만)
            from app.models import Account
            accounts = Account.query.filter_by(is_active=True).all()
            summary_data = {}
            for account in accounts:
                try:
                    account_summary = analytics_service.get_daily_summary(account.id)
                    summary_data[account.name] = account_summary
                except Exception as e:
                    current_app.logger.error(f'계정 {account.name} 일일 요약 생성 실패: {str(e)}')
            
            telegram_service.send_daily_summary(summary_data)
            message = '일일 요약 보고서가 전송되었습니다.'
            
        else:
            return jsonify({
                'success': False,
                'error': '유효하지 않은 작업 타입입니다.'
            }), 400
        
        current_app.logger.info(f'수동 작업 실행: {job_type} - {message}')
        
        return jsonify({
            'success': True,
            'message': message
        })
        
    except Exception as e:
        current_app.logger.error(f'수동 작업 실행 오류: {str(e)}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/system/cache-stats', methods=['GET'])
@login_required
def cache_stats():
    """캐시 통계 조회"""
    try:
        if not current_user.is_admin:
            return jsonify({
                'success': False,
                'error': '관리자 권한이 필요합니다.'
            }), 403
        
        from app.services.exchange_service import exchange_service
        
        stats = exchange_service.get_cache_stats()
        
        return jsonify({
            'success': True,
            'cache_stats': stats,
            'message': 'Market 캐시를 통한 API 호출 최적화 활성화됨'
        }), 200
    except Exception as e:
        current_app.logger.error(f'캐시 통계 조회 오류: {str(e)}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/system/cache-clear', methods=['POST'])
@login_required
def clear_cache():
    """캐시 정리"""
    try:
        if not current_user.is_admin:
            return jsonify({
                'success': False,
                'error': '관리자 권한이 필요합니다.'
            }), 403
        
        from app.services.exchange_service import exchange_service
        
        data = request.get_json() or {}
        exchange_name = data.get('exchange')
        symbol = data.get('symbol')
        cache_type = data.get('type', 'all')  # 'market', 'exchange', 'all'
        
        if cache_type == 'market':
            exchange_service.clear_market_cache(exchange_name, symbol)
            message = f"Market 캐시 정리 완료 - 거래소: {exchange_name or 'ALL'}, 심볼: {symbol or 'ALL'}"
        elif cache_type == 'exchange':
            exchange_service.clear_cache()
            message = "거래소 연결 캐시 정리 완료"
        else:
            exchange_service.clear_cache()
            exchange_service.clear_market_cache()
            message = "모든 캐시 정리 완료"
        
        current_app.logger.info(f'캐시 정리: {cache_type} - {message}')
        
        return jsonify({
            'success': True,
            'message': message
        }), 200
    except Exception as e:
        current_app.logger.error(f'캐시 정리 오류: {str(e)}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500 