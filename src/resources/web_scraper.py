"""
Web Scraper - Low-level website interaction
Handles all direct communication with sport.polimi.it
Includes HTML parsing and data extraction
"""

import logging
import re
import unicodedata
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from collections import defaultdict

from playwright.async_api import Page
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ============================================================================
# HTML PARSING HELPERS
# ============================================================================

RE_DURATION = re.compile(r"(\d+)\s*min", re.IGNORECASE)


def _norm_wd(s: str) -> str:
    """Normalize weekday string"""
    return unicodedata.normalize("NFC", s.strip())


def _text(el) -> str:
    """Extract text from element"""
    return el.get_text(strip=True) if el else None


def _duration_min(txt: str) -> int:
    """Extract duration in minutes from text"""
    if not txt:
        return None
    m = RE_DURATION.search(txt)
    return int(m.group(1)) if m else None


def _end_time(hhmm: str, minutes: int) -> str:
    """Calculate end time from start time and duration"""
    if not hhmm or minutes is None:
        return None
    try:
        t = datetime.strptime(hhmm, "%H:%M")
        return (t + timedelta(minutes=minutes)).strftime("%H:%M")
    except Exception:
        return None


def _location_and_skill(desc_el) -> Tuple[str, str, str, str]:
    """
    Parse location and skill from description element

    Returns: (location, course, skill, full_description)
    """
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
    """
    Parse a single event/slot element

    Args:
        weekday_it: Italian weekday name
        ev_el: BeautifulSoup element for the event

    Returns:
        Dict with event data
    """
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

    location_path, course_type, skill, activity_full = _location_and_skill(
        ev_el.select_one(".slot-description")
    )

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
    """
    Parse weekly schedule from HTML

    Args:
        html: Raw HTML content

    Returns:
        Dict mapping weekday names to list of events
    """
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

    # Sort and deduplicate
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


# ============================================================================
# PAGE INTERACTION
# ============================================================================

class WebScraper:
    """Low-level web scraping operations"""

    @staticmethod
    async def scrape_bookings(page: Page) -> List[Dict]:
        """
        Scrape current user bookings from the bookings page

        Args:
            page: Playwright page object

        Returns:
            List of booking dictionaries
        """
        logger.info("Scraping bookings...")
        html = await page.content()
        soup = BeautifulSoup(html, 'lxml')
        bookings = []

        # Find booking entries in event-repository
        repository = soup.select_one('#event-repository')
        if not repository:
            logger.warning("No event-repository found")
            return bookings

        booking_els = repository.select('.event-main-block')
        logger.info(f"Found {len(booking_els)} booking elements")

        for idx, el in enumerate(booking_els):
            try:
                # Extract date
                date_el = el.select_one('.event-info-schedule')
                booking_date = date_el.get_text(strip=True) if date_el else None

                # Extract time
                time_start_el = el.select_one('.time-start')
                time_duration_el = el.select_one('.time-duration')
                time_start = time_start_el.get_text(strip=True) if time_start_el else None
                time_duration = time_duration_el.get_text(strip=True) if time_duration_el else None

                # Extract description and skill
                description_el = el.select_one('.event-info-description')
                skill_el = el.select_one('.event-info-skill-level')

                location = description_el.get_text(strip=True) if description_el else 'Unknown'
                course_name = skill_el.get_text(strip=True) if skill_el else 'Unknown'

                # Create unique booking ID
                booking_id = f"{booking_date}_{time_start}_{course_name}".replace('/', '-').replace(' ', '_').replace(':', '')

                if booking_date and time_start and course_name:
                    bookings.append({
                        'booking_id': booking_id,
                        'course_name': course_name,
                        'location': location,
                        'booking_date': booking_date,
                        'booking_time': f"{time_start} ({time_duration})" if time_duration else time_start
                    })
                    logger.info(f"Parsed booking {idx+1}: {course_name} on {booking_date} at {time_start}")
                else:
                    logger.warning(f"Incomplete booking data at index {idx}")

            except Exception as e:
                logger.error(f"Error parsing booking {idx}: {e}")

        return bookings

    @staticmethod
    async def navigate_to_courses(page: Page) -> List[Dict]:
        """
        Navigate to Giuriati Corsi Platinum and scrape bookings first

        Returns:
            List of current bookings
        """
        logger.info("Navigating to courses...")
        await page.get_by_text('Booking Prenotazioni e noleggi View more').click()
        await page.wait_for_timeout(3000)

        # Scrape bookings from this page
        bookings = await WebScraper.scrape_bookings(page)

        # Continue to courses
        await page.get_by_role('link', name='Nuova Prenotazione').click()

        try:
            await page.get_by_role('button', name='Chiudi questa informativa').click(timeout=2000)
        except:
            pass

        await page.get_by_role('link', name='Giuriati - Corsi Platinum').click()
        await page.wait_for_timeout(3000)

        return bookings

    @staticmethod
    async def navigate_to_fit_center(page: Page):
        """Navigate to Giuriati Fit Center"""
        logger.info("Navigating to fit center...")
        await page.get_by_role("link", name="Attività").click()
        await page.wait_for_timeout(1000)
        await page.get_by_role("link", name="Giuriati - Fit Center").click()
        await page.wait_for_timeout(3000)

    @staticmethod
    async def move_date_forward(page: Page, days: int = 1):
        """Move calendar forward by N days"""
        for _ in range(days):
            await page.click("a.btn-move-date[data-date-target='+1']")
            await page.wait_for_timeout(200)
        await page.wait_for_timeout(3000)

    @staticmethod
    async def scrape_schedule(page: Page, pages_to_scrape: int = 5) -> Dict[str, List[Dict]]:
        """
        Scrape weekly schedule from current location

        Args:
            page: Playwright page object
            pages_to_scrape: Number of date pages to scrape

        Returns:
            Dict mapping weekdays to events
        """
        weekly = defaultdict(list)

        for i in range(pages_to_scrape):
            logger.info(f"Scraping page {i+1}/{pages_to_scrape}...")
            html = await page.content()
            parsed = parse_weekly_pattern_from_html(html)

            for k, v in parsed.items():
                weekly[_norm_wd(k)].extend(v)

            if i < pages_to_scrape - 1:
                await WebScraper.move_date_forward(page, days=1)

        # Build final dict with deduplication
        WEEKDAYS = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
        result = {}

        for wd in WEEKDAYS:
            items = list(weekly.get(_norm_wd(wd), []))
            items.sort(key=lambda r: (r.get("time_start") or "99:99"))

            # Deduplicate
            seen = set()
            deduped = []
            for r in items:
                key = (r.get("time_start"), r.get("activity_full"), r.get("instructor"), r.get("status"))
                if key not in seen:
                    seen.add(key)
                    deduped.append(r)

            result[wd] = deduped

        return result


if __name__ == '__main__':
    # Test HTML parsing
    logging.basicConfig(level=logging.INFO)

    test_html = '''
    <div id="day-schedule-container">
        <div class="day-schedule">
            <div class="day-schedule-label">Lunedì, 10 Oct</div>
            <div class="day-schedule-slots">
                <div class="event-slot slot-available">
                    <div class="slot-time">
                        <span class="time-start">10:00</span>
                        <span class="time-duration">55 min</span>
                    </div>
                    <div class="slot-description">Giuriati - Corsi Platinum - <span class="skill">YOGA</span></div>
                    <div class="slot-description2">con ROSSI MARIO</div>
                </div>
            </div>
        </div>
    </div>
    '''

    print("Testing HTML parsing...")
    result = parse_weekly_pattern_from_html(test_html)

    assert 'Lunedì' in result, "Should parse Lunedì"
    assert len(result['Lunedì']) > 0, "Should have events"

    event = result['Lunedì'][0]
    assert event['time_start'] == '10:00', "Should parse time"
    assert event['skill'] == 'YOGA', "Should parse skill"
    assert event['instructor'] == 'ROSSI MARIO', "Should parse instructor"

    print("✓ Lunedì parsed correctly")
    print(f"✓ Event: {event['time_start']} - {event['skill']} ({event['instructor']})")
    print("\n✅ Web scraper tests passed!")
