"""
tests/e2e/test_tier3_cross_feature.py
Tier 3: Pairwise and Tripartite Cross-Feature Interactions (T3_01 to T3_16).
Exercises the operational seams between monorepo tracking, dual remotes,
SELinux container volume mounts, and dropzone interchange.
"""

import os
import stat
import shutil
import subprocess
from pathlib import Path
from tests.e2e.base import E2EBaseTestCase
from tests.e2e.fixtures import (
    create_valid_transaction_xlsx,
    create_companion_instructions,
    create_valid_bank_statement_csv
)


class Tier3CrossFeatureTests(E2EBaseTestCase):
    """
    Tier 3 tests verify that independently configured features interact
    cohesively without cross-boundary regressions or permission conflicts.
    """

    # -------------------------------------------------------------------------
    # T3_01: Nested Git Elimination & Root Monorepo Tracking (F1 + F2)
    # -------------------------------------------------------------------------
    def test_t3_01_nested_git_elimination_and_tracking(self):
        """T3_01: Deleting nested .git enables root repo to track all 47 bot files directly."""
        bot_git = self.BOT_DIR / ".git"
        self.assertFalse(bot_git.exists(), "T3_01: dormitory-telegram-bot/.git must be deleted")

        code, out, _ = self.run_git_cmd(["ls-files", "-s", "dormitory-telegram-bot"])
        self.assertEqual(code, 0, "T3_01: git ls-files must exit 0")
        lines = [l.strip() for l in out.splitlines() if l.strip()]
        self.assertEqual(len(lines), 47, f"T3_01: Expected 47 tracked bot files, found {len(lines)}")

        # No submodule gitlinks (160000) allowed
        self.assertFalse(
            any(l.startswith("160000") for l in lines),
            "T3_01: No submodule gitlink (160000) entries permitted"
        )
        self.assertTrue(
            any("dormitory-telegram-bot/src/main.py" in l for l in lines),
            "T3_01: main.py must be tracked directly"
        )
        self.assertTrue(
            any("dormitory-telegram-bot/bot.sh" in l for l in lines),
            "T3_01: bot.sh must be tracked directly"
        )

    # -------------------------------------------------------------------------
    # T3_02: Monorepo Bot Tracking & Gitignore Layering (F2 + F3)
    # -------------------------------------------------------------------------
    def test_t3_02_gitignore_layering_and_preservation(self):
        """T3_02: Root .gitignore ignores .agents/ without shadowing bot files; nested ignore rules intact."""
        # Root ignore check
        is_ignored_agents, _ = self.git_check_ignore(".agents/plan.md")
        self.assertTrue(is_ignored_agents, "T3_02: .agents/ must be ignored by root .gitignore")

        # Bot source must NOT be ignored
        is_ignored_src, _ = self.git_check_ignore("dormitory-telegram-bot/src/main.py")
        self.assertFalse(is_ignored_src, "T3_02: Bot source files must NOT be ignored")

        # Nested ignore checks
        is_ignored_db, _ = self.git_check_ignore("dormitory-telegram-bot/data/dormitory_bot.db")
        self.assertTrue(is_ignored_db, "T3_02: Bot sqlite database must be ignored by nested .gitignore")

        is_ignored_env, _ = self.git_check_ignore("dormitory-telegram-bot/.env")
        self.assertTrue(is_ignored_env, "T3_02: Bot .env must be ignored by nested .gitignore")

        is_ignored_xlsx, _ = self.git_check_ignore("dormitory-telegram-bot/incoming_spreadsheets/test.xlsx")
        self.assertTrue(is_ignored_xlsx, "T3_02: Incoming xlsx files must be ignored")

        is_ignored_keep, _ = self.git_check_ignore("dormitory-telegram-bot/incoming_spreadsheets/.gitkeep")
        self.assertFalse(is_ignored_keep, "T3_02: .gitkeep in dropzone must NOT be ignored")

    # -------------------------------------------------------------------------
    # T3_03: Monorepo Bot Tracking & Sibling Stub Deprecation (F2 + F4)
    # -------------------------------------------------------------------------
    def test_t3_03_sibling_deprecation_and_path_independence(self):
        """T3_03: Sibling directory is inactive and monorepo files contain zero references to it."""
        sibling = self.SIBLING_DIR
        if sibling.exists():
            self.assertFalse((sibling / ".git").exists(), "T3_03: Sibling .git must not exist")
            self.assertFalse((sibling / "src").exists(), "T3_03: Sibling src/ must not exist")

        # Verify monorepo bot codebase does not contain hardcoded references to the external sibling
        code, out, _ = self.safe_run([
            "grep", "-rnw",
            "--exclude-dir=.venv",
            "--exclude-dir=__pycache__",
            "--exclude-dir=.git",
            "--exclude=*.pyc",
            "dormitory-telegram-bot",
            "-e", "/home/javad/projects/dorm/dormitory-telegram-bot"
        ])
        self.assertEqual(
            out.strip(),
            "",
            f"T3_03: Found stale sibling path references in monorepo: {out}"
        )

    # -------------------------------------------------------------------------
    # T3_04: Gitea SSH Key Auth & Divergent History Synchronization (F5 + F6)
    # -------------------------------------------------------------------------
    def test_t3_04_gitea_ssh_and_history_sync(self):
        """T3_04: Gitea SSH connects and aligned repository main branch matches local HEAD."""
        # 1. SSH Handshake
        code, out, err = self.verify_ssh_handshake("94.183.146.0", port=22022, timeout=5)
        combined = out + err
        self.assertTrue(
            "Hi" in combined or "authenticated" in combined or code in (0, 1),
            f"T3_04: Gitea SSH handshake failed: {combined}"
        )

        # 2. History alignment
        gitea_url = "ssh://git@94.183.146.0:22022/Javad/dormitory-management.git"
        code, remote_out, _ = self.run_git_cmd(["ls-remote", gitea_url, "refs/heads/main"])
        self.assertEqual(code, 0, "T3_04: ls-remote to Gitea failed")
        gitea_sha = remote_out.split()[0] if remote_out.strip() else ""

        code, local_out, _ = self.run_git_cmd(["rev-parse", "HEAD"])
        local_sha = local_out.strip()
        self.assertEqual(
            gitea_sha,
            local_sha,
            f"T3_04: Gitea main ({gitea_sha}) is not aligned with local HEAD ({local_sha})"
        )

    # -------------------------------------------------------------------------
    # T3_05: Gitea History Alignment & Dual Push Remote Configuration (F6 + F7)
    # -------------------------------------------------------------------------
    def test_t3_05_history_alignment_dual_push_urls(self):
        """T3_05: Origin push URLs include both remotes and dry-run push encounters no fast-forward rejection."""
        push_urls = self.get_git_push_urls("origin")
        self.assertIn("git@github.com:javad-hosseini/dorm-management.git", push_urls)
        self.assertIn("ssh://git@94.183.146.0:22022/Javad/dormitory-management.git", push_urls)

        code, _, err = self.git_push_dry_run("origin", "main")
        self.assertEqual(code, 0, f"T3_05: Dual push dry run failed: {err}")
        self.assertNotIn("rejected", err.lower(), "T3_05: Push was rejected by a remote")

    # -------------------------------------------------------------------------
    # T3_06: Dual Push Configuration & Synchronous Push Verification (F7 + F8)
    # -------------------------------------------------------------------------
    def test_t3_06_dual_push_synchronous_verification(self):
        """T3_06: Dual push targets both remotes and both remote heads match local HEAD."""
        code, local_out, _ = self.run_git_cmd(["rev-parse", "HEAD"])
        local_sha = local_out.strip()

        code, gh_out, _ = self.run_git_cmd([
            "ls-remote", "git@github.com:javad-hosseini/dorm-management.git", "refs/heads/main"
        ])
        gh_sha = gh_out.split()[0] if gh_out.strip() else ""

        code, gitea_out, _ = self.run_git_cmd([
            "ls-remote", "ssh://git@94.183.146.0:22022/Javad/dormitory-management.git", "refs/heads/main"
        ])
        gitea_sha = gitea_out.split()[0] if gitea_out.strip() else ""

        self.assertEqual(gh_sha, local_sha, f"T3_06: GitHub out of sync: {gh_sha} != {local_sha}")
        self.assertEqual(gitea_sha, local_sha, f"T3_06: Gitea out of sync: {gitea_sha} != {local_sha}")

    # -------------------------------------------------------------------------
    # T3_07: Unified Monorepo Bot Code & Dual Remote Push Verification (F2 + F7 + F8)
    # -------------------------------------------------------------------------
    def test_t3_07_monorepo_bot_code_pushed_to_both_remotes(self):
        """T3_07: Bot codebase tree exists at HEAD and is synchronized to both remotes."""
        code, head_out, _ = self.run_git_cmd(["rev-parse", "HEAD"])
        head_sha = head_out.strip()

        # Check tree object
        code, tree_out, _ = self.run_git_cmd(["ls-tree", head_sha, "dormitory-telegram-bot/"])
        self.assertIn("tree", tree_out, "T3_07: dormitory-telegram-bot must be a committed tree object at HEAD")

        # Verify remotes are at HEAD
        gh_sha = self.run_git_cmd(["ls-remote", "git@github.com:javad-hosseini/dorm-management.git", "refs/heads/main"])[1].split()[0]
        gitea_sha = self.run_git_cmd(["ls-remote", "ssh://git@94.183.146.0:22022/Javad/dormitory-management.git", "refs/heads/main"])[1].split()[0]
        self.assertEqual(gh_sha, head_sha)
        self.assertEqual(gitea_sha, head_sha)

    # -------------------------------------------------------------------------
    # T3_08: Shared Directory Hierarchy & Monorepo Relative Compose Volume Mount (F9 + F10)
    # -------------------------------------------------------------------------
    def test_t3_08_shared_directory_and_compose_volume_mount(self):
        """T3_08: Shared media directories exist and compose mounts relative path with :z."""
        for d in (self.INCOMING_DIR, self.PROCESSED_DIR, self.FAILED_DIR):
            self.assertTrue(d.is_dir(), f"T3_08: Directory {d} must exist")

        compose_data = self.parse_compose_file()
        volumes = compose_data.get("services", {}).get("dormitory-bot", {}).get("volumes", [])
        has_rel_mount = any(
            v.startswith("../media/spreadsheets/incoming:/app/incoming_spreadsheets") for v in volumes
        )
        self.assertTrue(has_rel_mount, f"T3_08: Compose must bind relative incoming dropzone: {volumes}")

    # -------------------------------------------------------------------------
    # T3_09: Relative Volume Mount & Container User 1000:1000 File Creation (F10 + F11)
    # -------------------------------------------------------------------------
    def test_t3_09_container_user_1000_file_creation(self):
        """T3_09: Compose maps user 1000:1000 ensuring files in dropzone have UID 1000."""
        compose_data = self.parse_compose_file()
        user_val = compose_data.get("services", {}).get("dormitory-bot", {}).get("user", "")
        self.assertTrue(
            "1000:1000" in user_val or "BOT_UID" in user_val,
            f"T3_09: Compose must specify non-root user (1000:1000), got: {user_val}"
        )

        # Drop canary and verify permissions
        canary = self.create_canary_file(self.INCOMING_DIR)
        st = canary.stat()
        self.assertEqual(st.st_uid, 1000, "T3_09: Dropzone canary UID must be 1000")
        self.assertEqual(st.st_gid, 1000, "T3_09: Dropzone canary GID must be 1000")

    # -------------------------------------------------------------------------
    # T3_10: Media Directory Hierarchy & Root Convenience Symlink Dropzone (F9 + F12)
    # -------------------------------------------------------------------------
    def test_t3_10_root_symlink_dropzone(self):
        """T3_10: Root symlink points to canonical dropzone and shares identical file inodes."""
        self.assertTrue(self.ROOT_SYMLINK.is_symlink(), "T3_10: Root dropzone must be a symlink")
        self.assertEqual(
            self.ROOT_SYMLINK.resolve(),
            self.INCOMING_DIR.resolve(),
            "T3_10: Root symlink must resolve to canonical incoming directory"
        )

        probe = self.ROOT_SYMLINK / ".t3_10_probe.tmp"
        probe.write_text("symlink-inode-test", encoding="utf-8")
        self.addCleanup(self._safe_unlink, probe)

        canonical = self.INCOMING_DIR / probe.name
        self.assertTrue(canonical.exists(), "T3_10: File written via symlink must exist at canonical path")
        self.assertEqual(probe.stat().st_ino, canonical.stat().st_ino, "T3_10: Inode numbers must match")

    # -------------------------------------------------------------------------
    # T3_11: Relative Volume Mount & bot.sh Host Directory Pre-Creation Guard (F10 + F13)
    # -------------------------------------------------------------------------
    def test_t3_11_bot_sh_precreation_guard(self):
        """T3_11: bot.sh pre-creates shared directory before docker compose up."""
        script_text = self.BOT_SCRIPT.read_text(encoding="utf-8")
        has_mkdir = "mkdir -p" in script_text and (
            "media/spreadsheets/incoming" in script_text or
            "../media/spreadsheets/incoming" in script_text
        )
        self.assertTrue(has_mkdir, "T3_11: bot.sh must contain mkdir -p for media/spreadsheets/incoming")

    # -------------------------------------------------------------------------
    # T3_12: Shared Hierarchy, Volume Mount, and Non-Root SELinux/Permissions (F9 + F10 + F11)
    # -------------------------------------------------------------------------
    def test_t3_12_shared_hierarchy_volume_mount_and_permissions(self):
        """T3_12: Verifies SELinux :z flag in compose and host directory access rights."""
        compose_data = self.parse_compose_file()
        volumes = compose_data.get("services", {}).get("dormitory-bot", {}).get("volumes", [])
        has_z = any(v.endswith(":z") and "incoming" in v for v in volumes)
        self.assertTrue(has_z, f"T3_12: Volume mount must include SELinux ':z' label: {volumes}")

        # Verify host permissions on incoming dropzone
        self.assertTrue(
            os.access(self.INCOMING_DIR, os.R_OK | os.W_OK | os.X_OK),
            "T3_12: Incoming dropzone must be accessible by non-root host user"
        )

    # -------------------------------------------------------------------------
    # T3_13: Container Non-Root Output & Host Non-Dockerized Django Read/Unlink (F11 + F14)
    # -------------------------------------------------------------------------
    def test_t3_13_container_write_host_read_unlink(self):
        """T3_13: Files deposited in dropzone are read and deleted without elevated permissions."""
        xlsx_path = self.INCOMING_DIR / "t3_13_interchange.xlsx"
        create_valid_transaction_xlsx(xlsx_path)
        self.addCleanup(self._safe_unlink, xlsx_path)

        md_path = create_companion_instructions(xlsx_path)
        self.addCleanup(self._safe_unlink, md_path)

        # Host unprivileged read
        self.assertTrue(xlsx_path.exists())
        self.assertGreater(xlsx_path.stat().st_size, 500)
        self.assertTrue(md_path.exists())

        # Host unprivileged unlink
        xlsx_path.unlink()
        md_path.unlink()
        self.assertFalse(xlsx_path.exists(), "T3_13: Excel file unlinked cleanly")
        self.assertFalse(md_path.exists(), "T3_13: Companion markdown unlinked cleanly")

    # -------------------------------------------------------------------------
    # T3_14: Git Ignore Alignment & Media Storage Persistence Immunity (F3 + F9)
    # -------------------------------------------------------------------------
    def test_t3_14_media_storage_persistence_git_immunity(self):
        """T3_14: Dropping transaction spreadsheets into media/ leaves git status clean."""
        probes = [
            self.INCOMING_DIR / f".git_immunity_in_{i}.xlsx" for i in range(2)
        ] + [
            self.PROCESSED_DIR / f".git_immunity_pr_{i}.xlsx" for i in range(2)
        ]
        for p in probes:
            p.write_bytes(b"probe_payload")
            self.addCleanup(self._safe_unlink, p)

        code, out, _ = self.run_git_cmd(["status", "--porcelain", "media/spreadsheets/"])
        self.assertEqual(code, 0, "T3_14: git status must exit 0")
        for p in probes:
            self.assertNotIn(
                p.name,
                out,
                f"T3_14: Media dropzone file exposed in git status: {p.name}"
            )

    # -------------------------------------------------------------------------
    # T3_15: Root Symlink Ingestion & Host Management Command Access (F9 + F12 + F14)
    # -------------------------------------------------------------------------
    def test_t3_15_management_command_via_symlink(self):
        """T3_15: Path access via root symlink resolves to identical file content for CLI tools."""
        statement_file = self.INCOMING_DIR / "symlink_cmd_test.csv"
        create_valid_bank_statement_csv(statement_file)
        self.addCleanup(self._safe_unlink, statement_file)

        symlink_file = self.ROOT_SYMLINK / statement_file.name
        self.assertTrue(symlink_file.exists(), "T3_15: File must be reachable via symlink")

        # Compare content
        self.assertEqual(
            statement_file.read_bytes(),
            symlink_file.read_bytes(),
            "T3_15: Content read via symlink must match canonical content"
        )

    # -------------------------------------------------------------------------
    # T3_16: bot.sh Pre-Creation, Symlink Target Integrity, and Container Mount (F10 + F12 + F13)
    # -------------------------------------------------------------------------
    def test_t3_16_topology_integrity_drill(self):
        """T3_16: Dropzone symlink target matches compose host mount source exactly."""
        compose_data = self.parse_compose_file()
        volumes = compose_data.get("services", {}).get("dormitory-bot", {}).get("volumes", [])
        incoming_vols = [v for v in volumes if "incoming_spreadsheets" in v]
        self.assertTrue(len(incoming_vols) > 0, "T3_16: Missing incoming volume in compose")

        host_mount_part = incoming_vols[0].split(":")[0]
        resolved_mount = (self.BOT_DIR / host_mount_part).resolve()
        resolved_symlink = self.ROOT_SYMLINK.resolve()

        self.assertEqual(
            resolved_mount,
            resolved_symlink,
            f"T3_16: Container host mount ({resolved_mount}) != symlink destination ({resolved_symlink})"
        )
