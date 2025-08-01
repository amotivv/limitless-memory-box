"""
Limitless to Memory Box Sync Agent - Main Entry Point

A production-ready Python application that automatically synchronizes
lifelog data from the Limitless Pendant to Memory Box.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.config import load_config, validate_required_config, create_directories
from src.sync_agent import create_sync_agent


def setup_logging(config) -> None:
    """Setup structured logging configuration."""
    
    # Create log directory
    log_dir = Path(config.log_path)
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Create handlers
    console_handler = logging.StreamHandler(sys.stdout)
    file_handler = logging.FileHandler(log_dir / "limitless_sync.log")
    error_handler = logging.FileHandler(log_dir / "limitless_sync_errors.log")
    error_handler.setLevel(logging.ERROR)
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, config.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[console_handler, file_handler, error_handler]
    )
    
    # Set specific logger levels
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.INFO)
    
    logger = logging.getLogger(__name__)
    logger.info("Logging configured successfully")


async def main():
    """Main entry point for the sync agent."""
    
    logger = None
    
    try:
        # Load and validate configuration
        print("Loading configuration...")
        config = load_config()
        validate_required_config(config)
        create_directories(config)
        
        # Setup logging
        setup_logging(config)
        logger = logging.getLogger(__name__)
        
        logger.info("=" * 60)
        logger.info("Limitless to Memory Box Sync Agent Starting")
        logger.info("=" * 60)
        
        # Log configuration (without sensitive data)
        logger.info(f"Configuration loaded:")
        logger.info(f"  - Limitless API URL: {config.limitless_api_url}")
        logger.info(f"  - Memory Box API URL: {config.memorybox_api_url}")
        logger.info(f"  - Memory Box Bucket: {config.memorybox_bucket}")
        logger.info(f"  - Sync Interval: {config.sync_interval_minutes} minutes")
        logger.info(f"  - Timezone: {config.timezone}")
        logger.info(f"  - Database Path: {config.database_path}")
        logger.info(f"  - Log Level: {config.log_level}")
        logger.info(f"  - Health Check Port: {config.health_check_port}")
        
        # Create and start sync agent
        logger.info("Creating sync agent...")
        agent = await create_sync_agent(config)
        
        logger.info("Starting sync agent...")
        await agent.start()
        
    except KeyboardInterrupt:
        if logger:
            logger.info("Received keyboard interrupt, shutting down...")
        else:
            print("Received keyboard interrupt, shutting down...")
        
    except Exception as e:
        if logger:
            logger.error(f"Fatal error: {e}", exc_info=True)
        else:
            print(f"Fatal error: {e}")
        sys.exit(1)
    
    finally:
        if logger:
            logger.info("Sync agent shutdown complete")
            logger.info("=" * 60)


if __name__ == "__main__":
    # Check Python version
    if sys.version_info < (3, 8):
        print("Error: Python 3.8 or higher is required")
        sys.exit(1)
    
    # Run the main function
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown complete.")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)
