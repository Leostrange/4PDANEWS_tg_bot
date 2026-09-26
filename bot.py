"""
Telegram-бот для анализа постов и создания сводок с помощью ИИ.

Работа:
  1. Пересылай посты из сохранённой папки боту (/new начать сессию)
  2. Когда все посты собраны — жми /gen
  3. Бот отправит запрос в ИИ с твоими правилами оформления
  4. Получи готовую сводку, скопируй или экспортируй в файл

Запуск:
  pip install aiogram aiohttp
  python bot.py
"""

import asyncio
import logging
import os
from datetime import datetime

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile
from aiogram.enums import ParseMode

from config import Config
from ai_client import AIClient

# ── Логирование ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(name)s │ %(levelname)s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("bot")

# ── Инициализация ──
bot = Bot(token=Config.BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()
router = Router()
dp.include_router(router)

ai = AIClient()

# ── Хранилище сессий (per-user) ──
# Ключ: user_id (int)
# Значение: dict с полями posts, summaries, processing, mode
sessions: dict[int, dict] = {}


def get_session(user_id: int) -> dict:
    """Получить или создать сессию пользователя."""
    if user_id not in sessions:
        sessions[user_id] = {
            "posts": [],           # [{text, source, date, media_type}]
            "summaries": [],       # [str — готовые сводки]
            "processing": False,   # Идёт ли сейчас генерация
            "mode": "manual",      # manual / auto
            "summary_counter": 0,  # Счётчик сводок (для номера #NNN)
        }
    return sessions[user_id]


def load_prompt() -> str:
    """Загрузить системный промпт из файла."""
    prompt_file = Config.SYSTEM_PROMPT_FILE
    if os.path.exists(prompt_file):
        with open(prompt_file, "r", encoding="utf-8") as f:
            content = f.read()
        logger.info(f"✓ Промпт загружен: {prompt_file} ({len(content)} символов)")
        return content
    else:
        logger.warning(f"✗ Файл промпта не найден: {prompt_file}")
        return _default_prompt()


def _default_prompt() -> str:
    """Промпт по умолчанию (если файл не найден)."""
    return """Ты — ИИ-ассистент, который анализирует посты из Telegram-каналов
и создаёт структурированные сводки в формате HTML.

ПРАВИЛА:
1. Анализируй каждый пост и определяй его категорию
2. Для каждого поста напиши: что произошло, в чём суть
3. Создай итоговую сводку с заголовком и категориями
4. Используй HTML-разметку Telegram: <b>, <i>, <code>, <a>
5. Каждая тема — отдельный блок с эмодзи-категорией
6. Текст — информативный и лаконичный
7. Ссылки сохраняй оригинальными"""


# ═══════════════════════════════════════════════════════════════
#  КОМАНДЫ
# ═══════════════════════════════════════════════════════════════


@router.message(Command("start"))
async def cmd_start(message: Message):
    """Приветствие и инструкция."""
    text = (
        "👋 <b>Привет! Я бот для создания сводок с помощью ИИ.</b>\n\n"
        "📋 <b>Как пользоваться:</b>\n"
        "1. Нажми /new — начать новую сессию\n"
        "2. Пересылай посты из сохранённой папки\n"
        "3. Когда все посты собраны — жми /gen\n"
        "4. Получи готовую сводку!\n\n"
        "⚙️ <b>Команды:</b>\n"
        "/new — новая сессия (очистить старые посты)\n"
        "/gen — создать сводку из собранных постов\n"
        "/status — статус текущей сессии\n"
        "/prompt — посмотреть системный промпт\n"
        "/export — экспортировать последнюю сводку в файл\n"
        "/clear — очистить сессию\n"
        "/test — проверить подключение к AI\n"
        "/help — эта справка"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Справка (дублирует /start)."""
    await cmd_start(message)


@router.message(Command("new"))
async def cmd_new(message: Message):
    """Начать новую сессию — очистить собранные посты (счётчик сохраняется)."""
    s = get_session(message.from_user.id)
    s["posts"] = []
    s["summaries"] = []
    s["processing"] = False
    # Счётчик НЕ сбрасывается — номера сводок идут подряд
    next_num = s["summary_counter"] + 1
    await message.answer(
        f"🆕 <b>Новая сессия начата!</b>\n\n"
        f"Следующая сводка будет <b>#{next_num}</b>\n"
        "Пересылай посты из сохранённой папки.\n"
        "Когда закончишь — жми /gen",
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("clear"))
async def cmd_clear(message: Message):
    """Полная очистка сессии (включая счётчик)."""
    sessions.pop(message.from_user.id, None)
    await message.answer(
        "🗑 Сессия полностью очищена (включая счётчик сводок).\n"
        "Начни заново с /new",
    )


@router.message(Command("status"))
async def cmd_status(message: Message):
    """Статус текущей сессии."""
    s = get_session(message.from_user.id)
    posts = s["posts"]
    summaries = s["summaries"]

    if not posts:
        await message.answer(
            "📭 Сессия пуста. Пересылай посты или нажми /new",
            parse_mode=ParseMode.HTML,
        )
        return

    # Подсчёт по типам
    text_count = sum(1 for p in posts if p.get("media_type") == "text")
    media_count = sum(1 for p in posts if p.get("media_type") != "text")

    # Список каналов-источников
    sources = set()
    for p in posts:
        src = p.get("source", "неизвестно")
        sources.add(src)
    sources_text = ", ".join(sorted(sources)[:5])
    if len(sources) > 5:
        sources_text += f" и ещё {len(sources) - 5}"

    status_emoji = "⏳ Генерация..." if s["processing"] else "✅ Готово"

    text = (
        f"📊 <b>Статус сессии</b>\n\n"
        f"📝 Постов собрано: <b>{len(posts)}</b>\n"
        f"  • Текстовых: {text_count}\n"
        f"  • С медиа: {media_count}\n"
        f"📌 Источники: {sources_text}\n"
        f"🔄 Статус: {status_emoji}\n"
        f"📚 Сводок создано: {len(summaries)}\n"
        f"🔢 Следующая сводка: <b>#{s['summary_counter'] + 1}</b>"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)


@router.message(Command("prompt"))
async def cmd_prompt(message: Message):
    """Показать текущий системный промпт."""
    prompt = load_prompt()
    preview = prompt[:2000] + ("..." if len(prompt) > 2000 else "")
    text = (
        f"📝 <b>Системный промпт</b> ({len(prompt)} символов):\n\n"
        f"<code>{preview}</code>"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)


@router.message(Command("test"))
async def cmd_test(message: Message):
    """Проверить подключение к AI."""
    msg = await message.answer("🔍 Проверяю подключение к AI...")
    ok = await ai.test_connection()
    if ok:
        await msg.edit_text(
            f"✅ <b>Подключение работает!</b>\n"
            f"Модель: <code>{Config.MODEL}</code>\n"
            f"Base URL: <code>{Config.API_BASE_URL}</code>",
            parse_mode=ParseMode.HTML,
        )
    else:
        await msg.edit_text(
            "❌ <b>Не удалось подключиться к AI</b>\n\n"
            "Проверь:\n"
            "• API_BASE_URL — правильный адрес?\n"
            "• API_KEY — валидный ключ?\n"
            "• Сеть — есть ли доступ к провайдеру?",
            parse_mode=ParseMode.HTML,
        )


@router.message(Command("gen"))
async def cmd_gen(message: Message):
    """
    ГЛАВНАЯ КОМАНДА: создать сводку из собранных постов.
    Берёт все посты из текущей сессии → отправляет в ИИ → возвращает сводку.
    """
    s = get_session(message.from_user.id)

    if not s["posts"]:
        await message.answer(
            "📭 <b>Нет постов для анализа.</b>\n\n"
            "Сначала пересылай посты из сохранённой папки.",
            parse_mode=ParseMode.HTML,
        )
        return

    if s["processing"]:
        await message.answer("⏳ Уже идёт генерация. Подожди завершения.")
        return

    s["processing"] = True
    post_count = len(s["posts"])

    # ── Автоинкремент номера сводки ──
    s["summary_counter"] += 1
    summary_number = s["summary_counter"]

    # ── Сообщение о прогрессе ──
    progress_msg = await message.answer(
        f"⏳ <b>Анализирую {post_count} постов...</b>\n"
        f"Номер сводки: #{summary_number}\n"
        "Это может занять 30–120 секунд в зависимости от модели.",
        parse_mode=ParseMode.HTML,
    )

    try:
        # ── Формируем входные данные для AI ──
        posts_text = _format_posts_for_ai(s["posts"])

        system_prompt = load_prompt()
        user_message = (
            f"Номер сводки: {summary_number}\n\n"
            f"Проанализируй {post_count} постов из Telegram-каналов "
            f"и создай структурированную сводку.\n\n"
            f"=== ПОСТЫ ДЛЯ АНАЛИЗА ===\n{posts_text}\n"
            f"=== КОНЕЦ ПОСТОВ ===\n\n"
            f"Создай сводку строго по правилам из системного промпта.\n"
            f"Используй номер сводки #{summary_number} в заголовке и итогах."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        # ── Запрос к AI ──
        result = await ai.generate(messages)

        if not result or not result.strip():
            raise Exception("AI вернул пустой ответ")

        # ── Сохраняем результат ──
        s["summaries"].append(result)

        # ── Отправляем сводку ──
        # Telegram лимит — 4096 символов, разбиваем если нужно
        await _send_long_message(message, result, parse_mode=ParseMode.HTML)

        # ── Уведомление о следующих шагах ──
        next_num = s["summary_counter"] + 1
        await message.answer(
            f"✅ <b>Сводка #{summary_number} готова!</b> "
            f"({len(result)} символов)\n\n"
            f"📋 Команды:\n"
            f"/gen — создать ещё одну (будет #{next_num})\n"
            f"/export — сохранить в файл\n"
            f"/new — начать новую сессию\n"
            f"/clear — очистить всё (включая счётчик)",
            parse_mode=ParseMode.HTML,
        )

    except Exception as e:
        logger.error(f"Ошибка генерации: {e}", exc_info=True)
        await message.answer(
            f"❌ <b>Ошибка при генерации:</b>\n\n<code>{str(e)[:500]}</code>",
            parse_mode=ParseMode.HTML,
        )

    finally:
        s["processing"] = False
        try:
            await progress_msg.delete()
        except Exception:
            pass


@router.message(Command("export"))
async def cmd_export(message: Message):
    """Экспорт последней сводки в текстовый файл."""
    s = get_session(message.from_user.id)

    if not s["summaries"]:
        await message.answer(
            "📭 Нет сводок для экспорта.\nСначала создай сводку через /gen"
        )
        return

    last_summary = s["summaries"][-1]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"summary_{timestamp}.md"

    # Сохраняем во временный файл
    with open(filename, "w", encoding="utf-8") as f:
        f.write(last_summary)

    await message.answer_document(
        FSInputFile(filename),
        caption=f"📄 Сводка ({len(last_summary)} символов)",
    )

    # Удаляем временный файл
    os.remove(filename)


# ═══════════════════════════════════════════════════════════════
#  ОБРАБОТКА ПЕРЕСЛАННЫХ ПОСТОВ
# ═══════════════════════════════════════════════════════════════


@router.message(F.forward_origin)
async def handle_forwarded(message: Message):
    """Ловит пересланные посты и добавляет в сессию."""
    s = get_session(message.from_user.id)

    # Лимиты
    if len(s["posts"]) >= Config.MAX_POSTS:
        await message.answer(
            f"⚠️ Достигнут лимит ({Config.MAX_POSTS} постов).\n"
            "Жми /gen для создания сводки или /new для новой сессии."
        )
        return

    total_chars = sum(len(p.get("text", "")) for p in s["posts"])
    if total_chars >= Config.MAX_CHARS:
        await message.answer(
            f"⚠️ Достигнут лимит символов ({Config.MAX_CHARS:,}).\n"
            "Жми /gen для создания сводки."
        )
        return

    # Извлекаем данные из сообщения
    post_data = _extract_post(message)
    s["posts"].append(post_data)

    count = len(s["posts"])
    await message.answer(
        f"✅ Пост #{count} принят!\n"
        f"📝 Текст: {len(post_data.get('text', ''))} символов\n"
        f"📌 Источник: {post_data.get('source', '—')}",
        parse_mode=ParseMode.HTML,
    )


@router.message(F.text | F.caption)
async def handle_text(message: Message):
    """
    Ловит текстовые сообщения (не пересланные).
    Если в сообщении есть текст — добавляем как пост.
    """
    text = message.text or message.caption or ""
    if not text.strip():
        return

    # Игнорируем команды
    if text.startswith("/"):
        return

    s = get_session(message.from_user.id)

    if len(s["posts"]) >= Config.MAX_POSTS:
        await message.answer(f"⚠️ Лимит {Config.MAX_POSTS} постов.")
        return

    post_data = {
        "text": text,
        "source": "вставлено вручную",
        "date": message.date.isoformat() if message.date else "",
        "media_type": "text",
    }
    s["posts"].append(post_data)

    count = len(s["posts"])
    await message.answer(
        f"✅ Текст #{count} принят! ({len(text)} символов)",
    )


# ═══════════════════════════════════════════════════════════════
#  ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ═══════════════════════════════════════════════════════════════


def _extract_post(message: Message) -> dict:
    """
    Извлекает данные поста из пересланного сообщения.
    Универсально работает с разными типами контента.
    """
    # ── Источник (из forward_origin) ──
    source = "неизвестный канал"
    origin = message.forward_origin
    if origin:
        # aiogram 3.x: forward_origin может быть разных типов
        if hasattr(origin, "sender_chat_name"):
            source = origin.sender_chat_name or source
        elif hasattr(origin, "chat_name"):
            source = origin.chat_name or source
        elif hasattr(origin, "sender_user_full_name"):
            source = origin.sender_user_full_name or source

        # Fallback: channel_post / forwarded_from
        if source == "неизвестный канал":
            if hasattr(message, "forward_from_chat") and message.forward_from_chat:
                source = message.forward_from_chat.title or source

    # ── Текст поста ──
    text = message.text or message.caption or ""

    # ── Тип медиа ──
    media_type = "text"
    if message.photo:
        media_type = "photo"
    elif message.video:
        media_type = "video"
    elif message.document:
        media_type = "document"
    elif message.voice or message.audio:
        media_type = "audio"
    elif message.sticker:
        media_type = "sticker"
    elif message.animation:
        media_type = "gif"

    # ── Дата ──
    date_str = ""
    if message.forward_date:
        date_str = message.forward_date.isoformat()
    elif message.date:
        date_str = message.date.isoformat()

    return {
        "text": text,
        "source": source,
        "date": date_str,
        "media_type": media_type,
    }


def _format_posts_for_ai(posts: list[dict]) -> str:
    """
    Форматирует список постов в текстовый блок для AI.
    Каждый пост пронумерован, с метаданными.
    """
    parts = []
    for i, post in enumerate(posts, 1):
        meta = []
        if post.get("source"):
            meta.append(f"Канал: {post['source']}")
        if post.get("date"):
            meta.append(f"Дата: {post['date']}")
        if post.get("media_type") and post["media_type"] != "text":
            meta.append(f"Медиа: {post['media_type']}")

        meta_str = " | ".join(meta) if meta else "без метаданных"
        text = post.get("text", "(без текста)")

        parts.append(
            f"═══ ПОСТ #{i} ═══ [{meta_str}]\n{text}\n"
        )

    return "\n".join(parts)


async def _send_long_message(message: Message, text: str, parse_mode=None):
    """
    Отправляет длинное сообщение, разбивая на части по 4096 символов.
    Умно разбивает по границам абзацев.
    """
    MAX_LEN = 4096

    if len(text) <= MAX_LEN:
        await message.answer(text, parse_mode=parse_mode)
        return

    # Разбиваем по строкам, собирая блоки
    chunks = []
    current = ""

    for line in text.split("\n"):
        # Если добавление строки не превысит лимит
        if len(current) + len(line) + 1 <= MAX_LEN:
            current += line + "\n"
        else:
            if current.strip():
                chunks.append(current.rstrip())
            current = line + "\n"

    if current.strip():
        chunks.append(current.rstrip())

    # Отправляем каждую часть
    for i, chunk in enumerate(chunks):
        if i > 0:
            await asyncio.sleep(0.5)  # Задержка чтобы Telegram не блокировал
        await message.answer(chunk, parse_mode=parse_mode)


# ═══════════════════════════════════════════════════════════════
#  ЗАПУСК
# ═══════════════════════════════════════════════════════════════


async def main():
    """Точка входа: проверка конфигурации и запуск polling."""
    Config.print_config()

    # Проверка конфигурации
    errors = Config.validate()
    if errors:
        logger.error("Ошибки конфигурации:")
        for e in errors:
            logger.error(f"  ✗ {e}")
        logger.error(
            "\nСоздай файл .env или задай переменные окружения.\n"
            "Смотри README.md для инструкций."
        )
        return

    # Проверка подключения к AI
    logger.info("Проверяю подключение к AI-провайдеру...")
    if await ai.test_connection():
        logger.info("✅ AI-провайдер доступен")
    else:
        logger.warning("⚠️ Не удалось проверить AI-провайдер, но бот запускается")

    # Загрузка промпта
    load_prompt()

    # Запуск бота
    logger.info("🤖 Бот запущен! Ожидаю сообщения...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
