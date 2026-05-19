from __future__ import annotations

import sqlite3
import time
import uuid

from core.runtime import SERVER_DIR
from core.security import redact_text

TASKS_DB = SERVER_DIR / 'tasks.sqlite3'


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(TASKS_DB)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            status TEXT NOT NULL,
            agent TEXT,
            project TEXT,
            namespace TEXT,
            prompt TEXT NOT NULL,
            result TEXT,
            created TEXT NOT NULL,
            updated TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def _now() -> str:
    return time.strftime('%Y-%m-%dT%H:%M:%S%z')


def task_create(title: str, prompt: str, project: str = '', agent: str = '', namespace: str = 'general') -> str:
    task_id = str(uuid.uuid4())
    now = _now()
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO tasks (id, title, status, agent, project, namespace, prompt, result, created, updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (task_id, title, 'pending', agent, project, namespace, redact_text(prompt), '', now, now),
        )
    return task_id


def task_list(status: str = '') -> list[dict]:
    with _db() as conn:
        if status:
            rows = conn.execute('SELECT * FROM tasks WHERE status = ? ORDER BY updated DESC', (status,)).fetchall()
        else:
            rows = conn.execute('SELECT * FROM tasks ORDER BY updated DESC').fetchall()
    return [dict(row) for row in rows]


def task_get(task_id: str) -> dict | None:
    with _db() as conn:
        row = conn.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
    return dict(row) if row else None


def task_update(task_id: str, status: str, result: str = '') -> bool:
    with _db() as conn:
        cur = conn.execute(
            'UPDATE tasks SET status = ?, result = ?, updated = ? WHERE id = ?',
            (status, redact_text(result), _now(), task_id),
        )
    return cur.rowcount > 0
