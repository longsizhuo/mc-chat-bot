"""Player statistics persistence - saves to JSON file."""

import json
import time
from pathlib import Path
from threading import Lock


class PlayerStats:
    """Track and persist player statistics."""

    def __init__(self, data_dir: str):
        self.data_path = Path(data_dir) / "player_stats.json"
        self.lock = Lock()
        self.data = self._load()

    def _load(self) -> dict:
        if self.data_path.exists():
            try:
                return json.loads(self.data_path.read_text())
            except (json.JSONDecodeError, OSError):
                return {"players": {}, "server": {"total_deaths": 0, "total_joins": 0}}
        return {"players": {}, "server": {"total_deaths": 0, "total_joins": 0}}

    def _save(self):
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        self.data_path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2))

    def _get_player(self, name: str) -> dict:
        if name not in self.data["players"]:
            self.data["players"][name] = {
                "deaths": 0,
                "joins": 0,
                "playtime_minutes": 0,
                "advancements": [],
                "last_seen": 0,
                "first_seen": int(time.time()),
                "death_causes": {},
            }
        return self.data["players"][name]

    def on_join(self, player: str):
        with self.lock:
            p = self._get_player(player)
            p["joins"] += 1
            p["last_seen"] = int(time.time())
            p["_join_time"] = time.time()
            self.data["server"]["total_joins"] += 1
            self._save()

    def on_leave(self, player: str):
        with self.lock:
            p = self._get_player(player)
            join_time = p.pop("_join_time", None)
            if join_time:
                minutes = (time.time() - join_time) / 60
                p["playtime_minutes"] = round(p.get("playtime_minutes", 0) + minutes, 1)
            p["last_seen"] = int(time.time())
            self._save()

    def on_death(self, player: str, cause: str = "unknown"):
        with self.lock:
            p = self._get_player(player)
            p["deaths"] += 1
            causes = p.get("death_causes", {})
            causes[cause] = causes.get(cause, 0) + 1
            p["death_causes"] = causes
            self.data["server"]["total_deaths"] += 1
            self._save()

    def on_advancement(self, player: str, advancement: str):
        with self.lock:
            p = self._get_player(player)
            if advancement not in p["advancements"]:
                p["advancements"].append(advancement)
                self._save()

    def get_all(self) -> dict:
        """Return all stats data (for API)."""
        with self.lock:
            return json.loads(json.dumps(self.data))
