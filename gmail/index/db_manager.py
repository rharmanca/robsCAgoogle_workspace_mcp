"""
SQLite database manager with FTS5 full-text search.

Uses external content FTS5 tables to avoid data duplication.
BM25 scoring with column weights for relevance ranking.
"""

import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Default database location - supports EMAIL_INDEX_DATA_DIR env var for Railway volumes
def get_default_db_path() -> Path:
    """Get default database path, using env var if set for Railway deployment."""
    data_dir = os.environ.get("EMAIL_INDEX_DATA_DIR")
    if data_dir:
        return Path(data_dir) / "email_index.db"
    return Path.home() / ".workspace-mcp" / "email_index.db"


class DatabaseManager:
    """Manages SQLite database with FTS5 for email indexing."""

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize database manager.

        Args:
            db_path: Path to SQLite database file. Uses EMAIL_INDEX_DATA_DIR env var if set.
        """
        self.db_path = db_path or get_default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        # Enable WAL mode for better concurrency
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self):
        """Initialize database schema with FTS5 tables and triggers."""
        with self._get_connection() as conn:
            # Main emails table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS emails (
                    id INTEGER PRIMARY KEY,
                    message_id TEXT UNIQUE NOT NULL,
                    thread_id TEXT,
                    user_email TEXT NOT NULL,
                    subject TEXT,
                    sender TEXT,
                    body_text TEXT,
                    date_sent TEXT,
                    indexed_at TEXT,
                    embedding_id TEXT
                )
            """)

            # Create indexes
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_emails_user_email
                ON emails(user_email)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_emails_message_id
                ON emails(message_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_emails_date_sent
                ON emails(date_sent)
            """)

            # Check if FTS table exists
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='emails_fts'"
            )
            if cursor.fetchone() is None:
                # Create FTS5 virtual table with external content
                conn.execute("""
                    CREATE VIRTUAL TABLE emails_fts USING fts5(
                        subject, sender, body_text,
                        content='emails', content_rowid='id',
                        tokenize='porter unicode61 remove_diacritics 1',
                        prefix='2 3'
                    )
                """)

                # Triggers for FTS sync (AFTER INSERT)
                conn.execute("""
                    CREATE TRIGGER IF NOT EXISTS emails_ai AFTER INSERT ON emails BEGIN
                        INSERT INTO emails_fts(rowid, subject, sender, body_text)
                        VALUES (new.id, new.subject, new.sender, new.body_text);
                    END
                """)

                # Trigger for DELETE - note special syntax with table name as first column
                conn.execute("""
                    CREATE TRIGGER IF NOT EXISTS emails_ad AFTER DELETE ON emails BEGIN
                        INSERT INTO emails_fts(emails_fts, rowid, subject, sender, body_text)
                        VALUES('delete', old.id, old.subject, old.sender, old.body_text);
                    END
                """)

                # Trigger for UPDATE - delete then insert
                conn.execute("""
                    CREATE TRIGGER IF NOT EXISTS emails_au AFTER UPDATE ON emails BEGIN
                        INSERT INTO emails_fts(emails_fts, rowid, subject, sender, body_text)
                        VALUES('delete', old.id, old.subject, old.sender, old.body_text);
                        INSERT INTO emails_fts(rowid, subject, sender, body_text)
                        VALUES (new.id, new.subject, new.sender, new.body_text);
                    END
                """)

            # Sync state table for tracking Gmail historyId
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sync_state (
                    user_email TEXT PRIMARY KEY,
                    history_id TEXT,
                    last_sync TEXT,
                    total_indexed INTEGER DEFAULT 0
                )
            """)

            logger.info(f"Database initialized at {self.db_path}")

    def upsert_email(
        self,
        message_id: str,
        user_email: str,
        thread_id: Optional[str] = None,
        subject: Optional[str] = None,
        sender: Optional[str] = None,
        body_text: Optional[str] = None,
        date_sent: Optional[str] = None,
        embedding_id: Optional[str] = None,
    ) -> int:
        """
        Insert or update an email in the database.

        Returns:
            The row id of the inserted/updated email.
        """
        indexed_at = datetime.now(timezone.utc).isoformat()

        with self._get_connection() as conn:
            # Check if email exists
            cursor = conn.execute(
                "SELECT id FROM emails WHERE message_id = ?",
                (message_id,)
            )
            existing = cursor.fetchone()

            if existing:
                # Update existing
                conn.execute("""
                    UPDATE emails SET
                        thread_id = ?,
                        user_email = ?,
                        subject = ?,
                        sender = ?,
                        body_text = ?,
                        date_sent = ?,
                        indexed_at = ?,
                        embedding_id = ?
                    WHERE message_id = ?
                """, (
                    thread_id, user_email, subject, sender,
                    body_text, date_sent, indexed_at, embedding_id,
                    message_id
                ))
                return existing['id']
            else:
                # Insert new
                cursor = conn.execute("""
                    INSERT INTO emails (
                        message_id, thread_id, user_email, subject,
                        sender, body_text, date_sent, indexed_at, embedding_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    message_id, thread_id, user_email, subject,
                    sender, body_text, date_sent, indexed_at, embedding_id
                ))
                return cursor.lastrowid

    def upsert_emails_batch(self, emails: list[dict]) -> int:
        """
        Batch insert/update emails.

        Args:
            emails: List of email dicts with keys matching upsert_email params.

        Returns:
            Number of emails processed.
        """
        indexed_at = datetime.now(timezone.utc).isoformat()
        count = 0

        with self._get_connection() as conn:
            for email in emails:
                message_id = email['message_id']

                # Check if exists
                cursor = conn.execute(
                    "SELECT id FROM emails WHERE message_id = ?",
                    (message_id,)
                )
                existing = cursor.fetchone()

                if existing:
                    conn.execute("""
                        UPDATE emails SET
                            thread_id = ?,
                            user_email = ?,
                            subject = ?,
                            sender = ?,
                            body_text = ?,
                            date_sent = ?,
                            indexed_at = ?,
                            embedding_id = ?
                        WHERE message_id = ?
                    """, (
                        email.get('thread_id'),
                        email['user_email'],
                        email.get('subject'),
                        email.get('sender'),
                        email.get('body_text'),
                        email.get('date_sent'),
                        indexed_at,
                        email.get('embedding_id'),
                        message_id
                    ))
                else:
                    conn.execute("""
                        INSERT INTO emails (
                            message_id, thread_id, user_email, subject,
                            sender, body_text, date_sent, indexed_at, embedding_id
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        message_id,
                        email.get('thread_id'),
                        email['user_email'],
                        email.get('subject'),
                        email.get('sender'),
                        email.get('body_text'),
                        email.get('date_sent'),
                        indexed_at,
                        email.get('embedding_id')
                    ))
                count += 1

        return count

    def search_fts(
        self,
        query: str,
        user_email: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict]:
        """
        Full-text search using FTS5 with BM25 ranking.

        BM25 returns negative values - lower (more negative) is better match.
        Column weights: sender(10), subject(5), body(1)

        Args:
            query: Search query (FTS5 syntax)
            user_email: Filter to specific user
            limit: Max results to return
            offset: Pagination offset

        Returns:
            List of matching emails with relevance scores.
        """
        # Escape special FTS5 characters in query
        escaped_query = self._escape_fts_query(query)

        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT
                    e.id,
                    e.message_id,
                    e.thread_id,
                    e.subject,
                    e.sender,
                    e.date_sent,
                    snippet(emails_fts, 2, '<b>', '</b>', '...', 32) as snippet,
                    bm25(emails_fts, 10.0, 5.0, 1.0) as score
                FROM emails_fts
                JOIN emails e ON e.id = emails_fts.rowid
                WHERE emails_fts MATCH ? AND e.user_email = ?
                ORDER BY bm25(emails_fts, 10.0, 5.0, 1.0)
                LIMIT ? OFFSET ?
            """, (escaped_query, user_email, limit, offset))

            results = []
            for row in cursor.fetchall():
                results.append({
                    'id': row['id'],
                    'message_id': row['message_id'],
                    'thread_id': row['thread_id'],
                    'subject': row['subject'],
                    'sender': row['sender'],
                    'date_sent': row['date_sent'],
                    'snippet': row['snippet'],
                    'score': row['score'],  # Negative, lower is better
                })

            return results

    def _escape_fts_query(self, query: str) -> str:
        """
        Escape special FTS5 characters for safe queries.
        Wraps terms in quotes to enable phrase matching.
        """
        # For simple queries, wrap each word to avoid syntax errors
        # Remove special characters that could break FTS5
        cleaned = query.replace('"', ' ').replace("'", ' ')
        # Split into words and filter empty
        words = [w.strip() for w in cleaned.split() if w.strip()]
        # Join with OR for broader matching
        if len(words) == 1:
            return words[0]
        return ' OR '.join(words)

    def get_email_by_message_id(self, message_id: str) -> Optional[dict]:
        """Get a single email by Gmail message ID."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM emails WHERE message_id = ?",
                (message_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_emails_by_ids(self, row_ids: list[int]) -> list[dict]:
        """Get emails by their database row IDs."""
        if not row_ids:
            return []

        placeholders = ','.join('?' * len(row_ids))
        with self._get_connection() as conn:
            cursor = conn.execute(
                f"SELECT * FROM emails WHERE id IN ({placeholders})",
                row_ids
            )
            return [dict(row) for row in cursor.fetchall()]

    def delete_email(self, message_id: str) -> bool:
        """Delete an email by message ID."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM emails WHERE message_id = ?",
                (message_id,)
            )
            return cursor.rowcount > 0

    def get_sync_state(self, user_email: str) -> Optional[dict]:
        """Get sync state for a user."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM sync_state WHERE user_email = ?",
                (user_email,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_sync_state(
        self,
        user_email: str,
        history_id: str,
        total_indexed: int,
    ):
        """Update sync state for a user."""
        last_sync = datetime.now(timezone.utc).isoformat()

        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO sync_state (user_email, history_id, last_sync, total_indexed)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_email) DO UPDATE SET
                    history_id = excluded.history_id,
                    last_sync = excluded.last_sync,
                    total_indexed = excluded.total_indexed
            """, (user_email, history_id, last_sync, total_indexed))

    def get_stats(self, user_email: Optional[str] = None) -> dict:
        """Get database statistics."""
        with self._get_connection() as conn:
            if user_email:
                cursor = conn.execute(
                    "SELECT COUNT(*) as count FROM emails WHERE user_email = ?",
                    (user_email,)
                )
                count = cursor.fetchone()['count']

                sync_state = self.get_sync_state(user_email)

                return {
                    'total_emails': count,
                    'user_email': user_email,
                    'last_sync': sync_state['last_sync'] if sync_state else None,
                    'history_id': sync_state['history_id'] if sync_state else None,
                }
            else:
                cursor = conn.execute("SELECT COUNT(*) as count FROM emails")
                count = cursor.fetchone()['count']

                cursor = conn.execute(
                    "SELECT COUNT(DISTINCT user_email) as users FROM emails"
                )
                users = cursor.fetchone()['users']

                return {
                    'total_emails': count,
                    'total_users': users,
                    'db_path': str(self.db_path),
                    'db_size_mb': self.db_path.stat().st_size / (1024 * 1024) if self.db_path.exists() else 0,
                }

    def rebuild_fts_index(self):
        """Rebuild the FTS index from the emails table."""
        with self._get_connection() as conn:
            # Delete all FTS content
            conn.execute("DELETE FROM emails_fts")

            # Rebuild from emails table
            conn.execute("""
                INSERT INTO emails_fts(rowid, subject, sender, body_text)
                SELECT id, subject, sender, body_text FROM emails
            """)

            logger.info("FTS index rebuilt successfully")
