"""
Scheduler - APScheduler-based job scheduler for automated bookings
Handles scheduled bookings execution and confirmation management
"""

import logging
from datetime import datetime
from typing import Callable, Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)


class BookingScheduler:
    """
    Manages automated scheduling for:
    - Executing scheduled bookings at midnight 2 days before
    - Sending confirmation requests 5 hours before courses
    - Auto-cancelling unconfirmed bookings 1 hour before courses
    """

    def __init__(self, config: dict = None):
        self.scheduler = AsyncIOScheduler()
        self.is_running = False

        # Load timing configuration with defaults
        scheduling = config.get('scheduling', {}) if config else {}
        self.booking_executor_hour = scheduling.get('booking_executor_hour', 0)
        self.booking_executor_minute = scheduling.get('booking_executor_minute', 30)
        self.periodic_processor_hour = scheduling.get('periodic_processor_hour', 0)
        self.periodic_processor_minute = scheduling.get('periodic_processor_minute', 0)

    def start(self):
        """Start the scheduler"""
        if not self.is_running:
            self.scheduler.start()
            self.is_running = True
            logger.info("BookingScheduler started")

    def shutdown(self):
        """Shutdown the scheduler"""
        if self.is_running:
            self.scheduler.shutdown()
            self.is_running = False
            logger.info("BookingScheduler stopped")

    # ==================== SCHEDULED BOOKING JOBS ====================

    def add_midnight_booking_executor(self, callback: Callable):
        """
        Add job to execute pending scheduled bookings
        Runs at configured time (default: midnight) to execute bookings 2 days before courses

        Args:
            callback: Async function to call when executing bookings
        """
        self.scheduler.add_job(
            callback,
            trigger=CronTrigger(hour=self.booking_executor_hour, minute=self.booking_executor_minute),
            id='booking_executor',
            name='Execute scheduled bookings',
            replace_existing=True
        )
        logger.info(f"Added booking executor job (daily at {self.booking_executor_hour:02d}:{self.booking_executor_minute:02d})")

    # ==================== CONFIRMATION JOBS ====================

    def add_confirmation_checker(self, callback: Callable):
        """
        Add job to check for confirmations that need to be sent
        Runs every 10 minutes

        Args:
            callback: Async function to call when checking confirmations
        """
        self.scheduler.add_job(
            callback,
            trigger=IntervalTrigger(minutes=10),
            id='confirmation_checker',
            name='Check pending confirmations',
            replace_existing=True
        )
        logger.info("Added confirmation checker job (every 10 minutes)")

    def add_auto_cancel_checker(self, callback: Callable):
        """
        Add job to auto-cancel unconfirmed bookings
        Runs every 10 minutes

        Args:
            callback: Async function to call when checking for cancellations
        """
        self.scheduler.add_job(
            callback,
            trigger=IntervalTrigger(minutes=10),
            id='auto_cancel_checker',
            name='Auto-cancel unconfirmed bookings',
            replace_existing=True
        )
        logger.info("Added auto-cancel checker job (every 10 minutes)")

    # ==================== PERIODIC BOOKING JOBS ====================

    def add_periodic_booking_processor(self, callback: Callable):
        """
        Add job to process periodic bookings and create scheduled bookings
        Runs daily at configured time

        Args:
            callback: Async function to call when processing periodic bookings
        """
        self.scheduler.add_job(
            callback,
            trigger=CronTrigger(hour=self.periodic_processor_hour, minute=self.periodic_processor_minute),
            id='periodic_booking_processor',
            name='Process periodic bookings',
            replace_existing=True
        )
        logger.info(f"Added periodic booking processor job (daily at {self.periodic_processor_hour:02d}:{self.periodic_processor_minute:02d})")

    # ==================== JOB MANAGEMENT ====================

    def remove_job(self, job_id: str):
        """Remove a specific job"""
        try:
            self.scheduler.remove_job(job_id)
            logger.info(f"Removed job: {job_id}")
        except Exception as e:
            logger.error(f"Failed to remove job {job_id}: {e}")

    def list_jobs(self) -> list:
        """List all scheduled jobs"""
        jobs = self.scheduler.get_jobs()
        return [
            {
                'id': job.id,
                'name': job.name,
                'next_run': job.next_run_time.strftime('%Y-%m-%d %H:%M:%S') if job.next_run_time else None
            }
            for job in jobs
        ]

    def pause_job(self, job_id: str):
        """Pause a specific job"""
        try:
            self.scheduler.pause_job(job_id)
            logger.info(f"Paused job: {job_id}")
        except Exception as e:
            logger.error(f"Failed to pause job {job_id}: {e}")

    def resume_job(self, job_id: str):
        """Resume a specific job"""
        try:
            self.scheduler.resume_job(job_id)
            logger.info(f"Resumed job: {job_id}")
        except Exception as e:
            logger.error(f"Failed to resume job {job_id}: {e}")


if __name__ == '__main__':
    # Test scheduler
    import asyncio

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    print("=== Scheduler Test ===\n")

    async def test_callback():
        """Test callback function"""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Test callback executed!")

    async def test_scheduler():
        """Test the scheduler"""
        scheduler = BookingScheduler()

        print("Starting scheduler...")
        scheduler.start()

        # Add test job
        print("Adding test job (runs every 3 seconds)...")
        scheduler.scheduler.add_job(
            test_callback,
            trigger=IntervalTrigger(seconds=3),
            id='test_job',
            name='Test Job'
        )

        # List jobs
        print("\nScheduled jobs:")
        for job in scheduler.list_jobs():
            print(f"  - {job['name']} (ID: {job['id']})")
            print(f"    Next run: {job['next_run']}")

        print("\nScheduler running. Press Ctrl+C to stop...")
        print("(Job will execute every 3 seconds)\n")

        try:
            # Keep running for 15 seconds
            await asyncio.sleep(15)
        except KeyboardInterrupt:
            print("\nInterrupted by user")

        print("\nStopping scheduler...")
        scheduler.shutdown()

        print("✅ Scheduler test completed!")

    asyncio.run(test_scheduler())
