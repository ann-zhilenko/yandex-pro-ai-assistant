"""Форматирование ответов для Telegram: Markdown, ссылки, структура."""

from __future__ import annotations

from rag.retriever import SearchResult

# Эмодзи-префиксы для категорий
CATEGORY_EMOJI: dict[str, str] = {
    "payments": "💳",
    "documents": "📋",
    "app": "📱",
    "rules": "⚖️",
    "onboarding": "🚀",
}


def format_answer(answer: str, sources: list[SearchResult]) -> str:
    """Форматирует ответ LLM + добавляет ссылки на источники.

    Args:
        answer: текст ответа от LLM.
        sources: найденные чанки (для ссылок).

    Returns:
        Готовый к отправке текст в Telegram Markdown.
    """
    lines = [answer.strip()]

    # Уникальные ссылки на статьи-источники
    seen_urls: set[str] = set()
    source_links: list[str] = []
    for src in sources:
        if src.url not in seen_urls:
            seen_urls.add(src.url)
            emoji = CATEGORY_EMOJI.get(src.category, "📄")
            source_links.append(f"{emoji} [{src.title}]({src.url})")

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


def format_welcome() -> str:
    """Приветственное сообщение при /start."""
    return (
        "👋 *Добро пожаловать в Яндекс Про Навигатор!*\n\n"
        "Я — бот-помощник для водителей Яндекс Про. "
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
