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

# Путь к базе знаний (в Docker — knowledge_base.json, локально — data/knowledge_base.json)
KB_FILE="${KB_PATH:-data/knowledge_base.json}"
VECTOR_FILE="data/vector_store/vector_store.npz"
HASH_FILE="data/vector_store/.kb_hash"

# Вычисляем хеш базы знаний для автоматического обнаружения изменений
KB_HASH=$(md5sum "$KB_FILE" 2>/dev/null | awk '{print $1}')
STORED_HASH=$(cat "$HASH_FILE" 2>/dev/null || echo "none")

# Индексация нужна если:
# 1. Векторное хранилище отсутствует
# 2. FORCE_REINDEX=true
# 3. Хеш базы знаний изменился (новая версия в образе)
NEED_INDEX=false

if [ ! -f "$VECTOR_FILE" ]; then
    echo "📦 Векторное хранилище не найдено"
    NEED_INDEX=true
elif [ "$FORCE_REINDEX" = "true" ]; then
    echo "📦 FORCE_REINDEX=true"
    NEED_INDEX=true
elif [ "$KB_HASH" != "$STORED_HASH" ]; then
    echo "📦 База знаний изменилась (хеш: $STORED_HASH → $KB_HASH)"
    NEED_INDEX=true
else
    echo "✅ Векторное хранилище актуально, индексация пропускается"
fi

if [ "$NEED_INDEX" = "true" ]; then
    echo "🔄 Индексация базы знаний..."
    python -m rag.indexer
    # Сохраняем хеш после успешной индексации
    mkdir -p data/vector_store
    echo "$KB_HASH" > "$HASH_FILE"
    echo "✅ Индексация завершена"
fi

# Запуск бота
echo "🚀 Запуск бота..."
exec python -m bot.main
