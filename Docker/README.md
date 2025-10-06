# Polimisport Bot - Docker Setup

This guide explains how to run the Polimisport Telegram bot using Docker.

## Prerequisites

- Docker (version 20.10 or higher)
- Docker Compose (version 2.0 or higher)
- A valid `config.json` file with your credentials

## Configuration File

Before running the bot, ensure you have a `config.json` file in the root directory with the following structure:

```json
{
  "username": "your_polimi_username",
  "password": "your_polimi_password",
  "otpauth_url": "otpauth://totp/...",
  "telegram_bot_token": "your_telegram_bot_token",
  "telegram_user_id": your_telegram_user_id
}
```

## Quick Start with Docker Compose (Recommended)

The easiest way to run the bot is using Docker Compose:

```bash
# Build and start the bot
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the bot
docker-compose down
```

### Volume Mounts

The `docker-compose.yml` file automatically mounts:

1. **config.json** (required): Your credentials file
   - Source: `./config.json`
   - Destination: `app/config.json` (read-only)
   - **Important**: This file must exist in the project root before starting

2. **Project directory**: For database persistence
   - Source: `.` (current directory)
   - Destination: `/app`
   - The `polimisport.db` file will be **automatically created** on first run
   - All data persists in your project directory between container restarts

## Manual Docker Run

If you prefer to run without Docker Compose:

```bash
# Build the image
docker build -t polimisport-bot .

# Run the container
docker run -d \
  --name polimisport-bot \
  --restart unless-stopped \
  -v $(pwd)/config.json:/app/config.json:ro \
  -v $(pwd):/app \
  -e TZ=Europe/Rome \
  anboiano/polimisport-bot
```

### Volume Explanation

- `-v $(pwd)/config.json:config.json:ro`: Mounts your config file as read-only
- `-v $(pwd):/app`: Mounts the project directory so the database persists automatically

## Common Commands

```bash
# View real-time logs
docker logs -f polimisport-bot

# Stop the bot
docker stop polimisport-bot

# Start the bot
docker start polimisport-bot

# Remove the container
docker rm polimisport-bot

# Rebuild after code changes
docker-compose up -d --build
```

## Troubleshooting

### Config file not found

If you see an error about missing config file:
```
FileNotFoundError: [Errno 2] No such file or directory: 'config.json'
```

Ensure that:
1. Your `config.json` exists in the project root directory
2. You're running Docker Compose from the project root
3. The volume mount is correct in `docker-compose.yml`

### Database not created

If the database isn't being created:
1. Check that the project directory is writable
2. Check logs: `docker logs polimisport-bot`
3. The database file `polimisport.db` should appear in your project root after first run

### Playwright/Browser issues

If Playwright fails to launch browsers:
- The Dockerfile already includes all necessary dependencies
- Ensure you're using the latest image: `docker-compose build --no-cache`

### Logs not showing

Check container status:
```bash
docker ps -a
docker logs polimisport-bot
```

## Updating the Bot

To update the bot with new code:

```bash
# Pull latest changes (if using git)
git pull

# Rebuild and restart
docker-compose up -d --build
```

## Security Notes

1. **Never commit config.json**: The config file contains sensitive credentials
2. **Read-only mount**: The config.json is mounted as read-only (`:ro`) for security
3. **Environment variables**: Consider using Docker secrets for production deployments

## Environment Variables

You can customize the timezone in `docker-compose.yml`:
```yaml
environment:
  - TZ=Europe/Rome  # Change to your timezone
```

## Data Persistence

All important data persists across container restarts:
- **config.json**: Your credentials (mounted from host, must exist before starting)
- **polimisport.db**: Booking history and schedules (automatically created on first run, persisted in project directory)
- All files are stored in your project directory

### First Run

On the first run, the bot will automatically:
1. Read the `config.json` file
2. Create the `polimisport.db` SQLite database
3. Initialize all necessary tables

**No manual database setup required!**

### Backup

To backup your data, simply copy these files from the project directory:
```bash
cp config.json config.json.backup
cp polimisport.db polimisport.db.backup
```

## Development Mode

The entire project directory is already mounted, so code changes are reflected immediately. However, for Python changes you'll need to restart:

```bash
docker-compose restart
```

For development with logs visible:
```bash
docker-compose up
```
