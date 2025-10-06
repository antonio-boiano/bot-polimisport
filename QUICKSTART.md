# Quick Start Guide

## Setup (One Time)

```bash
# 1. Install dependencies
pip install -r requirements.txt
playwright install chromium

# 2. Configure bot
nano config.json  # Edit with your credentials

# 3. Run tests (optional but recommended)
python test_bot.py
```

## Run the Bot

```bash
python polimisport_bot.py
```

That's it! One command runs everything.

## First Use

1. Send `/start` to your bot in Telegram
2. Click "🔄 Aggiorna Dati"
3. Wait ~30-60 seconds (logs in, scrapes everything)
4. Explore courses and bookings!

## What Gets Refreshed

When you click "🔄 Aggiorna Dati":
- ✅ All Corsi Platinum (~20 courses)
- ✅ All Fit Center slots (~50 slots)
- ✅ Your current bookings
- ✅ Database updated (no duplicates)

## Menu Options

### 🔄 Aggiorna Dati
Logs in once, refreshes all data. Takes ~30-60 seconds.

### 📅 Orari Corsi
View Corsi Platinum schedule:
- Select day (Lunedì, Martedì, etc.)
- See all courses for that day
- Shows time, instructor, course type

### 🏋️ Orari Fit Center
View Fit Center schedule:
- Select day
- See all available slots
- Shows time, activity type

### 📋 Le Mie Prenotazioni
View your active bookings:
- Course name
- Location
- Date and time

## Tips

1. **Refresh regularly** - Course availability changes
2. **One login** - Don't refresh too often (rate limiting)
3. **Test mode** - Run `python test_bot.py` to verify everything works

## Differences from Old Version

### Old (Complex):
- 13 separate Python files
- 3 processes to run simultaneously
- Multiple logins per operation
- Complex worker/scheduler system

### New (Simple):
- 1 main file (`polimisport_bot.py`)
- 1 command to run
- 1 login refreshes everything
- Direct, no background workers

## File Structure

```
bot-polimisport/
├── polimisport_bot.py     ← Run this
├── test_bot.py            ← Test this
├── config.json            ← Configure this
├── requirements.txt
├── otp_extractor.py       (kept for compatibility)
├── polimisport.db         (auto-created)
└── old_files/             (archived old version)
```

## Common Commands

```bash
# Run bot
python polimisport_bot.py

# Run tests
python test_bot.py

# Check database
sqlite3 polimisport.db "SELECT COUNT(*) FROM courses"

# View config
cat config.json
```

## Need Help?

1. Check README.md for full documentation
2. Run tests: `python test_bot.py`
3. Check logs in terminal output
4. Verify config.json is correct
