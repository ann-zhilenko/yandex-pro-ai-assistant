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
import time

import httpx
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.types import CallbackQuery, Message

from bot import formatter
from bot.keyboards import (
    category_keyboard,
    faq_keyboard,
    feedback_keyboard,
    get_faq_question,
    menu_button,
)
from db.analytics import log_feedback, log_query
from rag.classifier import classify
from rag.llm import generate_answer
from rag.retriever import Retriever

logger = logging.getLogger(__name__)

# Ретривер — загружается один раз при старте
_retriever: Retriever | None = None


async def _safe_send(
    message: Message,
    text: str,
    reply_markup=None,
    parse_mode: str = "Markdown",
) -> None:
    """Отправляет сообщение с fallback на plain text при ошибке Markdown.

    LLM может вернуть текст с незакрытыми _ * [ — Telegram выбросит
    TelegramBadRequest. В этом случае отправляем без форматирования.
    """
    try:
        await message.answer(
            text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=True,
        )
    except TelegramBadRequest:
        logger.warning("Markdown не парсится, отправляю plain text")
        await message.answer(
            text,
            reply_markup=reply_markup,
            parse_mode=None,
            disable_web_page_preview=True,
        )


async def _send_typing(message: Message) -> None:
    """Отправляет статус 'печатает...' в чат. Не критично — игнорируем ошибки."""
    try:
        await message.bot.send_chat_action(
            chat_id=message.chat.id,
            action="typing",
        )
    except Exception:
        pass


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
    logger.info("Команда /start от user_id=%d, username=%s", message.from_user.id, message.from_user.username)
    try:
        await message.answer(
            formatter.format_welcome(),
            reply_markup=category_keyboard(),
            parse_mode="Markdown",
        )
    except TelegramNetworkError as exc:
        logger.error("Не удалось отправить приветствие: %s", exc)


# ── Выбор категории ────────────────────────────────────────────

async def handle_category(callback: CallbackQuery) -> None:
    """Показывает частые вопросы по выбранной категории."""
    category = callback.data.split(":", 1)[1]
    logger.info("Категория '%s' от user_id=%d", category, callback.from_user.id)
    await callback.message.edit_text(
        formatter.format_category_menu(category),
        reply_markup=faq_keyboard(category),
        parse_mode="Markdown",
    )
    await callback.answer()


# ── Назад в меню ───────────────────────────────────────────────

async def handle_back_to_menu(callback: CallbackQuery) -> None:
    """Возврат в главное меню."""
    logger.info("Возврат в меню от user_id=%d", callback.from_user.id)
    await callback.message.edit_text(
        formatter.format_welcome(),
        reply_markup=category_keyboard(),
        parse_mode="Markdown",
    )
    await callback.answer()


# ── Частый вопрос (из кнопки) ──────────────────────────────────

async def handle_faq_question(callback: CallbackQuery) -> None:
    """Обрабатывает выбор частого вопроса из меню категории.

    callback_data формат: faq:{category}:{idx}
    """
    parts = callback.data.split(":")
    category = parts[1]
    idx = int(parts[2])
    question = get_faq_question(category, idx)

    if question is None:
        logger.warning("FAQ-вопрос не найден: cat=%s idx=%d", category, idx)
        await callback.answer("Вопрос не найден")
        return

    logger.info("FAQ-вопрос '%s' от user_id=%d", question, callback.from_user.id)
    await callback.message.edit_text(f"🔍 Ищу ответ на: _{question}_", parse_mode="Markdown")
    await process_question(callback.message, callback.from_user.id, callback.from_user.username, question)
    await callback.answer()


# ── Свободный текстовый запрос ─────────────────────────────────

async def handle_text_message(message: Message) -> None:
    """Главный обработчик: текст водителя → RAG-пайплайн → ответ."""
    if not message.text:
        return

    logger.info(
        "Текст от user_id=%d (%s): \"%s\"",
        message.from_user.id,
        message.from_user.username or "без username",
        message.text[:80],
    )
    await _send_typing(message)
    await process_question(message, message.from_user.id, message.from_user.username, message.text)


# ── Обратная связь ─────────────────────────────────────────────

async def handle_feedback(callback: CallbackQuery) -> None:
    """Обрабатывает нажатие 👍 / 👎."""
    parts = callback.data.split(":")
    query_id = int(parts[1])
    feedback = int(parts[2])
    log_feedback(query_id, feedback)
    logger.info("Обратная связь: query #%d → %s", query_id, "👍" if feedback > 0 else "👎")

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
    t_start = time.monotonic()

    # 1. Классификация — бесплатно
    features = classify(question)
    t_class = time.monotonic()
    logger.info(
        "[user=%d] Шаг 1/4 — классификация: category=%s, driver_type=%s, kz=%s (%.2fs)",
        user_id, features.category, features.driver_type, features.is_kz_context,
        t_class - t_start,
    )

    retriever = get_retriever()

    # 2. Векторный поиск + 3. LLM-генерация — в одной HTTP-сессии
    async with httpx.AsyncClient(timeout=60.0) as client:
        t_search_start = time.monotonic()
        results = await retriever.search(
            query=question,
            category=features.category,
            driver_type=features.driver_type,
            client=client,
        )
        t_search = time.monotonic()
        logger.info(
            "[user=%d] Шаг 2/4 — векторный поиск: найдено %d чанков (%.2fs)",
            user_id, len(results), t_search - t_search_start,
        )
        if results:
            for r in results:
                logger.info(
                    "  → [%.3f] %s", r.score, r.title,
                )

        if not results:
            # Ответ не найден
            answer = formatter.format_no_answer()
            query_id = log_query(
                user_id, username, question,
                features.category, features.driver_type,
                [], answer,
            )
            logger.warning(
                "[user=%d] Ответ не найден в базе знаний. Запрос залогирован #%d",
                user_id, query_id,
            )
            try:
                await _safe_send(message, answer, reply_markup=menu_button())
            except TelegramNetworkError as exc:
                logger.error("[user=%d] Не удалось отправить ответ: %s", user_id, exc)
            return

        # 3. Контекст для LLM из найденных чанков
        context = "\n\n---\n\n".join(
            f"[{r.title}] URL: {r.url}\n{r.text}"
            for r in results
        )

        # 4. LLM-генерация (1 API-вызов)
        t_llm_start = time.monotonic()
        await _send_typing(message)
        answer_text = await generate_answer(question, context, client=client)
        t_llm = time.monotonic()
        logger.info(
            "[user=%d] Шаг 3/4 — LLM генерация (%.2fs): %s",
            user_id, t_llm - t_llm_start, answer_text[:100].replace("\n", " "),
        )

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
    t_send_start = time.monotonic()
    try:
        await _safe_send(message, formatted, reply_markup=feedback_keyboard(query_id))
        t_end = time.monotonic()
        logger.info(
            "[user=%d] Шаг 4/4 — ответ отправлен (%.2fs). Итого: %.2fs",
            user_id, t_end - t_send_start, t_end - t_start,
        )
    except TelegramNetworkError as exc:
        logger.error("[user=%d] Не удалось отправить ответ: %s", user_id, exc)
