"""Эвристический классификатор запроса по ключевым словам.

Бесплатная альтернатива LLM-классификации: определяет категорию
запроса, тип водителя, язык и регион — без API-вызова.
"""

from __future__ import annotations

from dataclasses import dataclass

# ── Словари ключевых слов ──────────────────────────────────────

_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "payments": [
        "выплат", "комисси", "деньги", "заработок", "баланс", "снять",
        "перевод", "карт", "спис", "удерж", "бонус", "доплат", "гаранти",
        "налог", "самозанят", "чек", "выруч",
    ],
    "documents": [
        "документ", "паспорт", "лицензи", "договор", "акт", "подпис",
        "эдо", "закрывающ", "свидетельств", "удостоверен", "медицинск",
        "справк", "регистрац",
    ],
    "app": [
        "приложение", "висит", "ошибка", "не работает", "глючит",
        "навигатор", "карт", "gps", "геолокац", "зависл", "вылет",
        "обновлен", "сброс", "настройк",
    ],
    "rules": [
        "рейтинг", "отмен", "штраф", "правил", "блокировк", "оцен",
        "пассажир", "клиент", "опозда", "вежлив", "чистот", "компенсаци",
    ],
    "onboarding": [
        "начать", "старт", "регистрац", "как работать", "как зарабатывать",
        "первый заказ", "новичок", "обучен", "скачать", "установ",
        "партнёр", "аренд",
    ],
}

_DRIVER_TYPE_KEYWORDS: dict[str, list[str]] = {
    "taxi": ["такси", "водитель", "машина", "пассажир", "тариф", "заказ", "поездка", "подача"],
    "courier": ["курьер", "доставка", "посылка", "ресторан", "магазин", "пакет", "груз"],
}

# ── Регионы: словарь ключевых слов по странам ──────────────────
# Добавление нового региона = просто добавить запись сюда.
# Статьи с region=None (универсальные) показываются для всех регионов.

_REGION_KEYWORDS: dict[str, list[str]] = {
    "kz": [
        "казахстан", "алматы", "астана", "тенге", "мрп", "каспий",
        "иин", "эдо", "ндс", "закрывающ",
    ],
    "by": [
        "беларус", "минск", "белорус", "бнс", "рб",
    ],
    "uz": [
        "узбекистан", "ташкент", "сум", "сўм", "узб",
    ],
}


@dataclass
class QueryFeatures:
    """Результат классификации запроса."""

    category: str | None      # payments / documents / app / rules / onboarding
    driver_type: str | None   # taxi / courier
    language: str             # ru / kz / by / uz ...
    region: str | None        # kz / by / uz / None (универсальный)


def _match(text: str, keywords: list[str]) -> bool:
    """Возвращает True, если хоть одно ключевое слово найдено в тексте."""
    text_lower = text.lower()
    return any(kw in text_lower for kw in keywords)


def _detect_region(text: str) -> str | None:
    """Определяет регион запроса по ключевым словам.

    Возвращает код региона ('kz', 'by', 'uz') или None,
    если запрос не привязан к конкретному региону.
    """
    text_lower = text.lower()
    for region_code, keywords in _REGION_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return region_code
    return None


def classify(text: str) -> QueryFeatures:
    """Определяет категорию, тип водителя и регион запроса.

    Использует простейший поиск ключевых слов — без LLM, бесплатно.
    Если несколько категорий совпадают — берём ту, где больше совпадений.
    """
    # Категория — по максимальному числу совпадений
    best_category: str | None = None
    best_score = 0
    for category, keywords in _CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text.lower())
        if score > best_score:
            best_score = score
            best_category = category

    # Тип водителя — первое совпадение
    driver_type: str | None = None
    for dtype, keywords in _DRIVER_TYPE_KEYWORDS.items():
        if _match(text, keywords):
            driver_type = dtype
            break

    # Регион
    region = _detect_region(text)

    return QueryFeatures(
        category=best_category,
        driver_type=driver_type,
        language=region or "ru",
        region=region,
    )
