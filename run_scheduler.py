#!/usr/bin/env python3
"""
Standalone Lesson Reminder Scheduler Runner
Runs the scheduler in a separate process/container
"""
import logging
import time
import sys
import os

# Setup logging before any imports
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Import after logging setup
from src.services.lesson_reminder_scheduler import LessonReminderScheduler
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def main():
    """Main scheduler runner"""
    logger.info("=" * 80)
    logger.info("🚀 STARTING LESSON REMINDER SCHEDULER")
    logger.info("=" * 80)
    
    # Check configuration
    resend_api_key = os.getenv('RESEND_API_KEY')
    postgres_url = os.getenv('POSTGRES_URL')
    
    if not resend_api_key:
        logger.error("❌ RESEND_API_KEY not configured!")
        logger.error("   Scheduler cannot send emails without API key")
        sys.exit(1)
    
    if not postgres_url:
        logger.error("❌ POSTGRES_URL not configured!")
        logger.error("   Scheduler cannot access database")
        sys.exit(1)
    
    logger.info(f"✅ Configuration validated")
    logger.info(f"   RESEND_API_KEY: {'*' * 10}{resend_api_key[-6:]}")
    logger.info(f"   POSTGRES_URL: {postgres_url.split('@')[0].split(':')[0]}://***")
    logger.info(f"   EMAIL_SENDER: {os.getenv('EMAIL_SENDER', 'noreply@mail.mastereducation.kz')}")
    logger.info(f"   EMAIL_SENDER_NAME: {os.getenv('EMAIL_SENDER_NAME', 'MasterED Platform')}")
    
    # Initialize scheduler
    logger.info("")
    logger.info("🔧 Initializing scheduler...")
    scheduler = LessonReminderScheduler(check_interval=60)  # Check every minute
    
    # Start scheduler
    scheduler.start()
    logger.info("✅ Scheduler started successfully!")
    logger.info("")
    logger.info("📋 Scheduler Configuration:")
    logger.info(f"   Check interval: 60 seconds")
    logger.info(f"   Reminder window: 28-32 minutes before lesson")
    logger.info(f"   Timezone: UTC (converts to Kazakhstan time in emails)")
    logger.info("")
    logger.info("🔄 Scheduler is now running... (Press Ctrl+C to stop)")
    logger.info("=" * 80)
    
    try:
        # Keep the process running
        while True:
            time.sleep(60)
            logger.debug("🔄 Scheduler heartbeat...")
    except KeyboardInterrupt:
        logger.info("")
        logger.info("⏹️  Received stop signal")
        scheduler.stop()
        logger.info("✅ Scheduler stopped gracefully")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Scheduler crashed: {e}", exc_info=True)
        scheduler.stop()
        sys.exit(1)


if __name__ == "__main__":
    main()
