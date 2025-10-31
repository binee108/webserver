"""
애플리케이션 설정 모듈

Pydantic Settings를 사용하여 환경 변수를 타입 안전하게 로드합니다.
"""

from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from typing import List
import logging

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """애플리케이션 설정"""

    # Database Configuration
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://trader:password@localhost:5432/trading_system",
        description="PostgreSQL 비동기 연결 URL"
    )

    # Redis Configuration
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis 연결 URL"
    )

    # Security
    SECRET_KEY: str = Field(
        default="your-secret-key-change-this-in-production",
        description="JWT 토큰 서명 키"
    )
    ALGORITHM: str = Field(
        default="HS256",
        description="JWT 알고리즘"
    )
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=30,
        description="액세스 토큰 만료 시간 (분)"
    )

    # Database Performance
    DB_POOL_SIZE: int = Field(
        default=20,
        ge=1,
        le=100,
        description="DB 커넥션 풀 크기"
    )
    DB_MAX_OVERFLOW: int = Field(
        default=10,
        ge=0,
        le=50,
        description="DB 커넥션 풀 최대 오버플로우"
    )
    DB_POOL_PRE_PING: bool = Field(
        default=True,
        description="커넥션 사용 전 유효성 체크"
    )

    # Order Processing Configuration
    MARKET_ORDER_TIMEOUT: int = Field(
        default=10,
        ge=1,
        le=60,
        description="MARKET 주문 타임아웃 (초)"
    )
    CANCEL_QUEUE_INTERVAL: int = Field(
        default=10,
        ge=5,
        le=60,
        description="Cancel Queue 처리 간격 (초)"
    )
    MAX_CANCEL_RETRIES: int = Field(
        default=5,
        ge=1,
        le=10,
        description="최대 취소 재시도 횟수"
    )

    # Exchange API Keys (Phase 3)
    BINANCE_API_KEY: str = Field(
        default="",
        description="Binance API Key"
    )
    BINANCE_API_SECRET: str = Field(
        default="",
        description="Binance API Secret"
    )

    BYBIT_API_KEY: str = Field(
        default="",
        description="Bybit API Key"
    )
    BYBIT_API_SECRET: str = Field(
        default="",
        description="Bybit API Secret"
    )

    UPBIT_API_KEY: str = Field(
        default="",
        description="Upbit Access Key"
    )
    UPBIT_API_SECRET: str = Field(
        default="",
        description="Upbit Secret Key"
    )

    # Exchange Settings (Phase 3)
    EXCHANGE_TIMEOUT: int = Field(
        default=30,
        ge=5,
        le=120,
        description="거래소 API 타임아웃 (초)"
    )
    EXCHANGE_MAX_RETRIES: int = Field(
        default=3,
        ge=1,
        le=10,
        description="거래소 API 최대 재시도 횟수"
    )

    # Exchange Rate Limits (requests per second)
    BINANCE_RATE_LIMIT: float = Field(
        default=10.0,
        ge=1.0,
        le=100.0,
        description="Binance Rate Limit (req/s)"
    )
    BYBIT_RATE_LIMIT: float = Field(
        default=10.0,
        ge=1.0,
        le=100.0,
        description="Bybit Rate Limit (req/s)"
    )
    UPBIT_RATE_LIMIT: float = Field(
        default=8.0,
        ge=1.0,
        le=100.0,
        description="Upbit Rate Limit (req/s) - 주문 API"
    )

    # Mock Exchange (Phase 2/3 테스트)
    USE_MOCK_EXCHANGE: bool = Field(
        default=True,
        description="Mock Exchange 사용 여부 (테스트용)"
    )

    # Application Configuration
    ENV: str = Field(
        default="development",
        description="환경 (development, production)"
    )
    DEBUG: bool = Field(
        default=True,
        description="디버그 모드"
    )
    APP_HOST: str = Field(
        default="0.0.0.0",
        description="앱 호스트"
    )
    APP_PORT: int = Field(
        default=8000,
        ge=1024,
        le=65535,
        description="앱 포트"
    )

    # CORS Configuration
    CORS_ORIGINS: str = Field(
        default="http://localhost:3000,http://localhost:8000",
        description="CORS 허용 오리진 (쉼표로 구분)"
    )
    CORS_ALLOW_CREDENTIALS: bool = Field(
        default=True,
        description="CORS 인증 허용"
    )
    CORS_ALLOW_METHODS: str = Field(
        default="*",
        description="CORS 허용 메서드"
    )
    CORS_ALLOW_HEADERS: str = Field(
        default="*",
        description="CORS 허용 헤더"
    )

    # Logging Configuration
    LOG_LEVEL: str = Field(
        default="INFO",
        description="로그 레벨"
    )

    @field_validator("CORS_ORIGINS", mode="after")
    @classmethod
    def parse_cors_origins(cls, v):
        """CORS_ORIGINS를 리스트로 변환"""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    @field_validator("CORS_ALLOW_METHODS", mode="after")
    @classmethod
    def parse_cors_methods(cls, v):
        """CORS_ALLOW_METHODS를 리스트로 변환"""
        if isinstance(v, str):
            if v == "*":
                return ["*"]
            return [method.strip() for method in v.split(",")]
        return v

    @field_validator("CORS_ALLOW_HEADERS", mode="after")
    @classmethod
    def parse_cors_headers(cls, v):
        """CORS_ALLOW_HEADERS를 리스트로 변환"""
        if isinstance(v, str):
            if v == "*":
                return ["*"]
            return [header.strip() for header in v.split(",")]
        return v

    @field_validator("ENV")
    @classmethod
    def validate_env(cls, v):
        """ENV 값 검증"""
        allowed = ["development", "production", "test"]
        if v not in allowed:
            raise ValueError(f"ENV must be one of {allowed}")
        return v

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v):
        """LOG_LEVEL 값 검증"""
        allowed = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {allowed}")
        return v.upper()

    class Config:
        """Pydantic 설정"""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# 전역 설정 인스턴스
settings = Settings()


# 설정 로드 확인
if __name__ != "__main__":
    logger.info(f"⚙️ Settings loaded: ENV={settings.ENV}, DEBUG={settings.DEBUG}")
    logger.info(f"📊 DB Pool: size={settings.DB_POOL_SIZE}, max_overflow={settings.DB_MAX_OVERFLOW}")
    logger.info(f"⏱️ Timeouts: MARKET={settings.MARKET_ORDER_TIMEOUT}s, CancelQueue={settings.CANCEL_QUEUE_INTERVAL}s")
