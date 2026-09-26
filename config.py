"""
Конфигурация Telegram-бота.
Настройки загружаются из переменных окружения или .env файла.
"""

import os

# ── Попытка загрузить .env файл (необязательно) ──
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv не установлен — читаем из env напрямую


class Config:
    """Все настройки бота в одном месте."""

    # ── Telegram ──
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    ALLOWED_USER_IDS: set[int] = {
        int(value.strip()) for value in os.getenv("ALLOWED_USER_IDS", "").split(",")
        if value.strip()
    }

    # ── Параметры генерации ──
    MAX_TOKENS: int = int(os.getenv("MAX_TOKENS", "16384"))
    TEMPERATURE: float = float(os.getenv("TEMPERATURE", "0.3"))

    # ── Промпт ──
    SYSTEM_PROMPT_FILE: str = os.getenv("SYSTEM_PROMPT_FILE", "system_prompt.md")

    # ── Лимиты ──
    MAX_POSTS: int = int(os.getenv("MAX_POSTS", "100"))
    MAX_CHARS: int = int(os.getenv("MAX_CHARS", "60000"))
    DATA_FILE: str = os.getenv("DATA_FILE", "data/sessions.json")

    @classmethod
    def validate(cls) -> list[str]:
        """Проверяет обязательные настройки. Возвращает список ошибок."""
        errors = []
        if not cls.BOT_TOKEN:
            errors.append("BOT_TOKEN не задан")
        if cls.MAX_POSTS <= 0 or cls.MAX_CHARS <= 0:
            errors.append("MAX_POSTS и MAX_CHARS должны быть положительными")
        return errors
