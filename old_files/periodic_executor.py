#!/usr/bin/env python3
"""
Periodic Booking Executor - Handles periodic bookings with confirmations
Runs continuously, checking for upcoming bookings and sending confirmations
"""

import asyncio
import logging
import json
from database import Database
from datetime import datetime, timedelta
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class PeriodicExecutor:
    def __init__(self, config_path='../config.json'):
        with open(config_path, 'r') as f:
            self.config = json.load(f)

        self.db = Database()
        self.bot = Bot(token=self.config['telegram']['bot_token'])
        self.running = True

    async def run_executor(self):
        """Main executor loop"""
        while self.running:
            try:
                # Check for upcoming periodic bookings
                await self.check_periodic_bookings()

                # Check for expired confirmations
                await self.check_expired_confirmations()

                # Wait before next check (check every minute)
                await asyncio.sleep(60)

            except Exception as e:
                logger.error(f"Error in executor loop: {e}")
                await asyncio.sleep(60)

    async def check_periodic_bookings(self):
        """Check if any periodic booking needs confirmation"""
        now = datetime.now()
        current_day = now.weekday()  # 0 = Monday, 6 = Sunday
        current_time = now.strftime('%H:%M')

        # Get all active periodic bookings
        periodic_bookings = self.db.get_all_active_periodic_bookings()

        for booking in periodic_bookings:
            # Check if booking is for today
            if booking['day_of_week'] != current_day:
                continue

            # Parse booking time
            booking_time = datetime.strptime(booking['time_slot'], '%H:%M').time()
            booking_datetime = datetime.combine(now.date(), booking_time)

            # Calculate time until booking
            time_until = (booking_datetime - now).total_seconds() / 60  # minutes

            # If booking is approximately 1 hour away (58-62 minutes)
            if 58 <= time_until <= 62:
                await self.schedule_confirmation(booking, booking_datetime)

    async def schedule_confirmation(self, booking: dict, scheduled_for: datetime):
        """Send confirmation request for a periodic booking"""
        # Check if confirmation already exists
        confirmations = self.db.get_pending_confirmations(booking['user_id'])

        # Check if we already sent confirmation for this time slot today
        for conf in confirmations:
            conf_scheduled = datetime.fromisoformat(conf['scheduled_for'])
            if conf_scheduled.date() == scheduled_for.date() and \
               conf['periodic_booking_id'] == booking['id']:
                logger.info(f"Confirmation already sent for booking {booking['id']}")
                return

        # Create pending confirmation
        expires_at = scheduled_for - timedelta(minutes=5)  # Must confirm 5 min before

        confirmation_id = self.db.add_pending_confirmation(
            user_id=booking['user_id'],
            periodic_booking_id=booking['id'],
            scheduled_for=scheduled_for,
            expires_at=expires_at
        )

        # Send confirmation message
        await self.send_confirmation_request(booking, confirmation_id, scheduled_for, expires_at)

    async def send_confirmation_request(self, booking: dict, confirmation_id: int,
                                       scheduled_for: datetime, expires_at: datetime):
        """Send confirmation request to user via Telegram"""
        days = ['Lunedì', 'Martedì', 'Mercoledì', 'Giovedì', 'Venerdì', 'Sabato', 'Domenica']
        day_name = days[booking['day_of_week']]

        keyboard = [
            [InlineKeyboardButton("✅ Conferma", callback_data=f'confirm_{confirmation_id}')],
            [InlineKeyboardButton("❌ Salta questa volta", callback_data=f'skip_{confirmation_id}')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        message = (
            f"⏰ Conferma Prenotazione Periodica\n\n"
            f"📅 {day_name} {scheduled_for.strftime('%d/%m/%Y')}\n"
            f"🕐 Orario: {booking['time_slot']}\n"
            f"📍 Sede: {booking['location']}\n"
        )

        if booking['course_name']:
            message += f"🏃 Corso: {booking['course_name']}\n"

        if booking.get('name'):
            message += f"\n💾 Nome: {booking['name']}\n"

        message += f"\n⚠️ Conferma entro le {expires_at.strftime('%H:%M')} o verrà saltata."

        try:
            await self.bot.send_message(
                chat_id=booking['user_id'],
                text=message,
                reply_markup=reply_markup
            )
            logger.info(f"Sent confirmation request {confirmation_id} to user {booking['user_id']}")
        except Exception as e:
            logger.error(f"Failed to send confirmation: {e}")

    async def check_expired_confirmations(self):
        """Check for and handle expired confirmations"""
        expired = self.db.get_expired_confirmations()

        for confirmation in expired:
            logger.info(f"Confirmation {confirmation['id']} expired without confirmation")

            # Delete the expired confirmation
            self.db.delete_confirmation(confirmation['id'])

            # Notify user
            try:
                await self.bot.send_message(
                    chat_id=confirmation['user_id'],
                    text=f"⏰ Prenotazione periodica saltata (non confermata in tempo)\n"
                         f"Orario: {datetime.fromisoformat(confirmation['scheduled_for']).strftime('%d/%m/%Y %H:%M')}"
                )
            except Exception as e:
                logger.error(f"Failed to notify user of expiration: {e}")

    async def run(self):
        """Run the periodic executor"""
        logger.info("Periodic executor started")
        try:
            await self.run_executor()
        except KeyboardInterrupt:
            logger.info("Periodic executor stopped by user")
            self.running = False
        except Exception as e:
            logger.error(f"Periodic executor error: {e}")
            raise


async def main():
    executor = PeriodicExecutor()
    await executor.run()


if __name__ == '__main__':
    asyncio.run(main())
