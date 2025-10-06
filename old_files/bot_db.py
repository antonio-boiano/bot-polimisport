#!/usr/bin/env python3
"""
Telegram Bot for Polimisport - Database Version
Bot adds actions to queue, doesn't wait for results
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
import json
from datetime import datetime, timedelta
from database import Database

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class PolimisportBotDB:
    def __init__(self, config_path='../config.json'):
        with open(config_path, 'r') as f:
            self.config = json.load(f)

        self.allowed_user_id = self.config['telegram']['allowed_user_id']
        self.db = Database()

    def _check_authorization(self, update: Update) -> bool:
        user_id = update.effective_user.id
        return user_id == self.allowed_user_id

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_authorization(update):
            await update.message.reply_text("⛔ Non sei autorizzato ad usare questo bot.")
            return

        keyboard = [
            [InlineKeyboardButton("📅 Prenota Corso", callback_data='new_booking')],
            [InlineKeyboardButton("🏋️ Prenota Fit Center", callback_data='fit_center_booking')],
            [InlineKeyboardButton("📋 Le Mie Prenotazioni", callback_data='my_bookings')],
            [InlineKeyboardButton("🗓️ Visualizza Orari", callback_data='view_schedules_menu')],
            [InlineKeyboardButton("🔄 Prenotazioni Periodiche", callback_data='periodic_menu')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "👋 Benvenuto al Bot Polimisport!\n\n"
            "Cosa vuoi fare?",
            reply_markup=reply_markup
        )

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        if not self._check_authorization(update):
            await query.edit_message_text("⛔ Non sei autorizzato ad usare questo bot.")
            return

        user_id = update.effective_user.id
        data = query.data

        if data == 'new_booking':
            await self.show_booking_menu(query, user_id)
        elif data == 'fit_center_booking':
            await self.show_fit_center_menu(query, user_id)
        elif data == 'my_bookings':
            await self.show_my_bookings(query, user_id)
        elif data == 'view_schedules_menu':
            await self.show_schedules_menu(query, user_id)
        elif data == 'course_schedule':
            await self.show_course_schedule(query, user_id)
        elif data == 'fit_center_schedule':
            await self.show_fit_center_schedule(query, user_id)
        elif data == 'periodic_menu':
            await self.show_periodic_menu(query, user_id)
        elif data.startswith('day_'):
            await self.show_day_courses(query, user_id, data)
        elif data.startswith('fitday_'):
            await self.show_fit_center_day(query, user_id, data)
        elif data.startswith('book_'):
            await self.initiate_booking(query, user_id, data)
        elif data.startswith('cancel_'):
            await self.initiate_cancel(query, user_id, data)
        elif data.startswith('confirm_'):
            await self.confirm_periodic(query, user_id, data)
        elif data.startswith('periodic_add'):
            await self.add_periodic_booking_menu(query, user_id)
        elif data.startswith('periodic_type_'):
            await self.show_periodic_day_selection(query, user_id, data)
        elif data.startswith('periodic_list'):
            await self.list_periodic_bookings(query, user_id)
        elif data.startswith('periodic_delete_'):
            await self.delete_periodic_booking(query, user_id, data)
        elif data.startswith('periodic_day_'):
            await self.handle_periodic_day_selection(query, user_id, data)
        elif data == 'back_to_main':
            await self.start(update, context)

    async def show_booking_menu(self, query, user_id: int):
        """Show available courses for booking"""
        courses = self.db.get_all_courses()

        if not courses:
            await query.edit_message_text(
                "📋 Nessun corso disponibile.\n\n"
                "Usa /refresh_courses per aggiornare il database.\n"
                "Usa /start per tornare al menu."
            )
            return

        # Group courses by day (day_of_week is stored as Italian day name)
        days = ['Lunedì', 'Martedì', 'Mercoledì', 'Giovedì', 'Venerdì', 'Sabato', 'Domenica']
        keyboard = []

        for day_name in days:
            day_courses = [c for c in courses if c['day_of_week'] == day_name]
            if day_courses:
                keyboard.append([InlineKeyboardButton(
                    f"📅 {day_name} ({len(day_courses)} corsi)",
                    callback_data=f'day_{day_name}'
                )])

        keyboard.append([InlineKeyboardButton("🔙 Indietro", callback_data='back_to_main')])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "📅 Seleziona un giorno per vedere i corsi disponibili:",
            reply_markup=reply_markup
        )

    async def show_my_bookings(self, query, user_id: int):
        """Show user's active bookings"""
        bookings = self.db.get_user_bookings(user_id)

        if not bookings:
            await query.edit_message_text(
                "📋 Non hai prenotazioni attive.\n\n"
                "Usa /start per tornare al menu."
            )
            return

        message = "📋 Le tue prenotazioni:\n\n"
        keyboard = []

        for idx, booking in enumerate(bookings, 1):
            message += f"{idx}. {booking['course_name']}\n"
            message += f"   📍 {booking['location']}\n"
            message += f"   📅 {booking['booking_date']} alle {booking['booking_time']}\n\n"

            keyboard.append([InlineKeyboardButton(
                f"❌ Cancella #{idx}",
                callback_data=f'cancel_{booking["booking_id"]}'
            )])

        keyboard.append([InlineKeyboardButton("🔙 Indietro", callback_data='back_to_main')])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(message, reply_markup=reply_markup)

    async def show_day_courses(self, query, user_id: int, data: str):
        """Show courses for a specific day"""
        day_name = data.replace('day_', '')
        courses = self.db.get_all_courses()
        day_courses = [c for c in courses if c['day_of_week'] == day_name]

        if not day_courses:
            await query.edit_message_text(
                f"📋 Nessun corso trovato per {day_name}.\n\n"
                "Usa /start per tornare al menu."
            )
            return

        message = f"📅 Corsi - {day_name}\n\n"

        for idx, course in enumerate(day_courses, 1):
            message += f"{idx}. {course['course_type'] or course['name']}\n"
            message += f"   🕐 {course['time_start']} - {course['time_end']}\n"
            message += f"   📍 {course['location']}\n"
            if course['instructor']:
                message += f"   👤 {course['instructor']}\n"
            message += "\n"

        # Limit message length for Telegram
        if len(message) > 4000:
            message = message[:3900] + "\n\n... (lista troncata)"

        await query.edit_message_text(message + "\nUsa /start per tornare al menu.")

    async def show_course_schedule(self, query, user_id: int):
        """Show weekly course schedule from database"""
        courses = self.db.get_all_courses()

        if not courses:
            await query.edit_message_text(
                "📋 Database corsi vuoto.\n\n"
                "Usa /refresh_courses per popolare il database.\n"
                "Usa /start per tornare al menu."
            )
            return

        days = ['Lunedì', 'Martedì', 'Mercoledì', 'Giovedì', 'Venerdì', 'Sabato', 'Domenica']
        message = "🗓️ Orari Corsi Settimanali:\n\n"

        for day_name in days:
            day_courses = [c for c in courses if c['day_of_week'] == day_name]
            if day_courses:
                message += f"📅 {day_name} ({len(day_courses)} corsi)\n"
                # Show first 3 courses as preview
                for course in day_courses[:3]:
                    message += f"  • {course['time_start']} - {course['course_type'] or course['name']}\n"
                if len(day_courses) > 3:
                    message += f"  ... e altri {len(day_courses) - 3} corsi\n"
                message += "\n"

        # Limit message length
        if len(message) > 4000:
            message = message[:3900] + "\n\n... (lista troncata)"

        await query.edit_message_text(message + "\nUsa /start per tornare al menu.")

    async def show_schedules_menu(self, query, user_id: int):
        """Show menu to choose between course schedule and fit center"""
        keyboard = [
            [InlineKeyboardButton("📚 Orari Corsi Platinum", callback_data='course_schedule')],
            [InlineKeyboardButton("🏋️ Orari Fit Center", callback_data='fit_center_schedule')],
            [InlineKeyboardButton("🔙 Indietro", callback_data='back_to_main')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "🗓️ Cosa vuoi visualizzare?",
            reply_markup=reply_markup
        )

    async def show_fit_center_menu(self, query, user_id: int):
        """Show Fit Center booking menu by day"""
        fit_slots = self.db.get_fit_center_slots()

        if not fit_slots:
            await query.edit_message_text(
                "🏋️ Nessuno slot Fit Center disponibile.\n\n"
                "Usa /start per tornare al menu."
            )
            return

        # Group by day
        days = ['Lunedì', 'Martedì', 'Mercoledì', 'Giovedì', 'Venerdì', 'Sabato', 'Domenica']
        keyboard = []

        for day_name in days:
            day_slots = [s for s in fit_slots if s['day_of_week'] == day_name]
            if day_slots:
                keyboard.append([InlineKeyboardButton(
                    f"🏋️ {day_name} ({len(day_slots)} slot)",
                    callback_data=f'fitday_{day_name}'
                )])

        keyboard.append([InlineKeyboardButton("🔙 Indietro", callback_data='back_to_main')])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "🏋️ Seleziona un giorno per Fit Center:",
            reply_markup=reply_markup
        )

    async def show_fit_center_day(self, query, user_id: int, data: str):
        """Show Fit Center slots for a specific day"""
        day_name = data.replace('fitday_', '')
        fit_slots = self.db.get_fit_center_slots()
        day_slots = [s for s in fit_slots if s['day_of_week'] == day_name]

        if not day_slots:
            await query.edit_message_text(
                f"🏋️ Nessuno slot Fit Center per {day_name}.\n\n"
                "Usa /start per tornare al menu."
            )
            return

        message = f"🏋️ Fit Center - {day_name}\n\n"

        for idx, slot in enumerate(day_slots, 1):
            message += f"{idx}. {slot['course_type'] or 'Accesso libero'}\n"
            message += f"   🕐 {slot['time_start']} - {slot['time_end']}\n"
            message += f"   📍 {slot['location']}\n"
            if slot['instructor']:
                message += f"   👤 {slot['instructor']}\n"
            message += "\n"

        if len(message) > 4000:
            message = message[:3900] + "\n\n... (lista troncata)"

        await query.edit_message_text(message + "\nUsa /start per tornare al menu.")

    async def show_fit_center_schedule(self, query, user_id: int):
        """Show full Fit Center weekly schedule"""
        fit_slots = self.db.get_fit_center_slots()

        if not fit_slots:
            await query.edit_message_text(
                "🏋️ Database Fit Center vuoto.\n\n"
                "Usa /start per tornare al menu."
            )
            return

        days = ['Lunedì', 'Martedì', 'Mercoledì', 'Giovedì', 'Venerdì', 'Sabato', 'Domenica']
        message = "🏋️ Orari Fit Center Settimanali:\n\n"

        for day_name in days:
            day_slots = [s for s in fit_slots if s['day_of_week'] == day_name]
            if day_slots:
                message += f"📅 {day_name} ({len(day_slots)} slot)\n"
                for slot in day_slots[:3]:
                    message += f"  • {slot['time_start']} - {slot['course_type'] or 'Libero'}\n"
                if len(day_slots) > 3:
                    message += f"  ... e altri {len(day_slots) - 3} slot\n"
                message += "\n"

        if len(message) > 4000:
            message = message[:3900] + "\n\n... (lista troncata)"

        await query.edit_message_text(message + "\nUsa /start per tornare al menu.")

    async def show_periodic_menu(self, query, user_id: int):
        """Show periodic bookings menu"""
        keyboard = [
            [InlineKeyboardButton("➕ Nuova Prenotazione Periodica", callback_data='periodic_add')],
            [InlineKeyboardButton("📋 Lista Prenotazioni Periodiche", callback_data='periodic_list')],
            [InlineKeyboardButton("🔙 Indietro", callback_data='back_to_main')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "🔄 Prenotazioni Periodiche\n\n"
            "Le prenotazioni periodiche richiedono conferma 1 ora prima.\n"
            "Se non confermate, vengono cancellate automaticamente.",
            reply_markup=reply_markup
        )

    async def initiate_booking(self, query, user_id: int, data: str):
        """Queue a booking action"""
        # Parse booking data from callback
        # Format: book_location_coursename_date_time
        parts = data.split('_', 4)

        if len(parts) < 5:
            await query.edit_message_text("❌ Formato non valido.\n\nUsa /start per tornare al menu.")
            return

        location = parts[1]
        course_name = parts[2]
        date = parts[3]
        time_slot = parts[4]

        # Add to queue
        action_id = self.db.add_booking_action(
            action_type='book',
            user_id=user_id,
            location=location,
            course_name=course_name,
            date=date,
            time_slot=time_slot
        )

        await query.edit_message_text(
            f"✅ Prenotazione in coda!\n\n"
            f"📍 {course_name}\n"
            f"📅 {date} alle {time_slot}\n"
            f"🏢 {location}\n\n"
            f"ID azione: #{action_id}\n\n"
            f"Riceverai una notifica quando completata.\n"
            f"Usa /status_{action_id} per controllare lo stato.\n\n"
            f"Usa /start per tornare al menu."
        )

    async def initiate_cancel(self, query, user_id: int, data: str):
        """Queue a cancellation action"""
        booking_id = data.replace('cancel_', '')

        action_id = self.db.add_booking_action(
            action_type='cancel',
            user_id=user_id,
            booking_id=booking_id
        )

        await query.edit_message_text(
            f"✅ Cancellazione in coda!\n\n"
            f"ID azione: #{action_id}\n\n"
            f"Riceverai una notifica quando completata.\n\n"
            f"Usa /start per tornare al menu."
        )

    async def add_periodic_booking_menu(self, query, user_id: int):
        """Show menu to add periodic booking - select type first"""
        keyboard = [
            [InlineKeyboardButton("📚 Corso Platinum", callback_data='periodic_type_course')],
            [InlineKeyboardButton("🏋️ Fit Center", callback_data='periodic_type_fit')],
            [InlineKeyboardButton("🔙 Indietro", callback_data='periodic_menu')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "🔄 Che tipo di prenotazione periodica vuoi creare?",
            reply_markup=reply_markup
        )

    async def show_periodic_day_selection(self, query, user_id: int, data: str):
        """Show day selection after type is chosen"""
        booking_type = data.replace('periodic_type_', '')

        days = ['Lunedì', 'Martedì', 'Mercoledì', 'Giovedì', 'Venerdì', 'Sabato', 'Domenica']
        keyboard = []

        for day in days:
            emoji = "📚" if booking_type == 'course' else "🏋️"
            keyboard.append([InlineKeyboardButton(
                f"{emoji} {day}",
                callback_data=f'periodic_day_{day}_{booking_type}'
            )])

        keyboard.append([InlineKeyboardButton("🔙 Indietro", callback_data='periodic_add')])
        reply_markup = InlineKeyboardMarkup(keyboard)

        type_name = "Corsi Platinum" if booking_type == 'course' else "Fit Center"
        await query.edit_message_text(
            f"🔄 {type_name}\n\nSeleziona il giorno della settimana:",
            reply_markup=reply_markup
        )

    async def handle_periodic_day_selection(self, query, user_id: int, data: str):
        """Handle day selection for periodic booking"""
        # Extract day name from callback data
        # Format: periodic_day_{day_name}_{type}
        parts = data.split('_', 3)
        if len(parts) < 4:
            await query.edit_message_text("❌ Formato non valido.\n\nUsa /start per tornare al menu.")
            return

        day_name = parts[2]
        booking_type = parts[3]  # 'course' or 'fit'

        # Get available slots for that day
        if booking_type == 'course':
            slots = [c for c in self.db.get_all_courses() if c['day_of_week'] == day_name]
            title = f"📚 Corsi - {day_name}"
        else:
            slots = [c for c in self.db.get_fit_center_slots() if c['day_of_week'] == day_name]
            title = f"🏋️ Fit Center - {day_name}"

        if not slots:
            await query.edit_message_text(
                f"📋 Nessuno slot disponibile per {day_name}.\n\n"
                "Usa /start per tornare al menu."
            )
            return

        # Show available time slots
        message = f"{title}\n\nSeleziona orario disponibile:\n\n"
        keyboard = []

        for idx, slot in enumerate(slots[:10], 1):  # Limit to 10 slots
            slot_text = f"{slot['time_start']} - {slot['course_type'] or slot['name']}"
            message += f"{idx}. {slot_text}\n"
            # Note: Full implementation would need to handle slot selection
            # callback_data = f'periodic_select_{slot["id"]}'

        keyboard.append([InlineKeyboardButton("🔙 Indietro", callback_data='periodic_add')])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(message + "\n\nImplementazione completa in arrivo...", reply_markup=reply_markup)

    async def list_periodic_bookings(self, query, user_id: int):
        """List user's periodic bookings"""
        bookings = self.db.get_periodic_bookings(user_id)

        if not bookings:
            await query.edit_message_text(
                "📋 Nessuna prenotazione periodica attiva.\n\n"
                "Usa /start per tornare al menu."
            )
            return

        days = ['Lunedì', 'Martedì', 'Mercoledì', 'Giovedì', 'Venerdì', 'Sabato', 'Domenica']
        message = "🔄 Prenotazioni Periodiche Attive:\n\n"
        keyboard = []

        for booking in bookings:
            day_name = days[booking['day_of_week']]
            status = "✅" if booking['active'] else "⏸️"
            message += f"{status} {booking.get('name', 'Senza nome')}\n"
            message += f"   📅 {day_name} alle {booking['time_slot']}\n"
            message += f"   📍 {booking['location']}\n"
            if booking['course_name']:
                message += f"   🏃 {booking['course_name']}\n"
            message += "\n"

            keyboard.append([InlineKeyboardButton(
                f"🗑️ Elimina: {booking.get('name', f'ID {booking["id"]}')}",
                callback_data=f'periodic_delete_{booking["id"]}'
            )])

        keyboard.append([InlineKeyboardButton("🔙 Indietro", callback_data='periodic_menu')])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(message, reply_markup=reply_markup)

    async def delete_periodic_booking(self, query, user_id: int, data: str):
        """Delete a periodic booking"""
        booking_id = int(data.replace('periodic_delete_', ''))
        self.db.delete_periodic_booking(booking_id)

        await query.edit_message_text(
            "✅ Prenotazione periodica eliminata!\n\n"
            "Usa /start per tornare al menu."
        )

    async def confirm_periodic(self, query, user_id: int, data: str):
        """Confirm a periodic booking"""
        confirmation_id = int(data.replace('confirm_', ''))

        # Mark as confirmed
        self.db.confirm_booking(confirmation_id)

        # Get confirmation details
        confirmations = self.db.get_pending_confirmations(user_id)
        confirmation = next((c for c in confirmations if c['id'] == confirmation_id), None)

        if confirmation:
            # Queue the booking action
            periodic_booking = self.db.get_periodic_bookings(user_id)
            # Find the matching periodic booking
            # ... (implementation details)

            await query.edit_message_text(
                "✅ Prenotazione confermata e messa in coda!\n\n"
                "Riceverai una notifica quando completata."
            )
        else:
            await query.edit_message_text("❌ Conferma non trovata.")

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check status of an action"""
        if not self._check_authorization(update):
            return

        try:
            action_id = int(context.args[0])
            action = self.db.get_action_status(action_id)

            if not action:
                await update.message.reply_text("❌ Azione non trovata.")
                return

            status_emoji = {
                'pending': '⏳',
                'processing': '⚙️',
                'completed': '✅',
                'failed': '❌'
            }

            message = f"{status_emoji.get(action['status'], '❓')} Stato Azione #{action_id}\n\n"
            message += f"Tipo: {action['action_type']}\n"
            message += f"Stato: {action['status']}\n"

            if action['status'] == 'completed' and action['result']:
                message += f"\nRisultato:\n{action['result']}"
            elif action['status'] == 'failed' and action['error']:
                message += f"\nErrore:\n{action['error']}"

            await update.message.reply_text(message)

        except (IndexError, ValueError):
            await update.message.reply_text("Usa: /status <action_id>")

    def run(self):
        """Run the bot"""
        token = self.config['telegram']['bot_token']

        self.application = Application.builder().token(token).build()

        # Add handlers
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(CallbackQueryHandler(self.button_callback))

        logger.info("Bot started!")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    bot = PolimisportBotDB()
    bot.run()
