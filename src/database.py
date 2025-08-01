"""
Database management for Limitless to Memory Box Sync Agent.

Provides SQLite-based persistence for sync state and error tracking.
"""

import sqlite3
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any, Tuple
from pathlib import Path
import threading

from .models import (
    SyncedLifelog, SyncError, SyncMetrics, ProcessingStatus,
    LifelogEntry, SyncResult
)
from .config import Config

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages SQLite database operations for sync state."""
    
    def __init__(self, config: Config):
        self.config = config
        self.db_path = config.database_path
        self._local = threading.local()
        self._ensure_database_exists()
        self._init_database()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, 'connection'):
            self._local.connection = sqlite3.connect(
                self.db_path,
                timeout=30.0,
                check_same_thread=False
            )
            self._local.connection.row_factory = sqlite3.Row
            # Enable WAL mode for better concurrency
            self._local.connection.execute("PRAGMA journal_mode=WAL")
            self._local.connection.execute("PRAGMA synchronous=NORMAL")
            self._local.connection.execute("PRAGMA cache_size=10000")
            self._local.connection.execute("PRAGMA temp_store=memory")
        
        return self._local.connection
    
    def _ensure_database_exists(self) -> None:
        """Ensure database directory exists."""
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
    
    def _init_database(self) -> None:
        """Initialize database schema."""
        conn = self._get_connection()
        
        try:
            # Create tables
            self._create_sync_state_table(conn)
            self._create_synced_lifelogs_table(conn)
            self._create_sync_errors_table(conn)
            self._create_sync_metrics_table(conn)
            
            # Create indexes
            self._create_indexes(conn)
            
            # Initialize sync state if needed
            self._initialize_sync_state(conn)
            
            conn.commit()
            logger.info("Database initialized successfully")
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to initialize database: {e}")
            raise
    
    def _create_sync_state_table(self, conn: sqlite3.Connection) -> None:
        """Create sync_state table."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sync_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                last_sync_time TEXT NOT NULL,
                total_synced INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
    
    def _create_synced_lifelogs_table(self, conn: sqlite3.Connection) -> None:
        """Create synced_lifelogs table."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS synced_lifelogs (
                lifelog_id TEXT PRIMARY KEY,
                memory_box_id INTEGER,
                synced_at TEXT NOT NULL,
                title TEXT,
                start_time TEXT,
                end_time TEXT,
                processing_status TEXT DEFAULT 'pending',
                retry_count INTEGER DEFAULT 0,
                last_error TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
    
    def _create_sync_errors_table(self, conn: sqlite3.Connection) -> None:
        """Create sync_errors table."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sync_errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lifelog_id TEXT,
                error_type TEXT NOT NULL,
                error_message TEXT NOT NULL,
                error_details TEXT,
                occurred_at TEXT DEFAULT CURRENT_TIMESTAMP,
                resolved_at TEXT,
                FOREIGN KEY (lifelog_id) REFERENCES synced_lifelogs(lifelog_id)
            )
        """)
    
    def _create_sync_metrics_table(self, conn: sqlite3.Connection) -> None:
        """Create sync_metrics table."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sync_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sync_started_at TEXT NOT NULL,
                sync_completed_at TEXT,
                lifelogs_processed INTEGER DEFAULT 0,
                lifelogs_successful INTEGER DEFAULT 0,
                lifelogs_failed INTEGER DEFAULT 0,
                total_duration_seconds REAL,
                average_processing_time_ms REAL
            )
        """)
    
    def _create_indexes(self, conn: sqlite3.Connection) -> None:
        """Create database indexes for performance."""
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_synced_lifelogs_synced_at ON synced_lifelogs(synced_at)",
            "CREATE INDEX IF NOT EXISTS idx_synced_lifelogs_status ON synced_lifelogs(processing_status)",
            "CREATE INDEX IF NOT EXISTS idx_synced_lifelogs_start_time ON synced_lifelogs(start_time)",
            "CREATE INDEX IF NOT EXISTS idx_sync_errors_occurred_at ON sync_errors(occurred_at)",
            "CREATE INDEX IF NOT EXISTS idx_sync_errors_lifelog_id ON sync_errors(lifelog_id)",
            "CREATE INDEX IF NOT EXISTS idx_sync_metrics_started_at ON sync_metrics(sync_started_at)",
        ]
        
        for index_sql in indexes:
            conn.execute(index_sql)
    
    def _initialize_sync_state(self, conn: sqlite3.Connection) -> None:
        """Initialize sync state if not exists."""
        cursor = conn.execute("SELECT COUNT(*) FROM sync_state")
        if cursor.fetchone()[0] == 0:
            conn.execute("""
                INSERT INTO sync_state (last_sync_time, total_synced)
                VALUES (?, 0)
            """, (datetime.now(timezone.utc).isoformat(),))
    
    # Sync State Operations
    
    def get_last_sync_time(self) -> Optional[datetime]:
        """Get the last successful sync timestamp."""
        conn = self._get_connection()
        cursor = conn.execute("""
            SELECT last_sync_time FROM sync_state 
            ORDER BY id DESC LIMIT 1
        """)
        row = cursor.fetchone()
        if row and row[0]:
            return datetime.fromisoformat(row[0])
        return None
    
    def update_sync_time(self, sync_time: datetime) -> None:
        """Update the last sync timestamp."""
        conn = self._get_connection()
        conn.execute("""
            UPDATE sync_state 
            SET last_sync_time = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = (SELECT MAX(id) FROM sync_state)
        """, (sync_time.isoformat(),))
        conn.commit()
    
    def get_sync_stats(self) -> Dict[str, Any]:
        """Get synchronization statistics."""
        conn = self._get_connection()
        
        # Total synced
        cursor = conn.execute("SELECT COUNT(*) FROM synced_lifelogs")
        total_synced = cursor.fetchone()[0]
        
        # Last sync time
        cursor = conn.execute("""
            SELECT last_sync_time FROM sync_state ORDER BY id DESC LIMIT 1
        """)
        last_sync_row = cursor.fetchone()
        last_sync = last_sync_row[0] if last_sync_row else None
        
        # Recent syncs (last 24 hours)
        yesterday = (datetime.now(timezone.utc) - 
                    timedelta(days=1)).isoformat()
        cursor = conn.execute("""
            SELECT COUNT(*) FROM synced_lifelogs WHERE synced_at > ?
        """, (yesterday,))
        recent_syncs = cursor.fetchone()[0]
        
        # Processing status breakdown
        cursor = conn.execute("""
            SELECT processing_status, COUNT(*) 
            FROM synced_lifelogs 
            GROUP BY processing_status
        """)
        status_breakdown = dict(cursor.fetchall())
        
        # Recent errors (last 24 hours)
        cursor = conn.execute("""
            SELECT COUNT(*) FROM sync_errors WHERE occurred_at > ?
        """, (yesterday,))
        recent_errors = cursor.fetchone()[0]
        
        return {
            "total_synced": total_synced,
            "last_sync_time": last_sync,
            "recent_syncs_24h": recent_syncs,
            "recent_errors_24h": recent_errors,
            "status_breakdown": status_breakdown
        }
    
    # Lifelog Operations
    
    def is_lifelog_synced(self, lifelog_id: str) -> bool:
        """Check if a lifelog has already been synced."""
        conn = self._get_connection()
        cursor = conn.execute("""
            SELECT COUNT(*) FROM synced_lifelogs WHERE lifelog_id = ?
        """, (lifelog_id,))
        return cursor.fetchone()[0] > 0
    
    def get_synced_lifelog(self, lifelog_id: str) -> Optional[SyncedLifelog]:
        """Get a synced lifelog record."""
        conn = self._get_connection()
        cursor = conn.execute("""
            SELECT lifelog_id, memory_box_id, synced_at, title, start_time, 
                   end_time, processing_status, retry_count, last_error, created_at
            FROM synced_lifelogs WHERE lifelog_id = ?
        """, (lifelog_id,))
        row = cursor.fetchone()
        if row:
            return SyncedLifelog.from_db_row(tuple(row))
        return None
    
    def mark_lifelog_synced(
        self, 
        lifelog_entry: LifelogEntry,
        memory_box_id: Optional[int] = None,
        status: ProcessingStatus = ProcessingStatus.PENDING
    ) -> None:
        """Mark a lifelog as synced."""
        conn = self._get_connection()
        
        synced_lifelog = SyncedLifelog(
            lifelog_id=lifelog_entry.id,
            memory_box_id=memory_box_id,
            synced_at=datetime.now(timezone.utc),
            title=lifelog_entry.title,
            start_time=lifelog_entry.start_time,
            end_time=lifelog_entry.end_time,
            processing_status=status,
            retry_count=0,
            last_error=None,
            created_at=datetime.now(timezone.utc)
        )
        
        conn.execute("""
            INSERT OR REPLACE INTO synced_lifelogs
            (lifelog_id, memory_box_id, synced_at, title, start_time, 
             end_time, processing_status, retry_count, last_error, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, synced_lifelog.to_db_tuple())
        
        # Update total count
        conn.execute("""
            UPDATE sync_state 
            SET total_synced = (SELECT COUNT(*) FROM synced_lifelogs),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = (SELECT MAX(id) FROM sync_state)
        """)
        
        conn.commit()
    
    def update_lifelog_status(
        self, 
        lifelog_id: str, 
        status: ProcessingStatus,
        memory_box_id: Optional[int] = None,
        error_message: Optional[str] = None
    ) -> None:
        """Update lifelog processing status."""
        conn = self._get_connection()
        
        # Get current retry count
        cursor = conn.execute("""
            SELECT retry_count FROM synced_lifelogs WHERE lifelog_id = ?
        """, (lifelog_id,))
        row = cursor.fetchone()
        retry_count = (row[0] if row else 0) + (1 if status == ProcessingStatus.RETRY else 0)
        
        conn.execute("""
            UPDATE synced_lifelogs 
            SET processing_status = ?, 
                memory_box_id = COALESCE(?, memory_box_id),
                retry_count = ?,
                last_error = ?,
                synced_at = CURRENT_TIMESTAMP
            WHERE lifelog_id = ?
        """, (status.value, memory_box_id, retry_count, error_message, lifelog_id))
        
        conn.commit()
    
    def get_failed_lifelogs(self, max_retries: int = 3) -> List[SyncedLifelog]:
        """Get lifelogs that failed processing and can be retried."""
        conn = self._get_connection()
        cursor = conn.execute("""
            SELECT lifelog_id, memory_box_id, synced_at, title, start_time, 
                   end_time, processing_status, retry_count, last_error, created_at
            FROM synced_lifelogs 
            WHERE processing_status IN ('failed', 'retry') 
            AND retry_count < ?
            ORDER BY synced_at ASC
        """, (max_retries,))
        
        return [SyncedLifelog.from_db_row(tuple(row)) for row in cursor.fetchall()]
    
    def get_pending_lifelogs(self) -> List[SyncedLifelog]:
        """Get lifelogs that are still pending processing."""
        conn = self._get_connection()
        cursor = conn.execute("""
            SELECT lifelog_id, memory_box_id, synced_at, title, start_time, 
                   end_time, processing_status, retry_count, last_error, created_at
            FROM synced_lifelogs 
            WHERE processing_status = 'pending'
            ORDER BY synced_at ASC
        """)
        
        return [SyncedLifelog.from_db_row(tuple(row)) for row in cursor.fetchall()]
    
    # Error Operations
    
    def log_error(self, error: SyncError) -> int:
        """Log a sync error to the database."""
        conn = self._get_connection()
        cursor = conn.execute("""
            INSERT INTO sync_errors 
            (lifelog_id, error_type, error_message, error_details, occurred_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            error.lifelog_id,
            error.error_type,
            error.error_message,
            error.error_details,
            error.occurred_at.isoformat()
        ))
        
        conn.commit()
        return cursor.lastrowid
    
    def get_recent_errors(self, hours: int = 24) -> List[SyncError]:
        """Get recent sync errors."""
        conn = self._get_connection()
        since = (datetime.now(timezone.utc) - 
                timedelta(hours=hours)).isoformat()
        
        cursor = conn.execute("""
            SELECT id, lifelog_id, error_type, error_message, error_details, 
                   occurred_at, resolved_at
            FROM sync_errors 
            WHERE occurred_at > ?
            ORDER BY occurred_at DESC
        """, (since,))
        
        errors = []
        for row in cursor.fetchall():
            error = SyncError(
                id=row[0],
                lifelog_id=row[1],
                error_type=row[2],
                error_message=row[3],
                error_details=row[4],
                occurred_at=datetime.fromisoformat(row[5]),
                resolved_at=datetime.fromisoformat(row[6]) if row[6] else None
            )
            errors.append(error)
        
        return errors
    
    # Metrics Operations
    
    def start_sync_metrics(self) -> int:
        """Start tracking metrics for a sync operation."""
        conn = self._get_connection()
        cursor = conn.execute("""
            INSERT INTO sync_metrics (sync_started_at)
            VALUES (?)
        """, (datetime.now(timezone.utc).isoformat(),))
        
        conn.commit()
        return cursor.lastrowid
    
    def update_sync_metrics(self, metrics: SyncMetrics) -> None:
        """Update sync metrics."""
        conn = self._get_connection()
        conn.execute("""
            UPDATE sync_metrics 
            SET sync_completed_at = ?,
                lifelogs_processed = ?,
                lifelogs_successful = ?,
                lifelogs_failed = ?,
                total_duration_seconds = ?,
                average_processing_time_ms = ?
            WHERE id = ?
        """, (
            metrics.sync_completed_at.isoformat() if metrics.sync_completed_at else None,
            metrics.lifelogs_processed,
            metrics.lifelogs_successful,
            metrics.lifelogs_failed,
            metrics.total_duration_seconds,
            metrics.average_processing_time_ms,
            metrics.id
        ))
        
        conn.commit()
    
    def get_recent_metrics(self, days: int = 7) -> List[SyncMetrics]:
        """Get recent sync metrics."""
        conn = self._get_connection()
        since = (datetime.now(timezone.utc) - 
                timedelta(days=days)).isoformat()
        
        cursor = conn.execute("""
            SELECT id, sync_started_at, sync_completed_at, lifelogs_processed,
                   lifelogs_successful, lifelogs_failed, total_duration_seconds,
                   average_processing_time_ms
            FROM sync_metrics 
            WHERE sync_started_at > ?
            ORDER BY sync_started_at DESC
        """, (since,))
        
        metrics = []
        for row in cursor.fetchall():
            metric = SyncMetrics(
                id=row[0],
                sync_started_at=datetime.fromisoformat(row[1]),
                sync_completed_at=datetime.fromisoformat(row[2]) if row[2] else None,
                lifelogs_processed=row[3],
                lifelogs_successful=row[4],
                lifelogs_failed=row[5],
                total_duration_seconds=row[6],
                average_processing_time_ms=row[7]
            )
            metrics.append(metric)
        
        return metrics
    
    # Maintenance Operations
    
    def cleanup_old_data(self, days: int = 90) -> Dict[str, int]:
        """Clean up old data from the database."""
        conn = self._get_connection()
        cutoff = (datetime.now(timezone.utc) - 
                 timedelta(days=days)).isoformat()
        
        # Clean up old errors
        cursor = conn.execute("""
            DELETE FROM sync_errors WHERE occurred_at < ?
        """, (cutoff,))
        errors_deleted = cursor.rowcount
        
        # Clean up old metrics
        cursor = conn.execute("""
            DELETE FROM sync_metrics WHERE sync_started_at < ?
        """, (cutoff,))
        metrics_deleted = cursor.rowcount
        
        # Vacuum database
        conn.execute("VACUUM")
        conn.commit()
        
        return {
            "errors_deleted": errors_deleted,
            "metrics_deleted": metrics_deleted
        }
    
    def health_check(self) -> bool:
        """Perform database health check."""
        try:
            conn = self._get_connection()
            cursor = conn.execute("SELECT 1")
            cursor.fetchone()
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False
    
    def close(self) -> None:
        """Close database connections."""
        if hasattr(self._local, 'connection'):
            self._local.connection.close()
            delattr(self._local, 'connection')
