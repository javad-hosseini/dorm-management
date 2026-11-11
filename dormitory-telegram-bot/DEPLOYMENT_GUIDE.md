# Dormitory Telegram Bot - Operations & VPS Deployment Guide 🏢🚀

A comprehensive guide explaining the architecture, local Docker image management, VPS deployment to `javad@171.22.24.206`, network port configurations, and the manual Antigravity CLI (`agy`) workflow.

---

## Table of Contents
1. [Architecture & How the Bot Works](#1-architecture--how-the-bot-works)
2. [Network Ports: Port 8080 vs Port 9000](#2-network-ports-port-8080-vs-port-9000)
3. [Local Docker Image Storage & Inspection](#3-local-docker-image-storage--inspection)
4. [Step-by-Step VPS Deployment (`javad@171.22.24.206`)](#4-step-by-step-vps-deployment-javad1712224206)
   - [Method 1: Direct Docker Image Transfer (Fastest & 1:1 Binary)](#method-1-direct-docker-image-transfer-fastest--11-binary)
   - [Method 2: One-Liner SSH Streaming Pipeline](#method-2-one-liner-ssh-streaming-pipeline)
   - [Method 3: Source Sync & Remote Build (`rsync`)](#method-3-source-sync--remote-build-rsync)
5. [Docker Compose Lifecycle on the VPS](#5-docker-compose-lifecycle-on-the-vps)
6. [Antigravity CLI (`agy`) Manual Workflow](#6-antigravity-cli-agy-manual-workflow)
7. [Environment Configuration Reference (`.env`)](#7-environment-configuration-reference-env)
8. [Troubleshooting & Verification](#8-troubleshooting--verification)

---

## 1. Architecture & How the Bot Works

The bot solves physical-to-digital operational bottlenecks for dormitory management without requiring external third-party AI APIs.

### Core Workflows:
1. **User Whitelist Authorization (`AuthMiddleware`):**
   - Intercepts all incoming messages and callback queries.
   - Verifies `event.from_user.id` against `ALLOWED_TELEGRAM_USER_IDS` in `.env`.
   - Unauthorized users are immediately dropped with an alert:
     `"⛔ Unauthorized access. Your User ID ({user_id}) is not whitelisted."`

2. **Feature 1: Raw Data Collection & Cell-Anchored `.xlsx` Generation:**
   - Manager takes photos of paper POS receipts and types resident notes on mobile.
   - Groups each resident's data into a designated row (`Row 1 = Resident 1`, `Row 2 = Resident 2`).
   - Photos with captions automatically place the image in Column $C$ and the caption text in Column $C+1$.
   - Multi-photo albums are aggregated via a 0.6s debounce window into consecutive columns.
   - Embedded images are thumbnail-scaled (max 320px) with **EXIF auto-rotation** so smartphone photos remain upright.
   - An included `_AI_EXTRACTION_GUIDE` tab provides an automated 15-line Python script for code interpreters to extract images from `openpyxl`.

3. **Feature 2: SFTP-Like Spreadsheet Drop-Zone:**
   - Manager uploads cleaned transaction `.xlsx` spreadsheets from mobile.
   - The bot places the file directly into `incoming_spreadsheets/` with an optional `{filename}.instructions.md` companion note.
   - The bot does **not** make any external AI API calls; instead, it outputs the exact command to run with the Antigravity CLI (`agy`) on the server.

4. **Persistence & Crash Recovery:**
   - Active data sessions and row coordinates are persisted in SQLite (`data/dormitory_bot.db`).
   - If the container restarts or crashes mid-session, the manager receives a prompt to resume or discard when they next message the bot.

---

## 2. Network Ports: Port 8080 vs Port 9000

> [!IMPORTANT]
> **No Port Conflict on VPS!**
> The bot operates in **Telegram Long-Polling mode** via `aiogram`.
> - It initiates **outbound** TLS requests to `https://api.telegram.org:443`.
> - It does **not** listen on or bind to any inbound network ports.
> - Therefore, **it does not consume port 8080 or port 9000** on your VPS. It runs completely safely alongside your existing services occupying port 8080.

### What if you need to expose a web service or webhook on Port 9000 in the future?
If you ever attach an internal health-check server or switch to Telegram webhooks, edit `docker-compose.yml`:
```yaml
services:
  dormitory-bot:
    image: dormitory-telegram-bot:latest
    # Map port 9000 on the host to internal container port 9000:
    ports:
      - "9000:9000"
```

---

## 3. Local Docker Image Storage & Inspection

### Where is the image stored?
Docker stores compiled container layers locally in the Docker engine's root directory (typically `/var/lib/docker/overlay2/`).

You can check and inspect the built image locally:
```bash
# Check image in local Docker storage
docker images | grep dormitory-telegram-bot

# View detailed metadata
docker image inspect dormitory-telegram-bot:latest
```
- **Image Name:** `dormitory-telegram-bot:latest`
- **Base OS:** Debian Bookworm Slim (`ghcr.io/astral-sh/uv:python3.12-bookworm-slim`)
- **Size:** `~294 MB` uncompressed (`~110 MB` compressed with gzip).

---

## 4. Step-by-Step VPS Deployment (`javad@171.22.24.206`)

Target Host: `javad@171.22.24.206` (SSH key is already installed).

### Method 1: Direct Docker Image Transfer (Fastest & 1:1 Binary)

This approach transfers the exact, locally tested image binary to the VPS so the server does not need to download or compile anything.

#### Step 1: Export and compress the image locally
From the project root on your local machine:
```bash
docker save dormitory-telegram-bot:latest | gzip > dormitory-telegram-bot.tar.gz
```

#### Step 2: Prepare the remote directory and copy files
```bash
# 1. Create target directories on the VPS
ssh javad@171.22.24.206 "mkdir -p ~/dormitory-telegram-bot/incoming_spreadsheets ~/dormitory-telegram-bot/data ~/dormitory-telegram-bot/config"

# 2. Copy the compressed image
scp dormitory-telegram-bot.tar.gz javad@171.22.24.206:~/dormitory-telegram-bot/

# 3. Copy docker-compose.yml and your configured .env file
scp docker-compose.yml .env javad@171.22.24.206:~/dormitory-telegram-bot/

# 4. Copy default instructions template
scp config/default_agent_instructions.md javad@171.22.24.206:~/dormitory-telegram-bot/config/
```

#### Step 3: Load image and start on VPS
SSH into the server:
```bash
ssh javad@171.22.24.206
cd ~/dormitory-telegram-bot

# Load the image into the server's Docker daemon
docker load < dormitory-telegram-bot.tar.gz

# Start the bot container in background
docker compose up -d

# Verify it is running
docker compose ps
docker compose logs -f
```

---

### Method 2: One-Liner SSH Streaming Pipeline

If you want to stream the image directly to the VPS without saving an intermediate `.tar.gz` file on your local disk:

```bash
docker save dormitory-telegram-bot:latest | gzip | ssh javad@171.22.24.206 'mkdir -p ~/dormitory-telegram-bot && gunzip | docker load'
scp docker-compose.yml .env javad@171.22.24.206:~/dormitory-telegram-bot/
```

---

### Method 3: Source Sync & Remote Build (`rsync`)

If you want the entire codebase on the server so you can make code edits or run `git pull` directly on the VPS:

#### Step 1: Sync project files
```bash
rsync -avz --progress \
  --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='.pytest_cache' \
  --exclude='data/*.db' \
  ./ javad@171.22.24.206:~/dormitory-telegram-bot/
```

#### Step 2: Build and run on VPS
```bash
ssh javad@171.22.24.206
cd ~/dormitory-telegram-bot

# Build natively on the VPS and start
docker compose up -d --build
```

---

## 5. Docker Compose Lifecycle on the VPS

Once running inside `~/dormitory-telegram-bot` on `javad@171.22.24.206`:

```bash
# Check container status
docker compose ps

# Follow real-time bot logs
docker compose logs -f

# View last 100 log lines
docker compose logs --tail 100

# Restart the bot
docker compose restart

# Stop the bot container
docker compose down

# Rebuild after updating code
docker compose up -d --build
```

### SELinux Volume Note
On systems with SELinux (e.g. Fedora, CentOS, RHEL), volume mounts in `docker-compose.yml` use `:z` to grant container write permissions:
```yaml
volumes:
  - ./data:/app/data:z
  - ./incoming_spreadsheets:/app/incoming_spreadsheets:z
```

---

## 6. Antigravity CLI (`agy`) Manual Workflow

When the manager uploads a cleaned spreadsheet via Telegram, the bot saves the file and outputs the command to execute.

### File Location on the VPS:
```text
~/dormitory-telegram-bot/incoming_spreadsheets/
├── cleaned_dormitory_transactions.xlsx
└── cleaned_dormitory_transactions_instructions.md
```

### Manual Execution with Antigravity:
SSH into the VPS and run:
```bash
cd ~/dormitory-telegram-bot

agy "Read incoming_spreadsheets/cleaned_dormitory_transactions.xlsx and companion instructions, validate transactions, and insert clean records into SQLite database"
```

Because the bot operates as an authenticated drop-zone, you retain 100% control over when and how Antigravity processes the data.

---

## 7. Environment Configuration Reference (`.env`)

Your production `.env` file should look like this:

```dotenv
# ==============================================================================
# Telegram Bot Configuration
# ==============================================================================
BOT_TOKEN=9074677263:AAGwmIWeAY0684TZOk0yd5Sw_gZQ6rF_EDM
ALLOWED_TELEGRAM_USER_IDS=5188908459

# Optional: Set only if the VPS blocks direct Telegram access
# TELEGRAM_PROXY_URL=socks5://127.0.0.1:10808

# ==============================================================================
# Storage & Drop-Zone
# ==============================================================================
DATA_DIR=data
DB_PATH=data/dormitory_bot.db
SESSIONS_DIR=data/sessions
SPREADSHEET_UPLOAD_DIR=incoming_spreadsheets
OVERWRITE_EXISTING_FILES=true

# ==============================================================================
# Processing Modes
# ==============================================================================
INGESTION_MODE=file_dropzone
MAX_IMAGE_DIMENSION_PX=320
CLEANUP_TEMP_FILES_ON_FINISH=false
```

---

## 8. Troubleshooting & Verification

### 1. How to verify Telegram connectivity:
```bash
curl -s https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getMe
```
Should return:
`{"ok":true,"result":{"id":9074677263,"username":"javad_personal_assistant_bot",...}}`

### 2. Verify Whitelist Security:
- Send `/start` from your authorized account (`5188908459` / `@SMJH9386`). The bot greets you with the main menu.
- If someone else sends `/start`, the bot replies:
  `⛔ Unauthorized access. Your User ID (xxx) is not whitelisted.` and drops the event.

### 3. Check Database Health:
To inspect sessions or blocks saved in SQLite:
```bash
sqlite3 data/dormitory_bot.db ".tables"
sqlite3 data/dormitory_bot.db "SELECT * FROM sessions;"
sqlite3 data/dormitory_bot.db "SELECT * FROM row_blocks;"
```

---

## 9. Live VPS Production Setup Details (`171.22.24.206`)

The bot is currently deployed and active on your AlmaLinux 9.8 VPS:

- **Bot Directory:** `/home/javad/projects/dormitory-telegram-bot/`
- **Main Dormitory Project:** `/home/javad/projects/dormitory-management/`
- **Drop-Zone Volume Mount:**
  ```yaml
  volumes:
    - ./data:/app/data:z
    - /home/javad/projects/dormitory-management:/app/incoming_spreadsheets:z
  ```
- **Proxy Configuration:** `TELEGRAM_PROXY_URL=socks5://127.0.0.1:1080` (powered by the server's Dante/OpenVPN namespace via `vpn-ctl`).
- **Container Network Mode:** `network_mode: "host"` (allows direct localhost communication to `127.0.0.1:1080` with zero inbound open ports).

### How to process uploaded files with Antigravity on the VPS:
1. Upload `.xlsx` via Telegram to `@javad_personal_assistant_bot`.
2. The file is placed directly in `/home/javad/projects/dormitory-management/{filename}.xlsx`.
3. SSH into the server and run Antigravity CLI:
   ```bash
   ssh azimi
   cd ~/projects/dormitory-management
   agy "Process the uploaded transaction spreadsheet in this directory following BATCH_RECEIPT_PROTOCOL.md, run record_receipt for valid rows, and delete the spreadsheet file once finished."
   ```


