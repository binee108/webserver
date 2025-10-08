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
        SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'postgresql://trader:password123@localhost:5432/trading_system')
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
    
    # 🔧 세션 쿠키 설정 - localhost와 외부 IP 모두에서 작동하도록 
    app.config['SESSION_COOKIE_DOMAIN'] = None  # 도메인 제한 없음
    app.config['SESSION_COOKIE_SECURE'] = True  # HTTPS에서만 쿠키 전송
    app.config['SESSION_COOKIE_HTTPONLY'] = True  # JavaScript 접근 방지
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # CSRF 보호
    
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

                # 호환성 마이그레이션: strategies 테이블에 is_public 컬럼이 없으면 추가
                try:
                    from sqlalchemy import inspect
                    inspector = inspect(db.engine)
                    columns = [col['name'] for col in inspector.get_columns('strategies')]
                    if 'is_public' not in columns:
                        with db.engine.connect() as conn:
                            conn.execute(text("ALTER TABLE strategies ADD COLUMN is_public BOOLEAN NOT NULL DEFAULT FALSE"))
                            conn.commit()
                        app.logger.info("호환성 마이그레이션 적용: strategies.is_public 컬럼 추가")
                except Exception as mig_e:
                    app.logger.warning(f'호환성 마이그레이션(is_public) 적용 실패 또는 불필요: {str(mig_e)}')
                # 호환성 마이그레이션: users 테이블에 webhook_token 컬럼이 없으면 추가
                try:
                    from sqlalchemy import inspect
                    inspector = inspect(db.engine)
                    columns = [col['name'] for col in inspector.get_columns('users')]
                    if 'webhook_token' not in columns:
                        with db.engine.connect() as conn:
                            conn.execute(text("ALTER TABLE users ADD COLUMN webhook_token VARCHAR(64) UNIQUE"))
                            conn.commit()
                        app.logger.info("호환성 마이그레이션 적용: users.webhook_token 컬럼 추가")
                except Exception as mig_e:
                    app.logger.warning(f'호환성 마이그레이션(webhook_token) 적용 실패 또는 불필요: {str(mig_e)}')
                # 호환성 마이그레이션: strategy_accounts 테이블에 is_active 컬럼이 없으면 추가
                try:
                    from sqlalchemy import inspect
                    inspector = inspect(db.engine)
                    columns = [col['name'] for col in inspector.get_columns('strategy_accounts')]
                    if 'is_active' not in columns:
                        with db.engine.connect() as conn:
                            conn.execute(text("ALTER TABLE strategy_accounts ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE"))
                            conn.commit()
                        app.logger.info("호환성 마이그레이션 적용: strategy_accounts.is_active 컬럼 추가")
                except Exception as mig_e:
                    app.logger.warning(f'호환성 마이그레이션(strategy_accounts.is_active) 적용 실패 또는 불필요: {str(mig_e)}')

                # Order Queue System: pending_orders, order_fill_events 테이블 생성 (레이스 컨디션 방지)
                try:
                    from sqlalchemy import inspect

                    # PostgreSQL advisory lock으로 동시성 제어
                    with db.engine.connect() as conn:
                        # 락 획득 시도 (hashtext 사용)
                        lock_acquired = conn.execute(text(
                            "SELECT pg_try_advisory_lock(hashtext('order_queue_migration'))"
                        )).scalar()

                        if lock_acquired:
                            try:
                                # 락 획득 후 재확인
                                inspector = inspect(db.engine)
                                tables = inspector.get_table_names()

                                if 'pending_orders' not in tables or 'order_fill_events' not in tables:
                                    # 마이그레이션 경로를 동적으로 추가
                                    import importlib.util
                                    migrations_path = os.path.join(current_dir, '..', 'migrations')
                                    if os.path.exists(migrations_path) and migrations_path not in sys.path:
                                        sys.path.insert(0, migrations_path)

                                    # 파일명의 밑줄(_)을 dot(.)으로 변환하여 import
                                    spec = importlib.util.spec_from_file_location(
                                        "migration_module",
                                        os.path.join(migrations_path, "20251008_create_order_queue_tables.py")
                                    )
                                    migration_module = importlib.util.module_from_spec(spec)
                                    spec.loader.exec_module(migration_module)
                                    migration_module.upgrade(db.engine)
                                    app.logger.info("✅ 주문 대기열 시스템 마이그레이션 완료")
                                else:
                                    app.logger.debug("주문 대기열 테이블이 이미 존재합니다")
                            finally:
                                # 락 해제
                                conn.execute(text(
                                    "SELECT pg_advisory_unlock(hashtext('order_queue_migration'))"
                                ))
                                conn.commit()
                        else:
                            app.logger.info("다른 워커가 마이그레이션 진행 중 - 대기")
                            # 다른 워커가 락을 보유 중, 블로킹 락 대기
                            conn.execute(text(
                                "SELECT pg_advisory_lock(hashtext('order_queue_migration'))"
                            ))
                            # 락 획득 즉시 해제 (마이그레이션 완료 확인용)
                            conn.execute(text(
                                "SELECT pg_advisory_unlock(hashtext('order_queue_migration'))"
                            ))
                            conn.commit()
                            app.logger.debug("마이그레이션 완료 확인됨")
                except Exception as mig_e:
                    app.logger.warning(f'주문 대기열 마이그레이션 실패 또는 불필요: {str(mig_e)}')
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
                    admin_user.set_password('admin_test_0623')  # 기본 비밀번호
                    db.session.add(admin_user)
                    db.session.commit()
                    app.logger.info('기본 관리자 계정이 생성되었습니다. (username: admin, password: admin_test_0623)')
                    app.logger.info('최초 로그인 시 비밀번호 변경이 필요합니다.')
            except Exception as e:
                app.logger.warning(f'관리자 계정 생성 실패: {str(e)}')
            
            # APScheduler 초기화 및 백그라운드 작업 등록
            init_scheduler(app)

            # 서비스 의존성 초기화 (순환 의존성 해결)
            try:
                from app.services import initialize_services
                services = initialize_services()
                app.logger.info('서비스 의존성 초기화 완료')
            except Exception as e:
                app.logger.error(f'서비스 의존성 초기화 실패: {str(e)}')

            # OrderFillMonitor 초기화
            try:
                from app.services.order_fill_monitor import init_order_fill_monitor
                init_order_fill_monitor(app)
                app.logger.info('✅ OrderFillMonitor 초기화 완료')
            except Exception as e:
                app.logger.error(f'❌ OrderFillMonitor 초기화 실패: {str(e)}')

            # WebSocket 관리자 초기화
            try:
                from app.services.trading import trading_service
                trading_service.init_websocket_manager(app)
                app.logger.info('✅ WebSocket 관리자 초기화 완료')
            except Exception as e:
                app.logger.error(f'❌ WebSocket 관리자 초기화 실패: {str(e)}')
    else:
        app.logger.info('Flask CLI 명령어 실행 중 - 데이터베이스 초기화 및 스케줄러 건너뜀')

    # Flask CLI 명령어 등록
    try:
        from app.cli import init_app as init_cli
        init_cli(app)
        app.logger.debug('Flask CLI 명령어 등록 완료')
    except Exception as e:
        app.logger.warning(f'Flask CLI 명령어 등록 실패: {str(e)}')

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
            from app.services.telegram import telegram_service
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
        # 메인 프로세스가 아닌 경우 (Flask 개발 서버의 reloader 프로세스) 웜업 건너뜁니다
        app.logger.info('🔄 Flask reloader 프로세스에서는 초기 캐시 웜업을 건너뜁니다')
    else:
        try:
            warm_up_precision_cache_with_context(app)
            app.logger.info('✅ 애플리케이션 시작 시 Precision 캐시 웜업 완료')
        except Exception as e:
            app.logger.error(f'❌ 애플리케이션 시작 시 Precision 캐시 웜업 실패: {str(e)}')

        try:
            warm_up_market_caches_with_context(app)
            app.logger.info('✅ 애플리케이션 시작 시 캐시 웜업 완료')
        except Exception as e:
            app.logger.error(f'❌ 애플리케이션 시작 시 캐시 웜업 실패: {str(e)}')
    
    # 🆕 Precision 캐시 주기적 업데이트 (하루 1회, 새벽 3시 7분 - 소수 시간대)
    scheduler.add_job(
        func=update_precision_cache_with_context,
        args=[app],
        trigger="cron",
        hour=3,
        minute=7,
        id='precision_cache_update',
        name='Daily Precision Cache Update',
        replace_existing=True,
        max_instances=1
    )

    # 🆕 Symbol Validator 갱신 (매시 15분 - 소수 시간대)
    from app.services.symbol_validator import symbol_validator
    scheduler.add_job(
        func=symbol_validator.refresh_symbols_with_context,
        args=[app],
        trigger="cron",
        minute=15,
        id='symbol_validator_refresh',
        name='Symbol Validator - Hourly Refresh',
        replace_existing=True,
        max_instances=1
    )

    # 🆕 가격 캐시 업데이트 (31초마다, 소수 주기로 정각 집중 트래픽 회피)
    scheduler.add_job(
        func=update_price_cache_with_context,
        args=[app],
        trigger="interval",
        seconds=31,
        id='update_price_cache',
        name='Update Price Cache',
        replace_existing=True,
        max_instances=1
    )
    # 미체결 주문 상태 업데이트 (29초마다 - 소수 주기)
    scheduler.add_job(
        func=update_open_orders_with_context,
        args=[app],
        trigger="interval",
        seconds=29,
        id='update_open_orders',
        name='Update Open Orders Status',
        replace_existing=True,
        max_instances=1
    )

    # 미실현 손익 계산 (307초마다 ≈ 5분 7초 - 소수 주기)
    scheduler.add_job(
        func=calculate_unrealized_pnl_with_context,
        args=[app],
        trigger="interval",
        seconds=307,
        id='calculate_unrealized_pnl',
        name='Calculate Unrealized PnL',
        replace_existing=True,
        max_instances=1
    )

    # 일일 요약 전송 (매일 저녁 9시 3분 - 소수 시간대)
    scheduler.add_job(
        func=send_daily_summary_with_context,
        args=[app],
        trigger="cron",
        hour=21,
        minute=3,
        id='send_daily_summary',
        name='Send Daily Summary',
        replace_existing=True,
        max_instances=1
    )

    # Phase 3.4: 일일 성과 계산 (매일 00:00:13 - 소수 시간대)
    scheduler.add_job(
        func=calculate_daily_performance_with_context,
        args=[app],
        trigger="cron",
        hour=0,
        minute=0,
        second=13,
        id='calculate_daily_performance',
        name='Calculate Daily Strategy Performance',
        replace_existing=True,
        max_instances=1
    )

    # Phase 4: 자동 리밸런싱 (매시 17분 - 소수 시간대)
    scheduler.add_job(
        func=auto_rebalance_all_accounts_with_context,
        args=[app],
        trigger="cron",
        minute=17,
        id='auto_rebalance_accounts',
        name='Auto Rebalance Accounts',
        replace_existing=True,
        max_instances=1
    )

    # Phase 4.3: 증권 OAuth 토큰 자동 갱신 (6시간마다)
    scheduler.add_job(
        func=refresh_securities_tokens_with_context,
        args=[app],
        trigger="interval",
        hours=6,
        id='securities_token_refresh',
        name='Securities OAuth Token Refresh',
        replace_existing=True,
        max_instances=1
    )

    # Order Queue System: 대기열 재정렬 (1초마다)
    from app.services.background.queue_rebalancer import rebalance_all_symbols_with_context
    scheduler.add_job(
        func=rebalance_all_symbols_with_context,
        args=[app],
        trigger="interval",
        seconds=1,
        id='rebalance_order_queue',
        name='Rebalance Order Queue',
        replace_existing=True,
        max_instances=1
    )

    # Phase 4: WebSocket 연결 상태 모니터링 (1분마다)
    scheduler.add_job(
        func=check_websocket_health_with_context,
        args=[app],
        trigger="interval",
        minutes=1,
        id='check_websocket_health',
        name='Check WebSocket Health',
        replace_existing=True,
        max_instances=1
    )

    app.logger.info(f'백그라운드 작업 등록 완료 - {len(scheduler.get_jobs())}개 작업')

def warm_up_precision_cache_with_context(app):
    """🆕 애플리케이션 컨텍스트 내에서 Precision 캐시 웜업"""
    with app.app_context():
        try:
            from app.services.exchange import exchange_service
            
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
            from app.services.exchange import exchange_service
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

def _refresh_price_cache(app, *, source: str = 'scheduler') -> dict:
    """가격 캐시 갱신 핵심 로직 (앱 컨텍스트 내에서 호출 전제)"""
    from collections import defaultdict

    from app.services.price_cache import price_cache
    from app.services.exchange import exchange_service
    from app.models import StrategyPosition
    from app.constants import Exchange, MarketType

    logger = app.logger
    logger.debug('💰 가격 캐시 갱신 시작 (source=%s)', source)

    supported_exchanges = exchange_service.get_supported_exchanges()
    if not supported_exchanges:
        supported_exchanges = [Exchange.BINANCE]

    # 1) 거래소/마켓 전체 시세 갱신
    for exchange_name in supported_exchanges:
        normalized_exchange = Exchange.normalize(exchange_name) or Exchange.BINANCE

        for market_type in (MarketType.SPOT, MarketType.FUTURES):
            quotes = exchange_service.get_price_quotes(
                exchange=normalized_exchange,
                market_type=market_type,
                symbols=None
            )

            if not quotes:
                continue

            for quote in quotes.values():
                price_cache.set_price(
                    symbol=quote.symbol,
                    price=quote.last_price,
                    exchange=normalized_exchange,
                    market_type=market_type
                )

            logger.debug(
                '📦 가격 캐시 갱신: exchange=%s market=%s symbols=%s (source=%s)',
                normalized_exchange,
                market_type,
                len(quotes),
                source
            )

    # 2) 활성 포지션 심볼 우선 갱신
    active_positions = StrategyPosition.query.filter(
        StrategyPosition.quantity != 0
    ).all()

    symbol_groups = defaultdict(set)

    for position in active_positions:
        strategy_account = position.strategy_account
        if not strategy_account:
            continue

        account = strategy_account.account
        strategy = strategy_account.strategy
        if not account or not strategy:
            continue

        exchange_name = account.exchange or Exchange.BINANCE
        market_type = strategy.market_type or account.market_type or MarketType.SPOT

        normalized_exchange = Exchange.normalize(exchange_name) or Exchange.BINANCE
        normalized_market = MarketType.normalize(market_type) if market_type else MarketType.SPOT

        symbol_groups[(normalized_exchange, normalized_market)].add(position.symbol.upper())

    if symbol_groups:
        for (exchange_name, market_type), symbols in symbol_groups.items():
            symbol_list = sorted(symbols)
            if not symbol_list:
                continue

            updated = price_cache.update_batch_prices(
                symbols=symbol_list,
                exchange=exchange_name,
                market_type=market_type
            )
            logger.debug(
                '%s %s 가격 캐시 추가 갱신: %s개 심볼 (source=%s)',
                exchange_name,
                market_type,
                len(updated),
                source
            )
    else:
        logger.debug('활성 포지션이 없어 추가 갱신 단계는 건너뜁니다 (source=%s)', source)

    stats = price_cache.get_stats()
    return stats


def warm_up_market_caches_with_context(app):
    """애플리케이션 초기 구동 시 캐시를 일괄 웜업"""
    with app.app_context():
        try:
            stats = _refresh_price_cache(app, source='startup')
            app.logger.info('✅ 가격 캐시 초기 웜업 완료 - 통계: %s', stats)
        except Exception as e:
            app.logger.error(f'❌ 가격 캐시 초기 웜업 실패: {str(e)}')


def update_price_cache_with_context(app):
    """주기적으로 가격 캐시를 갱신"""
    with app.app_context():
        try:
            stats = _refresh_price_cache(app, source='scheduler')
            app.logger.debug(f'💰 가격 캐시 통계: {stats}')
        except Exception as e:
            app.logger.error(f'❌ 가격 캐시 업데이트 실패: {str(e)}')

def update_open_orders_with_context(app):
    """Flask 앱 컨텍스트 내에서 미체결 주문 상태 업데이트"""
    with app.app_context():
        try:
            from app.services.trading import trading_service as order_service
            order_service.update_open_orders_status()
            app.logger.debug('미체결 주문 상태 업데이트 완료')
        except Exception as e:
            app.logger.error(f'미체결 주문 상태 업데이트 실패: {str(e)}')
            try:
                from app.services.telegram import telegram_service
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
            from app.services.trading import trading_service as position_service
            position_service.calculate_unrealized_pnl()
            app.logger.debug('미실현 손익 계산 완료')
        except Exception as e:
            app.logger.error(f'미실현 손익 계산 실패: {str(e)}')
            try:
                from app.services.telegram import telegram_service
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
            from app.services.analytics import analytics_service
            from app.services.telegram import telegram_service
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
                from app.services.telegram import telegram_service
                if telegram_service.is_enabled():
                    telegram_service.send_error_alert(
                        "백그라운드 작업 오류",
                        f"일일 요약 보고서 전송 실패: {str(e)}"
                    )
            except Exception:
                pass  # 텔레그램 알림 실패는 조용히 무시

def auto_rebalance_all_accounts_with_context(app):
    """
    Phase 4: Flask 앱 컨텍스트 내에서 자동 리밸런싱 실행

    모든 활성 계좌에 대해 리밸런싱 조건을 확인하고,
    조건 충족 시 자동으로 자본 재배분을 실행합니다.
    매시 17분에 실행됩니다 (소수 시간대).
    """
    with app.app_context():
        try:
            from app.services.capital_service import capital_allocation_service
            from app.models import Account

            app.logger.info('🔄 자동 리밸런싱 작업 시작')

            # 모든 활성 계좌 조회
            accounts = Account.query.filter_by(is_active=True).all()

            if not accounts:
                app.logger.info('  ℹ️  활성 계좌가 없습니다')
                return

            rebalanced_count = 0
            skipped_count = 0
            failed_count = 0

            for account in accounts:
                try:
                    # 리밸런싱 조건 확인
                    check_result = capital_allocation_service.should_rebalance(
                        account_id=account.id,
                        min_interval_hours=1  # 최소 1시간 간격
                    )

                    if not check_result['should_rebalance']:
                        app.logger.debug(
                            f'  ⏭️  계좌 {account.id} ({account.name}): 리밸런싱 건너뜀 - {check_result["reason"]}'
                        )
                        skipped_count += 1
                        continue

                    # 리밸런싱 실행 (실시간 잔고 사용)
                    rebalance_result = capital_allocation_service.recalculate_strategy_capital(
                        account_id=account.id,
                        use_live_balance=True
                    )

                    app.logger.info(
                        f'  ✅ 계좌 {account.id} ({account.name}): 리밸런싱 완료 - '
                        f'{len(rebalance_result.get("allocations", []))}개 전략, '
                        f'총 자본 {rebalance_result.get("total_capital", 0):.2f} USDT'
                    )
                    rebalanced_count += 1

                except Exception as e:
                    app.logger.error(f'  ❌ 계좌 {account.id} 리밸런싱 실패: {e}')
                    failed_count += 1

            app.logger.info(
                f'✅ 자동 리밸런싱 작업 완료 - '
                f'성공: {rebalanced_count}, 건너뜀: {skipped_count}, 실패: {failed_count}'
            )

        except Exception as e:
            app.logger.error(f'❌ 자동 리밸런싱 작업 실패: {e}')
            # 텔레그램 알림 (선택사항)
            try:
                from app.services.telegram import telegram_service
                if telegram_service.is_enabled():
                    telegram_service.send_error_alert(
                        "백그라운드 작업 오류",
                        f"자동 리밸런싱 실패: {str(e)}"
                    )
            except Exception:
                pass  # 텔레그램 알림 실패는 조용히 무시

def calculate_daily_performance_with_context(app):
    """
    Phase 3.4: Flask 앱 컨텍스트 내에서 일일 성과 계산

    모든 활성 전략에 대해 전날의 성과를 계산하고 DB에 저장합니다.
    매일 자정 30초 후 실행되어 전날(어제) 데이터를 처리합니다.
    """
    with app.app_context():
        try:
            from app.services.performance_tracking import performance_tracking_service
            from app.models import Strategy
            from datetime import date, timedelta

            yesterday = date.today() - timedelta(days=1)
            app.logger.info(f'📊 일일 성과 계산 시작 (대상 날짜: {yesterday})')

            # 모든 활성 전략 조회
            strategies = Strategy.query.filter_by(is_active=True).all()

            success_count = 0
            fail_count = 0

            for strategy in strategies:
                try:
                    performance = performance_tracking_service.calculate_daily_performance(
                        strategy_id=strategy.id,
                        target_date=yesterday
                    )

                    if performance:
                        app.logger.info(
                            f'  ✅ 전략 {strategy.id} ({strategy.name}): '
                            f'일일 PnL {performance.daily_pnl} USDT, '
                            f'거래 {performance.total_trades}건'
                        )
                        success_count += 1
                    else:
                        app.logger.warning(f'  ⚠️ 전략 {strategy.id} ({strategy.name}): 성과 계산 실패')
                        fail_count += 1

                except Exception as e:
                    app.logger.error(f'  ❌ 전략 {strategy.id} 성과 계산 오류: {str(e)}')
                    fail_count += 1

            app.logger.info(
                f'📊 일일 성과 계산 완료: '
                f'성공 {success_count}개, 실패 {fail_count}개 (총 {len(strategies)}개 전략)'
            )

            # 성공률이 50% 미만이면 경고
            if len(strategies) > 0 and (fail_count / len(strategies)) >= 0.5:
                app.logger.warning('⚠️ 성과 계산 실패율이 50% 이상입니다!')

        except Exception as e:
            app.logger.error(f'일일 성과 계산 작업 실패: {str(e)}')
            try:
                from app.services.telegram import telegram_service
                if telegram_service.is_enabled():
                    telegram_service.send_error_alert(
                        "백그라운드 작업 오류",
                        f"일일 성과 계산 실패: {str(e)}"
                    )
            except Exception:
                pass  # 텔레그램 알림 실패는 조용히 무시

def check_websocket_health_with_context(app):
    """
    Phase 4: Flask 앱 컨텍스트 내에서 WebSocket 연결 상태 모니터링

    활성 계정의 WebSocket 연결 상태를 확인하고,
    연결이 끊어진 계정은 자동으로 재연결합니다.
    """
    with app.app_context():
        try:
            from app.services.trading import trading_service
            from app.models import Account

            if not trading_service.websocket_manager:
                return

            # 통계 조회
            stats = trading_service.websocket_manager.get_stats()
            app.logger.debug(
                f"🔌 WebSocket 상태 - "
                f"전체: {stats['total_connections']}, "
                f"활성: {stats['active_connections']}, "
                f"구독: {stats['total_subscriptions']}"
            )

            # 모든 활성 계정 조회
            active_accounts = Account.query.filter_by(is_active=True).all()

            for account in active_accounts:
                # 지원하는 거래소인지 확인
                if account.exchange.upper() not in ['BINANCE', 'BYBIT']:
                    continue

                connection = trading_service.websocket_manager.get_connection(account.id)

                # 연결되지 않은 경우 시작
                if not connection:
                    app.logger.info(f"🔌 WebSocket 연결 시작 - 계정: {account.id}")
                    trading_service.start_websocket_for_account(account.id)
                elif not connection.is_connected:
                    # 연결이 끊어진 경우 재연결
                    app.logger.warning(f"⚠️ WebSocket 연결 끊김 감지 - 계정: {account.id}")
                    trading_service.websocket_manager._schedule_coroutine(
                        trading_service.websocket_manager.auto_reconnect(account.id, 0)
                    )

        except Exception as e:
            app.logger.error(f"❌ WebSocket 상태 모니터링 실패: {str(e)}")

def refresh_securities_tokens_with_context(app):
    """
    Phase 4.3: Flask 앱 컨텍스트 내에서 증권 OAuth 토큰 자동 갱신

    모든 증권 계좌의 OAuth 토큰을 자동으로 갱신합니다.
    6시간마다 실행되어 토큰 만료를 방지합니다.

    관련 문서:
    - docs/korea_investment_api_auth.md (Line 78-82)
      * 토큰 유효기간: 24시간
      * 갱신 주기: 6시간
    """
    with app.app_context():
        try:
            from app.jobs.securities_token_refresh import SecuritiesTokenRefreshJob

            result = SecuritiesTokenRefreshJob.run(app)

            # 실패한 계좌가 있으면 경고 로그
            if result['failed'] > 0:
                app.logger.warning(
                    f"⚠️ 증권 토큰 갱신 중 {result['failed']}개 계좌 실패"
                )
                for failed in result['failed_accounts']:
                    app.logger.error(
                        f"  - 계좌 {failed['account_id']} ({failed['account_name']}): {failed['error']}"
                    )

        except Exception as e:
            app.logger.error(f'❌ 증권 토큰 자동 갱신 작업 실패: {str(e)}')
            try:
                from app.services.telegram import telegram_service
                if telegram_service.is_enabled():
                    telegram_service.send_error_alert(
                        "백그라운드 작업 오류",
                        f"증권 토큰 자동 갱신 실패: {str(e)}"
                    )
            except Exception:
                pass  # 텔레그램 알림 실패는 조용히 무시

