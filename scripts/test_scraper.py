#!/usr/bin/env python3
"""
Test Web Scraper
Interactive script to test HTML parsing and web scraping
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.resources.web_scraper import parse_weekly_pattern_from_html

print("=== Web Scraper Test ===\n")

# Test HTML (realistic example)
test_html = '''
<div id="day-schedule-container">
    <div class="day-schedule">
        <div class="day-schedule-label">Lunedì, 14 Ottobre</div>
        <div class="day-schedule-slots">
            <div class="event-slot slot-available">
                <div class="slot-time">
                    <span class="time-start">10:00</span>
                    <span class="time-duration">55 min</span>
                </div>
                <div class="slot-description">Giuriati - Corsi Platinum - <span class="skill">YOGA</span></div>
                <div class="slot-description2">con ROSSI MARIO</div>
            </div>
            <div class="event-slot slot-booked">
                <div class="slot-time">
                    <span class="time-start">11:00</span>
                    <span class="time-duration">55 min</span>
                </div>
                <div class="slot-description">Giuriati - Corsi Platinum - <span class="skill">PILATES</span></div>
                <div class="slot-description2">con VERDI LUIGI</div>
            </div>
        </div>
    </div>
    <div class="day-schedule">
        <div class="day-schedule-label">Martedì, 15 Ottobre</div>
        <div class="day-schedule-slots">
            <div class="event-slot slot-available">
                <div class="slot-time">
                    <span class="time-start">14:00</span>
                    <span class="time-duration">60 min</span>
                </div>
                <div class="slot-description">Sala Pesi - Fit Center</div>
            </div>
        </div>
    </div>
</div>
'''

print(">>> Parsing test HTML...")
result = parse_weekly_pattern_from_html(test_html)

print(f"✓ Parsed {len(result)} days\n")

# Validate structure
assert 'Lunedì' in result, "Should parse Lunedì"
assert 'Martedì' in result, "Should parse Martedì"

print(">>> Results by day:\n")

for day, events in result.items():
    print(f"{day}:")
    for event in events:
        time_range = f"{event['time_start']}-{event['time_end']}" if event['time_end'] else event['time_start']
        activity = event.get('skill') or event.get('activity_full', 'Unknown')
        instructor = f" ({event['instructor']})" if event.get('instructor') else ""
        status = f" [{event['status']}]" if event.get('status') else ""

        print(f"  {time_range}: {activity}{instructor}{status}")
    print()

# Detailed validation
monday = result['Lunedì']
assert len(monday) == 2, f"Should have 2 events on Monday, got {len(monday)}"

first_event = monday[0]
assert first_event['time_start'] == '10:00', "First event should start at 10:00"
assert first_event['time_end'] == '10:55', "Should calculate end time correctly"
assert first_event['skill'] == 'YOGA', "Should parse skill correctly"
assert first_event['instructor'] == 'ROSSI MARIO', "Should parse instructor correctly"
assert first_event['status'] == 'available', "Should parse status correctly"

print("✓ Lunedì first event validated:")
print(f"  Time: {first_event['time_start']}-{first_event['time_end']}")
print(f"  Skill: {first_event['skill']}")
print(f"  Instructor: {first_event['instructor']}")
print(f"  Status: {first_event['status']}\n")

tuesday = result['Martedì']
assert len(tuesday) == 1, "Should have 1 event on Tuesday"

fit_center_event = tuesday[0]
assert fit_center_event['time_start'] == '14:00', "Fit center should start at 14:00"
assert fit_center_event['location_path'] == 'Sala Pesi', "Should parse location correctly"

print("✓ Martedì fit center validated:")
print(f"  Time: {fit_center_event['time_start']}-{fit_center_event['time_end']}")
print(f"  Location: {fit_center_event['location_path']}\n")

print("✅ All web scraper tests passed!")
