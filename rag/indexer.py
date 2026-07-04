"""Индексатор базы знаний: статьи → чанки → эмбеддинги → векторное хранилище.

Хранилище — .npz (numpy) + metadata.json. Никаких внешних БД.
Запуск: python -m rag.indexer
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass

import httpx
import numpy as np

from config import settings
from rag.llm import get_embeddings_batch

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    """Смысловой фрагмент статьи базы знаний."""

    chunk_id: str
    article_id: str
    title: str
    category: str
    driver_types: list[str]
    region: str | None
    url_path: str
    valid_regions: list[str]
    text: str


def _split_into_chunks(text: str, article_id: str) -> list[str]:
    """Разбивает текст на чанки по абзацам с перекрытием.

    Группируем абзацы так, чтобы каждый чанк был ~chunk_size символов,
    с перекрытием chunk_overlap для сохранения контекста на границах.
    """
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    if not paragraphs:
        return []

    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        # Если абзац сам по себе длиннее chunk_size — режем по предложениям
        if len(para) > settings.chunk_size:
            sentences = para.replace(". ", ".\n").split("\n")
            for sent in sentences:
                if len(current) + len(sent) + 1 <= settings.chunk_size:
                    current = f"{current} {sent}".strip()
                else:
                    if current:
                        chunks.append(current)
                    current = sent
            continue

        if len(current) + len(para) + 1 <= settings.chunk_size:
            current = f"{current}\n{para}".strip()
        else:
            chunks.append(current)
            # Перекрытие: начинаем новый чанк с последнего абзаца
            current = para

    if current:
        chunks.append(current)

    return chunks


def _load_knowledge_base() -> list[dict]:
    """Загружает статьи из JSON-файла."""
    with open(settings.kb_file, encoding="utf-8") as f:
        return json.load(f)


def _build_chunks(articles: list[dict]) -> list[Chunk]:
    """Создаёт чанки из всех статей."""
    chunks: list[Chunk] = []
    for article in articles:
        text_parts = _split_into_chunks(article["content"], article["id"])
        for i, text in enumerate(text_parts):
            chunks.append(
                Chunk(
                    chunk_id=f"{article['id']}_chunk_{i}",
                    article_id=article["id"],
                    title=article["title"],
                    category=article["category"],
                    driver_types=article.get("driver_type", []),
                    region=article.get("region"),
                    url_path=article.get("url_path", ""),
                    valid_regions=article.get("valid_regions", []),
                    text=text,
                )
            )
    return chunks


async def _validate_url(url: str, client: httpx.AsyncClient) -> bool:
    """Проверяет, что URL возвращает HTTP 200 (не 404).

    Используется при индексации, чтобы отсеять битые ссылки
    до того, как они попадут к пользователю.
    """
    try:
        resp = await client.head(url, follow_redirects=True, timeout=10.0)
        # Некоторые серверы не поддерживают HEAD — пробуем GET
        if resp.status_code == 405:
            resp = await client.get(url, follow_redirects=True, timeout=10.0)
        return resp.status_code == 200
    except Exception:
        return False


async def _validate_article_urls(articles: list[dict], client: httpx.AsyncClient) -> None:
    """Валидирует URL-пути всех статей для всех регионов.

    Для каждой статьи проверяет url_path против каждого региона.
    Если url_path не работает ни для одного региона — обнуляет его.
    Логирует детальную сводку: какие url_path работают для каких регионов.
    """
    from rag.regions import build_url, REGION_BASE_URLS, REGIONS_WITH_KB

    # Проверяем только регионы с собственной базой знаний
    all_regions = sorted(REGIONS_WITH_KB)
    broken_count = 0

    for article in articles:
        url_path = article.get("url_path", "")
        if not url_path:
            article["valid_regions"] = all_regions
            continue

        # Проверяем url_path для всех регионов
        valid_regions: list[str] = []
        invalid_regions: list[str] = []
        for region_code in all_regions:
            full_url = build_url(url_path, region_code)
            is_valid = await _validate_url(full_url, client)
            if is_valid:
                valid_regions.append(region_code)
            else:
                invalid_regions.append(region_code)

        article["valid_regions"] = valid_regions

        if invalid_regions:
            logger.warning(
                "url_path %s НЕ работает для регионов: %s (статья: %s)",
                url_path, ", ".join(invalid_regions), article["title"],
            )

        if not valid_regions:
            broken_count += 1
            logger.warning(
                "url_path %s битый для ВСЕХ регионов → fallback (статья: %s)",
                url_path, article["title"],
            )
            article["url_path"] = ""
            article["valid_regions"] = all_regions

    if broken_count:
        logger.warning("Статей с полностью битыми ссылками: %d", broken_count)
    else:
        logger.info("Все URL-пути валидны хотя бы для одного региона ✅")


async def index_knowledge_base() -> None:
    """Полная индексация базы знаний: загрузка → валидация URL → чанки → эмбеддинги → сохранение."""
    logger.info("Загрузка базы знаний из %s", settings.kb_file)
    articles = _load_knowledge_base()
    logger.info("Загружено статей: %d", len(articles))

    async with httpx.AsyncClient(timeout=60.0) as client:
        # Валидация URL до индексации
        logger.info("Валидация URL статей...")
        await _validate_article_urls(articles, client)

        chunks = _build_chunks(articles)
        logger.info("Создано чанков: %d", len(chunks))

        logger.info("Получение эмбеддингов (модель: %s)...", settings.embedding_model_doc)
        texts = [c.text for c in chunks]
        embeddings = await get_embeddings_batch(texts, settings.embedding_model_doc, client)

    # Сохраняем матрицу эмбеддингов
    matrix = np.array(embeddings, dtype=np.float32)
    settings.vector_store_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(settings.vector_store_path, embeddings=matrix)
    logger.info("Векторы сохранены: %s (shape: %s)", settings.vector_store_path, matrix.shape)

    # Сохраняем метаданные чанков
    metadata = [
        {
            "chunk_id": c.chunk_id,
            "article_id": c.article_id,
            "title": c.title,
            "category": c.category,
            "driver_types": c.driver_types,
            "region": c.region,
            "url_path": c.url_path,
            "valid_regions": c.valid_regions,
            "text": c.text,
        }
        for c in chunks
    ]
    with open(settings.metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    logger.info("Метаданные сохранены: %s", settings.metadata_path)

    logger.info("✅ Индексация завершена: %d чанков, %d статей", len(chunks), len(articles))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    asyncio.run(index_knowledge_base())
