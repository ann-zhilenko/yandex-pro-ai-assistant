# ── Этап 1: установка зависимостей ─────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Кэширование слоя зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Этап 2: runtime-образ ──────────────────────────────────────
FROM python:3.12-slim

LABEL maintainer="Yandex Pro Navigator Bot"
LABEL description="RAG-бот-навигатор по базе знаний для водителей Яндекс Про"

WORKDIR /app

# Копируем установленные пакеты из builder-этапа
COPY --from=builder /install /usr/local

# Копируем исходный код
COPY bot/ ./bot/
COPY rag/ ./rag/
COPY db/ ./db/
COPY config.py ./

# База знаний — ВНЕ тома, чтобы не перекрывалась при пересборке образа
COPY data/knowledge_base.json ./knowledge_base.json

# Директория для персистентных данных (создаётся томом)
RUN mkdir -p /app/data

# Entrypoint-скрипт: индексация (при необходимости) + запуск бота
COPY entrypoint.sh ./
RUN chmod +x entrypoint.sh

# Том для персистентных данных (векторное хранилище + SQLite)
VOLUME ["/app/data"]

# Переменные окружения по умолчанию (переопределяются в docker-compose / .env)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FORCE_REINDEX=false

ENTRYPOINT ["./entrypoint.sh"]
