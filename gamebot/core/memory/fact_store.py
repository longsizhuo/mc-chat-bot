"""Fact 存储：Subject-Predicate-Value 三元组持久化。

设计参考 Hermes Agent 的 MEMORY.md：所有结构化事实都放在这里，
统一管理，按 subject 维度聚合。

示例：
    Fact(subject="风格一", predicate="alias_to_op", value=40011, source="user:龙龙")
    Fact(subject="风格一", predicate="also_plays",  value=20005, source="user_note")
    Fact(subject="老黑",   predicate="alias_to_op", value=30008)

JSON 文件存储（少量数据下足够快）。后续可以无缝换成 SQLite 不动 API。
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def _now_iso() -> str:
    """当前 UTC 时间 ISO 8601 字符串。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_id() -> str:
    """新 fact_id（短 UUID 前 8 位，够本项目规模用）。"""
    return uuid.uuid4().hex[:8]


@dataclass
class Fact:
    """一条事实记录。

    subject + predicate 复合"键"，但允许多值（同 subject 同 predicate 可以有多条 value，
    例如"风格一 also_plays 20005" 和 "风格一 also_plays 40005" 并存）。
    """

    subject: str
    predicate: str
    value: Any
    source: str = "ai"                      # 来源：user:nickname / inferred / tool:xxx
    confidence: float = 1.0                 # 0-1，AI 推断时可以 < 1
    fact_id: str = field(default_factory=_new_id)
    added_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Fact:
        return cls(**d)


class FactStore:
    """JSON 持久化的 Fact 存储。线程安全。"""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._facts: dict[str, Fact] = {}  # fact_id → Fact
        self._load()

    # ---- 持久化 ----

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self._facts = {
                f["fact_id"]: Fact.from_dict(f) for f in raw.get("facts", [])
            }
        except (json.JSONDecodeError, OSError, KeyError, TypeError) as e:
            print(f"[FactStore] 加载失败，从空开始：{e}")
            self._facts = {}

    def _save(self) -> None:
        """原子写入：tmp 文件 → fsync → os.replace。

        防止进程崩溃 / 断电时 facts.json 部分写入变成无效 JSON 导致下次加载
        清零（群友档案瞬间归零的事故）。
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # 序列化：转 dict，按 added_at 排序（稳定输出方便 diff）
        facts_list = sorted(
            (f.to_dict() for f in self._facts.values()),
            key=lambda d: d["added_at"],
        )
        payload = json.dumps({"facts": facts_list}, ensure_ascii=False, indent=2)

        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        # 写 tmp + fsync 保证落盘
        with tmp_path.open("w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        # 原子 rename（POSIX 保证 same-filesystem 原子性）
        os.replace(tmp_path, self.path)

    # ---- CRUD ----

    def add(
        self,
        subject: str,
        predicate: str,
        value: Any,
        source: str = "ai",
        confidence: float = 1.0,
        dedupe: bool = True,
    ) -> Fact:
        """添加一条 fact。

        dedupe=True：如果已存在完全相同的 (subject, predicate, value) 则更新它的
        updated_at 而不是新增（避免噪声）。
        """
        with self._lock:
            if dedupe:
                for f in self._facts.values():
                    if (
                        f.subject == subject
                        and f.predicate == predicate
                        and f.value == value
                    ):
                        f.updated_at = _now_iso()
                        f.source = source
                        f.confidence = max(f.confidence, confidence)
                        self._save()
                        return f
            fact = Fact(
                subject=subject,
                predicate=predicate,
                value=value,
                source=source,
                confidence=confidence,
            )
            self._facts[fact.fact_id] = fact
            self._save()
            return fact

    def remove(self, fact_id: str) -> bool:
        with self._lock:
            if fact_id not in self._facts:
                return False
            del self._facts[fact_id]
            self._save()
            return True

    def remove_where(self, subject: Optional[str] = None,
                     predicate: Optional[str] = None,
                     value: Any = None) -> int:
        """按条件批量删除。返回删除条数。"""
        with self._lock:
            to_remove = [
                fid for fid, f in self._facts.items()
                if (subject is None or f.subject == subject)
                and (predicate is None or f.predicate == predicate)
                and (value is None or f.value == value)
            ]
            for fid in to_remove:
                del self._facts[fid]
            if to_remove:
                self._save()
            return len(to_remove)

    # ---- 查询 ----

    def get(self, fact_id: str) -> Optional[Fact]:
        with self._lock:
            return self._facts.get(fact_id)

    def all(self) -> list[Fact]:
        with self._lock:
            return list(self._facts.values())

    def by_subject(self, subject: str) -> list[Fact]:
        """关于某主体的所有事实。"""
        with self._lock:
            return [f for f in self._facts.values() if f.subject == subject]

    def by_predicate(self, predicate: str) -> list[Fact]:
        with self._lock:
            return [f for f in self._facts.values() if f.predicate == predicate]

    def find(
        self,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
        value: Any = None,
    ) -> list[Fact]:
        """组合查询。"""
        with self._lock:
            return [
                f for f in self._facts.values()
                if (subject is None or f.subject == subject)
                and (predicate is None or f.predicate == predicate)
                and (value is None or f.value == value)
            ]

    def subjects(self) -> set[str]:
        """所有出现过的 subject。"""
        with self._lock:
            return {f.subject for f in self._facts.values()}

    def __len__(self) -> int:
        with self._lock:
            return len(self._facts)
