# Polimisport Bot - Database Architecture

Database-driven Telegram bot for managing Polimisport bookings with non-blocking operations.

## Architecture Overview

```
┌─────────────┐
│ Telegram Bot│ ← User interacts here
│  (bot_db.py)│
└──────┬──────┘
       │ Adds actions to queue
       ↓
┌──────────────────┐
│    Database      │ ← Central data store
│ (polimisport.db) │
└──────────────────┘
       ↑
       │ Processes actions
┌──────┴──────┐
│   Worker    │ ← Executes bookings
│ (worker.py) │
└─────────────┘

Additional Scripts:
- refresh_courses.py   → Scrapes and populates course data
- sync_bookings.py     → Syncs bookings with website
- periodic_executor.py → Handles periodic bookings
```

## Key Features

### Non-Blocking Operations
- Bot adds actions to database queue and immediately returns
- Worker processes actions asynchronously
- Users get notifications when actions complete
- Status can be checked anytime with `/status <action_id>`

### Database Tables

1. **courses** - Available courses (populated by scraper)
2. **booking_actions** - Action queue (book/cancel/check)
3. **user_bookings** - Current active bookings
4. **periodic_bookings** - Recurring bookings
5. **pending_confirmations** - Confirmations for periodic bookings

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure

Your `config.json` should already be configured. If not:

```json
{
  "username": "YOUR_USERNAME",
  "password": "YOUR_PASSWORD",
  "otpatu": "YOUR_OTP_URL",
  "telegram": {
    "bot_token": "YOUR_BOT_TOKEN",
    "allowed_user_id": YOUR_USER_ID
  }
}
```

### 3. Initialize Database

```bash
python setup.py
```

### 4. Populate Course Database

```bash
python refresh_courses.py
```

## Running the System

You need to run **3 processes** simultaneously:

### 1. Telegram Bot (Foreground)
```bash
python bot_db.py
```

### 2. Worker (Background)
```bash
python worker.py &
# or use screen/tmux:
screen -dmS worker python worker.py
```

### 3. Periodic Executor (Background)
```bash
python periodic_executor.py &
# or use screen/tmux:
screen -dmS periodic python periodic_executor.py
```

## Usage

### Bot Commands

- `/start` - Main menu
- `/status <action_id>` - Check action status

### Making a Booking

1. Click "📅 Nuova Prenotazione"
2. Select day
3. Select course
4. Bot queues the booking
5. You receive notification when complete
6. Use `/status <id>` to check progress

### Viewing Bookings

1. Click "📋 Le Mie Prenotazioni"
2. See all active bookings from database
3. Cancel any booking (queued for processing)

### Periodic Bookings

1. Click "🔄 Prenotazioni Periodiche"
2. Add new periodic booking:
   - Select day of week
   - Select time slot
   - Select location/course
3. Receive confirmation 1 hour before
4. Confirm or skip each instance
5. Auto-cancelled if not confirmed

### Course Schedule

1. Click "🗓️ Orari Corsi"
2. View all courses from database
3. Shows availability if known

## Maintenance Scripts

### Refresh Courses (Run Daily)

```bash
python refresh_courses.py
```

Updates course database from website.

### Sync Bookings (Run Hourly)

```bash
python sync_bookings.py
```

Syncs bookings between website and database.

### Cron Jobs (Recommended)

```cron
# Refresh courses daily at 6 AM
0 6 * * * cd /path/to/bot-polimisport && /path/to/python refresh_courses.py

# Sync bookings every hour
0 * * * * cd /path/to/bot-polimisport && /path/to/python sync_bookings.py
```

## How It Works

### Booking Flow

1. **User Request** → Bot adds action to `booking_actions` table with status `pending`
2. **Worker** → Polls for `pending` actions, sets to `processing`, executes
3. **Completion** → Updates to `completed` or `failed`, stores result
4. **Notification** → Worker notifies user via Telegram
5. **Database Update** → Booking added to `user_bookings` if successful

### Periodic Booking Flow

1. **Setup** → User creates periodic booking in database
2. **Monitoring** → `periodic_executor.py` checks every minute
3. **Confirmation** → 1 hour before booking, sends confirmation request
4. **User Response** → User confirms or skips
5. **Execution** → If confirmed, adds to booking queue
6. **Auto-Cancel** → If not confirmed before deadline, skipped

## File Structure

```
bot-polimisport/
├── database.py              # Database models and operations
├── bot_db.py               # Telegram bot (non-blocking)
├── worker.py               # Action processor
├── periodic_executor.py    # Periodic booking handler
├── refresh_courses.py      # Course scraper
├── sync_bookings.py        # Booking syncer
├── setup.py               # Setup script
│
├── booking.py             # Booking operations (from old version)
├── scraper.py             # Web scraper (from old version)
├── otp_extractor.py       # OTP generator
│
├── config.json            # Configuration
├── polimisport.db         # SQLite database
│
├── requirements.txt       # Python dependencies
└── README_DB.md          # This file
```

## Troubleshooting

### Worker not processing actions

```bash
# Check if worker is running
ps aux | grep worker.py

# View worker logs
tail -f worker.log  # if logging to file
```

### Periodic bookings not working

```bash
# Check if periodic_executor is running
ps aux | grep periodic_executor.py

# Check pending confirmations
sqlite3 polimisport.db "SELECT * FROM pending_confirmations;"
```

### Database issues

```bash
# Re-initialize database
python setup.py

# Check database
sqlite3 polimisport.db ".tables"
```

### Bot not responding

- Check bot token in `config.json`
- Verify bot is running: `ps aux | grep bot_db.py`
- Check Telegram API status

## Database Schema

### courses
```sql
id, name, location, day_of_week, time_start, time_end,
available_spots, total_spots, course_type, instructor, last_updated
```

### booking_actions
```sql
id, action_type, user_id, status, location, course_name, date,
time_slot, booking_id, created_at, started_at, completed_at, result, error
```

### user_bookings
```sql
id, user_id, booking_id, course_name, location, booking_date,
booking_time, status, created_at, updated_at
```

### periodic_bookings
```sql
id, user_id, name, location, course_name, day_of_week, time_slot,
requires_confirmation, active, created_at
```

### pending_confirmations
```sql
id, user_id, periodic_booking_id, scheduled_for, confirmed,
created_at, expires_at
```

## Security

- Bot accessible only to `allowed_user_id`
- Database stored locally (SQLite)
- Credentials in `config.json` (gitignored)

## Performance

- **Non-blocking**: Bot responds immediately, doesn't wait for bookings
- **Scalable**: Multiple workers can process queue in parallel
- **Reliable**: Actions persisted in database, survive restarts
- **Efficient**: Database queries indexed for speed

## Future Enhancements

- [ ] Multiple user support
- [ ] Web dashboard for monitoring
- [ ] Advanced scheduling (book N days in advance)
- [ ] Smart retry logic for failed bookings
- [ ] Notification preferences
- [ ] Export booking history
