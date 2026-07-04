"""Эвристический классификатор запроса по ключевым словам.

Бесплатная альтернатива LLM-классификации: определяет категорию
запроса, тип водителя, язык и регион — без API-вызова.

Регионы определяются в два уровня:
  1. _COUNTRY_NAMES — явные названия стран/городов («казахстан», «минск»).
     Могут перебивать регион сессии пользователя.
  2. _REGION_TERMS — региональные термины («эдо», «тенге», «мрп»).
     Только контекст, НЕ перебивают регион сессии.
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

# ── Уровень 1: явные названия стран и городов ──────────────────
# Только эти слова могут перебить регион сессии пользователя.

_COUNTRY_NAMES: dict[str, list[str]] = {
    "ru": [
        "россия", "москва", "питер", "спб", "петербург", "рф",
        "мск", "новосибирск", "екатеринбург", "казан", "самара",
    ],
    "kz": [
        "казахстан", "алматы", "астана",
    ],
    "by": [
        "беларус", "минск", "белорус",
    ],
    "uz": [
        "узбекистан", "ташкент", "узб",
    ],
    "am": [
        "армени", "ереван", "армян",
    ],
    "md": [
        "молдов", "кишинёв", "кишинев", "молдав",
    ],
    "ge": [
        "грузи", "тбилиси", "грузин",
    ],
    "lt": [
        "литва", "вильнюс", "литовск",
    ],
    "rs": [
        "серби", "белград", "сербск",
    ],
    "kg": [
        "кыргыз", "киргиз", "бишкек",
    ],
    "tj": [
        "таджикистан", "душанбе", "таджикск",
    ],
    "tr": [
        "турци", "стамбул", "турецк",
    ],
}

# ── Уровень 2: региональные термины ────────────────────────────
# Контекстные подсказки. НЕ перебивают регион сессии.
# Используются для clean_query (очистки запроса).

_REGION_TERMS: dict[str, list[str]] = {
    "ru": ["россий"],
    "kz": ["тенге", "мрп", "каспий", "иин", "эдо", "ндс", "закрывающ"],
    "by": ["бнс", "рб"],
    "uz": ["сум", "сўм"],
    "am": ["драм"],
    "md": [],
    "ge": ["лари"],
    "lt": ["евро"],
    "rs": ["динар"],
    "kg": ["сом"],
    "tj": ["сомони"],
    "tr": ["лира"],
}

# Объединённый словарь для обратной совместимости и clean_query
_REGION_KEYWORDS: dict[str, list[str]] = {
    region: _COUNTRY_NAMES.get(region, []) + _REGION_TERMS.get(region, [])
    for region in set(list(_COUNTRY_NAMES.keys()) + list(_REGION_TERMS.keys()))
}


@dataclass
class QueryFeatures:
    """Результат классификации запроса."""

    category: str | None        # payments / documents / app / rules / onboarding
    driver_type: str | None     # taxi / courier
    language: str               # ru / kz / by / uz ...
    region: str | None          # любой detected регион (страна ИЛИ термин)
    explicit_region: str | None  # только явное название страны — перебивает сессию
    clean_query: str            # запрос без региональных слов (для эмбеддинга)


def _match(text: str, keywords: list[str]) -> bool:
    """Возвращает True, если хоть одно ключевое слово найдено в тексте."""
    text_lower = text.lower()
    return any(kw in text_lower for kw in keywords)


def _detect_region(text: str) -> str | None:
    """Определяет регион запроса по любым ключевым словам (страны + термины).

    Возвращает код региона или None.
    """
    text_lower = text.lower()
    for region_code, keywords in _REGION_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return region_code
    return None


def _detect_explicit_region(text: str) -> str | None:
    """Определяет регион только по явным названиям стран/городов.

    В отличие от _detect_region, региональные термины («эдо», «тенге»)
    НЕ учитываются — только прямое упоминание страны или города.
    """
    text_lower = text.lower()
    for region_code, keywords in _COUNTRY_NAMES.items():
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

    # Регион (любой — страна или термин)
    region = _detect_region(text)

    # Явный регион (только названия стран/городов)
    explicit_region = _detect_explicit_region(text)

    # Очищаем запрос от всех региональных слов для лучшего семантического поиска.
    # Региональные слова уводят эмбеддинг от универсальных статей.
    clean_query = text
    detected_region = region or explicit_region
    if detected_region is not None:
        all_region_kw = _REGION_KEYWORDS.get(detected_region, [])
        clean_words = []
        for word in text.split():
            word_lower = word.lower().strip(".,!?;:")
            if not any(kw in word_lower for kw in all_region_kw):
                clean_words.append(word)
        clean_query = " ".join(clean_words) if clean_words else text

    return QueryFeatures(
        category=best_category,
        driver_type=driver_type,
        language=detected_region or "ru",
        region=region,
        explicit_region=explicit_region,
        clean_query=clean_query,
    )
