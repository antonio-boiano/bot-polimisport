#!/usr/bin/env python3
"""
Polimisport Bot - All-in-One Edition
Single file containing all functionality:
- Telegram bot interface
- Database management
- Web scraping (courses & bookings)
- OTP handling
- Automatic refresh on login
"""

import asyncio
import json
import logging
import sqlite3
import time
import re
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import defaultdict
import unicodedata

# Telegram imports
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Playwright imports
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

# OTP import
import pyotp

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ============================================================================
# DATABASE MODULE
# ============================================================================

class Database:
    """SQLite database handler"""

    def __init__(self, db_path='polimisport.db'):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def _init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Courses table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS courses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    location TEXT NOT NULL,
                    day_of_week TEXT NOT NULL,
                    time_start TEXT NOT NULL,
                    time_end TEXT NOT NULL,
                    course_type TEXT,
                    instructor TEXT,
                    is_fit_center INTEGER DEFAULT 0,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # User bookings
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_bookings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    booking_id TEXT UNIQUE,
                    course_name TEXT NOT NULL,
                    location TEXT NOT NULL,
                    booking_date TEXT NOT NULL,
                    booking_time TEXT NOT NULL,
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

    def add_course(self, course: Dict):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO courses
                (name, location, day_of_week, time_start, time_end, course_type, instructor, is_fit_center)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                course['name'],
                course['location'],
                course['day_of_week'],
                course['time_start'],
                course['time_end'],
                course.get('course_type'),
                course.get('instructor'),
                1 if course.get('is_fit_center') else 0
            ))

    def get_all_courses(self, include_fit_center: bool = False) -> List[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if include_fit_center:
                cursor.execute('SELECT * FROM courses ORDER BY day_of_week, time_start')
            else:
                cursor.execute('SELECT * FROM courses WHERE is_fit_center = 0 ORDER BY day_of_week, time_start')
            return [dict(row) for row in cursor.fetchall()]

    def get_fit_center_slots(self) -> List[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM courses WHERE is_fit_center = 1 ORDER BY day_of_week, time_start')
            return [dict(row) for row in cursor.fetchall()]

    def clear_courses(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM courses')

    def add_user_booking(self, user_id: int, booking: Dict):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO user_bookings
                (user_id, booking_id, course_name, location, booking_date, booking_time)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                user_id,
                booking['booking_id'],
                booking['course_name'],
                booking['location'],
                booking['booking_date'],
                booking['booking_time']
            ))

    def get_user_bookings(self, user_id: int, status: str = 'active') -> List[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM user_bookings
                WHERE user_id = ? AND status = ?
                ORDER BY booking_date, booking_time
            ''', (user_id, status))
            return [dict(row) for row in cursor.fetchall()]

    def update_booking_status(self, booking_id: str, status: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE user_bookings
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE booking_id = ?
            ''', (status, booking_id))

    def clear_bookings(self, user_id: int):
        """Clear all bookings for sync"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM user_bookings WHERE user_id = ?', (user_id,))


# ============================================================================
# OTP MODULE
# ============================================================================

def get_otp_info(otpauth_url: str) -> Dict:
    """Generate OTP from otpauth URL"""
    from urllib.parse import urlparse, parse_qs

    parsed = urlparse(otpauth_url)
    params = parse_qs(parsed.query)
    secret = params['secret'][0]
    period = int(params.get('period', ['30'])[0])

    totp = pyotp.TOTP(secret, interval=period)
    otp_code = totp.now()
    remaining = period - (int(time.time()) % period)

    return {
        'current_otp': otp_code,
        'time_remaining': remaining
    }


# ============================================================================
# SCRAPER MODULE
# ============================================================================

# HTML parsing helpers
RE_DURATION = re.compile(r"(\d+)\s*min", re.IGNORECASE)

def _norm_wd(s: str) -> str:
    return unicodedata.normalize("NFC", s.strip())

def _text(el):
    return el.get_text(strip=True) if el else None

def _duration_min(txt):
    if not txt:
        return None
    m = RE_DURATION.search(txt)
    return int(m.group(1)) if m else None

def _end_time(hhmm, minutes):
    if not hhmm or minutes is None:
        return None
    try:
        t = datetime.strptime(hhmm, "%H:%M")
        return (t + timedelta(minutes=minutes)).strftime("%H:%M")
    except Exception:
        return None

def _location_and_skill(desc_el):
    if not desc_el:
        return None, None, None, None

    skill_el = desc_el.find("span", class_="skill")
    skill = _text(skill_el)

    html = desc_el.decode_contents()
    if skill_el:
        html = html.replace(str(skill_el), "")
    base = BeautifulSoup(html, "html.parser").get_text(" ", strip=True).strip(" -\xa0")

    parts = [p.strip() for p in base.split(" - ") if p.strip()]
    location = parts[0] if len(parts) > 0 else None
    course = parts[1] if len(parts) > 1 else None
    full = " - ".join([p for p in parts if p]) + (f" - {skill}" if skill else "")

    return location, course, skill, full

def _parse_event(weekday_it: str, ev_el) -> Dict:
    classes = ev_el.get("class", [])
    status = None
    for st in ("slot-available", "slot-booked", "slot-disabled"):
        if st in classes:
            status = st.replace("slot-", "")
            break

    time_start = _text(ev_el.select_one(".slot-time .time-start"))
    duration_txt = _text(ev_el.select_one(".slot-time .time-duration"))
    duration_min = _duration_min(duration_txt)
    time_end = _end_time(time_start, duration_min)

    location_path, course_type, skill, activity_full = _location_and_skill(ev_el.select_one(".slot-description"))
    instructor = _text(ev_el.select_one(".slot-description2"))
    if instructor:
        instructor = re.sub(r"^\s*con\s+", "", instructor, flags=re.IGNORECASE).strip()

    return {
        "weekday_it": weekday_it,
        "status": status,
        "time_start": time_start,
        "time_end": time_end,
        "location_path": location_path,
        "skill": skill,
        "course_type": course_type,
        "activity_full": activity_full,
        "instructor": instructor,
    }

def parse_weekly_pattern_from_html(html: str) -> Dict[str, List[Dict]]:
    soup = BeautifulSoup(html, "lxml")
    weekly = defaultdict(list)

    day_blocks = []
    for root_sel in ("#day-schedule-container", "#day-schedule-repository"):
        root = soup.select_one(root_sel)
        if root:
            day_blocks.extend(root.select(".day-schedule"))

    for day in day_blocks:
        label_el = day.select_one(".day-schedule-label")
        if not label_el:
            continue
        label = label_el.get_text(strip=True)
        weekday_it = label.split(",")[0].strip() if "," in label else label.split()[0]
        weekday_it = unicodedata.normalize("NFC", weekday_it.strip())

        slots_container = day.select_one(".day-schedule-slots")
        slots = slots_container.select(".event-slot") if slots_container else []

        for ev in slots:
            weekly[weekday_it].append(_parse_event(weekday_it, ev))

    # Sort and dedupe
    for wd, items in weekly.items():
        items.sort(key=lambda r: (r.get("time_start") or "99:99"))
        seen = set()
        deduped = []
        for r in items:
            key = (r.get("time_start"), r.get("activity_full"), r.get("instructor"), r.get("status"))
            if key not in seen:
                seen.add(key)
                deduped.append(r)
        weekly[wd] = deduped

    return dict(weekly)


class PolimisportScraper:
    """Handles all web scraping with single login session"""

    def __init__(self, config: dict):
        self.config = config
        self.username = config['username']
        self.password = config['password']
        self.otp_path = config['otpatu']
        self.page = None
        self.browser = None
        self.context = None

    async def login(self, page):
        """Perform login"""
        try:
            await page.goto('https://www.sport.polimi.it/')
            await page.get_by_role('link', name='Area Riservata').click()
            await page.get_by_role('button', name='Accedi al tuo account').click()

            await page.get_by_role('textbox', name='Codice Persona').fill(self.username)
            await page.get_by_role('textbox', name='Password').fill(self.password)
            await page.get_by_role('button', name='Accedi').click()

            await page.get_by_role('textbox', name='OTP').click()

            otp_info = get_otp_info(self.otp_path)
            if otp_info['time_remaining'] < 2:
                logger.info("Waiting for new OTP code...")
                await page.wait_for_timeout(2000)
                otp_info = get_otp_info(self.otp_path)

            await page.get_by_role('textbox', name='OTP').fill(otp_info['current_otp'])
            await page.get_by_role('button', name='Continua').click()

            await page.wait_for_timeout(2000)
            logger.info("Login successful")
            return True
        except Exception as e:
            logger.error(f"Login failed: {e}")
            raise

    async def start_session(self, headless: bool = True):
        """Start browser session with login"""
        p = await async_playwright().start()
        self.browser = await p.chromium.launch(headless=headless)
        self.context = await self.browser.new_context()
        self.page = await self.context.new_page()
        await self.login(self.page)
        return self.page

    async def close_session(self):
        """Close browser session"""
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()

    async def get_weekly_schedule(self, page) -> tuple[Dict, Dict]:
        """Scrape weekly schedule (courses + fit center)"""
        # Navigate to Giuriati Platinum
        await page.get_by_text('Booking Prenotazioni e noleggi View more').click()
        await page.get_by_role('link', name='Nuova Prenotazione').click()

        try:
            await page.get_by_role('button', name='Chiudi questa informativa').click(timeout=2000)
        except:
            pass

        await page.get_by_role('link', name='Giuriati - Corsi Platinum').click()
        await page.wait_for_timeout(3000)

        # Scrape courses
        weekly_courses = defaultdict(list)
        for _ in range(3):
            html = await page.content()
            parsed = parse_weekly_pattern_from_html(html)
            for k, v in parsed.items():
                weekly_courses[_norm_wd(k)].extend(v)
            await page.click("a.btn-move-date[data-date-target='+1']")
            await page.wait_for_timeout(3000)

        # Navigate to Fit Center
        await page.get_by_role("link", name="Attività").click()
        await page.wait_for_timeout(500)
        await page.get_by_role("link", name="Giuriati - Fit Center").click()
        await page.wait_for_timeout(3000)

        # Scrape fit center
        weekly_fit = defaultdict(list)
        for _ in range(3):
            html = await page.content()
            parsed = parse_weekly_pattern_from_html(html)
            for k, v in parsed.items():
                weekly_fit[_norm_wd(k)].extend(v)
            await page.click("a.btn-move-date[data-date-target='+1']")
            await page.wait_for_timeout(3000)

        # Build final dicts
        WEEKDAYS = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]

        def build_weekly_dict(weekly_dd):
            weekly = {}
            for wd in WEEKDAYS:
                items = list(weekly_dd.get(_norm_wd(wd), []))
                items.sort(key=lambda r: (r.get("time_start") or "99:99"))
                seen = set()
                deduped = []
                for r in items:
                    key = (r.get("time_start"), r.get("activity_full"), r.get("instructor"), r.get("status"))
                    if key not in seen:
                        seen.add(key)
                        deduped.append(r)
                weekly[wd] = deduped
            return weekly

        return build_weekly_dict(weekly_courses), build_weekly_dict(weekly_fit)

    async def get_user_bookings(self, page) -> List[Dict]:
        """Get current user bookings"""
        try:
            # Navigate to bookings
            await page.get_by_text('Booking Prenotazioni e noleggi View more').click()
            await page.wait_for_timeout(2000)

            # Extract bookings
            bookings = []
            # TODO: Implement actual extraction based on HTML structure
            # This is placeholder - adjust selectors based on actual page

            logger.info(f"Found {len(bookings)} bookings")
            return bookings
        except Exception as e:
            logger.error(f"Failed to get bookings: {e}")
            return []


# ============================================================================
# TELEGRAM BOT
# ============================================================================

class PolimisportBot:
    def __init__(self, config_path='config.json'):
        with open(config_path, 'r') as f:
            self.config = json.load(f)

        self.allowed_user_id = self.config['telegram']['allowed_user_id']
        self.db = Database()
        self.scraper = PolimisportScraper(self.config)
        self.last_refresh = None

    def _check_authorization(self, update: Update) -> bool:
        user_id = update.effective_user.id
        return user_id == self.allowed_user_id

    async def refresh_data(self):
        """Refresh courses and bookings with single login"""
        try:
            logger.info("Starting data refresh with single login...")

            # Start session
            page = await self.scraper.start_session(headless=True)

            # Get courses and fit center
            courses, fit_center = await self.scraper.get_weekly_schedule(page)

            # Get user bookings
            bookings = await self.scraper.get_user_bookings(page)

            # Close session
            await self.scraper.close_session()

            # Update database
            logger.info("Updating database...")
            self.db.clear_courses()

            seen = set()
            course_count = 0
            fit_count = 0

            # Add courses
            for day_name, day_courses in courses.items():
                for course in day_courses:
                    key = (day_name, course.get('time_start'), course.get('skill'), course.get('instructor'))
                    if key not in seen:
                        seen.add(key)
                        self.db.add_course({
                            'name': course.get("course_type"),
                            'location': course.get('location_path'),
                            'day_of_week': day_name,
                            'time_start': course.get('time_start'),
                            'time_end': course.get('time_end'),
                            'course_type': course.get('skill'),
                            'instructor': course.get('instructor'),
                            'is_fit_center': False
                        })
                        course_count += 1

            # Add fit center
            for day_name, day_slots in fit_center.items():
                for slot in day_slots:
                    key = (day_name, slot.get('time_start'), slot.get('skill'), slot.get('instructor'))
                    if key not in seen:
                        seen.add(key)
                        self.db.add_course({
                            'name': 'Fit Center',
                            'location': slot.get('location_path'),
                            'day_of_week': day_name,
                            'time_start': slot.get('time_start'),
                            'time_end': slot.get('time_end'),
                            'course_type': slot.get('skill'),
                            'instructor': slot.get('instructor'),
                            'is_fit_center': True
                        })
                        fit_count += 1

            # Update bookings
            self.db.clear_bookings(self.allowed_user_id)
            for booking in bookings:
                self.db.add_user_booking(self.allowed_user_id, booking)

            self.last_refresh = datetime.now()
            logger.info(f"Refresh complete: {course_count} courses, {fit_count} fit center, {len(bookings)} bookings")

            return {
                'courses': course_count,
                'fit_center': fit_count,
                'bookings': len(bookings),
                'timestamp': self.last_refresh.isoformat()
            }

        except Exception as e:
            logger.error(f"Refresh failed: {e}")
            raise

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_authorization(update):
            await update.message.reply_text("⛔ Non sei autorizzato ad usare questo bot.")
            return

        keyboard = [
            [InlineKeyboardButton("🔄 Aggiorna Dati", callback_data='refresh')],
            [InlineKeyboardButton("📅 Orari Corsi", callback_data='view_courses')],
            [InlineKeyboardButton("🏋️ Orari Fit Center", callback_data='view_fit')],
            [InlineKeyboardButton("📋 Le Mie Prenotazioni", callback_data='my_bookings')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        status = ""
        if self.last_refresh:
            status = f"\n\n🕐 Ultimo aggiornamento: {self.last_refresh.strftime('%d/%m/%Y %H:%M')}"

        await update.message.reply_text(
            f"👋 Benvenuto al Bot Polimisport!{status}\n\n"
            "Cosa vuoi fare?",
            reply_markup=reply_markup
        )

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        if not self._check_authorization(update):
            await query.edit_message_text("⛔ Non sei autorizzato.")
            return

        user_id = update.effective_user.id
        data = query.data

        if data == 'refresh':
            await query.edit_message_text("🔄 Aggiornamento in corso...\n(Login, scraping corsi, fit center e prenotazioni)")
            try:
                result = await self.refresh_data()
                await query.edit_message_text(
                    f"✅ Aggiornamento completato!\n\n"
                    f"📚 Corsi: {result['courses']}\n"
                    f"🏋️ Fit Center: {result['fit_center']}\n"
                    f"📋 Prenotazioni: {result['bookings']}\n\n"
                    f"Usa /start per tornare al menu."
                )
            except Exception as e:
                await query.edit_message_text(f"❌ Errore: {e}\n\nUsa /start per tornare al menu.")

        elif data == 'view_courses':
            await self.show_courses(query, user_id)
        elif data == 'view_fit':
            await self.show_fit_center(query, user_id)
        elif data == 'my_bookings':
            await self.show_my_bookings(query, user_id)
        elif data.startswith('day_courses_'):
            await self.show_day_courses(query, user_id, data)
        elif data.startswith('day_fit_'):
            await self.show_day_fit(query, user_id, data)
        elif data == 'back_to_main':
            await self.start(update, context)

    async def show_courses(self, query, user_id: int):
        courses = self.db.get_all_courses()
        if not courses:
            await query.edit_message_text(
                "📋 Database vuoto. Clicca 🔄 Aggiorna Dati.\n\nUsa /start per tornare al menu."
            )
            return

        days = ['Lunedì', 'Martedì', 'Mercoledì', 'Giovedì', 'Venerdì', 'Sabato', 'Domenica']
        keyboard = []

        for day in days:
            day_courses = [c for c in courses if c['day_of_week'] == day]
            if day_courses:
                keyboard.append([InlineKeyboardButton(
                    f"📅 {day} ({len(day_courses)} corsi)",
                    callback_data=f'day_courses_{day}'
                )])

        keyboard.append([InlineKeyboardButton("🔙 Indietro", callback_data='back_to_main')])
        await query.edit_message_text("📅 Seleziona giorno:", reply_markup=InlineKeyboardMarkup(keyboard))

    async def show_day_courses(self, query, user_id: int, data: str):
        day = data.replace('day_courses_', '')
        courses = [c for c in self.db.get_all_courses() if c['day_of_week'] == day]

        message = f"📅 Corsi - {day}\n\n"
        for idx, c in enumerate(courses, 1):
            message += f"{idx}. {c['course_type'] or c['name']}\n"
            message += f"   🕐 {c['time_start']} - {c['time_end']}\n"
            if c['instructor']:
                message += f"   👤 {c['instructor']}\n"
            message += "\n"

        if len(message) > 4000:
            message = message[:3900] + "\n\n..."

        await query.edit_message_text(message + "\nUsa /start per tornare al menu.")

    async def show_fit_center(self, query, user_id: int):
        slots = self.db.get_fit_center_slots()
        if not slots:
            await query.edit_message_text(
                "📋 Database vuoto. Clicca 🔄 Aggiorna Dati.\n\nUsa /start per tornare al menu."
            )
            return

        days = ['Lunedì', 'Martedì', 'Mercoledì', 'Giovedì', 'Venerdì', 'Sabato', 'Domenica']
        keyboard = []

        for day in days:
            day_slots = [s for s in slots if s['day_of_week'] == day]
            if day_slots:
                keyboard.append([InlineKeyboardButton(
                    f"🏋️ {day} ({len(day_slots)} slot)",
                    callback_data=f'day_fit_{day}'
                )])

        keyboard.append([InlineKeyboardButton("🔙 Indietro", callback_data='back_to_main')])
        await query.edit_message_text("🏋️ Seleziona giorno:", reply_markup=InlineKeyboardMarkup(keyboard))

    async def show_day_fit(self, query, user_id: int, data: str):
        day = data.replace('day_fit_', '')
        slots = [s for s in self.db.get_fit_center_slots() if s['day_of_week'] == day]

        message = f"🏋️ Fit Center - {day}\n\n"
        for idx, s in enumerate(slots, 1):
            message += f"{idx}. {s['course_type'] or 'Accesso libero'}\n"
            message += f"   🕐 {s['time_start']} - {s['time_end']}\n"
            if s['instructor']:
                message += f"   👤 {s['instructor']}\n"
            message += "\n"

        if len(message) > 4000:
            message = message[:3900] + "\n\n..."

        await query.edit_message_text(message + "\nUsa /start per tornare al menu.")

    async def show_my_bookings(self, query, user_id: int):
        bookings = self.db.get_user_bookings(user_id)

        if not bookings:
            await query.edit_message_text(
                "📋 Nessuna prenotazione attiva.\n\n"
                "Clicca 🔄 Aggiorna Dati per sincronizzare.\n\n"
                "Usa /start per tornare al menu."
            )
            return

        message = "📋 Le tue prenotazioni:\n\n"
        for idx, b in enumerate(bookings, 1):
            message += f"{idx}. {b['course_name']}\n"
            message += f"   📍 {b['location']}\n"
            message += f"   📅 {b['booking_date']} - {b['booking_time']}\n\n"

        await query.edit_message_text(message + "\nUsa /start per tornare al menu.")

    def run(self):
        token = self.config['telegram']['bot_token']
        self.application = Application.builder().token(token).build()

        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CallbackQueryHandler(self.button_callback))

        logger.info("🚀 Bot started!")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)


# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    bot = PolimisportBot()
    bot.run()
