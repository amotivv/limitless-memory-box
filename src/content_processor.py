"""
Content processing and categorization for Limitless lifelogs.

Provides intelligent content analysis, categorization, and formatting for Memory Box.
"""

import logging
from datetime import datetime
from typing import List, Dict, Any, Set
import re

from .config import Config
from .models import (
    LifelogEntry, ContentNode, ConversationType, ContentStructure, 
    MemoryBoxReferenceData
)

logger = logging.getLogger(__name__)


class ContentProcessor:
    """
    Processes and categorizes Limitless lifelog content for Memory Box storage.
    
    Features:
    - Intelligent conversation type classification
    - Speaker extraction and identification
    - Content structure analysis
    - Markdown formatting for optimal searchability
    """
    
    def __init__(self, config: Config):
        self.config = config
        
        # Keywords for conversation type classification
        self.meeting_keywords = {
            "meeting", "standup", "sync", "1:1", "review", "retrospective",
            "planning", "kickoff", "demo", "presentation", "interview",
            "call", "conference", "discussion", "session"
        }
        
        self.technical_keywords = {
            "code", "debug", "api", "database", "deploy", "deployment",
            "bug", "fix", "feature", "implementation", "architecture",
            "system", "server", "client", "framework", "library",
            "programming", "development", "software", "technical",
            "infrastructure", "devops", "ci/cd", "testing"
        }
        
        self.decision_keywords = {
            "decision", "decided", "plan", "strategy", "approach",
            "solution", "recommendation", "proposal", "choice",
            "option", "alternative", "conclusion", "resolution",
            "agreement", "consensus", "direction", "path forward"
        }
        
        self.personal_keywords = {
            "personal", "family", "friend", "relationship", "health",
            "hobby", "interest", "vacation", "travel", "weekend",
            "evening", "morning", "lunch", "dinner", "coffee",
            "casual", "informal", "private"
        }
        
        logger.info("Content processor initialized")
    
    def process_lifelog(self, entry: LifelogEntry) -> tuple[str, MemoryBoxReferenceData]:
        """
        Process a lifelog entry for Memory Box storage.
        
        Args:
            entry: The lifelog entry to process
            
        Returns:
            Tuple of (formatted_content, reference_data)
        """
        logger.debug(f"Processing lifelog {entry.id}: {entry.title}")
        
        # Analyze content structure
        content_structure = self._analyze_content_structure(entry.contents)
        
        # Determine conversation type
        conversation_type = self._determine_conversation_type(entry, content_structure)
        
        # Extract speakers
        speakers = self._extract_speakers(entry.contents)
        
        # Format content for Memory Box
        formatted_content = self._format_content(entry, conversation_type, speakers, content_structure)
        
        # Build reference data
        reference_data = MemoryBoxReferenceData(
            lifelog_id=entry.id,
            duration_minutes=entry.duration_minutes,
            is_starred=entry.is_starred,
            speakers=speakers,
            start_time=entry.start_time.isoformat(),
            end_time=entry.end_time.isoformat(),
            conversation_type=conversation_type,
            content_structure=content_structure
        )
        
        logger.debug(
            f"Processed lifelog {entry.id}: type={conversation_type.value}, "
            f"speakers={len(speakers)}, duration={entry.duration_minutes}min"
        )
        
        return formatted_content, reference_data
    
    def _determine_conversation_type(
        self, 
        entry: LifelogEntry, 
        content_structure: ContentStructure
    ) -> ConversationType:
        """Determine the type of conversation based on content analysis."""
        
        # Combine title and content for analysis
        text_to_analyze = entry.title.lower()
        
        # Add content from nodes for better classification
        content_text = self._extract_text_from_contents(entry.contents).lower()
        text_to_analyze += " " + content_text[:500]  # Limit to first 500 chars for performance
        
        # Score each category
        scores = {
            ConversationType.MEETING: self._calculate_keyword_score(text_to_analyze, self.meeting_keywords),
            ConversationType.TECHNICAL: self._calculate_keyword_score(text_to_analyze, self.technical_keywords),
            ConversationType.DECISION: self._calculate_keyword_score(text_to_analyze, self.decision_keywords),
            ConversationType.PERSONAL: self._calculate_keyword_score(text_to_analyze, self.personal_keywords)
        }
        
        # Apply content structure bonuses
        if content_structure.speaker_changes >= 2:
            scores[ConversationType.MEETING] += 0.3
        
        if content_structure.heading_count >= 3:
            scores[ConversationType.TECHNICAL] += 0.2
            scores[ConversationType.DECISION] += 0.2
        
        if content_structure.has_user_speech:
            scores[ConversationType.MEETING] += 0.1
        
        # Apply time-based heuristics
        if entry.duration_minutes >= 30:
            scores[ConversationType.MEETING] += 0.2
        
        if entry.duration_minutes <= 5:
            scores[ConversationType.PERSONAL] += 0.1
        
        # Find the highest scoring category
        best_type = max(scores.items(), key=lambda x: x[1])
        
        # Require minimum confidence threshold
        if best_type[1] >= 0.3:
            logger.debug(f"Classified as {best_type[0].value} with score {best_type[1]:.2f}")
            return best_type[0]
        else:
            logger.debug(f"Low confidence classification, defaulting to CONVERSATION")
            return ConversationType.CONVERSATION
    
    def _calculate_keyword_score(self, text: str, keywords: Set[str]) -> float:
        """Calculate keyword match score for text."""
        words = set(re.findall(r'\b\w+\b', text.lower()))
        matches = words.intersection(keywords)
        
        if not keywords:
            return 0.0
        
        # Base score from keyword matches
        base_score = len(matches) / len(keywords)
        
        # Bonus for multiple matches of same keyword
        total_matches = sum(text.count(keyword) for keyword in matches)
        frequency_bonus = min(total_matches * 0.1, 0.5)
        
        return base_score + frequency_bonus
    
    def _analyze_content_structure(self, contents: List[ContentNode]) -> ContentStructure:
        """Analyze the structure of content nodes."""
        
        structure = ContentStructure()
        prev_speaker = None
        
        def analyze_nodes(nodes: List[ContentNode]):
            nonlocal prev_speaker
            
            for node in nodes:
                structure.total_nodes += 1
                
                # Track content types
                if node.type not in structure.content_types:
                    structure.content_types.append(node.type)
                
                # Count headings
                if node.type.startswith("heading"):
                    structure.heading_count += 1
                
                # Track speaker changes
                if node.speaker_name:
                    if prev_speaker and node.speaker_name != prev_speaker:
                        structure.speaker_changes += 1
                    prev_speaker = node.speaker_name
                
                # Check for user speech
                if node.speaker_identifier == "user":
                    structure.has_user_speech = True
                
                # Recursively analyze children
                if node.children:
                    analyze_nodes(node.children)
        
        analyze_nodes(contents)
        
        return structure
    
    def _extract_speakers(self, contents: List[ContentNode]) -> List[str]:
        """Extract unique speakers from content nodes."""
        speakers = set()
        
        def extract_from_nodes(nodes: List[ContentNode]):
            for node in nodes:
                if node.speaker_name:
                    speakers.add(node.speaker_name)
                if node.children:
                    extract_from_nodes(node.children)
        
        extract_from_nodes(contents)
        return sorted(list(speakers))
    
    def _extract_text_from_contents(self, contents: List[ContentNode]) -> str:
        """Extract plain text from content nodes."""
        text_parts = []
        
        def extract_from_nodes(nodes: List[ContentNode]):
            for node in nodes:
                if node.content:
                    text_parts.append(node.content)
                if node.children:
                    extract_from_nodes(node.children)
        
        extract_from_nodes(contents)
        return " ".join(text_parts)
    
    def _format_content(
        self, 
        entry: LifelogEntry, 
        conversation_type: ConversationType,
        speakers: List[str],
        content_structure: ContentStructure
    ) -> str:
        """Format lifelog content for Memory Box storage."""
        
        lines = []
        
        # Title and metadata
        lines.append(f"# {entry.title}")
        lines.append("")
        
        # Metadata section
        lines.append("## Metadata")
        lines.append(f"**Date:** {entry.start_time.strftime('%Y-%m-%d %H:%M')}")
        lines.append(f"**Duration:** {entry.duration_minutes} minutes")
        lines.append(f"**Type:** {conversation_type.value}")
        
        if entry.is_starred:
            lines.append("**Status:** ⭐ STARRED")
        
        if speakers:
            lines.append(f"**Participants:** {', '.join(speakers)}")
        
        lines.append("")
        
        # Content section
        if entry.markdown and entry.markdown.strip():
            lines.append("## Content")
            lines.append("")
            lines.append(entry.markdown)
        elif entry.contents:
            lines.append("## Conversation")
            lines.append("")
            lines.extend(self._format_content_nodes(entry.contents))
        else:
            lines.append("## Content")
            lines.append("*No content available*")
        
        lines.append("")
        
        # Summary section for longer conversations
        if entry.duration_minutes >= 10 and content_structure.heading_count > 0:
            lines.append("## Key Points")
            key_points = self._extract_key_points(entry.contents)
            if key_points:
                for point in key_points[:5]:  # Limit to top 5 points
                    lines.append(f"- {point}")
                lines.append("")
        
        # Tags for searchability
        lines.append("---")
        lines.append("")
        tags = self._generate_tags(entry, conversation_type, speakers)
        lines.append(f"**Tags:** {', '.join(tags)}")
        
        return "\n".join(lines)
    
    def _format_content_nodes(self, contents: List[ContentNode]) -> List[str]:
        """Format content nodes into readable markdown."""
        lines = []
        
        def format_nodes(nodes: List[ContentNode], level: int = 0):
            for node in nodes:
                if not node.content.strip():
                    continue
                
                if node.type == "heading1":
                    lines.append(f"### {node.content}")
                elif node.type == "heading2":
                    lines.append(f"#### {node.content}")
                elif node.type == "heading3":
                    lines.append(f"##### {node.content}")
                elif node.type == "blockquote":
                    if node.speaker_name:
                        lines.append(f"**{node.speaker_name}:** {node.content}")
                    else:
                        lines.append(f"> {node.content}")
                else:
                    # Regular content
                    if node.speaker_name:
                        lines.append(f"**{node.speaker_name}:** {node.content}")
                    else:
                        lines.append(node.content)
                
                # Add timestamp if available
                if node.start_time:
                    timestamp = node.start_time.strftime("%H:%M")
                    lines[-1] += f" *({timestamp})*"
                
                lines.append("")
                
                # Process children with increased indentation
                if node.children:
                    format_nodes(node.children, level + 1)
        
        format_nodes(contents)
        return lines
    
    def _extract_key_points(self, contents: List[ContentNode]) -> List[str]:
        """Extract key points from content nodes."""
        key_points = []
        
        def extract_from_nodes(nodes: List[ContentNode]):
            for node in nodes:
                # Headings are usually key points
                if node.type.startswith("heading") and node.content.strip():
                    key_points.append(node.content.strip())
                
                # Long content blocks might contain key information
                elif (node.content and len(node.content) > 50 and 
                      any(keyword in node.content.lower() for keyword in 
                          ["important", "key", "main", "primary", "decision", "conclusion"])):
                    # Truncate long content
                    content = node.content.strip()
                    if len(content) > 100:
                        content = content[:97] + "..."
                    key_points.append(content)
                
                if node.children:
                    extract_from_nodes(node.children)
        
        extract_from_nodes(contents)
        return key_points
    
    def _generate_tags(
        self, 
        entry: LifelogEntry, 
        conversation_type: ConversationType,
        speakers: List[str]
    ) -> List[str]:
        """Generate searchable tags for the memory."""
        tags = [
            "limitless",
            "pendant",
            "lifelog",
            conversation_type.value.lower()
        ]
        
        # Add date-based tags
        tags.append(entry.start_time.strftime("%B-%Y").lower())
        tags.append(entry.start_time.strftime("%Y").lower())
        
        # Add day of week
        tags.append(entry.start_time.strftime("%A").lower())
        
        # Add time of day
        hour = entry.start_time.hour
        if 5 <= hour < 12:
            tags.append("morning")
        elif 12 <= hour < 17:
            tags.append("afternoon")
        elif 17 <= hour < 21:
            tags.append("evening")
        else:
            tags.append("night")
        
        # Add duration-based tags
        if entry.duration_minutes < 5:
            tags.append("short")
        elif entry.duration_minutes > 30:
            tags.append("long")
        
        # Add speaker count
        if len(speakers) == 0:
            tags.append("monologue")
        elif len(speakers) == 2:
            tags.append("dialogue")
        elif len(speakers) > 2:
            tags.append("group")
        
        # Add starred tag
        if entry.is_starred:
            tags.append("starred")
            tags.append("important")
        
        return tags
    
    def get_processing_stats(self) -> Dict[str, Any]:
        """Get content processing statistics."""
        return {
            "processor_version": "1.0.0",
            "supported_content_types": [
                "heading1", "heading2", "heading3", 
                "blockquote", "paragraph"
            ],
            "conversation_types": [t.value for t in ConversationType],
            "keyword_categories": {
                "meeting": len(self.meeting_keywords),
                "technical": len(self.technical_keywords),
                "decision": len(self.decision_keywords),
                "personal": len(self.personal_keywords)
            }
        }
