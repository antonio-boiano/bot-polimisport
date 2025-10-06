# 🏃 Polimisport Bot

Automated Telegram bot for managing Polimisport (PoliMi sport center) course bookings and schedules. Never miss your favorite class again!

## 📋 Features

### 🎯 Booking Modes

- **⚡ Instant Booking** - Book available courses immediately (within 2 days)
- **📅 Scheduled Booking** - Automatically books at midnight 2 days before the course
- **🔄 Recurring Booking** - Automatically books the same course every week with two modes:
  - **With Confirmation**: Receive a notification 5 hours before to confirm/cancel
  - **Automatic**: Books automatically without confirmation

### 📚 Course Management

- **View Courses** - Browse all available courses and Fit Center slots by day
- **My Bookings** - View all your active bookings with quick cancel buttons
- **Database Sync** - Refresh course catalog and sync existing bookings from website

### 📆 Scheduling Features

- **Manage Scheduled Bookings** - View and cancel upcoming scheduled bookings
- **Manage Recurring Bookings** - Toggle on/off or delete recurring bookings
- **Calendar Export** - Receive .ics calendar files for successful bookings

### 🔐 Security

- Single-user authentication with Telegram user ID verification
- PoliMi 2FA support with TOTP (Time-based One-Time Password)
- Credentials stored in local config file (never committed to git)
- See [SECURITY.md](SECURITY.md) for security audit and best practices



## 🚀 Quick Start

### Prerequisites

- Python 3.8 or higher
- PoliMi account with 2FA enabled
- Telegram account

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/bot-polimisport.git
cd bot-polimisport
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

This installs:
- `python-telegram-bot` - Telegram bot framework
- `playwright` - Browser automation for web scraping
- `pyotp` - TOTP generation for 2FA
- `apscheduler` - Task scheduling for automated bookings

### 3. Configure

Create `config.json` in the root directory (you can copy from `config.example.json`):

```bash
cp config.example.json config.json
```

Then edit `config.json` with your actual credentials:

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

**⚠️ Security Warning**: Never commit `config.json` to git! It contains sensitive credentials.

#### 📝 Configuration Guide

**How to get your PoliMi credentials:**
- Use your PoliMi username (codice persona) and password

**How to get OTP URL:**
1. Go to PoliMi services and set up 2FA if not already enabled
2. When adding a new authenticator, you'll see a QR code
3. Most QR codes contain an `otpauth://` URL - you can:
   - Use a QR scanner app to extract the URL
   - Use an authenticator app that shows the secret (e.g., Aegis, Authy)
   - Manually create the URL: `otpauth://totp/PoliMi:username?secret=YOUR_SECRET&issuer=PoliMi`

**How to get Telegram bot token:**
1. Open Telegram and message [@BotFather](https://t.me/botfather)
2. Send `/newbot` command
3. Follow prompts to choose a name and username for your bot
4. Copy the token provided (format: `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`)

**How to get your Telegram user ID:**
1. Message [@userinfobot](https://t.me/userinfobot) on Telegram
2. Copy your numeric ID (e.g., `123456789`)

### 4. Run the Bot

```bash
python main.py
```

The bot will start and display:
```
Starting Polimisport Bot...
Setting up scheduler...
Scheduler setup complete!
Bot started with scheduler!
```

### 5. Use the Bot

Open Telegram and search for your bot by the username you created. Start chatting:

#### 🎮 Available Commands

- `/start` - Show main menu with all options
- `/refresh` - Update course database and sync bookings
- `/bookings` - View your active bookings
- `/book` - Start booking process
- `/scheduled` - View scheduled bookings
- `/periodic` - View recurring bookings
- `/confirmations` - Check pending booking confirmations

#### 🖱️ Interactive Menu

The bot uses inline buttons for easy navigation:
1. **📚 Visualizza Corsi** - Browse courses and Fit Center by day
2. **🎯 Prenota corso** - Start booking flow with mode selection
3. **📅 Le mie prenotazioni** - View and cancel bookings
4. **📆 Gestisci pianificazione** - Manage scheduled/recurring bookings
5. **🔄 Aggiorna database** - Refresh available courses

## 💡 How It Works

### Booking Flow Example

1. **First Time Setup**
   - Run `/refresh` to scrape all available courses from Polimisport website
   - Bot stores courses in local SQLite database

2. **Instant Booking** (courses within 2 days)
   - Select course → Click "⚡ Prenota subito"
   - Bot logs into Polimisport and books immediately
   - Receive .ics calendar file to add to your calendar

3. **Scheduled Booking** (courses 3+ days away)
   - Select course → Click "📅 Programma prenotazione"
   - Bot calculates midnight 2 days before course
   - Automated scheduler executes booking at the right time

4. **Recurring Booking**
   - Select course → Choose confirmation mode
   - Bot automatically creates scheduled bookings every week
   - **With confirmation**: Receive notification 5h before to approve
   - **Automatic**: Books without asking (auto-cancels 1h before if confirmation required)

### Background Scheduler

The bot runs these automated tasks:
- **Every 5 minutes**: Check and execute pending scheduled bookings
- **Midnight (00:00)**: Execute all bookings scheduled for that day
- **Hourly**: Check for pending confirmations and send notifications
- **Hourly**: Auto-cancel bookings that weren't confirmed in time
- **Daily (00:30)**: Process recurring bookings and create next week's schedule

## 🔧 Architecture

### Layer 1: Utils (Low-level)
- `database.py` - SQLite operations with context managers
- `otp.py` - TOTP generation from otpauth URLs
- `scheduler.py` - APScheduler configuration and job management

### Layer 2: Resources (Web Interaction)
- `session_manager.py` - Playwright browser lifecycle & authentication
- `web_scraper.py` - HTML parsing & data extraction from Polimisport

### Layer 3: Handlers (Business Logic)
- `course_handler.py` - Course refresh & retrieval operations
- `booking_handler.py` - Booking creation & cancellation
- `booking_service.py` - Scheduled & periodic booking management
- `booking_executor.py` - Automated booking execution engine

### Layer 4: Interface
- `main.py` - Telegram bot with commands, callbacks & scheduler integration




## 🐛 Troubleshooting

### Common Issues

**🔴 Bot says "⛔ Non autorizzato"**
- Your Telegram user ID doesn't match the one in `config.json`
- Double-check your ID using [@userinfobot](https://t.me/userinfobot)
- Update `telegram_user_id` in config and restart bot

**🔴 Login fails / Authentication error**
- Verify username and password are correct in `config.json`
- Test your OTP URL manually:
  ```bash
  python -c "import pyotp; print(pyotp.parse_uri('YOUR_OTPAUTH_URL').now())"
  ```
- Ensure 2FA is properly set up on your PoliMi account
- Check if PoliMi website is accessible

**🔴 No courses found / Database empty**
- Run `/refresh` command to scrape courses from website
- Check your internet connection
- Verify you're logged into the correct PoliMi account
- If still failing, Polimisport website structure may have changed

**🔴 Bot doesn't respond to commands**
- Verify bot is running (`python main.py` shows "Bot started")
- Check `telegram_bot_token` is correct
- Ensure you're messaging the correct bot
- Check Python console for error messages

**🔴 Scheduled bookings not executing**
- Bot must be running continuously for scheduler to work
- Check logs for scheduler errors
- Verify system time is correct
- Database path is writable

**🔴 Playwright/Browser errors**
- Run `playwright install chromium` again
- Check sufficient disk space for browser installation
- Try running with headless=False for debugging (edit `session_manager.py`)

**🔴 Booking fails with "❌ Prenotazione fallita"**
- Course may be full or no longer available
- Run `/refresh` to update course availability
- Check if you already have a booking at that time
- Verify your PoliMi account is in good standing

### Debug Mode

To see detailed logs, check the console output. The bot logs:
- INFO: Normal operations (startup, bookings, refresh)
- ERROR: Failed operations with stack traces

For even more detail, change logging level in `main.py`:
```python
logging.basicConfig(level=logging.DEBUG)
```

## 📱 Best Practices

### Running 24/7

For continuous operation (required for scheduled bookings), consider:

**Option 1: Keep Your Computer Running**
```bash
python main.py
```

**Option 2: Run in Background (Linux/Mac)**
```bash
nohup python main.py > bot.log 2>&1 &
```

**Option 3: Use systemd Service (Linux)**
Create `/etc/systemd/system/polimisport-bot.service`:
```ini
[Unit]
Description=Polimisport Telegram Bot
After=network.target

[Service]
Type=simple
User=yourusername
WorkingDirectory=/path/to/bot-polimisport
ExecStart=/usr/bin/python3 main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl enable polimisport-bot
sudo systemctl start polimisport-bot
```

**Option 4: Cloud Hosting**
Deploy to services like:
- DigitalOcean Droplet
- AWS EC2 (Free tier eligible)
- Google Cloud Platform
- Heroku

### Tips

- Run `/refresh` weekly to keep course database updated
- Use recurring bookings with confirmation for flexibility
- Check `/confirmations` regularly if using confirmation mode
- Keep the bot running continuously for automated features
- Monitor disk space - database and logs can grow over time

## 🔒 Security Best Practices

### Protecting Your Credentials

**⚠️ IMPORTANT**: Your `config.json` contains sensitive information:
- PoliMi password
- 2FA secret (in the otpauth_url)
- Telegram bot token

**Never commit config.json to git!** It's already in `.gitignore`, but be careful not to override this.

### Recommended Security Measures

1. **File Permissions** (Linux/Mac)
   ```bash
   chmod 600 config.json  # Make file readable/writable only by you
   ```

2. **Use the Example Template**
   - Copy `config.example.json` to `config.json`
   - Fill in your actual credentials
   - Never edit `config.example.json` with real values

3. **Credential Rotation**
   - If you suspect your config.json was exposed:
     - Change your PoliMi password immediately
     - Reset 2FA and update the otpauth_url
     - Revoke Telegram bot token via @BotFather and create a new bot

4. **Deployment Security**
   - On shared systems, ensure config.json has restrictive permissions
   - Consider using environment variables for production deployments
   - Keep backups of config.json secure (they contain secrets too)

5. **Monitor for Unauthorized Access**
   - Check for unexpected bookings in your PoliMi account
   - Watch for unknown Telegram messages from your bot
   - Review bot logs regularly

For a complete security audit and detailed recommendations, see [SECURITY.md](SECURITY.md).

## 🤝 Contributing

Contributions are welcome! Areas for improvement:
- Support for multiple users
- Web interface for configuration
- Notification preferences
- Booking history and statistics
- Support for other PoliMi services

## ⚠️ Disclaimer

This bot is for educational purposes. Use responsibly and in accordance with PoliMi's terms of service. The author is not responsible for any misuse or violations.

## 📄 License

MIT License - feel free to use and modify

## 💬 Support

For issues or questions:
- Check the troubleshooting section above
- Open an issue on GitHub
- Review the code architecture section for understanding