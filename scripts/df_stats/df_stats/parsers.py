"""raw JSON → 人话格式化。"""

from __future__ import annotations

from collections import Counter
from typing import Iterable

from .maps import map_name, operator_name, escape_reason_name


def _as_int(v, default: int = 0) -> int:
    """容错的 int 转换 —— 接口字段时而 int 时而 str。"""
    if v is None or v == "":
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return default


def format_match(rec: dict) -> str:
    """单场战绩 → 一行人话。"""
    map_id = rec.get("MapId", "?")
    reason = _as_int(rec.get("EscapeFailReason"))
    duration = _as_int(rec.get("DurationS"))
    kill_player = _as_int(rec.get("KillCount"))
    kill_player_ai = _as_int(rec.get("KillPlayerAICount"))
    kill_ai = _as_int(rec.get("KillAICount"))
    final_price = _as_int(rec.get("FinalPrice"))
    gained = _as_int(rec.get("flowCalGainedPrice"))
    op_id = _as_int(rec.get("ArmedForceId"))
    when = rec.get("dtEventTime", "")

    minutes, seconds = divmod(duration, 60)

    result = escape_reason_name(reason)
    map_label = map_name(map_id)
    op_label = operator_name(op_id) if op_id else "?"

    # 净收益用 +/- 标记
    net = f"{gained:+d}" if gained else "0"

    return (
        f"[{when}] {map_label} · {op_label} · {result} · "
        f"{minutes:02d}'{seconds:02d}\" · "
        f"杀人{kill_player} 杀AI玩家{kill_player_ai} 杀AI{kill_ai} · "
        f"带出{final_price} 净{net}"
    )


def summarize_records(records: Iterable[dict]) -> dict:
    """一批战绩的聚合统计。"""
    records = list(records)
    n = len(records)
    if n == 0:
        return {
            "total": 0,
            "summary_text": "（没有数据）",
        }

    success = sum(1 for r in records if _as_int(r.get("EscapeFailReason")) == 1)
    killed_by_player = sum(1 for r in records if _as_int(r.get("EscapeFailReason")) == 2)
    killed_by_ai = sum(1 for r in records if _as_int(r.get("EscapeFailReason")) == 3)

    total_kills = sum(_as_int(r.get("KillCount")) for r in records)
    total_kill_ai_players = sum(_as_int(r.get("KillPlayerAICount")) for r in records)
    total_kill_ai = sum(_as_int(r.get("KillAICount")) for r in records)
    total_gained = sum(_as_int(r.get("flowCalGainedPrice")) for r in records)
    total_carryout = sum(_as_int(r.get("FinalPrice")) for r in records)
    total_duration = sum(_as_int(r.get("DurationS")) for r in records)

    # 常用地图 / 常用干员
    map_counter = Counter(str(r.get("MapId", "?")) for r in records)
    op_counter = Counter(_as_int(r.get("ArmedForceId")) for r in records)

    top_maps = [
        (map_name(mid), cnt) for mid, cnt in map_counter.most_common(3)
    ]
    top_ops = [
        (operator_name(oid), cnt) for oid, cnt in op_counter.most_common(3) if oid
    ]

    avg_kill = total_kills / n
    avg_gained = total_gained / n
    success_rate = success / n * 100

    h, rem = divmod(total_duration, 3600)
    m = rem // 60

    lines = [
        f"📊 共 {n} 场，撤离成功 {success} 次（{success_rate:.0f}%）",
        f"💀 被真人击杀 {killed_by_player} 次 / 被 AI 击杀 {killed_by_ai} 次",
        f"🎯 总击败：玩家 {total_kills} / AI 玩家 {total_kill_ai_players} / AI {total_kill_ai}（场均 {avg_kill:.1f}）",
        f"💰 累计带出 {total_carryout:,} · 净收益 {total_gained:+,}（场均 {avg_gained:+,.0f}）",
        f"⏱️ 总时长 {h}h{m:02d}m",
    ]
    if top_maps:
        lines.append("🗺️ 常去地图：" + "、".join(f"{n}×{c}" for n, c in top_maps))
    if top_ops:
        lines.append("🪖 常用干员：" + "、".join(f"{n}×{c}" for n, c in top_ops))

    return {
        "total": n,
        "success": success,
        "success_rate": success_rate,
        "killed_by_player": killed_by_player,
        "killed_by_ai": killed_by_ai,
        "total_kills": total_kills,
        "total_kill_ai_players": total_kill_ai_players,
        "total_kill_ai": total_kill_ai,
        "total_gained": total_gained,
        "total_carryout": total_carryout,
        "total_duration_seconds": total_duration,
        "top_maps": top_maps,
        "top_operators": top_ops,
        "summary_text": "\n".join(lines),
    }
