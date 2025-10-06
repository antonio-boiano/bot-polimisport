# Architecture Documentation

## Overview

Professional modular architecture with clear separation of concerns. Each layer is independent and testable.

## Layer Structure

```
┌─────────────────────────────────────┐
│         main.py (Interface)         │
│      Telegram Bot + Commands        │
└─────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────┐
│      Handlers (Business Logic)      │
│   CourseHandler | BookingHandler    │
└─────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────┐
│    Resources (Web Interaction)      │
│  SessionManager | WebScraper        │
└─────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────┐
│       Utils (Low-level Ops)         │
│      Database | OTP                 │
└─────────────────────────────────────┘
```

## Module Details

### Layer 1: Utils (`src/utils/`)

**Purpose:** Low-level operations with no dependencies on other layers

#### `database.py`
- SQLite database operations
- Context manager for connections
- Tables: courses, user_bookings
- Self-test: `python -m src.utils.database`

#### `otp.py`
- TOTP generation from otpauth URLs
- Parses secret and generates 6-digit codes
- Self-test: `python -m src.utils.otp`

### Layer 2: Resources (`src/resources/`)

**Purpose:** Website interaction and data extraction

**Dependencies:** Utils layer only

#### `session_manager.py`
- Playwright browser lifecycle management
- Login with OTP authentication
- Context manager for session cleanup
- Self-test: `python -m src.resources.session_manager`

#### `web_scraper.py`
- HTML parsing with BeautifulSoup
- Schedule extraction from sport.polimi.it
- Page navigation helpers
- Deduplication logic
- Self-test: `python -m src.resources.web_scraper`

### Layer 3: Handlers (`src/handlers/`)

**Purpose:** Business logic coordinating resources and utils

**Dependencies:** Resources + Utils layers

#### `course_handler.py`
- Course database refresh
- Fit center slot management
- Day-based retrieval
- Formatting for display
- Self-test: `python -m src.handlers.course_handler`

#### `booking_handler.py`
- Booking operations (create, cancel)
- Sync bookings from website
- Booking status management
- Self-test: `python -m src.handlers.booking_handler`

### Layer 4: Interface (`main.py`)

**Purpose:** User-facing Telegram bot

**Dependencies:** All layers

- Command handlers: `/start`, `/refresh`, `/bookings`
- Callback query handling for menus
- Session management (auto-cleanup)
- Authorization check

## Data Flow

### Refresh Flow
```
User: /refresh
  ↓
main.py: refresh()
  ↓
SessionManager: login()
  ↓
CourseHandler: refresh_courses()
  ↓
WebScraper: scrape_schedule()
  ↓
Database: add_course()
  ↓
User: ✅ Database updated
```

### Booking View Flow
```
User: 📚 Corsi button
  ↓
main.py: button_callback()
  ↓
main.py: _show_day_menu()
  ↓
User: Select day
  ↓
CourseHandler: get_courses_by_day()
  ↓
Database: get_all_courses()
  ↓
User: Course list
```

## Testing Strategy

### 1. Unit Tests (Self-contained)
Each module has `if __name__ == '__main__'` block:
- Tests core functionality
- No external dependencies
- Quick validation

### 2. Integration Tests (`scripts/`)
- `test_database.py` - Database operations
- `test_scraper.py` - HTML parsing
- `test_login.py` - Session + login
- `test_full_flow.py` - End-to-end

### 3. Manual Testing
- Run main.py
- Test via Telegram interface
- Verify browser interactions

## Design Principles

### 1. Separation of Concerns
- Each layer has single responsibility
- No circular dependencies
- Clear interfaces between layers

### 2. Testability
- Self-testing modules
- Mocked dependencies
- In-memory databases for tests

### 3. Debuggability
- Comprehensive logging
- Clear error messages
- Browser visible in tests

### 4. Maintainability
- Type hints throughout
- Docstrings for all public methods
- Self-explanatory file names

## Configuration

### config.json Format
```json
{
    "username": "polimi_username",
    "password": "polimi_password",
    "otpauth_url": "otpauth://totp/...",
    "telegram_bot_token": "bot_token",
    "telegram_user_id": 123456,
    "db_path": "polimisport.db"
}
```

### Environment Setup
1. Install: `pip install -r requirements.txt`
2. Playwright: `playwright install chromium`
3. Config: Create `config.json`
4. Run: `python main.py`

## Migration from Previous Version

### What Changed
- **Before:** Single 800-line file (`polimisport_bot.py`)
- **After:** Modular structure with 9 focused files

### Benefits
1. **Easier debugging** - Test each layer independently
2. **Better organization** - Find code by responsibility
3. **Simpler maintenance** - Edit without breaking other parts
4. **Reusable components** - Use handlers in other scripts

### Backward Compatibility
- Old version moved to `old_files/`
- Same database schema
- Same config.json format
- Same bot commands

## Adding New Features

### New Low-level Utility
1. Create `src/utils/new_util.py`
2. Add self-test block
3. Export in `src/utils/__init__.py`
4. Test: `python -m src.utils.new_util`

### New Web Interaction
1. Create `src/resources/new_resource.py`
2. Use SessionManager for browser
3. Add to `src/resources/__init__.py`
4. Test: `python -m src.resources.new_resource`

### New Business Logic
1. Create `src/handlers/new_handler.py`
2. Inject dependencies (db, session)
3. Add to `src/handlers/__init__.py`
4. Create test script in `scripts/`

### New Bot Command
1. Add handler in `main.py`
2. Register with Application
3. Update README commands section

## Performance Considerations

### Single Login Optimization
- One browser session per refresh
- Parallel data fetching where possible
- Session cleanup after operations

### Database Efficiency
- Indexed day_of_week column
- Unique constraints on booking_id
- Transaction batching in handlers

### Async Operations
- Non-blocking Playwright calls
- Async context managers
- Parallel Telegram updates

## Security

### Credentials
- Never commit config.json
- Store in .gitignore
- Use environment variables in production

### Bot Authorization
- Single user check via telegram_user_id
- All commands verify authorization
- No multi-user support (by design)

### OTP Handling
- Secret never logged
- Generated on-demand
- Time-based expiration (30s)
