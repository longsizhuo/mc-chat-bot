"""小方本周悬案 - 每周三 19:00 推送。

从日志里扫描"反常数据点"，生成一个没答案的悬案丢到 QQ 群让玩家自己讨论。
知情的人跳出来解释，不知情的人进游戏去看。

设计要点：
- 不给答案，不下结论
- 数据完全来自日志，零玩家配置
- AI 包装成神秘语气，但不装神棍

可检测的反常类型：
1. 某玩家同一死因反复 ≥ 3 次（ObsessiveDeath）
2. 30 分钟内某玩家死 ≥ 3 次（Streak）
3. 凌晨 0-4 点有人在线（NightOwl）
4. 某玩家某天登录 ≥ 5 次（Rejoin）
5. 本周只死一次但死得特别奇葩（Unique）
"""

import gzip
import re
import time
import threading
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Callable


CST = timezone(timedelta(hours=8))

LOG_DATE_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2})")
JOIN_RE = re.compile(r"\[(\d{2}):(\d{2}):\d{2}\] \[Server thread/INFO\]: (\w+) joined the game")
DEATH_RE = re.compile(
    r"\[(\d{2}):(\d{2}):\d{2}\] \[Server thread/INFO\]: (\w+) "
    r"(was slain by[^\n]+|drowned|fell[^\n]*|burned to death|"
    r"was blown up by[^\n]+|walked into[^\n]+|tried to swim in lava[^\n]*|"
    r"withered away|starved to death|suffocated in a wall|"
    r"was killed by[^\n]+|died|was shot by[^\n]+)"
)

MYSTERY_SYSTEM_PROMPT = """你是小方，一个 Minecraft 服务器的 AI 助手。
你要基于一个真实的反常数据点，在 QQ 群里发一条"悬案"——提出一个没答案的问题。

要求：
- 神秘语气，但不装神棍
- 2-3 句话，精准扔出现象，不给答案，不下结论
- 结尾抛问题给群里，引玩家自己讨论（"有人知道吗""谁能解释""我不想下结论"）
- 禁用"据说""传言""相传"这种腔
- 允许带一点调侃色彩

示例：
- "本周 XX 死了 5 次，都是被岩浆送走的。我不想下结论，但有人愿意告诉他水在哪吗？"
- "昨晚 3 点 XX 还在线。我不会问他为什么，但我有点担心。"
- "XX 本周上下线 9 次，平均每次在线 4 分钟。是在躲谁？"
"""

MYSTERY_USER_TEMPLATE = """这周服务器的一个反常数据点：

{anomaly_description}

请以小方身份发一条悬案（2-3 句话），抛问题，不给答案。"""


class WeeklyMystery:
    """每周三晚 19:00 扫描本周日志，找反常点发悬案。"""

    def __init__(
        self,
        logs_dir: str,
        ai_provider,
        send_to_qq: Optional[Callable[[str], None]] = None,
        push_hour: int = 19,
    ):
        self.logs_dir = Path(logs_dir)
        self.ai = ai_provider
        self.send_to_qq = send_to_qq
        self.push_hour = push_hour
        self._last_push_week: Optional[int] = None

    # ========== 日志扫描 ==========

    def _iter_recent_lines(self, days: int = 7):
        """迭代最近 N 天的日志行，yield (date_str, line)。"""
        if not self.logs_dir.exists():
            return
        cutoff = time.time() - days * 86400
        today = datetime.now(CST).strftime("%Y-%m-%d")
        for lf in sorted(self.logs_dir.iterdir()):
            try:
                if lf.stat().st_mtime < cutoff:
                    continue
                date_match = LOG_DATE_PATTERN.match(lf.name)
                date_str = date_match.group(1) if date_match else today
                opener = gzip.open if lf.suffix == ".gz" else open
                if not (lf.suffix == ".gz" or lf.name.endswith(".log")):
                    continue
                with opener(lf, "rt", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        yield date_str, line
            except (OSError, EOFError):
                continue

    def _detect_anomalies(self) -> list[str]:
        """返回本周可用的反常描述列表，每条一个字符串。"""
        # 收集数据
        joins_by_player_day: dict[tuple[str, str], int] = defaultdict(int)
        deaths_by_player: dict[str, list[tuple[str, str, str]]] = defaultdict(list)  # (date, time, cause)
        night_activity: dict[str, int] = defaultdict(int)  # 0-4 点活动次数

        for date_str, line in self._iter_recent_lines(days=7):
            # Join
            m = JOIN_RE.search(line)
            if m:
                hour = int(m.group(1))
                player = m.group(3)
                joins_by_player_day[(player, date_str)] += 1
                if 0 <= hour < 4:
                    night_activity[player] += 1
                continue
            # Death
            m = DEATH_RE.search(line)
            if m:
                hour = int(m.group(1))
                minute = int(m.group(2))
                player = m.group(3)
                cause = m.group(4).strip()
                deaths_by_player[player].append((date_str, f"{hour:02d}:{minute:02d}", cause))
                if 0 <= hour < 4:
                    night_activity[player] += 1

        anomalies: list[str] = []

        # 类型 1：重复同类死因（≥3 次）
        for player, events in deaths_by_player.items():
            cause_counter: dict[str, int] = defaultdict(int)
            for _, _, cause in events:
                # 简化死因分类：取关键词
                key = self._simplify_cause(cause)
                cause_counter[key] += 1
            for key, cnt in cause_counter.items():
                if cnt >= 3:
                    anomalies.append(
                        f"[反复受难] 本周 {player} 死了 {cnt} 次都是同一种死法：{key}。"
                    )

        # 类型 2：单日登录 ≥ 5 次
        for (player, day), cnt in joins_by_player_day.items():
            if cnt >= 5:
                anomalies.append(
                    f"[反复上下线] {day} 这天 {player} 上下线 {cnt} 次，平均间隔很短。"
                )

        # 类型 3：凌晨活动 ≥ 5 次
        for player, cnt in night_activity.items():
            if cnt >= 5:
                anomalies.append(
                    f"[夜猫子] 本周 {player} 在凌晨 0-4 点共 {cnt} 次活动（登录或死亡）。"
                )

        # 类型 4：连击死亡（30 分钟内 ≥ 3 次）
        for player, events in deaths_by_player.items():
            events_sorted = sorted(events)  # 按 date+time 排
            for i in range(len(events_sorted) - 2):
                d1, t1, _ = events_sorted[i]
                d3, t3, _ = events_sorted[i + 2]
                if d1 == d3:
                    # 同一天，看时间差
                    h1, m1 = [int(x) for x in t1.split(":")]
                    h3, m3 = [int(x) for x in t3.split(":")]
                    diff = (h3 - h1) * 60 + (m3 - m1)
                    if 0 < diff <= 30:
                        anomalies.append(
                            f"[连环惨案] {d1} 当天 {player} 在 30 分钟内连续死了 3 次以上。"
                        )
                        break  # 同一玩家只报一次

        return anomalies

    def _simplify_cause(self, cause: str) -> str:
        """把死亡原因归类成中文简短标签。"""
        if "lava" in cause:
            return "跳岩浆"
        if "drowned" in cause:
            return "溺水"
        if "fell" in cause or "hit the ground" in cause:
            return "摔死"
        if "burned" in cause or "in flames" in cause:
            return "烧死"
        if "blown up" in cause:
            return "被炸死"
        if "slain" in cause or "killed" in cause:
            return "被怪物击杀"
        if "shot" in cause:
            return "被射杀"
        if "walked into" in cause:
            if "cactus" in cause:
                return "撞仙人掌"
            return "触碰危险物"
        if "starved" in cause:
            return "饿死"
        if "suffocated" in cause:
            return "被方块闷死"
        return cause[:20]

    # ========== 推送 ==========

    def push_mystery(self):
        anomalies = self._detect_anomalies()
        if not anomalies:
            print("[Mystery] 本周无反常数据，跳过")
            return

        # 随机挑一条（import random 在顶部会更干净，但这里小改动）
        import random
        picked = random.choice(anomalies)
        print(f"[Mystery] 选中反常点：{picked}")

        try:
            reply = self.ai.chat(
                [{"role": "user", "content": MYSTERY_USER_TEMPLATE.format(
                    anomaly_description=picked,
                )}],
                MYSTERY_SYSTEM_PROMPT,
            )
        except Exception as e:
            print(f"[Mystery] AI 生成失败: {e}")
            return
        if not reply:
            return

        msg = f"🕵️ 小方本周悬案\n\n{reply.strip()}"
        print(f"[Mystery] 推送:\n{msg}")
        if self.send_to_qq:
            self.send_to_qq(msg)

    def _scheduler_loop(self):
        """每分钟检查，周三 push_hour 点触发。"""
        while True:
            now = datetime.now(CST)
            week = now.isocalendar()[1]
            # 周三 = isoweekday() == 3
            if (
                now.isoweekday() == 3
                and now.hour == self.push_hour
                and self._last_push_week != week
            ):
                self._last_push_week = week
                try:
                    self.push_mystery()
                except Exception as e:
                    print(f"[Mystery] 推送出错: {e}")
            time.sleep(60)

    def start(self):
        t = threading.Thread(target=self._scheduler_loop, daemon=True)
        t.start()
        print(f"[Mystery] 本周悬案定时器已启动（周三 {self.push_hour}:00 推送）")
