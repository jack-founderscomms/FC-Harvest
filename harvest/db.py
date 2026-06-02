"""
SQLite persistence layer.

Schema
------
items          — every item ever fetched (deduped by source_id + item_id)
runs           — log of each harvest run
source_health  — last status per source (ok / error + message)
"""

import sqlite3
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "harvest.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS items (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id     TEXT    NOT NULL,
                item_id       TEXT    NOT NULL,
                title         TEXT    NOT NULL,
                url           TEXT,
                published_at  TEXT,
                summary       TEXT,
                matched_kws   TEXT    DEFAULT '[]',
                fetched_at    TEXT    NOT NULL,
                UNIQUE (source_id, item_id)
            );

            CREATE INDEX IF NOT EXISTS idx_items_source    ON items(source_id);
            CREATE INDEX IF NOT EXISTS idx_items_fetched   ON items(fetched_at DESC);
            CREATE INDEX IF NOT EXISTS idx_items_published ON items(published_at DESC);

            CREATE TABLE IF NOT EXISTS runs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at  TEXT NOT NULL,
                finished_at TEXT,
                new_items   INTEGER DEFAULT 0,
                errors      TEXT DEFAULT '[]'
            );

            CREATE TABLE IF NOT EXISTS source_health (
                source_id   TEXT PRIMARY KEY,
                status      TEXT NOT NULL DEFAULT 'unknown',  -- ok | error | warning
                message     TEXT DEFAULT '',
                item_count  INTEGER DEFAULT 0,
                checked_at  TEXT NOT NULL
            );
        """)


def upsert_item(db: sqlite3.Connection, source_id: str, item: dict) -> bool:
    fetched_at = datetime.now(timezone.utc).isoformat()
    matched_kws_json = json.dumps(item.get("matched_kws", []))
    try:
        db.execute(
            """
            INSERT INTO items (source_id, item_id, title, url, published_at, summary, matched_kws, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_id,
                item["item_id"],
                item["title"],
                item.get("url"),
                item.get("published_at"),
                item.get("summary"),
                matched_kws_json,
                fetched_at,
            ),
        )
        return True
    except sqlite3.IntegrityError:
        db.execute(
            "UPDATE items SET matched_kws = ? WHERE source_id = ? AND item_id = ?",
            (matched_kws_json, source_id, item["item_id"]),
        )
        return False


def record_source_health(
    db: sqlite3.Connection,
    source_id: str,
    status: str,
    message: str = "",
    item_count: int = 0,
):
    db.execute(
        """
        INSERT INTO source_health (source_id, status, message, item_count, checked_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(source_id) DO UPDATE SET
            status=excluded.status,
            message=excluded.message,
            item_count=excluded.item_count,
            checked_at=excluded.checked_at
        """,
        (source_id, status, message, item_count, datetime.now(timezone.utc).isoformat()),
    )


def get_source_health(db: sqlite3.Connection) -> dict[str, dict]:
    rows = db.execute("SELECT * FROM source_health").fetchall()
    return {r["source_id"]: _row_to_dict(r) for r in rows}


def get_items(
    db: sqlite3.Connection,
    source_ids: list[str] | None = None,
    keyword_filter: bool = False,
    limit: int = 500,
    offset: int = 0,
) -> list[dict]:
    where_clauses = []
    params: list = []

    if source_ids:
        placeholders = ",".join("?" * len(source_ids))
        where_clauses.append(f"source_id IN ({placeholders})")
        params.extend(source_ids)

    if keyword_filter:
        where_clauses.append("matched_kws != '[]'")

    where = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    rows = db.execute(
        f"""
        SELECT * FROM items
        {where}
        ORDER BY COALESCE(published_at, fetched_at) DESC
        LIMIT ? OFFSET ?
        """,
        params + [limit, offset],
    ).fetchall()

    return [_row_to_dict(r) for r in rows]


def get_source_ids(db: sqlite3.Connection) -> list[str]:
    rows = db.execute("SELECT DISTINCT source_id FROM items ORDER BY source_id").fetchall()
    return [r["source_id"] for r in rows]


def log_run_start(db: sqlite3.Connection) -> int:
    cur = db.execute(
        "INSERT INTO runs (started_at, errors) VALUES (?, '[]')",
        (datetime.now(timezone.utc).isoformat(),),
    )
    return cur.lastrowid


def log_run_finish(db: sqlite3.Connection, run_id: int, new_items: int, errors: list[str]):
    db.execute(
        "UPDATE runs SET finished_at=?, new_items=?, errors=? WHERE id=?",
        (
            datetime.now(timezone.utc).isoformat(),
            new_items,
            json.dumps(errors),
            run_id,
        ),
    )


def get_recent_runs(db: sqlite3.Connection, limit: int = 10) -> list[dict]:
    rows = db.execute(
        "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    for key in ("matched_kws", "errors"):
        if key in d and isinstance(d[key], str):
            try:
                d[key] = json.loads(d[key])
            except (json.JSONDecodeError, TypeError):
                pass
    return d
