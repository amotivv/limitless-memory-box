"""
Data models for Limitless to Memory Box Sync Agent.

Provides type-safe data structures for lifelogs, content nodes, and system state.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any, Union
from enum import Enum
import json


class ConversationType(Enum):
    """Types of conversations based on content analysis."""
    MEETING = "MEETING"
    TECHNICAL = "TECHNICAL"
    DECISION = "DECISION"
    PERSONAL = "PERSONAL"
    CONVERSATION = "CONVERSATION"


class ProcessingStatus(Enum):
    """Processing status for synced lifelogs."""
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    RETRY = "retry"


@dataclass
class ContentNode:
    """Represents a content node from Limitless lifelog structure."""
    type: str  # heading1, heading2, heading3, blockquote, etc.
    content: str
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    start_offset_ms: Optional[int] = None
    end_offset_ms: Optional[int] = None
    speaker_name: Optional[str] = None
    speaker_identifier: Optional[str] = None  # "user" when identified
    children: List['ContentNode'] = field(default_factory=list)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContentNode":
        """Create ContentNode from API response data."""
        children = []
        if data.get("children"):
            children = [cls.from_dict(child) for child in data["children"]]
        
        # Parse datetime strings if present
        start_time = None
        end_time = None
        if data.get("startTime"):
            try:
                start_time = datetime.fromisoformat(data["startTime"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass
        
        if data.get("endTime"):
            try:
                end_time = datetime.fromisoformat(data["endTime"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass
        
        return cls(
            type=data.get("type", ""),
            content=data.get("content", ""),
            start_time=start_time,
            end_time=end_time,
            start_offset_ms=data.get("startOffsetMs"),
            end_offset_ms=data.get("endOffsetMs"),
            speaker_name=data.get("speakerName"),
            speaker_identifier=data.get("speakerIdentifier"),
            children=children
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert ContentNode to dictionary."""
        result = {
            "type": self.type,
            "content": self.content,
            "children": [child.to_dict() for child in self.children]
        }
        
        if self.start_time:
            result["startTime"] = self.start_time.isoformat()
        if self.end_time:
            result["endTime"] = self.end_time.isoformat()
        if self.start_offset_ms is not None:
            result["startOffsetMs"] = self.start_offset_ms
        if self.end_offset_ms is not None:
            result["endOffsetMs"] = self.end_offset_ms
        if self.speaker_name:
            result["speakerName"] = self.speaker_name
        if self.speaker_identifier:
            result["speakerIdentifier"] = self.speaker_identifier
        
        return result


@dataclass
class LifelogEntry:
    """Represents a Limitless lifelog entry."""
    id: str
    title: str
    markdown: Optional[str]
    start_time: datetime
    end_time: datetime
    is_starred: bool
    updated_at: datetime
    contents: List[ContentNode]
    
    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> "LifelogEntry":
        """Create LifelogEntry from Limitless API response following official MCP patterns."""
        # Parse contents (following official MCP server pattern)
        contents = []
        if data.get("contents"):
            contents = [ContentNode.from_dict(node) for node in data["contents"]]
        
        return cls(
            id=data["id"],
            title=data["title"],
            markdown=data.get("markdown"),  # Prioritize markdown content as per official MCP server
            start_time=datetime.fromisoformat(data["startTime"].replace("Z", "+00:00")),
            end_time=datetime.fromisoformat(data["endTime"].replace("Z", "+00:00")),
            is_starred=data.get("isStarred", False),
            updated_at=datetime.fromisoformat(data["updatedAt"].replace("Z", "+00:00")),
            contents=contents
        )
    
    @property
    def duration_minutes(self) -> int:
        """Get duration in minutes."""
        return int((self.end_time - self.start_time).total_seconds() / 60)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert LifelogEntry to dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "markdown": self.markdown,
            "startTime": self.start_time.isoformat(),
            "endTime": self.end_time.isoformat(),
            "isStarred": self.is_starred,
            "updatedAt": self.updated_at.isoformat(),
            "contents": [node.to_dict() for node in self.contents]
        }


@dataclass
class SyncResult:
    """Result of a sync operation."""
    success_count: int
    error_count: int
    total_processed: int
    duration_seconds: float
    errors: List[str] = field(default_factory=list)
    sync_id: Optional[str] = None
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_processed == 0:
            return 1.0
        return self.success_count / self.total_processed
    
    @property
    def has_errors(self) -> bool:
        """Check if sync had any errors."""
        return self.error_count > 0 or len(self.errors) > 0
    
    def add_error(self, error: str) -> None:
        """Add an error to the result."""
        self.errors.append(error)
        self.error_count += 1
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
        return {
            "sync_id": self.sync_id,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "total_processed": self.total_processed,
            "duration_seconds": self.duration_seconds,
            "success_rate": self.success_rate,
            "has_errors": self.has_errors,
            "errors": self.errors
        }


@dataclass
class ContentStructure:
    """Analysis of content structure for categorization."""
    heading_count: int = 0
    speaker_changes: int = 0
    has_user_speech: bool = False
    content_types: List[str] = field(default_factory=list)
    total_nodes: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "heading_count": self.heading_count,
            "speaker_changes": self.speaker_changes,
            "has_user_speech": self.has_user_speech,
            "content_types": self.content_types,
            "total_nodes": self.total_nodes
        }


@dataclass
class MemoryBoxReferenceData:
    """Reference data structure for Memory Box API."""
    lifelog_id: str
    duration_minutes: int
    is_starred: bool
    speakers: List[str]
    start_time: str
    end_time: str
    conversation_type: ConversationType
    content_structure: ContentStructure
    
    def to_memory_box_format(self) -> Dict[str, Any]:
        """Convert to Memory Box API format following MCP server patterns."""
        return {
            "source": {
                "platform": "limitless_pendant",
                "type": "application_plugin",
                "version": "1.0",
                "url": f"limitless://lifelog/{self.lifelog_id}",
                "title": f"Limitless Lifelog - {self.conversation_type.value}"
            },
            "content_context": {
                "url": f"limitless://lifelog/{self.lifelog_id}",
                "title": f"Limitless Lifelog - {self.conversation_type.value}",
                "additional_context": {
                    "lifelog_id": self.lifelog_id,
                    "duration_minutes": self.duration_minutes,
                    "is_starred": self.is_starred,
                    "speakers": self.speakers,
                    "start_time": self.start_time,
                    "end_time": self.end_time,
                    "conversation_type": self.conversation_type.value,
                    "content_structure": self.content_structure.to_dict()
                }
            }
        }


@dataclass
class SyncedLifelog:
    """Represents a synced lifelog record in the database."""
    lifelog_id: str
    memory_box_id: Optional[int]
    synced_at: datetime
    title: str
    start_time: datetime
    end_time: datetime
    processing_status: ProcessingStatus
    retry_count: int = 0
    last_error: Optional[str] = None
    created_at: Optional[datetime] = None
    
    @classmethod
    def from_db_row(cls, row: tuple) -> "SyncedLifelog":
        """Create from database row."""
        return cls(
            lifelog_id=row[0],
            memory_box_id=row[1],
            synced_at=datetime.fromisoformat(row[2]),
            title=row[3],
            start_time=datetime.fromisoformat(row[4]),
            end_time=datetime.fromisoformat(row[5]),
            processing_status=ProcessingStatus(row[6]),
            retry_count=row[7] or 0,
            last_error=row[8],
            created_at=datetime.fromisoformat(row[9]) if row[9] else None
        )
    
    def to_db_tuple(self) -> tuple:
        """Convert to database tuple for insertion."""
        return (
            self.lifelog_id,
            self.memory_box_id,
            self.synced_at.isoformat(),
            self.title,
            self.start_time.isoformat(),
            self.end_time.isoformat(),
            self.processing_status.value,
            self.retry_count,
            self.last_error,
            self.created_at.isoformat() if self.created_at else datetime.now().isoformat()
        )


@dataclass
class SyncError:
    """Represents a sync error record."""
    id: Optional[int]
    lifelog_id: Optional[str]
    error_type: str
    error_message: str
    error_details: Optional[str]
    occurred_at: datetime
    resolved_at: Optional[datetime] = None
    
    @classmethod
    def from_exception(
        cls, 
        error: Exception, 
        lifelog_id: Optional[str] = None,
        error_type: Optional[str] = None
    ) -> "SyncError":
        """Create SyncError from an exception."""
        return cls(
            id=None,
            lifelog_id=lifelog_id,
            error_type=error_type or type(error).__name__,
            error_message=str(error),
            error_details=None,
            occurred_at=datetime.now()
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "id": self.id,
            "lifelog_id": self.lifelog_id,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "error_details": self.error_details,
            "occurred_at": self.occurred_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None
        }


@dataclass
class SyncMetrics:
    """Metrics for a sync operation."""
    id: Optional[int]
    sync_started_at: datetime
    sync_completed_at: Optional[datetime]
    lifelogs_processed: int = 0
    lifelogs_successful: int = 0
    lifelogs_failed: int = 0
    total_duration_seconds: Optional[float] = None
    average_processing_time_ms: Optional[float] = None
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.lifelogs_processed == 0:
            return 1.0
        return self.lifelogs_successful / self.lifelogs_processed
    
    def complete_sync(self) -> None:
        """Mark sync as completed and calculate metrics."""
        from datetime import timezone
        self.sync_completed_at = datetime.now(timezone.utc)
        if self.sync_started_at:
            self.total_duration_seconds = (
                self.sync_completed_at - self.sync_started_at
            ).total_seconds()
        
        if self.lifelogs_processed > 0 and self.total_duration_seconds:
            self.average_processing_time_ms = (
                self.total_duration_seconds * 1000 / self.lifelogs_processed
            )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "id": self.id,
            "sync_started_at": self.sync_started_at.isoformat(),
            "sync_completed_at": self.sync_completed_at.isoformat() if self.sync_completed_at else None,
            "lifelogs_processed": self.lifelogs_processed,
            "lifelogs_successful": self.lifelogs_successful,
            "lifelogs_failed": self.lifelogs_failed,
            "total_duration_seconds": self.total_duration_seconds,
            "average_processing_time_ms": self.average_processing_time_ms,
            "success_rate": self.success_rate
        }


@dataclass
class HealthStatus:
    """Health check status."""
    healthy: bool
    checks: Dict[str, bool]
    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "healthy": self.healthy,
            "checks": self.checks,
            "message": self.message,
            "timestamp": self.timestamp.isoformat()
        }
