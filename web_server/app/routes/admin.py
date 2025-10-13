# @FEAT:admin-panel @COMP:route @TYPE:core
"""
Admin Panel Routes

관리자 전용 페이지 및 API 엔드포인트
- 사용자 관리 (승인, 거부, 삭제, 권한 관리)
- 시스템 모니터링 (스케줄러, 통계, Precision 캐시)
- 텔레그램 설정 (전역/사용자별)
- 주문 추적 시스템 관리
- 대기열 시스템 관리
"""

from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, session
from flask_login import login_required, current_user
from functools import wraps
from app import db, csrf
from app.models import User, Account, Strategy, StrategyAccount
from app.services.telegram import telegram_service
import secrets
import string
from datetime import datetime, timedelta, date
from sqlalchemy import func

bp = Blueprint('admin', __name__, url_prefix='/admin')

# @FEAT:admin-panel @FEAT:auth-session @COMP:route @TYPE:validation
def admin_required(f):
    """
    관리자 권한 확인 데코레이터

    로그인된 사용자가 관리자 권한을 보유했는지 검증합니다.
    실패 시 메인 대시보드로 리다이렉트합니다.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('관리자 권한이 필요합니다.', 'error')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# @FEAT:admin-panel @FEAT:auth-session @COMP:route @TYPE:helper
def _is_admin_session_verified() -> bool:
    """
    관리자 민감 작업을 위한 추가 세션 검증 상태 확인

    세션에 저장된 검증 만료 시간을 확인하여 유효 여부를 반환합니다.
    """
    try:
        verified_until_str = session.get('admin_verified_until')
        if not verified_until_str:
            return False
        verified_until = datetime.fromisoformat(verified_until_str)
        return datetime.utcnow() < verified_until
    except Exception:
        return False

# @FEAT:admin-panel @FEAT:auth-session @COMP:route @TYPE:validation
def admin_verification_required(f):
    """
    민감한 관리자 작업에 대해 추가 비밀번호 검증을 요구

    사용자 삭제, 비밀번호 초기화 등 위험한 작업에 적용됩니다.
    검증 유효 시간: 10분
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _is_admin_session_verified():
            return jsonify({
                'success': False,
                'require_admin_verification': True,
                'message': '관리자 확인이 필요합니다. 비밀번호를 입력해주세요.'
            }), 401
        return f(*args, **kwargs)
    return decorated

# @FEAT:admin-panel @COMP:route @TYPE:core
@bp.route('/')
@login_required
@admin_required
def index():
    """관리자 대시보드 - 사용자 관리 페이지로 리다이렉트"""
    return redirect(url_for('admin.users'))

# @FEAT:admin-panel @FEAT:auth-session @COMP:route @TYPE:core
@bp.route('/verify-session', methods=['POST'])
@login_required
@admin_required
def verify_admin_session():
    """
    관리자 비밀번호로 민감 작업 허용 세션을 일정 시간 부여

    비밀번호 확인 후 10분간 유효한 세션을 생성합니다.
    """
    data = request.get_json() or {}
    password = data.get('password', '')
    if not password:
        return jsonify({'success': False, 'message': '비밀번호를 입력해주세요.'}), 400
    if not current_user.check_password(password):
        return jsonify({'success': False, 'message': '비밀번호가 올바르지 않습니다.'}), 401

    # 10분간 유효
    valid_until = datetime.utcnow() + timedelta(minutes=10)
    session['admin_verified_until'] = valid_until.isoformat()
    return jsonify({'success': True, 'verified_until': session['admin_verified_until']})

# @FEAT:admin-panel @COMP:route @TYPE:core
@bp.route('/users')
@login_required
@admin_required
def users():
    """
    사용자 관리 페이지

    전체 사용자 목록, 승인 대기 사용자, 통계 정보를 표시합니다.
    """
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

# @FEAT:admin-panel @COMP:route @TYPE:core
@bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    """
    사용자 정보 수정

    사용자명, 이메일, 활성화 상태, 관리자 권한, 비밀번호 변경 강제 플래그 수정
    자기 자신의 관리자 권한 제거 및 비활성화 불가
    """
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

# @FEAT:admin-panel @COMP:route @TYPE:core
@bp.route('/users/<int:user_id>/change-password', methods=['GET', 'POST'])
@login_required
@admin_required
def change_user_password(user_id):
    """
    사용자 비밀번호 변경 (관리자가 다른 사용자의 비밀번호 변경)

    최소 6자 이상 검증, 비밀번호 변경 강제 플래그 설정 가능
    """
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

# @FEAT:admin-panel @COMP:route @TYPE:core
@bp.route('/change-password', methods=['GET', 'POST'])
@login_required
@admin_required
def change_admin_password():
    """
    관리자 자신의 비밀번호 변경

    현재 비밀번호 확인 필요, 최소 6자 이상 검증
    """
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

# @FEAT:admin-panel @COMP:route @TYPE:core
@bp.route('/users/<int:user_id>/toggle-active', methods=['POST'])
@login_required
@admin_required
@admin_verification_required
def toggle_user_active(user_id):
    """
    사용자 활성화/비활성화 토글

    자기 자신은 비활성화 불가
    민감 작업: admin_verification_required
    """
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

# @FEAT:admin-panel @COMP:route @TYPE:core
@bp.route('/users/<int:user_id>/toggle-admin', methods=['POST'])
@login_required
@admin_required
@admin_verification_required
def toggle_user_admin(user_id):
    """
    사용자 관리자 권한 토글

    자기 자신의 관리자 권한 제거 불가
    민감 작업: admin_verification_required
    """
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

# @FEAT:admin-panel @COMP:route @TYPE:core
@bp.route('/users/<int:user_id>/approve', methods=['POST'])
@login_required
@admin_required
@admin_verification_required
def approve_user(user_id):
    """
    사용자 승인 (가입 승인)

    is_active=True 설정
    민감 작업: admin_verification_required
    """
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

# @FEAT:admin-panel @COMP:route @TYPE:core
@bp.route('/users/<int:user_id>/reject', methods=['POST'])
@login_required
@admin_required
@admin_verification_required
def reject_user(user_id):
    """
    사용자 가입 거부 (계정 삭제)

    자기 자신 삭제 불가
    민감 작업: admin_verification_required
    """
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

# @FEAT:admin-panel @COMP:route @TYPE:core
@bp.route('/users/<int:user_id>/reset-password', methods=['POST'])
@login_required
@admin_required
@admin_verification_required
def reset_user_password(user_id):
    """
    사용자 비밀번호 초기화

    임시 비밀번호 자동 생성 (8자리)
    다음 로그인 시 비밀번호 변경 강제
    민감 작업: admin_verification_required
    """
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

# @FEAT:admin-panel @COMP:route @TYPE:core
@bp.route('/users/<int:user_id>', methods=['DELETE'])
@login_required
@admin_required
@admin_verification_required
def delete_user(user_id):
    """
    사용자 삭제

    자기 자신 삭제 불가
    민감 작업: admin_verification_required
    """
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

# @FEAT:admin-panel @COMP:route @TYPE:core
@bp.route('/system')
@login_required
@admin_required
def system():
    """
    시스템 모니터링 페이지

    스케줄러 상태, 등록된 작업, 시스템 통계, Precision 캐시 통계 표시
    """
    try:
        from app import scheduler
        from app.services.exchange import exchange_service  # precision 캐시 통계용

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

        # Precision 캐시 통계 추가
        precision_stats = exchange_service.get_precision_cache_stats()

        return render_template('admin/system.html',
                             scheduler_running=scheduler_running,
                             jobs=jobs,
                             stats=stats,
                             precision_stats=precision_stats)

    except Exception as e:
        flash(f'시스템 정보 조회 중 오류가 발생했습니다: {str(e)}', 'error')
        return render_template('admin/system.html',
                             scheduler_running=False,
                             jobs=[],
                             stats={},
                             precision_stats={})

# @FEAT:admin-panel @FEAT:exchange-integration @COMP:route @TYPE:core
@bp.route('/system/precision-cache/clear', methods=['POST'])
@login_required
@admin_required
@admin_verification_required
def clear_precision_cache():
    """
    Precision 캐시 수동 정리

    특정 거래소 또는 전체 캐시 정리
    민감 작업: admin_verification_required
    """
    try:
        from app.services.exchange import exchange_service

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

# @FEAT:admin-panel @FEAT:exchange-integration @COMP:route @TYPE:core
@bp.route('/system/precision-cache/warmup', methods=['POST'])
@login_required
@admin_required
@admin_verification_required
def warmup_precision_cache():
    """
    Precision 캐시 수동 웜업

    백그라운드에서 캐시 재로딩
    민감 작업: admin_verification_required
    """
    try:
        from app.services.exchange import exchange_service

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

# @FEAT:admin-panel @FEAT:exchange-integration @COMP:route @TYPE:core
@bp.route('/system/precision-cache/stats')
@login_required
@admin_required
def get_precision_cache_stats():
    """
    Precision 캐시 통계 실시간 조회

    캐시 상태, 거래소별 심볼 수 등 반환
    """
    try:
        from app.services.exchange import exchange_service

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

# @FEAT:admin-panel @FEAT:telegram-notification @COMP:route @TYPE:core
@bp.route('/users/<int:user_id>/telegram-settings', methods=['GET', 'POST'])
@login_required
@admin_required
def user_telegram_settings(user_id):
    """
    사용자 텔레그램 설정 관리

    사용자별 텔레그램 봇 토큰 및 Chat ID 설정
    둘 다 입력하거나 둘 다 비워야 함
    """
    user = User.query.get_or_404(user_id)

    if request.method == 'POST':
        telegram_id = request.form.get('telegram_id', '').strip()
        telegram_bot_token = request.form.get('telegram_bot_token', '').strip()

        # 검증: 둘 다 있거나 둘 다 없어야 함
        if (telegram_id and not telegram_bot_token) or (not telegram_id and telegram_bot_token):
            flash('사용자 텔레그램 설정은 봇 토큰과 Chat ID를 모두 입력하거나 모두 비워두어야 합니다.', 'error')
            return render_template('admin/user_telegram_settings.html', user=user)

        # 빈 문자열을 None으로 변환 후 업데이트
        user.telegram_id = telegram_id if telegram_id else None
        user.telegram_bot_token = telegram_bot_token if telegram_bot_token else None

        try:
            db.session.commit()
            flash(f'{user.username} 사용자의 텔레그램 설정이 업데이트되었습니다.', 'success')
            return redirect(url_for('admin.user_telegram_settings', user_id=user_id))
        except Exception as e:
            db.session.rollback()
            flash('텔레그램 설정 업데이트 중 오류가 발생했습니다.', 'error')

    return render_template('admin/user_telegram_settings.html', user=user)

# @FEAT:admin-panel @FEAT:telegram-notification @COMP:route @TYPE:core
@bp.route('/users/<int:user_id>/test-telegram', methods=['POST'])
@login_required
@admin_required
@admin_verification_required
def test_user_telegram(user_id):
    """
    관리자가 사용자의 텔레그램 연결 테스트

    사용자 설정으로 테스트 메시지 전송
    민감 작업: admin_verification_required
    """
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

# @FEAT:admin-panel @FEAT:telegram-notification @COMP:route @TYPE:core
@bp.route('/users/<int:user_id>/send-telegram-notification', methods=['POST'])
@login_required
@admin_required
@admin_verification_required
def send_user_telegram_notification(user_id):
    """
    관리자가 사용자에게 텔레그램 알림 전송

    임의의 제목과 메시지를 사용자 텔레그램으로 전송
    민감 작업: admin_verification_required
    """
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

# @FEAT:admin-panel @FEAT:telegram-notification @COMP:route @TYPE:core
@bp.route('/system/telegram-settings', methods=['GET', 'POST'])
@login_required
@admin_required
def telegram_settings():
    """
    전역 텔레그램 설정 관리

    GET: 현재 설정 조회 (봇 토큰 마스킹)
    POST: 설정 업데이트
    """
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

# @FEAT:admin-panel @FEAT:telegram-notification @COMP:route @TYPE:core
@bp.route('/system/test-global-telegram', methods=['POST'])
@login_required
@admin_required
@admin_verification_required
def test_global_telegram():
    """
    전역 텔레그램 설정 테스트

    입력값 우선, 없으면 저장된 설정 사용
    민감 작업: admin_verification_required
    """
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

# ============================================
# 주문 추적 시스템 관련 엔드포인트
# ============================================

# @FEAT:admin-panel @FEAT:order-tracking @COMP:route @TYPE:core
@bp.route('/system/order-tracking')
@login_required
@admin_required
def order_tracking():
    """
    주문 추적 시스템 관리 페이지

    세션 통계, 최근 추적 세션, 최근 체결 내역, 오늘의 성과 요약 표시
    """
    try:
        from app.services.order_tracking import order_tracking_service
        from app.services.trade_record import trade_record_service
        from app.services.performance_tracking import performance_tracking_service
        from app.models import OrderTrackingSession, TradeExecution, StrategyPerformance

        # 세션 통계
        session_stats = order_tracking_service.get_session_stats()

        # 최근 추적 세션 (최근 10개)
        recent_sessions = OrderTrackingSession.query.order_by(
            OrderTrackingSession.started_at.desc()
        ).limit(10).all()

        # 최근 체결 내역 (최근 20개)
        recent_executions = TradeExecution.query.order_by(
            TradeExecution.execution_time.desc()
        ).limit(20).all()

        # 오늘의 성과 요약
        today = date.today()
        today_performances = StrategyPerformance.query.filter_by(date=today).all()

        performance_summary = {
            'total_strategies': len(today_performances),
            'total_pnl': sum(p.daily_pnl for p in today_performances),
            'total_trades': sum(p.total_trades for p in today_performances),
            'avg_win_rate': sum(p.win_rate for p in today_performances) / len(today_performances) if today_performances else 0
        }

        return render_template('admin/order_tracking.html',
                             session_stats=session_stats,
                             recent_sessions=recent_sessions,
                             recent_executions=recent_executions,
                             performance_summary=performance_summary)

    except Exception as e:
        flash(f'주문 추적 정보 조회 중 오류가 발생했습니다: {str(e)}', 'error')
        return redirect(url_for('admin.system'))

# @FEAT:admin-panel @FEAT:order-tracking @COMP:route @TYPE:core
@bp.route('/system/order-tracking/sync-orders', methods=['POST'])
@login_required
@admin_required
@admin_verification_required
def sync_open_orders():
    """
    미체결 주문 수동 동기화

    거래소와 DB 간 미체결 주문 동기화
    민감 작업: admin_verification_required
    """
    try:
        from app.services.order_tracking import order_tracking_service

        account_id = request.json.get('account_id')
        if not account_id:
            return jsonify({
                'success': False,
                'message': '계좌 ID가 필요합니다.'
            }), 400

        result = order_tracking_service.sync_open_orders(account_id)

        if result['success']:
            return jsonify({
                'success': True,
                'message': f"{result['synced_count']}개 주문이 동기화되었습니다.",
                'data': result
            })
        else:
            return jsonify({
                'success': False,
                'message': f"동기화 실패: {result['error']}"
            }), 400

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'동기화 중 오류가 발생했습니다: {str(e)}'
        }), 500

# @FEAT:admin-panel @FEAT:order-tracking @FEAT:analytics @COMP:route @TYPE:core
@bp.route('/system/order-tracking/calculate-performance', methods=['POST'])
@login_required
@admin_required
@admin_verification_required
def calculate_performance():
    """
    성과 메트릭 수동 계산

    특정 전략의 특정 날짜 성과 계산 또는 배치 계산
    민감 작업: admin_verification_required
    """
    try:
        from app.services.performance_tracking import performance_tracking_service
        from datetime import date

        data = request.get_json()
        strategy_id = data.get('strategy_id')
        target_date = data.get('date')

        if strategy_id:
            # 특정 전략 계산
            if target_date:
                target_date = datetime.strptime(target_date, '%Y-%m-%d').date()
            else:
                target_date = date.today()

            performance = performance_tracking_service.calculate_daily_performance(
                strategy_id, target_date
            )

            if performance:
                return jsonify({
                    'success': True,
                    'message': f'전략 {strategy_id}의 {target_date} 성과가 계산되었습니다.',
                    'data': {
                        'daily_pnl': performance.daily_pnl,
                        'total_trades': performance.total_trades,
                        'win_rate': performance.win_rate
                    }
                })
        else:
            # 배치 계산
            days_back = data.get('days_back', 7)
            result = performance_tracking_service.batch_calculate(days_back)

            return jsonify({
                'success': True,
                'message': f"{result['processed']}개 성과가 계산되었습니다.",
                'data': result
            })

        return jsonify({
            'success': False,
            'message': '계산 실패'
        }), 400

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'성과 계산 중 오류가 발생했습니다: {str(e)}'
        }), 500

# @FEAT:admin-panel @FEAT:order-tracking @COMP:route @TYPE:core
@bp.route('/system/order-tracking/cleanup-sessions', methods=['POST'])
@login_required
@admin_required
@admin_verification_required
def cleanup_tracking_sessions():
    """
    오래된 추적 세션 정리

    타임아웃 기본값: 5분
    민감 작업: admin_verification_required
    """
    try:
        from app.services.order_tracking import order_tracking_service

        timeout_minutes = request.json.get('timeout_minutes', 5)
        order_tracking_service.cleanup_stale_sessions(timeout_minutes)

        return jsonify({
            'success': True,
            'message': f'{timeout_minutes}분 이상 비활성 세션이 정리되었습니다.'
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'세션 정리 중 오류가 발생했습니다: {str(e)}'
        }), 500

# @FEAT:admin-panel @FEAT:order-tracking @COMP:route @TYPE:core
@bp.route('/system/order-tracking/stats')
@login_required
@admin_required
def get_tracking_stats():
    """
    추적 시스템 통계 API

    세션 통계, 체결 통계 (최근 24시간), 로그 통계 반환
    """
    try:
        from app.services.order_tracking import order_tracking_service
        from app.services.trade_record import trade_record_service
        from app.models import TrackingLog
        from datetime import datetime, timedelta

        # 세션 통계
        session_stats = order_tracking_service.get_session_stats()

        # 체결 통계 (최근 24시간)
        start_date = datetime.utcnow() - timedelta(days=1)
        execution_stats = trade_record_service.get_execution_stats(start_date=start_date)

        # 로그 통계
        log_stats = db.session.query(
            TrackingLog.severity,
            func.count(TrackingLog.id)
        ).filter(
            TrackingLog.created_at > start_date
        ).group_by(TrackingLog.severity).all()

        log_summary = {severity: count for severity, count in log_stats}

        return jsonify({
            'success': True,
            'session_stats': session_stats,
            'execution_stats': execution_stats,
            'log_stats': log_summary,
            'timestamp': datetime.utcnow().isoformat()
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'통계 조회 중 오류가 발생했습니다: {str(e)}'
        }), 500


# ============================================
# 대기열 시스템 API
# ============================================

# @FEAT:admin-panel @FEAT:order-queue @COMP:route @TYPE:core
@bp.route('/api/queue-status', methods=['GET'])
@login_required
@admin_required
def get_queue_status():
    """
    대기열 현황 조회 (Order Queue System)

    계좌별 심볼별 활성 주문 수, 대기 주문 수, 제한 반환
    """
    try:
        from app.models import Account, OpenOrder, PendingOrder, StrategyAccount
        from app.constants import ExchangeLimits
        from sqlalchemy import distinct, func

        # 활성 계정 조회
        active_accounts = Account.query.filter_by(is_active=True).all()

        result = {
            'success': True,
            'accounts': [],
            'total_active': 0,
            'total_pending': 0
        }

        for account in active_accounts:
            # (account_id, symbol) 조합 추출
            active_symbols_query = db.session.query(
                distinct(OpenOrder.symbol)
            ).join(
                StrategyAccount,
                OpenOrder.strategy_account_id == StrategyAccount.id
            ).filter(
                StrategyAccount.account_id == account.id
            )

            pending_symbols_query = db.session.query(
                distinct(PendingOrder.symbol)
            ).filter(
                PendingOrder.account_id == account.id
            )

            # 합집합
            all_symbols = set(
                [s[0] for s in active_symbols_query.all()] +
                [s[0] for s in pending_symbols_query.all()]
            )

            if not all_symbols:
                continue  # 주문이 없는 계정은 건너뛰기

            # market_type 결정
            strategy_account = StrategyAccount.query.filter_by(account_id=account.id).first()
            market_type = 'SPOT'
            if strategy_account and strategy_account.strategy:
                market_type = strategy_account.strategy.market_type or 'SPOT'

            account_data = {
                'account_id': account.id,
                'account_name': account.name,
                'exchange': account.exchange,
                'market_type': market_type,
                'symbols': []
            }

            for symbol in sorted(all_symbols):
                # 활성 주문 수 (DB 조회)
                active_count = OpenOrder.query.join(StrategyAccount).filter(
                    StrategyAccount.account_id == account.id,
                    OpenOrder.symbol == symbol
                ).count()

                # 대기열 주문 수
                pending_count = PendingOrder.query.filter_by(
                    account_id=account.id,
                    symbol=symbol
                ).count()

                # 제한 계산
                limits = ExchangeLimits.calculate_symbol_limit(
                    exchange=account.exchange,
                    market_type=market_type,
                    symbol=symbol
                )

                account_data['symbols'].append({
                    'symbol': symbol,
                    'active_orders': active_count,
                    'pending_orders': pending_count,
                    'total': active_count + pending_count,
                    'limit': limits['max_orders'],
                    'limit_stop': limits['max_stop_orders']
                })

                result['total_active'] += active_count
                result['total_pending'] += pending_count

            result['accounts'].append(account_data)

        return jsonify(result)

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'대기열 현황 조회 중 오류가 발생했습니다: {str(e)}'
        }), 500


# @FEAT:admin-panel @FEAT:order-queue @COMP:route @TYPE:core
@bp.route('/api/queue-rebalance', methods=['POST'])
@login_required
@admin_required
def manual_rebalance_queue():
    """
    수동 대기열 재정렬 (Order Queue System)

    특정 계좌/심볼의 대기열 수동 재정렬
    """
    try:
        data = request.get_json()
        account_id = data.get('account_id')
        symbol = data.get('symbol')

        if not account_id or not symbol:
            return jsonify({
                'success': False,
                'message': 'account_id와 symbol은 필수입니다'
            }), 400

        # 계정 존재 확인
        from app.models import Account
        account = Account.query.get(account_id)
        if not account:
            return jsonify({
                'success': False,
                'message': f'계정을 찾을 수 없습니다 (ID: {account_id})'
            }), 404

        # 재정렬 실행
        from app.services.trading.order_queue_manager import OrderQueueManager
        from app.services.trading import trading_service

        queue_manager = OrderQueueManager(service=trading_service.trading_core)
        result = queue_manager.rebalance_symbol(
            account_id=account_id,
            symbol=symbol
        )

        if result.get('success'):
            return jsonify({
                **result,
                'message': f'재정렬 완료: {result.get("executed")}개 실행, {result.get("cancelled")}개 취소'
            })
        else:
            return jsonify(result), 500

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'수동 재정렬 중 오류가 발생했습니다: {str(e)}'
        }), 500


# @FEAT:admin-panel @FEAT:order-queue @COMP:route @TYPE:core
@bp.route('/api/metrics', methods=['GET'])
@login_required
@admin_required
def get_metrics():
    """
    대기열 시스템 메트릭 조회

    재정렬 메트릭, 대기열 통계, WebSocket 통계 반환
    """
    try:
        from app.services.trading import trading_service
        from app.models import PendingOrder
        import logging

        logger = logging.getLogger(__name__)

        # 서비스 초기화 확인
        if not trading_service:
            return jsonify({
                'success': False,
                'error': 'Trading service가 초기화되지 않았습니다'
            }), 503

        if not hasattr(trading_service, 'order_queue_manager') or not trading_service.order_queue_manager:
            return jsonify({
                'success': False,
                'error': 'Order queue manager가 초기화되지 않았습니다'
            }), 503

        # 재정렬 메트릭
        queue_manager = trading_service.order_queue_manager
        queue_metrics = queue_manager.get_metrics()

        # 대기열 통계
        pending_stats = db.session.query(
            PendingOrder.account_id,
            PendingOrder.symbol,
            func.count(PendingOrder.id).label('count')
        ).group_by(
            PendingOrder.account_id,
            PendingOrder.symbol
        ).all()

        pending_by_symbol = [
            {
                'account_id': stat.account_id,
                'symbol': stat.symbol,
                'count': stat.count
            }
            for stat in pending_stats
        ]

        total_pending = sum(stat['count'] for stat in pending_by_symbol)

        # WebSocket 통계
        websocket_manager = trading_service.websocket_manager
        websocket_stats = websocket_manager.get_stats() if websocket_manager else {}

        return jsonify({
            'success': True,
            'data': {
                'queue_metrics': queue_metrics,
                'pending_orders': {
                    'total': total_pending,
                    'by_symbol': pending_by_symbol
                },
                'websocket_stats': websocket_stats
            }
        })

    except Exception as e:
        logger.error(f"❌ 메트릭 조회 실패: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
