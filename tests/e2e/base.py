"""
tests/e2e/base.py
Base TestCase classes and inspection utilities for E2E opaque-box testing.
Zero external runtime dependencies: strictly Python standard library.
"""

import os
import re
import sys
import stat
import uuid
import shutil
import tempfile
import unittest
import subprocess
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any


class E2EBaseTestCase(unittest.TestCase):
    """Base class for all Dormitory Management E2E test cases."""

    # Canonical paths
    REPO_ROOT = Path(__file__).resolve().parent.parent.parent
    BOT_DIR = REPO_ROOT / "dormitory-telegram-bot"
    MEDIA_DIR = REPO_ROOT / "media"
    SPREADSHEETS_DIR = MEDIA_DIR / "spreadsheets"
    INCOMING_DIR = SPREADSHEETS_DIR / "incoming"
    PROCESSED_DIR = SPREADSHEETS_DIR / "processed"
    FAILED_DIR = SPREADSHEETS_DIR / "failed"
    ROOT_SYMLINK = REPO_ROOT / "incoming_spreadsheets"
    COMPOSE_FILE = BOT_DIR / "docker-compose.yml"
    BOT_SCRIPT = BOT_DIR / "bot.sh"
    DJANGO_MANAGE = REPO_ROOT / "manage.py"
    SIBLING_DIR = REPO_ROOT.parent / "dormitory-telegram-bot"

    # -------------------------------------------------------------------------
    # Filesystem & POSIX Custom Assertions
    # -------------------------------------------------------------------------

    def assertPathExists(self, path: Path, msg: Optional[str] = None):
        """Asserts that a file or directory exists."""
        p = Path(path)
        self.assertTrue(p.exists(), msg or f"Expected path to exist: {p}")

    def assertPathDoesNotExist(self, path: Path, msg: Optional[str] = None):
        """Asserts that a file or directory does not exist."""
        p = Path(path)
        self.assertFalse(p.exists(), msg or f"Expected path NOT to exist: {p}")

    def assertSymlinkPointsTo(self, symlink_path: Path, expected_target: Path):
        """Asserts that symlink exists and points to expected target (resolving relative paths)."""
        p = Path(symlink_path)
        self.assertTrue(p.is_symlink(), f"Path is not a symbolic link: {p}")
        resolved = p.resolve()
        expected = Path(expected_target).resolve()
        self.assertEqual(
            resolved,
            expected,
            f"Symlink target mismatch: {resolved} != {expected} (raw link: {os.readlink(str(p))})"
        )

    def assertFileMode(self, path: Path, expected_mode: int):
        """Asserts file permission mode bits (e.g., 0o644, 0o755)."""
        p = Path(path)
        self.assertPathExists(p)
        actual_mode = stat.S_IMODE(p.stat().st_mode)
        self.assertEqual(
            oct(actual_mode),
            oct(expected_mode),
            f"Mode mismatch for {p}: {oct(actual_mode)} != {oct(expected_mode)}"
        )

    def assertOwnership(self, path: Path, uid: int = 1000, gid: int = 1000):
        """Asserts file or directory POSIX UID and GID ownership."""
        p = Path(path)
        self.assertPathExists(p)
        st = p.stat()
        self.assertEqual(st.st_uid, uid, f"UID mismatch for {p}: {st.st_uid} != {uid}")
        self.assertEqual(st.st_gid, gid, f"GID mismatch for {p}: {st.st_gid} != {gid}")

    def assertGitTracked(self, rel_path: str):
        """Asserts that a file path is tracked in the Git repository."""
        self.assertTrue(
            self.is_git_tracked(rel_path),
            f"File is not tracked in Git index: {rel_path}"
        )

    def assertGitNotTracked(self, rel_path: str):
        """Asserts that a file path is NOT tracked in the Git repository."""
        self.assertFalse(
            self.is_git_tracked(rel_path),
            f"File is unexpectedly tracked in Git index: {rel_path}"
        )

    # -------------------------------------------------------------------------
    # Subprocess & Shell Helpers
    # -------------------------------------------------------------------------

    def safe_run(
        self,
        cmd: List[str],
        cwd: Optional[Path] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: int = 30
    ) -> Tuple[int, str, str]:
        """Safely executes a subprocess command capturing returncode, stdout, and stderr."""
        target_cwd = str(cwd or self.REPO_ROOT)
        run_env = os.environ.copy()
        if env:
            run_env.update(env)
        # Disable git credential terminal prompt to prevent blocking in tests
        run_env["GIT_TERMINAL_PROMPT"] = "0"
        try:
            proc = subprocess.run(
                cmd,
                cwd=target_cwd,
                env=run_env,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as exc:
            return -1, exc.stdout or "", f"Command timed out after {timeout}s: {exc}"
        except Exception as exc:
            return -1, "", f"Execution error: {exc}"

    # -------------------------------------------------------------------------
    # Git Inspection Helpers
    # -------------------------------------------------------------------------

    def run_git_cmd(self, args: List[str], cwd: Optional[Path] = None) -> Tuple[int, str, str]:
        """Runs git commands in the repository root or specified cwd."""
        return self.safe_run(["git"] + args, cwd=cwd or self.REPO_ROOT)

    def get_git_config_all(self, key: str, cwd: Optional[Path] = None) -> List[str]:
        """Returns all configuration values for a given git config key."""
        code, out, _ = self.run_git_cmd(["config", "--get-all", key], cwd=cwd)
        if code != 0:
            return []
        return [line.strip() for line in out.splitlines() if line.strip()]

    def get_git_push_urls(self, remote: str = "origin") -> List[str]:
        """Returns all configured push URLs for a remote."""
        code, out, _ = self.run_git_cmd(["remote", "get-url", "--all", "--push", remote])
        if code == 0:
            return [line.strip() for line in out.splitlines() if line.strip()]
        # Fallback to config inspection
        return self.get_git_config_all(f"remote.{remote}.pushurl")

    def is_git_tracked(self, rel_path: str) -> bool:
        """Checks if a relative path is tracked in the Git index."""
        code, _, _ = self.run_git_cmd(["ls-files", "--error-unmatch", rel_path])
        return code == 0

    def get_tracked_files(self, prefix: str = "") -> List[str]:
        """Returns all tracked files matching prefix."""
        args = ["ls-files"]
        if prefix:
            args.append(prefix)
        code, out, _ = self.run_git_cmd(args)
        if code != 0:
            return []
        return [line.strip() for line in out.splitlines() if line.strip()]

    def git_check_ignore(self, path: str) -> Tuple[bool, str]:
        """Checks if a path is ignored by Git, returning (is_ignored, source_rule)."""
        code, out, err = self.run_git_cmd(["check-ignore", "-v", path])
        if code == 0:
            return True, out.strip()
        return False, err.strip()

    def git_push_dry_run(self, remote: str = "origin", branch: str = "main") -> Tuple[int, str, str]:
        """Executes non-destructive dry-run push."""
        return self.run_git_cmd(["push", remote, branch, "--dry-run"])

    # -------------------------------------------------------------------------
    # SSH Inspection Helpers
    # -------------------------------------------------------------------------

    def verify_ssh_handshake(
        self,
        host: str,
        port: int = 22,
        user: str = "git",
        timeout: int = 5
    ) -> Tuple[int, str, str]:
        """Tests SSH handshake without password prompts using BatchMode=yes."""
        cmd = [
            "ssh",
            "-T",
            "-p", str(port),
            "-o", "BatchMode=yes",
            "-o", f"ConnectTimeout={timeout}",
            "-o", "StrictHostKeyChecking=accept-new",
            f"{user}@{host}"
        ]
        return self.safe_run(cmd, timeout=timeout + 2)

    # -------------------------------------------------------------------------
    # Docker Compose Parser Helper (Zero Dependency)
    # -------------------------------------------------------------------------

    def parse_compose_file(self, path: Optional[Path] = None) -> Dict[str, Any]:
        """
        Parses docker-compose.yml extracting services, volumes, user, and network_mode.
        Uses regex fallback if PyYAML is not installed.
        """
        compose_path = Path(path or self.COMPOSE_FILE)
        if not compose_path.exists():
            return {}

        content = compose_path.read_text(encoding="utf-8")

        # Try pyyaml if available
        try:
            import yaml
            return yaml.safe_load(content) or {}
        except ImportError:
            pass

        # Regex fallback parser
        data: Dict[str, Any] = {"services": {}}
        current_service = None
        in_volumes = False
        volumes_list = []

        for line in content.splitlines():
            # Check service block (indent 2)
            svc_match = re.match(r"^ {2}([a-zA-Z0-9_-]+):", line)
            if svc_match:
                if current_service and in_volumes:
                    data["services"][current_service]["volumes"] = volumes_list
                current_service = svc_match.group(1)
                data["services"][current_service] = {"volumes": []}
                in_volumes = False
                volumes_list = []
                continue

            if not current_service:
                continue

            # Check user directive
            user_match = re.match(r"^ {4}user:\s*[\"']?([^\"'#\n]+)[\"']?", line)
            if user_match:
                data["services"][current_service]["user"] = user_match.group(1).strip()
                continue

            # Check network_mode
            net_match = re.match(r"^ {4}network_mode:\s*[\"']?([^\"'#\n]+)[\"']?", line)
            if net_match:
                data["services"][current_service]["network_mode"] = net_match.group(1).strip()
                continue

            # Check volumes block
            if re.match(r"^ {4}volumes:\s*$", line):
                in_volumes = True
                volumes_list = []
                continue

            if in_volumes:
                vol_item = re.match(r"^ {6}-\s*[\"']?([^\"'#\n]+)[\"']?", line)
                if vol_item:
                    volumes_list.append(vol_item.group(1).strip())
                elif re.match(r"^ {4}[a-zA-Z0-9_-]+:", line):
                    # Next property
                    data["services"][current_service]["volumes"] = volumes_list
                    in_volumes = False

        if current_service and in_volumes:
            data["services"][current_service]["volumes"] = volumes_list

        return data

    # -------------------------------------------------------------------------
    # Dropzone & Canary Isolation Helpers
    # -------------------------------------------------------------------------

    def create_canary_file(
        self,
        directory: Path,
        filename: Optional[str] = None,
        content: str = "canary_test_probe"
    ) -> Path:
        """
        Creates a uniquely named canary file in target directory and registers
        its guaranteed deletion in addCleanup.
        """
        target_dir = Path(directory)
        target_dir.mkdir(parents=True, exist_ok=True)
        name = filename or f".canary_test_{uuid.uuid4().hex[:8]}.tmp"
        canary_path = target_dir / name
        canary_path.write_text(content, encoding="utf-8")

        self.addCleanup(self._safe_unlink, canary_path)
        return canary_path

    def _safe_unlink(self, path: Path):
        """Safely unlinks a file or directory tree if it exists."""
        p = Path(path)
        try:
            if p.is_symlink() or p.is_file():
                p.unlink(missing_ok=True)
            elif p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
        except Exception:
            pass


class SandboxTestCase(E2EBaseTestCase):
    """Base class for tests requiring an isolated temporary filesystem or simulated repository."""

    def setUp(self):
        super().setUp()
        self._temp_dir_obj = tempfile.TemporaryDirectory()
        self.sandbox_path = Path(self._temp_dir_obj.name)
        self.addCleanup(self._temp_dir_obj.cleanup)

    def init_sandbox_git_repo(self) -> Path:
        """Initializes a clean Git repository inside the sandbox."""
        repo_dir = self.sandbox_path / "test_repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        self.safe_run(["git", "init", "-b", "main"], cwd=repo_dir)
        self.safe_run(["git", "config", "user.name", "E2E Tester"], cwd=repo_dir)
        self.safe_run(["git", "config", "user.email", "tester@dorm.local"], cwd=repo_dir)
        return repo_dir

    def create_sandbox_dropzone(self) -> Tuple[Path, Path, Path, Path]:
        """Creates an isolated media/spreadsheets hierarchy inside the sandbox."""
        base = self.sandbox_path / "media" / "spreadsheets"
        incoming = base / "incoming"
        processed = base / "processed"
        failed = base / "failed"
        for d in (incoming, processed, failed):
            d.mkdir(parents=True, exist_ok=True)
            (d / ".gitkeep").touch()
        symlink = self.sandbox_path / "incoming_spreadsheets"
        symlink.symlink_to(incoming, target_is_directory=True)
        return incoming, processed, failed, symlink
