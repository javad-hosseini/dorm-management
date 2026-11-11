# Dormitory Telegram Bot 🏢💳

A production-ready, Dockerized Telegram Bot built with Python 3.12+, managed strictly with `uv`, and powered by `aiogram 3`, `openpyxl`, `Pillow`, and `aiosqlite`.

Designed to eliminate operational bottlenecks for Dormitory Managers by digitizing physical notebook entries, POS paper receipts, card-to-card transfer notes, and tenant annotations directly from mobile devices into cell-anchored Excel spreadsheets and syncing cleaned transactions with Dormitory Management Systems or AI Agents.

---

## Architecture & Directory Layout

```text
dormitory-telegram-bot/
├── pyproject.toml              # Dependencies & build configuration managed by uv
├── uv.lock                     # Deterministic dependency lockfile
├── .python-version             # Python version pin (3.12)
├── Dockerfile                  # Container definition using astral-sh/uv:python3.12-bookworm-slim
├── docker-compose.yml          # Production container orchestration with volume mounts
├── .env.example                # Template for environment variables and secrets
├── .dockerignore               # Optimized image build exclusions
├── README.md                   # Full operational and architectural documentation
├── config/
│   └── default_agent_instructions.md # Base ledger parsing instructions for AI Agent
├── src/
│   ├── __init__.py
│   ├── main.py                 # Application entrypoint, lifecycle, and middleware registration
│   ├── config.py               # Pydantic Settings loading and validation
│   ├── database/
│   │   ├── __init__.py
│   │   └── repository.py       # Async SQLite persistence (crash recovery & row hash idempotency)
│   ├── middlewares/
│   │   ├── __init__.py
│   │   ├── auth.py             # User ID whitelist security middleware
│   │   └── album.py            # MediaGroup (album) debounce aggregator (0.6s)
│   ├── bot/
│   │   ├── __init__.py
│   │   ├── states.py           # Aiogram FSM state groups (RawDataStates, IngestStates)
│   │   ├── keyboards.py        # Reply and Inline control keyboards
│   │   └── handlers/
│   │       ├── __init__.py
│   │       ├── common.py       # /start, /help, /cancel, persistent main menu
│   │       ├── raw_data.py     # Feature 1: Raw photos, albums, undo/clear, export
│   │       └── ingest_cleaned.py # Feature 2: Cleaned .xlsx upload, preview, sync, error report
│   └── services/
│       ├── __init__.py
│       ├── excel_builder.py    # OpenPyXL + Pillow generator with cell-anchored images & guide tab
│       ├── excel_parser.py     # OpenPyXL parser, deterministic row hasher, and failed rows report
│       └── dormitory_client.py # Modular async client (file_dropzone, mock, webhook, openai)
└── tests/
    ├── conftest.py             # Shared fixtures: mock Bot, FSMContext, synthetic Pillow receipts
    ├── unit/
    │   ├── test_config.py      # Env parsing & allowed user ID list validation
    │   ├── test_repository.py  # SQLite persistence, crash recovery, undo/clear, SHA-256 idempotency
    │   ├── test_excel_builder.py # OpenPyXL cell-anchored images & guide sheet verification
    │   ├── test_excel_parser.py  # Cleaned .xlsx parser, date normalization, failed rows report
    │   ├── test_dormitory_client.py # File drop-zone, webhook, and OpenAI agent modes
    │   ├── test_middlewares.py # AuthMiddleware whitelist & AlbumMiddleware debouncing
    │   ├── test_common_handlers.py # /start, /help, /cancel command handlers
    │   └── test_main.py        # Application bootstrapping and proxy initialization
    └── integration/
        ├── test_raw_data_flow.py # Complete Feature 1 raw data collection FSM flow
        └── test_ingest_cleaned_flow.py # Complete Feature 2 spreadsheet ingestion FSM flow
```

---

## Key Features

### 1. Security Whitelist Middleware (`AuthMiddleware`)
- Intercepts all incoming messages and callback queries.
- Verifies `event.from_user.id` against `ALLOWED_TELEGRAM_USER_IDS` in `.env`.
- Unauthorized users receive an explicit rejection notice:
  `⛔ Unauthorized access. Your User ID ({user_id}) is not whitelisted.`
  and the event is immediately dropped.

### 2. Feature 1: Raw Data Collection & Cell-Anchored `.xlsx` Builder
- **Row-by-Row Resident Grouping:** Resident #1's receipts and notes are placed in Row 1; Resident #2's in Row 2, etc.
- **Arbitrary Inputs Without Interruption:** Send text notes, single receipts, photos with captions, or multi-photo albums continuously.
- **Automatic Column Assignment for Photo Captions:** If a photo has a caption, the photo is stored in Column $C$ as an image, and the caption is automatically appended to Column $C+1$ as a text note.
- **MediaGroup (Album) Debounce:** The `AlbumMiddleware` batches photos sent in an album within a `0.6s` debounce window, ensuring consecutive atomic columns and a single consolidated status message.
- **Crash Recovery & Session Persistence:** In-progress sessions and block coordinates survive bot and container restarts via `aiosqlite`. If the bot restarts mid-session, the manager can tap `[▶️ Resume Existing Session]`.
- **Row Correction Controls:**
  - `[➕ Next Resident]`: Advances to the next resident row (with empty-row guard).
  - `[↩️ Undo Last Block]`: Removes the previous block and cleans up the temporary image file. Steps back to previous row if current row is empty.
  - `[🗑️ Clear Row]`: Resets the current row and cleans up its stored photos.
- **Cell-Anchored OpenPyXL Workbook:**
  - **Sheet 1 (`Raw_Transactions`):**
    - `Col A = "Resident_Row_ID"`, `Col B = "Block_1"`, `Col C = "Block_2"`, etc.
    - Proportional image thumbnailing (max 320px) using Pillow with **EXIF orientation handling** (`ImageOps.exif_transpose`) so camera photos from smartphones remain upright.
    - Explicit text anchor reference written in cell value: `[IMAGE_ANCHOR: C2 | file: photo.jpg]`.
    - Strict cell anchoring via `openpyxl.drawing.image.Image` with row height expanded to `250pt` and column width to `45` to prevent visual overlapping.
  - **Sheet 2 (`_AI_EXTRACTION_GUIDE`):**
    - Contains instructions and a 15-line ready-to-run Python snippet for AI Code Interpreters to iterate `ws._images` and correlate receipt images to each resident row and block coordinate.

### 3. Feature 2: Cleaned Spreadsheet Ingestion & Antigravity CLI Drop-Zone
- **Zero External API Dependency:** Functions directly as an authenticated SFTP-like file channel from mobile to server.
- **Configurable Drop-Zone Path:** Uploaded `.xlsx` spreadsheets are saved directly into `SPREADSHEET_UPLOAD_DIR` (e.g. `./incoming_spreadsheets` or project root).
- **Companion Instructions File:** If custom instructions are provided in the caption, the bot saves `{filename}_instructions.md` alongside the `.xlsx` file.
- **Automated Processing with `manage.py process_excel`:**
  Both raw session workbooks and cleaned spreadsheets deposited in the drop-zone can be immediately processed:
  ```bash
  # Preview (Dry-Run):
  .venv/bin/python manage.py process_excel --file incoming_spreadsheets/<filename>.xlsx --dry-run

  # Apply and commit:
  .venv/bin/python manage.py process_excel --file incoming_spreadsheets/<filename>.xlsx --apply --archive
  ```
- **Data Parsing & Duplicate Checking:** Checks row counts, normalizes dates, and hashes rows with deterministic SHA-256 to alert if a file was previously uploaded.
- **Alternative Optional Modes:** Also supports `agent_webhook`, `openai_compatible_agent`, and `mock_dry_run` if external API sync is ever desired.

---

## Setup & Deployment

### Prerequisites
- Python 3.12+
- `uv` package manager (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Docker & Docker Compose (for containerized deployment)

### 1. Local Development with `uv`

```bash
# Clone repository
cd dormitory-telegram-bot

# Copy environment template
cp .env.example .env

# Edit .env with your Telegram BOT_TOKEN and ALLOWED_TELEGRAM_USER_IDS
nano .env

# Sync dependencies and create .venv
uv sync --extra dev

# Run all tests
uv run pytest -v

# Launch the bot
uv run python -m src.main
```

### 2. Docker & Docker Compose Deployment

```bash
# Verify environment file exists
cp -n .env.example .env

# Build and start container in detached mode
docker compose up -d --build

# View real-time logs
docker compose logs -f dormitory-bot

# Stop the container
docker compose down
```

---

## Configuration Reference (`.env`)

| Variable | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `BOT_TOKEN` | string | *required* | Telegram Bot API token from `@BotFather` |
| `ALLOWED_TELEGRAM_USER_IDS` | string | `""` | Comma-separated whitelisted Telegram User IDs |
| `TELEGRAM_PROXY_URL` | string | `""` | Optional HTTP or SOCKS5 proxy URL (e.g. `socks5://127.0.0.1:10808` or `http://127.0.0.1:2080`) |
| `DATA_DIR` | path | `data` | Base directory for runtime storage |
| `DB_PATH` | path | `data/dormitory_bot.db` | SQLite database file location |
| `SESSIONS_DIR` | path | `data/sessions` | Directory for active raw photo sessions |
| `SPREADSHEET_UPLOAD_DIR` | path | `incoming_spreadsheets` | Directory where uploaded .xlsx files are placed for Antigravity CLI |
| `OVERWRITE_EXISTING_FILES` | boolean | `true` | Overwrite existing spreadsheet files with same name in drop-zone |
| `MAX_IMAGE_DIMENSION_PX` | integer | `320` | Max pixel dimension for embedded cell thumbnails |
| `CLEANUP_TEMP_FILES_ON_FINISH` | boolean | `false` | Clean up raw image files after exporting raw xlsx |
| `INGESTION_MODE` | string | `file_dropzone` | `file_dropzone` (default), `mock_dry_run`, `agent_webhook`, `openai_compatible_agent` |
| `DORMITORY_AGENT_API_URL` | string | `""` | Target webhook URL for dormitory agent / API |
| `DORMITORY_AGENT_API_KEY` | string | `""` | Bearer token for agent API |
| `DORMITORY_BACKEND_API_URL` | string | `""` | Backend ERP / ledger endpoint for LLM tool call |
| `OPENAI_BASE_URL` | string | `https://api.openai.com/v1` | LLM agent endpoint |
| `OPENAI_API_KEY` | string | `""` | API key for OpenAI-compatible model |
| `AGENT_MODEL` | string | `gpt-4o-mini` | LLM model identifier |
| `DEFAULT_AGENT_INSTRUCTIONS` | string | `""` | Custom default prompt (falls back to `config/default_agent_instructions.md`) |

---

## Testing & Quality Verification

The test suite covers configuration, SQLite persistence, Excel generation, OpenPyXL parsing, middleware filtering, media group debouncing, and handler state transitions:

```bash
uv run pytest -v --tb=short
```

**Test Coverage Summary:**
- ✅ User ID whitelisting and unauthorized access drops (`AuthMiddleware`)
- ✅ Media group album debouncing with `0.6s` aggregation (`AlbumMiddleware`)
- ✅ Row and block creation with automatic column indexing
- ✅ Undo logic stepping back across empty rows
- ✅ EXIF auto-rotation and cell-anchored image embedding (`openpyxl`)
- ✅ `_AI_EXTRACTION_GUIDE` worksheet snippet generation
- ✅ Deterministic SHA-256 row hashing and duplicate detection
- ✅ Dry-run preview and custom agent instruction overrides
- ✅ Automatic `failed_rows_report.xlsx` generation on processing errors
- ✅ Webhook client retry backoff and fallback handling

---

## License
MIT License. Built for dormitory managers and operations teams.
