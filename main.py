#!/usr/bin/env python3
"""
Polimisport Bot - Main Entry Point
Telegram bot for managing Polimisport bookings
"""

import asyncio
import logging
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)

from src.utils import Database
from src.resources import SessionManager
from src.handlers import CourseHandler, BookingHandler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PolimisportBot:
    """Main bot controller"""

    def __init__(self, config_path: str = '../config.json'):
        self.config = self._load_config(config_path)
        self.db = Database(self.config.get('db_path', 'polimisport.db'))
        self.authorized_user = self.config['telegram_user_id']

        # Initialize handlers immediately with db
        self.course_handler = CourseHandler(self.db, None)
        self.booking_handler = BookingHandler(self.db, None)

        # Will be initialized when needed
        self.session = None

    def _load_config(self, config_path: str) -> dict:
        """Load configuration from JSON file"""
        import json
        with open(config_path, 'r') as f:
            return json.load(f)

    async def _ensure_session(self):
        """Ensure browser session is active"""
        if self.session is None:
            self.session = SessionManager(self.config.get('config_path', '../config.json'))
            await self.session.start()

            if not await self.session.login():
                raise RuntimeError("Login failed")

            # Update handlers with active session
            self.course_handler.session = self.session
            self.booking_handler.session = self.session

    async def _close_session(self):
        """Close browser session"""
        if self.session:
            await self.session.stop()
            self.session = None
            # Keep handlers but clear session reference
            self.course_handler.session = None
            self.booking_handler.session = None

    def _check_auth(self, update: Update) -> bool:
        """Check if user is authorized"""
        return update.effective_user.id == self.authorized_user

    # ==================== COMMANDS ====================

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command"""
        if not self._check_auth(update):
            await update.message.reply_text("⛔ Non autorizzato")
            return

        keyboard = [
            [InlineKeyboardButton("📚 Corsi", callback_data="menu_courses")],
            [InlineKeyboardButton("💪 Fit Center", callback_data="menu_fit_center")],
            [InlineKeyboardButton("📅 Le mie prenotazioni", callback_data="menu_bookings")],
            [InlineKeyboardButton("🔄 Aggiorna database", callback_data="action_refresh")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "🏃 *Polimisport Bot*\n\nCosa vuoi fare?",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    async def refresh(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Refresh database command"""
        if not self._check_auth(update):
            return

        msg = await update.message.reply_text("🔄 Aggiornamento in corso...")

        try:
            await self._ensure_session()

            # Clear old courses before refreshing
            self.db.clear_courses()

            # Refresh courses (also scrapes bookings)
            course_count, bookings = await self.course_handler.refresh_courses(pages_to_scrape=5)

            # Store bookings
            for booking in bookings:
                self.db.add_user_booking(self.authorized_user, booking)

            # Refresh fit center
            fit_count = await self.course_handler.refresh_fit_center(pages_to_scrape=5)

            booking_count = len(bookings)

            await msg.edit_text(
                f"✅ Database aggiornato!\n\n"
                f"📚 Corsi: {course_count}\n"
                f"💪 Fit Center: {fit_count}\n"
                f"📅 Prenotazioni: {booking_count}"
            )

        except Exception as e:
            logger.error(f"Refresh error: {e}")
            await msg.edit_text(f"❌ Errore: {str(e)}")

        finally:
            await self._close_session()

    async def bookings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show user bookings"""
        if not self._check_auth(update):
            return

        bookings = self.booking_handler.get_user_bookings(self.authorized_user)

        if not bookings:
            await update.message.reply_text("📅 Nessuna prenotazione attiva")
            return

        text = "📅 *Le tue prenotazioni:*\n\n"
        for b in bookings:
            text += f"• {self.booking_handler.format_booking_text(b)}\n"

        await update.message.reply_text(text, parse_mode='Markdown')

    # ==================== CALLBACK HANDLERS ====================

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks"""
        query = update.callback_query
        await query.answer()

        if not self._check_auth(update):
            return

        data = query.data

        if data == "menu_courses":
            await self._show_day_menu(query, is_fit_center=False)

        elif data == "menu_fit_center":
            await self._show_day_menu(query, is_fit_center=True)

        elif data == "menu_bookings":
            bookings = self.booking_handler.get_user_bookings(self.authorized_user)

            if not bookings:
                await query.edit_message_text("📅 Nessuna prenotazione attiva")
                return

            text = "📅 *Le tue prenotazioni:*\n\n"
            for b in bookings:
                text += f"• {self.booking_handler.format_booking_text(b)}\n"

            await query.edit_message_text(text, parse_mode='Markdown')

        elif data == "action_refresh":
            await query.edit_message_text("🔄 Aggiornamento in corso...")

            try:
                await self._ensure_session()

                # Clear old courses before refreshing
                self.db.clear_courses()

                # Refresh courses (also scrapes bookings)
                course_count, bookings = await self.course_handler.refresh_courses(pages_to_scrape=5)

                # Store bookings
                for booking in bookings:
                    self.db.add_user_booking(self.authorized_user, booking)

                fit_count = await self.course_handler.refresh_fit_center(pages_to_scrape=5)
                booking_count = len(bookings)

                await query.edit_message_text(
                    f"✅ Database aggiornato!\n\n"
                    f"📚 Corsi: {course_count}\n"
                    f"💪 Fit Center: {fit_count}\n"
                    f"📅 Prenotazioni: {booking_count}"
                )

            except Exception as e:
                logger.error(f"Refresh error: {e}")
                await query.edit_message_text(f"❌ Errore: {str(e)}")

            finally:
                await self._close_session()

        elif data.startswith("day_"):
            parts = data.split("_")
            day_name = parts[1]
            is_fit_center = len(parts) > 2 and parts[2] == "fit"

            await self._show_courses_for_day(query, day_name, is_fit_center)

    async def _show_day_menu(self, query, is_fit_center: bool):
        """Show day selection menu"""
        days = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]

        keyboard = []
        for day in days:
            callback_data = f"day_{day}_fit" if is_fit_center else f"day_{day}"
            keyboard.append([InlineKeyboardButton(day, callback_data=callback_data)])

        reply_markup = InlineKeyboardMarkup(keyboard)

        title = "💪 Fit Center - Seleziona giorno:" if is_fit_center else "📚 Corsi - Seleziona giorno:"
        await query.edit_message_text(title, reply_markup=reply_markup)

    async def _show_courses_for_day(self, query, day_name: str, is_fit_center: bool):
        """Show courses for a specific day"""
        if is_fit_center:
            courses = self.course_handler.get_fit_center_by_day(day_name)
            title = f"💪 Fit Center - {day_name}"
        else:
            courses = self.course_handler.get_courses_by_day(day_name)
            title = f"📚 Corsi - {day_name}"

        if not courses:
            await query.edit_message_text(f"{title}\n\nNessun corso disponibile")
            return

        text = f"*{title}*\n\n"
        for c in courses:
            text += f"• {self.course_handler.format_course_text(c)}\n"

        await query.edit_message_text(text, parse_mode='Markdown')

    # ==================== RUN ====================

    def run(self):
        """Start the bot"""
        logger.info("Starting Polimisport Bot...")

        # Create application
        app = Application.builder().token(self.config['telegram_bot_token']).build()

        # Register handlers
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CommandHandler("refresh", self.refresh))
        app.add_handler(CommandHandler("bookings", self.bookings))
        app.add_handler(CallbackQueryHandler(self.button_callback))

        # Start bot
        logger.info("Bot started!")
        app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    bot = PolimisportBot()
    bot.run()
