"""Точка входа: запуск Telegram-бота на aiogram.

Запуск:
    python -m bot.main
"""

from __future__ import annotations

import asyncio
import logging

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.exceptions import TelegramNetworkError

from bot.handlers import (
    cmd_start,
    handle_back_to_menu,
    handle_category,
    handle_change_region,
    handle_faq_question,
    handle_feedback,
    handle_region,
    handle_text_message,
)
from config import settings
from db.analytics import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def register_handlers(dp: Dispatcher) -> None:
    """Регистрирует все хендлеры в диспетчере."""
    dp.message.register(cmd_start, Command("start"))

    dp.callback_query.register(handle_region, F.data.startswith("region:"))
    dp.callback_query.register(handle_change_region, F.data == "change_region")
    dp.callback_query.register(handle_category, F.data.startswith("cat:"))
    dp.callback_query.register(handle_back_to_menu, F.data == "back_to_menu")
    dp.callback_query.register(handle_faq_question, F.data.startswith("faq:"))
    dp.callback_query.register(handle_feedback, F.data.startswith("fb:"))

    # Свободный текст — в конце, как fallback
    dp.message.register(handle_text_message, F.text)


async def _check_connectivity(bot: Bot) -> bool:
    """Проверяет доступность Telegram API перед запуском polling.

    Делает несколько попыток с задержкой — помогает на серверах
    с нестабильной связью (например, в РФ, где Telegram может быть недоступен).
    """
    for attempt in range(1, settings.telegram_retry_attempts + 1):
        try:
            me = await bot.get_me()
            logger.info(
                "✅ Telegram API доступен. Бот: @%s (%s)",
                me.username, me.first_name,
            )
            return True
        except (TelegramNetworkError, aiohttp.ClientError, asyncio.TimeoutError) as exc:
            wait = 5 * attempt
            logger.warning(
                "⚠️ Попытка %d/%d — нет связи с Telegram API: %s. Жду %ds...",
                attempt, settings.telegram_retry_attempts, exc, wait,
            )
            await asyncio.sleep(wait)

    logger.error(
        "❌ Не удалось подключиться к Telegram API за %d попыток. "
        "Возможные причины: блокировка api.telegram.org на сервере, "
        "отсутствие интернета, неверный BOT_TOKEN.",
        settings.telegram_retry_attempts,
    )
    return False


def _make_session() -> AiohttpSession:
    """Создаёт aiohttp-сессию с увеличенным таймаутом.

    aiogram ожидает timeout как число (секунды), не ClientTimeout.
    """
    return AiohttpSession(
        timeout=settings.telegram_read_timeout,
    )


async def main() -> None:
    """Инициализация и запуск бота."""
    if not settings.bot_token:
        logger.error("BOT_TOKEN не задан! Укажите его в .env")
        return

    # Инициализация БД
    init_db()
    logger.info("БД аналитики готова")

    # Создание бота с кастомной сессией (увеличенные таймауты)
    session = _make_session()
    bot = Bot(
        token=settings.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )
    dp = Dispatcher()
    register_handlers(dp)

    logger.info("Бот запускается... Модель LLM: %s", settings.llm_model)
    logger.info(
        "Таймауты: connect=%ds, read=%ds",
        settings.telegram_connect_timeout,
        settings.telegram_read_timeout,
    )

    # Проверка связи с Telegram API
    if not await _check_connectivity(bot):
        await session.close()
        return

    # Удаляем webhook (на случай, если был установлен) — с retry
    for attempt in range(3):
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            logger.info("Webhook удалён, pending updates сброшены")
            break
        except TelegramNetworkError as exc:
            logger.warning("Не удалось удалить webhook (попытка %d): %s", attempt + 1, exc)
            await asyncio.sleep(5)

    # Polling с retry-циклом при сетевых ошибках
    logger.info("🚀 Polling запущен")
    while True:
        try:
            await dp.start_polling(
                bot,
                handle_as_tasks=True,  # параллельная обработка запросов
            )
        except (TelegramNetworkError, asyncio.TimeoutError, aiohttp.ClientError) as exc:
            logger.error("Сетевая ошибка во время polling: %s. Перезапуск через 10s...", exc)
            await asyncio.sleep(10)
        except Exception as exc:
            logger.error("Непредвиденная ошибка во время polling: %s. Перезапуск через 10s...", exc)
            await asyncio.sleep(10)
        else:
            # start_polling завершился без ошибки — выходим из цикла
            break
        finally:
            # Сессию не закрываем при retry — она нужна для следующей итерации
            pass

    await session.close()
    logger.info("Сессия закрыта")


if __name__ == "__main__":
    asyncio.run(main())
