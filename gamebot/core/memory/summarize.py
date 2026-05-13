"""老 episodes 压缩 —— Phase 5。

episodes.jsonl 是 append-only，长期会无限增长。压缩策略：

1. **类型保留策略**：
   - type=conversation → 默认只留 30 天，老的删
   - type=match        → 永久保留（数据价值高）
   - type=alias_change → 永久保留
   - type=note_added   → 永久保留（重要变更）
   - type=tool_call    → 默认只留 7 天

2. **聚合 fact**（可选，LLM-based 留给 Phase 5.1）：
   把每周/每月的 conversation 按 actor 聚合成一条 fact，例如
   `Fact(subject="王博", predicate="recent_topics_2026W19", value=["战绩查询x3","密码x1"])`

本 Phase 实现 1（类型保留），LLM 聚合留接口。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from .episode_log import Episode, EpisodeLog


# 默认每种 episode 的保留天数（None = 永久）
DEFAULT_RETENTION = {
    "conversation": 30,
    "tool_call": 7,
    "match": None,
    "alias_change": None,
    "note_added": None,
    "alias_learn": None,
    "system": 60,
}


def _parse_iso(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


def prune_old_episodes(
    episode_log: EpisodeLog,
    retention_days: Optional[dict[str, Optional[int]]] = None,
    now: Optional[datetime] = None,
) -> dict:
    """按类型保留策略修剪老 episodes。

    重写 jsonl 文件（保留下来的 episodes）。返回统计字典。
    """
    retention = {**DEFAULT_RETENTION, **(retention_days or {})}
    now = now or datetime.now(timezone.utc)

    all_eps = episode_log.all()
    kept: list[Episode] = []
    pruned_count = 0
    pruned_by_type: dict[str, int] = {}

    for ep in all_eps:
        keep_days = retention.get(ep.type, None)  # 未知类型默认永久保留
        if keep_days is None:
            kept.append(ep)
            continue
        ts = _parse_iso(ep.timestamp)
        if ts is None:
            kept.append(ep)  # 时间戳坏了的保留（保守）
            continue
        # naive datetime fallback
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age = now - ts
        if age > timedelta(days=keep_days):
            pruned_count += 1
            pruned_by_type[ep.type] = pruned_by_type.get(ep.type, 0) + 1
        else:
            kept.append(ep)

    # 重写 jsonl
    episode_log.path.parent.mkdir(parents=True, exist_ok=True)
    with episode_log.path.open("w", encoding="utf-8") as fh:
        for ep in kept:
            fh.write(json.dumps(ep.to_dict(), ensure_ascii=False) + "\n")
    # 内存里也同步
    episode_log._episodes = kept

    return {
        "total_before": len(all_eps),
        "kept": len(kept),
        "pruned": pruned_count,
        "pruned_by_type": pruned_by_type,
    }


def summarize_into_facts(
    memory,
    actor: Optional[str] = None,
    days_back: int = 7,
) -> dict:
    """把最近 N 天某 actor 的 conversation 类 episodes 聚合成一条 weekly_topics fact。

    简版（无 LLM）：直接按 type 计数。LLM 聚合留给 Phase 5.1。
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    episodes = [
        e for e in memory.episodes.all()
        if (actor is None or actor in e.actors)
        and e.type in ("conversation", "tool_call")
    ]
    recent = []
    for e in episodes:
        ts = _parse_iso(e.timestamp)
        if ts is None:
            continue
        # naive datetime fallback：把无时区的 ts 当成 UTC
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts >= cutoff:
            recent.append(e)

    if not recent:
        return {"created": 0}

    summary = {
        "conversation_count": sum(1 for e in recent if e.type == "conversation"),
        "tool_call_count": sum(1 for e in recent if e.type == "tool_call"),
        "actors": sorted({a for e in recent for a in e.actors}),
    }
    iso_week = datetime.now(timezone.utc).strftime("%YW%V")
    subject = actor or "squad"
    fact = memory.remember(
        subject=subject,
        predicate=f"weekly_activity_{iso_week}",
        value=summary,
        source="auto_summary",
    )
    return {"created": 1, "fact_id": fact.fact_id, "summary": summary}
