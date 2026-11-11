# Test Infrastructure Specification: E2E Testing Track

## 1. Overview & Architecture Principles

The End-to-End (E2E) Test Suite for `dormitory-management` validates monorepo consolidation, dual git remotes, and cross-boundary container-to-host spreadsheet interchange.

### Architectural Principles:
1. **Opaque-Box Testing**: Tests interact strictly through public interfaces: filesystem hierarchy, POSIX file permissions, Git porcelain/configuration commands, Docker Compose declarations, and Django CLI management commands. Tests make no assumptions about private internal implementations.
2. **Zero External Runtime Dependencies**: The test runner, test cases, and fixture generators rely exclusively on Python standard library modules (`unittest`, `subprocess`, `pathlib`, `stat`, `json`, `zipfile`, `tempfile`). No virtualenv activation or third-party packages (`pip`) are required to execute or validate the test suite.
3. **Dual Runner Compatibility**: Tests can be executed using the standalone CLI test runner (`python3 tests/e2e/runner.py`), the universal shell entrypoint (`./tests/e2e/run_all.sh`), or standard `pytest` (`pytest tests/e2e/`).
4. **Non-Destructive Safety Invariants**:
   - **Zero Remote Git Mutation**: Remote push verifications execute exclusively via `git push --dry-run` to protect upstream repository history.
   - **Zero Database Mutation**: Management command tests use dry-run flags or isolated temporary SQLite copies to ensure the production database (`db.sqlite3`) remains untouched.
   - **Dropzone Isolation via Canary Files**: Dropzone filesystem probes write temporary canary files matching `.canary_test_<uuid>.tmp` and register automated lifecycle cleanup via `addCleanup()`.
   - **Sandbox Isolation for Mutation Tests**: Destructive and negative test scenarios (corrupted git repositories, permission denial, missing directories) execute exclusively inside temporary directories via `SandboxTestCase`.
5. **Progressive Testability**: Organized in 4 progressive tiers ranging from atomic feature validation up to complete multi-service workflow simulations.

---

## 2. Feature Inventory Mapping (F1 to F14)

| # | Feature | Milestone | Description | Interface Contract | Primary Test Assertion |
|---|---------|-----------|-------------|--------------------|------------------------|
| **F1** | Nested Git Elimination | M1 | Delete nested `.git` directory inside `dormitory-telegram-bot/` to dissolve nested repo | Filesystem, Git index | `test ! -e dormitory-telegram-bot/.git` & no mode 160000 |
| **F2** | Monorepo Bot Tracking | M1 | Stage and track 47 bot codebase files directly in root Git repository | Git index (`ls-files`) | Exactly 47 bot files tracked in root repo |
| **F3** | Git Ignore Alignment | M1 | Add `.agents/` to root `.gitignore` and preserve hierarchical ignore rules | `.gitignore`, `check-ignore` | Clean `git status`, `.agents/` ignored |
| **F4** | Sibling Directory Cleanup | M1 | Deprecate and remove empty sibling `/home/javad/projects/dorm/dormitory-telegram-bot` | Filesystem | Path removed or verified completely inactive |
| **F5** | Gitea SSH Key Authorization | M2 | Register public key in Gitea user Javad via admin API token | SSH port 22022 | Non-interactive SSH handshake succeeds |
| **F6** | Gitea History Synchronization | M2 | Align divergent initial commit in Gitea repo with root repository history | Git refspecs | Local `HEAD` matches Gitea `refs/heads/main` |
| **F7** | Dual Push Remote Configuration | M2 | Configure `origin` with push URLs for GitHub SSH and Gitea SSH | `.git/config` | Two push URLs listed under `origin` |
| **F8** | Git Dual Push Verification | M2 | Verify SSH handshakes and dual push synchronization | `git push --dry-run` | Dry-run push targets both remotes without errors |
| **F9** | Shared Directory Hierarchy | M3 | Establish `media/spreadsheets/{incoming,processed,failed}/` | Filesystem (POSIX) | Mode 0755 dirs owned by UID 1000, GID 1000 |
| **F10** | Monorepo Relative Volume Mount | M3 | Update `docker-compose.yml` to mount `../media/spreadsheets/incoming` with `:z` | Compose YAML | Valid relative volume binding to shared dropzone |
| **F11** | Container User & Permissions | M3 | Configure `user: "${BOT_UID:-1000}:${BOT_GID:-1000}"` in compose | Docker runtime | Container-created files owned by UID/GID 1000 |
| **F12** | Root Dropzone Symlink | M3 | Create root symlink `incoming_spreadsheets -> media/spreadsheets/incoming` | Symlink | Valid symlink pointing to canonical dropzone |
| **F13** | Bot Startup Script Update | M3 | Update `bot.sh` to pre-create target shared directories before container startup | Shell script | Pre-creates target directories with host ownership |
| **F14** | End-to-End Acceptance Validation | M4 | Validate full workflow: git tracking, dual remotes push, container write & host Django read/delete | Integrated System | All acceptance criteria in ORIGINAL_REQUEST satisfied |

---

## 3. Test Architecture & Directory Layout

```
tests/e2e/
├── __init__.py                               # Package initialization
├── base.py                                   # E2EBaseTestCase & SandboxTestCase base classes
├── fixtures.py                               # Zero-dependency spreadsheet and companion generators
├── runner.py                                 # Standalone CLI test runner with JSON reporting
├── run_all.sh                                # Universal executable shell entrypoint
├── test_tier1_feature_coverage.py            # Tier 1: Feature Coverage (F1 to F14, >=5 checks each)
├── test_tier2_boundaries_corners.py          # Tier 2: Boundaries, Missing Paths, Error Cases (>=70 checks)
├── test_tier3_cross_feature.py               # Tier 3: Pairwise Cross-Feature Interactions (16 tests T3_01 to T3_16)
└── test_tier4_real_world.py                  # Tier 4: Real-World Workload Scenarios (7 scenarios T4_01 to T4_07)
```

---

## 4. Test Tier Breakdown

| Tier | Name | Target Scope | Assertion / Scenario Count |
|------|------|--------------|----------------------------|
| **Tier 1** | Feature Coverage | Verifies individual features F1 through F14 independently | >= 5 assertions per feature (>= 70 total assertions) |
| **Tier 2** | Boundaries & Corners | Negative inputs, missing paths, permission denials, symlink edges | >= 5 assertions per feature (>= 70 total assertions) |
| **Tier 3** | Cross-Feature Interactions | Pairwise and tripartite feature interaction matrices | Exactly 16 comprehensive cross-feature tests (T3_01 to T3_16) |
| **Tier 4** | Real-World Workloads | Complete bot-dropzone-to-Django management command workflows | Exactly 7 comprehensive end-to-end scenarios (T4_01 to T4_07) |

---

## 5. Scenario Index

### Tier 1: Feature Coverage (`test_tier1_feature_coverage.py`)
- `test_f01_nested_git_elimination`: F1 elimination of nested `.git`, worktrees, and submodule gitlinks.
- `test_f02_monorepo_bot_tracking`: F2 tracking of all 47 Telegram bot files under root git index.
- `test_f03_git_ignore_alignment`: F3 root `.gitignore` ignores `.agents/` and preserves nested ignore rules.
- `test_f04_sibling_directory_cleanup`: F4 removal or complete deprecation of sibling directory stub.
- `test_f05_gitea_ssh_key_authorization`: F5 SSH key registration and authentication to Gitea server.
- `test_f06_gitea_history_synchronization`: F6 commit alignment between local repository and Gitea repository.
- `test_f07_dual_push_remote_configuration`: F7 configuration of dual push URLs on remote `origin`.
- `test_f08_git_dual_push_verification`: F8 non-destructive verification of dual push to GitHub and Gitea.
- `test_f09_shared_directory_hierarchy`: F9 structure, permissions (0755), and ownership (1000:1000) of `media/spreadsheets/`.
- `test_f10_monorepo_relative_volume_mount`: F10 Docker Compose relative volume mount and `:z` SELinux flag.
- `test_f11_container_user_and_permissions`: F11 container user mapping (`1000:1000`) and non-root file creation.
- `test_f12_root_dropzone_symlink`: F12 root symlink `incoming_spreadsheets` resolution to `media/spreadsheets/incoming`.
- `test_f13_bot_startup_script_update`: F13 `bot.sh` syntax, pre-creation commands, and safety flags.
- `test_f14_end_to_end_acceptance_validation`: F14 full verification of all acceptance criteria in `ORIGINAL_REQUEST.md`.

### Tier 2: Boundaries & Corners (`test_tier2_boundaries_corners.py`)
- `test_f01_boundary_gitlink_and_backup`: Mode 160000 detection and backup tarball integrity.
- `test_f02_boundary_untracked_sensitive_files`: Exclusion of `.env`, `data/`, and `.pytest_cache/` from tracking.
- `test_f03_boundary_gitignore_syntax_and_preexisting`: Trailing newlines and preservation of existing ignore patterns.
- `test_f04_boundary_sibling_symlink_and_worktree`: Guarantee sibling is not a symlink or active git worktree.
- `test_f05_boundary_ssh_timeout_and_idempotency`: Handling SSH timeouts and duplicate key registrations.
- `test_f06_boundary_non_fast_forward_rejection_and_branch_protection`: Detection of non-fast-forward push rejections.
- `test_f07_boundary_git_remote_duplicate_and_config_format`: Rejection of duplicate remotes and syntax validation.
- `test_f08_boundary_non_interactive_push_and_tag_safety`: Non-interactive `GIT_TERMINAL_PROMPT=0` dry-runs and tag pushes.
- `test_f09_boundary_permission_denial_and_atomic_move`: Dropzone write permissions and cross-directory file moves.
- `test_f10_boundary_missing_compose_and_invalid_volume`: Detection of invalid compose mounts and missing files.
- `test_f11_boundary_unprivileged_deletion_and_env_override`: Host unprivileged file deletion and `BOT_UID` overrides.
- `test_f12_boundary_dangling_symlink_and_idempotent_creation`: Dangling symlink handling and idempotent `ln -sfn`.
- `test_f13_boundary_bot_sh_invalid_command_and_relative_execution`: Handling invalid commands and invocation from `/tmp`.
- `test_f14_boundary_persian_unicode_and_quarantine_lifecycle`: Persian UTF-8 filenames and zero-byte file quarantine.

### Tier 3: Cross-Feature Interactions (`test_tier3_cross_feature.py`)
- `T3_01`: F1 + F2 — Nested Git Elimination & Root Monorepo Tracking
- `T3_02`: F2 + F3 — Monorepo Bot Tracking & Gitignore Layering
- `T3_03`: F2 + F4 — Monorepo Bot Tracking & Sibling Stub Deprecation
- `T3_04`: F5 + F6 — Gitea SSH Key Auth & Divergent History Synchronization
- `T3_05`: F6 + F7 — Gitea History Alignment & Dual Push Remote Configuration
- `T3_06`: F7 + F8 — Dual Push Configuration & Synchronous Push Verification
- `T3_07`: F2 + F7 + F8 — Unified Monorepo Bot Code & Dual Remote Push Verification
- `T3_08`: F9 + F10 — Shared Directory Hierarchy & Monorepo Relative Compose Volume Mount
- `T3_09`: F10 + F11 — Relative Volume Mount & Container User 1000:1000 File Creation
- `T3_10`: F9 + F12 — Media Directory Hierarchy & Root Convenience Symlink Dropzone
- `T3_11`: F10 + F13 — Relative Volume Mount & bot.sh Host Directory Pre-Creation Guard
- `T3_12`: F9 + F10 + F11 — Shared Media Hierarchy, Volume Mount, and Non-Root SELinux/Permissions
- `T3_13`: F11 + F14 — Container Non-Root Output & Host Non-Dockerized Django Read/Unlink
- `T3_14`: F3 + F9 — Git Ignore Alignment & Media Storage Persistence Immunity
- `T3_15`: F9 + F12 + F14 — Root Symlink Ingestion & Host Management Command Access
- `T3_16`: F10 + F12 + F13 — bot.sh Pre-Creation, Symlink Target Integrity, and Container Mount

### Tier 4: Real-World Workload Scenarios (`test_tier4_real_world.py`)
- `T4_01`: Full Cycle Receipt Recording Workflow (Dropzone Ingestion -> Symlink -> Django `record_receipt` -> Archive)
- `T4_02`: Bank Statement Reconciliation & Discrepancy Discovery (Iranian Bank Statement Ingestion -> Matching -> Quarantine)
- `T4_03`: Malformed & Corrupted Spreadsheet Quarantine Pipeline (Truncated ZIP / Bad Header -> Quarantine to `failed/`)
- `T4_04`: Non-Root Container Write & Host Django Read/Unlink Lifecycle (Cross-boundary UID 1000 interchange)
- `T4_05`: Monorepo Unified Commit & Dual Push Lifecycle (Cross-service commit -> `git push origin` -> Dual remote sync)
- `T4_06`: Dropzone Symlink Resilience & Self-Healing Workflow (Broken symlink recovery & pipeline healing)
- `T4_07`: High-Throughput Multi-Spreadsheet Batch Ingestion & Deduplication (Sequential batch drops -> SHA-256 deduplication)

---

## 6. Coverage Thresholds

| Metric | Target Threshold | Suite Capacity |
|--------|------------------|----------------|
| Tier 1 Assertions | >= 70 assertions (5 per feature) | 70+ assertions |
| Tier 2 Assertions | >= 70 assertions (5 per feature) | 70+ assertions |
| Tier 3 Scenarios | Exactly 16 cross-feature tests | 16 tests |
| Tier 4 Scenarios | Exactly 7 end-to-end workflows | 7 tests |
| Total Distinct Checks | >= 163 checks | 165+ checks |
| Zero External Dependencies | 100% standard library | Python 3.9 / 3.12 compatible |

---

## 7. Test Runner & CLI Usage

### Running via Shell Entrypoint
```bash
# Execute entire test suite
./tests/e2e/run_all.sh

# Run specific tier
./tests/e2e/run_all.sh --tier 1
./tests/e2e/run_all.sh --tier 2
./tests/e2e/run_all.sh --tier 3
./tests/e2e/run_all.sh --tier 4

# Run specific feature tests across tiers
./tests/e2e/run_all.sh --feature F1
./tests/e2e/run_all.sh --feature F14

# Validate suite structure, imports, and discovery without test execution
./tests/e2e/run_all.sh --validate-suite

# Verbose output with custom JSON output path
./tests/e2e/run_all.sh -v --json-output /tmp/custom_results.json
```

### Running via Python Directly
```bash
python3 tests/e2e/runner.py --tier 1 -v
python3.12 tests/e2e/runner.py --validate-suite
```

### Running via Pytest
```bash
pytest tests/e2e/ -v
```

---

## 8. Exit Code Semantics

- **`0`**: All executed tests passed (or were cleanly skipped due to environment capabilities).
- **`1`**: One or more tests failed or threw unexpected runtime exceptions.
- **`2`**: Invalid CLI arguments or fatal initialization failure.
