"""小方今日心情 - 每天 09:00 根据昨日事件生成心情描述，存 JSON 供前端展示。

数据文件：data/today_mood.json
格式：{"date": "2026-04-15", "mood": "疑神疑鬼", "desc": "昨天没人上线，小方觉得被遗弃了"}
"""

import json
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Callable


CST = timezone(timedelta(hours=8))

MOOD_SYSTEM_PROMPT = """你是小方，一个 Minecraft 服务器的 AI 助手，性格毒舌但真情实感。
根据昨天服务器里发生的事，给自己生成一个今日心情。

输出严格为 JSON，两个字段：
- "mood"：2-4 字的心情词（例：摸鱼成瘾、受宠若惊、怨天尤人、无所事事）
- "desc"：一句话解释，15-30 字，第一人称，可以有点自嘲

例子：
{"mood": "无所事事", "desc": "昨天没人上线，我一个人对着空气说了 4 小时的话。"}
{"mood": "受宠若惊", "desc": "昨天 3 个人同时上线，热闹得我不知道先回谁。"}

只输出 JSON，不要多余文字。"""


class DailyMood:
    """每天 09:00 生成一次心情，存 JSON，供 /api/mood 端点读取。"""

    def __init__(
        self,
        stats_path: str,
        state_path: str,
        ai_provider,
        generate_hour: int = 9,
    ):
        self.stats_path = Path(stats_path)
        self.state_path = Path(state_path)
        self.ai = ai_provider
        self.generate_hour = generate_hour
        self._last_date: Optional[str] = None

    # ========== 数据读写 ==========

    def load(self) -> dict:
        if not self.state_path.exists():
            return {}
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self, data: dict):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.state_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    # ========== 昨日事件摘要 ==========

    def _yesterday_summary(self) -> str:
        """从 player_stats 里提取昨日活跃情况，给 AI 做上下文。"""
        if not self.stats_path.exists():
            return "昨天没有任何记录"
        try:
            data = json.loads(self.stats_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return "昨天没有任何记录"

        yesterday_ts_start = time.time() - 86400 * 2
        yesterday_ts_end = time.time() - 86400

        active_players = []
        total_deaths = 0
        for name, p in (data.get("players") or {}).items():
            if not isinstance(p, dict):
                continue
            last_seen = p.get("last_seen", 0)
            if yesterday_ts_start <= last_seen <= yesterday_ts_end:
                active_players.append(name)
            # 统计死亡次数（只看总数，无法精确到昨天，作为参考）
            total_deaths += sum((p.get("death_causes") or {}).values())

        if not active_players:
            return "昨天没有任何玩家上线，服务器空空如也"

        players_str = "、".join(active_players)
        return f"昨天上线的玩家有：{players_str}；服务器累计记录死亡 {total_deaths} 次"

    # ========== 生成心情 ==========

    def generate(self):
        """调用 AI 生成今日心情并保存。"""
        summary = self._yesterday_summary()
        prompt = f"昨天服务器情况：{summary}\n\n请生成今日小方心情 JSON。"
        try:
            raw = self.ai.chat(
                [{"role": "user", "content": prompt}],
                MOOD_SYSTEM_PROMPT,
            )
        except Exception as e:
            print(f"[DailyMood] AI 调用失败: {e}")
            return

        if not raw:
            return

        # 提取 JSON（AI 可能多输出了空白或 markdown 代码块）
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if len(lines) > 2 else text

        try:
            parsed = json.loads(text)
            mood = str(parsed.get("mood", "")).strip()
            desc = str(parsed.get("desc", "")).strip()
            if not mood or not desc:
                raise ValueError("字段缺失")
        except (json.JSONDecodeError, ValueError) as e:
            print(f"[DailyMood] 解析 AI 输出失败: {e}，原文：{raw[:200]}")
            return

        today = datetime.now(CST).strftime("%Y-%m-%d")
        self._save({"date": today, "mood": mood, "desc": desc})
        print(f"[DailyMood] 今日心情：{mood} — {desc}")

    # ========== 调度 ==========

    def _scheduler_loop(self):
        while True:
            now = datetime.now(CST)
            today = now.strftime("%Y-%m-%d")
            if now.hour == self.generate_hour and self._last_date != today:
                self._last_date = today
                try:
                    self.generate()
                except Exception as e:
                    print(f"[DailyMood] 生成出错: {e}")
            time.sleep(60)

    def start(self):
        # 启动时如果今天还没生成过，立即生成一次（方便首次部署）
        existing = self.load()
        today = datetime.now(CST).strftime("%Y-%m-%d")
        if existing.get("date") != today:
            try:
                self.generate()
            except Exception as e:
                print(f"[DailyMood] 启动时生成失败: {e}")

        t = threading.Thread(target=self._scheduler_loop, daemon=True)
        t.start()
        print(f"[DailyMood] 心情定时器已启动（每天 {self.generate_hour}:00 更新）")
