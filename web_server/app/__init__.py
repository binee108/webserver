import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
import atexit
import sys

# config 모듈 import를 더 안정적으로 처리
def setup_config_path():
    """config 경로 설정 및 import"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(current_dir, '..', '..', 'config')
    
    if os.path.exists(config_path):
        sys.path.insert(0, os.path.abspath(config_path))
        try:
            from config import config
            return config
        except ImportError as e:
            print(f"Error importing config: {e}")
            # 기본 설정으로 fallback
            return None
    else:
        print(f"Warning: config path not found at {config_path}")
        return None

# config import 시도
config = setup_config_path()
if config is None:
    # 기본 설정 사용
    print("Using fallback config...")
    class DefaultConfig:
        SECRET_KEY = 'dev-secret-key-change-in-production'
        SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///trading_system.db')
        SQLALCHEMY_TRACK_MODIFICATIONS = False
        SQLALCHEMY_ENGINE_OPTIONS = {
            'pool_size': 10,
            'pool_timeout': 20,
            'pool_recycle': -1,
            'max_overflow': 0,
            'pool_pre_ping': True
        }
        LOG_LEVEL = 'INFO'
        LOG_FILE = 'logs/app.log'
        BACKGROUND_LOG_LEVEL = 'WARNING'
        SCHEDULER_API_ENABLED = True
        WTF_CSRF_ENABLED = True
        WTF_CSRF_TIME_LIMIT = None
        # SSL은 Nginx에서 처리
        ENABLE_SSL = False
        FORCE_HTTPS = False
        # 프록시 환경 설정
        PREFERRED_URL_SCHEME = 'https'
        SERVER_NAME = None
        DEBUG = True
        APPLICATION_ROOT = '/'
    
    config = {
        'development': DefaultConfig,
        'production': DefaultConfig,
        'testing': DefaultConfig,
        'default': DefaultConfig
    }
from datetime import datetime

# 전역 확장 객체들
db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
scheduler = BackgroundScheduler()

def create_app(config_name=None):
    """Flask 애플리케이션 팩토리"""
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'default')
    
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    
    # URL 라우팅 설정
    app.url_map.strict_slashes = False
    
    # ProxyFix 설정 (Nginx 리버스 프록시용)
    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=1,
        x_proto=1,
        x_host=1,
        x_prefix=1
    )
    
    # 확장 초기화
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    
    # Flask-Login 설정
    login_manager.login_view = 'auth.login'
    login_manager.login_message = '로그인이 필요합니다.'
    login_manager.login_message_category = 'info'
    
    # 사용자 로더 함수
    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        return User.query.get(int(user_id))
    
    # 비밀번호 변경 강제 미들웨어
    @app.before_request
    def check_password_change_required():
        """비밀번호 변경이 필요한 사용자의 접근 제한"""
        # 로그인하지 않은 사용자는 통과
        if not current_user.is_authenticated:
            return
        
        # 비밀번호 변경이 필요하지 않은 사용자는 통과
        if not current_user.must_change_password:
            return
        
        # 허용된 엔드포인트들
        allowed_endpoints = [
            'auth.force_change_password',
            'auth.logout',
            'static'
        ]
        
        # 현재 요청이 허용된 엔드포인트인지 확인
        if request.endpoint in allowed_endpoints:
            return
        
        # 비밀번호 변경 페이지로 리다이렉트
        return redirect(url_for('auth.force_change_password'))
    
    # 블루프린트 등록
    from app.routes import register_blueprints
    register_blueprints(app)
    
    # 등록된 라우트 디버그 출력 (개발환경에서만)
    if app.debug:
        app.logger.info("등록된 라우트들:")
        for rule in app.url_map.iter_rules():
            app.logger.info(f"  {rule.rule} -> {rule.endpoint}")
    
    # 로깅 설정
    if not os.path.exists('logs'):
        os.mkdir('logs')
    
    # 파일 핸들러 설정
    file_handler = RotatingFileHandler(
        app.config['LOG_FILE'], 
        maxBytes=10240000, 
        backupCount=10
    )
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    
    # 환경별 로깅 레벨 설정
    log_level = getattr(logging, app.config.get('LOG_LEVEL', 'INFO').upper())
    file_handler.setLevel(log_level)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(log_level)
    
    # 개발 환경에서는 콘솔에도 출력
    if app.debug:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s'
        ))
        app.logger.addHandler(console_handler)
    
    # 백그라운드 작업용 별도 로거 설정
    background_logger = logging.getLogger('trading_system.background')
    background_log_level = getattr(logging, app.config.get('BACKGROUND_LOG_LEVEL', 'WARNING').upper())
    background_logger.setLevel(background_log_level)
    background_logger.addHandler(file_handler)
    
    app.logger.info('Trading System startup')
    
    # Flask CLI 명령어 실행 중인지 확인
    import sys
    is_cli_command = len(sys.argv) > 1 and sys.argv[1] in ['--help'] or 'flask' in sys.argv[0]
    
    # CLI 명령어가 아닐 때만 데이터베이스 초기화 및 스케줄러 시작
    if not is_cli_command:
        # 데이터베이스 테이블 생성
        with app.app_context():
            try:
                # alembic_version 테이블이 있으면 제거 (마이그레이션 히스토리 제거)
                from sqlalchemy import text
                if db.engine.dialect.has_table(db.engine.connect(), 'alembic_version'):
                    with db.engine.connect() as conn:
                        conn.execute(text('DROP TABLE alembic_version'))
                        conn.commit()
                    app.logger.info('마이그레이션 히스토리 테이블 제거 완료')
                
                # 모든 테이블 생성 (이미 존재하는 테이블은 무시됨)
                db.create_all()
                app.logger.info('데이터베이스 테이블 생성 완료')
            except Exception as e:
                app.logger.error(f'데이터베이스 테이블 생성 실패: {str(e)}')
            
            # 기본 관리자 계정 생성
            try:
                from app.models import User
                admin_user = User.query.filter_by(username='admin').first()
                if not admin_user:
                    admin_user = User(
                        username='admin',
                        email='admin@example.com',
                        telegram_id=None,
                        is_admin=True,
                        is_active=True,
                        must_change_password=True  # 최초 로그인 시 비밀번호 변경 강제
                    )
                    admin_user.set_password('admin123')  # 기본 비밀번호
                    db.session.add(admin_user)
                    db.session.commit()
                    app.logger.info('기본 관리자 계정이 생성되었습니다. (username: admin, password: admin123)')
                    app.logger.info('최초 로그인 시 비밀번호 변경이 필요합니다.')
            except Exception as e:
                app.logger.warning(f'관리자 계정 생성 실패: {str(e)}')
            
            # APScheduler 초기화 및 백그라운드 작업 등록
            init_scheduler(app)
    else:
        app.logger.info('Flask CLI 명령어 실행 중 - 데이터베이스 초기화 및 스케줄러 건너뜀')
    
    return app

def init_scheduler(app):
    """APScheduler 초기화 및 백그라운드 작업 등록"""
    if scheduler.running:
        return
    
    try:
        # APScheduler 설정 (메모리 기반 jobstore 사용)
        from apscheduler.jobstores.memory import MemoryJobStore
        
        jobstores = {
            'default': MemoryJobStore()
        }
        executors = {
            'default': ThreadPoolExecutor(20)
        }
        job_defaults = {
            'coalesce': False,
            'max_instances': 3
        }
        
        scheduler.configure(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone='Asia/Seoul'
        )
        
        # 스케줄러에 강제 실행 메서드 추가
        def get_status():
            """스케줄러 상태 조회"""
            jobs = scheduler.get_jobs()
            return {
                'is_running': scheduler.running,
                'jobs_count': len(jobs),
                'jobs': [
                    {
                        'id': job.id,
                        'name': job.name,
                        'next_run_time': job.next_run_time.isoformat() if job.next_run_time else None
                    } for job in jobs
                ],
                'last_check': datetime.utcnow().isoformat()
            }
        
        def force_update_orders():
            """주문 상태 강제 업데이트"""
            try:
                update_open_orders_with_context(app)
                return True
            except Exception as e:
                app.logger.error(f'주문 상태 강제 업데이트 실패: {str(e)}')
                return False
        
        def force_calculate_pnl():
            """미실현 손익 강제 계산"""
            try:
                calculate_unrealized_pnl_with_context(app)
                return True
            except Exception as e:
                app.logger.error(f'미실현 손익 강제 계산 실패: {str(e)}')
                return False
        
        # 스케줄러 객체에 메서드 추가
        scheduler.get_status = get_status
        scheduler.force_update_orders = force_update_orders
        scheduler.force_calculate_pnl = force_calculate_pnl
        
        # 스케줄러 시작
        scheduler.start()
        app.logger.info('APScheduler 시작됨')
        
        # 백그라운드 작업 등록
        register_background_jobs(app)
        
        # 애플리케이션 종료 시 스케줄러도 종료
        def shutdown_scheduler():
            if scheduler.running:
                scheduler.shutdown()
        atexit.register(shutdown_scheduler)
        
        # 텔레그램 시스템 시작 알림
        try:
            from app.services.telegram_service import telegram_service
            if telegram_service.is_enabled():
                telegram_service.send_system_status('startup', 'APScheduler 백그라운드 작업 시스템이 시작되었습니다.')
            else:
                app.logger.debug('텔레그램이 비활성화되어 있어 시작 알림을 건너뜁니다.')
        except Exception as e:
            app.logger.debug(f'텔레그램 시작 알림 전송 실패: {str(e)}')
            
    except Exception as e:
        app.logger.error(f'APScheduler 초기화 실패: {str(e)}')

def register_background_jobs(app):
    """백그라운드 작업 등록"""
    
    # 🆕 애플리케이션 시작 시 Precision 캐시 웜업을 직접 실행 (한 번만)
    # Flask 개발 서버의 자동 재시작으로 인한 중복 실행 방지
    if not os.environ.get('WERKZEUG_RUN_MAIN'):
        # 메인 프로세스가 아닌 경우 (Flask 개발 서버의 reloader 프로세스) 웜업 건너뛰기
        app.logger.info('🔄 Flask reloader 프로세스에서는 Precision 캐시 웜업을 건너뜁니다')
    else:
        try:
            # 웜업을 직접 실행 (스케줄러에 등록하지 않음)
            warm_up_precision_cache_with_context(app)
            app.logger.info('✅ 애플리케이션 시작 시 Precision 캐시 웜업 완료')
        except Exception as e:
            app.logger.error(f'❌ 애플리케이션 시작 시 Precision 캐시 웜업 실패: {str(e)}')
    
    # 🆕 Precision 캐시 주기적 업데이트 (하루 1회, 새벽 3시)
    scheduler.add_job(
        func=update_precision_cache_with_context,
        args=[app],
        trigger="cron",
        hour=3,
        minute=0,
        id='precision_cache_update',
        name='Daily Precision Cache Update',
        replace_existing=True,
        max_instances=1
    )
    
    # 미체결 주문 상태 업데이트 (30초마다)
    scheduler.add_job(
        func=update_open_orders_with_context,
        args=[app],
        trigger="interval",
        seconds=30,
        id='update_open_orders',
        name='Update Open Orders Status',
        replace_existing=True,
        max_instances=1
    )
    
    # 미실현 손익 계산 (5분마다)
    scheduler.add_job(
        func=calculate_unrealized_pnl_with_context,
        args=[app],
        trigger="interval",
        minutes=5,
        id='calculate_unrealized_pnl',
        name='Calculate Unrealized PnL',
        replace_existing=True,
        max_instances=1
    )
    
    # 일일 요약 전송 (매일 저녁 9시)
    scheduler.add_job(
        func=send_daily_summary_with_context,
        args=[app],
        trigger="cron",
        hour=21,
        minute=0,
        id='send_daily_summary',
        name='Send Daily Summary',
        replace_existing=True,
        max_instances=1
    )
    
    app.logger.info(f'백그라운드 작업 등록 완료 - {len(scheduler.get_jobs())}개 작업')

def warm_up_precision_cache_with_context(app):
    """🆕 애플리케이션 컨텍스트 내에서 Precision 캐시 웜업"""
    with app.app_context():
        try:
            from app.services.exchange_service import exchange_service
            
            app.logger.info('🔥 Precision 캐시 웜업 시작')
            
            # 모든 활성 계좌로 캐시 웜업
            exchange_service.warm_up_precision_cache()
            
            # 웜업 완료 후 통계 로깅
            stats = exchange_service.get_precision_cache_stats()
            app.logger.info(f'🔥 Precision 캐시 웜업 완료 - 통계: {stats}')
            
        except Exception as e:
            app.logger.error(f'❌ Precision 캐시 웜업 실패: {str(e)}')

def update_precision_cache_with_context(app):
    """🆕 애플리케이션 컨텍스트 내에서 Precision 캐시 주기적 업데이트"""
    with app.app_context():
        try:
            from app.services.exchange_service import exchange_service
            from app.models import Account
            
            app.logger.info('🔄 Precision 캐시 주기적 업데이트 시작')
            
            # 모든 활성 계좌 조회
            active_accounts = Account.query.filter_by(is_active=True).all()
            
            if not active_accounts:
                app.logger.warning('활성 계좌가 없어 Precision 캐시 업데이트를 건너뜁니다')
                return
            
            # 거래소별로 그룹화하여 업데이트
            exchange_groups = {}
            for account in active_accounts:
                exchange_name = account.exchange.lower()
                if exchange_name not in exchange_groups:
                    exchange_groups[exchange_name] = account
            
            # 각 거래소별로 precision 캐시 업데이트
            total_updated = 0
            for exchange_name, account in exchange_groups.items():
                try:
                    exchange_instance = exchange_service.get_exchange(account)
                    updated_count = exchange_service.precision_cache.update_exchange_precision_cache(
                        exchange_name, exchange_instance
                    )
                    total_updated += updated_count
                    app.logger.info(f'✅ {exchange_name} precision 캐시 업데이트 완료 - {updated_count}개 심볼')
                    
                except Exception as e:
                    app.logger.error(f'❌ {exchange_name} precision 캐시 업데이트 실패: {str(e)}')
                    continue
            
            # 업데이트 완료 후 통계 로깅
            stats = exchange_service.get_precision_cache_stats()
            app.logger.info(f'🔄 Precision 캐시 주기적 업데이트 완료 - 총 {total_updated}개 심볼, 통계: {stats}')
            
        except Exception as e:
            app.logger.error(f'❌ Precision 캐시 주기적 업데이트 실패: {str(e)}')

def update_open_orders_with_context(app):
    """Flask 앱 컨텍스트 내에서 미체결 주문 상태 업데이트"""
    with app.app_context():
        try:
            from app.services.order_service import order_service
            order_service.update_open_orders_status()
            app.logger.debug('미체결 주문 상태 업데이트 완료')
        except Exception as e:
            app.logger.error(f'미체결 주문 상태 업데이트 실패: {str(e)}')
            try:
                from app.services.telegram_service import telegram_service
                if telegram_service.is_enabled():
                    telegram_service.send_error_alert(
                        "백그라운드 작업 오류",
                        f"미체결 주문 상태 업데이트 실패: {str(e)}"
                    )
            except Exception:
                pass  # 텔레그램 알림 실패는 조용히 무시

def calculate_unrealized_pnl_with_context(app):
    """Flask 앱 컨텍스트 내에서 미실현 손익 계산"""
    with app.app_context():
        try:
            from app.services.position_service import position_service
            position_service.calculate_unrealized_pnl()
            app.logger.debug('미실현 손익 계산 완료')
        except Exception as e:
            app.logger.error(f'미실현 손익 계산 실패: {str(e)}')
            try:
                from app.services.telegram_service import telegram_service
                if telegram_service.is_enabled():
                    telegram_service.send_error_alert(
                        "백그라운드 작업 오류",
                        f"미실현 손익 계산 실패: {str(e)}"
                    )
            except Exception:
                pass  # 텔레그램 알림 실패는 조용히 무시

def send_daily_summary_with_context(app):
    """Flask 앱 컨텍스트 내에서 일일 요약 보고서 전송"""
    with app.app_context():
        try:
            from app.services.analytics_service import analytics_service
            from app.services.telegram_service import telegram_service
            from app.models import Account
            
            # 모든 활성 계정에 대한 일일 요약 데이터 생성
            accounts = Account.query.filter_by(is_active=True).all()
            summary_data = {}
            for account in accounts:
                try:
                    account_summary = analytics_service.get_daily_summary(account.id)
                    summary_data[account.name] = account_summary
                except Exception as e:
                    app.logger.error(f'계정 {account.name} 일일 요약 생성 실패: {str(e)}')
            
            # 텔레그램으로 전송
            telegram_service.send_daily_summary(summary_data)
            app.logger.info('일일 요약 보고서 전송 완료')
        except Exception as e:
            app.logger.error(f'일일 요약 보고서 전송 실패: {str(e)}')
            try:
                from app.services.telegram_service import telegram_service
                if telegram_service.is_enabled():
                    telegram_service.send_error_alert(
                        "백그라운드 작업 오류",
                        f"일일 요약 보고서 전송 실패: {str(e)}"
                    )
            except Exception:
                pass  # 텔레그램 알림 실패는 조용히 무시 