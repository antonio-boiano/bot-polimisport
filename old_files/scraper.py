#!/usr/bin/env python3
"""
Polimisport Course Schedule Scraper
Extracts weekly course schedules from the website (date-agnostic weekly periodicity)
"""

import logging
from typing import Dict, List
from collections import defaultdict
import re
from datetime import datetime, timedelta

from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

from otp_extractor import get_otp_info

from collections import defaultdict
import unicodedata

logger = logging.getLogger(__name__)

# ---------------------------
# HTML parsing helpers (WEEKLY, no dates)
# ---------------------------

RE_DURATION = re.compile(r"(\d+)\s*min", re.IGNORECASE)
RE_AVAIL_NUM = re.compile(r"Posti\s+disponibili\s*:\s*(\d+)", re.IGNORECASE)


def _norm_wd(s: str) -> str:
    # Keep accents, but normalize Unicode form (prevents weird composed/decomposed mismatches)
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
    """
    Parses a slot description element like:
      'Giuriati - Corsi Platinum - ' + <span class="skill">XYZ</span>
    or
      'Giuriati - Fit Center'
    Returns:
      (location, course, skill, full)
    """

    if not desc_el:
        return None, None, None, None

    # Extract skill
    skill_el = desc_el.find("span", class_="skill")
    skill = _text(skill_el)

    # Remove the skill span from the HTML to isolate the text part
    html = desc_el.decode_contents()
    if skill_el:
        html = html.replace(str(skill_el), "")
    base = BeautifulSoup(html, "html.parser").get_text(" ", strip=True).strip(" -\u00a0")

    # Split base by ' - '
    parts = [p.strip() for p in base.split(" - ") if p.strip()]

    location = parts[0] if len(parts) > 0 else None
    course = parts[1] if len(parts) > 1 else None

    # Construct full string
    full = " - ".join([p for p in parts if p]) + (f" - {skill}" if skill else "")

    return location, course, skill, full


def _parse_event(weekday_it: str, ev_el) -> Dict:
    classes = ev_el.get("class", [])
    status = None
    for st in ("slot-available", "slot-booked", "slot-disabled"):
        if st in classes:
            status = st.replace("slot-", "")
            break

    icon_i = ev_el.select_one(".slot-icon i")
    icon_classes = " ".join(icon_i.get("class", [])) if icon_i else None

    time_start = _text(ev_el.select_one(".slot-time .time-start"))
    duration_txt = _text(ev_el.select_one(".slot-time .time-duration"))
    duration_min = _duration_min(duration_txt)
    time_end = _end_time(time_start, duration_min)

    location_path, course_type, skill, activity_full = _location_and_skill(ev_el.select_one(".slot-description"))

    instructor = _text(ev_el.select_one(".slot-description2"))
    if instructor:
        instructor = re.sub(r"^\s*con\s+", "", instructor, flags=re.IGNORECASE).strip()

    avail_txt = _text(ev_el.select_one(".slot-description3"))
    m = RE_AVAIL_NUM.search(avail_txt or "")
    avail_count = int(m.group(1)) if m else None

    notes_before = _text(ev_el.select_one(".slot-notes.slot-notes-before"))
    notes_after = _text(ev_el.select_one(".slot-notes.slot-notes-after"))

    return {
        "weekday_it": weekday_it,         # "Lunedì", "Martedì", ...
        "status": status,                 # available | booked | disabled
        "time_start": time_start,         # "12:20"
        "duration_min": duration_min,     # 55
        "time_end": time_end,             # "13:15"
        "location_path": location_path,   # "Giuriati - Corsi Platinum"
        "skill": skill,                   # "PILATES MATWORK"
        "course_type": course_type,       # "CORSO" or "FIT CENTER"
        "activity_full": activity_full,   # "Giuriati - Corsi Platinum - PILATES MATWORK"
        "instructor": instructor,         # "MENDINI ANNA"
        "availability_text": avail_txt,   # e.g., "Posti disponibili: 7"
        "availability_count": avail_count,
        "notes_before": notes_before,
        "notes_after": notes_after,
        "icon_classes": icon_classes,
        
    }

def parse_weekly_pattern_from_html(html: str, keep_empty_days: bool = False, dedupe: bool = True) -> Dict[str, List[Dict]]:
    """
    Parse BOTH #day-schedule-container and #day-schedule-repository,
    return dict keyed by Italian weekday, ignoring actual dates.
    """
    soup = BeautifulSoup(html, "lxml")
    weekly = defaultdict(list)

    # Collect day-schedule blocks from visible container and repository
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

        if not slots:
            empty_el = day.select_one(".day-schedule-empty")
            is_visible_empty = (empty_el and "display:none" not in (empty_el.get("style") or ""))
            if keep_empty_days and is_visible_empty:
                weekly[weekday_it].append({
                    "weekday_it": weekday_it,
                    "status": "empty",
                    "time_start": None,
                    "duration_min": None,
                    "time_end": None,
                    "location_path": None,
                    "skill": None,
                    "course_type": None,
                    "activity_full": None,
                    "instructor": None,
                    "availability_text": _text(empty_el),
                    "availability_count": None,
                    "notes_before": None,
                    "notes_after": None,
                    "icon_classes": None,
                })
            continue

        for ev in slots:
            weekly[weekday_it].append(_parse_event(weekday_it, ev))

    # Sort and dedupe inside each weekday
    for wd, items in weekly.items():
        items.sort(key=lambda r: (r.get("time_start") or "99:99"))
        if dedupe:
            seen = set()
            deduped = []
            for r in items:
                key = (r.get("time_start"), r.get("activity_full"), r.get("instructor"), r.get("status"))
                if key not in seen:
                    seen.add(key)
                    deduped.append(r)
            weekly[wd] = deduped

    return dict(weekly)

# ---------------------------
# Playwright scraper
# ---------------------------


class CourseScraper:
    def __init__(self, config: dict):
        """Initialize scraper with configuration"""
        self.config = config
        self.username = config['username']
        self.password = config['password']
        self.otp_path = config['otpatu']

    
    
    async def _login(self, page):
        """Perform login to Polimisport website"""
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

            otp = otp_info['current_otp']
            await page.get_by_role('textbox', name='OTP').fill(otp)
            await page.get_by_role('button', name='Continua').click()

            await page.wait_for_timeout(2000)
            logger.info("Login successful")
            return True

        except Exception as e:
            logger.error(f"Login failed: {e}")
            raise
    
    async def _move_date_forward(self, page, days=1):
        """Move the calendar forward by a number of days"""
        for _ in range(days):
            await page.click("a.btn-move-date[data-date-target='+1']")
            await page.wait_for_timeout(200)
        
        await page.wait_for_timeout(3000)
        
    
    async def _move_to_fit_center(self, page):
        """Move to fit center of the page"""
        await page.get_by_role("link", name="Attività").click()
        
        await page.wait_for_timeout(500)
        await page.get_by_role("link", name="Giuriati - Fit Center").click()
        await page.wait_for_timeout(3000)

    async def _goto_giuriati_platinum(self, page):
        """Navigate to Booking → Nuova Prenotazione → Giuriati - Corsi Platinum"""
        await page.get_by_text('Booking Prenotazioni e noleggi View more').click()
        await page.get_by_role('link', name='Nuova Prenotazione').click()

        # Close info modal if present
        try:
            await page.get_by_role('button', name='Chiudi questa informativa').click(timeout=2000)
        except Exception:
            pass

        await page.get_by_role('link', name='Giuriati - Corsi Platinum').click()
        # Wait for the calendar to render (JS builds DOM)
        await page.wait_for_timeout(3000)

    async def get_weekly_schedule(self, headless: bool = True) -> Dict[str, List[Dict]]:
        """
        Scrape the weekly course schedule, grouped by weekday (no calendar dates).
        """
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            page = await browser.new_page()

            try:
                await self._login(page)
                await self._goto_giuriati_platinum(page)
                
                # Use only one accumulator, then build the final dict at the end
                weekly_dd = defaultdict(list)
                
                # Grab HTML and parse both visible + repository day schedules
                html = await page.content()
                parsed = parse_weekly_pattern_from_html(html, keep_empty_days=False, dedupe=True)
                
                for k, v in parsed.items():
                    weekly_dd[_norm_wd(k)].extend(v)
                
                await self._move_date_forward(page, days=3)
                
                html = await page.content()
                parsed = parse_weekly_pattern_from_html(html, keep_empty_days=False, dedupe=True)
                for k, v in parsed.items():
                    weekly_dd[_norm_wd(k)].extend(v)
                
                await self._move_date_forward(page, days=3)
                
                html = await page.content()
                parsed = parse_weekly_pattern_from_html(html, keep_empty_days=False, dedupe=True)
                for k, v in parsed.items():
                    weekly_dd[_norm_wd(k)].extend(v)
                
                weekly_fit = defaultdict(list)
                
                await self._move_to_fit_center(page)
                
                html = await page.content()
                parsed = parse_weekly_pattern_from_html(html, keep_empty_days=False, dedupe=True)
                for k, v in parsed.items():
                    weekly_fit[_norm_wd(k)].extend(v)
                
                
                await self._move_date_forward(page, days=3)
                
                html = await page.content()
                parsed = parse_weekly_pattern_from_html(html, keep_empty_days=False, dedupe=True)
                for k, v in parsed.items():
                    weekly_fit[_norm_wd(k)].extend(v)
                
                await self._move_date_forward(page, days=3)
                
                html = await page.content()
                parsed = parse_weekly_pattern_from_html(html, keep_empty_days=False, dedupe=True)
                for k, v in parsed.items():
                    weekly_fit[_norm_wd(k)].extend(v)

                
                def build_weekly_dict(weekly_dd):
                    WEEKDAYS = ["Lunedì","Martedì","Mercoledì","Giovedì","Venerdì","Sabato","Domenica"]
                    # Build final weekly dict in fixed order and dedupe across merged pages
                    weekly: Dict[str, List[Dict]] = {}
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
                    
                weekly = build_weekly_dict(weekly_dd)
                weekly_fit = build_weekly_dict(weekly_fit)
                
                await browser.close()
                total = sum(len(v) for v in weekly.values())
                logger.info(f"Weekly schedule extracted: {total} slots")
                total_fit = sum(len(v) for v in weekly_fit.values())
                logger.info(f"Weekly Fit Center schedule extracted: {total_fit} slots")
                return weekly, weekly_fit

            except Exception as e:
                logger.error(f"Failed to get schedule: {e}")
                await browser.close()
                raise

    async def get_available_slots(self, location: str, headless: bool = True) -> List[Dict]:
        """
        Get currently available slots for a specific location (weekly view on current page).
        `location` supports 'giuriati_platinum' for now.
        """
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            page = await browser.new_page()

            try:
                await self._login(page)

                # Navigate to booking section
                await page.get_by_text('Booking Prenotazioni e noleggi View more').click()
                await page.get_by_role('link', name='Nuova Prenotazione').click()

                try:
                    await page.get_by_role('button', name='Chiudi questa informativa').click(timeout=2000)
                except Exception:
                    pass

                if location == 'giuriati_platinum':
                    await page.get_by_role('link', name='Giuriati - Corsi Platinum').click()
                else:
                    raise ValueError(f"Unsupported location: {location}")

                await page.wait_for_timeout(2000)

                # Parse only available slots from DOM
                html = await page.content()
                soup = BeautifulSoup(html, "lxml")

                slots = []
                for root_sel in ("#day-schedule-container", "#day-schedule-repository"):
                    root = soup.select_one(root_sel)
                    if not root:
                        continue
                    for day in root.select(".day-schedule"):
                        label = day.select_one(".day-schedule-label")
                        weekday_it = label.get_text(strip=True).split(",")[0].strip() if label else None
                        for ev in day.select(".day-schedule-slots .event-slot.slot-available"):
                            data = _parse_event(weekday_it or "", ev)
                            # Return a leaner record, but keep essential fields
                            slots.append({
                                "weekday_it": data["weekday_it"],
                                "time_start": data["time_start"],
                                "time_end": data["time_end"],
                                "activity_full": data["activity_full"],
                                "instructor": data["instructor"],
                                "availability_count": data["availability_count"],
                                "availability_text": data["availability_text"],
                            })

                await browser.close()
                return slots

            except Exception as e:
                logger.error(f"Failed to get available slots: {e}")
                await browser.close()
                raise


def main():
    import asyncio
    import json
    logging.basicConfig(level=logging.INFO)

    # Load config
    with open('../config.json', 'r') as f:
        config = json.load(f)

    scraper = CourseScraper(config)

    # Get weekly schedule (headless=False to watch it)
    weekly, weekly_fit = asyncio.run(scraper.get_weekly_schedule(headless=False))

    # Pretty print
    import pprint
    pprint.pprint(weekly)
    pprint.pprint(weekly_fit)

if __name__ == '__main__':
    main()
