"""SQLite durable entities. One installation / operator; teacher IDs isolate content."""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat()


def ident(prefix):
    return prefix + '_' + uuid4().hex[:16]


class Store:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        for folder in ('assets', 'exports'):
            (root / folder).mkdir(exist_ok=True)
        self.path = root / 'studio.sqlite3'
        with self.connection() as conn:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('CREATE TABLE IF NOT EXISTS entities (id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL)')
            conn.execute('CREATE INDEX IF NOT EXISTS entity_kind ON entities(kind)')

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path, timeout=15)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def get(self, kind, id):
        with self.connection() as c:
            row = c.execute('SELECT payload FROM entities WHERE id=? AND kind=?', (id, kind)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, kind, teacher_id=None):
        with self.connection() as c:
            rows = c.execute('SELECT payload FROM entities WHERE kind=? ORDER BY rowid DESC', (kind,)).fetchall()
        result = [json.loads(r[0]) for r in rows]
        return [r for r in result if teacher_id is None or r.get('teacher_id') == teacher_id]

    def put(self, kind, data):
        with self.connection() as c:
            c.execute('INSERT INTO entities VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',
                      (data['id'], kind, json.dumps(data, ensure_ascii=False)))
        return data

    def change_session(self, id, revision, mutate):
        # Database-level compare-and-swap also works across HTTP worker threads.
        with self.connection() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute("SELECT payload FROM entities WHERE kind='session' AND id=?", (id,)).fetchone()
            if not row:
                raise KeyError(id)
            value = json.loads(row[0])
            if value['revision'] != revision:
                raise ValueError('会话已更新，已丢弃旧操作。请重新同步。')
            mutate(value)
            value['revision'] += 1
            value['updated_at'] = now()
            c.execute('UPDATE entities SET payload=? WHERE id=?', (json.dumps(value, ensure_ascii=False), id))
        return value
