#!/usr/bin/env bash
# ==============================================================================
# Dormitory Management System & Bot - Unified Service Runner 🚀
# ==============================================================================
# Controls both the host Django backend service and the Dockerized Telegram Bot.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

DJANGO_PORT="${DJANGO_PORT:-8080}"
DJANGO_HOST="${DJANGO_HOST:-0.0.0.0}"
DJANGO_PID_FILE="${SCRIPT_DIR}/.django.pid"
DJANGO_LOG_FILE="${SCRIPT_DIR}/django.log"
BOT_DIR="${SCRIPT_DIR}/dormitory-telegram-bot"
BOT_SCRIPT="${BOT_DIR}/bot.sh"

# ------------------------------------------------------------------------------
# Python & Environment Discovery
# ------------------------------------------------------------------------------
find_python() {
    if [[ -x "${SCRIPT_DIR}/.venv/bin/python" ]]; then
        echo "${SCRIPT_DIR}/.venv/bin/python"
    elif [[ -x "${SCRIPT_DIR}/venv/bin/python" ]]; then
        echo "${SCRIPT_DIR}/venv/bin/python"
    elif command -v python3 >/dev/null 2>&1; then
        echo "$(command -v python3)"
    else
        echo ""
    fi
}

PYTHON_BIN="$(find_python)"

ensure_prerequisites() {
    # Ensure spreadsheet storage folders and symlinks exist
    mkdir -p media/spreadsheets/incoming media/spreadsheets/processed media/spreadsheets/failed
    if [[ ! -L "${SCRIPT_DIR}/incoming_spreadsheets" ]]; then
        ln -sfn media/spreadsheets/incoming "${SCRIPT_DIR}/incoming_spreadsheets"
    fi
}

# ------------------------------------------------------------------------------
# Django Management
# ------------------------------------------------------------------------------
is_django_running() {
    if [[ -f "${DJANGO_PID_FILE}" ]]; then
        local pid
        pid="$(cat "${DJANGO_PID_FILE}" 2>/dev/null || true)"
        if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
            return 0
        else
            rm -f "${DJANGO_PID_FILE}"
        fi
    fi
    # Also check if another runserver is holding the target port
    if ss -tulpn 2>/dev/null | grep -q ":${DJANGO_PORT}\b"; then
        return 0
    fi
    return 1
}

get_django_pid() {
    if [[ -f "${DJANGO_PID_FILE}" ]]; then
        cat "${DJANGO_PID_FILE}" 2>/dev/null || true
    else
        # Find pid listening on DJANGO_PORT
        ss -tulpn 2>/dev/null | grep ":${DJANGO_PORT}\b" | awk '{print $NF}' | sed -E 's/.*pid=([0-9]+).*/\1/' || true
    fi
}

django_run_foreground() {
    ensure_prerequisites
    if [[ -z "${PYTHON_BIN}" ]]; then
        echo "❌ Error: Python virtual environment not found (.venv/bin/python)."
        exit 1
    fi
    echo "🌟 Starting Django development server on http://${DJANGO_HOST}:${DJANGO_PORT} (Foreground)..."
    echo "   Press Ctrl+C to stop."
    exec "${PYTHON_BIN}" manage.py runserver "${DJANGO_HOST}:${DJANGO_PORT}" "$@"
}

django_start_daemon() {
    ensure_prerequisites
    if [[ -z "${PYTHON_BIN}" ]]; then
        echo "❌ Error: Python virtual environment not found (.venv/bin/python)."
        exit 1
    fi
    if is_django_running; then
        local pid
        pid="$(get_django_pid)"
        echo "⚠️ Django is already running (PID: ${pid:-unknown}, Port: ${DJANGO_PORT})."
        return 0
    fi

    echo "🚀 Starting Django backend in background (Port: ${DJANGO_PORT})..."
    nohup "${PYTHON_BIN}" manage.py runserver "${DJANGO_HOST}:${DJANGO_PORT}" "$@" > "${DJANGO_LOG_FILE}" 2>&1 &
    local new_pid=$!
    echo "${new_pid}" > "${DJANGO_PID_FILE}"
    sleep 1

    if kill -0 "${new_pid}" 2>/dev/null; then
        echo "✅ Django started successfully (PID: ${new_pid})."
        echo "   Logs: tail -f ${DJANGO_LOG_FILE}"
        echo "   URL:  http://localhost:${DJANGO_PORT}/"
    else
        echo "❌ Django failed to start. Last log entries:"
        tail -n 15 "${DJANGO_LOG_FILE}" 2>/dev/null || true
        rm -f "${DJANGO_PID_FILE}"
        return 1
    fi
}

django_stop() {
    echo "🛑 Stopping Django backend..."
    local stopped=0
    if [[ -f "${DJANGO_PID_FILE}" ]]; then
        local pid
        pid="$(cat "${DJANGO_PID_FILE}" 2>/dev/null || true)"
        if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
            kill "${pid}" 2>/dev/null || true
            sleep 1
            if kill -0 "${pid}" 2>/dev/null; then
                kill -9 "${pid}" 2>/dev/null || true
            fi
            stopped=1
        fi
        rm -f "${DJANGO_PID_FILE}"
    fi

    # Kill any lingering process on DJANGO_PORT
    local lingering
    lingering="$(ss -tulpn 2>/dev/null | grep ":${DJANGO_PORT}\b" | awk '{print $NF}' | sed -E 's/.*pid=([0-9]+).*/\1/' || true)"
    if [[ -n "${lingering}" ]]; then
        kill "${lingering}" 2>/dev/null || true
        stopped=1
    fi

    if [[ ${stopped} -eq 1 ]]; then
        echo "✅ Django server stopped."
    else
        echo "ℹ️ Django was not running."
    fi
}

django_restart() {
    echo "🔄 Restarting Django backend..."
    django_stop
    sleep 1
    django_start_daemon "$@"
}

django_status() {
    echo -n "• Django Backend: "
    if is_django_running; then
        local pid
        pid="$(get_django_pid)"
        echo -e "\033[0;32mRUNNING\033[0m (PID: ${pid:-active}, Port: ${DJANGO_PORT})"
    else
        echo -e "\033[0;31mSTOPPED\033[0m"
    fi
}

django_logs() {
    if [[ -f "${DJANGO_LOG_FILE}" ]]; then
        echo "📜 Streaming Django logs (${DJANGO_LOG_FILE}, Ctrl+C to exit)..."
        tail -f -n 50 "${DJANGO_LOG_FILE}"
    else
        echo "ℹ️ No Django log file found at ${DJANGO_LOG_FILE}"
    fi
}

# ------------------------------------------------------------------------------
# Telegram Bot Management
# ------------------------------------------------------------------------------
bot_cmd() {
    if [[ ! -f "${BOT_SCRIPT}" ]]; then
        echo "❌ Error: Bot script not found at ${BOT_SCRIPT}"
        exit 1
    fi
    "${BOT_SCRIPT}" "$@"
}

bot_status_brief() {
    echo -n "• Telegram Bot:   "
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^dormitory-telegram-bot$"; then
        echo -e "\033[0;32mRUNNING\033[0m (Container: dormitory-telegram-bot)"
    else
        echo -e "\033[0;31mSTOPPED\033[0m"
    fi
}

# ------------------------------------------------------------------------------
# Usage & Help
# ------------------------------------------------------------------------------
usage() {
    cat <<EOF
Dormitory Management System - Unified Service Runner

Usage:
  ./run_server.sh [TARGET] [ACTION] [OPTIONS]
  ./run_server.sh [ACTION]

Primary Targets:
  django    Manage the host Django web application
  bot       Manage the containerized Telegram Bot
  all       Manage both services simultaneously

Available Actions:
  start     Start service(s) in background daemon mode
  stop      Stop running service(s)
  restart   Restart service(s)
  status    Show current running status of services
  logs      Stream live logs
  run       Run Django in interactive foreground mode (default if no args)

Quick Examples:
  ./run_server.sh                # Start Django in interactive foreground (default port 8080)
  ./run_server.sh status         # Show status of both Django and Telegram Bot
  ./run_server.sh start          # Start both Django (daemon) and Telegram Bot container
  ./run_server.sh stop           # Stop both Django and Telegram Bot
  ./run_server.sh restart        # Restart both services

Targeted Examples:
  ./run_server.sh django start   # Start Django in background on port 8080
  ./run_server.sh django run     # Run Django in foreground
  ./run_server.sh django logs    # Stream Django logs
  ./run_server.sh bot start      # Start Telegram Bot container
  ./run_server.sh bot logs       # Stream Telegram Bot logs
  ./run_server.sh bot status     # Detailed bot container status
  ./run_server.sh bot stop       # Stop Telegram Bot container

Custom Port:
  DJANGO_PORT=8000 ./run_server.sh
  ./run_server.sh 0.0.0.0:8000
EOF
}

# ------------------------------------------------------------------------------
# Main Dispatcher
# ------------------------------------------------------------------------------
TARGET="${1:-}"

case "${TARGET}" in
    "")
        django_run_foreground
        ;;
    help|--help|-h)
        usage
        ;;
    django)
        ACTION="${2:-run}"
        shift 2 || shift 1
        case "${ACTION}" in
            run)     django_run_foreground "$@" ;;
            start)   django_start_daemon "$@" ;;
            stop)    django_stop ;;
            restart) django_restart "$@" ;;
            status)  django_status ;;
            logs)    django_logs ;;
            *)       django_run_foreground "${ACTION}" "$@" ;;
        esac
        ;;
    bot)
        ACTION="${2:-start}"
        shift 2 || shift 1
        bot_cmd "${ACTION}" "$@"
        ;;
    all)
        ACTION="${2:-status}"
        shift 2 || shift 1
        case "${ACTION}" in
            start)
                echo "🚀 Starting all services..."
                django_start_daemon
                bot_cmd start
                echo ""
                django_status
                bot_status_brief
                ;;
            stop)
                echo "🛑 Stopping all services..."
                django_stop
                bot_cmd stop
                ;;
            restart)
                echo "🔄 Restarting all services..."
                django_stop
                bot_cmd stop
                sleep 1
                django_start_daemon
                bot_cmd start
                ;;
            status)
                echo "📊 Services Status:"
                django_status
                bot_status_brief
                ;;
            *)
                echo "❌ Unknown action for 'all': ${ACTION}"
                usage
                exit 1
                ;;
        esac
        ;;
    start)
        shift 1
        echo "🚀 Starting both Django and Bot services..."
        django_start_daemon "$@"
        bot_cmd start
        echo ""
        django_status
        bot_status_brief
        ;;
    stop)
        echo "🛑 Stopping both Django and Bot services..."
        django_stop
        bot_cmd stop
        ;;
    restart)
        shift 1
        echo "🔄 Restarting both services..."
        django_stop
        bot_cmd stop
        sleep 1
        django_start_daemon "$@"
        bot_cmd start
        ;;
    status)
        echo "📊 Services Status:"
        django_status
        bot_status_brief
        ;;
    logs)
        django_logs
        ;;
    *)
        # If user passed arguments like port 8000, 0.0.0.0:8000, or flags like --noreload
        if [[ "${TARGET}" =~ ^[0-9]+$ ]]; then
            DJANGO_PORT="${TARGET}"
            shift 1
            django_run_foreground "$@"
        elif [[ "${TARGET}" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+:[0-9]+$ ]]; then
            DJANGO_HOST="$(echo "${TARGET}" | cut -d: -f1)"
            DJANGO_PORT="$(echo "${TARGET}" | cut -d: -f2)"
            shift 1
            django_run_foreground "$@"
        elif [[ "${TARGET}" == -* ]]; then
            django_run_foreground "$@"
        else
            echo "❌ Unknown command or target: ${TARGET}"
            echo ""
            usage
            exit 1
        fi
        ;;
esac
