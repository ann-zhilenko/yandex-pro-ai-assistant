"""Inline-клавиатуры для Telegram-бота: меню категорий и обратная связь.

callback_data ограничен 64 байтами (UTF-8), поэтому для FAQ-кнопок
используем короткие индексы: faq:{category}:{idx} вместо полного текста.

FAQ-пункты — кортежи (short_label, search_query):
  - short_label: короткий текст на кнопке (Telegram обрезает длинные)
  - search_query: полный запрос для RAG-поиска
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

# ── Регионы ────────────────────────────────────────────────────

REGION_LABELS: dict[str, str] = {
    "ru": "🇷🇺 Россия",
    "kz": "🇰🇿 Казахстан",
    "by": "🇧🇾 Беларусь",
    "uz": "🇺🇿 Узбекистан",
    "am": "🇦🇲 Армения",
    "md": "🇲🇩 Молдова",
    "ge": "🇬🇪 Грузия",
    "lt": "🇱🇹 Литва",
    "rs": "🇷🇸 Сербия",
    "kg": "🇰🇬 Кыргызстан",
    "tj": "🇹🇯 Таджикистан",
    "tr": "🇹🇷 Турция",
}

# ── Частые вопросы по категории ────────────────────────────────
# (короткая подпись на кнопке, поисковый запрос для RAG)

FAQ_QUESTIONS: dict[str, list[tuple[str, str]]] = {
    "payments": [
        ("Комиссия", "какая комиссия сервиса"),
        ("Выплаты", "когда приходят выплаты"),
        ("Бонусы", "какие бывают бонусы"),
    ],
    "documents": [
        ("Самозанятость", "стать самозанятым"),
        ("Лицензия", "разрешение деятельность такси"),
        ("Документы", "документы для самозанятого"),
    ],
    "app": [
        ("Приложение", "приложение не работает"),
        ("Навигатор", "как работает навигатор"),
    ],
    "rules": [
        ("Рейтинг", "повысить рейтинг"),
        ("Отмена заказа", "отменить заказ"),
    ],
    "onboarding": [
        ("Начать работать", "как зарегистрироваться в приложении"),
    ],
}


def category_keyboard(current_region: str | None = None) -> InlineKeyboardMarkup:
    """Главное меню с кнопками-категориями + смена региона."""
    builder = InlineKeyboardBuilder()
    for cat_id, label in CATEGORY_LABELS.items():
        builder.button(text=label, callback_data=f"cat:{cat_id}")
    # Кнопка смены региона в нижнем ряду
    region_label = REGION_LABELS.get(current_region or "ru", "🌍 Регион")
    builder.button(text=f"{region_label} (сменить)", callback_data="change_region")
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()


def region_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора региона при старте сессии."""
    builder = InlineKeyboardBuilder()
    for region_code, label in REGION_LABELS.items():
        builder.button(text=label, callback_data=f"region:{region_code}")
    builder.adjust(3, 3, 3, 3)
    return builder.as_markup()


def faq_keyboard(category: str) -> InlineKeyboardMarkup:
    """Кнопки с частыми вопросами по выбранной категории.

    На кнопке — короткая подпись, в callback_data — индекс.
    """
    builder = InlineKeyboardBuilder()
    for idx, (label, _query) in enumerate(FAQ_QUESTIONS.get(category, [])):
        builder.button(text=label, callback_data=f"faq:{category}:{idx}")
    builder.button(text="⬅️ Назад", callback_data="back_to_menu")
    builder.adjust(1)
    return builder.as_markup()


def get_faq_question(category: str, idx: int) -> str | None:
    """Возвращает поисковый запрос FAQ-вопроса по категории и индексу."""
    questions = FAQ_QUESTIONS.get(category, [])
    if 0 <= idx < len(questions):
        return questions[idx][1]  # search_query, не label
    return None


# ── Обратная связь ─────────────────────────────────────────────

def feedback_keyboard(query_id: int) -> InlineKeyboardMarkup:
    """Кнопки оценки ответа + возврат в меню."""
    builder = InlineKeyboardBuilder()
    builder.button(text="👍 Помогло", callback_data=f"fb:{query_id}:1")
    builder.button(text="👎 Не помогло", callback_data=f"fb:{query_id}:-1")
    builder.button(text="📋 В меню", callback_data="back_to_menu")
    builder.adjust(2, 1)
    return builder.as_markup()


# ── Кнопка-меню ────────────────────────────────────────────────

def menu_button() -> InlineKeyboardMarkup:
    """Кнопка возврата в главное меню."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 В меню", callback_data="back_to_menu")
    return builder.as_markup()
