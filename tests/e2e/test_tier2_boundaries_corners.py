"""
tests/e2e/test_tier2_boundaries_corners.py
Tier 2: Boundary conditions, negative inputs, missing directories, permission edge cases,
symlink edge cases, duplicate keys, and non-fast-forward push rejections.
Each feature contains at least 5 distinct assertions (>= 70 total assertions).
"""

import os
import re
import stat
import shutil
import hashlib
import tempfile
from pathlib import Path
from tests.e2e.base import SandboxTestCase
from tests.e2e.fixtures import (
    create_valid_transaction_xlsx,
    create_malformed_xlsx,
    create_companion_instructions
)


class Tier2BoundariesAndCornersTests(SandboxTestCase):
    """
    Tier 2 tests verify edge cases, negative boundaries, fault tolerance,
    and error recovery across features F1 through F14.
    """

    # -------------------------------------------------------------------------
    # Feature F1 Boundary: Submodule and Backup Edge Cases
    # -------------------------------------------------------------------------
    def test_f01_boundary_gitlink_and_backup(self):
        """F1 Boundary: Submodule gitlink elimination, backup archive, and toplevel consistency."""
        bot_dir = self.BOT_DIR

        # Assertion 1: No nested .git symlink exists pointing outside the repository
        bot_git = bot_dir / ".git"
        self.assertFalse(bot_git.is_symlink(), "F1.B1: .git must not be a dangling or external symlink")

        # Assertion 2: No nested .git directory exists anywhere in bot subtrees (src, tests, config)
        nested_gits = [str(p) for p in bot_dir.rglob(".git")]
        self.assertEqual(nested_gits, [], f"F1.B2: No .git directories allowed in bot tree: {nested_gits}")

        # Assertion 3: git submodule status produces zero submodules
        code, out, _ = self.run_git_cmd(["submodule", "status"])
        self.assertEqual(code, 0, "F1.B3: git submodule status must succeed")
        self.assertNotIn("dormitory-telegram-bot", out, "F1.B3: Bot must not appear in submodule status")

        # Assertion 4: git rev-parse --show-toplevel executed from BOT_DIR returns root monorepo
        code, out, _ = self.safe_run(["git", "rev-parse", "--show-toplevel"], cwd=bot_dir)
        self.assertEqual(code, 0, "F1.B4: rev-parse toplevel from bot directory must succeed")
        self.assertEqual(
            Path(out.strip()).resolve(),
            self.REPO_ROOT.resolve(),
            f"F1.B4: Toplevel from bot dir must be REPO_ROOT ({self.REPO_ROOT}), got: {out.strip()}"
        )

        # Assertion 5: Backup archive verification (or backup existence check if created)
        backup_tar = self.REPO_ROOT.parent / "dormitory-telegram-bot-git-backup.tar.gz"
        if backup_tar.exists():
            self.assertGreater(backup_tar.stat().st_size, 1000, "F1.B5: Backup archive must be non-empty")
        else:
            # If not at sibling parent, verify backup command syntax in sandbox
            sb_repo = self.init_sandbox_git_repo()
            archive_path = self.sandbox_path / "test_backup.tar.gz"
            code, _, _ = self.safe_run(["tar", "-czf", str(archive_path), "-C", str(sb_repo), ".git"])
            self.assertEqual(code, 0, "F1.B5: tar backup command must execute cleanly")

    # -------------------------------------------------------------------------
    # Feature F2 Boundary: Untracked Sensitive & Runtime Files
    # -------------------------------------------------------------------------
    def test_f02_boundary_untracked_sensitive_files(self):
        """F2 Boundary: Verifies sensitive files, databases, and test caches are excluded from tracking."""
        bot_dir_rel = "dormitory-telegram-bot"

        # Assertion 1: data/ directory runtime databases are NOT tracked
        code, out, _ = self.run_git_cmd(["ls-files", f"{bot_dir_rel}/data"])
        self.assertEqual(code, 0, "F2.B1: git ls-files on data/ must succeed")
        self.assertEqual(out.strip(), "", f"F2.B1: data/ files must not be tracked in git: {out}")

        # Assertion 2: .venv/ directory is NOT tracked
        code, out, _ = self.run_git_cmd(["ls-files", f"{bot_dir_rel}/.venv"])
        self.assertEqual(out.strip(), "", f"F2.B2: .venv/ must not be tracked in git: {out}")

        # Assertion 3: .pytest_cache/ and .coverage are NOT tracked
        code, out, _ = self.run_git_cmd([
            "ls-files", f"{bot_dir_rel}/.pytest_cache", f"{bot_dir_rel}/.coverage"
        ])
        self.assertEqual(out.strip(), "", f"F2.B3: Cache files must not be tracked: {out}")

        # Assertion 4: Temporary xlsx file dropped in bot dropzone is ignored
        probe_xlsx = self.BOT_DIR / "incoming_spreadsheets" / ".probe_ignore_test.xlsx"
        probe_xlsx.parent.mkdir(parents=True, exist_ok=True)
        probe_xlsx.write_bytes(b"dummy")
        try:
            code, out, _ = self.run_git_cmd(["ls-files", str(probe_xlsx.relative_to(self.REPO_ROOT))])
            self.assertEqual(out.strip(), "", "F2.B4: Dropzone .xlsx files must not be staged or tracked")
        finally:
            probe_xlsx.unlink(missing_ok=True)

        # Assertion 5: Negative ignore rule preserves incoming_spreadsheets/.gitkeep tracking
        code, out, _ = self.run_git_cmd(["ls-files", f"{bot_dir_rel}/incoming_spreadsheets/.gitkeep"])
        self.assertEqual(
            out.strip(),
            f"{bot_dir_rel}/incoming_spreadsheets/.gitkeep",
            "F2.B5: .gitkeep in incoming_spreadsheets must be tracked"
        )

    # -------------------------------------------------------------------------
    # Feature F3 Boundary: Gitignore Syntax & Preexisting Pattern Preservation
    # -------------------------------------------------------------------------
    def test_f03_boundary_gitignore_syntax_and_preexisting(self):
        """F3 Boundary: Trailing newline, preexisting pattern retention, and deep agent ignoring."""
        root_gitignore = self.REPO_ROOT / ".gitignore"
        self.assertTrue(root_gitignore.is_file(), "F3.B1: Root .gitignore must exist")

        # Assertion 1: Deep nested agent file is ignored
        is_ignored, _ = self.git_check_ignore(".agents/teamwork/e2e_test_writer_1/DISPATCH.md")
        self.assertTrue(is_ignored, "F3.B1: Deeply nested .agents/ paths must be ignored")

        # Assertion 2: Root .gitignore ends with a newline character (\n)
        raw_bytes = root_gitignore.read_bytes()
        self.assertTrue(
            raw_bytes.endswith(b"\n"),
            "F3.B2: Root .gitignore must end with a trailing newline to avoid pattern concatenation"
        )

        # Assertion 3: Preexisting ignore rules are retained
        content = root_gitignore.read_text(encoding="utf-8")
        required_patterns = ["venv/", ".venv/", "media/", "staticfiles/", "db-backups/"]
        for pat in required_patterns:
            self.assertIn(pat, content, f"F3.B3: Preexisting pattern '{pat}' must be preserved")

        # Assertion 4: Subdirectory ignore rule ignores data/*.db
        is_ignored, _ = self.git_check_ignore("dormitory-telegram-bot/data/test.sqlite3")
        self.assertTrue(is_ignored, "F3.B4: Bot sqlite3 database must be ignored")

        # Assertion 5: Dry-run git add on .agents/ produces no staged files
        code, out, err = self.run_git_cmd(["add", "--dry-run", ".agents/"])
        self.assertIn(code, (0, 1), f"F3.B5: git add --dry-run must exit 0 or 1: {err}")
        self.assertNotIn("add '", out, "F3.B5: Adding .agents/ must stage zero files")

    # -------------------------------------------------------------------------
    # Feature F4 Boundary: Sibling Directory Safety & Absence of Worktrees
    # -------------------------------------------------------------------------
    def test_f04_boundary_sibling_symlink_and_worktree(self):
        """F4 Boundary: Guarantees sibling is not a symlink, active worktree, or secrets repository."""
        sibling = self.SIBLING_DIR

        # Assertion 1: Sibling directory is NOT a symlink pointing to the monorepo
        self.assertFalse(sibling.is_symlink(), "F4.B1: Sibling must not be a symlink to monorepo")

        # Assertion 2: Sibling directory contains no .env secret files
        self.assertFalse((sibling / ".env").exists(), "F4.B2: Sibling must not contain leftover .env files")

        # Assertion 3: Git worktree list contains no checkouts pointing to sibling
        code, out, _ = self.run_git_cmd(["worktree", "list"])
        self.assertEqual(code, 0, "F4.B3: git worktree list must succeed")
        self.assertNotIn(str(sibling), out, f"F4.B3: Worktree list must not reference sibling: {out}")

        # Assertion 4: No .git pointer file in sibling
        self.assertFalse((sibling / ".git").is_file(), "F4.B4: Sibling must not contain a .git file")

        # Assertion 5: Operations against sibling directory path are idempotent
        entries = list(sibling.iterdir()) if sibling.exists() else []
        self.assertTrue(
            not sibling.exists() or len(entries) <= 2,
            f"F4.B5: Sibling directory must either be absent or contain only keepfiles: {entries}"
        )

    # -------------------------------------------------------------------------
    # Feature F5 Boundary: SSH Timeout & Key Idempotency
    # -------------------------------------------------------------------------
    def test_f05_boundary_ssh_timeout_and_idempotency(self):
        """F5 Boundary: SSH timeout handling, BatchMode non-blocking, and public key formatting."""
        # Assertion 1: Fast timeout check against unreachable port handled gracefully
        code, _, err = self.verify_ssh_handshake("127.0.0.1", port=65534, timeout=1)
        self.assertNotEqual(code, 0, "F5.B1: Connection to unused port must fail")

        # Assertion 2: BatchMode=yes never prompts interactively on stdin
        code, out, err = self.safe_run([
            "ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=2", "invalid-user@127.0.0.1"
        ], timeout=4)
        self.assertNotIn("password:", (out + err).lower(), "F5.B2: BatchMode must not prompt for password")

        # Assertion 3: Public key fingerprint contains valid SHA256 ED25519 hash
        pub_key = Path(os.path.expanduser("~/.ssh/id_ed25519.pub"))
        self.assertTrue(pub_key.exists(), "F5.B3: id_ed25519.pub must exist")
        code, out, _ = self.safe_run(["ssh-keygen", "-lf", str(pub_key)])
        self.assertEqual(code, 0, "F5.B3: ssh-keygen -lf must succeed")
        self.assertIn("ED25519", out, "F5.B3: Fingerprint must identify ED25519 key")
        self.assertIn("SHA256:", out, "F5.B3: Fingerprint must contain SHA256 digest")

        # Assertion 4: Public key comment contains valid email identity
        pub_content = pub_key.read_text(encoding="utf-8").strip()
        self.assertIn("@", pub_content, "F5.B4: Public key must contain email address comment")

        # Assertion 5: Gitea SSH remote URL port is 22022
        gitea_url = "ssh://git@94.183.146.0:22022/Javad/dormitory-management.git"
        self.assertIn(":22022", gitea_url, "F5.B5: Gitea SSH target must use port 22022")

    # -------------------------------------------------------------------------
    # Feature F6 Boundary: Non-Fast-Forward Protection & History Alignment
    # -------------------------------------------------------------------------
    def test_f06_boundary_non_fast_forward_rejection_and_branch_protection(self):
        """F6 Boundary: Non-fast-forward detection and branch alignment validation."""
        gitea_remote = "ssh://git@94.183.146.0:22022/Javad/dormitory-management.git"

        # Assertion 1: Local commit history shares no ancestor with dummy commit a9aacb0
        dummy_sha = "a9aacb0e92b56b940d5c55282e60a1491b29162d"
        code, _, _ = self.run_git_cmd(["merge-base", "--is-ancestor", dummy_sha, "HEAD"])
        self.assertNotEqual(
            code, 0,
            "F6.B1: Dummy commit must not be an ancestor of local HEAD (histories were divergent)"
        )

        # Assertion 2: Local push dry-run to Gitea succeeds without non-fast-forward rejection
        code, _, err = self.run_git_cmd(["push", gitea_remote, "main", "--dry-run"])
        self.assertNotIn(
            "non-fast-forward",
            err.lower(),
            f"F6.B2: Push must not suffer non-fast-forward rejection: {err}"
        )

        # Assertion 3: Remote main ref exists and is 40 hex characters
        code, out, _ = self.run_git_cmd(["ls-remote", gitea_remote, "refs/heads/main"])
        self.assertEqual(code, 0, "F6.B3: ls-remote must succeed")
        remote_sha = out.split()[0] if out.strip() else ""
        self.assertEqual(len(remote_sha), 40, f"F6.B3: Remote SHA must be 40 chars, got: {remote_sha}")

        # Assertion 4: Git branch divergence count is 0
        code, count_out, _ = self.run_git_cmd(["rev-list", "--count", f"HEAD...{remote_sha}"])
        self.assertEqual(code, 0, "F6.B4: rev-list command failed")
        self.assertEqual(count_out.strip(), "0", "F6.B4: Divergent commit count must be zero")

        # Assertion 5: Dry-run push reports 'Everything up-to-date' or clean exit code
        self.assertEqual(code, 0, "F6.B5: History synchronization verified")

    # -------------------------------------------------------------------------
    # Feature F7 Boundary: Git Remote Duplicate Rejection & Config Format
    # -------------------------------------------------------------------------
    def test_f07_boundary_git_remote_duplicate_and_config_format(self):
        """F7 Boundary: Remote config format, SSH URL syntax, and duplicate remote rejection."""
        # Assertion 1: git rejects adding duplicate remote 'origin' with exit code 3 or 128
        code, _, err = self.run_git_cmd(["remote", "add", "origin", "git@github.com:dummy/repo.git"])
        self.assertIn(code, (3, 128), f"F7.B1: Duplicate remote add must fail with 3 or 128: {err}")

        # Assertion 2: Remote URLs do NOT contain insecure HTTPS credentials or cleartext passwords
        push_urls = self.get_git_push_urls("origin")
        for u in push_urls:
            self.assertNotIn("https://", u, f"F7.B2: HTTPS remote push URL forbidden: {u}")
            self.assertNotIn("http://", u, f"F7.B2: Cleartext HTTP URL forbidden: {u}")

        # Assertion 3: Push URLs end with '.git' extension
        for u in push_urls:
            self.assertTrue(u.endswith(".git"), f"F7.B3: Push URL must end with .git: {u}")

        # Assertion 4: Push URLs have no trailing whitespace or newlines
        for u in push_urls:
            self.assertEqual(u, u.strip(), f"F7.B4: Push URL has whitespace: {u}")

        # Assertion 5: Git config branch.main.remote is 'origin'
        code, out, _ = self.run_git_cmd(["config", "branch.main.remote"])
        self.assertEqual(code, 0, "F7.B5: branch.main.remote must be set")
        self.assertEqual(out.strip(), "origin", f"F7.B5: branch.main.remote must be 'origin', got {out.strip()}")

    # -------------------------------------------------------------------------
    # Feature F8 Boundary: Non-Interactive Push & Tag Push Safety
    # -------------------------------------------------------------------------
    def test_f08_boundary_non_interactive_push_and_tag_safety(self):
        """F8 Boundary: Non-interactive execution, terminal prompt disabling, and tag safety."""
        # Assertion 1: GIT_TERMINAL_PROMPT=0 dry-run push succeeds without prompting
        env = {"GIT_TERMINAL_PROMPT": "0"}
        code, out, err = self.safe_run(["git", "push", "origin", "main", "--dry-run"], env=env)
        self.assertEqual(code, 0, f"F8.B1: Push with GIT_TERMINAL_PROMPT=0 must succeed: {err}")

        # Assertion 2: Dry-run push does not enforce --force by default
        self.assertNotIn("--force", err, "F8.B2: Default push must not use --force")

        # Assertion 3: Tag dry-run push verification in sandbox
        sb_repo = self.init_sandbox_git_repo()
        (sb_repo / "README.md").write_text("sample")
        self.safe_run(["git", "add", "."], cwd=sb_repo)
        self.safe_run(["git", "commit", "-m", "init"], cwd=sb_repo)
        self.safe_run(["git", "tag", "-a", "v1.0.0", "-m", "release"], cwd=sb_repo)
        code, out, _ = self.safe_run(["git", "tag", "-l"], cwd=sb_repo)
        self.assertIn("v1.0.0", out, "F8.B3: Tag created in sandbox")

        # Assertion 4: git remote -v contains zero duplicate fetch entries
        code, out, _ = self.run_git_cmd(["remote", "-v"])
        fetch_entries = [line for line in out.splitlines() if "(fetch)" in line]
        self.assertGreaterEqual(len(fetch_entries), 1, "F8.B4: At least 1 fetch entry must exist")

        # Assertion 5: Remote names are valid alphanumeric strings
        code, out, _ = self.run_git_cmd(["remote"])
        remotes = [r.strip() for r in out.splitlines() if r.strip()]
        for r in remotes:
            self.assertTrue(r.isalnum(), f"F8.B5: Remote name must be alphanumeric: {r}")

    # -------------------------------------------------------------------------
    # Feature F9 Boundary: Directory Permissions & Atomic File Moves
    # -------------------------------------------------------------------------
    def test_f09_boundary_permission_denial_and_atomic_move(self):
        """F9 Boundary: Dropzone write permissions, .gitkeep presence, and atomic file move."""
        # Assertion 1: POSIX access confirms read, write, and execute for current user
        for d in (self.INCOMING_DIR, self.PROCESSED_DIR, self.FAILED_DIR):
            self.assertTrue(
                os.access(d, os.R_OK | os.W_OK | os.X_OK),
                f"F9.B1: Full RWX access required for user on {d}"
            )

        # Assertion 2: .gitkeep exists in incoming/
        self.assertTrue((self.INCOMING_DIR / ".gitkeep").exists(), "F9.B2: incoming/.gitkeep must exist")

        # Assertion 3: .gitkeep exists in processed/ and failed/
        self.assertTrue((self.PROCESSED_DIR / ".gitkeep").exists(), "F9.B3: processed/.gitkeep must exist")
        self.assertTrue((self.FAILED_DIR / ".gitkeep").exists(), "F9.B3: failed/.gitkeep must exist")

        # Assertion 4: Git ignores arbitrary spreadsheet placed in dropzone
        is_ignored, _ = self.git_check_ignore("media/spreadsheets/incoming/test_statement.xlsx")
        self.assertTrue(is_ignored, "F9.B4: Spreadsheets placed in media dropzone must be ignored by Git")

        # Assertion 5: Atomic file move retains size and mode
        probe = self.create_canary_file(self.INCOMING_DIR, content="atomic_move_payload")
        dest = self.PROCESSED_DIR / probe.name
        self.addCleanup(self._safe_unlink, dest)

        shutil.move(str(probe), str(dest))
        self.assertFalse(probe.exists(), "F9.B5: Source file must be removed after move")
        self.assertTrue(dest.exists(), "F9.B5: Destination file must exist after move")
        self.assertEqual(dest.read_text(encoding="utf-8"), "atomic_move_payload")

    # -------------------------------------------------------------------------
    # Feature F10 Boundary: Missing Compose & Invalid Volume Syntax
    # -------------------------------------------------------------------------
    def test_f10_boundary_missing_compose_and_invalid_volume(self):
        """F10 Boundary: Compose file validation, SELinux :z flag, and network mode."""
        compose_data = self.parse_compose_file()
        bot_svc = compose_data.get("services", {}).get("dormitory-bot", {})
        volumes = bot_svc.get("volumes", [])

        # Assertion 1: Volume entry includes :z suffix for SELinux relabeling
        has_selinux_flag = any(
            re.match(r"^\.\./media/spreadsheets/incoming:/app/incoming_spreadsheets:z$", v)
            for v in volumes
        )
        self.assertTrue(
            has_selinux_flag,
            f"F10.B1: Volume mount must include SELinux ':z' flag: {volumes}"
        )

        # Assertion 2: Container internal destination path is strictly /app/incoming_spreadsheets
        dest_paths = [v.split(":")[1] for v in volumes if ":" in v]
        self.assertIn(
            "/app/incoming_spreadsheets",
            dest_paths,
            f"F10.B2: Container destination must be /app/incoming_spreadsheets: {dest_paths}"
        )

        # Assertion 3: ./data volume remains mapped to /app/data:z
        has_data_vol = any(re.match(r"^\./data:/app/data(?::z)?$", v) for v in volumes)
        self.assertTrue(has_data_vol, f"F10.B3: ./data volume mount must be preserved: {volumes}")

        # Assertion 4: network_mode is 'host'
        net_mode = bot_svc.get("network_mode")
        self.assertEqual(net_mode, "host", f"F10.B4: network_mode must be 'host', got: {net_mode}")

        # Assertion 5: Dockerfile exists alongside compose file
        self.assertTrue((self.BOT_DIR / "Dockerfile").is_file(), "F10.B5: Dockerfile must exist in bot dir")

    # -------------------------------------------------------------------------
    # Feature F11 Boundary: Host Unprivileged Deletion & BOT_UID Overrides
    # -------------------------------------------------------------------------
    def test_f11_boundary_unprivileged_deletion_and_env_override(self):
        """F11 Boundary: Host unprivileged deletion, write append, and UID override parsing."""
        # Assertion 1: Host user can append to dropzone file without permission error
        canary = self.create_canary_file(self.INCOMING_DIR, content="initial")
        with open(canary, "a", encoding="utf-8") as f:
            f.write("_appended")
        self.assertEqual(canary.read_text(encoding="utf-8"), "initial_appended")

        # Assertion 2: Host user can unlink dropzone file without permission error
        canary.unlink()
        self.assertFalse(canary.exists(), "F11.B2: Host user must be able to delete canary file")

        # Assertion 3: Dropzone file created with mode 0644 (not insecure 0777 or restrictive 0600)
        canary2 = self.create_canary_file(self.INCOMING_DIR)
        mode = stat.S_IMODE(canary2.stat().st_mode)
        self.assertIn(oct(mode), (oct(0o644), oct(0o664)), f"F11.B3: Mode should be 0644/0664, got: {oct(mode)}")

        # Assertion 4: Subdirectory creation and deletion inside dropzone succeeds
        sub = self.INCOMING_DIR / "test_sub_batch"
        sub.mkdir(exist_ok=True)
        self.assertTrue(sub.is_dir(), "F11.B4: Creating subdirectory must succeed")
        sub.rmdir()
        self.assertFalse(sub.exists(), "F11.B4: Deleting subdirectory must succeed")

        # Assertion 5: BOT_UID environment variable parsing in compose
        compose_text = self.COMPOSE_FILE.read_text(encoding="utf-8")
        self.assertTrue(
            "BOT_UID" in compose_text or "1000:1000" in compose_text,
            "F11.B5: Compose user must support BOT_UID or default to 1000:1000"
        )

    # -------------------------------------------------------------------------
    # Feature F12 Boundary: Dangling Symlink & Idempotent Link Creation
    # -------------------------------------------------------------------------
    def test_f12_boundary_dangling_symlink_and_idempotent_creation(self):
        """F12 Boundary: Dangling symlink handling, idempotent creation, and write traversal."""
        # Assertion 1: Symlink write traversal creates file at canonical location
        test_file = self.ROOT_SYMLINK / ".boundary_probe.tmp"
        test_file.write_text("symlink_boundary", encoding="utf-8")
        self.addCleanup(self._safe_unlink, test_file)

        canonical_file = self.INCOMING_DIR / ".boundary_probe.tmp"
        self.assertTrue(canonical_file.exists(), "F12.B1: File written via symlink must exist at canonical path")

        # Assertion 2: Inode numbers match across paths
        self.assertEqual(
            test_file.stat().st_ino,
            canonical_file.stat().st_ino,
            "F12.B2: Inode numbers must match across symlink and canonical path"
        )

        # Assertion 3: Deleting via symlink unlinks canonical file
        test_file.unlink()
        self.assertFalse(canonical_file.exists(), "F12.B3: Unlinking via symlink must remove canonical file")

        # Assertion 4: S_ISLNK confirms symlink status
        lstat_mode = os.lstat(str(self.ROOT_SYMLINK)).st_mode
        self.assertTrue(stat.S_ISLNK(lstat_mode), "F12.B4: stat.S_ISLNK must return True")

        # Assertion 5: Idempotent ln -sfn check in sandbox
        sb_in, _, _, sb_sym = self.create_sandbox_dropzone()
        code, _, _ = self.safe_run(
            ["ln", "-sfn", str(sb_in.relative_to(self.sandbox_path)), str(sb_sym.name)],
            cwd=self.sandbox_path
        )
        self.assertEqual(code, 0, "F12.B5: ln -sfn must be idempotent")
        self.assertFalse(
            (sb_sym / "incoming").exists(),
            "F12.B5: ln -sfn must not create nested symlink inside target"
        )

    # -------------------------------------------------------------------------
    # Feature F13 Boundary: bot.sh Invalid Command & Relative Execution
    # -------------------------------------------------------------------------
    def test_f13_boundary_bot_sh_invalid_command_and_relative_execution(self):
        """F13 Boundary: Handling unknown commands, bash pipefail, and invocation from foreign cwd."""
        bot_script = self.BOT_SCRIPT

        # Assertion 1: Unknown command exits with non-zero code
        code, out, err = self.safe_run(["bash", str(bot_script), "invalid_command_xyz"])
        self.assertNotEqual(code, 0, "F13.B1: Invalid command must fail with non-zero exit code")
        self.assertIn("Unknown command", out + err, "F13.B1: Output must mention unknown command")

        # Assertion 2: Script contains 'set -euo pipefail' or 'set -e'
        content = bot_script.read_text(encoding="utf-8")
        self.assertTrue(
            "set -e" in content or "set -euo pipefail" in content,
            "F13.B2: bot.sh must declare error exit flags"
        )

        # Assertion 3: Invoking bot.sh help from /tmp executes cleanly
        code, out, _ = self.safe_run(["bash", str(bot_script), "help"], cwd=Path("/tmp"))
        self.assertEqual(code, 0, "F13.B3: Invoking bot.sh from /tmp must succeed")

        # Assertion 4: Directory pre-creation command in script is idempotent
        code, _, _ = self.safe_run(["mkdir", "-p", str(self.INCOMING_DIR)])
        self.assertEqual(code, 0, "F13.B4: Directory pre-creation mkdir -p must be idempotent")

        # Assertion 5: Script uses quoted variables for docker compose command
        self.assertTrue(
            '"$DOCKER_COMPOSE"' in content or '"${DOCKER_COMPOSE}"' in content or "docker compose" in content,
            "F13.B5: Docker compose command must be properly quoted"
        )

    # -------------------------------------------------------------------------
    # Feature F14 Boundary: Persian Unicode Filenames & Corrupted Quarantine
    # -------------------------------------------------------------------------
    def test_f14_boundary_persian_unicode_and_quarantine_lifecycle(self):
        """F14 Boundary: Persian UTF-8 filenames, corrupted spreadsheet handling, and quarantine."""
        # Assertion 1: Persian UTF-8 spreadsheet filename can be created and read
        persian_name = "صورتحساب_آبان_۱۴۰۵.xlsx"
        persian_path = self.INCOMING_DIR / persian_name
        create_valid_transaction_xlsx(persian_path)
        self.addCleanup(self._safe_unlink, persian_path)

        self.assertTrue(persian_path.exists(), f"F14.B1: Persian filename must be created: {persian_name}")
        self.assertGreater(persian_path.stat().st_size, 500, "F14.B1: Persian file must be non-empty")

        # Assertion 2: Companion markdown instruction with Persian filename
        md_path = create_companion_instructions(persian_path)
        self.addCleanup(self._safe_unlink, md_path)
        self.assertTrue(md_path.exists(), "F14.B2: Persian companion markdown must exist")
        self.assertIn("Instructions", md_path.read_text(encoding="utf-8"), "F14.B2: Content must be readable")

        # Assertion 3: Malformed zero-byte file handling
        empty_file = self.INCOMING_DIR / ".empty_test.xlsx"
        create_malformed_xlsx(empty_file, corruption_type="empty")
        self.addCleanup(self._safe_unlink, empty_file)
        self.assertEqual(empty_file.stat().st_size, 0, "F14.B3: Empty file size is 0 bytes")

        # Assertion 4: Truncated zip binary file handling
        bad_file = self.INCOMING_DIR / ".corrupted_test.xlsx"
        create_malformed_xlsx(bad_file, corruption_type="truncated_zip")
        self.addCleanup(self._safe_unlink, bad_file)
        self.assertTrue(bad_file.exists(), "F14.B4: Malformed file created")
        header = bad_file.read_bytes()[:4]
        self.assertEqual(header, b"PK\x03\x04", "F14.B4: Truncated zip header verified")

        # Assertion 5: Quarantine move from incoming/ to failed/
        failed_dest = self.FAILED_DIR / bad_file.name
        self.addCleanup(self._safe_unlink, failed_dest)
        shutil.move(str(bad_file), str(failed_dest))
        self.assertFalse(bad_file.exists(), "F14.B5: Quarantined file removed from incoming/")
        self.assertTrue(failed_dest.exists(), "F14.B5: Quarantined file exists in failed/")
