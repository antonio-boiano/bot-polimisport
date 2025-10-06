# 🏃 Polimisport Bot

Professional Telegram bot for managing Polimisport (PoliMi sport center) course bookings and schedules.

## 📋 Features

### Core Functionality
- **🔐 Secure Authentication** - Automatic login with OTP support
- **📚 Course Management** - View and track all available courses
- **💪 Fit Center Integration** - Access fit center slots
- **📅 Booking Management** - View, create, and cancel bookings
- **🔄 Auto-sync** - Automatic database refresh on login
- **🤖 Telegram Interface** - Easy-to-use bot commands and menus

### Technical Features
- **Modular Architecture** - Clean separation of concerns
- **Async/Await** - Non-blocking operations with Playwright
- **SQLite Database** - Efficient local storage
- **Self-testing Modules** - Each module can be tested independently
- **Comprehensive Logging** - Debug-friendly with detailed logs

## 🏗️ Project Structure

```
bot-polimisport/
├── main.py                 # Main entry point - Telegram bot
├── config.json             # Configuration (credentials, tokens)
├── requirements.txt        # Python dependencies
│
├── src/
│   ├── utils/             # Low-level utilities
│   │   ├── database.py    # SQLite operations
│   │   └── otp.py         # OTP generation
│   │
│   ├── resources/         # Website interaction
│   │   ├── session_manager.py  # Browser & login
│   │   └── web_scraper.py      # HTML parsing & scraping
│   │
│   └── handlers/          # Business logic
│       ├── course_handler.py   # Course operations
│       └── booking_handler.py  # Booking operations
│
├── scripts/               # Interactive test scripts
│   ├── test_database.py   # Test database ops
│   ├── test_scraper.py    # Test HTML parsing
│   ├── test_login.py      # Test session & login
│   └── test_full_flow.py  # End-to-end test
│
└── old_files/            # Previous implementations (backup)
```

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure

Create `config.json`:

```json
{
    "username": "your_polimi_username",
    "password": "your_polimi_password",
    "otpauth_url": "otpauth://totp/PoliMi:username?secret=YOUR_SECRET&issuer=PoliMi",
    "telegram_bot_token": "your_telegram_bot_token",
    "telegram_user_id": 123456789,
    "db_path": "polimisport.db"
}
```

**How to get OTP URL:**
1. Set up 2FA on PoliMi services
2. When scanning QR code, extract the `otpauth://` URL
3. Or use authenticator apps that show the secret

**How to get Telegram bot token:**
1. Message [@BotFather](https://t.me/botfather) on Telegram
2. Create new bot with `/newbot`
3. Copy the token provided

**How to get your Telegram user ID:**
1. Message [@userinfobot](https://t.me/userinfobot) on Telegram
2. Copy the ID number

### 3. Run the Bot

```bash
python main.py
```

### 4. Use the Bot

Open Telegram and message your bot:
- `/start` - Main menu
- `/refresh` - Update database
- `/bookings` - View your bookings

## 🧪 Testing

Each module is self-testable. Run individual tests:

### Test Database
```bash
python scripts/test_database.py
```

### Test Web Scraper (HTML parsing)
```bash
python scripts/test_scraper.py
```

### Test Login & Session
```bash
python scripts/test_login.py
# Browser will open - verify login works
```

### Test Full Flow (End-to-End)
```bash
python scripts/test_full_flow.py
# Complete workflow: login → scrape → store
```

### Test Individual Modules
Each module has a test block:

```bash
python -m src.utils.database
python -m src.utils.otp
python -m src.resources.web_scraper
python -m src.resources.session_manager
python -m src.handlers.course_handler
python -m src.handlers.booking_handler
```

## 🔧 Architecture

### Layer 1: Utils (Low-level)
- `database.py` - SQLite operations with context managers
- `otp.py` - TOTP generation from otpauth URLs

### Layer 2: Resources (Web Interaction)
- `session_manager.py` - Browser lifecycle & authentication
- `web_scraper.py` - HTML parsing & data extraction

### Layer 3: Handlers (Business Logic)
- `course_handler.py` - Course refresh & retrieval
- `booking_handler.py` - Booking operations & sync

### Layer 4: Interface
- `main.py` - Telegram bot with commands & callbacks

## 📊 Database Schema

### Courses Table
```sql
courses (
    id INTEGER PRIMARY KEY,
    name TEXT,
    location TEXT,
    day_of_week TEXT,        -- Italian day names
    time_start TEXT,
    time_end TEXT,
    course_type TEXT,
    instructor TEXT,
    is_fit_center INTEGER,   -- 0=course, 1=fit center
    last_updated TIMESTAMP
)
```

### Bookings Table
```sql
user_bookings (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    booking_id TEXT UNIQUE,
    course_name TEXT,
    location TEXT,
    booking_date TEXT,
    booking_time TEXT,
    status TEXT,             -- 'active' or 'cancelled'
    created_at TIMESTAMP,
    updated_at TIMESTAMP
)
```

## 🐛 Debugging

### Enable Debug Logging
Edit any module and change:
```python
logging.basicConfig(level=logging.DEBUG)
```

### Common Issues

**Login fails:**
- Check username/password in `config.json`
- Verify OTP URL is correct (try generating code manually)
- Ensure 2FA is enabled on PoliMi account

**No courses found:**
- Run `/refresh` command to update database
- Check if you're logged into the correct account
- Verify the website structure hasn't changed

**Bot doesn't respond:**
- Check `telegram_bot_token` is correct
- Verify `telegram_user_id` matches your account
- Check bot is running (`python main.py`)

**Scraping errors:**
- Website structure may have changed
- Check browser console in test scripts
- Verify selectors in `web_scraper.py`

## 📝 Development

### Adding New Features

1. **Low-level functionality** → Add to `src/utils/`
2. **Website interaction** → Add to `src/resources/`
3. **Business logic** → Add to `src/handlers/`
4. **User interface** → Update `main.py`

### Testing New Code

1. Add `if __name__ == '__main__'` test block
2. Create test script in `scripts/`
3. Run independently before integration

### Code Style
- Use type hints for function parameters
- Add docstrings to all public methods
- Include logger statements for debugging
- Keep modules focused and self-contained

## 📚 Dependencies

- **python-telegram-bot** - Telegram bot API
- **playwright** - Browser automation
- **beautifulsoup4** - HTML parsing
- **pyotp** - OTP generation
- **sqlite3** - Database (built-in)

## 🔒 Security Notes

- `config.json` contains sensitive data - **never commit to git**
- Add to `.gitignore`: `config.json`, `*.db`
- OTP secrets should be stored securely
- Bot is single-user (authorized via `telegram_user_id`)

## 📄 License

Personal project for PoliMi students.

## 🙏 Credits

Created for managing Polimisport bookings efficiently.

---

**Need help?** Check the test scripts or run modules individually to debug issues.
