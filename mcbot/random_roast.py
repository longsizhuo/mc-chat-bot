"""小方找茬 - 每 2-3 天随机挑一个玩家，用吐槽口吻点评他最近的表现。

设计原则：
- 完全随机，没有固定仪式感（朋友调侃不该变成"每周惯例"）
- 每小时摇一次骰子，平均 2-3 天触发一次
- 同一玩家不能连续 2 次被点（防止"针对某人"的不适感）
- 只挑活跃玩家（最近 7 天有数据），不骚扰挂机号
- 只在白天触发（10:00-21:00 CST），别半夜吓人
"""

import json
import random
import time
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Callable


CST = timezone(timedelta(hours=8))

# 每小时有 2% 概率触发 → 期望约 50 小时一次 ≈ 2 天
# 加上白天时段限制（约 11 小时/天），实际期望 ~4.5 天，调到 3% 更合适
ROAST_PROBABILITY_PER_HOUR = 0.03

# 只在这个时段触发（北京时间）
ACTIVE_HOUR_START = 10
ACTIVE_HOUR_END = 21

ROAST_SYSTEM_PROMPT = """你是小方，一个 Minecraft 服务器的 AI 助手。
你现在要在 QQ 群里随机找一个朋友"找茬"——用吐槽口吻点评他最近的表现。

语气要求：
- 朋友之间的调侃，不是羞辱
- 结合他的具体数据（死亡次数、死因模式、在线时长、成就等）
- 1-2 句话，精准毒舌，像游戏主播顺口一吐槽
- 结尾可以留一句建议，但别说教
- 禁用空话（"继续加油""期待下次"这种）

示例：
- "XX，你这周死了 8 次，其中 6 次是摔死的，我怀疑你是在测试重力定律。"
- "XX 在线 12 小时，解锁 0 个成就，我不知道你这 12 小时在干什么。"
- "XX 上周 pvp 没赢过一次，但每次都在群里说'我就是手残'——这是预防性人设。"
"""

ROAST_USER_TEMPLATE = """今天随机点到的玩家是 {player}。

他最近 7 天的数据：
{stats_text}

请用小方的身份发一句找茬吐槽（1-2 句话），结合具体数据，别说教。"""


class RandomRoast:
    """每小时摇骰子，命中则随机找茬一个玩家。"""

    def __init__(
        self,
        stats_path: str,
        ai_provider,
        send_to_qq: Optional[Callable[[str], None]] = None,
        probability_per_hour: float = ROAST_PROBABILITY_PER_HOUR,
    ):
        self.stats_path = Path(stats_path)
        self.ai = ai_provider
        self.send_to_qq = send_to_qq
        self.probability = probability_per_hour
        self._last_roasted_player: Optional[str] = None  # 上次点的人，下次避开
        self._last_fire_time: float = 0.0
        self._state_file = self.stats_path.parent / ".roast_state.json"
        self._load_state()

    # ====== 状态持久化（bot 重启不丢失"上次点谁了"）======

    def _load_state(self):
        if not self._state_file.exists():
            return
        try:
            data = json.loads(self._state_file.read_text())
            self._last_roasted_player = data.get("last_player")
            self._last_fire_time = data.get("last_fire_time", 0)
        except (json.JSONDecodeError, OSError):
            pass

    def _save_state(self):
        try:
            self._state_file.write_text(json.dumps({
                "last_player": self._last_roasted_player,
                "last_fire_time": self._last_fire_time,
            }))
        except OSError:
            pass

    # ====== 玩家数据抽取 ======

    def _pick_active_player(self) -> Optional[tuple[str, dict]]:
        """从 stats 里挑一个最近 7 天活跃的玩家，避开上次被点的。"""
        if not self.stats_path.exists():
            return None
        try:
            data = json.loads(self.stats_path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

        cutoff = time.time() - 7 * 86400
        candidates: list[tuple[str, dict]] = []
        for name, p in (data.get("players") or {}).items():
            if not isinstance(p, dict):
                continue
            if p.get("last_seen", 0) < cutoff:
                continue
            # 必须有一点数据（死亡/成就/在线）才有得吐槽
            if (p.get("deaths", 0) + len(p.get("advancements", []))
                    + (1 if p.get("playtime_minutes", 0) > 30 else 0)) == 0:
                continue
            candidates.append((name, p))

        if not candidates:
            return None

        # 避开上次被点的（除非只剩一个人）
        if self._last_roasted_player and len(candidates) > 1:
            candidates = [c for c in candidates if c[0] != self._last_roasted_player]

        return random.choice(candidates)

    def _build_stats_text(self, player: str, data: dict) -> str:
        """把玩家数据整理成 AI 能消化的简短描述。"""
        lines: list[str] = []
        playtime = round(data.get("playtime_minutes", 0))
        if playtime > 0:
            lines.append(f"在线 {playtime} 分钟")
        deaths = data.get("deaths", 0)
        if deaths > 0:
            lines.append(f"死亡 {deaths} 次")
            # 最常死因前 3
            causes = data.get("death_causes", {}) or {}
            top_causes = sorted(causes.items(), key=lambda x: -x[1])[:3]
            for cause, cnt in top_causes:
                lines.append(f"  · {cause}：{cnt} 次")
        joins = data.get("joins", 0)
        if joins > 0:
            lines.append(f"登录 {joins} 次")
        advs = data.get("advancements") or []
        if advs:
            lines.append(f"解锁 {len(advs)} 个成就")
            for a in advs[-5:]:
                lines.append(f"  · {a}")
        else:
            lines.append("没有解锁任何成就")
        return "\n".join(lines)

    # ====== 推送 ======

    def maybe_fire(self):
        """摇骰子判断是否触发。命中则挑人 + 生成吐槽 + 推 QQ 群。"""
        if random.random() > self.probability:
            return

        picked = self._pick_active_player()
        if not picked:
            print("[RandomRoast] 没有活跃玩家，跳过")
            return
        name, data = picked

        stats_text = self._build_stats_text(name, data)
        try:
            reply = self.ai.chat(
                [{"role": "user", "content": ROAST_USER_TEMPLATE.format(
                    player=name, stats_text=stats_text,
                )}],
                ROAST_SYSTEM_PROMPT,
            )
        except Exception as e:
            print(f"[RandomRoast] AI 生成失败: {e}")
            return

        if not reply:
            return

        msg = f"🎯 小方找茬 · 今日随机点名\n\n{reply.strip()}"
        print(f"[RandomRoast] 推送:\n{msg}")
        if self.send_to_qq:
            self.send_to_qq(msg)

        self._last_roasted_player = name
        self._last_fire_time = time.time()
        self._save_state()

    def _scheduler_loop(self):
        """每小时整点摇一次。只在白天活跃时段触发。"""
        last_tick_hour: Optional[int] = None
        while True:
            now = datetime.now(CST)
            # 每小时执行一次（以小时为粒度防止同一小时重复）
            hour_key = (now.year, now.month, now.day, now.hour)
            if last_tick_hour != hash(hour_key):
                last_tick_hour = hash(hour_key)
                if ACTIVE_HOUR_START <= now.hour <= ACTIVE_HOUR_END:
                    try:
                        self.maybe_fire()
                    except Exception as e:
                        print(f"[RandomRoast] 循环出错: {e}")
            time.sleep(60)

    def start(self):
        t = threading.Thread(target=self._scheduler_loop, daemon=True)
        t.start()
        print(
            f"[RandomRoast] 小方找茬定时器已启动"
            f"（{ACTIVE_HOUR_START}:00-{ACTIVE_HOUR_END}:00 每小时摇骰子，"
            f"概率 {self.probability*100:.1f}%）"
        )
