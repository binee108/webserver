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
from app.constants import BackgroundJobTag, JOB_TAG_MAP
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

# @FEAT:error-warning-logs @COMP:route @TYPE:helper
def _is_development_mode() -> bool:
    """
    환경 감지: 개발 모드 여부 확인

    환경 감지 방식:
    - .env 파일의 FLASK_ENV 변수 확인
    - 'production'이 아니면 개발 모드로 간주
    - python run.py setup --env production으로 설정

    Returns:
        bool: 개발 모드이면 True, 프로덕션이면 False

    Note:
        개발 모드에서는 디버깅 API의 인증을 우회하여
        빠른 오류 확인이 가능합니다.
    """
    import os
    from flask import current_app

    # FLASK_ENV 환경 변수를 우선 확인 (docker-compose.yml에서 설정됨)
    env_var = os.environ.get('FLASK_ENV', '')
    if env_var:
        env = env_var
    else:
        # 환경 변수가 없으면 app.config에서 확인
        env = current_app.config.get('ENV', 'production')

    return env.lower() not in ['production', 'prod']

# @FEAT:error-warning-logs @COMP:route @TYPE:validation
def conditional_admin_required(f):
    """
    환경별 인증 분기 데코레이터

    개발 모드 (ENV != 'production'):
        - 인증 완전 우회 (로그인 불필요)
        - 목적: API 요청으로 빠른 디버깅 지원

    ⚠️ SECURITY WARNING:
        개발 모드는 인증을 완전히 우회합니다.
        - 절대 프로덕션 환경에서 ENV != 'production' 설정 금지
        - 외부 네트워크 노출 시 심각한 보안 위험
        - 배포 전 반드시 `python run.py setup --env production` 실행 필수

    프로덕션 모드 (ENV = 'production'):
        - 로그인 필수 (@login_required)
        - 관리자 권한 필수 (@admin_required 로직)
        - 보안: 민감한 로그 정보 보호

    Usage:
        @bp.route('/debug-endpoint')
        @conditional_admin_required
        def debug_view():
            # 개발: 누구나 접근, 프로덕션: 관리자만
            pass
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if _is_development_mode():
            # 개발 모드: 인증 우회 (디버깅 편의성)
            from flask import current_app
            current_app.logger.warning(
                f"🔓 [DEV MODE] Authentication bypassed for {f.__name__} "
                f"(ENV={current_app.config.get('ENV')})"
            )
            return f(*args, **kwargs)
        else:
            # 프로덕션 모드: 로그인 및 관리자 권한 검증
            if not current_user.is_authenticated:
                flash('로그인이 필요합니다.', 'error')
                return redirect(url_for('auth.login', next=request.url))
            if not current_user.is_admin:
                flash('관리자 권한이 필요합니다.', 'error')
                return redirect(url_for('main.dashboard'))
            return f(*args, **kwargs)
    return decorated_function

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


# @FEAT:admin-panel @COMP:route @TYPE:core
@bp.route('/api/metrics', methods=['GET'])
@login_required
@admin_required
def get_metrics():
    """
    시스템 메트릭 조회

    WebSocket 통계 반환
    """
    try:
        from app.services.trading import trading_service
        import logging

        logger = logging.getLogger(__name__)

        # 서비스 초기화 확인
        if not trading_service:
            return jsonify({
                'success': False,
                'error': 'Trading service가 초기화되지 않았습니다'
            }), 503

        # WebSocket 통계
        websocket_manager = trading_service.websocket_manager
        websocket_stats = websocket_manager.get_stats() if websocket_manager else {}

        return jsonify({
            'success': True,
            'data': {
                'websocket_stats': websocket_stats
            }
        })

    except Exception as e:
        logger.error(f"❌ 메트릭 조회 실패: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================
# 백그라운드 작업 로그 조회
# ============================================

# @FEAT:background-job-logs @COMP:route @TYPE:core
@bp.route('/system/background-jobs/<job_id>/logs', methods=['GET'])
@login_required
@admin_required
def get_job_logs(job_id):
    """
    특정 백그라운드 작업의 로그 조회

    **태그 기반 필터링**: JOB_TAG_MAP을 통해 job_id를 BackgroundJobTag로 변환하여
    해당 작업의 로그만 정확하게 필터링합니다. (Phase 4 개선)

    Args:
        job_id (str): 백그라운드 작업 ID (예: queue_rebalancer, update_open_orders)

    Query Parameters:
        limit (int): 최대 로그 줄 수 (기본: 100, 최대: 500)
        level (str): 로그 레벨 필터 (ALL, INFO, WARNING, ERROR, DEBUG)
        search (str): 텍스트 검색어 (대소문자 무시)

    Returns:
        JSON (200):
            {
                "success": true,
                "logs": [
                    {
                        "timestamp": "2025-10-23 14:08:29",
                        "level": "INFO",
                        "tag": "QUEUE_REBAL",  # 🆕 추가됨 (Phase 4)
                        "message": "재정렬 대상 조합: 3개",
                        "file": "queue_rebalancer.py",
                        "line": 123
                    }
                ],
                "total": 1000,
                "filtered": 45,
                "job_id": "queue_rebalancer"
            }

        JSON (404):
            { "success": false, "message": "유효하지 않은 작업 ID: xxx", "logs": [], "total": 0, "filtered": 0, "job_id": "xxx" }

        JSON (403):
            { "success": false, "message": "로그 조회 중 오류가 발생했습니다.", "logs": [], "total": 0, "filtered": 0, "job_id": "xxx" }

        JSON (500):
            { "success": false, "message": "로그 조회 중 오류가 발생했습니다.", "logs": [], "total": 0, "filtered": 0 }

    Note:
        - 태그 없는 로그도 파싱 가능 (하위 호환성)
        - job_id가 JOB_TAG_MAP에 없으면 WARNING 로그 출력 후 모든 로그 반환
        - API 응답의 'tag' 필드는 Optional (null 가능)

    Implementation (GitHub Issue #2 해결):
        헬퍼 함수를 활용한 안전한 로그 읽기 및 파싱:

        1. validate_log_file_path(): Path Traversal 방어 및 파일 검증
        2. read_log_tail_utf8_safe(): UTF-8 안전 tail 읽기 (200KB 최적화)
           - 바이너리 모드, 라인 경계 탐색, errors='replace'
           - 폴백: 최적화 실패 시 전체 파일 읽기
        3. parse_log_line(): 정규식 기반 구조화 파싱
           - timestamp, level, tag, message, file, line 추출

        상세 구현은 app/utils/log_reader.py 참조

    Security:
        - Path Traversal 방어: allowed_log_dir 범위 내 파일만 허용
        - Job ID 화이트리스트 검증: scheduler.get_jobs()에 등록된 작업만 접근 허용

    Feature Tags:
        @FEAT:background-job-logs @COMP:route @TYPE:core
    """
    try:
        from flask import current_app
        from app import scheduler
        from app.utils.log_reader import (
            validate_log_file_path,
            read_log_tail_utf8_safe,
            parse_log_line
        )

        # Job ID 검증 (화이트리스트)
        valid_job_ids = [job.id for job in scheduler.get_jobs()]
        if job_id not in valid_job_ids:
            return jsonify({
                'success': False,
                'message': f'유효하지 않은 작업 ID: {job_id}',
                'logs': [],
                'total': 0,
                'filtered': 0,
                'job_id': job_id
            }), 404

        # 로그 파일 경로 가져오기 및 검증
        log_path = current_app.config.get('LOG_FILE')
        try:
            log_path = validate_log_file_path(log_path, current_app)
        except ValueError:
            # LOG_FILE 설정 누락
            return jsonify({
                'success': False,
                'message': '로그 조회 중 오류가 발생했습니다.',
                'logs': [],
                'total': 0,
                'filtered': 0,
                'job_id': job_id
            }), 500
        except PermissionError:
            # Path traversal 시도
            return jsonify({
                'success': False,
                'message': '로그 조회 중 오류가 발생했습니다.',
                'logs': [],
                'total': 0,
                'filtered': 0,
                'job_id': job_id
            }), 403
        except FileNotFoundError:
            # 로그 파일 없음
            return jsonify({
                'success': False,
                'message': '로그 파일을 찾을 수 없습니다.',
                'logs': [],
                'total': 0,
                'filtered': 0,
                'job_id': job_id
            }), 404

        # 쿼리 파라미터 파싱
        limit = min(int(request.args.get('limit', 100)), 500)
        level = request.args.get('level', 'ALL').upper()
        search_term = request.args.get('search', '').lower()

        # 로그 파일 읽기 (tail 방식 - UTF-8 안전)
        try:
            lines = read_log_tail_utf8_safe(log_path)
        except OSError as e:
            current_app.logger.error(f'로그 파일 읽기 실패: {str(e)}')
            return jsonify({
                'success': False,
                'message': '로그 조회 중 오류가 발생했습니다.',
                'logs': [],
                'total': 0,
                'filtered': 0,
                'job_id': job_id
            }), 500

        # Job ID → Tag 매핑 조회
        job_tag = JOB_TAG_MAP.get(job_id)
        if not job_tag:
            current_app.logger.warning(
                f'Job ID "{job_id}"에 대한 태그 매핑이 없습니다. '
                f'사용 가능한 Job ID: {", ".join(JOB_TAG_MAP.keys())}'
            )

        parsed_logs = []
        total_count = 0

        for line in lines:
            total_count += 1

            # Phase 3.1 헬퍼 재사용: parse_log_line()으로 구조화 파싱
            parsed = parse_log_line(line)

            if parsed:
                # 태그 기반 필터링 (job_tag가 있을 경우)
                if job_tag:
                    # job_tag: "[QUEUE_REBAL]" (constants.py에서 대괄호 포함)
                    # parsed['tag']: "QUEUE_REBAL" (정규식으로 추출, 대괄호 제외)
                    if parsed['tag'] != job_tag.strip('[]'):  # 대괄호 제거하여 비교
                        continue  # 다른 작업의 로그는 스킵

                # 로그 레벨 필터
                if level != 'ALL' and parsed['level'] != level:
                    continue

                # 검색어 필터
                if search_term and search_term not in parsed['message'].lower():
                    continue

                parsed_logs.append(parsed)
            else:
                # 파싱 실패 시 fallback (태그 없는 로그도 포함)
                if search_term and search_term not in line.lower():
                    continue

                parsed_logs.append({
                    'timestamp': 'N/A',
                    'level': 'UNKNOWN',
                    'tag': None,
                    'message': line.strip(),
                    'file': 'N/A',
                    'line': 0
                })

        # limit 적용
        filtered_logs = parsed_logs[-limit:]

        return jsonify({
            'success': True,
            'logs': filtered_logs,
            'total': total_count,
            'filtered': len(filtered_logs),
            'job_id': job_id
        })

    except Exception as e:
        current_app.logger.error(f'로그 조회 중 오류 발생: {str(e)}', exc_info=True)
        return jsonify({
            'success': False,
            'message': '로그 조회 중 오류가 발생했습니다.',
            'logs': [],
            'total': 0,
            'filtered': 0
        }), 500


# @FEAT:error-warning-logs @FEAT:log-ordering-fix @COMP:route @TYPE:core
@bp.route('/system/logs/errors-warnings', methods=['GET'])
@conditional_admin_required
def get_errors_warnings_logs():
    """
    ERROR/WARNING 로그 조회 API (디버깅 용도)

    시스템 전체의 ERROR 및 WARNING 로그를 빠르게 조회하는 API입니다.
    개발 모드에서는 인증을 우회하여 디버깅을 편리하게 지원하며,
    프로덕션 모드에서는 관리자 권한을 요구하여 보안을 강화합니다.

    **인증 정책:**
    - 개발 모드 (ENV != 'production'): 인증 완전 우회 (로그인 불필요)
    - 프로덕션 모드 (ENV = 'production'): 로그인 + 관리자 권한 필수

    **로그 정렬 (역순 정렬):**
    - 최신 로그가 먼저 표시됩니다 (newest-first 순서)
    - 가장 최근 오류/경고를 즉시 확인 가능
    - 기술적 구현: parsed_logs[-limit:][::-1]
      * [-limit:]: 최신 N개 항목 선택 (chronological order 유지)
      * [::-1]: 배열 역순 정렬로 newest-first 순서로 변환

    **사용 사례:**
    - 실시간 오류 모니터링
    - 경고 메시지 빠른 확인
    - 문제 원인 파악 (파일명, 라인 번호 포함)

    Query Parameters:
        limit (int): 최대 로그 줄 수 (기본: 100, 최대: 500)
            설명: 최근 N개 로그 반환 (가장 최신 순서, 역순 정렬)
        level (str): 로그 레벨 필터 (기본: 'ERROR')
            옵션: 'ERROR' (오류만), 'WARNING' (경고만), 'ALL' (둘 다)
        search (str): 텍스트 검색어 (대소문자 무시, 선택사항)
            예: '{"search": "order"}' → "order" 포함된 로그만 반환

    Returns:
        JSON (200) - 성공:
            {
                "success": true,
                "logs": [
                    {
                        "timestamp": "2025-10-23 14:08:29",
                        "level": "ERROR",
                        "tag": null,
                        "message": "Failed to execute order",
                        "file": "order_executor.py",
                        "line": 456
                    },
                    {
                        "timestamp": "2025-10-23 14:07:15",
                        "level": "WARNING",
                        "tag": null,
                        "message": "High slippage detected",
                        "file": "risk_manager.py",
                        "line": 234
                    }
                ],
                "total": 1250,
                "filtered": 45,
                "level_filter": "ERROR",
                "environment": "development",
                "log_file": "app.log"
            }

        JSON (404) - 로그 파일 미발견:
            {
                "success": false,
                "message": "로그 파일을 찾을 수 없습니다.",
                "logs": [],
                "total": 0,
                "filtered": 0
            }

        JSON (403) - 경로 검증 실패 (Path Traversal):
            {
                "success": false,
                "message": "로그 조회 중 오류가 발생했습니다.",
                "logs": [],
                "total": 0,
                "filtered": 0
            }

        JSON (500) - 서버 오류:
            {
                "success": false,
                "message": "로그 조회 중 오류가 발생했습니다.",
                "logs": [],
                "total": 0,
                "filtered": 0
            }

    Implementation Notes:
        1. UTF-8 Safe Tail Read Algorithm (get_job_logs 참고):
           - 바이너리 모드('rb')로 파일 열기 (멀티바이트 안전성)
           - 파일 끝에서 200KB 역방향 seek (성능 최적화)
           - 라인 경계 탐색으로 완전한 라인부터 읽기
           - decode('utf-8', errors='replace') 사용 (깨진 문자 대체)

        2. 태그 필터링 제거 (get_job_logs와의 차이점):
           - Job ID별 태그 필터링 없음
           - 모든 ERROR/WARNING 로그 조회
           - 검색어로만 추가 필터링 가능

        3. 성능 고려사항:
           - 200KB 청크 읽기 (약 1000줄)
           - 메모리 효율적인 처리
           - 느린 클라이언트를 위한 limit 제한 (최대 500)

    Security:
        - Path Traversal 방어: allowed_log_dir 범위 내 파일만 허용
        - 환경 기반 인증: 프로덕션에서만 관리자 권한 요구
        - 사용자 입력 검증: limit, level, search 파라미터 검증

    Feature Tags:
        @FEAT:error-warning-logs @COMP:route @TYPE:core
    """
    try:
        from flask import current_app
        import os
        from app.utils.log_reader import (
            validate_log_file_path,
            read_log_tail_utf8_safe,
            parse_log_line
        )

        # 로그 파일 경로 가져오기 및 검증
        log_path = current_app.config.get('LOG_FILE')
        try:
            log_path = validate_log_file_path(log_path, current_app)
        except ValueError:
            # LOG_FILE 설정 누락
            return jsonify({
                'success': False,
                'message': '로그 조회 중 오류가 발생했습니다.',
                'logs': [],
                'total': 0,
                'filtered': 0
            }), 500
        except PermissionError:
            # Path traversal 시도
            return jsonify({
                'success': False,
                'message': '로그 조회 중 오류가 발생했습니다.',
                'logs': [],
                'total': 0,
                'filtered': 0
            }), 403
        except FileNotFoundError:
            # 로그 파일 없음
            return jsonify({
                'success': False,
                'message': '로그 파일을 찾을 수 없습니다.',
                'logs': [],
                'total': 0,
                'filtered': 0
            }), 404

        # 쿼리 파라미터 파싱
        try:
            limit = min(int(request.args.get('limit', 100)), 500)
        except (ValueError, TypeError):
            limit = 100

        level = request.args.get('level', 'ERROR').upper()
        # 유효한 레벨 검증
        valid_levels = ['ERROR', 'WARNING', 'ALL']
        if level not in valid_levels:
            level = 'ERROR'

        search_term = request.args.get('search', '').lower()

        # 로그 파일 읽기 (tail 방식 - UTF-8 안전)
        try:
            lines = read_log_tail_utf8_safe(log_path)
        except OSError as e:
            current_app.logger.error(f'로그 파일 읽기 실패: {str(e)}')
            return jsonify({
                'success': False,
                'message': '로그 조회 중 오류가 발생했습니다.',
                'logs': [],
                'total': 0,
                'filtered': 0
            }), 500

        parsed_logs = []
        total_count = 0

        for line in lines:
            total_count += 1

            # 헬퍼를 사용한 파싱
            parsed = parse_log_line(line)

            if parsed:
                # 로그 레벨 필터 (ERROR, WARNING 또는 ALL)
                if level != 'ALL' and parsed['level'] != level:
                    continue

                # 검색어 필터
                if search_term and search_term not in parsed['message'].lower():
                    continue

                parsed_logs.append(parsed)
            else:
                # 파싱 실패 시 fallback (기존 동작 유지)
                if search_term and search_term not in line.lower():
                    continue

                # ERROR/WARNING 필터링을 위해 키워드 포함 여부 확인
                # ⚠️ CRITICAL: 이 로직은 get_job_logs()에 없는 고유 로직임
                line_upper = line.upper()
                if level != 'ALL':
                    if level == 'ERROR' and 'ERROR' not in line_upper:
                        continue
                    elif level == 'WARNING' and 'WARNING' not in line_upper:
                        continue

                parsed_logs.append({
                    'timestamp': 'N/A',
                    'level': 'UNKNOWN',
                    'tag': None,
                    'message': line.strip(),
                    'file': 'N/A',
                    'line': 0
                })

        # limit 적용: 최신 N개 로그를 역순(최신순)으로 반환
        # parsed_logs[-limit:]: 마지막 N개 항목 선택 (chronological order 유지)
        # [::-1]: 배열 역순 정렬하여 newest-first 순서로 변환
        filtered_logs = parsed_logs[-limit:][::-1]

        return jsonify({
            'success': True,
            'logs': filtered_logs,
            'total': total_count,
            'filtered': len(filtered_logs),
            'level_filter': level,
            'environment': 'development' if _is_development_mode() else 'production',
            'log_file': os.path.basename(log_path)
        })

    except Exception as e:
        current_app.logger.error(f'ERROR/WARNING 로그 조회 중 오류 발생: {str(e)}', exc_info=True)
        return jsonify({
            'success': False,
            'message': '로그 조회 중 오류가 발생했습니다.',
            'logs': [],
            'total': 0,
            'filtered': 0
        }), 500
