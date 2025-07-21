import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """기본 설정 클래스"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///trading_system.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # 텔레그램 봇 설정
    TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
    
    # 로깅 설정
    LOG_LEVEL = os.environ.get('LOG_LEVEL') or 'INFO'
    LOG_FILE = os.environ.get('LOG_FILE') or 'logs/app.log'
    # 백그라운드 작업용 로깅 레벨 (스케줄러 작업)
    BACKGROUND_LOG_LEVEL = os.environ.get('BACKGROUND_LOG_LEVEL') or 'WARNING'
    
    # APScheduler 설정
    SCHEDULER_API_ENABLED = True
    
    # 보안 설정
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None

class DevelopmentConfig(Config):
    """개발 환경 설정"""
    DEBUG = True
    SQLALCHEMY_ECHO = False
    SKIP_EXCHANGE_TEST = False  # 개발 환경에서는 거래소 연결 테스트 건너뛰기
    # 개발 환경에서는 백그라운드 작업도 DEBUG 레벨로 로깅
    LOG_LEVEL = os.environ.get('LOG_LEVEL') or 'DEBUG'
    BACKGROUND_LOG_LEVEL = os.environ.get('BACKGROUND_LOG_LEVEL') or 'DEBUG'

class ProductionConfig(Config):
    """운영 환경 설정"""
    DEBUG = False
    SQLALCHEMY_ECHO = False
    # 프로덕션 환경에서는 백그라운드 작업은 WARNING 이상만 로깅
    LOG_LEVEL = os.environ.get('LOG_LEVEL') or 'INFO'
    BACKGROUND_LOG_LEVEL = os.environ.get('BACKGROUND_LOG_LEVEL') or 'WARNING'

class TestingConfig(Config):
    """테스트 환경 설정"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///test.db'
    WTF_CSRF_ENABLED = False

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
} 