# User Guide — Dormitory Management System

> **این راهنما برای کاربر انسانی (نه هوش مصنوعی) نوشته شده است.**
> شامل دستورات روزمره توسعه، مدیریت سرور پروداکشن، و راهنمای استقرار کامل می‌شود.

---

## 📑 Table of Contents

1. [🧪 Local Development Commands](#1--local-development-commands)
2. [🧹 Transaction Purge Tool](#2--transaction-purge-tool)
3. [🌐 Useful URLs & Admin Panel](#3--useful-urls--admin-panel)
4. [🏢 Production Server Management (Port 8080)](#4--production-server-management-port-8080)
5. [🤖 Telegram Bot (Docker)](#5--telegram-bot-docker)
6. [🛡️ SOCKS5 Proxy & VPN Management](#6-️-socks5-proxy--vpn-management)
7. [📱 Executive Daily SMS Report](#7--executive-daily-sms-report)
8. [⚡ Processing Uploaded Spreadsheets (Antigravity)](#8--processing-uploaded-spreadsheets-antigravity)
9. [📋 One-Liner Health Check](#9--one-liner-health-check)
10. [🚀 Production Deployment Guide](#10--production-deployment-guide)
11. [💡 Windows Troubleshooting Tips](#11--windows-troubleshooting-tips)

---

## 1. 🧪 Local Development Commands

### Activate Virtual Environment
```powershell
# PowerShell:
.\venv\Scripts\Activate.ps1

# CMD:
.\venv\Scripts\activate.bat

# Direct (no activation needed):
.\venv\Scripts\python.exe manage.py runserver
```

### Django Management
```bash
# Start local server (default port 8000)
python manage.py runserver

# Start on custom port
python manage.py runserver 8080

# Apply migrations
python manage.py makemigrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Open Django shell
python manage.py shell

# Quick DB record count
.venv/bin/python manage.py shell -c "from apps.dormitory.models import Transaction, Resident, Room; print('Transactions:', Transaction.objects.count()); print('Residents:', Resident.objects.count()); print('Rooms:', Room.objects.count())"
```

### Running Automated Tests

> The system has **62 automated tests** covering Jalali calendar logic, billing, prepayment, purge, AI loader, and format validation.

```bash
# Run all dormitory tests
python manage.py test apps.dormitory

# Specific test classes:
python manage.py test apps.dormitory.tests.ClearTransactionsCommandTests
python manage.py test apps.dormitory.tests.IncompleteProfileTests
python manage.py test apps.dormitory.tests.ResidentPrepaymentAndOverdueTests
python manage.py test apps.dormitory.tests.AILoaderTests
```

---

## 2. 🧹 Transaction Purge Tool

> 🛡️ **Safety guarantee:** This script deletes **only financial transactions**. All **resident records (106)**, **rooms (41)**, dormitories, supervisors, and notes are 100% preserved.

```bash
# Dry-run preview (no changes applied) — always run this first:
python clear_transactions.py --dry-run --yes

# Interactive mode (shows stats, asks for confirmation):
python clear_transactions.py

# Full purge + reset settled_until to null (start fresh):
python clear_transactions.py --yes --reset-settled --include-archived

# Purge transactions but keep existing settled dates:
python clear_transactions.py --yes --keep-settled

# Via Django management command (equivalent):
python manage.py clear_transactions --dry-run --yes
python manage.py clear_transactions --yes --reset-settled
```

### Flags Reference

| Flag | Effect |
| :--- | :--- |
| `--dry-run` | Preview only — no DB changes |
| `-y` / `--yes` / `--force` | Skip confirmation prompts |
| `--reset-settled` | Set `settled_until = None` for all residents |
| `--keep-settled` | Preserve current settlement dates |
| `--include-archived` | Also purge archived (departed residents') transactions |
| `--exclude-archived` | Keep archived transactions, purge only active |

---

## 3. 🌐 Useful URLs & Admin Panel

| Section | URL | Description |
| :--- | :--- | :--- |
| 🏢 Main Dashboard | `http://127.0.0.1:8000/dashboard/` | Modern glass UI, room status, charts, Jalali calendar |
| 🎙️ AI Daily Loader | `http://127.0.0.1:8000/admin/ai-loader/` | Voice/text → DB via DeepSeek |
| ⚙️ Admin Panel | `http://127.0.0.1:8000/admin/` | Full Django admin with Jazzmin skin |
| 💳 Transactions | `http://127.0.0.1:8000/admin/dormitory/transaction/` | View, filter, approve payments |
| 👥 Residents | `http://127.0.0.1:8000/admin/dormitory/resident/` | Debt status, settlement dates, profile editing |

---

## 4. 🏢 Production Server Management (Port 8080)

**Directory:** `~/projects/dormitory-management/`

```bash
# Foreground (interactive output):
cd ~/projects/dormitory-management
./run_server.sh
# Or directly:
.venv/bin/python manage.py runserver 0.0.0.0:8080

# Background (persistent daemon with logging):
nohup .venv/bin/python manage.py runserver 0.0.0.0:8080 > server.log 2>&1 &

# Check if running:
ss -tulpn | grep :8080
curl -I http://localhost:8080

# View logs:
tail -f ~/projects/dormitory-management/server.log

# Stop:
pkill -f "manage.py runserver 0.0.0.0:8080"
```

---

## 5. 🤖 Telegram Bot (Docker)

**Directory:** `~/projects/dormitory-telegram-bot/`

| Action | Command |
| :--- | :--- |
| **Start (background)** | `cd ~/projects/dormitory-telegram-bot && docker compose up -d` |
| **View real-time logs** | `cd ~/projects/dormitory-telegram-bot && docker compose logs -f` |
| **Last 50 log lines** | `cd ~/projects/dormitory-telegram-bot && docker compose logs --tail 50` |
| **Check container status** | `cd ~/projects/dormitory-telegram-bot && docker compose ps` |
| **Restart bot** | `cd ~/projects/dormitory-telegram-bot && docker compose restart` |
| **Stop & remove** | `cd ~/projects/dormitory-telegram-bot && docker compose down` |
| **Rebuild after code edit** | `cd ~/projects/dormitory-telegram-bot && docker compose up -d --build` |

---

## 6. 🛡️ SOCKS5 Proxy & VPN Management

The Telegram bot uses the internal SOCKS5 proxy at `127.0.0.1:1080` to reach Telegram:

```bash
# Check status (should show ONLINE and SOCKS5 Proxy: 127.0.0.1:1080 ACTIVE)
sudo /usr/local/bin/vpn-ctl status

# Restart proxy if Telegram connection drops
sudo /usr/local/bin/vpn-ctl restart

sudo /usr/local/bin/vpn-ctl start
sudo /usr/local/bin/vpn-ctl stop
```

---

## 7. 📱 Executive Daily SMS Report

Generates and sends an executive SMS for **yesterday's** activity: income, transaction count, current-month cumulative income, remaining unpaid rent, and empty-bed breakdown by room.

```bash
# Send real SMS to 09210431554
.venv/bin/python manage.py sendreport

# Dry run (preview in terminal, no SMS sent)
.venv/bin/python manage.py sendreport --dry-run
```

### Options

| Flag | Description | Example |
| :--- | :--- | :--- |
| `--dry-run` | Print to terminal, don't send | `.venv/bin/python manage.py sendreport --dry-run` |
| `--date <YYYY/MM/DD>` | Target date (default: yesterday) | `--date "1405/08/10"` |
| `--phone <MOBILE>` | Override recipient | `--phone "09123456789"` |
| `--dorm-id <ID>` | Target dormitory (default: 1) | `--dorm-id 1` |
| `--real` | Force send via MeliPayamak in dev mode | `.venv/bin/python manage.py sendreport --real` |

### Automated Daily Cron (08:00 AM)
```bash
# Add to crontab -e:
0 8 * * * cd "/home/javad/projects/websites/Dormitory Management System/dormitory-management" && .venv/bin/python manage.py sendreport >> daily_report.log 2>&1
```

---

## 8. ⚡ Processing Uploaded Spreadsheets (Antigravity)

When a spreadsheet is uploaded via Telegram (`@javad_personal_assistant_bot`), it drops into `~/projects/dormitory-management/`. Run Antigravity to process it:

```bash
cd ~/projects/dormitory-management

agy "Process the uploaded transaction spreadsheet in this directory following BATCH_RECEIPT_PROTOCOL section of AGENTS.md, run record_receipt for valid rows, and delete the spreadsheet file once finished."
```

---

## 9. 📋 One-Liner Health Check

Run this on the VPS to verify all services at a glance:

```bash
echo "=== Port 8080 ===" && ss -tulpn | grep :8080 || echo "Port 8080: DOWN" ; \
echo "=== Docker Bot ===" && docker ps --filter "name=dormitory-telegram-bot" --format "table {{.Names}}\t{{.Status}}" ; \
echo "=== SOCKS5 Proxy ===" && ss -tulpn | grep :1080 || echo "Proxy 1080: DOWN"
```

---

## 10. 🚀 Production Deployment Guide

### Prerequisites (Ubuntu 22.04 / 24.04)
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl docker.io docker-compose-plugin
sudo systemctl enable --now docker
```
**Minimum specs:** 2 CPU cores, 2 GB RAM, 20 GB SSD.

---

### Method A: Docker Compose (Recommended for Linux VPS)

Runs Django (Gunicorn) + Nginx + PostgreSQL in isolated containers.

**Step 1 — Clone the repo:**
```bash
git clone <repo-url> /opt/dormitory-management
cd /opt/dormitory-management
```

**Step 2 — Configure environment:**
```bash
cp .env.example .env
nano .env
```
Key values to set:
- `SECRET_KEY` — a long random string
- `DEBUG=False`
- `ALLOWED_HOSTS` — your domain or IP (e.g. `dorm.example.ir,185.120.40.10`)
- `CSRF_TRUSTED_ORIGINS` — full domain with protocol (e.g. `https://dorm.example.ir`)
- `DB_PASSWORD` — strong PostgreSQL password
- `MELIPAYAMAK_API_TOKEN` — MeliPayamak API key (for SMS)

**Step 3 — Start:**
```bash
docker compose up -d --build
```
Migrations, staticfiles collection, and container startup all happen automatically.

**Step 4 — Create superuser:**
```bash
docker compose exec web python manage.py createsuperuser
```

**Step 5 — Verify:**
```bash
docker compose ps
docker compose logs -f web
```
Site is now accessible on port 80.

---

### SSL Certificate (Let's Encrypt / HTTPS)

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot certonly --webroot -w /opt/dormitory-management/certbot_www -d dorm.example.ir
```

Add to `.env`:
```env
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
```

Restart:
```bash
docker compose restart web nginx
```

---

### Method B: Liara Cloud (No self-managed server)

1. Create a **PostgreSQL** database in the Liara panel.
2. Create a **Python app** in Liara.
3. Set environment variables in the Liara app panel: `SECRET_KEY`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`.
4. Create a **Disk** for media files at `/app/media`.
5. Deploy:
```bash
liara deploy
```

---

### Backup & Restore

```bash
# Create DB backup:
docker compose exec db pg_dump -U postgres dormitory_db > backup_$(date +%Y%m%d_%H%M%S).sql

# Backup resident document images:
tar -czvf media_backup_$(date +%Y%m%d).tar.gz media/

# Restore DB:
cat backup_file.sql | docker compose exec -T db psql -U postgres dormitory_db
```

**Automated nightly backup (cron at 03:00 AM):**
```bash
0 3 * * * cd /opt/dormitory-management && docker compose exec -T db pg_dump -U postgres dormitory_db | gzip > /opt/backups/db_$(date +\%Y\%m\%d).sql.gz
```

---

### Production Security Notes

1. **DB port isolation:** PostgreSQL port 5432 is not exposed to the host — only the `web` container can reach it via the internal Docker network.
2. **Brute-force protection:** Nginx rate-limits `/accounts/login/` to 5 requests/minute per IP.
3. **Upload size:** Max file upload is 15 MB; uploaded ID card images are auto-compressed by Pillow.
4. **Access control:** No resident can access another resident's data or the admin panel.

---

## 11. 💡 Windows Troubleshooting Tips

### PowerShell ExecutionPolicy Error
If `Activate.ps1` is blocked:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### Browser Cache for Jalali Calendar / Styles
If style or calendar changes don't appear, hard-refresh:
- **Windows:** `Ctrl + F5` or `Ctrl + Shift + R`
