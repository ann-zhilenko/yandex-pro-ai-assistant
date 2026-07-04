"""Маппинг регионов: код → базовый URL базы знаний Яндекс Про.

Каждый регион имеет свой домен и формат URL. Полный URL статьи =
base_url + url_path (например, /income-diff/comission).

Для регионов без собственной базы знаний используется fallback на РФ.
"""

from __future__ import annotations

# Базовые URL базы знаний Яндекс Про по регионам
# Формат: pro.yandex.{domain}/{locale}-{country}/{city}/knowledge-base/taxi
# None = нет собственной базы, fallback на РФ
REGION_BASE_URLS: dict[str, str | None] = {
    "ru": "https://pro.yandex.ru/ru-ru/moskva/knowledge-base/taxi",
    "kz": "https://pro.yandex.com/kz-ru/almaty/knowledge-base/taxi",
    "by": "https://pro.yandex.com/by-ru/minsk/knowledge-base/taxi",
    "uz": "https://pro.yandex.com/uz-ru/tashkent/knowledge-base/taxi",
    "am": "https://pro.yandex.com/am-ru/erevan/knowledge-base/taxi",
    "md": "https://pro.yandex.com/md-ru/chisinau/knowledge-base/taxi",
    # Регионы без собственной базы знаний — fallback на РФ
    "ge": None,  # Грузия
    "lt": None,  # Литва
    "rs": None,  # Сербия
    "kg": None,  # Кыргызстан
    "tj": None,  # Таджикистан
    "tr": None,  # Турция
}

# Главные страницы (fallback, если конкретная статья не найдена)
REGION_HOME_URLS: dict[str, str] = {
    "ru": "https://pro.yandex.ru/ru-ru/moskva/knowledge-base",
    "kz": "https://pro.yandex.com/kz-ru/almaty/knowledge-base",
    "by": "https://pro.yandex.com/by-ru/minsk/knowledge-base",
    "uz": "https://pro.yandex.com/uz-ru/tashkent/knowledge-base",
    "am": "https://pro.yandex.com/am-ru/erevan/knowledge-base",
    "md": "https://pro.yandex.com/md-ru/chisinau/knowledge-base",
    # Fallback на РФ для регионов без базы
    "ge": "https://pro.yandex.ru/ru-ru/moskva/knowledge-base",
    "lt": "https://pro.yandex.ru/ru-ru/moskva/knowledge-base",
    "rs": "https://pro.yandex.ru/ru-ru/moskva/knowledge-base",
    "kg": "https://pro.yandex.ru/ru-ru/moskva/knowledge-base",
    "tj": "https://pro.yandex.ru/ru-ru/moskva/knowledge-base",
    "tr": "https://pro.yandex.ru/ru-ru/moskva/knowledge-base",
}

# Регионы, у которых есть собственная база знаний
REGIONS_WITH_KB: set[str] = {r for r, url in REGION_BASE_URLS.items() if url is not None}


def has_own_kb(region: str | None) -> bool:
    """Возвращает True, если у региона есть собственная база знаний."""
    return (region or "ru") in REGIONS_WITH_KB


def build_url(url_path: str | None, region: str | None) -> str:
    """Строит полный URL статьи на основе пути и региона.

    Args:
        url_path: относительный путь (например, /income-diff/comission).
                  Если None или пустой — возвращает главную страницу региона.
        region: код региона (ru, kz, by, ...). None трактуется как ru.
                Если у региона нет собственной базы — fallback на РФ.

    Returns:
        Полный URL статьи.
    """
    region = region or "ru"

    # Если у региона нет собственной базы — используем РФ
    base_url = REGION_BASE_URLS.get(region)
    if base_url is None:
        base_url = REGION_BASE_URLS["ru"]
        region = "ru"

    if not url_path:
        return REGION_HOME_URLS.get(region, REGION_HOME_URLS["ru"])

    return f"{base_url}{url_path}"
