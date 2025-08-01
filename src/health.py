"""
Health check system for monitoring application status.

Provides HTTP health check endpoint and system monitoring.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from aiohttp import web, ClientSession
import json

from .config import Config
from .models import HealthStatus
from .database import DatabaseManager

logger = logging.getLogger(__name__)


class HealthChecker:
    """
    Health check system for monitoring application components.
    
    Features:
    - Database connectivity checks
    - API endpoint availability
    - System resource monitoring
    - HTTP health check endpoint
    """
    
    def __init__(
        self, 
        config: Config,
        database: Optional[DatabaseManager] = None
    ):
        self.config = config
        self.database = database
        self.app = web.Application()
        self.setup_routes()
        
        logger.info(f"Health checker initialized on port {config.health_check_port}")
    
    def setup_routes(self):
        """Setup HTTP routes for health checks."""
        self.app.router.add_get('/health', self.health_check_handler)
        self.app.router.add_get('/health/detailed', self.detailed_health_handler)
        self.app.router.add_get('/ready', self.readiness_handler)
        self.app.router.add_get('/live', self.liveness_handler)
    
    async def health_check_handler(self, request: web.Request) -> web.Response:
        """Basic health check endpoint."""
        try:
            health_status = await self.check_health()
            
            status_code = 200 if health_status.healthy else 503
            
            return web.json_response(
                health_status.to_dict(),
                status=status_code
            )
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return web.json_response(
                {
                    "healthy": False,
                    "message": f"Health check error: {str(e)}",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                },
                status=503
            )
    
    async def detailed_health_handler(self, request: web.Request) -> web.Response:
        """Detailed health check with component status."""
        try:
            health_status = await self.check_health()
            detailed_checks = await self.run_detailed_checks()
            
            response_data = health_status.to_dict()
            response_data["detailed_checks"] = detailed_checks
            
            status_code = 200 if health_status.healthy else 503
            
            return web.json_response(response_data, status=status_code)
            
        except Exception as e:
            logger.error(f"Detailed health check failed: {e}")
            return web.json_response(
                {
                    "healthy": False,
                    "message": f"Detailed health check error: {str(e)}",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                },
                status=503
            )
    
    async def readiness_handler(self, request: web.Request) -> web.Response:
        """Readiness probe - checks if app is ready to serve traffic."""
        try:
            checks = {
                "database": await self.check_database(),
                "configuration": await self.check_configuration()
            }
            
            ready = all(checks.values())
            status_code = 200 if ready else 503
            
            return web.json_response(
                {
                    "ready": ready,
                    "checks": checks,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                },
                status=status_code
            )
            
        except Exception as e:
            logger.error(f"Readiness check failed: {e}")
            return web.json_response(
                {"ready": False, "error": str(e)},
                status=503
            )
    
    async def liveness_handler(self, request: web.Request) -> web.Response:
        """Liveness probe - checks if app is alive."""
        return web.json_response(
            {
                "alive": True,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )
    
    async def check_health(self) -> HealthStatus:
        """
        Perform comprehensive health check.
        
        Returns:
            HealthStatus object with overall health and individual checks
        """
        checks = {}
        
        # Database check
        checks["database"] = await self.check_database()
        
        # Configuration check
        checks["configuration"] = await self.check_configuration()
        
        # Sync activity check (replaces API connectivity checks)
        checks["sync_activity"] = await self.check_sync_health()
        
        # System resource checks
        checks["disk_space"] = await self.check_disk_space()
        checks["memory"] = await self.check_memory()
        
        # Overall health
        healthy = all(checks.values())
        
        if healthy:
            message = "All systems operational"
        else:
            failed_checks = [name for name, status in checks.items() if not status]
            message = f"Health check failures: {', '.join(failed_checks)}"
        
        return HealthStatus(
            healthy=healthy,
            checks=checks,
            message=message,
            timestamp=datetime.now(timezone.utc)
        )
    
    async def check_database(self) -> bool:
        """Check database connectivity and health."""
        try:
            if not self.database:
                return True  # No database configured
            
            return self.database.health_check()
            
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False
    
    async def check_configuration(self) -> bool:
        """Check configuration validity."""
        try:
            # Check required configuration
            required_fields = [
                self.config.limitless_api_key,
                self.config.memorybox_api_key,
                self.config.mailgun_api_key,
                self.config.mailgun_domain,
                self.config.alert_email
            ]
            
            return all(field and field.strip() for field in required_fields)
            
        except Exception as e:
            logger.error(f"Configuration check failed: {e}")
            return False
    
    async def check_limitless_api(self) -> bool:
        """Check Limitless API connectivity."""
        try:
            timeout = 10  # Quick check
            async with ClientSession(timeout=timeout) as session:
                headers = {
                    "X-API-Key": self.config.limitless_api_key,
                    "Accept": "application/json"
                }
                
                # Try a simple endpoint
                async with session.get(
                    f"{self.config.limitless_api_url}/v1/lifelogs",
                    headers=headers,
                    params={"limit": 1}
                ) as response:
                    return response.status in [200, 401]  # 401 means API is up but auth failed
                    
        except Exception as e:
            logger.debug(f"Limitless API health check failed: {e}")
            return False
    
    async def check_memorybox_api(self) -> bool:
        """Check Memory Box API connectivity."""
        try:
            timeout = 10  # Quick check
            async with ClientSession(timeout=timeout) as session:
                headers = {
                    "Authorization": f"Bearer {self.config.memorybox_api_key}",
                    "Accept": "application/json"
                }
                
                # Try a simple endpoint
                async with session.get(
                    f"{self.config.memorybox_api_url}/api/v2/buckets",
                    headers=headers
                ) as response:
                    return response.status in [200, 401]  # 401 means API is up but auth failed
                    
        except Exception as e:
            logger.debug(f"Memory Box API health check failed: {e}")
            return False
    
    async def check_disk_space(self) -> bool:
        """Check available disk space."""
        try:
            import shutil
            
            # Check disk space for database directory
            db_path = self.config.database_path
            total, used, free = shutil.disk_usage(db_path)
            
            # Require at least 100MB free space
            min_free_bytes = 100 * 1024 * 1024  # 100MB
            return free > min_free_bytes
            
        except Exception as e:
            logger.debug(f"Disk space check failed: {e}")
            return True  # Don't fail health check for this
    
    async def check_memory(self) -> bool:
        """Check memory usage."""
        try:
            import psutil
            
            # Check memory usage
            memory = psutil.virtual_memory()
            
            # Fail if memory usage is above 90%
            return memory.percent < 90.0
            
        except ImportError:
            # psutil not available, skip check
            return True
        except Exception as e:
            logger.debug(f"Memory check failed: {e}")
            return True  # Don't fail health check for this
    
    async def check_sync_health(self) -> bool:
        """Check if sync is working based on recent activity."""
        if not self.database:
            return True  # No database configured, assume healthy
        
        try:
            stats = self.database.get_sync_stats()
            last_sync = stats.get('last_sync_time')
            
            if not last_sync:
                return True  # No syncs yet, that's okay for a new installation
            
            # Parse last sync time
            from datetime import timedelta
            last_sync_dt = datetime.fromisoformat(last_sync.replace('Z', '+00:00'))
            
            # Consider healthy if synced within last 2 hours
            # (accounts for 30-minute sync interval with plenty of buffer)
            cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
            return last_sync_dt > cutoff
            
        except Exception as e:
            logger.debug(f"Sync health check failed: {e}")
            return True  # Don't fail health check for this
    
    async def run_detailed_checks(self) -> Dict[str, Any]:
        """Run detailed system checks."""
        details = {}
        
        # Database details
        if self.database:
            try:
                stats = self.database.get_sync_stats()
                details["database"] = {
                    "connected": True,
                    "stats": stats
                }
            except Exception as e:
                details["database"] = {
                    "connected": False,
                    "error": str(e)
                }
        
        # Configuration details (non-sensitive only)
        details["configuration"] = {
            "sync_interval_minutes": self.config.sync_interval_minutes,
            "timezone": self.config.timezone
        }
        
        return details
    
    async def start_server(self) -> None:
        """Start the health check HTTP server."""
        runner = web.AppRunner(self.app)
        await runner.setup()
        
        site = web.TCPSite(
            runner, 
            '0.0.0.0', 
            self.config.health_check_port
        )
        
        await site.start()
        logger.info(f"Health check server started on port {self.config.health_check_port}")
    
    async def stop_server(self) -> None:
        """Stop the health check HTTP server."""
        await self.app.cleanup()
        logger.info("Health check server stopped")


async def create_health_checker(
    config: Config,
    database: Optional[DatabaseManager] = None
) -> HealthChecker:
    """
    Factory function to create and start health checker.
    
    Args:
        config: Application configuration
        database: Database manager instance
        
    Returns:
        Configured and started HealthChecker
    """
    checker = HealthChecker(config, database)
    await checker.start_server()
    return checker


# Standalone health check script
async def standalone_health_check() -> None:
    """Standalone health check for external monitoring."""
    try:
        from .config import load_config
        
        config = load_config()
        checker = HealthChecker(config)
        
        health_status = await checker.check_health()
        
        print(json.dumps(health_status.to_dict(), indent=2))
        
        # Exit with appropriate code
        exit(0 if health_status.healthy else 1)
        
    except Exception as e:
        print(json.dumps({
            "healthy": False,
            "message": f"Health check error: {str(e)}",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }, indent=2))
        exit(1)


if __name__ == "__main__":
    asyncio.run(standalone_health_check())
