"""
Main sync agent orchestrating Limitless to Memory Box synchronization.

Provides scheduled sync operations with comprehensive error handling and monitoring.
"""

import asyncio
import logging
import signal
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .config import Config
from .database import DatabaseManager
from .limitless_client import LimitlessClient, create_limitless_client
from .memorybox_client import MemoryBoxClient, create_memorybox_client
from .content_processor import ContentProcessor
from .notifications import NotificationManager, create_notification_manager
from .health import HealthChecker, create_health_checker
from .models import (
    LifelogEntry, SyncResult, SyncMetrics, SyncError, ProcessingStatus
)

logger = logging.getLogger(__name__)


class SyncAgent:
    """
    Main synchronization agent orchestrating the sync process.
    
    Features:
    - Scheduled periodic sync operations
    - Incremental sync with state tracking
    - Comprehensive error handling and recovery
    - Health monitoring and notifications
    - Graceful shutdown handling
    """
    
    def __init__(self, config: Config):
        self.config = config
        self.running = False
        self.shutdown_event = asyncio.Event()
        
        # Core components
        self.database: Optional[DatabaseManager] = None
        self.limitless_client: Optional[LimitlessClient] = None
        self.memorybox_client: Optional[MemoryBoxClient] = None
        self.content_processor: Optional[ContentProcessor] = None
        self.notification_manager: Optional[NotificationManager] = None
        self.health_checker: Optional[HealthChecker] = None
        
        # Scheduler
        self.scheduler: Optional[AsyncIOScheduler] = None
        
        # Statistics
        self.last_sync_result: Optional[SyncResult] = None
        self.total_synced = 0
        
        logger.info("Sync agent initialized")
    
    async def initialize(self) -> None:
        """Initialize all components."""
        logger.info("Initializing sync agent components...")
        
        try:
            # Initialize database
            logger.info("Initializing database...")
            self.database = DatabaseManager(self.config)
            
            # Initialize content processor
            logger.info("Initializing content processor...")
            self.content_processor = ContentProcessor(self.config)
            
            # Initialize API clients
            logger.info("Initializing Limitless client...")
            self.limitless_client = await create_limitless_client(self.config)
            
            logger.info("Initializing Memory Box client...")
            self.memorybox_client = await create_memorybox_client(self.config)
            
            # Initialize notification manager
            logger.info("Initializing notification manager...")
            self.notification_manager = await create_notification_manager(self.config)
            
            # Initialize health checker
            logger.info("Initializing health checker...")
            self.health_checker = await create_health_checker(self.config, self.database)
            
            # Initialize scheduler
            self.scheduler = AsyncIOScheduler()
            
            logger.info("All components initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize components: {e}")
            await self.cleanup()
            raise
    
    async def start(self) -> None:
        """Start the sync agent."""
        if self.running:
            logger.warning("Sync agent is already running")
            return
        
        logger.info("Starting Limitless to Memory Box Sync Agent...")
        
        try:
            # Initialize components if not already done
            if not self.database:
                await self.initialize()
            
            # Setup signal handlers
            self._setup_signal_handlers()
            
            # Schedule periodic sync
            self._schedule_sync()
            
            # Start scheduler
            self.scheduler.start()
            
            # Run initial sync
            logger.info("Running initial sync...")
            await self.sync_lifelogs()
            
            # Mark as running
            self.running = True
            
            logger.info(
                f"Sync agent started successfully. "
                f"Syncing every {self.config.sync_interval_minutes} minutes."
            )
            
            # Send startup notification
            if self.notification_manager:
                await self._send_startup_notification()
            
            # Keep running until shutdown
            await self.shutdown_event.wait()
            
        except Exception as e:
            logger.error(f"Failed to start sync agent: {e}")
            await self.cleanup()
            raise
    
    async def stop(self) -> None:
        """Stop the sync agent gracefully."""
        if not self.running:
            return
        
        logger.info("Stopping sync agent...")
        
        self.running = False
        
        # Stop scheduler
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=True)
        
        # Send shutdown notification
        if self.notification_manager:
            await self._send_shutdown_notification()
        
        # Cleanup components
        await self.cleanup()
        
        # Signal shutdown complete
        self.shutdown_event.set()
        
        logger.info("Sync agent stopped")
    
    async def sync_lifelogs(self) -> SyncResult:
        """
        Perform synchronization of lifelogs from Limitless to Memory Box.
        
        Returns:
            SyncResult with operation statistics
        """
        sync_id = str(uuid.uuid4())[:8]
        start_time = datetime.now(timezone.utc)
        
        logger.info(f"Starting sync operation {sync_id}")
        
        # Initialize metrics tracking
        metrics_id = self.database.start_sync_metrics()
        metrics = SyncMetrics(
            id=metrics_id,
            sync_started_at=start_time,
            sync_completed_at=None
        )
        
        # Initialize result
        result = SyncResult(
            success_count=0,
            error_count=0,
            total_processed=0,
            duration_seconds=0.0,
            sync_id=sync_id
        )
        
        try:
            # Get last sync time for incremental sync
            last_sync_time = self.database.get_last_sync_time()
            
            # Fetch new lifelogs with enhanced parameters
            logger.info(f"Fetching lifelogs since {last_sync_time}")
            lifelogs = await self.limitless_client.fetch_lifelogs(
                start_date=last_sync_time,
                limit=None,  # Fetch all new lifelogs
                direction="asc",  # Chronological order for sync
                include_markdown=True,  # Get both markdown and structured content
                include_headings=True   # Include heading structure
            )
            
            # Filter out already synced lifelogs
            new_lifelogs = [
                lifelog for lifelog in lifelogs
                if not self.database.is_lifelog_synced(lifelog.id)
            ]
            
            logger.info(f"Found {len(new_lifelogs)} new lifelogs to sync")
            
            result.total_processed = len(new_lifelogs)
            metrics.lifelogs_processed = len(new_lifelogs)
            
            # Process each lifelog
            for lifelog in new_lifelogs:
                try:
                    success = await self._process_lifelog(lifelog)
                    
                    if success:
                        result.success_count += 1
                        metrics.lifelogs_successful += 1
                    else:
                        result.error_count += 1
                        metrics.lifelogs_failed += 1
                        result.add_error(f"Failed to process lifelog {lifelog.id}")
                    
                    # Small delay between processing
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    logger.error(f"Error processing lifelog {lifelog.id}: {e}")
                    result.error_count += 1
                    metrics.lifelogs_failed += 1
                    result.add_error(f"Exception processing {lifelog.id}: {str(e)}")
                    
                    # Log error to database
                    sync_error = SyncError.from_exception(e, lifelog.id, "ProcessingError")
                    self.database.log_error(sync_error)
            
            # Update sync time if we processed any lifelogs
            if new_lifelogs:
                latest_time = max(lifelog.updated_at for lifelog in new_lifelogs)
                self.database.update_sync_time(latest_time)
            
            # Complete metrics
            metrics.complete_sync()
            result.duration_seconds = metrics.total_duration_seconds or 0.0
            
            # Update database metrics
            self.database.update_sync_metrics(metrics)
            
            # Update statistics
            self.last_sync_result = result
            self.total_synced += result.success_count
            
            # Log results
            logger.info(
                f"Sync {sync_id} completed: {result.success_count}/{result.total_processed} successful "
                f"in {result.duration_seconds:.1f}s"
            )
            
            # Send notifications if needed
            if result.has_errors and self.notification_manager:
                await self._send_error_notifications(result)
            
            return result
            
        except Exception as e:
            logger.error(f"Sync operation {sync_id} failed: {e}")
            
            # Complete metrics with error
            metrics.complete_sync()
            metrics.lifelogs_failed = metrics.lifelogs_processed
            self.database.update_sync_metrics(metrics)
            
            # Update result
            result.duration_seconds = (datetime.now(timezone.utc) - start_time).total_seconds()
            result.add_error(f"Sync operation failed: {str(e)}")
            
            # Log error
            sync_error = SyncError.from_exception(e, None, "SyncOperationError")
            self.database.log_error(sync_error)
            
            # Send error notification
            if self.notification_manager:
                await self.notification_manager.send_error_alert(sync_error)
            
            raise
    
    async def _process_lifelog(self, lifelog: LifelogEntry) -> bool:
        """
        Process a single lifelog entry.
        
        Args:
            lifelog: The lifelog entry to process
            
        Returns:
            True if processed successfully, False otherwise
        """
        logger.debug(f"Processing lifelog {lifelog.id}: {lifelog.title}")
        
        try:
            # Mark as pending in database
            self.database.mark_lifelog_synced(
                lifelog, 
                memory_box_id=None, 
                status=ProcessingStatus.PENDING
            )
            
            # Process content
            formatted_content, reference_data = self.content_processor.process_lifelog(lifelog)
            
            # Create memory in Memory Box
            memory_id = await self.memorybox_client.create_memory(
                lifelog, 
                formatted_content, 
                reference_data
            )
            
            if memory_id:
                # Update database with success
                self.database.update_lifelog_status(
                    lifelog.id,
                    ProcessingStatus.PROCESSED,
                    memory_box_id=memory_id
                )
                
                logger.info(f"Successfully synced lifelog {lifelog.id} to memory {memory_id}")
                return True
            else:
                # Update database with failure
                self.database.update_lifelog_status(
                    lifelog.id,
                    ProcessingStatus.FAILED,
                    error_message="Memory Box processing failed"
                )
                
                logger.error(f"Failed to sync lifelog {lifelog.id}")
                return False
                
        except Exception as e:
            logger.error(f"Error processing lifelog {lifelog.id}: {e}")
            
            # Update database with error
            self.database.update_lifelog_status(
                lifelog.id,
                ProcessingStatus.FAILED,
                error_message=str(e)
            )
            
            return False
    
    def _schedule_sync(self) -> None:
        """Schedule periodic sync operations."""
        self.scheduler.add_job(
            self.sync_lifelogs,
            IntervalTrigger(minutes=self.config.sync_interval_minutes),
            id="sync_job",
            name="Sync Limitless to Memory Box",
            max_instances=1,  # Prevent overlapping syncs
            coalesce=True,    # Combine missed runs
            misfire_grace_time=300  # 5 minutes grace period
        )
        
        logger.info(f"Scheduled sync every {self.config.sync_interval_minutes} minutes")
    
    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating shutdown...")
            asyncio.create_task(self.stop())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    async def _send_startup_notification(self) -> None:
        """Send startup notification."""
        try:
            stats = self.database.get_sync_stats()
            
            subject = "✅ Limitless Sync Agent Started"
            message = f"""
Limitless to Memory Box Sync Agent has started successfully.

**Configuration:**
- Sync Interval: {self.config.sync_interval_minutes} minutes
- Timezone: {self.config.timezone}
- Memory Box Bucket: {self.config.memorybox_bucket}

**Current Statistics:**
- Total Synced: {stats.get('total_synced', 0)}
- Last Sync: {stats.get('last_sync_time', 'Never')}

The agent is now monitoring for new lifelogs and will sync them automatically.

---
Limitless to Memory Box Sync Agent
            """.strip()
            
            await self.notification_manager._send_email(subject, message)
            
        except Exception as e:
            logger.error(f"Failed to send startup notification: {e}")
    
    async def _send_shutdown_notification(self) -> None:
        """Send shutdown notification."""
        try:
            subject = "🛑 Limitless Sync Agent Stopped"
            message = f"""
Limitless to Memory Box Sync Agent has been stopped.

**Final Statistics:**
- Total Synced This Session: {self.total_synced}
- Last Sync Result: {self.last_sync_result.success_count if self.last_sync_result else 0} successful

The agent is no longer monitoring for new lifelogs.

---
Limitless to Memory Box Sync Agent
            """.strip()
            
            await self.notification_manager._send_email(subject, message)
            
        except Exception as e:
            logger.error(f"Failed to send shutdown notification: {e}")
    
    async def _send_error_notifications(self, result: SyncResult) -> None:
        """Send error notifications for failed sync."""
        try:
            # Send summary if there were errors
            stats = self.database.get_sync_stats()
            await self.notification_manager.send_sync_summary(result, stats)
            
        except Exception as e:
            logger.error(f"Failed to send error notifications: {e}")
    
    async def get_status(self) -> Dict[str, Any]:
        """Get current sync agent status."""
        status = {
            "running": self.running,
            "total_synced": self.total_synced,
            "last_sync_result": self.last_sync_result.to_dict() if self.last_sync_result else None,
            "next_sync": None
        }
        
        # Get next scheduled sync time
        if self.scheduler and self.scheduler.running:
            jobs = self.scheduler.get_jobs()
            if jobs:
                status["next_sync"] = jobs[0].next_run_time.isoformat()
        
        # Get component status
        if self.database:
            status["database_stats"] = self.database.get_sync_stats()
        
        if self.limitless_client:
            status["limitless_client"] = await self.limitless_client.get_stats()
        
        if self.memorybox_client:
            status["memorybox_client"] = await self.memorybox_client.get_stats()
        
        return status
    
    async def cleanup(self) -> None:
        """Clean up all resources."""
        logger.info("Cleaning up sync agent resources...")
        
        # Close clients
        if self.limitless_client:
            await self.limitless_client.close()
        
        if self.memorybox_client:
            await self.memorybox_client.close()
        
        if self.notification_manager:
            await self.notification_manager.close()
        
        if self.health_checker:
            await self.health_checker.stop_server()
        
        # Close database
        if self.database:
            self.database.close()
        
        logger.info("Cleanup completed")


async def create_sync_agent(config: Config) -> SyncAgent:
    """
    Factory function to create and initialize sync agent.
    
    Args:
        config: Application configuration
        
    Returns:
        Initialized SyncAgent
    """
    agent = SyncAgent(config)
    await agent.initialize()
    return agent
