"""
환경변수 기반 애플리케이션 설정.

Pydantic BaseSettings로 .env / 시스템 환경변수를 읽고,
개발(development) / 운영(production) 환경을 분리합니다.
"""

from enum import Enum
from functools import lru_cache
from typing import List, Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    """실행 환경 구분."""

    DEVELOPMENT = "development"
    PRODUCTION = "production"
    TESTING = "testing"


class Settings(BaseSettings):
    """전역 설정 — 환경변수 또는 .env 파일에서 로드."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- 애플리케이션 ---
    APP_NAME: str = "PeakBridge EV Peak Shaving API"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: Environment = Environment.DEVELOPMENT
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # --- 서버 ---
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    ALLOWED_ORIGINS: List[str] = Field(default=[
        "http://localhost:5173",
        "http://localhost:3000",
        "https://peakbridge-production.up.railway.app",
        "*"
    ])

    # --- 데이터베이스 (PostgreSQL + TimescaleDB, asyncpg 드라이버) ---
    DB_URL: str = Field(
        default="postgresql+asyncpg://peakbridge:peakbridge@localhost:5432/peakbridge"
    )
    DATABASE_URL: str | None = None
    DB_ECHO: bool = False
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # --- MQTT (EV 충전기 / 그리드 센서 연동) ---
    MQTT_HOST: str = "localhost"
    MQTT_PORT: int = 1883
    MQTT_USERNAME: str | None = None
    MQTT_PASSWORD: str | None = None
    MQTT_TOPIC_PREFIX: str = "peakbridge"

    # --- 보안 ---
    JWT_SECRET: str = Field(default="change-me-in-production-use-strong-secret")
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # --- 피크쉐이빙 ---
    PEAK_THRESHOLD_A: float = 15.0
    ESS_MIN_SOC: float = 20.0

    # --- ML ---
    ML_MODEL_DIR: str = "./data/models"

    # --- 전력 요금 (피크쉐이빙 경제성 계산용, 원/kWh) ---
    KWH_PRICE: float = 150.0
    PEAK_KWH_PRICE: float = 250.0
    
    # --- 기상청 API ---
    WEATHER_API_KEY: str = "QlrgTilFRBWa4E4pRXQVVQ"
    WEATHER_NX: int = 98
    WEATHER_NY: int = 76
    
    # --- 한전 API ---
    KEPCO_API_KEY: str = "bfd9f8210ee4ea52b156c2b570822168f22977469c8765f7c346e217edc97533"

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_allowed_origins(cls, value: str | List[str]) -> List[str]:
        """쉼표 구분 문자열 또는 리스트 형태의 CORS origin을 파싱."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def use_database_url_if_available(self) -> "Settings":
        """Railway에서 제공하는 DATABASE_URL 환경변수를 DB_URL로 사용 (postgres:// → postgresql+asyncpg://로 변환)"""
        if self.DATABASE_URL:
            db_url = self.DATABASE_URL
            # Railway에서 제공하는 postgres:// 를 postgresql+asyncpg:// 로 변환
            if db_url.startswith("postgres://"):
                db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
            elif db_url.startswith("postgresql://"):
                db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
            self.DB_URL = db_url
        return self

    @property
    def is_development(self) -> bool:
        """개발 환경 여부."""
        return self.ENVIRONMENT == Environment.DEVELOPMENT

    @property
    def is_production(self) -> bool:
        """운영 환경 여부."""
        return self.ENVIRONMENT == Environment.PRODUCTION


@lru_cache
def get_settings() -> Settings:
    """설정 싱글톤 — 애플리케이션 수명 동안 한 번만 로드."""
    return Settings()


settings = get_settings()
