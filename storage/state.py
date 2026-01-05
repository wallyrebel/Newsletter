"""
SQLite state management for the Newsletter Digest system.
Tracks sent articles, run history, and prevents duplicate sends.
"""

import sqlite3
from datetime import datetime, date
from pathlib import Path
from typing import Optional, Set
from contextlib import contextmanager
import logging

from utils.helpers import normalize_url

logger = logging.getLogger(__name__)


class StateManager:
    """Manages persistent state using SQLite."""
    
    def __init__(self, db_path: Path):
        """
        Initialize the state manager.
        
        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
        self._ensure_db_exists()
    
    def _ensure_db_exists(self):
        """Create the database and tables if they don't exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Table for tracking sent articles
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sent_articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL UNIQUE,
                    title TEXT,
                    source_name TEXT,
                    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Index for faster lookups
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sent_articles_url ON sent_articles(url)
            """)
            
            # Table for run history
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS run_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_date DATE NOT NULL,
                    run_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    articles_count INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'success',
                    error_message TEXT
                )
            """)
            
            # Index for checking if already sent today
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_run_history_date ON run_history(run_date)
            """)
            
            conn.commit()
    
    @contextmanager
    def _get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(
            self.db_path,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
        )
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def is_article_sent(self, url: str) -> bool:
        """
        Check if an article URL has already been sent.
        
        Args:
            url: Article URL to check
            
        Returns:
            True if the article was previously sent
        """
        normalized_url = normalize_url(url)
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM sent_articles WHERE url = ?",
                (normalized_url,)
            )
            return cursor.fetchone() is not None
    
    def get_sent_urls(self) -> Set[str]:
        """
        Get all previously sent article URLs.
        
        Returns:
            Set of normalized URLs
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT url FROM sent_articles")
            return {row['url'] for row in cursor.fetchall()}
    
    def mark_article_sent(self, url: str, title: str = "", source_name: str = ""):
        """
        Mark an article as sent.
        
        Args:
            url: Article URL
            title: Article title
            source_name: Source name
        """
        normalized_url = normalize_url(url)
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO sent_articles (url, title, source_name)
                    VALUES (?, ?, ?)
                    """,
                    (normalized_url, title, source_name)
                )
                conn.commit()
            except sqlite3.Error as e:
                logger.error(f"Error marking article as sent: {e}")
    
    def mark_articles_sent(self, articles: list):
        """
        Mark multiple articles as sent in a batch.
        
        Args:
            articles: List of article dicts with 'url', 'title', 'source_name'
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            for article in articles:
                normalized_url = normalize_url(article.get('url', ''))
                if normalized_url:
                    try:
                        cursor.execute(
                            """
                            INSERT OR IGNORE INTO sent_articles (url, title, source_name)
                            VALUES (?, ?, ?)
                            """,
                            (
                                normalized_url,
                                article.get('title', ''),
                                article.get('source_name', '')
                            )
                        )
                    except sqlite3.Error as e:
                        logger.error(f"Error marking article as sent: {e}")
            conn.commit()
    
    def was_sent_today(self, check_date: Optional[date] = None) -> bool:
        """
        Check if a digest was already sent today.
        
        Args:
            check_date: Date to check (defaults to today)
            
        Returns:
            True if already sent today
        """
        if check_date is None:
            check_date = date.today()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT 1 FROM run_history 
                WHERE run_date = ? AND status = 'success'
                """,
                (check_date,)
            )
            return cursor.fetchone() is not None
    
    def record_successful_run(self, articles_count: int, run_date: Optional[date] = None):
        """
        Record a successful digest run.
        
        Args:
            articles_count: Number of articles included
            run_date: Date of the run (defaults to today)
        """
        if run_date is None:
            run_date = date.today()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO run_history (run_date, articles_count, status)
                VALUES (?, ?, 'success')
                """,
                (run_date, articles_count)
            )
            conn.commit()
            logger.info(f"Recorded successful run for {run_date} with {articles_count} articles")
    
    def record_failed_run(self, error_message: str, run_date: Optional[date] = None):
        """
        Record a failed digest run.
        
        Args:
            error_message: Error description
            run_date: Date of the run (defaults to today)
        """
        if run_date is None:
            run_date = date.today()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO run_history (run_date, status, error_message)
                VALUES (?, 'failed', ?)
                """,
                (run_date, error_message)
            )
            conn.commit()
            logger.error(f"Recorded failed run for {run_date}: {error_message}")
    
    def get_last_successful_run(self) -> Optional[datetime]:
        """
        Get the timestamp of the last successful run.
        
        Returns:
            Datetime of last successful run or None
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT run_timestamp FROM run_history
                WHERE status = 'success'
                ORDER BY run_timestamp DESC
                LIMIT 1
                """
            )
            row = cursor.fetchone()
            return row['run_timestamp'] if row else None
    
    def cleanup_old_articles(self, days: int = 90):
        """
        Remove old sent article records to keep database size manageable.
        
        Args:
            days: Number of days to keep
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM sent_articles
                WHERE sent_at < datetime('now', ?)
                """,
                (f'-{days} days',)
            )
            deleted = cursor.rowcount
            conn.commit()
            if deleted > 0:
                logger.info(f"Cleaned up {deleted} old article records")
    
    def get_stats(self) -> dict:
        """
        Get statistics about the state database.
        
        Returns:
            Dict with stats like total_articles, total_runs, etc.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) as count FROM sent_articles")
            total_articles = cursor.fetchone()['count']
            
            cursor.execute(
                "SELECT COUNT(*) as count FROM run_history WHERE status = 'success'"
            )
            successful_runs = cursor.fetchone()['count']
            
            cursor.execute(
                "SELECT COUNT(*) as count FROM run_history WHERE status = 'failed'"
            )
            failed_runs = cursor.fetchone()['count']
            
            return {
                'total_articles_sent': total_articles,
                'successful_runs': successful_runs,
                'failed_runs': failed_runs
            }
