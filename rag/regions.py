"""Маппинг регионов: код → базовый URL базы знаний Яндекс Про.

Каждый регион имеет свой домен и формат URL. Полный URL статьи =
base_url + url_path (например, /income-diff/comission).

Добавление нового региона:
  1. Добавить запись в REGION_BASE_URLS
  2. Добавить ключевые слова в rag/classifier.py → _REGION_KEYWORDS
  3. Добавить кнопку в bot/keyboards.py → REGION_LABELS
"""

from __future__ import annotations

# Базовые URL базы знаний Яндекс Про по регионам
# Формат: pro.yandex.{domain}/{locale}-{country}/{city}/knowledge-base/taxi
REGION_BASE_URLS: dict[str, str] = {
    "ru": "https://pro.yandex.ru/ru-ru/moskva/knowledge-base/taxi",
    "kz": "https://pro.yandex.com/kz-ru/almaty/knowledge-base/taxi",
    "by": "https://pro.yandex.com/by-ru/minsk/knowledge-base/taxi",
    "uz": "https://pro.yandex.com/uz-ru/tashkent/knowledge-base/taxi",
}

# Главные страницы (fallback, если конкретная статья не найдена)
REGION_HOME_URLS: dict[str, str] = {
    "ru": "https://pro.yandex.ru/ru-ru/moskva/knowledge-base",
    "kz": "https://pro.yandex.com/kz-ru/almaty/knowledge-base",
    "by": "https://pro.yandex.com/by-ru/minsk/knowledge-base",
    "uz": "https://pro.yandex.com/uz-ru/tashkent/knowledge-base",
}


def build_url(url_path: str | None, region: str | None) -> str:
    """Строит полный URL статьи на основе пути и региона.

    Args:
        url_path: относительный путь (например, /income-diff/comission).
                  Если None или пустой — возвращает главную страницу региона.
        region: код региона (ru, kz, by, uz). None трактуется как ru.

    Returns:
        Полный URL статьи.
    """
    region = region or "ru"
    base_url = REGION_BASE_URLS.get(region, REGION_BASE_URLS["ru"])

    if not url_path:
        return REGION_HOME_URLS.get(region, REGION_HOME_URLS["ru"])

    return f"{base_url}{url_path}"
