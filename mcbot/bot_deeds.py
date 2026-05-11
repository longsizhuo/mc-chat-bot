"""小方工作日志 - 从 latest.log 扫 Rcon 命令执行记录，按玩家归类。

扫描 "[Rcon: ...]" 开头的日志行，识别 Gave/Teleported/Set/Summoned 等常见动作。
不需要单独持久化，每次请求实时计算。
"""

import re
from pathlib import Path
from typing import Optional


# RCON 指令执行后的回显格式：
# [HH:MM:SS] [Server thread/INFO]: [Rcon: Gave 64 [Diamond] to Abore]
# [HH:MM:SS] [Server thread/INFO]: [Rcon: Teleported longlong to 0.0, 64.0, 0.0]
RCON_RE = re.compile(r"\[(\d{2}):\d{2}:\d{2}\] \[Server thread/INFO\]: \[Rcon: (.+?)\]")


def _classify(action: str) -> tuple[str, Optional[str], str]:
    """把 RCON action 文本分类成 (动作类别, 玩家名, 简短描述)。
    玩家名可能为 None（全局操作）。"""

    # Gave X [Item] to Player
    m = re.match(r"Gave (\d+) \[([^\]]+)\] to (\w+)", action)
    if m:
        return ("give", m.group(3), f"给了 {m.group(3)} {m.group(1)} 个 {m.group(2)}")

    # Teleported Player to ...
    m = re.match(r"Teleported (\w+) to", action)
    if m:
        return ("tp", m.group(1), f"把 {m.group(1)} 传送走了")

    # Set Player's game mode to ...
    m = re.match(r"Set (\w+)'s game mode to (\w+)", action)
    if m:
        return ("gamemode", m.group(1), f"把 {m.group(1)} 切到 {m.group(2)} 模式")

    # Applied effect to Player
    m = re.match(r"Applied effect .+? to (\w+)", action)
    if m:
        return ("effect", m.group(1), f"给 {m.group(1)} 加了效果")

    # Set the weather to X
    m = re.match(r"Set the weather to (\w+)", action)
    if m:
        return ("weather", None, f"改天气为 {m.group(1)}")

    # Set the time to X
    m = re.match(r"Set the time to (\d+)", action)
    if m:
        return ("time", None, f"改时间到 {m.group(1)}")

    # Summoned X
    m = re.match(r"Summoned ", action)
    if m:
        return ("summon", None, action)

    # Enchant ...
    m = re.match(r"Applied enchantment .+? to (\w+)", action)
    if m:
        return ("enchant", m.group(1), f"给 {m.group(1)} 附魔")

    return ("other", None, action[:60])


def collect_today_deeds(latest_log: Path) -> dict:
    """扫描 latest.log 统计今日小方执行了什么。
    返回：{total, by_player, by_category, recent: [...]}"""
    if not latest_log.exists():
        return _empty()

    by_player: dict[str, int] = {}
    by_category: dict[str, int] = {}
    recent: list[dict] = []
    total = 0

    try:
        with open(latest_log, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                m = RCON_RE.search(line)
                if not m:
                    continue
                hour = m.group(1)
                action = m.group(2)
                cat, player, desc = _classify(action)
                total += 1
                by_category[cat] = by_category.get(cat, 0) + 1
                if player:
                    by_player[player] = by_player.get(player, 0) + 1
                recent.append({
                    "time": hour,
                    "category": cat,
                    "player": player,
                    "desc": desc,
                })
    except OSError:
        return _empty()

    # 只保留最近 20 条
    recent = recent[-20:]
    recent.reverse()  # 最新在前

    return {
        "total": total,
        "by_player": by_player,
        "by_category": by_category,
        "recent": recent,
    }


def _empty() -> dict:
    return {"total": 0, "by_player": {}, "by_category": {}, "recent": []}
