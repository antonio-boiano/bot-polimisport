#!/usr/bin/env python3
"""
Periodic Booking Scheduler with Confirmation
Manages periodic bookings and auto-cancellation
"""

import logging
import json
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import os

logger = logging.getLogger(__name__)


class BookingScheduler:
    def __init__(self, config: dict, booker):
        """Initialize scheduler with configuration and booker instance"""
        self.config = config
        self.booker = booker
        self.scheduler = AsyncIOScheduler()
        self.periodic_bookings_file = 'periodic_bookings.json'
        self.pending_confirmations_file = 'pending_confirmations.json'
        self.application = None  # Will be set when bot starts

        # Load existing periodic bookings
        self.periodic_bookings = self._load_periodic_bookings()
        self.pending_confirmations = self._load_pending_confirmations()

    def _load_periodic_bookings(self) -> List[Dict]:
        """Load periodic bookings from file"""
        if os.path.exists(self.periodic_bookings_file):
            try:
                with open(self.periodic_bookings_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading periodic bookings: {e}")
                return []
        return []

    def _save_periodic_bookings(self):
        """Save periodic bookings to file"""
        try:
            with open(self.periodic_bookings_file, 'w') as f:
                json.dump(self.periodic_bookings, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving periodic bookings: {e}")

    def _load_pending_confirmations(self) -> Dict:
        """Load pending confirmations from file"""
        if os.path.exists(self.pending_confirmations_file):
            try:
                with open(self.pending_confirmations_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading pending confirmations: {e}")
                return {}
        return {}

    def _save_pending_confirmations(self):
        """Save pending confirmations to file"""
        try:
            with open(self.pending_confirmations_file, 'w') as f:
                json.dump(self.pending_confirmations, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving pending confirmations: {e}")

    def add_periodic_booking(self, user_id: int, booking_config: Dict) -> str:
        """
        Add a new periodic booking

        Args:
            user_id: Telegram user ID
            booking_config: Dict containing booking details
                - day_of_week: 0-6 (Monday-Sunday)
                - time: Time string (HH:MM)
                - location: Location identifier
                - course: Course name
                - requires_confirmation: Boolean

        Returns:
            Booking ID
        """
        booking_id = f"periodic_{int(datetime.now().timestamp())}_{user_id}"

        periodic_booking = {
            'id': booking_id,
            'user_id': user_id,
            'day_of_week': booking_config['day_of_week'],
            'time': booking_config['time'],
            'location': booking_config['location'],
            'course': booking_config['course'],
            'requires_confirmation': booking_config.get('requires_confirmation', True),
            'active': True,
            'created_at': datetime.now().isoformat()
        }

        self.periodic_bookings.append(periodic_booking)
        self._save_periodic_bookings()

        # Schedule the periodic booking
        self._schedule_periodic_booking(periodic_booking)

        logger.info(f"Added periodic booking: {booking_id}")
        return booking_id

    def remove_periodic_booking(self, booking_id: str) -> bool:
        """Remove a periodic booking"""
        for i, booking in enumerate(self.periodic_bookings):
            if booking['id'] == booking_id:
                self.periodic_bookings.pop(i)
                self._save_periodic_bookings()

                # Remove from scheduler
                try:
                    self.scheduler.remove_job(f"periodic_{booking_id}")
                except:
                    pass

                logger.info(f"Removed periodic booking: {booking_id}")
                return True

        return False

    def _schedule_periodic_booking(self, booking: Dict):
        """Schedule a periodic booking using cron"""
        try:
            # Create cron trigger for the specified day and time
            hour, minute = booking['time'].split(':')

            trigger = CronTrigger(
                day_of_week=booking['day_of_week'],
                hour=int(hour),
                minute=int(minute)
            )

            # Schedule the booking task
            self.scheduler.add_job(
                self._execute_periodic_booking,
                trigger=trigger,
                args=[booking],
                id=f"periodic_{booking['id']}",
                replace_existing=True
            )

            logger.info(f"Scheduled periodic booking {booking['id']} for day {booking['day_of_week']} at {booking['time']}")

        except Exception as e:
            logger.error(f"Error scheduling periodic booking: {e}")

    async def _execute_periodic_booking(self, booking: Dict):
        """Execute a periodic booking"""
        try:
            logger.info(f"Executing periodic booking: {booking['id']}")

            if booking['requires_confirmation']:
                # Create pending confirmation
                booking_instance_id = f"{booking['id']}_{int(datetime.now().timestamp())}"

                booking_info = {
                    'id': booking_instance_id,
                    'periodic_booking_id': booking['id'],
                    'user_id': booking['user_id'],
                    'location': booking['location'],
                    'course': booking['course'],
                    'datetime': datetime.now().isoformat(),
                    'confirmed': False,
                    'created_at': datetime.now().isoformat()
                }

                self.pending_confirmations[booking_instance_id] = booking_info
                self._save_pending_confirmations()

                # Send confirmation request to user
                await self._send_confirmation_request(booking_info)

                # Schedule auto-cancellation in 1 hour
                self.scheduler.add_job(
                    self._auto_cancel_unconfirmed,
                    'date',
                    run_date=datetime.now() + timedelta(hours=1),
                    args=[booking_instance_id],
                    id=f"autocancel_{booking_instance_id}"
                )

            else:
                # Make booking immediately without confirmation
                await self.booker.make_booking(
                    location=booking['location'],
                    time_slot=booking.get('time_slot')
                )

                # Notify user
                if self.application:
                    await self.application.bot.send_message(
                        chat_id=booking['user_id'],
                        text=f"✅ Prenotazione automatica effettuata:\n"
                             f"Corso: {booking['course']}\n"
                             f"Sede: {booking['location']}"
                    )

        except Exception as e:
            logger.error(f"Error executing periodic booking: {e}")

            # Notify user of error
            if self.application:
                await self.application.bot.send_message(
                    chat_id=booking['user_id'],
                    text=f"❌ Errore nella prenotazione automatica:\n{str(e)}"
                )

    async def _send_confirmation_request(self, booking_info: Dict):
        """Send confirmation request to user via Telegram"""
        if not self.application:
            logger.error("Application not set, cannot send confirmation request")
            return

        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        keyboard = [
            [InlineKeyboardButton("✅ Conferma", callback_data=f'confirm_periodic_{booking_info["id"]}')],
            [InlineKeyboardButton("❌ Annulla", callback_data=f'cancel_periodic_{booking_info["id"]}')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        message = (
            f"⏰ Conferma Prenotazione Periodica\n\n"
            f"Corso: {booking_info['course']}\n"
            f"Sede: {booking_info['location']}\n"
            f"Data/Ora: {datetime.fromisoformat(booking_info['datetime']).strftime('%Y-%m-%d %H:%M')}\n\n"
            f"⚠️ Confermare entro 1 ora o verrà cancellata automaticamente."
        )

        try:
            await self.application.bot.send_message(
                chat_id=booking_info['user_id'],
                text=message,
                reply_markup=reply_markup
            )
            logger.info(f"Sent confirmation request for {booking_info['id']}")
        except Exception as e:
            logger.error(f"Error sending confirmation request: {e}")

    async def confirm_booking(self, booking_instance_id: str) -> bool:
        """Confirm a pending booking"""
        if booking_instance_id not in self.pending_confirmations:
            logger.warning(f"Booking {booking_instance_id} not found in pending confirmations")
            return False

        booking_info = self.pending_confirmations[booking_instance_id]

        try:
            # Make the booking
            await self.booker.make_booking(
                location=booking_info['location'],
                time_slot=booking_info.get('time_slot')
            )

            # Mark as confirmed
            booking_info['confirmed'] = True
            self._save_pending_confirmations()

            # Remove auto-cancel job
            try:
                self.scheduler.remove_job(f"autocancel_{booking_instance_id}")
            except:
                pass

            # Clean up pending confirmation
            del self.pending_confirmations[booking_instance_id]
            self._save_pending_confirmations()

            logger.info(f"Confirmed booking {booking_instance_id}")
            return True

        except Exception as e:
            logger.error(f"Error confirming booking: {e}")
            return False

    async def _auto_cancel_unconfirmed(self, booking_instance_id: str):
        """Automatically cancel unconfirmed booking after 1 hour"""
        if booking_instance_id not in self.pending_confirmations:
            return

        booking_info = self.pending_confirmations[booking_instance_id]

        if not booking_info['confirmed']:
            logger.info(f"Auto-cancelling unconfirmed booking {booking_instance_id}")

            # Remove from pending
            del self.pending_confirmations[booking_instance_id]
            self._save_pending_confirmations()

            # Notify user
            if self.application:
                await self.application.bot.send_message(
                    chat_id=booking_info['user_id'],
                    text=f"⏰ Prenotazione automaticamente cancellata (non confermata):\n"
                         f"Corso: {booking_info['course']}\n"
                         f"Sede: {booking_info['location']}"
                )

    def start(self, application):
        """Start the scheduler"""
        self.application = application

        # Reschedule all active periodic bookings
        for booking in self.periodic_bookings:
            if booking.get('active', True):
                self._schedule_periodic_booking(booking)

        # Start the scheduler
        self.scheduler.start()
        logger.info("Scheduler started")

    def stop(self):
        """Stop the scheduler"""
        self.scheduler.shutdown()
        logger.info("Scheduler stopped")

    def get_periodic_bookings(self, user_id: int) -> List[Dict]:
        """Get all periodic bookings for a user"""
        return [b for b in self.periodic_bookings if b['user_id'] == user_id and b.get('active', True)]

    def get_pending_confirmations(self, user_id: int) -> List[Dict]:
        """Get all pending confirmations for a user"""
        return [b for b in self.pending_confirmations.values() if b['user_id'] == user_id and not b['confirmed']]
