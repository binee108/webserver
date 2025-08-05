from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from app import db, csrf
from app.models import User
from app.services.telegram_service import telegram_service
from datetime import datetime

bp = Blueprint('auth', __name__, url_prefix='/auth')

@bp.route('/login', methods=['GET', 'POST'])
def login():
    """로그인 페이지"""
    if current_user.is_authenticated:
        # 비밀번호 변경이 필요한 경우
        if current_user.must_change_password:
            return redirect(url_for('auth.force_change_password'))
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            flash('사용자명과 비밀번호를 입력해주세요.', 'error')
            return render_template('auth/login.html')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            if not user.is_active:
                flash('계정이 비활성화되어 있습니다. 관리자의 승인을 기다려주세요.', 'error')
                return render_template('auth/login.html')
            
            # 마지막 로그인 시간 업데이트
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            login_user(user, remember=True)
            flash(f'환영합니다, {user.username}님!', 'success')
            
            # 비밀번호 변경이 필요한 경우
            if user.must_change_password:
                return redirect(url_for('auth.force_change_password'))
            
            # 다음 페이지로 리다이렉트
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            return redirect(url_for('main.dashboard'))
        else:
            flash('잘못된 사용자명 또는 비밀번호입니다.', 'error')
    
    return render_template('auth/login.html')

@bp.route('/force-change-password', methods=['GET', 'POST'])
@login_required
def force_change_password():
    """강제 비밀번호 변경"""
    # 비밀번호 변경이 필요하지 않은 경우 대시보드로 리다이렉트
    if not current_user.must_change_password:
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        # 입력 검증
        if not all([current_password, new_password, confirm_password]):
            flash('모든 필드를 입력해주세요.', 'error')
            return render_template('auth/force_change_password.html')
        
        if not current_user.check_password(current_password):
            flash('현재 비밀번호가 올바르지 않습니다.', 'error')
            return render_template('auth/force_change_password.html')
        
        if new_password != confirm_password:
            flash('새 비밀번호가 일치하지 않습니다.', 'error')
            return render_template('auth/force_change_password.html')
        
        if len(new_password) < 6:
            flash('비밀번호는 최소 6자 이상이어야 합니다.', 'error')
            return render_template('auth/force_change_password.html')
        
        try:
            current_user.set_password(new_password)
            current_user.must_change_password = False
            db.session.commit()
            flash('비밀번호가 성공적으로 변경되었습니다. 이제 모든 기능을 이용하실 수 있습니다.', 'success')
            return redirect(url_for('main.dashboard'))
        except Exception as e:
            db.session.rollback()
            flash('비밀번호 변경 중 오류가 발생했습니다.', 'error')
    
    return render_template('auth/force_change_password.html')

@bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """일반 비밀번호 변경"""
    # 강제 비밀번호 변경이 필요한 경우 해당 페이지로 리다이렉트
    if current_user.must_change_password:
        return redirect(url_for('auth.force_change_password'))
    
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        # 입력 검증
        if not all([current_password, new_password, confirm_password]):
            flash('모든 필드를 입력해주세요.', 'error')
            return render_template('auth/change_password.html')
        
        if not current_user.check_password(current_password):
            flash('현재 비밀번호가 올바르지 않습니다.', 'error')
            return render_template('auth/change_password.html')
        
        if new_password != confirm_password:
            flash('새 비밀번호가 일치하지 않습니다.', 'error')
            return render_template('auth/change_password.html')
        
        if len(new_password) < 6:
            flash('비밀번호는 최소 6자 이상이어야 합니다.', 'error')
            return render_template('auth/change_password.html')
        
        try:
            current_user.set_password(new_password)
            db.session.commit()
            flash('비밀번호가 성공적으로 변경되었습니다.', 'success')
            return redirect(url_for('main.dashboard'))
        except Exception as e:
            db.session.rollback()
            flash('비밀번호 변경 중 오류가 발생했습니다.', 'error')
    
    return render_template('auth/change_password.html')

@bp.route('/register', methods=['GET', 'POST'])
def register():
    """회원가입 페이지"""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        password_confirm = request.form.get('password_confirm', '')
        telegram_id = request.form.get('telegram_id', '').strip()
        
        # 입력 검증
        if not all([username, email, password, password_confirm]):
            flash('모든 필드를 입력해주세요.', 'error')
            return render_template('auth/register.html')
        
        if password != password_confirm:
            flash('비밀번호가 일치하지 않습니다.', 'error')
            return render_template('auth/register.html')
        
        if len(password) < 6:
            flash('비밀번호는 최소 6자 이상이어야 합니다.', 'error')
            return render_template('auth/register.html')
        
        # 중복 확인
        if User.query.filter_by(username=username).first():
            flash('이미 존재하는 사용자명입니다.', 'error')
            return render_template('auth/register.html')
        
        if User.query.filter_by(email=email).first():
            flash('이미 존재하는 이메일입니다.', 'error')
            return render_template('auth/register.html')
        
        # 새 사용자 생성
        user = User(
            username=username,
            email=email,
            telegram_id=telegram_id if telegram_id else None,
            is_active=False  # 관리자 승인 필요
        )
        user.set_password(password)
        
        try:
            db.session.add(user)
            db.session.commit()
            flash('회원가입이 완료되었습니다. 관리자의 승인을 기다려주세요.', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            flash('회원가입 중 오류가 발생했습니다.', 'error')
    
    return render_template('auth/register.html')

@bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """사용자 프로필 설정"""
    # 강제 비밀번호 변경이 필요한 경우 해당 페이지로 리다이렉트
    if current_user.must_change_password:
        return redirect(url_for('auth.force_change_password'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        telegram_id = request.form.get('telegram_id', '').strip()
        telegram_bot_token = request.form.get('telegram_bot_token', '').strip()
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        # 이메일 업데이트
        if email != current_user.email:
            # 이메일 중복 확인
            if email and User.query.filter(User.email == email, User.id != current_user.id).first():
                flash('이미 존재하는 이메일입니다.', 'error')
                return render_template('auth/profile.html')
            
            current_user.email = email if email else None
        
        # 텔레그램 설정 검증: 둘 다 있거나 둘 다 없어야 함
        if (telegram_id and not telegram_bot_token) or (not telegram_id and telegram_bot_token):
            flash('텔레그램 알림을 사용하려면 봇 토큰과 Chat ID를 모두 입력해야 합니다.', 'error')
            return render_template('auth/profile.html')
        
        # 텔레그램 ID 업데이트
        if telegram_id != current_user.telegram_id:
            current_user.telegram_id = telegram_id if telegram_id else None
        
        # 텔레그램 봇 토큰 업데이트
        if telegram_bot_token != current_user.telegram_bot_token:
            current_user.telegram_bot_token = telegram_bot_token if telegram_bot_token else None
        
        # 비밀번호 변경 (선택사항)
        if current_password or new_password or confirm_password:
            # 비밀번호 변경 시 입력 검증
            if not all([current_password, new_password, confirm_password]):
                flash('비밀번호를 변경하려면 모든 비밀번호 필드를 입력해주세요.', 'error')
                return render_template('auth/profile.html')
            
            if not current_user.check_password(current_password):
                flash('현재 비밀번호가 올바르지 않습니다.', 'error')
                return render_template('auth/profile.html')
            
            if new_password != confirm_password:
                flash('새 비밀번호가 일치하지 않습니다.', 'error')
                return render_template('auth/profile.html')
            
            if len(new_password) < 6:
                flash('비밀번호는 최소 6자 이상이어야 합니다.', 'error')
                return render_template('auth/profile.html')
            
            current_user.set_password(new_password)
        
        try:
            db.session.commit()
            flash('프로필이 성공적으로 업데이트되었습니다.', 'success')
            return redirect(url_for('auth.profile'))
        except Exception as e:
            db.session.rollback()
            flash('프로필 업데이트 중 오류가 발생했습니다.', 'error')
    
    return render_template('auth/profile.html')

@bp.route('/profile/test-telegram', methods=['POST'])
@login_required
@csrf.exempt
def test_telegram():
    """사용자의 텔레그램 연결 테스트 (사용자별 봇 토큰 지원)"""
    try:
        # JSON 요청에서 현재 입력된 값들 가져오기
        data = request.get_json()
        if data:
            telegram_id = data.get('telegram_id', '').strip()
            telegram_bot_token = data.get('telegram_bot_token', '').strip()
            # 빈 문자열을 None으로 변환
            if not telegram_bot_token:
                telegram_bot_token = None
        else:
            # JSON이 없으면 현재 저장된 값 사용 (폴백)
            telegram_id = current_user.telegram_id
            telegram_bot_token = current_user.telegram_bot_token
        
        # 디버깅 로그
        from flask import current_app
        current_app.logger.debug(f"텔레그램 테스트 요청: telegram_id={telegram_id}, bot_token={'설정됨' if telegram_bot_token else '없음'}")
        
        if not telegram_id or not telegram_bot_token:
            return jsonify({
                'success': False,
                'message': '텔레그램 봇 토큰과 Chat ID를 모두 입력해야 테스트할 수 있습니다.'
            }), 400
        
        result = telegram_service.test_user_connection(
            telegram_id, 
            telegram_bot_token
        )
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'테스트 중 오류가 발생했습니다: {str(e)}'
        }), 500

@bp.route('/logout')
@login_required
def logout():
    """로그아웃"""
    logout_user()
    flash('로그아웃되었습니다.', 'info')
    return redirect(url_for('auth.login')) 