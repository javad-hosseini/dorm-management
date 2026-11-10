# Project: Dormitory Management Monorepo Consolidation & Service Integration

## Architecture
- **Repository Structure**: Monorepo under `/home/javad/projects/dorm/dormitory-management`. Houses the Django backend (apps/dormitory), the containerized Telegram bot (`dormitory-telegram-bot/`), and documentation/tools.
- **Git Remote Topology**: Dual push remotes configured on `origin`. Commits pushed to `origin` update both GitHub (`git@github.com:javad-hosseini/dorm-management.git`) and the on-premise Gitea server (`ssh://git@94.183.146.0:22022/Javad/dormitory-management.git`) synchronously.
- **Service Integration Architecture**:
  - Non-dockerized Django service on the host running natively with Python 3.12 and SQLite database (`db.sqlite3`).
  - Containerized Telegram bot running via Docker with `network_mode: "host"` and mapped user permissions (`1000:1000`).
  - Shared filesystem dropzone located at `media/spreadsheets/incoming/` (symlinked as `incoming_spreadsheets/` at project root). The bot writes incoming transaction `.xlsx` documents and companion instruction `.md` files; host Django management commands (`record_receipt`, `reconcile_bank_statement`) and Antigravity processing agents read, process, and archive them.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| F1 | Nested Git Elimination | Backup and delete nested `.git` inside `dormitory-telegram-bot` to dissolve nested repo | M1 | ORIGINAL_REQUEST §R1 |
| F2 | Monorepo Bot Tracking | Stage and commit all 47 Telegram bot codebase files directly in root `dormitory-management` git repo | M1 | ORIGINAL_REQUEST §R1 |
| F3 | Git Ignore Alignment | Add `.agents/` to root `.gitignore` and preserve hierarchical ignore rules | M1 | Survey Explorer 1 |
| F4 | Sibling Directory Cleanup | Deprecate and remove empty sibling `/home/javad/projects/dorm/dormitory-telegram-bot` stub | M1 | Survey Explorer 1 |
| F5 | Gitea SSH Key Authorization | Register local public key `~/.ssh/id_ed25519.pub` in Gitea user Javad via admin API token | M2 | Survey Explorer 2 |
| F6 | Gitea History Synchronization | Align divergent initial commit in Gitea repo with root repository history via initial force push | M2 | Survey Explorer 2 |
| F7 | Dual Push Remote Configuration | Set up `origin` with dual push URLs for GitHub SSH and Gitea SSH | M2 | ORIGINAL_REQUEST §R2 |
| F8 | Git Dual Push Verification | Verify `git remote -v`, test SSH handshakes, and verify push synchronization to both servers | M2 | ORIGINAL_REQUEST §R2 |
| F9 | Shared Directory Hierarchy | Establish `media/spreadsheets/` with `incoming/`, `processed/`, and `failed/` subdirectories and `.gitkeep` | M3 | ORIGINAL_REQUEST §R3 |
| F10 | Monorepo Relative Volume Mount | Update `docker-compose.yml` to mount `../media/spreadsheets/incoming:/app/incoming_spreadsheets:z` | M3 | Survey Explorer 3 |
| F11 | Container User & Permissions | Configure `user: "${BOT_UID:-1000}:${BOT_GID:-1000}"` in compose to guarantee non-root file ownership | M3 | Survey Explorer 3 |
| F12 | Root Dropzone Symlink | Create root symlink `incoming_spreadsheets -> media/spreadsheets/incoming` for backward compatibility | M3 | Survey Explorer 3 |
| F13 | Bot Startup Script Update | Update `bot.sh` to pre-create target shared directories with host user ownership before starting container | M3 | Survey Explorer 3 |
| F14 | End-to-End Acceptance Validation | Verify full integration: git tracking, dual remotes push, container write & host Django read/delete | M4 | ORIGINAL_REQUEST Acceptance Criteria |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Monorepo Consolidation | Backup nested .git, remove .git, add .agents/ to .gitignore, stage and commit bot files into main repo, deprecate sibling folder | none | IN_PROGRESS |
| M2 | Dual Git Remote Tracking | Register SSH key in Gitea, sync initial history, configure origin dual push URLs, verify SSH and push | M1 | PLANNED |
| M3 | Service Integration & Spreadsheet Interchange | Set up shared media directories, configure docker-compose volume & user mapping, update bot.sh, create backward-compatibility symlink | M1 | PLANNED |
| M4 | E2E Acceptance Verification & Hardening | Execute all acceptance criteria tests across monorepo tracking, dual git remotes, and cross-boundary container-host permissions | M2, M3 | PLANNED |

## Interface Contracts
### Dockerized Bot ↔ Host Django Filesystem
- **Path Mapping**:
  - Container internal path: `/app/incoming_spreadsheets/`
  - Host canonical path: `/home/javad/projects/dorm/dormitory-management/media/spreadsheets/incoming/`
  - Host convenience path: `/home/javad/projects/dorm/dormitory-management/incoming_spreadsheets/` (symlink)
- **File Format & Naming**:
  - Uploaded spreadsheet: `<filename>.xlsx`
  - Companion instructions: `<filename_stem>_instructions.md` (UTF-8 markdown)
- **POSIX Ownership & Permissions**:
  - Owner: UID 1000 (`javad`), GID 1000 (`javad`)
  - File permissions: `-rw-r--r--` (0644)
  - Directory permissions: `drwxr-xr-x` (0755)
  - Both container bot and host Django commands (`record_receipt`, `reconcile_bank_statement`) have read, write, and unlink capabilities without elevated privileges.

### Git Remotes Interface
- **Primary Origin Fetch URL**: `git@github.com:javad-hosseini/dorm-management.git`
- **Primary Origin Push URL 1 (GitHub)**: `git@github.com:javad-hosseini/dorm-management.git`
- **Primary Origin Push URL 2 (Gitea)**: `ssh://git@94.183.146.0:22022/Javad/dormitory-management.git`
- **Secondary Dedicated Gitea Remote**: `gitea` -> `ssh://git@94.183.146.0:22022/Javad/dormitory-management.git`
- **Command Semantics**: `git push origin <branch>` pushes the branch head to both remotes in sequence.

## Code Layout
```
/home/javad/projects/dorm/dormitory-management/
├── .git/
├── .gitignore
├── PROJECT.md
├── manage.py
├── config/
│   ├── settings.py
│   └── urls.py
├── apps/
│   └── dormitory/
│       ├── models/
│       ├── views/
│       └── management/commands/
│           ├── record_receipt.py
│           └── reconcile_bank_statement.py
├── media/
│   ├── id_cards/
│   └── spreadsheets/
│       ├── incoming/        <-- Shared container mount target
│       ├── processed/       <-- Processed files archive
│       └── failed/          <-- Malformed files quarantine
├── incoming_spreadsheets/   <-- Symlink to media/spreadsheets/incoming/
└── dormitory-telegram-bot/  <-- Consolidated Telegram bot codebase
    ├── Dockerfile
    ├── docker-compose.yml   <-- Updated volume and user configuration
    ├── bot.sh               <-- Updated directory pre-creation
    ├── pyproject.toml
    ├── uv.lock
    ├── src/
    │   ├── main.py
    │   ├── config.py
    │   ├── bot/
    │   ├── database/
    │   ├── middlewares/
    │   └── services/
    └── tests/
```
