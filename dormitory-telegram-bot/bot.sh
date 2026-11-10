#!/usr/bin/env bash
# ==============================================================================
# Dormitory Telegram Bot - Container Management Script 🚀
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

# Detect if current user can run docker without sudo
if docker info >/dev/null 2>&1; then
    DOCKER_COMPOSE="docker compose"
else
    DOCKER_COMPOSE="sudo docker compose"
fi

usage() {
    cat <<EOF
Usage: ./bot.sh [COMMAND]

Commands:
  start     - Start the Telegram bot container in the background
  stop      - Stop and remove the running bot container
  restart   - Restart the bot container
  status    - Check container status and running processes
  logs      - Tail bot container logs in real time (Ctrl+C to exit)
  build     - Rebuild the Docker image
  test      - Run test suite locally with uv
  help      - Show this help message

Examples:
  ./bot.sh start
  ./bot.sh logs
  ./bot.sh status
  ./bot.sh stop
EOF
}

COMMAND="${1:-help}"

case "${COMMAND}" in
    start)
        echo "🚀 Starting Dormitory Telegram Bot..."
        # Ensure directories exist
        mkdir -p data/sessions data/uploads data/reports incoming_spreadsheets /home/javad/projects/dormitory-management
        ${DOCKER_COMPOSE} up -d
        echo "✅ Bot container started. Checking status:"
        ${DOCKER_COMPOSE} ps
        ;;
    stop)
        echo "🛑 Stopping Dormitory Telegram Bot..."
        ${DOCKER_COMPOSE} down
        echo "✅ Bot container stopped."
        ;;
    restart)
        echo "🔄 Restarting Dormitory Telegram Bot..."
        ${DOCKER_COMPOSE} restart
        echo "✅ Bot container restarted."
        ${DOCKER_COMPOSE} ps
        ;;
    status)
        echo "📊 Container Status:"
        ${DOCKER_COMPOSE} ps
        ;;
    logs)
        echo "📜 Streaming bot logs (Ctrl+C to exit)..."
        ${DOCKER_COMPOSE} logs -f --tail=100
        ;;
    build)
        echo "🔨 Building Docker image..."
        ${DOCKER_COMPOSE} build
        echo "✅ Docker image built successfully."
        ;;
    test)
        echo "🧪 Running test suite..."
        uv run pytest
        ;;
    help|--help|-h)
        usage
        ;;
    *)
        echo "❌ Unknown command: ${COMMAND}"
        usage
        exit 1
        ;;
esac
