"""Ретривер: векторный поиск по базе знаний.

Загружает предрассчитанные эмбеддинги из .npz и метаданные из JSON,
считает cosine similarity между запросом и чанками, возвращает top-K.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import httpx
import numpy as np

from config import settings
from rag.llm import get_embedding

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Результат поиска одного чанка."""

    chunk_id: str
    title: str
    category: str
    region: str | None    # регион статьи (kz, by, ...) или None (универсальная)
    url_path: str
    valid_regions: list[str]
    text: str
    score: float          # cosine similarity (0..1)


class Retriever:
    """Векторный поиск по базе знаний.

    Загружает эмбеддинги один раз при инициализации, затем работает в памяти.
    """

    def __init__(self) -> None:
        self._embeddings: np.ndarray | None = None
        self._metadata: list[dict] | None = None
        self._loaded = False

    def load(self) -> None:
        """Загружает матрицу эмбеддингов и метаданные с диска."""
        if not settings.vector_store_path.exists():
            raise FileNotFoundError(
                f"Векторное хранилище не найдено: {settings.vector_store_path}.\n"
                "Запустите индексацию: python -m rag.indexer"
            )

        data = np.load(settings.vector_store_path)
        self._embeddings = data["embeddings"].astype(np.float32)

        with open(settings.metadata_path, encoding="utf-8") as f:
            self._metadata = json.load(f)

        # Нормализуем строки матрицы для cosine similarity
        norms = np.linalg.norm(self._embeddings, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self._embeddings = self._embeddings / norms

        self._loaded = True
        logger.info(
            "Retriever загружен: %d чанков, размерность %d",
            self._embeddings.shape[0],
            self._embeddings.shape[1],
        )

    async def search(
        self,
        query: str,
        category: str | None = None,
        driver_type: str | None = None,
        region: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> list[SearchResult]:
        """Ищет top-K релевантных чанков по запросу.

        Args:
            query: текст запроса.
            category: фильтр по категории (если определена классификатором).
            driver_type: фильтр по типу водителя.
            region: код региона запроса ('kz', 'by', ...) или None.
                Статьи с другим регионом исключаются; статьи без региона
                (универсальные) показываются всегда.
            client: переиспользуемый httpx-клиент.

        Returns:
            Список результатов, отсортированных по убыванию релевантности.
        """
        if not self._loaded:
            self.load()

        assert self._embeddings is not None
        assert self._metadata is not None

        # Вектор запроса
        query_vec = await get_embedding(query, client=client)
        query_vec = np.array(query_vec, dtype=np.float32)
        query_vec = query_vec / (np.linalg.norm(query_vec) + 1e-8)

        # Cosine similarity (матрица уже нормализована)
        scores = self._embeddings @ query_vec

        # Мягкий буст по категории и типу водителя (не исключаем, а повышаем скор)
        # Жёсткий фильтр приводил к false negatives при ошибке классификатора
        score_boost = np.ones(len(self._metadata), dtype=np.float32)
        for i, meta in enumerate(self._metadata):
            if category and meta["category"] == category:
                score_boost[i] *= 1.15  # +15% за совпадение категории
            if driver_type and meta["driver_types"] and driver_type in meta["driver_types"]:
                score_boost[i] *= 1.10  # +10% за совпадение типа водителя
            # Региональная фильтрация:
            # - region=None → без фильтра (все регионы, включая kz, by...)
            # - region="ru" → универсальные + RU
            # - region="kz" → универсальные + KZ
            if region is not None:
                query_region = None if region == "ru" else region
                article_region = meta.get("region")
                if article_region is not None and article_region != query_region:
                    score_boost[i] = 0.0

        # Применяем буст
        scores = scores * score_boost

        # Top-K
        top_indices = np.argsort(scores)[::-1][:settings.top_k]

        results: list[SearchResult] = []
        for idx in top_indices:
            score = float(scores[idx])
            if score < settings.relevance_threshold:
                continue
            meta = self._metadata[idx]
            results.append(
                SearchResult(
                    chunk_id=meta["chunk_id"],
                    title=meta["title"],
                    category=meta["category"],
                    region=meta.get("region"),
                    url_path=meta.get("url_path", ""),
                    valid_regions=meta.get("valid_regions", []),
                    text=meta["text"],
                    score=score,
                )
            )

        # Если ничего не найдено — fallback с пониженным порогом
        if not results:
            logger.info(
                "Fallback: повторный поиск с порогом %.2f (было %.2f)",
                settings.relevance_threshold * 0.7,
                settings.relevance_threshold,
            )
            fallback_threshold = settings.relevance_threshold * 0.7
            for idx in top_indices:
                score = float(scores[idx])
                if score < fallback_threshold:
                    continue
                meta = self._metadata[idx]
                results.append(
                    SearchResult(
                        chunk_id=meta["chunk_id"],
                        title=meta["title"],
                        category=meta["category"],
                        region=meta.get("region"),
                        url_path=meta.get("url_path", ""),
                        valid_regions=meta.get("valid_regions", []),
                        text=meta["text"],
                        score=score,
                    )
                )

        return results
