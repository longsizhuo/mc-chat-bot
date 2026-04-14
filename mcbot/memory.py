"""Persistent per-player memory: chat history + long-term facts.

Chat history: rolling window of recent messages, persisted to disk so a bot
restart doesn't wipe context.

Facts: free-form notes the bot writes to itself via [CMD:remember <player> <fact>]
(player preferences, past builds, running jokes, promises). Always injected
into the system prompt when that player talks.
"""

import json
import threading
from pathlib import Path


class Memory:
    def __init__(self, memory_dir: str | Path, max_history: int, max_facts: int = 50):
        self.dir = Path(memory_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.history_dir = self.dir / "history"
        self.history_dir.mkdir(exist_ok=True)
        self.facts_file = self.dir / "facts.json"
        self.max_history = max_history
        self.max_facts = max_facts
        self._lock = threading.Lock()

        self._histories: dict[str, list[dict]] = {}
        self._facts: dict[str, list[str]] = self._load_facts()

    # ---------- history ----------

    def _history_path(self, player: str) -> Path:
        safe = "".join(c for c in player if c.isalnum() or c in "_-")
        return self.history_dir / f"{safe}.json"

    def get_history(self, player: str) -> list[dict]:
        if player in self._histories:
            return self._histories[player]
        path = self._history_path(player)
        if path.exists():
            try:
                self._histories[player] = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                self._histories[player] = []
        else:
            self._histories[player] = []
        return self._histories[player]

    def append_history(self, player: str, role: str, content: str) -> list[dict]:
        history = self.get_history(player)
        history.append({"role": role, "content": content})
        if len(history) > self.max_history:
            history[:] = history[-self.max_history:]
        self._save_history(player)
        return history

    def _save_history(self, player: str) -> None:
        with self._lock:
            try:
                self._history_path(player).write_text(
                    json.dumps(self._histories[player], ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception as e:
                print(f"[Memory] Failed to save history for {player}: {e}")

    # ---------- facts ----------

    def _load_facts(self) -> dict[str, list[str]]:
        if self.facts_file.exists():
            try:
                return json.loads(self.facts_file.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_facts(self) -> None:
        with self._lock:
            try:
                self.facts_file.write_text(
                    json.dumps(self._facts, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception as e:
                print(f"[Memory] Failed to save facts: {e}")

    def get_facts(self, player: str) -> list[str]:
        return self._facts.get(player, [])

    def add_fact(self, player: str, fact: str) -> bool:
        fact = fact.strip()
        if not fact:
            return False
        facts = self._facts.setdefault(player, [])
        if fact in facts:
            return False
        facts.append(fact)
        if len(facts) > self.max_facts:
            facts[:] = facts[-self.max_facts:]
        self._save_facts()
        return True

    def forget_fact(self, player: str, index_or_text: str) -> bool:
        facts = self._facts.get(player, [])
        if not facts:
            return False
        if index_or_text.isdigit():
            i = int(index_or_text)
            if 0 <= i < len(facts):
                facts.pop(i)
                self._save_facts()
                return True
            return False
        for i, f in enumerate(facts):
            if index_or_text in f:
                facts.pop(i)
                self._save_facts()
                return True
        return False
