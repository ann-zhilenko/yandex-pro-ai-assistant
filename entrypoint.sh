#!/bin/sh
set -e

echo "━━━ Яндекс Про Навигатор — запуск ━━━"

# Проверка обязательных переменных
if [ -z "$BOT_TOKEN" ]; then
    echo "❌ ОШИБКА: BOT_TOKEN не задан. Укажите его в .env или переменных окружения."
    exit 1
fi
if [ -z "$YANDEX_API_KEY" ]; then
    echo "❌ ОШИБКА: YANDEX_API_KEY не задан. Укажите его в .env или переменных окружения."
    exit 1
fi

echo "✅ Переменные окружения проверены"

# Индексация базы знаний, если векторное хранилище отсутствует
VECTOR_FILE="data/vector_store/vector_store.npz"

if [ ! -f "$VECTOR_FILE" ] || [ "$FORCE_REINDEX" = "true" ]; then
    echo "📦 Векторное хранилище не найдено (или FORCE_REINDEX=true). Индексация..."
    python -m rag.indexer
    echo "✅ Индексация завершена"
else
    echo "✅ Векторное хранилище найдено, индексация пропускается"
fi

# Запуск бота
echo "🚀 Запуск бота..."
exec python -m bot.main
