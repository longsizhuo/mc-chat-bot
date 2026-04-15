"""每周服务器传说生成 - 周日晚上发一篇史诗叙事推送到QQ群。"""

import json
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Callable


# 史诗叙事 prompt，要求古典第三人称，把普通数据包装成传奇
EPIC_SYSTEM_PROMPT = """你是一位古典史诗的吟游诗人，负责记录一个Minecraft服务器的传奇史册。
你的叙事风格要求：
- 第三人称古典口吻，如"勇士XX"、"英灵归天"、"荣耀加身"
- 把普通游戏数据变成传奇故事，死亡是"英灵升天"，在线是"驻守大陆"
- 语言简洁有力，全文控制在5-8句话，不要废话
- 结尾留一句带悬念或期待感的话，引导下周继续
- 禁止出现"本周"、"统计"、"数据"等词，要有史诗感
- 如果某个玩家死亡次数最多，要用荣耀感描述，不是嘲讽"""

EPIC_USER_TEMPLATE = """本周服务器战报数据如下，请将其铸成传奇史诗（5-8句，约100字）：

{stats_text}

要求：史诗叙事，第三人称，古典口吻，结尾带悬念。"""


class WeeklyChronicle:
    """每周史诗传说生成器，周日晚上10点推送到QQ群。"""

    def __init__(
        self,
        stats_path: str,
        ai_provider,
        send_to_qq: Optional[Callable[[str], None]] = None,
        push_hour: int = 22,  # 晚上10点推送
    ):
        self.stats_path = Path(stats_path)
        self.ai = ai_provider
        self.send_to_qq = send_to_qq
        self.push_hour = push_hour
        self._last_push_week: Optional[int] = None  # 防止同一周重复推送

    def _load_stats(self) -> dict:
        if self.stats_path.exists():
            try:
                return json.loads(self.stats_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {"players": {}, "server": {"total_deaths": 0, "total_joins": 0}}

    def _build_stats_text(self, stats: dict) -> str:
        """把 player_stats.json 的数据整理成可读文本喂给 AI。"""
        players = stats.get("players", {})
        if not players:
            return "本周服务器空无一人，寂静如初。"

        lines = []
        # 按在线时长排序
        sorted_players = sorted(
            players.items(),
            key=lambda x: x[1].get("playtime_minutes", 0),
            reverse=True,
        )

        most_deaths = max(players.items(), key=lambda x: x[1].get("deaths", 0), default=None)
        most_online = sorted_players[0] if sorted_players else None

        for name, p in sorted_players:
            playtime = round(p.get("playtime_minutes", 0))
            deaths = p.get("deaths", 0)
            joins = p.get("joins", 0)
            pvp_kills = p.get("pvp_kills", 0)
            parts = [f"玩家【{name}】"]
            if playtime > 0:
                parts.append(f"在线{playtime}分钟")
            if deaths > 0:
                parts.append(f"死亡{deaths}次")
            if pvp_kills > 0:
                parts.append(f"击杀{pvp_kills}人")
            if joins > 1:
                parts.append(f"共登录{joins}次")
            lines.append("，".join(parts))

        summary = "\n".join(lines)

        # 添加特别注记
        notes = []
        if most_deaths and most_deaths[1].get("deaths", 0) >= 3:
            notes.append(f"死亡最多：{most_deaths[0]}（{most_deaths[1]['deaths']}次）")
        if most_online and most_online[1].get("playtime_minutes", 0) >= 60:
            h = round(most_online[1]["playtime_minutes"] / 60, 1)
            notes.append(f"在线最久：{most_online[0]}（{h}小时）")

        if notes:
            summary += "\n\n特别战报：" + "；".join(notes)

        return summary

    def generate_epic(self) -> Optional[str]:
        """调用 AI 生成史诗文本。"""
        stats = self._load_stats()
        stats_text = self._build_stats_text(stats)

        prompt = EPIC_USER_TEMPLATE.format(stats_text=stats_text)
        result = self.ai.chat(
            [{"role": "user", "content": prompt}],
            EPIC_SYSTEM_PROMPT,
        )
        return result

    def push_weekly_epic(self):
        """生成并发送本周史诗到QQ群。"""
        print("[Chronicle] 生成本周传说...")
        epic = self.generate_epic()
        if not epic:
            print("[Chronicle] AI生成失败，跳过本周推送")
            return

        # 格式化消息
        week_num = datetime.now().isocalendar()[1]
        msg = f"📜【第{week_num}周 传奇史册】\n\n{epic}"

        print(f"[Chronicle] 推送史诗:\n{msg}")
        if self.send_to_qq:
            self.send_to_qq(msg)

    def _scheduler_loop(self):
        """后台线程：每分钟检查一次，周日晚上 push_hour 点触发推送。"""
        while True:
            now = datetime.now()
            # 周日 = isoweekday() == 7
            current_week = now.isocalendar()[1]
            if (
                now.isoweekday() == 7
                and now.hour == self.push_hour
                and self._last_push_week != current_week
            ):
                self._last_push_week = current_week
                try:
                    self.push_weekly_epic()
                except Exception as e:
                    print(f"[Chronicle] 推送出错: {e}")

            time.sleep(60)

    def start(self):
        """启动后台定时线程。"""
        t = threading.Thread(target=self._scheduler_loop, daemon=True)
        t.start()
        print(f"[Chronicle] 每周传说定时器已启动（周日 {self.push_hour}:00 推送）")
