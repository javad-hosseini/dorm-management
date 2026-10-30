import os
import shutil
import sqlite3
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
        Supports both .sqlite3, .db, and legacy .sql backups.
        """
        backup_dir = cls.get_backup_dir()
        valid_extensions = (".sqlite3", ".db", ".sql")
        files = []
        for entry in backup_dir.iterdir():
            if entry.is_file() and entry.name.startswith("backup_") and entry.name.endswith(valid_extensions):
                stat = entry.stat()
                files.append({
                    "name": entry.name,
                    "filename": entry.name,
                    "path": str(entry.resolve()),
                    "size_bytes": stat.st_size,
                    "size": cls.format_size(stat.st_size),
                    "mtime": stat.st_mtime,
                    "download_url": f"/dashboard/api/backup/download/{entry.name}/",
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
        When SQLite is active, creates a 100% consistent .sqlite3 database file.
        When PostgreSQL is active, uses pg_dump to produce .sql.
        Returns a dict with backup details.
        """
        backup_dir = cls.get_backup_dir()
        now = datetime.now()
        unix_ts = int(now.timestamp())
        timestamp_str = now.strftime("%Y-%m-%d_%H-%M-%S")

        db = settings.DATABASES.get("default", {})
        engine = db.get("ENGINE", "")
        dbname = db.get("NAME", "db.sqlite3")

        is_sqlite = "sqlite3" in engine or str(dbname).endswith((".sqlite3", ".db"))
        is_postgres = "postgresql" in engine

        if is_sqlite:
            ext = ".sqlite3"
        elif is_postgres:
            ext = ".sql"
        else:
            ext = ".sqlite3"

        filename = f"backup_{timestamp_str}_{unix_ts}{ext}"
        filepath = backup_dir / filename

        if is_sqlite:
            # Official SQLite online backup API via Django connection ensures
            # complete atomic snapshot both on disk (db.sqlite3) and in test memory databases
            from django.db import connection
            connection.ensure_connection()

            dest_conn = sqlite3.connect(str(filepath))
            try:
                with dest_conn:
                    connection.connection.backup(dest_conn)
            finally:
                dest_conn.close()

        elif is_postgres:
            host = db.get("HOST", "localhost") or "localhost"
            port = str(db.get("PORT", "5432") or "5432")
            user = db.get("USER", "postgres") or "postgres"
            password = str(db.get("PASSWORD", "") or "")
            pg_dump_bin = shutil.which("pg_dump")

            if pg_dump_bin:
                env = os.environ.copy()
                if password:
                    env["PGPASSWORD"] = password
                cmd = [
                    pg_dump_bin,
                    "-h", host,
                    "-p", port,
                    "-U", user,
                    "-d", str(dbname),
                    "-f", str(filepath)
                ]
                process = subprocess.run(cmd, env=env, capture_output=True, text=True)
                if process.returncode != 0:
                    raise RuntimeError(f"خطا در اجرای pg_dump: {process.stderr.strip() or process.stdout.strip()}")
            else:
                with open(filepath, "w", encoding="utf-8") as f:
                    call_command("dumpdata", stdout=f, indent=2, exclude=["contenttypes", "auth.permission"])
        else:
            with open(filepath, "w", encoding="utf-8") as f:
                call_command("dumpdata", stdout=f, indent=2, exclude=["contenttypes", "auth.permission"])

        if not filepath.exists() or filepath.stat().st_size == 0:
            raise RuntimeError("فایل پشتیبان ایجاد نشد یا خالی است.")

        file_stat = filepath.stat()
        file_size_formatted = cls.format_size(file_stat.st_size)

        # Apply rotation (keep up to MAX_BACKUPS)
        removed_files = cls.rotate_backups(cls.MAX_BACKUPS)
        remaining_backups = cls.list_backups()

        return {
            "filename": filename,
            "path": str(filepath.resolve()),
            "format": "sqlite3" if is_sqlite else "sql",
            "download_url": f"/dashboard/api/backup/download/{filename}/",
            "size": file_size_formatted,
            "size_bytes": file_stat.st_size,
            "created_at": timestamp_str,
            "timestamp": unix_ts,
            "removed_files": removed_files,
            "total_backups_count": len(remaining_backups)
        }
