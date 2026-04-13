"""Game-day based world backup system."""

import gzip
import os
import struct
import subprocess
import time
from pathlib import Path

from .config import Config


class DayBackup:
    def __init__(self, config: Config):
        self.config = config
        self.server_dir = Path(config.server_dir)
        self.world_dir = self.server_dir / "world"
        self.level_dat = self.world_dir / "level.dat"
        self.backup_dir = self.server_dir / config.backup.backup_dir
        self.state_file = self.backup_dir / ".last_day"
        self.check_interval = config.backup.check_interval
        self.max_backups = config.backup.max_backups

    def get_game_day(self) -> int | None:
        """Read game day from level.dat NBT data."""
        try:
            with gzip.open(self.level_dat, "rb") as f:
                data = f.read()
        except Exception as e:
            print(f"[MCBot] Cannot read level.dat: {e}")
            return None

        for i in range(len(data) - 10):
            if data[i] == 4:  # NBT Long tag
                name_len = struct.unpack(">H", data[i + 1 : i + 3])[0]
                if 0 < name_len < 50 and i + 3 + name_len + 8 <= len(data):
                    name = data[i + 3 : i + 3 + name_len]
                    if name == b"Time":
                        val = struct.unpack(
                            ">q", data[i + 3 + name_len : i + 3 + name_len + 8]
                        )[0]
                        return val // 24000
        return None

    def get_last_backed_up_day(self) -> int:
        try:
            return int(self.state_file.read_text().strip())
        except (FileNotFoundError, ValueError):
            return -1

    def save_last_backed_up_day(self, day: int):
        self.state_file.write_text(str(day))

    def do_backup(self, day: int):
        """Create a backup of the world directory."""
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        backup_name = f"world_day{day}_{timestamp}.tar.gz"
        backup_path = self.backup_dir / backup_name

        print(f"[MCBot] Backup: game day {day} - starting...")
        result = subprocess.run(
            ["tar", "-czf", str(backup_path), "-C", str(self.server_dir), "world"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            size_mb = backup_path.stat().st_size / (1024 * 1024)
            print(f"[MCBot] Backup done: {backup_name} ({size_mb:.1f}MB)")
            self.save_last_backed_up_day(day)
            self.cleanup()
        else:
            print(f"[MCBot] Backup failed: {result.stderr}")

    def cleanup(self):
        """Keep only the most recent backups."""
        backups = sorted(
            p for p in self.backup_dir.iterdir()
            if p.name.startswith("world_day") and p.name.endswith(".tar.gz")
        )
        while len(backups) > self.max_backups:
            old = backups.pop(0)
            old.unlink()
            print(f"[MCBot] Cleaned up old backup: {old.name}")

    def run(self):
        """Main backup loop."""
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        print(f"[MCBot] Backup system started (check every {self.check_interval}s, keep {self.max_backups})")

        last_day = self.get_last_backed_up_day()
        if last_day >= 0:
            print(f"[MCBot] Last backup: day {last_day}")

        while True:
            day = self.get_game_day()
            if day is not None and day > last_day:
                self.do_backup(day)
                last_day = day
            time.sleep(self.check_interval)
