#!/usr/bin/env python3
"""
Standalone health check script for Docker health checks.

This script can be run independently to check the health of the sync agent.
"""

import asyncio
import sys
from pathlib import Path

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.health import standalone_health_check

if __name__ == "__main__":
    asyncio.run(standalone_health_check())
