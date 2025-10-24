"""CLI 시스템 설정

@FEAT:cli-migration @COMP:config @TYPE:core

run_legacy.py의 모든 상수를 중앙 집중화하여 관리합니다.
TradingSystemManager의 클래스 상수들을 이 모듈로 추출했습니다.
"""
from pathlib import Path


class SystemConfig:
    """시스템 전역 설정

    TradingSystemManager의 클래스 상수들을 중앙 집중화
    Helper와 Command에서 공통으로 사용하는 설정값을 관리합니다.
    """

    # ============================================================================
    # 포트 설정
    # ============================================================================
    DEFAULT_FLASK_PORT = 5001
    FLASK_PORT_RANGE = (5001, 5010)
    DEFAULT_POSTGRES_PORT = 5432
    POSTGRES_PORT_RANGE = (5432, 5441)
    DEFAULT_HTTPS_PORT = 443
    HTTPS_PORT_RANGE = (443, 452)
    DEFAULT_HTTP_PORT = 80

    # ============================================================================
    # Docker 설정
    # ============================================================================
    DEFAULT_PROJECT_NAME = "webserver"
    COMPOSE_FILE = "docker-compose.yml"

    # ============================================================================
    # 대기 시간 설정
    # ============================================================================
    POSTGRES_MAX_WAIT_ATTEMPTS = 30
    POSTGRES_WAIT_INTERVAL = 2

    # ============================================================================
    # 외부 IP 조회 서비스
    # ============================================================================
    EXTERNAL_IP_SERVICES = [
        'https://api.ipify.org',
        'https://ifconfig.me/ip',
        'https://icanhazip.com'
    ]

    # ============================================================================
    # 환경별 기본값 (EnvHelper에서 사용)
    # ============================================================================
    COMMON_DEFAULTS = {
        'ENABLE_SSL': 'true',
        'FORCE_HTTPS': 'true',
        'SSL_CERT_DIR': 'certs',
        'SSL_DOMAIN': 'localhost',
        'PORT': '443',
        'HSTS_MAX_AGE': '31536000',
        'SESSION_COOKIE_SECURE': 'True',
        'SESSION_COOKIE_HTTPONLY': 'True',
        'SESSION_COOKIE_SAMESITE': 'Lax',
        'PERMANENT_SESSION_LIFETIME': '3600',
        'SCHEDULER_API_ENABLED': 'True'
    }

    ENV_DEFAULTS = {
        'development': {
            'FLASK_ENV': 'development',
            'DEBUG': 'True',
            'LOG_LEVEL': 'DEBUG',
            'LOG_FILE': 'logs/app.log',
            'BACKGROUND_LOG_LEVEL': 'DEBUG',
            'DATABASE_URL': 'postgresql://trader:password123@postgres:5432/trading_dev',
            'SKIP_EXCHANGE_TEST': 'False'
        },
        'staging': {
            'FLASK_ENV': 'staging',
            'DEBUG': 'False',
            'LOG_LEVEL': 'INFO',
            'LOG_FILE': 'logs/app.log',
            'BACKGROUND_LOG_LEVEL': 'WARNING',
            'DATABASE_URL': 'postgresql://trader:password123@postgres:5432/trading_staging',
            'SKIP_EXCHANGE_TEST': 'False'
        },
        'production': {
            'FLASK_ENV': 'production',
            'DEBUG': 'False',
            'LOG_LEVEL': 'WARNING',
            'LOG_FILE': 'logs/app.log',
            'BACKGROUND_LOG_LEVEL': 'ERROR',
            'DATABASE_URL': 'postgresql://trader:secure_password@postgres:5432/trading_prod',
            'SKIP_EXCHANGE_TEST': 'False',
            'SESSION_COOKIE_SAMESITE': 'Strict'
        }
    }

    # ============================================================================
    # SSL/보안 설정
    # ============================================================================
    SSL_CERT_DIR = 'certs'
    SSL_DOMAIN = 'localhost'
    SSL_CERT_VALIDITY_DAYS = 365

    @classmethod
    def get_root_dir(cls) -> Path:
        """프로젝트 루트 디렉토리 반환

        Returns:
            Path: 프로젝트 루트 경로 (절대 경로)
        """
        # cli/config.py → cli/ → project_root/
        return Path(__file__).parent.parent.resolve()
