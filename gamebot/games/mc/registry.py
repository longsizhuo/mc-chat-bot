"""Minecraft item/block registry — fuzzy lookup for the bot.

The registry data (data/registry.json) is dumped directly from the server
jar via `java -DbundlerMainClass=net.minecraft.data.Main -jar server.jar --reports`,
so every ID is guaranteed to exist in this exact MC version (26.1.2).
Refresh by re-running the dump after a server update.
"""

import json
from difflib import get_close_matches
from pathlib import Path


class Registry:
    def __init__(self, path: str | Path):
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        self.version: str = data.get("version", "unknown")
        self.items: list[str] = data.get("items", [])
        self.blocks: list[str] = data.get("blocks", [])
        self._items_set = set(self.items)
        self._blocks_set = set(self.blocks)

    def exists(self, identifier: str, kind: str = "any") -> bool:
        i = identifier.replace("minecraft:", "").strip()
        if kind in ("any", "item") and i in self._items_set:
            return True
        if kind in ("any", "block") and i in self._blocks_set:
            return True
        return False

    def find(self, query: str, kind: str = "any", limit: int = 12) -> list[str]:
        """Fuzzy-search IDs. Substring hits first, then close matches."""
        q = query.lower().replace("minecraft:", "").replace(" ", "_").strip()
        if not q:
            return []

        if kind == "item":
            pool = self.items
        elif kind == "block":
            pool = self.blocks
        else:
            pool = self.blocks + [i for i in self.items if i not in self._blocks_set]

        substring = [x for x in pool if q in x]
        if substring:
            substring.sort(key=lambda x: (len(x), x))
            return substring[:limit]

        return get_close_matches(q, pool, n=limit, cutoff=0.5)
