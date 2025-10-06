# Testing Guide - Updated Features

## Prerequisites

Make sure dependencies are installed:
```bash
pip install -r requirements.txt
```

## Step-by-Step Testing

### 1. Database Migration & Refresh

```bash
# Apply database migration
python migrate_db.py

# Should output: ✅ Migration completed successfully!
```

```bash
# Refresh courses (this will take a minute as it scrapes the website)
python refresh_courses.py

# Expected output:
# ✅ Successfully refreshed X courses + Y fit center slots
```

### 2. Verify Database Contents

```bash
# Check total counts
python -c "from database import Database; db = Database(); print(f'Courses: {len(db.get_all_courses())}'); print(f'Fit Center: {len(db.get_fit_center_slots())}'); print(f'Total: {len(db.get_all_courses(include_fit_center=True))}')"
```

Expected output similar to:
```
Courses: 19
Fit Center: 45
Total: 64
```

### 3. Test Deduplication

Run refresh twice to ensure no duplicates are added:

```bash
# First run
python refresh_courses.py
# Note the count

# Second run immediately after
python refresh_courses.py
# Should be SAME count - no duplicates added!
```

### 4. Visualize Data

```bash
python test_db_view.py
```

Should show courses grouped by day with no duplicates.

### 5. Test Bot (if you have it configured)

```bash
python bot_db.py
```

Then in Telegram:

#### Test Main Menu
1. Send `/start`
2. Verify you see:
   - 📅 Prenota Corso
   - 🏋️ Prenota Fit Center
   - 📋 Le Mie Prenotazioni
   - 🗓️ Visualizza Orari
   - 🔄 Prenotazioni Periodiche

#### Test Course Viewing
1. Click "📅 Prenota Corso"
2. Should see days with course counts
3. Click any day (e.g., "Lunedì")
4. Should see list of courses for that day
5. No duplicates should appear

#### Test Fit Center Viewing
1. Go back to main menu
2. Click "🏋️ Prenota Fit Center"
3. Should see days with fit center slot counts
4. Click any day
5. Should see fit center slots for that day

#### Test Schedule Viewing
1. Go back to main menu
2. Click "🗓️ Visualizza Orari"
3. Should see two options:
   - 📚 Orari Corsi Platinum
   - 🏋️ Orari Fit Center
4. Try both - should show weekly summaries

#### Test Periodic Booking Setup
1. Go back to main menu
2. Click "🔄 Prenotazioni Periodiche"
3. Click "➕ Nuova Prenotazione Periodica"
4. Should see:
   - 📚 Corso Platinum
   - 🏋️ Fit Center
5. Choose one
6. Should see day selection with emoji indicators
7. Choose a day
8. Should see available slots for that day/type

## Common Issues & Solutions

### Issue: "No courses found"
**Solution**: Run `python refresh_courses.py` to populate database

### Issue: Duplicates still appear
**Solution**:
```bash
# Clear and refresh
python -c "from database import Database; db = Database(); db.clear_courses()"
python refresh_courses.py
```

### Issue: "is_fit_center column not found"
**Solution**: Run `python migrate_db.py`

### Issue: Bot shows no fit center slots
**Solution**:
1. Check database: `python -c "from database import Database; print(len(Database().get_fit_center_slots()))"`
2. If 0, run refresh: `python refresh_courses.py`

### Issue: Playwright not installed
**Solution**:
```bash
pip install playwright
playwright install chromium
```

## Verification Checklist

- [ ] Migration completed successfully
- [ ] Refresh completed without errors
- [ ] No duplicate courses in database
- [ ] Fit center slots are in database
- [ ] Bot shows both course and fit center options
- [ ] Day selection works for both types
- [ ] Schedule viewing shows both types
- [ ] Periodic booking flow includes type selection

## Quick Database Queries

```bash
# Count courses vs fit center
sqlite3 polimisport.db "SELECT is_fit_center, COUNT(*) FROM courses GROUP BY is_fit_center"

# Should output:
# 0|19  (courses)
# 1|45  (fit center)

# View sample of each type
sqlite3 polimisport.db "SELECT day_of_week, time_start, course_type, is_fit_center FROM courses LIMIT 10"

# Check for duplicates
sqlite3 polimisport.db "SELECT day_of_week, time_start, course_type, instructor, COUNT(*) as cnt FROM courses GROUP BY day_of_week, time_start, course_type, instructor HAVING cnt > 1"

# Should return no results if deduplication works
```

## Performance Test

```bash
# Time the refresh operation
time python refresh_courses.py

# Should complete in 30-60 seconds (depends on website speed)
```

## Next Steps After Testing

1. ✅ Verify all tests pass
2. ✅ Check database has correct data
3. ✅ Test bot functionality
4. 🚀 Set up cron jobs for automatic refresh (optional)
5. 🚀 Start worker and periodic executor for full functionality

## Cron Job Setup (Optional)

```bash
crontab -e
```

Add:
```cron
# Refresh courses daily at 6 AM
0 6 * * * cd /home/antonio/bot-polimisport && /usr/bin/python3 refresh_courses.py >> /tmp/refresh_courses.log 2>&1

# Check every hour
0 * * * * cd /home/antonio/bot-polimisport && /usr/bin/python3 sync_bookings.py >> /tmp/sync_bookings.log 2>&1
```

## Support

If issues persist:
1. Check logs in terminal output
2. Verify config.json is correct
3. Check database file permissions
4. Ensure Python dependencies are installed
