# Limitless to Memory Box Sync Agent - Project Brief

## Project Overview

The Limitless to Memory Box Sync Agent is a Python-based application that continuously synchronizes lifelog data from the Limitless Pendant to a Memory Box instance, providing seamless integration between personal conversation capture and semantic memory storage.

## Core Requirements

### Primary Objectives
1. **Automated Sync**: Continuously sync new lifelog entries from Limitless API to Memory Box
2. **Incremental Processing**: Only process new/updated entries to prevent duplicates
3. **Semantic Enhancement**: Intelligently categorize and format conversations for optimal searchability
4. **Production Ready**: Deploy as a containerized service with monitoring and alerting

### Key Features
- **Incremental Sync Strategy**: Track sync state using SQLite database
- **Smart Categorization**: Automatically classify conversations (MEETING, TECHNICAL, DECISION, etc.)
- **Rich Metadata**: Preserve speaker information, timestamps, and conversation structure
- **Error Resilience**: Comprehensive error handling with email notifications
- **Docker Deployment**: Container-ready for local and cloud deployment

## Technical Constraints

### API Limitations
- **Limitless API**: 180 requests/minute rate limit
- **Memory Box API**: Bearer token authentication required
- **Processing Delays**: Memory Box requires polling for processing completion

### Deployment Requirements
- **Docker**: Must run in containerized environment
- **Cloud Ready**: Deployable to cloud VMs
- **Persistent Storage**: SQLite database for sync state
- **Monitoring**: Email alerts via Mailgun for operational awareness

## Success Criteria

1. **Reliability**: 99%+ sync success rate for new lifelog entries
2. **Performance**: Process new entries within 5 minutes of creation
3. **Data Integrity**: Zero duplicate memories in Memory Box
4. **Operational**: Automated alerts for failures, daily summary reports
5. **Maintainability**: Clear logging, health checks, and monitoring

## Scope Boundaries

### In Scope
- Sync lifelog entries from Limitless to Memory Box
- Intelligent content categorization and formatting
- Duplicate prevention and incremental sync
- Email notifications and monitoring
- Docker containerization and deployment

### Out of Scope
- Bi-directional sync (Memory Box to Limitless)
- Real-time sync (acceptable delay: 30 minutes)
- Custom Memory Box instance management
- Advanced analytics or reporting beyond basic stats

## Stakeholders

- **Primary User**: Individual with Limitless Pendant seeking centralized memory storage
- **Technical Owner**: Developer responsible for deployment and maintenance
- **Dependencies**: Limitless API, Memory Box API, Mailgun email service

## Timeline

- **Phase 1**: Core sync functionality (Week 1)
- **Phase 2**: Docker containerization and deployment (Week 2)
- **Phase 3**: Monitoring, alerts, and production hardening (Week 3)
- **Phase 4**: Documentation and handoff (Week 4)
