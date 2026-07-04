"""Точка входа: запуск Telegram-бота на aiogram.

Запуск:
    python -m bot.main
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command

from bot.handlers import (
    cmd_start,
    handle_back_to_menu,
    handle_category,
    handle_faq_question,
    handle_feedback,
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

    dp.callback_query.register(handle_category, F.data.startswith("cat:"))
    dp.callback_query.register(handle_back_to_menu, F.data == "back_to_menu")
    dp.callback_query.register(handle_faq_question, F.data.startswith("faq:"))
    dp.callback_query.register(handle_feedback, F.data.startswith("fb:"))

    # Свободный текст — в конце, как fallback
    dp.message.register(handle_text_message, F.text)


async def main() -> None:
    """Инициализация и запуск бота."""
    if not settings.bot_token:
        logger.error("BOT_TOKEN не задан! Укажите его в .env")
        return

    # Инициализация БД
    init_db()
    logger.info("БД аналитики готова")

    # Создание бота
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )
    dp = Dispatcher()
    register_handlers(dp)

    logger.info("Бот запускается... Модель LLM: %s", settings.llm_model)

    # Удаляем webhook (на случай, если был установлен)
    await bot.delete_webhook(drop_pending_updates=True)

    # Polling
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
