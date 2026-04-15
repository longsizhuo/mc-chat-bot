"""小方日记 - 每周日晚 10 点推送到 QQ 群。

用小方（bot）第一人称温情视角，把这周服务器发生的事串成一篇 100 字左右的日记。
定位：不是古风史诗，不是游戏主播，是"你们家的 AI 管家给这帮人写的周记"。

替代原 chronicle.py（古风史诗过于对外宣传腔）。
"""

import gzip
import json
import re
import time
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Callable


# 服务器跑 UTC，推送按北京时间
CST = timezone(timedelta(hours=8))

# 日志文件名日期前缀，用于按时间排序事件
LOG_DATE_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2})")

# 小方第一人称 prompt - 朋友小服的温情管家语气
DIARY_SYSTEM_PROMPT = """你是小方，一个 Minecraft 服务器的 AI 助手。
你要写一篇本周的日记，记录这几个朋友在服务器里做的事。

语气要求：
- 第一人称"我"，你是观察者，也是参与者（偶尔插一句自己的评论）
- 像朋友给朋友写的日记，不是对外宣传，不是古风史诗
- 不装文艺腔，不用"英灵归天"、"勇士"这种词
- 朴实，带一点温度和幽默。可以点名某个玩家做了什么，但不要羞辱
- 可以吐槽、可以感动、可以无奈，但语气是熟人之间的
- 100-150 字，不要废话，不要强行押韵
- 结尾一句话留点余味，不用格言，不用"期待下周"的空话
- 禁用词：勇士、英灵、传奇、战绩、壮举、史诗、荣耀、大陆"""

DIARY_USER_TEMPLATE = """本周服务器发生的事（按时间顺序）：

{events_text}

请以小方的身份写一篇本周日记（100-150 字），朴实有温度，点名提到几个玩家做的具体事。"""

# 抽取事件用的正则
CHAT_RE = re.compile(
    r"\[Server thread/INFO\]: (?:\[Not Secure\] )?<(\w+)> (.+)"
)
JOIN_RE = re.compile(r"\[Server thread/INFO\]: (\w+) joined the game")
DEATH_RE = re.compile(
    r"\[Server thread/INFO\]: (\w+) "
    r"(was slain by[^\n]+|drowned|fell[^\n]*|burned to death|"
    r"was blown up by[^\n]+|walked into[^\n]+|tried to swim in lava[^\n]*|"
    r"withered away|starved to death|suffocated in a wall|"
    r"was killed by[^\n]+|died)"
)
ADV_RE = re.compile(r"\[Server thread/INFO\]: (\w+) has made the advancement \[(.+?)\]")


class WeeklyDiary:
    """小方日记，每周日 push_hour 点推送到 QQ 群。"""

    def __init__(
        self,
        logs_dir: str,
        ai_provider,
        send_to_qq: Optional[Callable[[str], None]] = None,
        push_hour: int = 22,
    ):
        self.logs_dir = Path(logs_dir)
        self.ai = ai_provider
        self.send_to_qq = send_to_qq
        self.push_hour = push_hour
        self._last_push_week: Optional[int] = None

    def _collect_events(self, days: int = 7) -> list[dict]:
        """从最近 7 天日志里抽关键事件 —— 聊天/加入/死亡/成就各采样一部分，
        避免给 AI 塞一整周上千条消息。"""
        if not self.logs_dir.exists():
            return []

        cutoff = time.time() - days * 86400
        today = datetime.now(CST).strftime("%Y-%m-%d")
        events: list[dict] = []

        for lf in sorted(self.logs_dir.iterdir()):
            try:
                if lf.stat().st_mtime < cutoff:
                    continue

                date_match = LOG_DATE_PATTERN.match(lf.name)
                date_str = date_match.group(1) if date_match else today

                opener = gzip.open if lf.suffix == ".gz" else open
                if lf.suffix == ".gz" or lf.name.endswith(".log"):
                    with opener(lf, "rt", encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            # 聊天（非小方自己的）
                            m = CHAT_RE.search(line)
                            if m and m.group(1) not in ("小方", "bot"):
                                # 过滤掉 Rcon 广播 / 纯数字投票
                                content = m.group(2)
                                if content.strip().isdigit():
                                    continue
                                events.append({
                                    "date": date_str,
                                    "type": "chat",
                                    "player": m.group(1),
                                    "text": content[:60],  # 截断太长的
                                })
                                continue
                            # 加入
                            m = JOIN_RE.search(line)
                            if m:
                                events.append({
                                    "date": date_str, "type": "join",
                                    "player": m.group(1), "text": "上线",
                                })
                                continue
                            # 死亡
                            m = DEATH_RE.search(line)
                            if m:
                                events.append({
                                    "date": date_str, "type": "death",
                                    "player": m.group(1),
                                    "text": m.group(2)[:60],
                                })
                                continue
                            # 成就
                            m = ADV_RE.search(line)
                            if m:
                                events.append({
                                    "date": date_str, "type": "advancement",
                                    "player": m.group(1),
                                    "text": f"解锁成就：{m.group(2)}",
                                })
            except (OSError, EOFError):
                continue

        return events

    def _build_events_text(self, events: list[dict]) -> str:
        """把事件列表按类型采样+整理，避免 prompt 过载。"""
        if not events:
            return "本周服务器冷清，没什么事发生。"

        # 按类型分桶，每类最多 8 条（优先保留多样性）
        buckets: dict[str, list[dict]] = {"chat": [], "join": [], "death": [], "advancement": []}
        for e in events:
            if e["type"] in buckets and len(buckets[e["type"]]) < 8:
                buckets[e["type"]].append(e)

        lines = []
        if buckets["chat"]:
            lines.append("【聊天片段】")
            for e in buckets["chat"]:
                lines.append(f"  {e['player']}: {e['text']}")
        if buckets["death"]:
            lines.append("【死亡事件】")
            for e in buckets["death"]:
                lines.append(f"  {e['player']} {e['text']}")
        if buckets["advancement"]:
            lines.append("【解锁成就】")
            for e in buckets["advancement"]:
                lines.append(f"  {e['player']} {e['text']}")
        if buckets["join"]:
            upline = sorted(set(e["player"] for e in buckets["join"]))
            lines.append(f"【上线玩家】{', '.join(upline)}")

        return "\n".join(lines)

    def generate_diary(self) -> Optional[str]:
        events = self._collect_events(days=7)
        events_text = self._build_events_text(events)
        prompt = DIARY_USER_TEMPLATE.format(events_text=events_text)
        return self.ai.chat(
            [{"role": "user", "content": prompt}],
            DIARY_SYSTEM_PROMPT,
        )

    def push_weekly_diary(self):
        """生成并发 QQ 群。"""
        print("[WeeklyDiary] 生成小方日记...")
        diary = self.generate_diary()
        if not diary:
            print("[WeeklyDiary] AI 生成失败，跳过本周推送")
            return

        today = datetime.now(CST).strftime("%m 月 %d 日")
        msg = f"📓【小方日记 · {today}】\n\n{diary}"
        print(f"[WeeklyDiary] 推送:\n{msg}")
        if self.send_to_qq:
            self.send_to_qq(msg)

    def _scheduler_loop(self):
        """每分钟检查一次，周日 push_hour 点触发。"""
        while True:
            now = datetime.now(CST)
            week = now.isocalendar()[1]
            # 周日 = isoweekday() == 7
            if (
                now.isoweekday() == 7
                and now.hour == self.push_hour
                and self._last_push_week != week
            ):
                self._last_push_week = week
                try:
                    self.push_weekly_diary()
                except Exception as e:
                    print(f"[WeeklyDiary] 推送出错: {e}")
            time.sleep(60)

    def start(self):
        t = threading.Thread(target=self._scheduler_loop, daemon=True)
        t.start()
        print(f"[WeeklyDiary] 小方日记定时器已启动（周日 {self.push_hour}:00 推送）")
