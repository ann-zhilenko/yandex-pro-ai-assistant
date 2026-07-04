"""Inline-клавиатуры для Telegram-бота: меню категорий и обратная связь.

callback_data ограничен 64 байтами (UTF-8), поэтому для FAQ-кнопок
используем короткие индексы: faq:{category}:{idx} вместо полного текста.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ── Меню категорий ─────────────────────────────────────────────

CATEGORY_LABELS: dict[str, str] = {
    "payments": "💳 Выплаты и комиссия",
    "documents": "📋 Документы",
    "app": "📱 Приложение",
    "rules": "⚖️ Правила и рейтинг",
    "onboarding": "🚀 Как начать",
}

# ── Частые вопросы по категории ────────────────────────────────

FAQ_QUESTIONS: dict[str, list[str]] = {
    "payments": [
        "Какая комиссия Яндекса с заказа?",
        "Когда придут деньги за заказы?",
        "Как получить бонус за активность?",
    ],
    "documents": [
        "Как оформить самозанятость?",
        "Где получить лицензию таксиста?",
        "Как подписать документы через ЭДО?",
    ],
    "app": [
        "Приложение зависло, что делать?",
        "Не работает навигатор в приложении",
    ],
    "rules": [
        "Как повысить рейтинг?",
        "Что будет за отмену заказа?",
    ],
    "onboarding": [
        "Как начать работать в Яндекс Про?",
        "Какие документы нужны для старта?",
    ],
}


def category_keyboard() -> InlineKeyboardMarkup:
    """Главное меню с кнопками-категориями."""
    builder = InlineKeyboardBuilder()
    for cat_id, label in CATEGORY_LABELS.items():
        builder.button(text=label, callback_data=f"cat:{cat_id}")
    builder.adjust(2, 2, 1)
    return builder.as_markup()


def faq_keyboard(category: str) -> InlineKeyboardMarkup:
    """Кнопки с частыми вопросами по выбранной категории.

    callback_data формат: faq:{category}:{idx} — короткий, до 64 байт.
    """
    builder = InlineKeyboardBuilder()
    for idx, question in enumerate(FAQ_QUESTIONS.get(category, [])):
        builder.button(text=question, callback_data=f"faq:{category}:{idx}")
    builder.button(text="⬅️ Назад", callback_data="back_to_menu")
    builder.adjust(1)
    return builder.as_markup()


def get_faq_question(category: str, idx: int) -> str | None:
    """Возвращает текст FAQ-вопроса по категории и индексу."""
    questions = FAQ_QUESTIONS.get(category, [])
    if 0 <= idx < len(questions):
        return questions[idx]
    return None


# ── Обратная связь ─────────────────────────────────────────────

def feedback_keyboard(query_id: int) -> InlineKeyboardMarkup:
    """Кнопки оценки ответа + ссылка на источник."""
    builder = InlineKeyboardBuilder()
    builder.button(text="👍 Помогло", callback_data=f"fb:{query_id}:1")
    builder.button(text="👎 Не помогло", callback_data=f"fb:{query_id}:-1")
    builder.adjust(2)
    return builder.as_markup()


# ── Кнопка-меню ────────────────────────────────────────────────

def menu_button() -> InlineKeyboardMarkup:
    """Кнопка возврата в главное меню."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 В меню", callback_data="back_to_menu")
    return builder.as_markup()
