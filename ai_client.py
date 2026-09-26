"""
Модуль для работы с OpenAI-совместимым API.
Поддерживает любой провайдер: OpenAI, Anthropic (через прокси),
OpenRouter, Together, Groq, LM Studio, Ollama и др.
"""

import json
import logging
from typing import AsyncIterator

import aiohttp

from config import Config

logger = logging.getLogger(__name__)


class AIClient:
    """Асинхронный клиент для OpenAI-совместимого /chat/completions API."""

    def __init__(self):
        self.base_url = Config.API_BASE_URL.rstrip("/")
        self.api_key = Config.API_KEY
        self.model = Config.MODEL
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def generate(self, messages: list[dict]) -> str:
        """
        Отправляет запрос в AI-провайдер и возвращает текст ответа.

        Args:
            messages: Список сообщений в формате OpenAI
                      [{"role": "system", "content": "..."},
                       {"role": "user", "content": "..."}]

        Returns:
            Текст ответа от модели
        """
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": Config.MAX_TOKENS,
            "temperature": Config.TEMPERATURE,
        }

        logger.info(f"→ Запрос к AI: {self.model} ({len(messages)} сообщений)")

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    url,
                    headers=self.headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=300),  # 5 минут на ответ
                ) as resp:
                    if resp.status != 200:
                        raise RuntimeError(f"AI API вернул HTTP {resp.status}; проверь настройки провайдера и его логи")

                    data = await resp.json()
                    content = data["choices"][0]["message"]["content"]
                    tokens_used = data.get("usage", {})
                    logger.info(
                        f"← Ответ получен: {len(content)} символов, "
                        f"tokens: {tokens_used}"
                    )
                    return content

            except aiohttp.ClientError as e:
                raise Exception(f"Ошибка подключения к API: {e}")

    async def generate_stream(self, messages: list[dict]) -> AsyncIterator[str]:
        """
        Стриминговый ответ от AI-провайдера (для длинных ответов).
        Генерирует чанки текста по мере генерации.
        """
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": Config.MAX_TOKENS,
            "temperature": Config.TEMPERATURE,
            "stream": True,
        }

        logger.info(f"→ Стриминговый запрос к AI: {self.model}")

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    url,
                    headers=self.headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=300),
                ) as resp:
                    if resp.status != 200:
                        raise RuntimeError(f"AI API вернул HTTP {resp.status}; проверь настройки провайдера и его логи")

                    async for line in resp.content:
                        line = line.decode("utf-8").strip()
                        if not line or not line.startswith("data: "):
                            continue
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            delta = data["choices"][0].get("delta", {})
                            if "content" in delta:
                                yield delta["content"]
                        except json.JSONDecodeError:
                            continue

            except aiohttp.ClientError as e:
                raise Exception(f"Ошибка подключения к API: {e}")

    async def test_connection(self) -> bool:
        """Проверяет доступность API-провайдера."""
        try:
            url = f"{self.base_url}/models"
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=self.headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        models = [m.get("id", "?") for m in data.get("data", [])]
                        logger.info(f"Доступные модели: {models[:10]}")
                        return True
                    else:
                        logger.warning("Проверка /models вернула HTTP %s", resp.status)
                        return False
        except Exception as e:
            logger.error(f"Ошибка подключения к API: {e}")
            return False
