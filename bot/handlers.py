"""Хендлеры Telegram-бота: приём сообщений, маршрутизация, RAG-пайплайн.

Поток обработки одного запроса:
  1. Классификация (бесплатно, по ключевым словам)
  2. Векторный поиск по базе знаний
  3. LLM-генерация ответа (1 API-вызов)
  4. Форматирование + отправка
  5. Логирование в SQLite
"""

from __future__ import annotations

import logging

import httpx
from aiogram.types import CallbackQuery, Message

from bot import formatter
from bot.keyboards import (
    category_keyboard,
    faq_keyboard,
    feedback_keyboard,
    menu_button,
)
from db.analytics import log_feedback, log_query
from rag.classifier import classify
from rag.llm import generate_answer
from rag.retriever import Retriever

logger = logging.getLogger(__name__)

# Ретривер — загружается один раз при старте
_retriever: Retriever | None = None


def get_retriever() -> Retriever:
    """Возвращает singleton-ретривер."""
    global _retriever
    if _retriever is None:
        _retriever = Retriever()
        _retriever.load()
    return _retriever


# ── /start ─────────────────────────────────────────────────────

async def cmd_start(message: Message) -> None:
    """Приветствие + меню категорий."""
    await message.answer(
        formatter.format_welcome(),
        reply_markup=category_keyboard(),
        parse_mode="Markdown",
    )


# ── Выбор категории ────────────────────────────────────────────

async def handle_category(callback: CallbackQuery) -> None:
    """Показывает частые вопросы по выбранной категории."""
    category = callback.data.split(":", 1)[1]
    await callback.message.edit_text(
        formatter.format_category_menu(category),
        reply_markup=faq_keyboard(category),
        parse_mode="Markdown",
    )
    await callback.answer()


# ── Назад в меню ───────────────────────────────────────────────

async def handle_back_to_menu(callback: CallbackQuery) -> None:
    """Возврат в главное меню."""
    await callback.message.edit_text(
        formatter.format_welcome(),
        reply_markup=category_keyboard(),
        parse_mode="Markdown",
    )
    await callback.answer()


# ── Частый вопрос (из кнопки) ──────────────────────────────────

async def handle_faq_question(callback: CallbackQuery) -> None:
    """Обрабатывает выбор частого вопроса из меню категории."""
    question = callback.data.split(":", 1)[1]
    await callback.message.edit_text(f"🔍 Ищу ответ на: _{question}_", parse_mode="Markdown")
    await process_question(callback.message, callback.from_user.id, callback.from_user.username, question)
    await callback.answer()


# ── Свободный текстовый запрос ─────────────────────────────────

async def handle_text_message(message: Message) -> None:
    """Главный обработчик: текст водителя → RAG-пайплайн → ответ."""
    if not message.text:
        return

    await message.chat.do_action("typing")
    await process_question(message, message.from_user.id, message.from_user.username, message.text)


# ── Обратная связь ─────────────────────────────────────────────

async def handle_feedback(callback: CallbackQuery) -> None:
    """Обрабатывает нажатие 👍 / 👎."""
    parts = callback.data.split(":")
    query_id = int(parts[1])
    feedback = int(parts[2])
    log_feedback(query_id, feedback)

    if feedback > 0:
        await callback.answer("Спасибо за отзыв! 🙏")
    else:
        await callback.answer("Жаль, что не помогло. Мы работаем над улучшением.")
    await callback.message.edit_reply_markup(reply_markup=None)


# ── Ядро RAG-пайплайна ─────────────────────────────────────────

async def process_question(
        message: Message,
        user_id: int,
        username: str | None,
        question: str,
) -> None:
    """Полный RAG-пайплайн: классификация → поиск → LLM → ответ.

    Ровно один LLM-вызов на запрос (для минимальной стоимости API).
    """
    # 1. Классификация — бесплатно
    features = classify(question)
    logger.info(
        "Запрос от %s: category=%s, driver_type=%s, kz=%s",
        user_id, features.category, features.driver_type, features.is_kz_context,
    )

    retriever = get_retriever()

    # 2. Векторный поиск
    async with httpx.AsyncClient(timeout=30.0) as client:
        results = await retriever.search(
            query=question,
            category=features.category,
            driver_type=features.driver_type,
            client=client,
        )

        if not results:
            # Ответ не найден
            answer = formatter.format_no_answer()
            query_id = log_query(
                user_id, username, question,
                features.category, features.driver_type,
                [], answer,
            )
            await message.answer(
                answer,
                reply_markup=menu_button(),
                parse_mode="Markdown",
            )
            return

        # 3. Контекст для LLM из найденных чанков
        context = "\n\n---\n\n".join(
            f"[{r.title}] URL: {r.url}\n{r.text}"
            for r in results
        )

        # 4. LLM-генерация (1 API-вызов)
        answer_text = await generate_answer(question, context, client=client)

    # 5. Форматирование
    formatted = formatter.format_answer(answer_text, results)

    # 6. Логирование
    found_articles = [
        {"chunk_id": r.chunk_id, "title": r.title, "url": r.url, "score": r.score}
        for r in results
    ]
    query_id = log_query(
        user_id, username, question,
        features.category, features.driver_type,
        found_articles, answer_text,
    )

    # 7. Отправка
    await message.answer(
        formatted,
        reply_markup=feedback_keyboard(query_id),
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )
