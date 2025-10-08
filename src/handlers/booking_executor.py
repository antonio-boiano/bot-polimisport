"""
Booking Executor - Executes scheduled bookings and manages confirmations
Connects scheduler with booking service and browser automation
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from ..utils import Database
from ..resources import SessionManager
from .booking_handler import BookingHandler
from .booking_service import BookingService

logger = logging.getLogger(__name__)


class BookingExecutor:
    """
    Executes bookings and manages confirmations
    Works with scheduler to automate booking operations
    """

    def __init__(
        self,
        db: Database,
        session_manager: Optional[SessionManager] = None,
        telegram_app = None
    ):
        self.db = db
        self.session_manager = session_manager
        self.telegram_app = telegram_app
        self.booking_service = BookingService(db)
        self.booking_handler = None

        if session_manager:
            self.booking_handler = BookingHandler(db, session_manager)

    async def _send_notification_with_menu(self, chat_id: int, message: str):
        """Send notification and main menu"""
        if not self.telegram_app:
            return

        try:
            # Send notification
            await self.telegram_app.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode='Markdown'
            )

            # Send main menu
            keyboard = [
                [InlineKeyboardButton("📚 Visualizza Corsi", callback_data="menu_all_courses")],
                [InlineKeyboardButton("🎯 Prenota corso", callback_data="menu_book")],
                [InlineKeyboardButton("📅 Le mie prenotazioni", callback_data="menu_bookings")],
                [InlineKeyboardButton("📆 Gestisci pianificazione", callback_data="menu_scheduling")],
                [InlineKeyboardButton("🔄 Aggiorna database", callback_data="action_refresh")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await self.telegram_app.bot.send_message(
                chat_id=chat_id,
                text="🏃 *Polimisport Bot*\n\nCosa vuoi fare?",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error sending notification with menu: {e}")

    # ==================== SCHEDULED BOOKING EXECUTION ====================

    async def execute_pending_scheduled_bookings(self):
        """
        Execute all pending scheduled bookings that are ready
        Called by scheduler daily at 1:00 AM
        """
        logger.info("Checking for pending scheduled bookings...")

        pending = self.db.get_pending_scheduled_bookings()

        if not pending:
            logger.info("No pending scheduled bookings")
            return

        logger.info(f"Found {len(pending)} pending scheduled bookings")

        # Ensure we have a session
        if not self.session_manager:
            logger.error("No session manager available")
            return

        for booking in pending:
            try:
                await self._execute_single_booking(booking)
            except Exception as e:
                logger.error(f"Failed to execute booking {booking['id']}: {e}")
                self.db.update_scheduled_booking_status(booking['id'], 'failed')

    async def _execute_single_booking(self, booking: Dict):
        """
        Execute a single scheduled booking

        Args:
            booking: Scheduled booking dictionary
        """
        logger.info(
            f"Executing booking {booking['id']}: "
            f"{booking['course_name']} on {booking['target_date']}"
        )

        # Create booking handler if not exists or if session changed
        # Always recreate to ensure we have the latest session
        if not self.booking_handler or self.booking_handler.session != self.session_manager:
            self.booking_handler = BookingHandler(self.db, self.session_manager)

        # Execute the booking
        success = await self.booking_handler.create_booking(
            user_id=booking['user_id'],
            course_name=booking['course_name'],
            location=booking['location'],
            day=booking['day_of_week'],
            time_start=booking['time_start'],
            is_fit_center=bool(booking['is_fit_center'])
        )

        if success:
            self.db.update_scheduled_booking_status(booking['id'], 'completed')
            logger.info(f"Booking {booking['id']} completed successfully")

            # Notify user via Telegram
            if self.telegram_app:
                await self._notify_booking_success(booking)
        else:
            self.db.update_scheduled_booking_status(booking['id'], 'failed')
            logger.error(f"Booking {booking['id']} failed")

            # Notify user via Telegram
            if self.telegram_app:
                await self._notify_booking_failure(booking)

    # ==================== CONFIRMATION MANAGEMENT ====================

    async def process_pending_confirmations(self):
        """
        Check for confirmations that need to be sent
        Called by scheduler every 10 minutes
        """
        logger.info("Checking for pending confirmations...")

        confirmations = self.booking_service.get_confirmations_needing_action()

        if not confirmations:
            logger.info("No confirmations need action")
            return

        logger.info(f"Found {len(confirmations)} confirmations needing action")

        for confirmation in confirmations:
            try:
                # If message not sent yet, send confirmation request
                if not confirmation.get('confirmation_message_id'):
                    await self._send_confirmation_request(confirmation)
                else:
                    # Check if we're past cancel deadline
                    cancel_deadline = datetime.strptime(
                        confirmation['cancel_deadline'],
                        '%Y-%m-%d %H:%M:%S'
                    )

                    if datetime.now() >= cancel_deadline:
                        await self._auto_cancel_unconfirmed(confirmation)

            except Exception as e:
                logger.error(f"Failed to process confirmation {confirmation['id']}: {e}")

    async def _send_confirmation_request(self, confirmation: Dict):
        """
        Send confirmation request to user via Telegram

        Args:
            confirmation: Pending confirmation dictionary
        """
        if not self.telegram_app:
            logger.warning("No Telegram app available to send confirmation")
            return

        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        # Get periodic booking details
        periodic_bookings = self.db.get_periodic_bookings()
        periodic = next(
            (p for p in periodic_bookings if p['id'] == confirmation['periodic_booking_id']),
            None
        )

        if not periodic:
            logger.error(f"Periodic booking {confirmation['periodic_booking_id']} not found")
            return

        # Create confirmation message
        text = (
            f"🔔 *Conferma prenotazione*\n\n"
            f"📚 {periodic['course_name']}\n"
            f"📍 {periodic['location']}\n"
            f"📅 {confirmation['target_date']}\n"
            f"🕐 {periodic['time_start']}-{periodic['time_end']}\n\n"
            f"Vuoi confermare questa prenotazione?"
        )

        keyboard = [
            [
                InlineKeyboardButton("✅ Conferma", callback_data=f"confirm_{confirmation['id']}"),
                InlineKeyboardButton("❌ Annulla", callback_data=f"reject_{confirmation['id']}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Send message
        try:
            message = await self.telegram_app.bot.send_message(
                chat_id=confirmation['user_id'],
                text=text,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )

            # Store message ID
            self.db.update_confirmation_message_id(confirmation['id'], message.message_id)
            logger.info(f"Sent confirmation request {confirmation['id']} to user {confirmation['user_id']}")

        except Exception as e:
            logger.error(f"Failed to send confirmation message: {e}")

    async def _auto_cancel_unconfirmed(self, confirmation: Dict):
        """
        Auto-cancel an unconfirmed booking

        Args:
            confirmation: Pending confirmation dictionary
        """
        logger.info(f"Auto-cancelling unconfirmed booking {confirmation['id']}")

        # Cancel the scheduled booking
        if confirmation.get('scheduled_booking_id'):
            self.db.update_scheduled_booking_status(
                confirmation['scheduled_booking_id'],
                'cancelled'
            )

        # Update confirmation status
        self.db.update_confirmation_status(confirmation['id'], 'auto_cancelled')

        # Notify user with menu
        text = (
            f"⏰ *Prenotazione auto-annullata*\n\n"
            f"La prenotazione per {confirmation['target_date']} "
            f"è stata annullata per mancata conferma."
        )
        await self._send_notification_with_menu(confirmation['user_id'], text)

    # ==================== PERIODIC BOOKING PROCESSING ====================

    async def process_periodic_bookings(self):
        """
        Process periodic bookings and create scheduled bookings for next week
        Called by scheduler daily at 6:00 AM
        """
        logger.info("Processing periodic bookings...")

        created = self.booking_service.process_periodic_bookings_for_week()

        if created:
            logger.info(f"Created {len(created)} scheduled bookings from periodic bookings")
        else:
            logger.info("No periodic bookings to process")

    # ==================== TELEGRAM NOTIFICATIONS ====================

    async def _notify_booking_success(self, booking: Dict):
        """Notify user of successful booking via Telegram"""
        text = (
            f"✅ *Prenotazione completata!*\n\n"
            f"📚 {booking['course_name']}\n"
            f"📍 {booking['location']}\n"
            f"📅 {booking['target_date']}\n"
            f"🕐 {booking['time_start']}-{booking['time_end']}"
        )
        await self._send_notification_with_menu(booking['user_id'], text)

    async def _notify_booking_failure(self, booking: Dict):
        """Notify user of failed booking via Telegram"""
        text = (
            f"❌ *Prenotazione fallita*\n\n"
            f"📚 {booking['course_name']}\n"
            f"📍 {booking['location']}\n"
            f"📅 {booking['target_date']}\n"
            f"🕐 {booking['time_start']}-{booking['time_end']}\n\n"
            f"Si prega di riprovare manualmente."
        )
        await self._send_notification_with_menu(booking['user_id'], text)


if __name__ == '__main__':
    # Test booking executor
    import asyncio

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    print("=== Booking Executor Test ===\n")

    async def test_executor():
        """Test the booking executor"""
        # Initialize
        db = Database(':memory:')
        executor = BookingExecutor(db)

        print("✓ Executor initialized\n")

        # Test 1: Check pending scheduled bookings (should be empty)
        print("Test 1: Check pending scheduled bookings")
        await executor.execute_pending_scheduled_bookings()
        print()

        # Test 2: Check pending confirmations (should be empty)
        print("Test 2: Check pending confirmations")
        await executor.process_pending_confirmations()
        print()

        # Test 3: Process periodic bookings (should be empty)
        print("Test 3: Process periodic bookings")
        await executor.process_periodic_bookings()
        print()

        print("✅ Booking executor test completed!")

    asyncio.run(test_executor())
