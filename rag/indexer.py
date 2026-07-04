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
    url: str
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
                    url=article["url"],
                    text=text,
                )
            )
    return chunks


async def index_knowledge_base() -> None:
    """Полная индексация базы знаний: загрузка → чанки → эмбеддинги → сохранение."""
    logger.info("Загрузка базы знаний из %s", settings.kb_file)
    articles = _load_knowledge_base()
    logger.info("Загружено статей: %d", len(articles))

    chunks = _build_chunks(articles)
    logger.info("Создано чанков: %d", len(chunks))

    logger.info("Получение эмбеддингов (модель: %s)...", settings.embedding_model_doc)
    texts = [c.text for c in chunks]

    async with httpx.AsyncClient(timeout=60.0) as client:
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
            "url": c.url,
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
