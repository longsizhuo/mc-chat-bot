"""本周最惨死法投票 - 周一 10:00 发起，周四 23:59 开奖。

流程：
1. 周一 10:00 从上周日志挑 3 条最"奇葩"的死亡（按死因稀缺度排序），发到 QQ 群
2. 监听 QQ 群里的回复 "1" / "2" / "3"，累计票数
3. 周四 23:59 开奖，写入 /home/ubuntu/minecraft-server/weekly_shame.json
4. mc-website 前端读该文件，给赢家玩家卡打上"💀 本周最惨"徽章
"""

import gzip
import json
import re
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

# 死亡行正则，复用 weekly_deaths 的范围
DEATH_LOG_RE = re.compile(
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

# "奇葩度"权重：分数越高越该被选上投票榜（稀有死因 + 特殊场景更吸睛）
CAUSE_WEIRDNESS: dict[str, int] = {
    "tried to swim in lava": 10,
    "walked into a cactus": 9,
    "was fireballed": 9,
    "was impaled": 8,
    "suffocated in a wall": 8,
    "starved": 7,
    "withered": 7,
    "drowned": 6,
    "was blown up": 6,
    "went up in flames": 5,
    "burned": 5,
    "fell": 4,
    "hit the ground": 4,
    "was shot": 3,
    "was slain": 2,
    "was killed": 2,
    "died": 1,
}


class WeeklyShameVote:
    """每周最惨死法投票管理器。"""

    def __init__(
        self,
        logs_dir: str,
        output_path: str,
        send_to_qq: Optional[Callable[[str], None]] = None,
        vote_start_hour: int = 10,   # 周一 10:00 开始
        vote_end_hour: int = 23,     # 周四 23:59 结束（用 23 简化）
    ):
        self.logs_dir = Path(logs_dir)
        self.output_path = Path(output_path)
        self.send_to_qq = send_to_qq
        self.vote_start_hour = vote_start_hour
        self.vote_end_hour = vote_end_hour

        # 本周候选：[{id, player, cause, full_desc}]，id 是 1/2/3
        self._candidates: list[dict] = []
        # 票数累计：{candidate_id: count}
        self._votes: dict[int, int] = {}
        # 已投票的 QQ 用户（防刷票）
        self._voters: set[str] = set()
        # 本周已发起过投票？防止重复
        self._vote_started_week: Optional[int] = None
        self._vote_ended_week: Optional[int] = None
        self._lock = threading.Lock()

    # ====== 日志解析与候选筛选 ======

    def _collect_recent_deaths(self, days: int = 7) -> list[dict]:
        """收集最近 N 天所有死亡事件。"""
        if not self.logs_dir.exists():
            return []
        cutoff = time.time() - days * 86400
        deaths: list[dict] = []

        for lf in sorted(self.logs_dir.iterdir()):
            try:
                if lf.stat().st_mtime < cutoff:
                    continue
                opener = gzip.open if lf.suffix == ".gz" else open
                with opener(lf, "rt", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        m = DEATH_LOG_RE.search(line)
                        if not m:
                            continue
                        deaths.append({
                            "time": m.group(1),
                            "player": m.group(2),
                            "cause": m.group(3).strip(),
                        })
            except (OSError, EOFError):
                continue
        return deaths

    def _pick_candidates(self, deaths: list[dict]) -> list[dict]:
        """从死亡列表里挑 3 条最奇葩的（按 CAUSE_WEIRDNESS 权重），去重同玩家同死因。"""
        scored: list[tuple[int, dict]] = []
        seen_keys: set[tuple] = set()

        for d in deaths:
            # 去重：同一玩家同一死因只留第一条
            key = (d["player"], d["cause"][:40])
            if key in seen_keys:
                continue
            seen_keys.add(key)

            # 打分：匹配 CAUSE_WEIRDNESS 中任一 key 则使用对应权重
            score = 0
            for pattern, weight in CAUSE_WEIRDNESS.items():
                if pattern in d["cause"]:
                    score = max(score, weight)
            scored.append((score, d))

        # 按权重降序取前 3
        scored.sort(key=lambda x: -x[0])
        return [d for _, d in scored[:3]]

    # ====== 投票流程 ======

    def start_vote(self):
        """周一 10:00 调用：挑出候选 + 发 QQ 群 + 重置票数。"""
        with self._lock:
            deaths = self._collect_recent_deaths(days=7)
            candidates = self._pick_candidates(deaths)

            if not candidates:
                print("[WeeklyShameVote] 本周没有死亡记录，跳过投票")
                return

            # 重置状态
            self._candidates = [
                {"id": i + 1, **c} for i, c in enumerate(candidates)
            ]
            self._votes = {c["id"]: 0 for c in self._candidates}
            self._voters = set()

            # 构造投票消息
            msg_lines = ["🗳️【本周最惨死法投票】", "", "哪个死得最离谱？回复数字参与投票："]
            for c in self._candidates:
                msg_lines.append(f"  {c['id']}. {c['player']} · {c['cause']}")
            msg_lines.append("")
            msg_lines.append("周四 23:59 开奖，最高票玩家获得「💀 本周最惨」徽章展示在卡片上。")

            msg = "\n".join(msg_lines)
            print(f"[WeeklyShameVote] 发起投票:\n{msg}")
            if self.send_to_qq:
                self.send_to_qq(msg)

    def record_vote(self, qq_user_id: str, text: str):
        """处理 QQ 群消息：如果是单数字 1/2/3 且投票进行中，累计票数。

        从 qq_bridge 的 on_qq_message 里调用。
        """
        if not self._candidates:
            return  # 没有正在进行的投票

        # 只接受纯数字回复（去掉空格）
        stripped = text.strip()
        if not stripped.isdigit():
            return

        vote_id = int(stripped)
        with self._lock:
            if vote_id not in self._votes:
                return
            if qq_user_id in self._voters:
                # 同一人不能重复投票
                return
            self._voters.add(qq_user_id)
            self._votes[vote_id] += 1
            print(f"[WeeklyShameVote] {qq_user_id} 投给 {vote_id}，当前票数: {self._votes}")

    def end_vote(self):
        """周四 23:59 调用：统计结果 + 写入 weekly_shame.json + 发群通告。"""
        with self._lock:
            if not self._candidates:
                print("[WeeklyShameVote] 本周无投票可结算")
                return

            # 选最高票的候选
            winner_id = max(self._votes, key=self._votes.get)
            winner_candidate = next(c for c in self._candidates if c["id"] == winner_id)
            winner_votes = self._votes[winner_id]

            # 写结果到 shared json
            result = {
                "week": datetime.now().isocalendar()[1],
                "winner": winner_candidate["player"],
                "cause": winner_candidate["cause"],
                "votes": winner_votes,
                "candidates": self._candidates,
                "tally": self._votes,
            }
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            self.output_path.write_text(
                json.dumps(result, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"[WeeklyShameVote] 开奖: {winner_candidate['player']} 以 {winner_votes} 票获胜")

            # 发 QQ 群通告
            if self.send_to_qq:
                total_votes = sum(self._votes.values())
                msg = (
                    f"🏆【本周最惨死法开奖】\n\n"
                    f"本周「💀 最惨死法」得主是——\n"
                    f"  {winner_candidate['player']}\n"
                    f"  死于：{winner_candidate['cause']}\n"
                    f"  {winner_votes} / {total_votes} 票\n\n"
                    f"徽章已挂在他的玩家卡片上（mc.involutionhell.com）"
                )
                self.send_to_qq(msg)

            # 清空状态，等下周重开
            self._candidates = []
            self._votes = {}
            self._voters = set()

    # ====== 后台定时线程 ======

    def _scheduler_loop(self):
        """每分钟检查一次。周一 10:00 开投，周四 23:59 开奖。"""
        while True:
            now = datetime.now()
            week = now.isocalendar()[1]

            # 周一 10:00 开始投票（isoweekday == 1）
            if (
                now.isoweekday() == 1
                and now.hour == self.vote_start_hour
                and self._vote_started_week != week
            ):
                self._vote_started_week = week
                try:
                    self.start_vote()
                except Exception as e:
                    print(f"[WeeklyShameVote] start_vote 出错: {e}")

            # 周四 23:00-23:59 开奖（isoweekday == 4）
            if (
                now.isoweekday() == 4
                and now.hour == self.vote_end_hour
                and self._vote_ended_week != week
            ):
                self._vote_ended_week = week
                try:
                    self.end_vote()
                except Exception as e:
                    print(f"[WeeklyShameVote] end_vote 出错: {e}")

            time.sleep(60)

    def start(self):
        """启动后台调度线程。"""
        t = threading.Thread(target=self._scheduler_loop, daemon=True)
        t.start()
        print(
            f"[WeeklyShameVote] 本周最惨投票定时器已启动"
            f"（周一 {self.vote_start_hour}:00 开投，周四 {self.vote_end_hour}:59 开奖）"
        )
