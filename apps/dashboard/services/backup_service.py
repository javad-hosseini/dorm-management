import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from django.conf import settings
from django.core.management import call_command


class BackupService:
    BACKUP_DIR_NAME = "db-backups"
    MAX_BACKUPS = 5

    @classmethod
    def get_backup_dir(cls) -> Path:
        """Return the absolute path to db-backups directory in project root and ensure it exists."""
        backup_dir = Path(settings.BASE_DIR) / cls.BACKUP_DIR_NAME
        backup_dir.mkdir(parents=True, exist_ok=True)
        return backup_dir

    @classmethod
    def format_size(cls, size_in_bytes: int) -> str:
        """Format bytes to human-readable size string."""
        for unit in ["B", "KB", "MB", "GB"]:
            if size_in_bytes < 1024.0:
                return f"{size_in_bytes:.1f} {unit}"
            size_in_bytes /= 1024.0
        return f"{size_in_bytes:.1f} TB"

    @classmethod
    def list_backups(cls) -> list:
        """
        List all backup files in db-backups, sorted from oldest to newest by modification time.
        """
        backup_dir = cls.get_backup_dir()
        files = []
        for entry in backup_dir.iterdir():
            if entry.is_file() and entry.name.startswith("backup_") and entry.name.endswith(".sql"):
                stat = entry.stat()
                files.append({
                    "name": entry.name,
                    "path": str(entry.resolve()),
                    "size_bytes": stat.st_size,
                    "size": cls.format_size(stat.st_size),
                    "mtime": stat.st_mtime,
                    "created_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                })
        # Sort oldest first
        files.sort(key=lambda x: x["mtime"])
        return files

    @classmethod
    def rotate_backups(cls, max_files: int = None) -> list:
        """
        Ensure at most max_files are kept in db-backups.
        If file count exceeds max_files, delete the oldest files.
        Returns the list of removed filenames.
        """
        if max_files is None:
            max_files = cls.MAX_BACKUPS

        backups = cls.list_backups()
        removed = []
        while len(backups) > max_files:
            oldest = backups.pop(0)
            try:
                if os.path.exists(oldest["path"]):
                    os.remove(oldest["path"])
                removed.append(oldest["name"])
            except OSError:
                pass
        return removed

    @classmethod
    def create_backup(cls) -> dict:
        """
        Create a new database backup, save to db-backups, and apply rotation policy.
        Returns a dict with backup details.
        """
        backup_dir = cls.get_backup_dir()
        now = datetime.now()
        unix_ts = int(now.timestamp())
        timestamp_str = now.strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"backup_{timestamp_str}_{unix_ts}.sql"
        filepath = backup_dir / filename

        db = settings.DATABASES.get("default", {})
        engine = db.get("ENGINE", "")
        host = db.get("HOST", "localhost") or "localhost"
        port = str(db.get("PORT", "5432") or "5432")
        user = db.get("USER", "postgres") or "postgres"
        password = str(db.get("PASSWORD", "") or "")
        dbname = db.get("NAME", "dormitory_db")

        # Preferred: pg_dump for PostgreSQL
        pg_dump_bin = shutil.which("pg_dump")
        is_postgres = "postgresql" in engine

        if is_postgres and pg_dump_bin:
            env = os.environ.copy()
            if password:
                env["PGPASSWORD"] = password
            cmd = [
                pg_dump_bin,
                "-h", host,
                "-p", port,
                "-U", user,
                "-d", dbname,
                "-f", str(filepath)
            ]
            process = subprocess.run(cmd, env=env, capture_output=True, text=True)
            if process.returncode != 0:
                raise RuntimeError(f"خطا در اجرای pg_dump: {process.stderr.strip() or process.stdout.strip()}")
        else:
            # Fallback to Django dumpdata if pg_dump not available or another db engine is active
            with open(filepath, "w", encoding="utf-8") as f:
                call_command("dumpdata", stdout=f, indent=2, exclude=["contenttypes", "auth.permission"])

        if not filepath.exists() or filepath.stat().st_size == 0:
            raise RuntimeError("فایل پشتیبان ایجاد نشد یا خالی است.")

        file_stat = filepath.stat()
        file_size_formatted = cls.format_size(file_stat.st_size)

        # Apply rotation (keep up to 5)
        removed_files = cls.rotate_backups(cls.MAX_BACKUPS)
        remaining_backups = cls.list_backups()

        return {
            "filename": filename,
            "path": str(filepath.resolve()),
            "size": file_size_formatted,
            "size_bytes": file_stat.st_size,
            "created_at": timestamp_str,
            "timestamp": unix_ts,
            "removed_files": removed_files,
            "total_backups_count": len(remaining_backups)
        }
