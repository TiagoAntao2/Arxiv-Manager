#!/usr/bin/env python3
"""
store.py: SQLite-backed paper store for arxivManager.
"""

import sqlite3
import datetime
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path("arxiv_manager.db")


@contextmanager
def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db() -> None:
    with _conn() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS papers (
                arxiv_id    TEXT PRIMARY KEY,
                title       TEXT NOT NULL,
                authors     TEXT NOT NULL,
                abstract    TEXT NOT NULL,
                url         TEXT NOT NULL,
                submitted   TEXT NOT NULL,
                added       TEXT NOT NULL,
                highlighted INTEGER DEFAULT NULL
            );

            CREATE TABLE IF NOT EXISTS paper_recipients (
                arxiv_id    TEXT NOT NULL REFERENCES papers(arxiv_id),
                recipient   TEXT NOT NULL,
                PRIMARY KEY (arxiv_id, recipient)
            );

            CREATE TABLE IF NOT EXISTS downloads (
                arxiv_id    TEXT PRIMARY KEY REFERENCES papers(arxiv_id),
                path        TEXT NOT NULL,
                downloaded  TEXT NOT NULL
            );
        """)
        # migrate existing DBs that predate the highlighted column
        cols = {r[1] for r in con.execute("PRAGMA table_info(papers)")}
        if "highlighted" not in cols:
            con.execute("ALTER TABLE papers ADD COLUMN highlighted INTEGER DEFAULT NULL")


def upsert_paper(arxiv_id: str, title: str, authors: str, abstract: str,
                 url: str, submitted: datetime.datetime, recipients: list[str]) -> None:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with _conn() as con:
        con.execute("""
            INSERT INTO papers (arxiv_id, title, authors, abstract, url, submitted, added)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(arxiv_id) DO NOTHING
        """, (arxiv_id, title, authors, abstract, url, submitted.isoformat(), now))
        for r in recipients:
            con.execute("""
                INSERT INTO paper_recipients (arxiv_id, recipient)
                VALUES (?, ?)
                ON CONFLICT DO NOTHING
            """, (arxiv_id, r))


def mark_highlighted(arxiv_id: str, highlighted: bool) -> None:
    with _conn() as con:
        con.execute("UPDATE papers SET highlighted=? WHERE arxiv_id=?",
                    (1 if highlighted else 0, arxiv_id))


def get_pending_highlight(limit: int = 100) -> list[sqlite3.Row]:
    with _conn() as con:
        return con.execute(
            "SELECT * FROM papers WHERE highlighted IS NULL ORDER BY submitted DESC LIMIT ?",
            (limit,)
        ).fetchall()


def mark_downloaded(arxiv_id: str, path: Path) -> None:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with _conn() as con:
        con.execute("""
            INSERT INTO downloads (arxiv_id, path, downloaded)
            VALUES (?, ?, ?)
            ON CONFLICT(arxiv_id) DO UPDATE SET path=excluded.path, downloaded=excluded.downloaded
        """, (arxiv_id, str(path), now))


def get_available_dates() -> list[str]:
    with _conn() as con:
        rows = con.execute(
            "SELECT DISTINCT substr(submitted, 1, 10) AS day FROM papers ORDER BY day DESC"
        ).fetchall()
        return [r["day"] for r in rows]


def get_papers(downloaded_only: bool = False, highlighted_only: bool = False,
               search: str = "", date: str = "") -> list[sqlite3.Row]:
    query = """
        SELECT p.*, d.path IS NOT NULL AS is_downloaded
        FROM papers p
        LEFT JOIN downloads d USING (arxiv_id)
    """
    conditions, params = [], []
    if date:
        conditions.append("substr(p.submitted, 1, 10) = ?")
        params.append(date)
    if downloaded_only:
        conditions.append("d.path IS NOT NULL")
    if highlighted_only:
        conditions.append("p.highlighted = 1")
    if search:
        conditions.append("(p.title LIKE ? OR p.abstract LIKE ? OR p.authors LIKE ?)")
        term = f"%{search}%"
        params.extend([term, term, term])
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY p.highlighted DESC NULLS LAST, p.submitted DESC"
    with _conn() as con:
        return con.execute(query, params).fetchall()
