"""小方今日预言 - 每天 8:00 发预言，23:00 验证。

设计：
- 8:00  随机挑一个最近 7 天活跃的玩家，AI 生成荒诞预言（今天你将死于 X）
- 23:00 查当天死亡日志：
    - 命中 → 补发"我说了吧"
    - 未命中 → 沉默

闭环制造期待感：玩家会主动上线看"今天会不会成真"。

状态持久化在 data/today_prophecy.json，bot 重启也不丢。
"""

import gzip
import json
import random
import re
import time
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Callable


CST = timezone(timedelta(hours=8))

LOG_DATE_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2})")
DEATH_RE = re.compile(
    r"\[Server thread/INFO\]: (\w+) "
    r"(was slain by[^\n]+|drowned|fell[^\n]*|burned to death|"
    r"was blown up by[^\n]+|walked into[^\n]+|tried to swim in lava[^\n]*|"
    r"withered away|starved to death|suffocated in a wall|"
    r"was killed by[^\n]+|died)"
)

PROPHECY_SYSTEM_PROMPT = """你是小方，一个 Minecraft 服务器的 AI 助手。
你今天要对一个朋友发出一条"荒诞预言"——预言他今天会以某种方式死亡。

要求：
- 1-2 句话，带点神秘感但不装神棍
- 必须是具体的死法（死于苦力怕 / 死于自己挖的坑 / 死于岩浆游泳 等），不要笼统
- 可以结合他最近的行为模式作依据（最近老摔死 → 预言摔死）
- 结尾可以加一句"请大家见证"或"不接受退款"这种调皮话
- 禁用"祝""愿"，这不是生日祝福

示例：
- "今天 XX 将死于他自己挖的坑。请大家见证。"
- "我预言 XX 将在凌晨之前与一只苦力怕完成物理上的亲密接触。"
- "XX 今日命数偏离主世界，很可能通过岩浆离开。不接受退款。"
"""

PROPHECY_USER_TEMPLATE = """今天随机选中的玩家是 {player}。

他最近 7 天的死因分布：
{death_hints}

请以小方的身份发一条荒诞预言（1-2 句话）。"""

VERIFY_PROMPT = """我之前预言了 {player} 今天会死亡，而他真的死了。
死因是：{cause}

用小方的身份发一句话跟进，语气类似"我说了吧"的得意但不浮夸。
1 句话，简洁毒舌。"""


class DailyProphecy:
    """每天早上发预言 + 晚上验证。"""

    def __init__(
        self,
        stats_path: str,
        logs_dir: str,
        state_path: str,
        ai_provider,
        send_to_qq: Optional[Callable[[str], None]] = None,
        morning_hour: int = 8,
        evening_hour: int = 23,
    ):
        self.stats_path = Path(stats_path)
        self.logs_dir = Path(logs_dir)
        self.state_path = Path(state_path)
        self.ai = ai_provider
        self.send_to_qq = send_to_qq
        self.morning_hour = morning_hour
        self.evening_hour = evening_hour
        self._last_morning_date: Optional[str] = None
        self._last_evening_date: Optional[str] = None

    # ========== 状态 ==========

    def _load_state(self) -> dict:
        if not self.state_path.exists():
            return {}
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_state(self, data: dict):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.state_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    # ========== 早上 8:00：发预言 ==========

    def _pick_player(self) -> Optional[tuple[str, dict]]:
        """从 stats 里随机挑一个最近 7 天活跃玩家。"""
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
            candidates.append((name, p))

        return random.choice(candidates) if candidates else None

    def _death_hints(self, player_data: dict) -> str:
        """格式化玩家近期死因，给 AI 做预言依据。"""
        causes = player_data.get("death_causes", {}) or {}
        if not causes:
            return "（还没死过，是个新鲜人）"
        top = sorted(causes.items(), key=lambda x: -x[1])[:3]
        return "，".join(f"{c}（{n} 次）" for c, n in top)

    def push_prophecy(self):
        """生成并发送今日预言。"""
        picked = self._pick_player()
        if not picked:
            print("[Prophecy] 没有活跃玩家，今天没预言")
            return
        player, player_data = picked

        prompt = PROPHECY_USER_TEMPLATE.format(
            player=player,
            death_hints=self._death_hints(player_data),
        )
        try:
            reply = self.ai.chat(
                [{"role": "user", "content": prompt}],
                PROPHECY_SYSTEM_PROMPT,
            )
        except Exception as e:
            print(f"[Prophecy] AI 生成失败: {e}")
            return
        if not reply:
            return

        today = datetime.now(CST).strftime("%Y-%m-%d")
        msg = f"🔮 小方今日预言 · {today}\n\n{reply.strip()}"
        print(f"[Prophecy] 推送:\n{msg}")
        if self.send_to_qq:
            self.send_to_qq(msg)

        # 保存今日预言状态，晚上验证用
        self._save_state({
            "date": today,
            "player": player,
            "prophecy_text": reply.strip(),
            "verified": False,
        })

    # ========== 晚上 23:00：验证 ==========

    def _find_today_death(self, player: str) -> Optional[str]:
        """查当天日志里该玩家是否死过；返回死因（找到的第一条）。"""
        today_str = datetime.now(CST).strftime("%Y-%m-%d")
        if not self.logs_dir.exists():
            return None
        # 只看今天和 latest.log
        for lf in sorted(self.logs_dir.iterdir()):
            try:
                # 只看文件名匹配今天日期或 latest.log
                if not (lf.name.startswith(today_str) or lf.name == "latest.log"):
                    continue
                opener = gzip.open if lf.suffix == ".gz" else open
                if not (lf.suffix == ".gz" or lf.name.endswith(".log")):
                    continue
                with opener(lf, "rt", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        m = DEATH_RE.search(line)
                        if m and m.group(1) == player:
                            return m.group(2).strip()
            except (OSError, EOFError):
                continue
        return None

    def verify_prophecy(self):
        """晚上检查预言是否应验；应验则补发一条得意话。"""
        state = self._load_state()
        today = datetime.now(CST).strftime("%Y-%m-%d")
        if state.get("date") != today:
            return  # 今天没发预言
        if state.get("verified"):
            return  # 已经验证过（重启等场景）

        player = state.get("player")
        if not player:
            return

        cause = self._find_today_death(player)
        if not cause:
            # 未应验，沉默 —— 但标记已处理避免重复跑
            state["verified"] = True
            state["outcome"] = "miss"
            self._save_state(state)
            print(f"[Prophecy] {player} 今天没死，沉默。")
            return

        # 应验了，生成补发消息
        try:
            reply = self.ai.chat(
                [{"role": "user", "content": VERIFY_PROMPT.format(
                    player=player, cause=cause,
                )}],
                PROPHECY_SYSTEM_PROMPT,
            )
        except Exception as e:
            print(f"[Prophecy] 验证消息生成失败: {e}")
            reply = None

        text = (reply or "我说了吧。").strip()
        msg = f"🔮 预言应验\n\n{text}"
        print(f"[Prophecy] 应验推送:\n{msg}")
        if self.send_to_qq:
            self.send_to_qq(msg)

        state["verified"] = True
        state["outcome"] = "hit"
        state["hit_cause"] = cause
        self._save_state(state)

    # ========== 调度 ==========

    def _scheduler_loop(self):
        """每分钟检查一次。8:00 发预言，23:00 验证。"""
        while True:
            now = datetime.now(CST)
            today = now.strftime("%Y-%m-%d")

            # 早上发预言
            if (
                now.hour == self.morning_hour
                and self._last_morning_date != today
            ):
                self._last_morning_date = today
                try:
                    self.push_prophecy()
                except Exception as e:
                    print(f"[Prophecy] 发预言出错: {e}")

            # 晚上验证
            if (
                now.hour == self.evening_hour
                and self._last_evening_date != today
            ):
                self._last_evening_date = today
                try:
                    self.verify_prophecy()
                except Exception as e:
                    print(f"[Prophecy] 验证出错: {e}")

            time.sleep(60)

    def start(self):
        t = threading.Thread(target=self._scheduler_loop, daemon=True)
        t.start()
        print(
            f"[Prophecy] 今日预言定时器已启动"
            f"（{self.morning_hour}:00 发预言 / {self.evening_hour}:00 验证）"
        )
