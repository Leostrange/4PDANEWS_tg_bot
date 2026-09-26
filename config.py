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

    # ── AI-провайдер (OpenAI-совместимый API) ──
    API_BASE_URL: str = os.getenv("API_BASE_URL", "https://api.openai.com/v1")
    API_KEY: str = os.getenv("API_KEY", "")
    MODEL: str = os.getenv("MODEL", "gpt-4o")
    MAX_TOKENS: int = int(os.getenv("MAX_TOKENS", "16384"))
    TEMPERATURE: float = float(os.getenv("TEMPERATURE", "0.3"))

    # ── Промпт ──
    SYSTEM_PROMPT_FILE: str = os.getenv("SYSTEM_PROMPT_FILE", "system_prompt.md")

    # ── Лимиты ──
    MAX_POSTS: int = int(os.getenv("MAX_POSTS", "100"))
    MAX_CHARS: int = int(os.getenv("MAX_CHARS", "500000"))

    @classmethod
    def validate(cls) -> list[str]:
        """Проверяет обязательные настройки. Возвращает список ошибок."""
        errors = []
        if not cls.BOT_TOKEN:
            errors.append("BOT_TOKEN не задан")
        if not cls.API_KEY:
            errors.append("API_KEY не задан (ключ от AI-провайдера)")
        return errors

    @classmethod
    def print_config(cls):
        """Выводит текущую конфигурацию (без секретов)."""
        key_preview = cls.API_KEY[:8] + "..." if cls.API_KEY else "НЕ ЗАДАН"
        print(f"""
╔══════════════════════════════════════════════╗
║           Конфигурация Telegram-бота         ║
╠══════════════════════════════════════════════╣
║  AI Base URL:  {cls.API_BASE_URL:<28s} ║
║  API Key:      {key_preview:<28s} ║
║  Model:        {cls.MODEL:<28s} ║
║  Max Tokens:   {str(cls.MAX_TOKENS):<28s} ║
║  Temperature:  {str(cls.TEMPERATURE):<28s} ║
║  Prompt File:  {cls.SYSTEM_PROMPT_FILE:<28s} ║
║  Bot Token:    {"✓ задан" if cls.BOT_TOKEN else "✗ НЕ ЗАДАН":<28s} ║
╚══════════════════════════════════════════════╝
        """)
