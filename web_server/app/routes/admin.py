from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from functools import wraps
from app import db, csrf
from app.models import User, Account, Strategy, StrategyAccount
from app.services.telegram_service import telegram_service
import secrets
import string

bp = Blueprint('admin', __name__, url_prefix='/admin')

def admin_required(f):
    """관리자 권한 확인 데코레이터"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('관리자 권한이 필요합니다.', 'error')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

@bp.route('/')
@login_required
@admin_required
def index():
    """관리자 대시보드"""
    return redirect(url_for('admin.users'))

@bp.route('/users')
@login_required
@admin_required
def users():
    """사용자 관리 페이지"""
    users = User.query.all()
    pending_users = User.query.filter_by(is_active=False).all()
    
    # 통계 정보
    approved_users_count = User.query.filter_by(is_active=True).count()
    pending_users_count = User.query.filter_by(is_active=False).count()
    admin_users_count = User.query.filter_by(is_admin=True).count()
    
    return render_template('admin/users.html', 
                         users=users,
                         pending_users=pending_users,
                         approved_users_count=approved_users_count,
                         pending_users_count=pending_users_count,
                         admin_users_count=admin_users_count)

@bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    """사용자 정보 수정"""
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        is_active = request.form.get('is_active') == 'on'
        is_admin = request.form.get('is_admin') == 'on'
        must_change_password = request.form.get('must_change_password') == 'on'
        
        # 입력 검증
        if not username:
            flash('사용자명을 입력해주세요.', 'error')
            return render_template('admin/edit_user.html', user=user)
        
        # 중복 확인 (자기 자신 제외)
        existing_user = User.query.filter(User.username == username, User.id != user_id).first()
        if existing_user:
            flash('이미 존재하는 사용자명입니다.', 'error')
            return render_template('admin/edit_user.html', user=user)
        
        if email:
            existing_email = User.query.filter(User.email == email, User.id != user_id).first()
            if existing_email:
                flash('이미 존재하는 이메일입니다.', 'error')
                return render_template('admin/edit_user.html', user=user)
        
        # 자기 자신의 관리자 권한은 제거할 수 없음
        if user.id == current_user.id and not is_admin:
            flash('자기 자신의 관리자 권한은 제거할 수 없습니다.', 'error')
            return render_template('admin/edit_user.html', user=user)
        
        # 자기 자신은 비활성화할 수 없음
        if user.id == current_user.id and not is_active:
            flash('자기 자신은 비활성화할 수 없습니다.', 'error')
            return render_template('admin/edit_user.html', user=user)
        
        try:
            user.username = username
            user.email = email
            user.is_active = is_active
            user.is_admin = is_admin
            user.must_change_password = must_change_password
            db.session.commit()
            flash('사용자 정보가 수정되었습니다.', 'success')
            return redirect(url_for('admin.users'))
        except Exception as e:
            db.session.rollback()
            flash('사용자 정보 수정 중 오류가 발생했습니다.', 'error')
    
    return render_template('admin/edit_user.html', user=user)

@bp.route('/users/<int:user_id>/change-password', methods=['GET', 'POST'])
@login_required
@admin_required
def change_user_password(user_id):
    """사용자 비밀번호 변경"""
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        must_change = request.form.get('must_change_password') == 'on'
        
        # 입력 검증
        if not new_password or not confirm_password:
            flash('새 비밀번호를 입력해주세요.', 'error')
            return render_template('admin/change_user_password.html', user=user)
        
        if new_password != confirm_password:
            flash('비밀번호가 일치하지 않습니다.', 'error')
            return render_template('admin/change_user_password.html', user=user)
        
        if len(new_password) < 6:
            flash('비밀번호는 최소 6자 이상이어야 합니다.', 'error')
            return render_template('admin/change_user_password.html', user=user)
        
        try:
            user.set_password(new_password)
            user.must_change_password = must_change
            db.session.commit()
            flash(f'{user.username} 사용자의 비밀번호가 변경되었습니다.', 'success')
            return redirect(url_for('admin.users'))
        except Exception as e:
            db.session.rollback()
            flash('비밀번호 변경 중 오류가 발생했습니다.', 'error')
    
    return render_template('admin/change_user_password.html', user=user)

@bp.route('/change-password', methods=['GET', 'POST'])
@login_required
@admin_required
def change_admin_password():
    """관리자 자신의 비밀번호 변경"""
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        # 입력 검증
        if not all([current_password, new_password, confirm_password]):
            flash('모든 필드를 입력해주세요.', 'error')
            return render_template('admin/change_admin_password.html')
        
        if not current_user.check_password(current_password):
            flash('현재 비밀번호가 올바르지 않습니다.', 'error')
            return render_template('admin/change_admin_password.html')
        
        if new_password != confirm_password:
            flash('새 비밀번호가 일치하지 않습니다.', 'error')
            return render_template('admin/change_admin_password.html')
        
        if len(new_password) < 6:
            flash('비밀번호는 최소 6자 이상이어야 합니다.', 'error')
            return render_template('admin/change_admin_password.html')
        
        try:
            current_user.set_password(new_password)
            current_user.must_change_password = False  # 비밀번호 변경 완료
            db.session.commit()
            flash('비밀번호가 성공적으로 변경되었습니다.', 'success')
            return redirect(url_for('admin.users'))
        except Exception as e:
            db.session.rollback()
            flash('비밀번호 변경 중 오류가 발생했습니다.', 'error')
    
    return render_template('admin/change_admin_password.html')

@bp.route('/users/<int:user_id>/toggle-active', methods=['POST'])
@login_required
@admin_required
@csrf.exempt
def toggle_user_active(user_id):
    """사용자 활성화/비활성화 토글"""
    user = User.query.get_or_404(user_id)
    
    # 자기 자신은 비활성화할 수 없음
    if user.id == current_user.id:
        return jsonify({
            'success': False,
            'message': '자기 자신은 비활성화할 수 없습니다.'
        }), 400
    
    user.is_active = not user.is_active
    db.session.commit()
    
    status = '활성화' if user.is_active else '비활성화'
    flash(f'{user.username} 사용자가 {status}되었습니다.', 'success')
    
    return jsonify({
        'success': True,
        'message': f'사용자가 {status}되었습니다.',
        'is_active': user.is_active
    })

@bp.route('/users/<int:user_id>/toggle-admin', methods=['POST'])
@login_required
@admin_required
@csrf.exempt
def toggle_user_admin(user_id):
    """사용자 관리자 권한 토글"""
    user = User.query.get_or_404(user_id)
    
    # 자기 자신의 관리자 권한은 제거할 수 없음
    if user.id == current_user.id:
        return jsonify({
            'success': False,
            'message': '자기 자신의 관리자 권한은 제거할 수 없습니다.'
        }), 400
    
    user.is_admin = not user.is_admin
    db.session.commit()
    
    status = '부여' if user.is_admin else '제거'
    flash(f'{user.username} 사용자의 관리자 권한이 {status}되었습니다.', 'success')
    
    return jsonify({
        'success': True,
        'message': f'관리자 권한이 {status}되었습니다.',
        'is_admin': user.is_admin
    })

@bp.route('/users/<int:user_id>/approve', methods=['POST'])
@login_required
@admin_required
@csrf.exempt
def approve_user(user_id):
    """사용자 승인"""
    try:
        from flask import current_app
        current_app.logger.info(f'사용자 승인 요청: user_id={user_id}, 요청자={current_user.username}')
        
        user = User.query.get_or_404(user_id)
        current_app.logger.info(f'사용자 정보: username={user.username}, is_active={user.is_active}')
        
        if user.is_active:
            current_app.logger.warning(f'이미 승인된 사용자 승인 시도: {user.username}')
            return jsonify({
                'success': False,
                'message': '이미 승인된 사용자입니다.'
            }), 400
        
        user.is_active = True
        db.session.commit()
        current_app.logger.info(f'사용자 승인 완료: {user.username}')
        
        return jsonify({
            'success': True,
            'message': f'{user.username} 사용자가 승인되었습니다.'
        })
        
    except Exception as e:
        current_app.logger.error(f'사용자 승인 중 오류 발생: {str(e)}', exc_info=True)
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'승인 중 오류가 발생했습니다: {str(e)}'
        }), 500

@bp.route('/users/<int:user_id>/reject', methods=['POST'])
@login_required
@admin_required
@csrf.exempt
def reject_user(user_id):
    """사용자 가입 거부 (계정 삭제)"""
    try:
        user = User.query.get_or_404(user_id)
        
        # 자기 자신은 삭제할 수 없음
        if user.id == current_user.id:
            return jsonify({
                'success': False,
                'message': '자기 자신은 삭제할 수 없습니다.'
            }), 400
        
        username = user.username
        db.session.delete(user)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'{username} 사용자의 가입이 거부되어 계정이 삭제되었습니다.'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'거부 처리 중 오류가 발생했습니다: {str(e)}'
        }), 500

@bp.route('/users/<int:user_id>/reset-password', methods=['POST'])
@login_required
@admin_required
@csrf.exempt
def reset_user_password(user_id):
    """사용자 비밀번호 초기화"""
    try:
        user = User.query.get_or_404(user_id)
        
        # 임시 비밀번호 생성 (8자리)
        temp_password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(8))
        
        user.set_password(temp_password)
        user.must_change_password = True  # 다음 로그인 시 비밀번호 변경 강제
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'{user.username} 사용자의 비밀번호가 초기화되었습니다.',
            'temp_password': temp_password
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'비밀번호 초기화 중 오류가 발생했습니다: {str(e)}'
        }), 500

@bp.route('/users/<int:user_id>', methods=['DELETE'])
@login_required
@admin_required
@csrf.exempt
def delete_user(user_id):
    """사용자 삭제"""
    try:
        user = User.query.get_or_404(user_id)
        
        # 자기 자신은 삭제할 수 없음
        if user.id == current_user.id:
            return jsonify({
                'success': False,
                'message': '자기 자신은 삭제할 수 없습니다.'
            }), 400
        
        username = user.username
        db.session.delete(user)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'{username} 사용자가 삭제되었습니다.'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'사용자 삭제 중 오류가 발생했습니다: {str(e)}'
        }), 500

@bp.route('/system')
@login_required
@admin_required
def system():
    """시스템 모니터링 페이지"""
    try:
        from app import scheduler
        from app.services.exchange_service import exchange_service  # 🆕 precision 캐시 통계용
        
        # 스케줄러 상태
        scheduler_running = scheduler.running if scheduler else False
        
        # 등록된 작업 목록
        jobs = []
        if scheduler and scheduler_running:
            for job in scheduler.get_jobs():
                jobs.append({
                    'id': job.id,
                    'name': job.name,
                    'next_run_time': job.next_run_time,
                    'trigger': str(job.trigger),
                    'func_name': job.func.__name__ if hasattr(job.func, '__name__') else str(job.func)
                })
        
        # 시스템 통계
        stats = {
            'total_users': User.query.count(),
            'active_users': User.query.filter_by(is_active=True).count(),
            'total_accounts': Account.query.count(),
            'active_accounts': Account.query.filter_by(is_active=True).count(),
            'total_strategies': Strategy.query.count(),
            'active_strategies': Strategy.query.filter_by(is_active=True).count(),
        }
        
        # 🆕 Precision 캐시 통계 추가
        precision_stats = exchange_service.get_precision_cache_stats()
        
        return render_template('admin/system.html', 
                             scheduler_running=scheduler_running,
                             jobs=jobs,
                             stats=stats,
                             precision_stats=precision_stats)  # 🆕 precision 통계 추가
                             
    except Exception as e:
        flash(f'시스템 정보 조회 중 오류가 발생했습니다: {str(e)}', 'error')
        return render_template('admin/system.html', 
                             scheduler_running=False,
                             jobs=[],
                             stats={},
                             precision_stats={})  # 🆕 빈 precision 통계

@bp.route('/system/precision-cache/clear', methods=['POST'])
@login_required
@admin_required
@csrf.exempt
def clear_precision_cache():
    """🆕 Precision 캐시 수동 정리"""
    try:
        from app.services.exchange_service import exchange_service
        
        exchange_name = request.json.get('exchange_name') if request.is_json else None
        
        exchange_service.clear_precision_cache(exchange_name)
        
        message = f'{exchange_name} precision 캐시 정리 완료' if exchange_name else 'Precision 캐시 전체 정리 완료'
        
        return jsonify({
            'success': True,
            'message': message
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Precision 캐시 정리 실패: {str(e)}'
        }), 500

@bp.route('/system/precision-cache/warmup', methods=['POST'])
@login_required
@admin_required
@csrf.exempt
def warmup_precision_cache():
    """🆕 Precision 캐시 수동 웜업"""
    try:
        from app.services.exchange_service import exchange_service
        
        # 백그라운드 웜업 실행
        exchange_service.warm_up_precision_cache()
        
        # 웜업 완료 후 통계 조회
        stats = exchange_service.get_precision_cache_stats()
        
        return jsonify({
            'success': True,
            'message': 'Precision 캐시 웜업 완료',
            'stats': stats
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Precision 캐시 웜업 실패: {str(e)}'
        }), 500

@bp.route('/system/precision-cache/stats')
@login_required
@admin_required
def get_precision_cache_stats():
    """🆕 Precision 캐시 통계 실시간 조회"""
    try:
        from app.services.exchange_service import exchange_service
        
        stats = exchange_service.get_precision_cache_stats()
        
        return jsonify({
            'success': True,
            'stats': stats
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Precision 캐시 통계 조회 실패: {str(e)}'
        }), 500

@bp.route('/users/<int:user_id>/telegram-settings', methods=['GET', 'POST'])
@login_required
@admin_required
def user_telegram_settings(user_id):
    """사용자 텔레그램 설정 관리"""
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        telegram_id = request.form.get('telegram_id', '').strip()
        
        # 텔레그램 ID 업데이트
        user.telegram_id = telegram_id if telegram_id else None
        
        try:
            db.session.commit()
            flash(f'{user.username} 사용자의 텔레그램 설정이 업데이트되었습니다.', 'success')
            return redirect(url_for('admin.user_telegram_settings', user_id=user_id))
        except Exception as e:
            db.session.rollback()
            flash('텔레그램 설정 업데이트 중 오류가 발생했습니다.', 'error')
    
    return render_template('admin/user_telegram_settings.html', user=user)

@bp.route('/users/<int:user_id>/test-telegram', methods=['POST'])
@login_required
@admin_required
@csrf.exempt
def test_user_telegram(user_id):
    """관리자가 사용자의 텔레그램 연결 테스트"""
    try:
        user = User.query.get_or_404(user_id)
        
        if not user.telegram_id:
            return jsonify({
                'success': False,
                'message': '해당 사용자의 텔레그램 ID가 설정되지 않았습니다.'
            }), 400
        
        result = telegram_service.test_user_connection(user.telegram_id, user.telegram_bot_token)
        
        if result['success']:
            return jsonify({
                'success': True,
                'message': f'{user.username} 사용자의 텔레그램 연결 테스트 성공'
            })
        else:
            return jsonify({
                'success': False,
                'message': f'{user.username} 사용자의 텔레그램 연결 실패: {result["message"]}'
            }), 400
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'테스트 중 오류가 발생했습니다: {str(e)}'
        }), 500

@bp.route('/users/<int:user_id>/send-telegram-notification', methods=['POST'])
@login_required
@admin_required
@csrf.exempt
def send_user_telegram_notification(user_id):
    """관리자가 사용자에게 텔레그램 알림 전송"""
    try:
        user = User.query.get_or_404(user_id)
        data = request.get_json()
        
        if not user.telegram_id:
            return jsonify({
                'success': False,
                'message': '해당 사용자의 텔레그램 ID가 설정되지 않았습니다.'
            }), 400
        
        title = data.get('title', '관리자 알림')
        message = data.get('message', '')
        
        if not message:
            return jsonify({
                'success': False,
                'message': '메시지를 입력해주세요.'
            }), 400
        
        success = telegram_service.send_user_notification(
            user.telegram_id, 
            title, 
            message,
            {'보낸이': '시스템 관리자'},
            user.telegram_bot_token
        )
        
        if success:
            return jsonify({
                'success': True,
                'message': f'{user.username} 사용자에게 알림이 전송되었습니다.'
            })
        else:
            return jsonify({
                'success': False,
                'message': '알림 전송에 실패했습니다.'
            }), 400
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'알림 전송 중 오류가 발생했습니다: {str(e)}'
        }), 500

@bp.route('/system/telegram-settings', methods=['GET', 'POST'])
@login_required
@admin_required
def telegram_settings():
    """전역 텔레그램 설정 관리"""
    if request.method == 'GET':
        # 현재 설정 조회
        settings = telegram_service.get_global_settings()
        return jsonify({
            'success': True,
            'settings': {
                'bot_token': settings['bot_token'][:20] + '...' if settings['bot_token'] else None,  # 마스킹
                'bot_token_full': settings['bot_token'],  # 편집용
                'chat_id': settings['chat_id']
            }
        })
    
    elif request.method == 'POST':
        try:
            data = request.get_json()
            bot_token = data.get('bot_token', '').strip()
            chat_id = data.get('chat_id', '').strip()
            
            # 설정 검증: 둘 다 있거나 둘 다 없어야 함
            if (bot_token and not chat_id) or (not bot_token and chat_id):
                return jsonify({
                    'success': False,
                    'message': '전역 텔레그램 설정은 봇 토큰과 Chat ID를 모두 입력하거나 모두 비워두어야 합니다.'
                }), 400
            
            # 빈 문자열을 None으로 변환
            bot_token = bot_token if bot_token else None
            chat_id = chat_id if chat_id else None
            
            # 설정 업데이트
            success = telegram_service.update_global_settings(
                bot_token=bot_token,
                chat_id=chat_id
            )
            
            if success:
                return jsonify({
                    'success': True,
                    'message': '전역 텔레그램 설정이 업데이트되었습니다.'
                })
            else:
                return jsonify({
                    'success': False,
                    'message': '설정 업데이트에 실패했습니다.'
                }), 500
                
        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'설정 업데이트 중 오류가 발생했습니다: {str(e)}'
            }), 500

@bp.route('/system/test-global-telegram', methods=['POST'])
@login_required
@admin_required
@csrf.exempt
def test_global_telegram():
    """전역 텔레그램 설정 테스트"""
    try:
        # JSON에서 현재 입력값 가져오기
        data = request.get_json()
        if data:
            bot_token = data.get('bot_token', '').strip()
            chat_id = data.get('chat_id', '').strip()
            
            # 디버깅 로그
            from flask import current_app
            current_app.logger.debug(f"전역 텔레그램 테스트 요청: bot_token={'설정됨' if bot_token else '없음'}, chat_id={chat_id}")
            
            # 입력값으로 직접 테스트
            result = telegram_service.test_with_params(bot_token, chat_id)
        else:
            # JSON이 없으면 저장된 설정 사용 (폴백)
            current_app.logger.debug("JSON 데이터가 없어 저장된 전역 설정으로 테스트")
            result = telegram_service.test_global_settings()
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400
            
    except Exception as e:
        from flask import current_app
        current_app.logger.error(f"전역 텔레그램 테스트 중 예외 발생: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'테스트 중 오류가 발생했습니다: {str(e)}'
        }), 500 