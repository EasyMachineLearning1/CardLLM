"""Конфигурация приложения. Загружается из переменных окружения / .env файла."""
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки сервиса карточек приборов."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # GigaChat
    gigachat_credentials: str  # base64-ключ авторизации (client_id:client_secret)
    gigachat_scope: str = "GIGACHAT_API_PERS"  # или GIGACHAT_API_B2B / GIGACHAT_API_CORP
    gigachat_model: str = "GigaChat"
    gigachat_verify_ssl: bool = True  # False допустимо только для локальной отладки
    gigachat_temperature: float = 0.2  # низкая температура — меньше фантазий модели
    gigachat_timeout: int = 120  # таймаут запроса к API, сек
    gigachat_max_retries: int = 3  # попыток при временных сбоях API
    gigachat_retry_delay: float = 1.0  # базовая задержка между попытками, сек

    # Приложение
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_debug: bool = False

    @field_validator("gigachat_credentials")
    @classmethod
    def credentials_required(cls, value: str) -> str:
        """Fail-fast: без ключа авторизации сервис запускать бессмысленно."""
        value = value.strip()
        if not value:
            raise ValueError(
                "GIGACHAT_CREDENTIALS не задан: укажите base64-ключ авторизации "
                "(client_id:client_secret) в .env или переменных окружения"
            )
        return value


@lru_cache
def get_settings() -> Settings:
    """Singleton-доступ к настройкам."""
    return Settings()
