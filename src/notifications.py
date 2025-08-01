"""
Email notification system using Mailgun.

Provides email alerts and summaries for operational monitoring.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import httpx

from .config import Config
from .models import SyncResult, SyncError, HealthStatus

logger = logging.getLogger(__name__)


class NotificationError(Exception):
    """Base exception for notification errors."""
    pass


class MailgunError(NotificationError):
    """Raised when Mailgun API fails."""
    pass


class NotificationManager:
    """
    Manages email notifications via Mailgun.
    
    Features:
    - Error alerts for sync failures
    - Daily summary reports
    - System health notifications
    - Configurable alert thresholds
    """
    
    def __init__(self, config: Config):
        self.config = config
        
        # Initialize HTTP client for Mailgun
        self.client = httpx.AsyncClient(
            base_url=f"https://api.mailgun.net/v3/{config.mailgun_domain}",
            auth=("api", config.mailgun_api_key),
            timeout=httpx.Timeout(30.0, connect=10.0)
        )
        
        # Email templates
        self.from_email = f"Limitless Sync <sync@{config.mailgun_domain}>"
        
        logger.info(f"Notification manager initialized for {config.mailgun_domain}")
    
    async def send_error_alert(
        self, 
        error: SyncError, 
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Send immediate error alert email.
        
        Args:
            error: The sync error that occurred
            context: Additional context information
            
        Returns:
            True if sent successfully, False otherwise
        """
        logger.info(f"Sending error alert for {error.error_type}")
        
        subject = f"🚨 Limitless Sync Error: {error.error_type}"
        
        # Build error message
        message_lines = [
            "An error occurred in the Limitless to Memory Box sync process:",
            "",
            f"**Error Type:** {error.error_type}",
            f"**Error Message:** {error.error_message}",
            f"**Time:** {error.occurred_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
        ]
        
        if error.lifelog_id:
            message_lines.append(f"**Lifelog ID:** {error.lifelog_id}")
        
        if error.error_details:
            message_lines.extend([
                "",
                "**Details:**",
                error.error_details
            ])
        
        if context:
            message_lines.extend([
                "",
                "**Additional Context:**"
            ])
            for key, value in context.items():
                message_lines.append(f"- {key}: {value}")
        
        message_lines.extend([
            "",
            "Please check the application logs for more information.",
            "",
            "---",
            "Limitless to Memory Box Sync Agent"
        ])
        
        message = "\n".join(message_lines)
        
        return await self._send_email(subject, message, priority="high")
    
    async def send_sync_summary(
        self, 
        result: SyncResult, 
        stats: Dict[str, Any]
    ) -> bool:
        """
        Send sync operation summary email.
        
        Args:
            result: The sync operation result
            stats: Additional statistics
            
        Returns:
            True if sent successfully, False otherwise
        """
        logger.info("Sending sync summary email")
        
        # Determine subject based on success
        if result.has_errors:
            subject = f"⚠️ Limitless Sync Summary - {result.error_count} Errors"
        else:
            subject = f"✅ Limitless Sync Summary - {result.success_count} Processed"
        
        # Build summary message
        message_lines = [
            "Limitless to Memory Box Sync Summary",
            "",
            f"**Sync ID:** {result.sync_id or 'N/A'}",
            f"**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"**Duration:** {result.duration_seconds:.1f} seconds",
            "",
            "**Results:**",
            f"- Total Processed: {result.total_processed}",
            f"- Successful: {result.success_count}",
            f"- Failed: {result.error_count}",
            f"- Success Rate: {result.success_rate:.1%}",
        ]
        
        # Add statistics if available
        if stats:
            message_lines.extend([
                "",
                "**Statistics:**"
            ])
            for key, value in stats.items():
                if isinstance(value, dict):
                    message_lines.append(f"- {key}:")
                    for sub_key, sub_value in value.items():
                        message_lines.append(f"  - {sub_key}: {sub_value}")
                else:
                    message_lines.append(f"- {key}: {value}")
        
        # Add errors if any
        if result.errors:
            message_lines.extend([
                "",
                "**Errors:**"
            ])
            for i, error in enumerate(result.errors[:5], 1):  # Limit to first 5 errors
                message_lines.append(f"{i}. {error}")
            
            if len(result.errors) > 5:
                message_lines.append(f"... and {len(result.errors) - 5} more errors")
        
        message_lines.extend([
            "",
            "---",
            "Limitless to Memory Box Sync Agent"
        ])
        
        message = "\n".join(message_lines)
        
        return await self._send_email(subject, message)
    
    async def send_daily_summary(
        self, 
        daily_stats: Dict[str, Any],
        recent_errors: List[SyncError]
    ) -> bool:
        """
        Send daily summary report.
        
        Args:
            daily_stats: Daily statistics
            recent_errors: Recent errors (last 24 hours)
            
        Returns:
            True if sent successfully, False otherwise
        """
        logger.info("Sending daily summary email")
        
        date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        subject = f"📊 Limitless Sync Daily Summary - {date_str}"
        
        # Build daily summary
        message_lines = [
            f"Daily Summary Report - {date_str}",
            "",
            "**24-Hour Statistics:**",
            f"- Total Synced: {daily_stats.get('total_synced', 0)}",
            f"- Recent Syncs: {daily_stats.get('recent_syncs_24h', 0)}",
            f"- Recent Errors: {daily_stats.get('recent_errors_24h', 0)}",
        ]
        
        # Add status breakdown if available
        if daily_stats.get('status_breakdown'):
            message_lines.extend([
                "",
                "**Processing Status Breakdown:**"
            ])
            for status, count in daily_stats['status_breakdown'].items():
                message_lines.append(f"- {status.title()}: {count}")
        
        # Add recent errors
        if recent_errors:
            message_lines.extend([
                "",
                "**Recent Errors (Last 24 Hours):**"
            ])
            for error in recent_errors[:10]:  # Limit to 10 most recent
                time_str = error.occurred_at.strftime('%H:%M')
                message_lines.append(f"- {time_str}: {error.error_type} - {error.error_message}")
            
            if len(recent_errors) > 10:
                message_lines.append(f"... and {len(recent_errors) - 10} more errors")
        else:
            message_lines.extend([
                "",
                "**Recent Errors:** None ✅"
            ])
        
        # Add system health info
        message_lines.extend([
            "",
            "**System Status:**",
            f"- Last Sync: {daily_stats.get('last_sync_time', 'Unknown')}",
            f"- Database: {'✅ Healthy' if daily_stats.get('database_healthy', True) else '❌ Issues'}",
        ])
        
        message_lines.extend([
            "",
            "---",
            "Limitless to Memory Box Sync Agent"
        ])
        
        message = "\n".join(message_lines)
        
        return await self._send_email(subject, message)
    
    async def send_health_alert(
        self, 
        health_status: HealthStatus,
        details: Optional[str] = None
    ) -> bool:
        """
        Send system health alert.
        
        Args:
            health_status: Current health status
            details: Additional details about the health issue
            
        Returns:
            True if sent successfully, False otherwise
        """
        logger.info(f"Sending health alert: healthy={health_status.healthy}")
        
        if health_status.healthy:
            subject = "✅ Limitless Sync - System Recovered"
            status_emoji = "✅"
        else:
            subject = "🚨 Limitless Sync - System Health Alert"
            status_emoji = "❌"
        
        # Build health message
        message_lines = [
            f"System Health Alert - {status_emoji}",
            "",
            f"**Status:** {'Healthy' if health_status.healthy else 'Unhealthy'}",
            f"**Time:** {health_status.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"**Message:** {health_status.message}",
            "",
            "**Health Checks:**"
        ]
        
        for check_name, check_result in health_status.checks.items():
            status = "✅ Pass" if check_result else "❌ Fail"
            message_lines.append(f"- {check_name}: {status}")
        
        if details:
            message_lines.extend([
                "",
                "**Additional Details:**",
                details
            ])
        
        message_lines.extend([
            "",
            "Please investigate and resolve any failing health checks.",
            "",
            "---",
            "Limitless to Memory Box Sync Agent"
        ])
        
        message = "\n".join(message_lines)
        
        priority = "high" if not health_status.healthy else "normal"
        return await self._send_email(subject, message, priority=priority)
    
    async def _send_email(
        self, 
        subject: str, 
        message: str,
        priority: str = "normal"
    ) -> bool:
        """
        Send email via Mailgun API.
        
        Args:
            subject: Email subject
            message: Email message body
            priority: Email priority (normal, high)
            
        Returns:
            True if sent successfully, False otherwise
        """
        try:
            # Prepare email data
            data = {
                "from": self.from_email,
                "to": self.config.alert_email,
                "subject": subject,
                "text": message
            }
            
            # Add priority headers
            if priority == "high":
                data["h:X-Priority"] = "1"
                data["h:Importance"] = "high"
            
            # Send email
            response = await self.client.post("/messages", data=data)
            
            if response.status_code == 200:
                logger.info(f"Email sent successfully: {subject}")
                return True
            else:
                logger.error(f"Failed to send email: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending email: {e}")
            return False
    
    async def test_email_delivery(self) -> bool:
        """
        Test email delivery by sending a test message.
        
        Returns:
            True if test email sent successfully, False otherwise
        """
        logger.info("Sending test email")
        
        subject = "🧪 Limitless Sync - Test Email"
        message = """
This is a test email from the Limitless to Memory Box Sync Agent.

If you receive this email, the notification system is working correctly.

**Test Details:**
- Time: {time}
- Configuration: {domain}
- Recipient: {email}

---
Limitless to Memory Box Sync Agent
        """.format(
            time=datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
            domain=self.config.mailgun_domain,
            email=self.config.alert_email
        ).strip()
        
        return await self._send_email(subject, message)
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get notification system statistics."""
        return {
            "mailgun_domain": self.config.mailgun_domain,
            "alert_email": self.config.alert_email,
            "from_email": self.from_email
        }
    
    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()
        logger.info("Notification manager closed")


async def create_notification_manager(config: Config) -> NotificationManager:
    """
    Factory function to create and test notification manager.
    
    Args:
        config: Application configuration
        
    Returns:
        Configured NotificationManager
        
    Raises:
        NotificationError: If manager creation or test fails
    """
    manager = NotificationManager(config)
    
    # Test email delivery
    if not await manager.test_email_delivery():
        await manager.close()
        raise NotificationError("Failed to send test email")
    
    return manager
