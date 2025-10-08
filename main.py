#!/usr/bin/env python3
"""
Polimisport Bot - Main Entry Point
Telegram bot for managing Polimisport bookings
"""

import asyncio
import logging
from pathlib import Path
from datetime import datetime, timedelta
from io import BytesIO

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)

from src.utils import Database, BookingScheduler
from src.resources import SessionManager
from src.handlers import (
    CourseHandler,
    BookingHandler,
    BookingService,
    BookingMode,
    BookingExecutor
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PolimisportBot:
    """Main bot controller"""

    def __init__(self, config_path: str = 'config.json'):
        self.config = self._load_config(config_path)
        self.db = Database(self.config.get('db_path', 'polimisport.db'))
        self.authorized_user = self.config['telegram_user_id']

        # Initialize handlers immediately with db
        self.course_handler = CourseHandler(self.db, None)
        self.booking_handler = BookingHandler(self.db, None)
        self.booking_service = BookingService(self.db, self.config)
        self.booking_executor = None  # Will be initialized with telegram app

        # Initialize scheduler
        self.scheduler = BookingScheduler(self.config)

        # Will be initialized when needed
        self.session = None
        self.telegram_app = None

    def _load_config(self, config_path: str) -> dict:
        """Load configuration from JSON file"""
        import json
        with open(config_path, 'r') as f:
            return json.load(f)

    async def _ensure_session(self):
        """Ensure browser session is active"""
        if self.session is None:
            self.session = SessionManager(self.config.get('config_path', 'config.json'))
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
            [InlineKeyboardButton("📚 Visualizza Corsi", callback_data="menu_all_courses")],
            [InlineKeyboardButton("🎯 Prenota corso", callback_data="menu_book")],
            [InlineKeyboardButton("📅 Le mie prenotazioni", callback_data="menu_bookings")],
            [InlineKeyboardButton("📆 Gestisci pianificazione", callback_data="menu_scheduling")],
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
            self.db.sync_user_bookings(self.authorized_user, bookings)

            # Refresh fit center
            fit_count = await self.course_handler.refresh_fit_center(pages_to_scrape=5)

            booking_count = len(bookings)

            # Send success message
            await msg.edit_text(
                f"✅ Database aggiornato!\n\n"
                f"📚 Corsi: {course_count}\n"
                f"💪 Fit Center: {fit_count}\n"
                f"📅 Prenotazioni: {booking_count}"
            )

            # Send main menu
            await self._send_notification_and_menu(
                self.authorized_user,
                ""  # Empty message since we already sent the success message
            )

        except Exception as e:
            logger.error(f"Refresh error: {e}")
            await msg.edit_text(f"❌ Errore: {str(e)}")
            # Send menu even on error
            await self._send_notification_and_menu(self.authorized_user, "")

        finally:
            await self._close_session()

    async def bookings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show user bookings with cancel buttons"""
        if not self._check_auth(update):
            return

        bookings = self.booking_handler.get_user_bookings(self.authorized_user)

        if not bookings:
            await update.message.reply_text("📅 Nessuna prenotazione attiva")
            # Send main menu
            await self._send_notification_and_menu(self.authorized_user, "")
            return

        text = "📅 *Le tue prenotazioni:*\n\n"
        keyboard = []

        for idx, b in enumerate(bookings, 1):
            text += f"{idx}. {self.booking_handler.format_booking_text(b)}\n"
            # Add compact cancel button for each booking
            keyboard.append([
                InlineKeyboardButton(
                    f"❌ #{idx}",
                    callback_data=f"cancel_booking_{b['booking_id']}"
                )
            ])

        # Add back button
        keyboard.append([InlineKeyboardButton("🔙 Menu", callback_data="back_to_menu")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    async def book(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Book a course - show course selection menu"""
        if not self._check_auth(update):
            return

        keyboard = [
            [InlineKeyboardButton("📚 Corsi", callback_data="book_courses")],
            [InlineKeyboardButton("💪 Fit Center", callback_data="book_fit_center")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "🎯 *Prenota un corso*\n\nSeleziona tipo:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    async def scheduled(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show scheduled bookings"""
        if not self._check_auth(update):
            return

        scheduled = self.booking_service.get_user_scheduled_bookings(self.authorized_user)

        if not scheduled:
            await update.message.reply_text("📆 Nessuna prenotazione programmata")
            return

        text = "📆 *Prenotazioni programmate:*\n\n"
        for s in scheduled:
            status_emoji = "⏳" if s['status'] == 'pending' else "✅" if s['status'] == 'completed' else "❌"
            text += (
                f"{status_emoji} *{s['course_name']}*\n"
                f"  📍 {s['location']}\n"
                f"  📅 {s['target_date']} {s['time_start']}-{s['time_end']}\n"
                f"  🕐 Esegue: {s['execution_time']}\n"
                f"  ID: {s['id']}\n\n"
            )

        keyboard = [[InlineKeyboardButton("🗑 Gestisci", callback_data="manage_scheduled")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    async def periodic(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show periodic bookings"""
        if not self._check_auth(update):
            return

        periodic = self.booking_service.get_user_periodic_bookings(self.authorized_user)

        if not periodic:
            await update.message.reply_text("🔄 Nessuna prenotazione ricorrente")
            return

        text = "🔄 *Prenotazioni ricorrenti:*\n\n"
        for p in periodic:
            active_emoji = "✅" if p['is_active'] else "⏸"
            conf_text = "con conferma" if p['requires_confirmation'] else "senza conferma"
            text += (
                f"{active_emoji} *{p['course_name']}*\n"
                f"  📍 {p['location']}\n"
                f"  📅 Ogni {p['day_of_week']} {p['time_start']}-{p['time_end']}\n"
                f"  🔔 {conf_text}\n"
                f"  ID: {p['id']}\n\n"
            )

        keyboard = [[InlineKeyboardButton("🗑 Gestisci", callback_data="manage_periodic")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    async def confirmations(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show pending confirmations"""
        if not self._check_auth(update):
            return

        confirmations = self.booking_service.get_pending_confirmations(self.authorized_user)

        if not confirmations:
            await update.message.reply_text("✅ Nessuna conferma in sospeso")
            return

        text = "🔔 *Conferme in sospeso:*\n\n"
        for c in confirmations:
            text += (
                f"📅 {c['target_date']}\n"
                f"  ⏰ Scadenza: {c['confirmation_deadline']}\n"
                f"  ID: {c['id']}\n\n"
            )

        await update.message.reply_text(text, parse_mode='Markdown')

    # ==================== CALLBACK HANDLERS ====================

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks"""
        query = update.callback_query
        await query.answer()

        if not self._check_auth(update):
            return

        data = query.data

        if data == "menu_all_courses":
            # Show combined courses and fit center selection
            keyboard = [
                [InlineKeyboardButton("📚 Corsi", callback_data="view_courses")],
                [InlineKeyboardButton("💪 Fit Center", callback_data="view_fit_center")],
                [InlineKeyboardButton("🔙 Home", callback_data="back_to_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "📚 *Visualizza Corsi*\n\nSeleziona tipo:",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )

        elif data == "view_courses":
            await self._show_day_menu(query, is_fit_center=False)

        elif data == "view_fit_center":
            await self._show_day_menu(query, is_fit_center=True)

        elif data == "menu_book":
            keyboard = [
                [InlineKeyboardButton("📚 Corsi", callback_data="book_courses")],
                [InlineKeyboardButton("💪 Fit Center", callback_data="book_fit_center")],
                [InlineKeyboardButton("🔙 Home", callback_data="back_to_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "🎯 *Prenota un corso*\n\nSeleziona tipo:",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )

        elif data == "menu_scheduling":
            # Show combined scheduling menu
            scheduled = self.booking_service.get_user_scheduled_bookings(self.authorized_user)
            periodic = self.booking_service.get_user_periodic_bookings(self.authorized_user)

            text = "📆 *Gestisci Pianificazione*\n\n"

            if scheduled:
                text += "*Prenotazioni programmate:*\n"
                for s in scheduled:
                    status_emoji = "⏳" if s['status'] == 'pending' else "✅" if s['status'] == 'completed' else "❌"
                    text += (
                        f"{status_emoji} {s['course_name']}\n"
                        f"   📅 {s['target_date']} {s['time_start']}\n"
                    )
                text += "\n"

            if periodic:
                text += "*Prenotazioni ricorrenti:*\n"
                for p in periodic:
                    active_emoji = "✅" if p['is_active'] else "⏸"
                    text += (
                        f"{active_emoji} {p['course_name']}\n"
                        f"   📅 Ogni {p['day_of_week']} {p['time_start']}\n"
                    )
                text += "\n"

            if not scheduled and not periodic:
                text += "Nessuna pianificazione attiva"

            keyboard = []
            if scheduled:
                keyboard.append([InlineKeyboardButton("🗑 Gestisci programmate", callback_data="manage_scheduled")])
            if periodic:
                keyboard.append([InlineKeyboardButton("🗑 Gestisci ricorrenti", callback_data="manage_periodic")])
            keyboard.append([InlineKeyboardButton("🔙 Home", callback_data="back_to_menu")])

            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

        elif data == "menu_bookings":
            await self._show_bookings_with_cancel(query)

        elif data == "back_to_menu":
            await self._show_main_menu(query)

        elif data == "action_refresh":
            await query.edit_message_text("🔄 Aggiornamento in corso...")

            try:
                await self._ensure_session()

                # Clear old courses before refreshing
                self.db.clear_courses()

                # Refresh courses (also scrapes bookings)
                course_count, bookings = await self.course_handler.refresh_courses(pages_to_scrape=5)

                # Store bookings
                self.db.sync_user_bookings(self.authorized_user, bookings)

                fit_count = await self.course_handler.refresh_fit_center(pages_to_scrape=5)
                booking_count = len(bookings)

                await query.edit_message_text(
                    f"✅ Database aggiornato!\n\n"
                    f"📚 Corsi: {course_count}\n"
                    f"💪 Fit Center: {fit_count}\n"
                    f"📅 Prenotazioni: {booking_count}"
                )
                # Return to main menu
                await self._show_main_menu(query)

            except Exception as e:
                logger.error(f"Refresh error: {e}")
                await query.edit_message_text(f"❌ Errore: {str(e)}")
                # Return to main menu even on error
                await self._show_main_menu(query)

            finally:
                await self._close_session()

        elif data.startswith("day_"):
            parts = data.split("_")
            day_name = parts[1]
            is_fit_center = len(parts) > 2 and parts[2] == "fit"

            await self._show_courses_for_day(query, day_name, is_fit_center)

        elif data == "book_courses":
            await self._show_booking_day_menu(query, is_fit_center=False)

        elif data == "book_fit_center":
            await self._show_booking_day_menu(query, is_fit_center=True)

        elif data.startswith("bookday_"):
            parts = data.split("_", 2)
            day_name = parts[1]
            is_fit_center = len(parts) > 2 and parts[2] == "fit"
            await self._show_booking_courses(query, day_name, is_fit_center)

        elif data.startswith("selectcourse_"):
            course_id = int(data.split("_")[1])
            await self._show_booking_options(query, course_id)

        elif data.startswith("instant_"):
            course_id = int(data.split("_")[1])
            await self._book_instant(query, course_id)

        elif data.startswith("schedule_"):
            course_id = int(data.split("_")[1])
            await self._book_scheduled(query, course_id)

        elif data.startswith("periodic_"):
            parts = data.split("_")
            course_id = int(parts[1])
            requires_conf = parts[2] == "conf" if len(parts) > 2 else False
            await self._book_periodic(query, course_id, requires_conf)

        elif data == "manage_scheduled":
            await self._show_manage_scheduled(query)

        elif data == "manage_periodic":
            await self._show_manage_periodic(query)

        elif data.startswith("delsch_"):
            booking_id = int(data.split("_")[1])
            await self._delete_scheduled(query, booking_id)

        elif data.startswith("delper_"):
            booking_id = int(data.split("_")[1])
            await self._delete_periodic(query, booking_id)

        elif data.startswith("toggle_"):
            booking_id = int(data.split("_")[1])
            await self._toggle_periodic(query, booking_id)

        elif data.startswith("confirm_"):
            confirmation_id = int(data.split("_")[1])
            await self._confirm_booking(query, confirmation_id)

        elif data.startswith("reject_"):
            confirmation_id = int(data.split("_")[1])
            await self._reject_booking(query, confirmation_id)

        elif data.startswith("cancel_booking_"):
            booking_id = data.replace("cancel_booking_", "")
            await self._cancel_booking(query, booking_id)

    async def _show_day_menu(self, query, is_fit_center: bool):
        """Show day selection menu"""
        days = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]

        keyboard = []
        for day in days:
            callback_data = f"day_{day}_fit" if is_fit_center else f"day_{day}"
            keyboard.append([InlineKeyboardButton(day, callback_data=callback_data)])

        keyboard.append([InlineKeyboardButton("🔙 Home", callback_data="back_to_menu")])
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

        text = f"*{title}*\n\n"
        if not courses:
            text += "Nessun corso disponibile"
        else:
            for c in courses:
                text += f"• {self.course_handler.format_course_text(c)}\n"

        keyboard = [[InlineKeyboardButton("🔙 Home", callback_data="back_to_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    # ==================== BOOKING UI HELPERS ====================

    async def _show_booking_day_menu(self, query, is_fit_center: bool):
        """Show day selection menu for booking"""
        days = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]

        keyboard = []
        for day in days:
            callback_data = f"bookday_{day}_fit" if is_fit_center else f"bookday_{day}"
            keyboard.append([InlineKeyboardButton(day, callback_data=callback_data)])

        reply_markup = InlineKeyboardMarkup(keyboard)

        title = "💪 Fit Center - Seleziona giorno:" if is_fit_center else "📚 Corsi - Seleziona giorno:"
        await query.edit_message_text(title, reply_markup=reply_markup)

    async def _show_booking_courses(self, query, day_name: str, is_fit_center: bool):
        """Show courses available for booking on a specific day"""
        if is_fit_center:
            courses = self.course_handler.get_fit_center_by_day(day_name)
            title = f"💪 Prenota Fit Center - {day_name}"
        else:
            courses = self.course_handler.get_courses_by_day(day_name)
            title = f"📚 Prenota Corso - {day_name}"

        if not courses:
            await query.edit_message_text(f"{title}\n\nNessun corso disponibile")
            return

        keyboard = []
        for c in courses:
            button_text = f"{c['time_start']} - {c['name']}"
            callback_data = f"selectcourse_{c['id']}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"*{title}*\n\nSeleziona corso:", reply_markup=reply_markup, parse_mode='Markdown')

    async def _show_booking_options(self, query, course_id: int):
        """Show booking options for selected course"""
        courses = self.db.get_all_courses(include_fit_center=True)
        course = next((c for c in courses if c['id'] == course_id), None)

        if not course:
            await query.edit_message_text("❌ Corso non trovato")
            return

        # Determine available booking modes
        can_instant = self.booking_service.can_book_instantly(course['day_of_week'])

        text = (
            f"🎯 *Opzioni di prenotazione*\n\n"
            f"📚 {course['name']}\n"
            f"📍 {course['location']}\n"
            f"📅 {course['day_of_week']} {course['time_start']}-{course['time_end']}\n\n"
        )

        keyboard = []

        if can_instant:
            text += "✅ Prenotazione immediata disponibile (entro 2 giorni)\n"
            keyboard.append([InlineKeyboardButton("⚡ Prenota subito", callback_data=f"instant_{course_id}")])
        else:
            text += "📆 Prenotazione programmata (esegue a mezzanotte 2 giorni prima)\n"
            keyboard.append([InlineKeyboardButton("📅 Programma prenotazione", callback_data=f"schedule_{course_id}")])

        keyboard.append([InlineKeyboardButton("🔄 Prenotazione ricorrente (con conferma)", callback_data=f"periodic_{course_id}_conf")])
        keyboard.append([InlineKeyboardButton("🔄 Prenotazione ricorrente (automatica)", callback_data=f"periodic_{course_id}_auto")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    async def _book_instant(self, query, course_id: int):
        """Execute instant booking"""
        courses = self.db.get_all_courses(include_fit_center=True)
        course = next((c for c in courses if c['id'] == course_id), None)

        if not course:
            await query.edit_message_text("❌ Corso non trovato")
            return

        await query.edit_message_text("⏳ Prenotazione in corso...")

        try:
            await self._ensure_session()

            success = await self.booking_handler.create_booking(
                user_id=self.authorized_user,
                course_name=course['name'],
                location=course['location'],
                day=course['day_of_week'],
                time_start=course['time_start'],
                is_fit_center=bool(course.get('is_fit_center'))
            )

            if success:
                # Send calendar notification
                await self._send_booking_calendar(query, course)
                # Return to main menu
                await self._show_main_menu(query)
            else:
                keyboard = [[InlineKeyboardButton("🔙 Home", callback_data="back_to_menu")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text("❌ Prenotazione fallita. Riprova.", reply_markup=reply_markup)

        except Exception as e:
            logger.error(f"Instant booking error: {e}")
            keyboard = [[InlineKeyboardButton("🔙 Home", callback_data="back_to_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(f"❌ Errore: {str(e)}", reply_markup=reply_markup)

        finally:
            await self._close_session()

    async def _book_scheduled(self, query, course_id: int):
        """Create scheduled booking"""
        courses = self.db.get_all_courses(include_fit_center=True)
        course = next((c for c in courses if c['id'] == course_id), None)

        if not course:
            await query.edit_message_text("❌ Corso non trovato")
            return

        try:
            scheduled_id = self.booking_service.create_scheduled_booking(
                user_id=self.authorized_user,
                course=course
            )

            next_date = self.booking_service.get_next_date_for_day(course['day_of_week'])
            exec_time = self.booking_service.calculate_execution_time(next_date)

            text = (
                f"✅ *Prenotazione programmata!*\n\n"
                f"📚 {course['name']}\n"
                f"📍 {course['location']}\n"
                f"📅 {course['day_of_week']} {course['time_start']}-{course['time_end']}\n"
                f"🎯 Data corso: {next_date.strftime('%Y-%m-%d')}\n"
                f"🕐 Esegue: {exec_time.strftime('%Y-%m-%d alle 00:00')}\n\n"
                f"ID: {scheduled_id}"
            )
            keyboard = [[InlineKeyboardButton("🏠 Home", callback_data="back_to_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Scheduled booking error: {e}")
            keyboard = [[InlineKeyboardButton("🔙 Home", callback_data="back_to_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(f"❌ Errore: {str(e)}", reply_markup=reply_markup)

    async def _book_periodic(self, query, course_id: int, requires_confirmation: bool):
        """Create periodic booking"""
        courses = self.db.get_all_courses(include_fit_center=True)
        course = next((c for c in courses if c['id'] == course_id), None)

        if not course:
            await query.edit_message_text("❌ Corso non trovato")
            return

        try:
            periodic_id = self.booking_service.create_periodic_booking(
                user_id=self.authorized_user,
                course=course,
                requires_confirmation=requires_confirmation
            )

            conf_hours = self.booking_service.default_confirmation_hours_before
            conf_text = f"con conferma ({conf_hours}h prima)" if requires_confirmation else "automatica (nessuna conferma)"

            text = (
                f"✅ *Prenotazione ricorrente creata!*\n\n"
                f"📚 {course['name']}\n"
                f"📍 {course['location']}\n"
                f"📅 Ogni {course['day_of_week']} {course['time_start']}-{course['time_end']}\n"
                f"🔔 Modalità: {conf_text}\n\n"
                f"ID: {periodic_id}"
            )
            keyboard = [[InlineKeyboardButton("🏠 Home", callback_data="back_to_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Periodic booking error: {e}")
            keyboard = [[InlineKeyboardButton("🔙 Home", callback_data="back_to_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(f"❌ Errore: {str(e)}", reply_markup=reply_markup)

    async def _show_manage_scheduled(self, query):
        """Show scheduled bookings management"""
        scheduled = self.booking_service.get_user_scheduled_bookings(self.authorized_user, status='pending')

        keyboard = []

        if not scheduled:
            text = "📆 Nessuna prenotazione programmata da gestire"
        else:
            text = "🗑 *Elimina prenotazione programmata:*"
            for s in scheduled:
                button_text = f"🗑 {s['course_name']} - {s['target_date']}"
                keyboard.append([InlineKeyboardButton(button_text, callback_data=f"delsch_{s['id']}")])

        keyboard.append([InlineKeyboardButton("🔙 Home", callback_data="back_to_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    async def _show_manage_periodic(self, query):
        """Show periodic bookings management"""
        periodic = self.booking_service.get_user_periodic_bookings(self.authorized_user)

        keyboard = []

        if not periodic:
            text = "🔄 Nessuna prenotazione ricorrente da gestire"
        else:
            text = "🔄 *Gestisci prenotazioni ricorrenti:*"
            for p in periodic:
                active_emoji = "⏸" if p['is_active'] else "▶️"
                button_text = f"{active_emoji} {p['course_name']} - {p['day_of_week']}"
                keyboard.append([InlineKeyboardButton(button_text, callback_data=f"toggle_{p['id']}")])
                keyboard.append([InlineKeyboardButton(f"🗑 Elimina {p['course_name']}", callback_data=f"delper_{p['id']}")])

        keyboard.append([InlineKeyboardButton("🔙 Home", callback_data="back_to_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    async def _delete_scheduled(self, query, booking_id: int):
        """Delete a scheduled booking"""
        try:
            self.booking_service.cancel_scheduled_booking(booking_id)
            keyboard = [[InlineKeyboardButton("🏠 Home", callback_data="back_to_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("✅ Prenotazione programmata eliminata", reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Delete scheduled error: {e}")
            keyboard = [[InlineKeyboardButton("🔙 Home", callback_data="back_to_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(f"❌ Errore: {str(e)}", reply_markup=reply_markup)

    async def _delete_periodic(self, query, booking_id: int):
        """Delete a periodic booking"""
        try:
            self.booking_service.delete_periodic_booking(booking_id)
            keyboard = [[InlineKeyboardButton("🏠 Home", callback_data="back_to_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("✅ Prenotazione ricorrente eliminata", reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Delete periodic error: {e}")
            keyboard = [[InlineKeyboardButton("🔙 Home", callback_data="back_to_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(f"❌ Errore: {str(e)}", reply_markup=reply_markup)

    async def _toggle_periodic(self, query, booking_id: int):
        """Toggle a periodic booking"""
        try:
            periodic = self.booking_service.get_user_periodic_bookings(self.authorized_user)
            booking = next((p for p in periodic if p['id'] == booking_id), None)

            if not booking:
                keyboard = [[InlineKeyboardButton("🔙 Home", callback_data="back_to_menu")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text("❌ Prenotazione non trovata", reply_markup=reply_markup)
                return

            new_status = not bool(booking['is_active'])
            self.booking_service.toggle_periodic_booking(booking_id, new_status)

            status_text = "attivata" if new_status else "disattivata"
            keyboard = [[InlineKeyboardButton("🏠 Home", callback_data="back_to_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(f"✅ Prenotazione ricorrente {status_text}", reply_markup=reply_markup)

        except Exception as e:
            logger.error(f"Toggle periodic error: {e}")
            keyboard = [[InlineKeyboardButton("🔙 Home", callback_data="back_to_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(f"❌ Errore: {str(e)}", reply_markup=reply_markup)

    async def _confirm_booking(self, query, confirmation_id: int):
        """Confirm a booking"""
        try:
            self.booking_service.confirm_booking(confirmation_id)
            await query.edit_message_text("✅ Prenotazione confermata!")
        except Exception as e:
            logger.error(f"Confirm booking error: {e}")
            await query.edit_message_text(f"❌ Errore: {str(e)}")

    async def _reject_booking(self, query, confirmation_id: int):
        """Reject a booking"""
        try:
            self.booking_service.reject_booking(confirmation_id)
            await query.edit_message_text("❌ Prenotazione annullata")
        except Exception as e:
            logger.error(f"Reject booking error: {e}")
            await query.edit_message_text(f"❌ Errore: {str(e)}")

    async def _cancel_booking(self, query, booking_id: str):
        """Cancel an active booking"""
        try:
            await query.edit_message_text("🔄 Cancellazione in corso...")

            # Ensure session is active
            await self._ensure_session()

            # Cancel the booking
            success = await self.booking_handler.cancel_booking(self.authorized_user, booking_id)

            if success:
                # Show updated bookings list
                await self._show_bookings_with_cancel(query, success_message="✅ Prenotazione cancellata!")
            else:
                await self._show_bookings_with_cancel(query, success_message="❌ Errore durante la cancellazione")

        except Exception as e:
            logger.error(f"Cancel booking error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await query.edit_message_text(f"❌ Errore: {str(e)}")
        finally:
            await self._close_session()

    async def _show_bookings_with_cancel(self, query, success_message: str = None):
        """Show bookings list with cancel buttons"""
        bookings = self.booking_handler.get_user_bookings(self.authorized_user)

        if not bookings:
            text = "📅 Nessuna prenotazione attiva"
            keyboard = [[InlineKeyboardButton("🔙 Menu", callback_data="back_to_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup)
            return

        text = ""
        if success_message:
            text = f"{success_message}\n\n"

        text += "📅 *Le tue prenotazioni:*\n\n"
        keyboard = []

        for idx, b in enumerate(bookings, 1):
            text += f"{idx}. {self.booking_handler.format_booking_text(b)}\n"
            # Add compact cancel button
            keyboard.append([
                InlineKeyboardButton(
                    f"❌ #{idx}",
                    callback_data=f"cancel_booking_{b['booking_id']}"
                )
            ])

        # Add back button
        keyboard.append([InlineKeyboardButton("🔙 Menu", callback_data="back_to_menu")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    def _create_ics_calendar(self, course: dict, booking_date: str = None) -> str:
        """Create ICS calendar file content"""
        # Parse day of week to get next occurrence date
        days_map = {
            'Lunedì': 0, 'Martedì': 1, 'Mercoledì': 2,
            'Giovedì': 3, 'Venerdì': 4, 'Sabato': 5, 'Domenica': 6
        }

        if booking_date:
            # Use provided date
            event_date = datetime.strptime(booking_date, '%d/%m/%Y')
        else:
            # Calculate next occurrence of this day
            today = datetime.now()
            target_day = days_map.get(course['day_of_week'], 0)
            days_ahead = target_day - today.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            event_date = today + timedelta(days=days_ahead)

        # Parse time
        start_time = datetime.strptime(course['time_start'], '%H:%M')
        end_time = datetime.strptime(course['time_end'], '%H:%M')

        start_datetime = event_date.replace(hour=start_time.hour, minute=start_time.minute)
        end_datetime = event_date.replace(hour=end_time.hour, minute=end_time.minute)

        # Format for ICS
        dtstart = start_datetime.strftime('%Y%m%dT%H%M%S')
        dtend = end_datetime.strftime('%Y%m%dT%H%M%S')
        dtstamp = datetime.now().strftime('%Y%m%dT%H%M%SZ')

        ics_content = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Polimisport Bot//IT
BEGIN:VEVENT
UID:{course['id']}-{dtstart}@polimisport
DTSTAMP:{dtstamp}
DTSTART:{dtstart}
DTEND:{dtend}
SUMMARY:{course['name']}
DESCRIPTION:Prenotazione Polimisport
LOCATION:{course['location']}
STATUS:CONFIRMED
END:VEVENT
END:VCALENDAR"""
        return ics_content

    async def _send_booking_calendar(self, query, course: dict, booking_date: str = None):
        """Send booking confirmation with calendar attachment"""
        ics_content = self._create_ics_calendar(course, booking_date)
        ics_file = BytesIO(ics_content.encode('utf-8'))
        ics_file.name = f"polimisport_{course['name']}.ics"

        # Send message with calendar
        message_text = (
            f"✅ *Prenotazione completata!*\n\n"
            f"📚 {course['name']}\n"
            f"📍 {course['location']}\n"
            f"📅 {course['day_of_week']} {course['time_start']}-{course['time_end']}\n\n"
            f"📎 Calendario allegato - aggiungilo al tuo Google Calendar!"
        )

        # Send calendar file
        await query.message.reply_document(
            document=ics_file,
            caption=message_text,
            parse_mode='Markdown'
        )

    async def _send_notification_and_menu(self, chat_id: int, message: str):
        """Send notification message and then show main menu"""
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

    async def _show_main_menu(self, query):
        """Show main menu"""
        keyboard = [
            [InlineKeyboardButton("📚 Visualizza Corsi", callback_data="menu_all_courses")],
            [InlineKeyboardButton("🎯 Prenota corso", callback_data="menu_book")],
            [InlineKeyboardButton("📅 Le mie prenotazioni", callback_data="menu_bookings")],
            [InlineKeyboardButton("📆 Gestisci pianificazione", callback_data="menu_scheduling")],
            [InlineKeyboardButton("🔄 Aggiorna database", callback_data="action_refresh")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "🏃 *Polimisport Bot*\n\nCosa vuoi fare?",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    # ==================== RUN ====================

    def run(self):
        """Start the bot"""
        logger.info("Starting Polimisport Bot...")

        # Create application
        app = Application.builder().token(self.config['telegram_bot_token']).build()
        self.telegram_app = app

        # Initialize booking executor with telegram app
        self.booking_executor = BookingExecutor(
            db=self.db,
            session_manager=None,  # Will be created when needed
            telegram_app=app
        )

        # Setup scheduler jobs
        self._setup_scheduler()

        # Register command handlers
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CommandHandler("refresh", self.refresh))
        app.add_handler(CommandHandler("bookings", self.bookings))
        app.add_handler(CommandHandler("book", self.book))
        app.add_handler(CommandHandler("scheduled", self.scheduled))
        app.add_handler(CommandHandler("periodic", self.periodic))
        app.add_handler(CommandHandler("confirmations", self.confirmations))
        app.add_handler(CallbackQueryHandler(self.button_callback))

        # Start bot
        logger.info("Bot started with scheduler!")
        app.run_polling(allowed_updates=Update.ALL_TYPES)

    def _setup_scheduler(self):
        """Setup scheduler jobs for automated booking operations"""
        logger.info("Setting up scheduler...")

        # Start scheduler
        self.scheduler.start()

        # Add scheduled booking executor (runs at midnight to execute bookings)
        async def execute_bookings():
            """Execute pending scheduled bookings"""
            try:
                # Ensure session for executor
                if not self.booking_executor.session_manager or not self.booking_executor.session_manager.page:
                    self.booking_executor.session_manager = SessionManager(
                        self.config.get('config_path', 'config.json')
                    )
                    await self.booking_executor.session_manager.start()
                    await self.booking_executor.session_manager.login()

                await self.booking_executor.execute_pending_scheduled_bookings()

            except Exception as e:
                logger.error(f"Scheduler execute_bookings error: {e}")

        # Only use midnight executor - the 1AM checker is redundant
        self.scheduler.add_midnight_booking_executor(execute_bookings)

        # Add confirmation checker
        async def check_confirmations():
            """Check and send pending confirmations"""
            try:
                await self.booking_executor.process_pending_confirmations()
            except Exception as e:
                logger.error(f"Scheduler check_confirmations error: {e}")

        self.scheduler.add_confirmation_checker(check_confirmations)
        self.scheduler.add_auto_cancel_checker(check_confirmations)

        # Add periodic booking processor
        async def process_periodic():
            """Process periodic bookings daily"""
            try:
                await self.booking_executor.process_periodic_bookings()
            except Exception as e:
                logger.error(f"Scheduler process_periodic error: {e}")

        self.scheduler.add_periodic_booking_processor(process_periodic)

        logger.info("Scheduler setup complete!")


if __name__ == '__main__':
    bot = PolimisportBot()
    bot.run()
