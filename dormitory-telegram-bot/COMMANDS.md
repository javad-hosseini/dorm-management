# 🚀 Dormitory System & Docker Cheat Sheet (`COMMANDS.md`)

This quick reference guide contains all the essential CLI commands to manage:
1. **The Main Dormitory Management Service** (running on port **8080**)
2. **The Dormitory Telegram Bot** (running via **Docker Compose**)
3. **The SOCKS5 Proxy Service** (for Telegram connectivity)
4. **The Antigravity AI Agent** (for automated spreadsheet ingestion)

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

Directory: `~/projects/dorm/dormitory-telegram-bot/`

### Management Script (`./bot.sh`)
| Action | Helper Script | Docker Compose Command | Systemd Command |
| :--- | :--- | :--- | :--- |
| **Start Bot (Background)** | `./bot.sh start` | `docker compose up -d` | `sudo systemctl start dormitory-bot` |
| **View Real-Time Logs** | `./bot.sh logs` | `docker compose logs -f` | `journalctl -u dormitory-bot -f` |
| **Check Container Status** | `./bot.sh status` | `docker compose ps` | `sudo systemctl status dormitory-bot` |
| **Restart Bot** | `./bot.sh restart` | `docker compose restart` | `sudo systemctl restart dormitory-bot` |
| **Stop Container** | `./bot.sh stop` | `docker compose down` | `sudo systemctl stop dormitory-bot` |
| **Rebuild Container** | `./bot.sh build` | `docker compose build` | - |
| **Run Tests Locally** | `./bot.sh test` | - | - |

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
