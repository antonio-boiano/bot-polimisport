# Polimisport Telegram Bot

Telegram bot for managing Polimisport bookings with automated scheduling and confirmation.

## Features

- 🔐 **Authentication**: Bot accessible only to authorized user
- 📅 **Manual Bookings**: Create one-time bookings
- 📋 **View Bookings**: List all your current bookings
- ❌ **Cancel Bookings**: Cancel existing bookings
- 🗓️ **Course Schedule**: View weekly course schedules
- 🔄 **Periodic Bookings**: Set up recurring bookings with confirmation
- ⏰ **Auto-Cancel**: Unconfirmed bookings are cancelled 1 hour before

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure the Bot

Edit `config.json`:

```json
{
  "username": "YOUR_POLIMISPORT_USERNAME",
  "password": "YOUR_POLIMISPORT_PASSWORD",
  "otpatu": "YOUR_OTP_URL",
  "telegram": {
    "bot_token": "YOUR_TELEGRAM_BOT_TOKEN",
    "allowed_user_id": YOUR_TELEGRAM_USER_ID
  }
}
```

#### Getting Your Telegram User ID

1. Start a chat with [@userinfobot](https://t.me/userinfobot)
2. The bot will send you your user ID
3. Use that ID in the config

#### Creating a Telegram Bot

1. Start a chat with [@BotFather](https://t.me/botfather)
2. Send `/newbot` and follow the instructions
3. Copy the bot token and add it to your config

### 3. Run the Bot

```bash
python bot.py
```

## Usage

### Commands

- `/start` - Show main menu

### Manual Booking

1. Click "📅 Nuova Prenotazione"
2. Select location (e.g., Giuriati - Corsi Platinum)
3. Choose date and time slot
4. Confirm booking

### View Bookings

1. Click "📋 Le Mie Prenotazioni"
2. See all your active bookings
3. Cancel any booking if needed

### Course Schedule

1. Click "🗓️ Orari Corsi Settimanali"
2. View the weekly schedule with all courses

### Periodic Bookings

1. Click "🔄 Prenotazioni Periodiche"
2. Create a new periodic booking:
   - Select day of week
   - Select time
   - Select location and course
3. You'll receive confirmation requests 1 hour before each booking
4. Confirm or cancel within 1 hour, otherwise it's auto-cancelled

## File Structure

```
bot-polimisport/
├── bot.py                      # Main Telegram bot
├── booking.py                  # Booking operations with Playwright
├── scraper.py                  # Course schedule scraper
├── scheduler.py                # Periodic booking scheduler
├── otp_extractor.py           # OTP code generator
├── main.py                     # Original manual booking script
├── config.json                 # Configuration file
├── requirements.txt            # Python dependencies
├── periodic_bookings.json      # Stored periodic bookings
└── pending_confirmations.json  # Pending confirmations
```

## How It Works

### Periodic Bookings with Confirmation

1. **Setup**: You create a periodic booking (e.g., every Monday at 18:00)
2. **Schedule**: The scheduler runs in background and watches for booking times
3. **Confirmation Request**: 1 hour before booking time, you receive a Telegram message with confirm/cancel buttons
4. **Confirmation**: If you click "Confirm", the booking is made
5. **Auto-Cancel**: If not confirmed within 1 hour, booking is automatically cancelled

### Security

- Only the configured `allowed_user_id` can use the bot
- All other users are rejected with an unauthorized message

## Troubleshooting

### Bot doesn't respond
- Check that bot token is correct in `config.json`
- Ensure bot is running (`python bot.py`)

### Login fails
- Verify username/password in `config.json`
- Check OTP URL is correct
- Make sure Playwright browser is installed

### Periodic bookings not working
- Check that scheduler is running (logs should show "Scheduler started")
- Verify periodic bookings are saved in `periodic_bookings.json`

## Development Notes

Some selectors in `booking.py` and `scraper.py` are placeholders and need to be adjusted based on the actual Polimisport website structure. Use browser developer tools to find the correct selectors.

## License

MIT
