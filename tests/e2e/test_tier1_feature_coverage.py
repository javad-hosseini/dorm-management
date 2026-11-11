"""
tests/e2e/test_tier1_feature_coverage.py
Tier 1: Comprehensive Feature Coverage for Features F1 through F14.
Each feature contains at least 5 distinct assertions (>= 70 total assertions).
"""

import os
import re
import stat
import subprocess
from pathlib import Path
from tests.e2e.base import E2EBaseTestCase


class Tier1FeatureCoverageTests(E2EBaseTestCase):
    """
    Tier 1 tests verify the primary requirements and acceptance criteria
    for each feature (F1 through F14) in isolation.
    """

    # -------------------------------------------------------------------------
    # Feature F1: Nested Git Elimination
    # -------------------------------------------------------------------------
    def test_f01_nested_git_elimination(self):
        """F1: Verifies nested .git inside dormitory-telegram-bot is removed and no submodule gitlink exists."""
        bot_git = self.BOT_DIR / ".git"

        # Assertion 1: .git directory does not exist
        self.assertFalse(
            bot_git.is_dir(),
            f"F1.1: Nested .git directory must not exist: {bot_git}"
        )

        # Assertion 2: .git is not a git worktree pointer file
        self.assertFalse(
            bot_git.is_file(),
            f"F1.2: Nested .git pointer file must not exist: {bot_git}"
        )

        # Assertion 3: .gitmodules does not exist or does not reference dormitory-telegram-bot
        gitmodules = self.REPO_ROOT / ".gitmodules"
        if gitmodules.exists():
            content = gitmodules.read_text(encoding="utf-8")
            self.assertNotIn(
                "dormitory-telegram-bot",
                content,
                "F1.3: .gitmodules must not register dormitory-telegram-bot as a submodule"
            )
        else:
            self.assertFalse(gitmodules.exists(), "F1.3: .gitmodules does not exist")

        # Assertion 4: Git stage index contains zero mode 160000 (submodule gitlink) entries
        code, out, _ = self.run_git_cmd(["ls-files", "-s", "dormitory-telegram-bot"])
        self.assertEqual(code, 0, "F1.4: git ls-files command must succeed")
        gitlinks = [line for line in out.splitlines() if line.startswith("160000")]
        self.assertEqual(
            gitlinks,
            [],
            f"F1.4: Monorepo must not contain mode 160000 gitlinks: {gitlinks}"
        )

        # Assertion 5: Git status does not report submodule dirty status ('m')
        code, out, _ = self.run_git_cmd(["status", "--porcelain", "dormitory-telegram-bot"])
        self.assertEqual(code, 0, "F1.5: git status must succeed")
        submodule_dirty = [line for line in out.splitlines() if line.startswith(" m")]
        self.assertEqual(
            submodule_dirty,
            [],
            f"F1.5: No submodule dirty status indicators allowed: {submodule_dirty}"
        )

    # -------------------------------------------------------------------------
    # Feature F2: Monorepo Bot Tracking
    # -------------------------------------------------------------------------
    def test_f02_monorepo_bot_tracking(self):
        """F2: Verifies all 47 Telegram bot codebase files are tracked directly in root git repo."""
        # Assertion 1: Exactly 47 files tracked under dormitory-telegram-bot/
        code, out, _ = self.run_git_cmd(["ls-files", "dormitory-telegram-bot"])
        self.assertEqual(code, 0, "F2.1: git ls-files command must succeed")
        tracked_files = [line.strip() for line in out.splitlines() if line.strip()]
        self.assertEqual(
            len(tracked_files),
            47,
            f"F2.1: Expected exactly 47 tracked bot files, found {len(tracked_files)}"
        )

        # Assertion 2: Core configuration files are tracked
        core_configs = [
            "dormitory-telegram-bot/pyproject.toml",
            "dormitory-telegram-bot/uv.lock",
            "dormitory-telegram-bot/Dockerfile",
            "dormitory-telegram-bot/docker-compose.yml"
        ]
        for cfg in core_configs:
            self.assertIn(cfg, tracked_files, f"F2.2: Core config file must be tracked: {cfg}")

        # Assertion 3: bot.sh is tracked and has executable file mode (100755)
        code, out, _ = self.run_git_cmd(["ls-files", "-s", "dormitory-telegram-bot/bot.sh"])
        self.assertEqual(code, 0, "F2.3: bot.sh must be in git index")
        self.assertTrue(
            out.strip().startswith("100755"),
            f"F2.3: bot.sh must have git mode 100755, got: {out.strip()}"
        )

        # Assertion 4: All 19 src/ files and 14 tests/ files are tracked
        src_files = [f for f in tracked_files if f.startswith("dormitory-telegram-bot/src/")]
        test_files = [f for f in tracked_files if f.startswith("dormitory-telegram-bot/tests/")]
        self.assertEqual(len(src_files), 19, f"F2.4: Expected 19 src/ files, found {len(src_files)}")
        self.assertEqual(len(test_files), 14, f"F2.4: Expected 14 tests/ files, found {len(test_files)}")

        # Assertion 5: Runtime secrets (.env) are NOT tracked
        code, out, _ = self.run_git_cmd(["ls-files", "dormitory-telegram-bot/.env"])
        self.assertEqual(
            out.strip(),
            "",
            "F2.5: dormitory-telegram-bot/.env must not be tracked in Git"
        )

    # -------------------------------------------------------------------------
    # Feature F3: Git Ignore Alignment
    # -------------------------------------------------------------------------
    def test_f03_git_ignore_alignment(self):
        """F3: Verifies .agents/ is ignored by root .gitignore and hierarchical ignore rules are preserved."""
        root_gitignore = self.REPO_ROOT / ".gitignore"

        # Assertion 1: Root .gitignore contains .agents/
        self.assertTrue(root_gitignore.is_file(), "F3.1: Root .gitignore must exist")
        content = root_gitignore.read_text(encoding="utf-8")
        has_agents_rule = any(
            re.match(r"^\s*\.agents/?\s*$", line) for line in content.splitlines()
        )
        self.assertTrue(has_agents_rule, "F3.1: Root .gitignore must contain .agents/ rule")

        # Assertion 2: git check-ignore confirms .agents/ is ignored
        is_ignored, source = self.git_check_ignore(".agents/")
        self.assertTrue(is_ignored, f"F3.2: .agents/ must be ignored by git: {source}")

        # Assertion 3: git status reports zero untracked files for .agents/
        code, out, _ = self.run_git_cmd(["status", "--porcelain", ".agents/"])
        self.assertEqual(code, 0, "F3.3: git status .agents/ must exit 0")
        self.assertEqual(out.strip(), "", f"F3.3: .agents/ should not appear in status: {out}")

        # Assertion 4: Subdirectory .gitignore exists in dormitory-telegram-bot/
        bot_gitignore = self.BOT_DIR / ".gitignore"
        self.assertTrue(bot_gitignore.is_file(), "F3.4: Subdirectory .gitignore must exist")

        # Assertion 5: Subdirectory .gitignore is tracked in root Git index
        self.assertGitTracked("dormitory-telegram-bot/.gitignore")

    # -------------------------------------------------------------------------
    # Feature F4: Sibling Directory Cleanup
    # -------------------------------------------------------------------------
    def test_f04_sibling_directory_cleanup(self):
        """F4: Verifies deprecated sibling directory stub is deleted or completely inactive."""
        sibling = self.SIBLING_DIR

        # Assertion 1: Sibling directory has no .git folder
        self.assertFalse(
            (sibling / ".git").exists(),
            f"F4.1: Sibling directory must not have a .git folder: {sibling / '.git'}"
        )

        # Assertion 2: Sibling directory has no src/ folder
        self.assertFalse(
            (sibling / "src").exists(),
            f"F4.2: Sibling directory must not have a src/ folder: {sibling / 'src'}"
        )

        # Assertion 3: Sibling directory has no pyproject.toml
        self.assertFalse(
            (sibling / "pyproject.toml").exists(),
            f"F4.3: Sibling directory must not have pyproject.toml"
        )

        # Assertion 4: Sibling directory has no docker-compose.yml
        self.assertFalse(
            (sibling / "docker-compose.yml").exists(),
            f"F4.4: Sibling directory must not have docker-compose.yml"
        )

        # Assertion 5: Sibling directory is either deleted or contains no codebase files
        if sibling.exists():
            entries = [e.name for e in sibling.iterdir() if e.name not in (".keep", ".agents")]
            self.assertEqual(
                entries,
                [],
                f"F4.5: Sibling directory must contain no codebase files, found: {entries}"
            )
        else:
            self.assertFalse(sibling.exists(), "F4.5: Sibling directory completely removed")

    # -------------------------------------------------------------------------
    # Feature F5: Gitea SSH Key Authorization
    # -------------------------------------------------------------------------
    def test_f05_gitea_ssh_key_authorization(self):
        """F5: Verifies local SSH key exists and can authenticate against Gitea server."""
        ssh_dir = Path(os.path.expanduser("~/.ssh"))
        priv_key = ssh_dir / "id_ed25519"
        pub_key = ssh_dir / "id_ed25519.pub"

        # Assertion 1: Private and public ED25519 keys exist
        self.assertTrue(priv_key.is_file(), f"F5.1: Private key must exist: {priv_key}")
        self.assertTrue(pub_key.is_file(), f"F5.1: Public key must exist: {pub_key}")

        # Assertion 2: Private key has mode 0600
        actual_mode = stat.S_IMODE(priv_key.stat().st_mode)
        self.assertEqual(
            oct(actual_mode),
            oct(0o600),
            f"F5.2: Private key mode must be 0600, got: {oct(actual_mode)}"
        )

        # Assertion 3: Public key has non-empty valid OpenSSH ed25519 format
        pub_content = pub_key.read_text(encoding="utf-8").strip()
        self.assertTrue(
            pub_content.startswith("ssh-ed25519 "),
            "F5.3: Public key must be in valid ssh-ed25519 format"
        )

        # Assertion 4: Public key comment or content length is valid
        parts = pub_content.split()
        self.assertGreaterEqual(len(parts), 2, "F5.4: Public key must contain key-type and key-blob")
        self.assertGreater(len(parts[1]), 30, "F5.4: Public key blob length must be > 30 chars")

        # Assertion 5: SSH handshake to Gitea server succeeds without password prompt
        code, out, err = self.verify_ssh_handshake("94.183.146.0", port=22022, timeout=5)
        combined = out + err
        self.assertTrue(
            "Hi there" in combined or "successfully authenticated" in combined or code in (0, 1),
            f"F5.5: Gitea SSH authentication failed: {combined}"
        )
        self.assertNotIn("Permission denied (publickey)", combined, "F5.5: Publickey was rejected by Gitea")

    # -------------------------------------------------------------------------
    # Feature F6: Gitea History Synchronization
    # -------------------------------------------------------------------------
    def test_f06_gitea_history_synchronization(self):
        """F6: Verifies local HEAD commit matches remote Gitea repository main branch."""
        gitea_remote = "ssh://git@94.183.146.0:22022/Javad/dormitory-management.git"

        # Assertion 1: git ls-remote connects to Gitea repository with exit code 0
        code, out, err = self.run_git_cmd(["ls-remote", gitea_remote])
        self.assertEqual(code, 0, f"F6.1: git ls-remote to Gitea failed: {err}")

        # Assertion 2: Gitea refs/heads/main exists in remote refs
        remote_refs = dict(line.split("\t")[::-1] for line in out.splitlines() if "\t" in line)
        self.assertIn("refs/heads/main", remote_refs, "F6.2: refs/heads/main must exist on Gitea")

        # Assertion 3: Gitea main branch SHA does NOT match the dummy initial commit
        dummy_sha = "a9aacb0e92b56b940d5c55282e60a1491b29162d"
        gitea_main_sha = remote_refs.get("refs/heads/main")
        self.assertNotEqual(
            gitea_main_sha,
            dummy_sha,
            "F6.3: Gitea main branch must not be stuck on dummy initial commit"
        )

        # Assertion 4: Local HEAD SHA matches Gitea main branch SHA
        code, local_head, _ = self.run_git_cmd(["rev-parse", "HEAD"])
        self.assertEqual(code, 0, "F6.4: git rev-parse HEAD failed")
        local_head_sha = local_head.strip()
        self.assertEqual(
            gitea_main_sha,
            local_head_sha,
            f"F6.4: Gitea main SHA ({gitea_main_sha}) does not match local HEAD ({local_head_sha})"
        )

        # Assertion 5: Git rev-list confirms zero divergent commits
        code, count_out, _ = self.run_git_cmd(
            ["rev-list", "--count", f"HEAD...{gitea_main_sha}"]
        )
        self.assertEqual(code, 0, "F6.5: rev-list command failed")
        self.assertEqual(
            count_out.strip(),
            "0",
            f"F6.5: History divergence count must be 0, got: {count_out.strip()}"
        )

    # -------------------------------------------------------------------------
    # Feature F7: Dual Push Remote Configuration
    # -------------------------------------------------------------------------
    def test_f07_dual_push_remote_configuration(self):
        """F7: Verifies origin is configured with dual push URLs for GitHub SSH and Gitea SSH."""
        # Assertion 1: Fetch URL for origin is GitHub SSH URL
        code, fetch_url, _ = self.run_git_cmd(["remote", "get-url", "origin"])
        self.assertEqual(code, 0, "F7.1: git remote get-url origin failed")
        self.assertEqual(
            fetch_url.strip(),
            "git@github.com:javad-hosseini/dorm-management.git",
            f"F7.1: Origin fetch URL must be GitHub SSH, got: {fetch_url.strip()}"
        )

        # Assertion 2: Exactly 2 push URLs configured for origin
        push_urls = self.get_git_push_urls("origin")
        self.assertEqual(
            len(push_urls),
            2,
            f"F7.2: Origin must have exactly 2 push URLs, found {len(push_urls)}: {push_urls}"
        )

        # Assertion 3: Push URL 1 is GitHub SSH
        self.assertIn(
            "git@github.com:javad-hosseini/dorm-management.git",
            push_urls,
            "F7.3: Push URL 1 must be GitHub SSH"
        )

        # Assertion 4: Push URL 2 is Gitea SSH on port 22022
        self.assertIn(
            "ssh://git@94.183.146.0:22022/Javad/dormitory-management.git",
            push_urls,
            "F7.4: Push URL 2 must be Gitea SSH"
        )

        # Assertion 5: Dedicated secondary remote 'gitea' is configured
        code, gitea_url, _ = self.run_git_cmd(["remote", "get-url", "gitea"])
        self.assertEqual(code, 0, "F7.5: Dedicated 'gitea' remote must exist")
        self.assertEqual(
            gitea_url.strip(),
            "ssh://git@94.183.146.0:22022/Javad/dormitory-management.git",
            f"F7.5: gitea remote URL mismatch: {gitea_url.strip()}"
        )

    # -------------------------------------------------------------------------
    # Feature F8: Git Dual Push Verification
    # -------------------------------------------------------------------------
    def test_f08_git_dual_push_verification(self):
        """F8: Verifies non-destructive dry-run push and remote ref synchronization."""
        # Assertion 1: GitHub SSH handshake succeeds
        code, out, err = self.verify_ssh_handshake("github.com", port=22, timeout=5)
        combined_gh = out + err
        self.assertTrue(
            "javad-hosseini" in combined_gh or "successfully authenticated" in combined_gh or code in (0, 1),
            f"F8.1: GitHub SSH handshake failed: {combined_gh}"
        )

        # Assertion 2: Gitea SSH handshake succeeds
        code, out, err = self.verify_ssh_handshake("94.183.146.0", port=22022, timeout=5)
        combined_gitea = out + err
        self.assertTrue(
            "Javad" in combined_gitea or "successfully authenticated" in combined_gitea or code in (0, 1),
            f"F8.2: Gitea SSH handshake failed: {combined_gitea}"
        )

        # Assertion 3: git push origin main --dry-run completes with exit code 0
        code, out, err = self.git_push_dry_run("origin", "main")
        self.assertEqual(
            code,
            0,
            f"F8.3: git push origin main --dry-run failed with code {code}: {err or out}"
        )

        # Assertion 4: Remote main branch on GitHub matches local HEAD
        code, gh_out, _ = self.run_git_cmd([
            "ls-remote", "git@github.com:javad-hosseini/dorm-management.git", "refs/heads/main"
        ])
        self.assertEqual(code, 0, "F8.4: GitHub ls-remote failed")
        gh_main_sha = gh_out.split()[0] if gh_out.strip() else ""

        code, local_head, _ = self.run_git_cmd(["rev-parse", "HEAD"])
        local_head_sha = local_head.strip()
        self.assertEqual(
            gh_main_sha,
            local_head_sha,
            f"F8.4: GitHub main ({gh_main_sha}) does not match local HEAD ({local_head_sha})"
        )

        # Assertion 5: Remote main branch on Gitea matches local HEAD
        code, gitea_out, _ = self.run_git_cmd([
            "ls-remote", "ssh://git@94.183.146.0:22022/Javad/dormitory-management.git", "refs/heads/main"
        ])
        self.assertEqual(code, 0, "F8.5: Gitea ls-remote failed")
        gitea_main_sha = gitea_out.split()[0] if gitea_out.strip() else ""
        self.assertEqual(
            gitea_main_sha,
            local_head_sha,
            f"F8.5: Gitea main ({gitea_main_sha}) does not match local HEAD ({local_head_sha})"
        )

    # -------------------------------------------------------------------------
    # Feature F9: Shared Directory Hierarchy
    # -------------------------------------------------------------------------
    def test_f09_shared_directory_hierarchy(self):
        """F9: Verifies media/spreadsheets/{incoming,processed,failed} directory structure and permissions."""
        base = self.SPREADSHEETS_DIR

        # Assertion 1: media/spreadsheets parent directory exists
        self.assertTrue(base.is_dir(), f"F9.1: Directory {base} must exist")

        # Assertion 2: media/spreadsheets/incoming exists
        self.assertTrue(self.INCOMING_DIR.is_dir(), f"F9.2: Directory {self.INCOMING_DIR} must exist")

        # Assertion 3: media/spreadsheets/processed exists
        self.assertTrue(self.PROCESSED_DIR.is_dir(), f"F9.3: Directory {self.PROCESSED_DIR} must exist")

        # Assertion 4: media/spreadsheets/failed exists
        self.assertTrue(self.FAILED_DIR.is_dir(), f"F9.4: Directory {self.FAILED_DIR} must exist")

        # Assertion 5: POSIX ownership is UID 1000 and GID 1000 for all three subdirectories
        for d in (self.INCOMING_DIR, self.PROCESSED_DIR, self.FAILED_DIR):
            st = d.stat()
            self.assertEqual(st.st_uid, 1000, f"F9.5: UID must be 1000 for {d}, got {st.st_uid}")
            self.assertEqual(st.st_gid, 1000, f"F9.5: GID must be 1000 for {d}, got {st.st_gid}")
            mode = stat.S_IMODE(st.st_mode)
            self.assertIn(
                oct(mode),
                (oct(0o755), oct(0o775)),
                f"F9.5: Mode must be 0755 or 0775 for {d}, got {oct(mode)}"
            )

    # -------------------------------------------------------------------------
    # Feature F10: Monorepo Relative Volume Mount
    # -------------------------------------------------------------------------
    def test_f10_monorepo_relative_volume_mount(self):
        """F10: Verifies docker-compose.yml uses monorepo-relative volume mount with SELinux :z flag."""
        # Assertion 1: docker-compose.yml exists
        self.assertTrue(self.COMPOSE_FILE.is_file(), "F10.1: docker-compose.yml must exist")

        # Assertion 2: Parse compose configuration
        compose_data = self.parse_compose_file()
        services = compose_data.get("services", {})
        bot_svc = services.get("dormitory-bot", {})
        volumes = bot_svc.get("volumes", [])
        self.assertGreater(len(volumes), 0, "F10.2: dormitory-bot must have volumes defined")

        # Assertion 3: Obsolete path /home/javad/projects/dormitory-management is completely absent
        raw_text = self.COMPOSE_FILE.read_text(encoding="utf-8")
        self.assertNotIn(
            "/home/javad/projects/dormitory-management",
            raw_text,
            "F10.3: Obsolete absolute mount path must be removed from docker-compose.yml"
        )

        # Assertion 4: Volume list contains relative mount to ../media/spreadsheets/incoming with :z
        has_correct_mount = any(
            re.match(r"^\.\./media/spreadsheets/incoming:/app/incoming_spreadsheets(?::z)?$", vol)
            for vol in volumes
        )
        self.assertTrue(
            has_correct_mount,
            f"F10.4: Missing relative volume mount to ../media/spreadsheets/incoming: {volumes}"
        )

        # Assertion 5: Relative path resolves from BOT_DIR to canonical host incoming dropzone
        rel_resolved = (self.BOT_DIR / "../media/spreadsheets/incoming").resolve()
        canonical_target = self.INCOMING_DIR.resolve()
        self.assertEqual(
            rel_resolved,
            canonical_target,
            f"F10.5: Relative mount path resolves to {rel_resolved}, expected {canonical_target}"
        )

    # -------------------------------------------------------------------------
    # Feature F11: Container User & Permissions
    # -------------------------------------------------------------------------
    def test_f11_container_user_and_permissions(self):
        """F11: Verifies docker-compose user mapping and non-root dropzone file permissions."""
        compose_data = self.parse_compose_file()
        bot_svc = compose_data.get("services", {}).get("dormitory-bot", {})

        # Assertion 1: user directive is configured in dormitory-bot service
        user_val = bot_svc.get("user")
        self.assertIsNotNone(user_val, "F11.1: 'user:' directive must be specified in docker-compose.yml")

        # Assertion 2: user directive maps UID 1000 and GID 1000 (directly or via env substitution)
        is_valid_user = user_val in ("1000:1000", "${BOT_UID:-1000}:${BOT_GID:-1000}", "$BOT_UID:$BOT_GID")
        self.assertTrue(
            is_valid_user,
            f"F11.2: User mapping must specify 1000:1000, got: {user_val}"
        )

        # Assertion 3: Host dropzone directory is writable by user javad (UID 1000)
        self.assertTrue(
            os.access(self.INCOMING_DIR, os.R_OK | os.W_OK | os.X_OK),
            "F11.3: Incoming dropzone must be writable by host user"
        )

        # Assertion 4: Canary file created in dropzone inherits UID 1000 and GID 1000
        canary = self.create_canary_file(self.INCOMING_DIR)
        st = canary.stat()
        self.assertEqual(st.st_uid, 1000, f"F11.4: Canary UID must be 1000, got: {st.st_uid}")
        self.assertEqual(st.st_gid, 1000, f"F11.4: Canary GID must be 1000, got: {st.st_gid}")

        # Assertion 5: Canary file mode is regular read-write (0644 or 0664)
        mode = stat.S_IMODE(st.st_mode)
        self.assertIn(
            oct(mode),
            (oct(0o644), oct(0o664)),
            f"F11.5: File mode must be 0644 or 0664, got: {oct(mode)}"
        )

    # -------------------------------------------------------------------------
    # Feature F12: Root Dropzone Symlink
    # -------------------------------------------------------------------------
    def test_f12_root_dropzone_symlink(self):
        """F12: Verifies root incoming_spreadsheets symlink points to media/spreadsheets/incoming."""
        symlink = self.ROOT_SYMLINK

        # Assertion 1: incoming_spreadsheets exists at repo root
        self.assertTrue(
            os.path.lexists(str(symlink)),
            f"F12.1: Symlink {symlink} must exist"
        )

        # Assertion 2: Path is indeed a symbolic link
        self.assertTrue(
            symlink.is_symlink(),
            f"F12.2: {symlink} must be a symbolic link"
        )

        # Assertion 3: Raw symlink points to media/spreadsheets/incoming
        raw_target = os.readlink(str(symlink))
        self.assertIn(
            raw_target.rstrip("/"),
            ("media/spreadsheets/incoming", str(self.INCOMING_DIR)),
            f"F12.3: Raw symlink target unexpected: {raw_target}"
        )

        # Assertion 4: Resolves to an existing directory
        self.assertTrue(
            symlink.is_dir(),
            f"F12.4: Symlink destination must be a directory"
        )

        # Assertion 5: Canonical path matches canonical incoming dropzone path
        self.assertEqual(
            symlink.resolve(),
            self.INCOMING_DIR.resolve(),
            f"F12.5: Symlink resolved to {symlink.resolve()}, expected {self.INCOMING_DIR.resolve()}"
        )

    # -------------------------------------------------------------------------
    # Feature F13: Bot Startup Script Update
    # -------------------------------------------------------------------------
    def test_f13_bot_startup_script_update(self):
        """F13: Verifies bot.sh syntax, directory pre-creation, and execution safety."""
        # Assertion 1: bot.sh exists and is marked executable
        self.assertTrue(self.BOT_SCRIPT.is_file(), "F13.1: bot.sh must exist")
        self.assertTrue(os.access(self.BOT_SCRIPT, os.X_OK), "F13.1: bot.sh must be executable")

        # Assertion 2: bash -n checks syntax without errors
        code, out, err = self.safe_run(["bash", "-n", str(self.BOT_SCRIPT)])
        self.assertEqual(code, 0, f"F13.2: bot.sh syntax check failed: {err}")

        # Assertion 3: bot.sh pre-creates media/spreadsheets/incoming
        content = self.BOT_SCRIPT.read_text(encoding="utf-8")
        has_precreation = (
            "media/spreadsheets/incoming" in content or
            "../media/spreadsheets/incoming" in content
        )
        self.assertTrue(
            has_precreation,
            "F13.3: bot.sh must pre-create media/spreadsheets/incoming directory"
        )

        # Assertion 4: Obsolete path /home/javad/projects/dormitory-management is absent from bot.sh
        self.assertNotIn(
            "/home/javad/projects/dormitory-management",
            content,
            "F13.4: Obsolete path must be removed from bot.sh"
        )

        # Assertion 5: bot.sh help command executes cleanly with exit code 0
        code, out, err = self.safe_run(["bash", str(self.BOT_SCRIPT), "help"], cwd=self.BOT_DIR)
        self.assertEqual(code, 0, f"F13.5: bot.sh help failed: {err}")
        self.assertIn("Usage:", out, "F13.5: bot.sh help must display usage information")

    # -------------------------------------------------------------------------
    # Feature F14: End-to-End Acceptance Validation
    # -------------------------------------------------------------------------
    def test_f14_end_to_end_acceptance_validation(self):
        """F14: Verifies full integration across monorepo tracking, dual push, and dropzone interchange."""
        # Assertion 1: Monorepo acceptance - no nested .git, 47 tracked bot files
        self.assertFalse((self.BOT_DIR / ".git").exists(), "F14.1: No nested .git")
        code, out, _ = self.run_git_cmd(["ls-files", "dormitory-telegram-bot"])
        tracked = [l for l in out.splitlines() if l.strip()]
        self.assertEqual(len(tracked), 47, f"F14.1: Expected 47 tracked bot files, got {len(tracked)}")

        # Assertion 2: Dual push remote configuration verified
        push_urls = self.get_git_push_urls("origin")
        self.assertEqual(len(push_urls), 2, f"F14.2: Expected 2 push URLs, got: {push_urls}")

        # Assertion 3: Push dry-run executes cleanly targeting both remotes
        code, _, err = self.git_push_dry_run("origin", "main")
        self.assertEqual(code, 0, f"F14.3: Dry-run push failed: {err}")

        # Assertion 4: Dropzone interchange - file written via symlink is accessible via canonical path with same inode
        canary = self.create_canary_file(self.ROOT_SYMLINK)
        canonical_canary = self.INCOMING_DIR / canary.name
        self.assertTrue(canonical_canary.exists(), "F14.4: File written via symlink must appear in canonical path")
        self.assertEqual(
            canary.stat().st_ino,
            canonical_canary.stat().st_ino,
            "F14.4: Inode numbers must match across symlink and canonical path"
        )

        # Assertion 5: Host unprivileged delete succeeds cleanly without PermissionError
        canary.unlink()
        self.assertFalse(canonical_canary.exists(), "F14.5: Canary file deleted cleanly")
