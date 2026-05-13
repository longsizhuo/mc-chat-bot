"""今日服务器快照 - 扫描 latest.log 统计今天的事件。

输出字段：
- chats: 今日聊天条数
- joins: 今日不同玩家 join 次数
- deaths: 今日死亡次数
- unique_players: 今日出现过的玩家名集合
- hourly: 24 小时每小时的活动热度（join + chat + death 之和）

只扫 latest.log 一个文件。MC 每天凌晨滚动一次，所以 latest.log 基本就是"今天"。
"""

import re
from pathlib import Path
from typing import Optional


CHAT_RE = re.compile(r"\[(\d{2}):\d{2}:\d{2}\] \[Server thread/INFO\]: (?:\[Not Secure\] )?<(\w+)> ")
JOIN_RE = re.compile(r"\[(\d{2}):\d{2}:\d{2}\] \[Server thread/INFO\]: (\w+) joined the game")
DEATH_RE = re.compile(
    r"\[(\d{2}):\d{2}:\d{2}\] \[Server thread/INFO\]: (\w+) "
    r"(?:was slain|drowned|fell|burned|was blown|walked into|tried to swim|"
    r"withered|starved|suffocated|was killed|died|was shot)"
)


def collect_today(latest_log_path: Path) -> dict:
    if not latest_log_path.exists():
        return _empty()

    chats = 0
    joins = 0
    deaths = 0
    unique_players: set[str] = set()
    hourly = [0] * 24

    try:
        with open(latest_log_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                mc = CHAT_RE.search(line)
                if mc:
                    hour = int(mc.group(1))
                    player = mc.group(2)
                    # 过滤小方自己和 QQ 桥接的消息
                    if player not in ("小方", "bot", "Server"):
                        chats += 1
                        unique_players.add(player)
                        hourly[hour] += 1
                    continue

                mj = JOIN_RE.search(line)
                if mj:
                    hour = int(mj.group(1))
                    player = mj.group(2)
                    joins += 1
                    unique_players.add(player)
                    hourly[hour] += 1
                    continue

                md = DEATH_RE.search(line)
                if md:
                    hour = int(md.group(1))
                    player = md.group(2)
                    deaths += 1
                    unique_players.add(player)
                    hourly[hour] += 1
    except OSError:
        return _empty()

    return {
        "chats": chats,
        "joins": joins,
        "deaths": deaths,
        "unique_players": sorted(unique_players),
        "hourly": hourly,
    }


def _empty() -> dict:
    return {
        "chats": 0,
        "joins": 0,
        "deaths": 0,
        "unique_players": [],
        "hourly": [0] * 24,
    }
