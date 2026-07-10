"""Конфигурация приложения. Значения загружаются из .env."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Корень проекта
BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    """Настройки бота, RAG-пайплайна и внешних API."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Telegram ──────────────────────────────────────────────
    bot_token: str = ""
    # Таймауты Telegram API (сек). На серверах с плохой связью — увеличить.
    telegram_connect_timeout: int = 30
    telegram_read_timeout: int = 60
    # Макс. попыток переподключения при сетевых ошибках
    telegram_retry_attempts: int = 5

    # ── Yandex AI Studio ──────────────────────────────────────
    yandex_api_key: str = ""
    yandex_folder_id: str = ""

    # LLM: YandexGPT Lite — дёшево, продукт Яндекса, хорошо работает с русским
    llm_model: str = "yandexgpt-lite"
    llm_temperature: float = 0.3
    llm_max_tokens: int = 500

    # Модель эмбеддингов: text-search-doc для индексации, text-search-query для запросов
    embedding_model_doc: str = "text-search-doc"
    embedding_model_query: str = "text-search-query"

    # ── RAG ───────────────────────────────────────────────────
    chunk_size: int = 1000            # символов на чанк (~250 токенов, лимит API 2048)
    chunk_overlap: int = 200          # перекрытие в символах
    top_k: int = 3                    # сколько чанков передаём в LLM
    relevance_threshold: float = 0.35  # порог cosine similarity (Yandex embeddings дают ниже скор, чем OpenAI)

    # ── Пути ──────────────────────────────────────────────────
    vector_store_dir: str = "data/vector_store"
    kb_path: str = "data/knowledge_base.json"
    db_path: str = "data/analytics.db"

    @property
    def vector_store_path(self) -> Path:
        """Путь к .npz файлу с матрицей эмбеддингов."""
        return BASE_DIR / self.vector_store_dir / "vector_store.npz"

    @property
    def metadata_path(self) -> Path:
        """Путь к JSON с метаданными чанков."""
        return BASE_DIR / self.vector_store_dir / "metadata.json"

    @property
    def kb_file(self) -> Path:
        return BASE_DIR / self.kb_path

    @property
    def db_file(self) -> Path:
        return BASE_DIR / self.db_path


settings = Settings()
