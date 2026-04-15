"""每周最佳死法集锦 - 周一上午9点推送到QQ群。

读取最近 7 天的 Minecraft 服务器日志，提取所有死亡事件，
交给 AI 生成"黑色幽默、游戏主播复盘集锦"风格的集锦。
"""

import gzip
import re
import time
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Callable

# 服务器跑 UTC，但周一上午 9 点推送要按北京时间
CST = timezone(timedelta(hours=8))

# Minecraft 日志文件名格式：2026-04-14-1.log.gz / latest.log
# 用于给死亡事件拼上日期，解决跨天同时刻无法排序的问题
LOG_DATE_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2})")


# AI 人格 prompt - 游戏主播复盘集锦风格，黑色幽默不说教
DEATHS_SYSTEM_PROMPT = """你是一位游戏主播，正在为一个Minecraft私服做《本周死亡集锦》复盘。
你的风格要求：
- 黑色幽默，像主播做集锦视频那样调侃，不说教不劝学
- 吐槽重点放在"死法本身的戏剧性"，不羞辱玩家
- 每条点评一句话为主，最多两句，简洁有力
- 可以使用网络梗、游戏梗，但别过火
- 语气要让人想截图分享，不是"活该被杀"那种优越感"""

DEATHS_USER_TEMPLATE = """本周服务器全部死亡事件如下：

{deaths_text}

请按以下格式输出《本周死亡集锦》（**严格按结构**，不要加多余解释）：

🏆 本周最佳死法
[选一条最戏剧性的，1-2句点评，带玩家名]

🎬 提名榜（2-3条）
- [玩家名] [死法一句话吐槽]
- [玩家名] [死法一句话吐槽]

👑 本周死亡王
[死得最多的玩家名]，本周死亡[次数]次 · 封号：[自拟一个半戏谑半尊敬的称号]

💬 主播寄语
[一句话对全体玩家的神评论，幽默收尾]

注意：
- 如果本周零死亡，直接输出"🎉 本周零伤亡 —— 你们这周是不是太无聊了？"
- 如果只有一条死亡，只填最佳死法部分，其它省略"""

# 死亡日志正则，匹配 Minecraft 服务端日志里的死亡行
DEATH_LOG_PATTERN = re.compile(
    r"\[(\d{2}:\d{2}:\d{2})\] \[Server thread/INFO\]: "
    r"(\w+) ("
    r"was slain by[^\n]+|"
    r"was shot by[^\n]+|"
    r"was killed by[^\n]+|"
    r"burned to death|went up in flames|"
    r"drowned|"
    r"fell from a high place|fell off[^\n]+|hit the ground too hard[^\n]+|"
    r"was blown up by[^\n]+|blew up[^\n]*|"
    r"was squashed by[^\n]+|"
    r"starved to death|"
    r"suffocated in a wall|"
    r"was impaled by[^\n]+|"
    r"was fireballed by[^\n]+|"
    r"withered away|"
    r"died|"
    r"was poked to death by[^\n]+|"
    r"was pricked to death|"
    r"tried to swim in lava[^\n]*|"
    r"walked into[^\n]+"
    r")"
)


class WeeklyDeaths:
    """每周死亡集锦生成器，周一上午 push_hour 点推送到 QQ 群。"""

    def __init__(
        self,
        logs_dir: str,
        ai_provider,
        send_to_qq: Optional[Callable[[str], None]] = None,
        push_hour: int = 9,  # 周一上午 9 点推送
    ):
        self.logs_dir = Path(logs_dir)
        self.ai = ai_provider
        self.send_to_qq = send_to_qq
        self.push_hour = push_hour
        self._last_push_week: Optional[int] = None  # 防止同一周重复推送

    def _collect_recent_logs(self, days: int = 7) -> list[tuple[str, str]]:
        """收集最近 N 天的日志文件内容。返回 [(date_str, line), ...]。
        date_str 从文件名（如 2026-04-14-1.log.gz）提取；latest.log 用今天的日期。
        这样后续跨天死亡事件也能按真实时间排序。"""
        if not self.logs_dir.exists():
            return []

        cutoff = time.time() - days * 86400
        today = datetime.now(CST).strftime("%Y-%m-%d")
        items: list[tuple[str, str]] = []

        for log_file in sorted(self.logs_dir.iterdir()):
            try:
                if log_file.stat().st_mtime < cutoff:
                    continue

                # 从文件名解析日期；latest.log 回退到今天
                date_match = LOG_DATE_PATTERN.match(log_file.name)
                date_str = date_match.group(1) if date_match else today

                if log_file.suffix == ".gz":
                    with gzip.open(log_file, "rt", encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            items.append((date_str, line))
                elif log_file.name.endswith(".log"):
                    with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            items.append((date_str, line))
            except (OSError, EOFError):
                continue

        return items

    def _extract_deaths(self, items: list[tuple[str, str]]) -> list[dict]:
        """从 (date, line) 元组中提取死亡事件，带完整日期+时间便于排序。"""
        deaths: list[dict] = []
        for date_str, line in items:
            m = DEATH_LOG_PATTERN.search(line)
            if not m:
                continue
            deaths.append({
                "date": date_str,
                "time": m.group(1),
                "player": m.group(2),
                "cause": m.group(3).strip(),
            })
        # 按真实时间排序（日期 + 时间），保证跨天顺序正确
        deaths.sort(key=lambda d: f"{d['date']} {d['time']}")
        return deaths

    def _build_deaths_text(self, deaths: list[dict]) -> str:
        """把死亡列表整理成可读文本喂给 AI，同时附上死亡王统计。"""
        if not deaths:
            return "本周零死亡，玩家全部幸存。"

        # 死亡次数统计
        counts: dict[str, int] = {}
        for d in deaths:
            counts[d["player"]] = counts.get(d["player"], 0) + 1

        lines = [f"总死亡事件：{len(deaths)}次"]
        lines.append("")
        lines.append("按时间顺序的死亡明细：")
        for d in deaths[:30]:  # 最多喂30条给 AI，避免 prompt 过长
            lines.append(f"  [{d['date']} {d['time']}] {d['player']} → {d['cause']}")

        if len(deaths) > 30:
            lines.append(f"  ...（还有 {len(deaths) - 30} 次死亡省略）")

        lines.append("")
        lines.append("死亡次数排行：")
        for name, cnt in sorted(counts.items(), key=lambda x: -x[1])[:5]:
            lines.append(f"  {name}: {cnt}次")

        return "\n".join(lines)

    def generate_deaths_digest(self) -> Optional[str]:
        """调用 AI 生成本周死亡集锦文案。"""
        log_lines = self._collect_recent_logs(days=7)
        deaths = self._extract_deaths(log_lines)
        deaths_text = self._build_deaths_text(deaths)

        prompt = DEATHS_USER_TEMPLATE.format(deaths_text=deaths_text)
        result = self.ai.chat(
            [{"role": "user", "content": prompt}],
            DEATHS_SYSTEM_PROMPT,
        )
        return result

    def push_weekly_deaths(self):
        """生成并发送本周死亡集锦到 QQ 群。"""
        print("[WeeklyDeaths] 生成本周死亡集锦...")
        digest = self.generate_deaths_digest()
        if not digest:
            print("[WeeklyDeaths] AI 生成失败，跳过本周推送")
            return

        week_num = datetime.now(CST).isocalendar()[1]
        msg = f"☠️【第{week_num}周 死亡集锦】\n\n{digest}"

        print(f"[WeeklyDeaths] 推送集锦:\n{msg}")
        if self.send_to_qq:
            self.send_to_qq(msg)

    def _scheduler_loop(self):
        """后台线程：每分钟检查一次，周一 push_hour 点触发推送。"""
        while True:
            now = datetime.now(CST)
            current_week = now.isocalendar()[1]
            # 周一 = isoweekday() == 1
            if (
                now.isoweekday() == 1
                and now.hour == self.push_hour
                and self._last_push_week != current_week
            ):
                self._last_push_week = current_week
                try:
                    self.push_weekly_deaths()
                except Exception as e:
                    print(f"[WeeklyDeaths] 推送出错: {e}")

            time.sleep(60)

    def start(self):
        """启动后台定时线程。"""
        t = threading.Thread(target=self._scheduler_loop, daemon=True)
        t.start()
        print(f"[WeeklyDeaths] 每周死亡集锦定时器已启动（周一 {self.push_hour}:00 推送）")
