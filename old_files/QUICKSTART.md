# Quick Start Guide - Polimisport Bot

## ✅ What's Working

Your database is now populated with **38 courses** across the week:
- Lunedì: 14 corsi
- Martedì: 5 corsi
- Mercoledì: 6 corsi
- Giovedì: 6 corsi
- Venerdì: 5 corsi
- Sabato: 2 corsi

## 🚀 Running the Bot

### Option 1: Run all components manually

**Terminal 1 - Telegram Bot:**
```bash
cd /home/antonio/bot-polimisport
python bot_db.py
```

**Terminal 2 - Worker (processes bookings):**
```bash
cd /home/antonio/bot-polimisport
python worker.py
```

**Terminal 3 - Periodic Executor (handles recurring bookings):**
```bash
cd /home/antonio/bot-polimisport
python periodic_executor.py
```

### Option 2: Use screen/tmux (recommended for background)

```bash
cd /home/antonio/bot-polimisport

# Start worker in background
screen -dmS worker python worker.py

# Start periodic executor in background
screen -dmS periodic python periodic_executor.py

# Start bot (foreground or background)
python bot_db.py
# OR
screen -dmS bot python bot_db.py
```

**View running screens:**
```bash
screen -ls
```

**Attach to a screen:**
```bash
screen -r worker    # or 'bot', 'periodic'
```

**Detach from screen:** Press `Ctrl+A`, then `D`

## 📱 Using the Bot

Once running, open Telegram and send `/start` to your bot.

### Main Menu Options:

1. **📅 Nuova Prenotazione**
   - Select a day
   - View courses for that day
   - (Booking functionality to be completed)

2. **📋 Le Mie Prenotazioni**
   - View your active bookings
   - Cancel bookings

3. **🗓️ Orari Corsi**
   - View weekly schedule summary
   - Shows all days with course counts

4. **🔄 Prenotazioni Periodiche**
   - Create recurring bookings
   - View/manage periodic bookings
   - Get confirmation requests before each booking

## 🔧 Maintenance Commands

### Refresh Course Database
```bash
python refresh_courses.py
```
Run this daily to keep courses up to date.

### Sync Bookings
```bash
python sync_bookings.py
```
Run this hourly to sync with website.

### Check Database
```bash
python test_db_view.py
```
View all courses in terminal.

### Test Database Directly
```bash
python -c "from database import Database; db = Database(); print(f'Courses: {len(db.get_all_courses())}')"
```

## 🐛 Troubleshooting

### Bot shows empty courses
```bash
python refresh_courses.py
```

### Check worker is processing
```bash
ps aux | grep worker.py
```

### View worker logs (if running in screen)
```bash
screen -r worker
```

### Database issues
```bash
# Reinitialize database
python setup.py

# Repopulate courses
python refresh_courses.py
```

### Kill all processes
```bash
pkill -f bot_db.py
pkill -f worker.py
pkill -f periodic_executor.py
```

Or with screen:
```bash
screen -X -S bot quit
screen -X -S worker quit
screen -X -S periodic quit
```

## 📊 Database Structure

**Tables:**
- `courses` - All available courses (38 courses currently)
- `booking_actions` - Queue of booking/cancel actions
- `user_bookings` - Your active bookings
- `periodic_bookings` - Your recurring bookings
- `pending_confirmations` - Pending periodic booking confirmations

**Database file:** `polimisport.db`

## 🔍 Useful SQL Queries

```bash
sqlite3 polimisport.db
```

```sql
-- View all courses
SELECT day_of_week, time_start, course_type, instructor FROM courses ORDER BY day_of_week, time_start;

-- Count courses by day
SELECT day_of_week, COUNT(*) FROM courses GROUP BY day_of_week;

-- View pending actions
SELECT * FROM booking_actions WHERE status = 'pending';

-- View your bookings
SELECT * FROM user_bookings WHERE status = 'active';

-- View periodic bookings
SELECT * FROM periodic_bookings WHERE active = 1;
```

Exit sqlite3: `.quit`

## 🎯 Next Steps

1. **Start the bot**: `python bot_db.py`
2. **Test visualization**: Send `/start` and click "🗓️ Orari Corsi"
3. **Browse by day**: Click "📅 Nuova Prenotazione" then select a day
4. **(Optional)** Set up cron jobs for automatic refresh

## 📅 Cron Jobs (Optional)

Edit crontab:
```bash
crontab -e
```

Add these lines:
```cron
# Refresh courses daily at 6 AM
0 6 * * * cd /home/antonio/bot-polimisport && python refresh_courses.py

# Sync bookings every hour
0 * * * * cd /home/antonio/bot-polimisport && python sync_bookings.py
```

## 🆘 Support

If you encounter issues:
1. Check all 3 processes are running
2. Check database has courses: `python test_db_view.py`
3. Check logs in terminal/screen sessions
4. Restart all processes

## ✨ Current Status

✅ Database initialized
✅ 38 courses populated
✅ Bot can visualize courses by day
✅ Course schedule display working
✅ Day-based filtering working

⏳ To be completed:
- Actual booking execution (worker integration)
- Periodic booking implementation
- Confirmation workflow
