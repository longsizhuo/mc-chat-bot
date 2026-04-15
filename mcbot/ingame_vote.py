"""游戏内民主投票 - 玩家喊 `投票 xxx` 发起，30 秒内 +1/-1，到时公布结果。

设计：
- 任意玩家在游戏聊天发 `投票 <议题>` → 小方广播 + 启动 30 秒倒计时
- 其它玩家发 `+1` 或 `-1`（必须是纯字符串）→ 计票
- 同一玩家只计第一次投票；发起人默认 +1
- 30 秒到 → 广播结果；若议题匹配"允许/禁止 xxx"等常见模板，给出管理员建议
- 同一时刻只允许一个议题，期间再发 `投票 xxx` 会被拒绝

为了避免刷屏，只在有 2 人或以上投票时才广播结果，单人投票静默收场。
"""

import re
import threading
import time
from typing import Optional


# 命令正则
CMD_START_VOTE = re.compile(r"^投票\s+(.+)$")
CMD_VOTE_YES = re.compile(r"^\+1$")
CMD_VOTE_NO = re.compile(r"^-1$")

VOTE_DURATION_SECONDS = 30


class InGameVote:
    """进行中的投票状态 + 命令处理。"""

    def __init__(self, rcon, bot_name: str = "小方", duration: int = VOTE_DURATION_SECONDS):
        self.rcon = rcon
        self.bot_name = bot_name
        self.duration = duration

        self._lock = threading.Lock()
        self._active: Optional[dict] = None  # 正在进行中的投票
        # 结构：{
        #   "topic": str, "starter": str, "start_ts": float,
        #   "votes": {player: "yes"|"no"}, "end_timer": threading.Timer
        # }

    def _say(self, text: str):
        try:
            self.rcon.say(self.bot_name, text)
        except Exception as e:
            print(f"[InGameVote] RCON 播报失败: {e}")

    def try_handle(self, player: str, message: str) -> Optional[str]:
        """聊天 hook：识别投票命令。返回需要 say 的文本；None 表示不处理。
        返回空串 "" 表示已在内部处理（比如 +1 计票，不需要额外说话）。"""
        msg = message.strip()

        # 发起投票
        m = CMD_START_VOTE.match(msg)
        if m:
            topic = m.group(1).strip()
            return self._start_vote(player, topic)

        # 投赞成
        if CMD_VOTE_YES.match(msg):
            return self._record_vote(player, "yes")

        # 投反对
        if CMD_VOTE_NO.match(msg):
            return self._record_vote(player, "no")

        return None

    def _start_vote(self, starter: str, topic: str) -> str:
        with self._lock:
            if self._active is not None:
                return f"已经有一个投票在进行：「{self._active['topic']}」，等它结束再说"
            if len(topic) > 80:
                return "议题太长（限 80 字内）"

            # 发起人自动 +1
            self._active = {
                "topic": topic,
                "starter": starter,
                "start_ts": time.time(),
                "votes": {starter: "yes"},
                "end_timer": None,
            }

            # 启动结束定时器（放锁外执行以免死锁）
            timer = threading.Timer(self.duration, self._end_vote)
            timer.daemon = True
            self._active["end_timer"] = timer
            timer.start()

            return (
                f"🗳️ {starter} 发起投票：「{topic}」\n"
                f"其他人 {self.duration} 秒内发「+1」赞成 / 「-1」反对 · 发起人默认 +1"
            )

    def _record_vote(self, player: str, choice: str) -> str:
        """记录投票；返回空串或确认消息。返回 None 表示没进行中的投票。"""
        with self._lock:
            if self._active is None:
                # 没有进行中的投票，"+1"/"-1" 当普通聊天忽略
                return None
            if player in self._active["votes"]:
                # 已投过票，不重复计数，但也不抢麦
                return None
            self._active["votes"][player] = choice

        # 实时微确认（不 say 到群免得刷屏；仅打日志）
        print(f"[InGameVote] {player} 投了 {choice}")
        return ""  # 内部已处理，别再 say 任何东西

    def _end_vote(self):
        """定时器到期：结算 + 广播。"""
        with self._lock:
            if self._active is None:
                return
            active = self._active
            self._active = None  # 清空状态，允许下一次投票

        votes = active["votes"]
        yes = sum(1 for v in votes.values() if v == "yes")
        no = sum(1 for v in votes.values() if v == "no")
        total = yes + no
        topic = active["topic"]

        # 只有 1 人（发起人自己）投的话静默
        if total <= 1:
            print(f"[InGameVote] 投票「{topic}」参与不足，静默收场")
            self._say(f"投票「{topic}」没人理，{active['starter']} 自己说了算")
            return

        if yes > no:
            result = f"✅ 通过：赞成 {yes} 反对 {no}"
        elif no > yes:
            result = f"❌ 否决：赞成 {yes} 反对 {no}"
        else:
            result = f"⚖️ 平局：赞成 {yes} 反对 {no}（需要管理员决定）"

        self._say(f"🗳️ 投票结果「{topic}」— {result}")
