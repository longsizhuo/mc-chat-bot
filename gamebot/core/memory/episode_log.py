"""Episode 时序事件流：每次对话/查询/重要变更都 append 一条。

设计参考 OpenClaw 的 "save conversations after each run" 思想。
append-only JSONL 文件，便于增量写入和 tail 读取。

事件类型示例：
    type=conversation, actors=[群友A], content="问了上把战绩"
    type=match,        actors=[龙龙, 老黑, 风格一], content="航天-绝密 全员撤离 +215万"
    type=alias_change, actors=[老黑], content="老黑 alias 改为牧羊人(30008)"
    type=tool_call,    actors=[bot], content="调 df_match 1"
"""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


@dataclass
class Episode:
    """一条时序事件。"""

    type: str                           # conversation / match / alias_change / tool_call / ...
    content: str                        # 一句话 summary（FTS 索引主要字段）
    actors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    episode_id: str = field(default_factory=_new_id)
    timestamp: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Episode:
        return cls(**d)


class EpisodeLog:
    """JSONL append-only 事件流。

    设计选择：
    - jsonl（每行一个 JSON 对象）而不是单个大 JSON，方便 append 不重写
    - 内存里也保留一份完整 list，启动时一次性 load（事件量大时再考虑分文件）
    - 加锁保证 thread safe
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._episodes: list[Episode] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            with self.path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        self._episodes.append(Episode.from_dict(d))
                    except (json.JSONDecodeError, TypeError, KeyError):
                        continue
        except OSError as e:
            print(f"[EpisodeLog] 加载失败：{e}")

    def append(
        self,
        type: str,
        content: str,
        actors: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Episode:
        ep = Episode(
            type=type,
            content=content,
            actors=actors or [],
            metadata=metadata or {},
        )
        with self._lock:
            self._episodes.append(ep)
            # append-only 写盘
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(ep.to_dict(), ensure_ascii=False) + "\n")
        return ep

    # ---- 查询 ----

    def all(self) -> list[Episode]:
        with self._lock:
            return list(self._episodes)

    def recent(
        self,
        n: int = 10,
        type: Optional[str] = None,
        actor: Optional[str] = None,
    ) -> list[Episode]:
        """最近 N 条事件（可按类型 / 涉及主体过滤）。倒序返回（新的在前）。"""
        with self._lock:
            filtered = [
                e for e in self._episodes
                if (type is None or e.type == type)
                and (actor is None or actor in e.actors)
            ]
        return list(reversed(filtered))[:n]

    def by_actor(self, actor: str, n: int = 20) -> list[Episode]:
        return self.recent(n=n, actor=actor)

    def by_type(self, type: str, n: int = 20) -> list[Episode]:
        return self.recent(n=n, type=type)

    def __len__(self) -> int:
        with self._lock:
            return len(self._episodes)
