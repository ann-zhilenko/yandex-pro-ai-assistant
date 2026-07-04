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
    url: str
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
        client: httpx.AsyncClient | None = None,
    ) -> list[SearchResult]:
        """Ищет top-K релевантных чанков по запросу.

        Args:
            query: текст запроса.
            category: фильтр по категории (если определена классификатором).
            driver_type: фильтр по типу водителя.
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

        # Фильтрация по категории и типу водителя
        mask = np.ones(len(self._metadata), dtype=bool)
        for i, meta in enumerate(self._metadata):
            if category and meta["category"] != category:
                mask[i] = False
            if driver_type and meta["driver_types"] and driver_type not in meta["driver_types"]:
                # Не отфильтровываем чанки без указания типа — они универсальные
                if meta["driver_types"]:
                    mask[i] = False

        # Применяем фильтр
        scores = np.where(mask, scores, -1.0)

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
                    url=meta["url"],
                    text=meta["text"],
                    score=score,
                )
            )

        return results
