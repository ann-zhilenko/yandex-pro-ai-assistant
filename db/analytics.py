"""SQLite-логирование запросов, ответов и обратной связи.

Даёт команде аналитику: популярные темы, пробелы в базе знаний,
удовлетворённость водителей ответами бота.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone

from config import settings

logger = logging.getLogger(__name__)


def _get_conn() -> sqlite3.Connection:
    """Создаёт подключение к БД (создаёт файл при первом запуске)."""
    settings.db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_file)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Создаёт таблицы, если их ещё нет."""
    conn = _get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS queries (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            username    TEXT,
            question    TEXT NOT NULL,
            category    TEXT,
            driver_type TEXT,
            found_articles TEXT,
            answer      TEXT,
            feedback    INTEGER,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_queries_user ON queries(user_id);
        CREATE INDEX IF NOT EXISTS idx_queries_created ON queries(created_at);
        CREATE INDEX IF NOT EXISTS idx_queries_category ON queries(category);
        """
    )
    conn.commit()
    conn.close()
    logger.info("SQLite БД инициализирована: %s", settings.db_file)


def log_query(
    user_id: int,
    username: str | None,
    question: str,
    category: str | None,
    driver_type: str | None,
    found_articles: list[dict],
    answer: str,
) -> int:
    """Сохраняет запрос и ответ в БД. Возвращает ID записи."""
    conn = _get_conn()
    cursor = conn.execute(
        """
        INSERT INTO queries (user_id, username, question, category, driver_type,
                             found_articles, answer, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            username,
            question,
            category,
            driver_type,
            json.dumps(found_articles, ensure_ascii=False),
            answer,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    query_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return query_id


def log_feedback(query_id: int, feedback: int) -> None:
    """Записывает обратную связь пользователя (1=плюс, -1=минус)."""
    conn = _get_conn()
    conn.execute(
        "UPDATE queries SET feedback = ? WHERE id = ?",
        (feedback, query_id),
    )
    conn.commit()
    conn.close()
    logger.info("Обратная связь: query #%d → %s", query_id, "👍" if feedback > 0 else "👎")


def get_unanswered_stats() -> list[dict]:
    """Возвращает статистику по неотвеченным запросам для аналитики команды."""
    conn = _get_conn()
    rows = conn.execute(
        """
        SELECT question, category, COUNT(*) as cnt
        FROM queries
        WHERE answer LIKE '%не нашёл%' OR answer LIKE '%Не удалось%'
        GROUP BY question
        ORDER BY cnt DESC
        LIMIT 20
        """
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
