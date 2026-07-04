"""Форматирование ответов для Telegram: Markdown, ссылки, структура."""

from __future__ import annotations

from rag.retriever import SearchResult
from rag.regions import build_url

# Эмодзи-префиксы для категорий
CATEGORY_EMOJI: dict[str, str] = {
    "payments": "💳",
    "documents": "📋",
    "app": "📱",
    "rules": "⚖️",
    "onboarding": "🚀",
}


def format_answer(answer: str, sources: list[SearchResult], region: str | None = None) -> str:
    """Форматирует ответ LLM + добавляет ссылки на источники.

    Args:
        answer: текст ответа от LLM.
        sources: найденные чанки (для ссылок).
        region: регион пользователя для построения URL.

    Returns:
        Готовый к отправке текст в Telegram Markdown.
    """
    lines = [answer.strip()]

    # Уникальные ссылки на статьи-источники
    seen_urls: set[str] = set()
    source_links: list[str] = []
    for src in sources:
        # Если url_path не работает для региона пользователя — fallback на главную
        user_region = region or "ru"
        if src.url_path and src.valid_regions and user_region not in src.valid_regions:
            full_url = build_url(None, user_region)
        else:
            full_url = build_url(src.url_path, user_region)
        if full_url not in seen_urls:
            seen_urls.add(full_url)
            emoji = CATEGORY_EMOJI.get(src.category, "📄")
            source_links.append(f"{emoji} [{src.title}]({full_url})")

    if source_links:
        lines.append("\n📚 _Подробнее:_")
        lines.extend(f"   • {link}" for link in source_links)

    return "\n".join(lines)


def format_no_answer() -> str:
    """Сообщение, когда ответ не найден в базе знаний."""
    return (
        "К сожалению, я не нашёл точного ответа в базе знаний. 😔\n\n"
        "Обратитесь в поддержку:\n"
        "📩 @yandex_pro_support\n"
        "📞 8 800 333-96-39\n\n"
        "Или попробуйте переформулировать вопрос."
    )


def format_region_prompt() -> str:
    """Промпт выбора региона при старте сессии."""
    return (
        "👋 *Добро пожаловать в Яндекс Про Навигатор!*\n\n"
        "Я — бот-помощник для водителей Яндекс Про. "
        "Отвечаю на вопросы о выплатах, документах, правилах и приложении.\n\n"
        "Сначала выберите ваш регион работы —\n"
        "это поможет давать точные ответы для вашей страны:"
    )


def format_welcome(region: str | None = None) -> str:
    """Приветственное сообщение с указанием региона."""
    from bot.keyboards import REGION_LABELS
    region_label = REGION_LABELS.get(region or "ru", "Россия")
    return (
        f"🌍 *Регион: {region_label}*\n\n"
        "Задайте вопрос своими словами или выберите категорию ниже.\n\n"
        "✍️ _Например: «какая комиссия с заказа», «когда придут деньги», "
        "«приложение зависло»_\n\n"
        "Выберите раздел 👇"
    )


def format_category_menu(category: str) -> str:
    """Заголовок для меню частых вопросов по категории."""
    emoji = CATEGORY_EMOJI.get(category, "📄")
    labels = {
        "payments": "Выплаты и комиссия",
        "documents": "Документы",
        "app": "Приложение",
        "rules": "Правила и рейтинг",
        "onboarding": "Как начать",
    }
    label = labels.get(category, category)
    return f"{emoji} *{label}*\n\nЧастые вопросы в этом разделе:"
