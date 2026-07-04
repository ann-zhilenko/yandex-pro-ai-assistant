"""Обёртка над Yandex AI Studio API: LLM-генерация и эмбеддинги.

Документация API: https://aistudio.yandex.ru/docs/ru/
Используется async httpx — без лишних синхронных зависимостей.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from config import settings

logger = logging.getLogger(__name__)

# ── Эндпоинты Yandex AI Studio ────────────────────────────────

_LLM_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
_EMBEDDING_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/textEmbedding"

# ── Системный промпт ───────────────────────────────────────────

SYSTEM_PROMPT = """Ты — помощник водителей Яндекс Про (такси и курьеры). \
Твоя задача — отвечать на вопросы водителей на основе предоставленных статей базы знаний.

ПРАВИЛА:
1. Отвечай кратко и по делу — не более 3-4 предложений.
2. Опирайся ТОЛЬКО на предоставленный контекст. Не придумывай факты.
3. Если в контексте нет ответа на вопрос — честно скажи: \
«Я не нашёл точного ответа в базе знаний. Обратитесь в поддержку: @yandex_pro_support»
4. В конце ответа укажи ссылку на источник, если она есть в контексте.
5. Пиши простым языком, без канцелярита.
6. Если вопрос на казахском — отвечай на казахском, иначе на русском.
"""


def _model_uri(model: str) -> str:
    """Формирует modelUri для Yandex AI Studio."""
    return f"gpt://{settings.yandex_folder_id}/{model}"


def _emb_uri(model: str) -> str:
    """Формирует modelUri для эмбеддингов."""
    return f"emb://{settings.yandex_folder_id}/{model}"


def _headers() -> dict[str, str]:
    """HTTP-заголовки с авторизацией."""
    headers = {"Authorization": f"Bearer {settings.yandex_api_key}"}
    if settings.yandex_folder_id:
        headers["x-folder-id"] = settings.yandex_folder_id
    return headers


# ── LLM-генерация ──────────────────────────────────────────────

async def generate_answer(
    question: str,
    context: str,
    client: httpx.AsyncClient | None = None,
) -> str:
    """Генерирует ответ через Yandex GPT на основе контекста.

    Args:
        question: вопрос водителя.
        context: найденные фрагменты базы знаний (concatenated).
        client: опционально переиспользуемый httpx-клиент.

    Returns:
        Текст ответа от LLM.
    """
    own_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=30.0)

    user_content = f"КОНТЕКСТ ИЗ БАЗЫ ЗНАНИЙ:\n{context}\n\nВОПРОС ВОДИТЕЛЯ:\n{question}"

    payload = {
        "modelUri": _model_uri(settings.llm_model),
        "completionOptions": {
            "stream": False,
            "temperature": settings.llm_temperature,
            "maxTokens": str(settings.llm_max_tokens),
        },
        "messages": [
            {"role": "system", "text": SYSTEM_PROMPT},
            {"role": "user", "text": user_content},
        ],
    }

    try:
        response = await client.post(_LLM_URL, json=payload, headers=_headers())
        response.raise_for_status()
        data = response.json()
        # Структура ответа может быть с обёрткой "result" или без
        result = data.get("result", data)
        return result["alternatives"][0]["message"]["text"]
    except httpx.HTTPStatusError as exc:
        logger.error("LLM API error %s: %s", exc.response.status_code, exc.response.text)
        return "⚠️ Не удалось получить ответ. Попробуйте позже."
    except (KeyError, IndexError) as exc:
        logger.error("LLM response parse error: %s", exc)
        return "⚠️ Не удалось обработать ответ. Попробуйте позже."
    finally:
        if own_client:
            await client.aclose()


# ── Эмбеддинги ─────────────────────────────────────────────────

async def get_embedding(
    text: str,
    model: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> list[float]:
    """Получает векторное представление текста через Yandex embeddings API.

    Args:
        text: текст для векторизации.
        model: модель эмбеддингов (по умолчанию — text-search-query).
        client: опционально переиспользуемый httpx-клиент.

    Returns:
        Список float — вектор эмбеддинга.
    """
    if model is None:
        model = settings.embedding_model_query

    own_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=30.0)

    payload = {
        "modelUri": _emb_uri(model),
        "text": text,
    }

    try:
        # Retry с экспоненциальной задержкой для 429 Too Many Requests
        max_retries = 4
        for attempt in range(max_retries):
            response = await client.post(_EMBEDDING_URL, json=payload, headers=_headers())
            if response.status_code == 429 and attempt < max_retries - 1:
                wait = 0.5 * (2 ** attempt)  # 0.5s, 1s, 2s, 4s
                logger.warning("Rate limit (429), retry %d/%d через %.1fs", attempt + 1, max_retries, wait)
                await asyncio.sleep(wait)
                continue
            response.raise_for_status()
            break

        data = response.json()
        # Структура ответа зависит от эндпоинта:
        #   /embedding    → {"result": {"embedding": [...]}}
        #   /textEmbedding → {"embedding": [...]}
        if "result" in data:
            return data["result"]["embedding"]
        if "embedding" in data:
            return data["embedding"]
        logger.error("Unexpected embedding response: %s", list(data.keys()))
        raise RuntimeError(f"Неизвестная структура ответа API: {list(data.keys())}")
    except httpx.HTTPStatusError as exc:
        logger.error("Embedding API error %s: %s", exc.response.status_code, exc.response.text)
        raise
    finally:
        if own_client:
            await client.aclose()


async def get_embeddings_batch(
    texts: list[str],
    model: str,
    client: httpx.AsyncClient | None = None,
) -> list[list[float]]:
    """Получает эмбеддинги для списка текстов.

    Yandex API не поддерживает батчинг, поэтому запрашиваем по одному
    с ограничением конкуренции, чтобы не упереться в rate limit.
    """
    own_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=30.0)

    sem = asyncio.Semaphore(3)  # Yandex API: лимит 10 запросов/сек

    async def _one(idx: int, text: str) -> list[float]:
        async with sem:
            # Небольшая задержка между запросами для соблюдения rate limit
            await asyncio.sleep(idx * 0.1)
            return await get_embedding(text, model, client)

    try:
        results = await asyncio.gather(*[_one(i, t) for i, t in enumerate(texts)])
        return results
    finally:
        if own_client:
            await client.aclose()
