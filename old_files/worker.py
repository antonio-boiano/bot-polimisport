#!/usr/bin/env python3
"""
Worker Script - Processes booking actions from the queue
Runs continuously, checking for pending actions and executing them
"""

import asyncio
import logging
import json
import time
from database import Database
from booking import PolimisportBooker
from datetime import datetime
from telegram import Bot

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class BookingWorker:
    def __init__(self, config_path='config.json'):
        with open(config_path, 'r') as f:
            self.config = json.load(f)

        self.db = Database()
        self.booker = PolimisportBooker(self.config)
        self.bot = Bot(token=self.config['telegram']['bot_token'])
        self.running = True

    async def process_actions(self):
        """Process pending actions from the queue"""
        while self.running:
            try:
                # Get pending actions
                actions = self.db.get_pending_actions()

                if not actions:
                    # No actions, wait before checking again
                    await asyncio.sleep(5)
                    continue

                for action in actions:
                    await self.process_action(action)

                # Small delay between batches
                await asyncio.sleep(2)

            except Exception as e:
                logger.error(f"Error in process_actions loop: {e}")
                await asyncio.sleep(10)

    async def process_action(self, action: dict):
        """Process a single action"""
        action_id = action['id']
        action_type = action['action_type']
        user_id = action['user_id']

        logger.info(f"Processing action {action_id}: {action_type}")

        # Mark as processing
        self.db.update_action_status(action_id, 'processing')

        try:
            if action_type == 'book':
                result = await self.execute_booking(action)
            elif action_type == 'cancel':
                result = await self.execute_cancellation(action)
            elif action_type == 'check':
                result = await self.execute_check(action)
            else:
                raise ValueError(f"Unknown action type: {action_type}")

            # Mark as completed
            self.db.update_action_status(action_id, 'completed', result=json.dumps(result))

            # Notify user
            await self.notify_user_success(user_id, action_type, result)

            logger.info(f"Action {action_id} completed successfully")

        except Exception as e:
            logger.error(f"Action {action_id} failed: {e}")

            # Mark as failed
            self.db.update_action_status(action_id, 'failed', error=str(e))

            # Notify user of failure
            await self.notify_user_failure(user_id, action_type, str(e))

    async def execute_booking(self, action: dict) -> dict:
        """Execute a booking action"""
        logger.info(f"Executing booking: {action['location']} - {action['course_name']}")

        result = await self.booker.make_booking(
            location=action['location'],
            date=action['date'],
            time_slot=action['time_slot'],
            headless=True
        )

        # Add to user bookings
        self.db.add_user_booking(
            user_id=action['user_id'],
            booking={
                'booking_id': result['id'],
                'course_name': action['course_name'],
                'location': action['location'],
                'booking_date': action['date'],
                'booking_time': action['time_slot']
            }
        )

        return result

    async def execute_cancellation(self, action: dict) -> dict:
        """Execute a cancellation action"""
        logger.info(f"Executing cancellation: {action['booking_id']}")

        success = await self.booker.cancel_booking(action['booking_id'])

        if success:
            # Update booking status in database
            self.db.update_booking_status(action['booking_id'], 'cancelled')

        return {'success': success, 'booking_id': action['booking_id']}

    async def execute_check(self, action: dict) -> dict:
        """Execute a check bookings action"""
        logger.info(f"Executing check bookings for user {action['user_id']}")

        bookings = await self.booker.get_bookings()
        return {'bookings': bookings}

    async def notify_user_success(self, user_id: int, action_type: str, result: dict):
        """Notify user of successful action"""
        messages = {
            'book': f"✅ Prenotazione completata!\n\n"
                   f"📍 {result.get('course', 'N/A')}\n"
                   f"📅 {result.get('datetime', 'N/A')}\n"
                   f"🏢 {result.get('location', 'N/A')}",
            'cancel': f"✅ Cancellazione completata!\n\n"
                     f"ID: {result.get('booking_id', 'N/A')}",
            'check': f"✅ Check completato!\n\n"
                    f"Trovate {len(result.get('bookings', []))} prenotazioni."
        }

        message = messages.get(action_type, f"✅ Azione {action_type} completata!")

        try:
            await self.bot.send_message(chat_id=user_id, text=message)
        except Exception as e:
            logger.error(f"Failed to notify user {user_id}: {e}")

    async def notify_user_failure(self, user_id: int, action_type: str, error: str):
        """Notify user of failed action"""
        message = f"❌ Azione {action_type} fallita!\n\nErrore: {error}"

        try:
            await self.bot.send_message(chat_id=user_id, text=message)
        except Exception as e:
            logger.error(f"Failed to notify user {user_id}: {e}")

    async def run(self):
        """Run the worker"""
        logger.info("Worker started, processing actions...")
        try:
            await self.process_actions()
        except KeyboardInterrupt:
            logger.info("Worker stopped by user")
            self.running = False
        except Exception as e:
            logger.error(f"Worker error: {e}")
            raise


async def main():
    worker = BookingWorker()
    await worker.run()


if __name__ == '__main__':
    asyncio.run(main())
