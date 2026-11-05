# 🚀 Dormitory System & Docker Cheat Sheet (`COMMANDS.md`)

This quick reference guide contains all the essential CLI commands to manage:
1. **The Main Dormitory Management Service** (running on port **8080**)
2. **The Dormitory Telegram Bot** (running via **Docker Compose**)
3. **The SOCKS5 Proxy Service** (for Telegram connectivity)
4. **The Antigravity AI Agent** (for automated spreadsheet ingestion)
5. **One-Liner Quick Health Check**
6. **Executive Daily SMS Report** (`python manage.py sendreport`)
7. **Single / Split Receipt Ingestion** (`python manage.py record_receipt`)

---

## 🏢 1. Main Dormitory Service (Port 8080)

Directory: `~/projects/dormitory-management/`

### Start the Service

#### Option A: Foreground (Interactive / Terminal output)
```bash
cd ~/projects/dormitory-management
./run_server.sh
# Or directly via virtualenv:
.venv/bin/python manage.py runserver 0.0.0.0:8080
```

#### Option B: Background (Persistent Daemon with logging)
```bash
cd ~/projects/dormitory-management
nohup .venv/bin/python manage.py runserver 0.0.0.0:8080 > server.log 2>&1 &
```

---

### Check Service Status & Port 8080
```bash
# Check if port 8080 is listening
ss -tulpn | grep :8080

# Test HTTP response
curl -I http://localhost:8080
```

---

### View Main Service Logs
```bash
tail -f ~/projects/dormitory-management/server.log
```

---

### Stop the Service
```bash
pkill -f "manage.py runserver 0.0.0.0:8080"
```

---

## 🤖 2. Telegram Bot (Docker Containers)

Directory: `~/projects/dormitory-telegram-bot/`

| Action | Command |
| :--- | :--- |
| **Start Bot (Background)** | `cd ~/projects/dormitory-telegram-bot && docker compose up -d` |
| **View Real-Time Logs** | `cd ~/projects/dormitory-telegram-bot && docker compose logs -f` |
| **View Last 50 Log Lines** | `cd ~/projects/dormitory-telegram-bot && docker compose logs --tail 50` |
| **Check Container Status** | `cd ~/projects/dormitory-telegram-bot && docker compose ps` |
| **Restart Bot** | `cd ~/projects/dormitory-telegram-bot && docker compose restart` |
| **Stop & Remove Container** | `cd ~/projects/dormitory-telegram-bot && docker compose down` |
| **Rebuild After Code Edit** | `cd ~/projects/dormitory-telegram-bot && docker compose up -d --build` |

---

## 🛡️ 3. SOCKS5 Proxy & VPN Management (VPS)

The Telegram bot uses the internal SOCKS5 proxy on `127.0.0.1:1080` to reach Telegram securely:

```bash
# Check proxy status (Should show ONLINE and SOCKS5 Proxy: 127.0.0.1:1080 ACTIVE)
sudo /usr/local/bin/vpn-ctl status

# Restart proxy if Telegram connection drops
sudo /usr/local/bin/vpn-ctl restart

# Start proxy
sudo /usr/local/bin/vpn-ctl start

# Stop proxy
sudo /usr/local/bin/vpn-ctl stop
```

---

## ⚡ 4. Process Uploaded Spreadsheets with Antigravity (`agy`)

When a spreadsheet is uploaded via Telegram (`@javad_personal_assistant_bot`), it drops automatically into the root of `~/projects/dormitory-management/`.

Execute Antigravity to parse and record receipts:
```bash
cd ~/projects/dormitory-management

agy "Process the uploaded transaction spreadsheet in this directory following BATCH_RECEIPT_PROTOCOL.md, run record_receipt for valid rows, and delete the spreadsheet file once finished."
```

---

## 📋 5. One-Liner Quick Health Check

Run this single command on the VPS to verify all services at a glance:
```bash
echo "=== Port 8080 ===" && ss -tulpn | grep :8080 || echo "Port 8080: DOWN" ; \
echo "=== Docker Bot ===" && docker ps --filter "name=dormitory-telegram-bot" --format "table {{.Names}}\t{{.Status}}" ; \
echo "=== SOCKS5 Proxy ===" && ss -tulpn | grep :1080 || echo "Proxy 1080: DOWN"
```

---

## 📱 6. Executive Daily SMS Report (`python manage.py sendreport`)

Generates and sends an executive SMS summary for **yesterday's** activity (or any custom date) including yesterday's income, transaction count, current month's cumulative income, remaining unpaid rent for the current month, and a line-by-line breakdown of empty beds by room.

Directory: `~/projects/dormitory-management/`

### Direct Execution (Sends Real SMS to `09210431554`)
```bash
.venv/bin/python manage.py sendreport
```

### Dry Run (Preview in Terminal without sending SMS)
```bash
.venv/bin/python manage.py sendreport --dry-run
```

### Options & Flags
| Flag | Description | Example |
| :--- | :--- | :--- |
| `--dry-run` | Output message to terminal without sending SMS | `.venv/bin/python manage.py sendreport --dry-run` |
| `--date <YYYY/MM/DD>` | Specify report target date (Default: Yesterday) | `.venv/bin/python manage.py sendreport --date "1405/08/10"` |
| `--phone <MOBILE>` | Override recipient phone number | `.venv/bin/python manage.py sendreport --phone "09123456789"` |
| `--dorm-id <ID>` | Target dormitory ID (Default: `1` خوابگاه نوید) | `.venv/bin/python manage.py sendreport --dorm-id 1` |
| `--real` | Force send via MeliPayamak even in console/dev mode | `.venv/bin/python manage.py sendreport --real` |

### Automated Daily Scheduling (Cron Job)
To send the executive summary every day automatically at 08:00 AM, add this line to `crontab -e`:
```bash
0 8 * * * cd "/home/javad/projects/websites/Dormitory Management System/dormitory-management" && .venv/bin/python manage.py sendreport >> daily_report.log 2>&1
```

---

## 🧾 7. Manual & POS Receipt Processing (`python manage.py record_receipt`)

Atomic CLI tool to register single or split receipts with Jalali settlement advancement.

### Single Rent Payment
```bash
.venv/bin/python manage.py record_receipt \
  --resident "امید رضایی" \
  --room "105" \
  --amount-tomans 3800000 \
  --type RENT \
  --method CARD \
  --date "1405/08/10 11:30:00" \
  --ref "123456"
```

### Split Payment (Rent + Deposit in One Transaction)
```bash
.venv/bin/python manage.py record_receipt \
  --resident "امید رضایی" \
  --room "105" \
  --deposit-tomans 1000000 \
  --rent-tomans 3800000 \
  --date "1405/08/10 11:30:00" \
  --ref "123456"
```
