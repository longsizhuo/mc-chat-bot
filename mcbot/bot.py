"""Main chat bot loop - monitors server log and responds via RCON."""

import re
import threading
import time
from pathlib import Path

from .config import Config
from .events import EventHandler
from .providers import AIProvider
from .rcon import RCON
from .abilities import build_system_prompt
from .stats import PlayerStats
from .qq_bridge import QQBridge
from .memory import Memory
from .registry import Registry
from .weekly_diary import WeeklyDiary
from .weekly_deaths import WeeklyDeaths
from .weekly_shame_vote import WeeklyShameVote
from .random_roast import RandomRoast
from .daily_prophecy import DailyProphecy
from .weekly_mystery import WeeklyMystery
from .landmarks import LandmarksManager
from .messageboard import MessageBoard
from .ingame_vote import InGameVote
from .death_heatmap import DeathHeatmap

CMD_PATTERN = re.compile(r"\[CMD:(.*?)\]")
REMEMBER_PATTERN = re.compile(r"^remember\s+(\S+)\s+(.+)$", re.IGNORECASE)
FORGET_PATTERN = re.compile(r"^forget\s+(\S+)\s+(.+)$", re.IGNORECASE)
FIND_PATTERN = re.compile(r"^find(?:\s+(item|block))?\s+(.+)$", re.IGNORECASE)

# Rare advancements worth forwarding to QQ
RARE_ADVANCEMENTS = {
    "The End?", "The End.", "Free the End",
    "You Need a Mint", "Is It a Plane?", "Withering Heights",
    "Beaconator", "A Balanced Diet", "Serious Dedication",
    "How Did We Get Here?", "Adventuring Time", "Two by Two",
    "Cover Me in Debris", "Uneasy Alliance",
    "Return to Sender", "A Terrible Fortress",
    "Spooky Scary Skeleton", "Subspace Bubble",
    "Hidden in the Depths", "Country Lode, Take Me Home",
    "Voluntary Exile", "Hero of the Village",
    "Star Trader", "Smithing with Style",
    "The Parrots and the Bats", "Monsters Hunted",
    # Chinese names
    "结束了？", "结束了。", "解放末地",
    "信标工程师", "均衡饮食", "隆重献礼",
    "这是怎么回事？", "探索的时间到了",
    "深层残骸", "不安的同盟", "以彼之道",
    "恐怖堡垒", "亚空间泡泡",
    "自愿流放", "村庄英雄",
}

# Death streak thresholds that are worth forwarding to QQ
QQ_DEATH_STREAK_THRESHOLD = 3

CHAT_PATTERN = re.compile(
    r"\[.*?\] \[Server thread/INFO\]: (?:\[Not Secure\] )?<(\w+)> (.+)"
)
JOIN_PATTERN = re.compile(
    r"\[.*?\] \[Server thread/INFO\]: (\w+) joined the game"
)
LEAVE_PATTERN = re.compile(
    r"\[.*?\] \[Server thread/INFO\]: (\w+) left the game"
)
DEATH_PATTERN = re.compile(
    r"\[.*?\] \[Server thread/INFO\]: (\w+) "
    r"(was slain|was shot|burned|drowned|fell|was blown|hit the ground|"
    r"was killed|was squashed|starved|suffocated|was impaled|was fireballed|"
    r"withered|died|was poked|was pricked|tried to swim|walked into)"
)
ADVANCEMENT_PATTERN = re.compile(
    r"\[.*?\] \[Server thread/INFO\]: (\w+) has made the advancement \[(.+)\]"
)

# Polling interval for RCON status checks (seconds)
POLL_INTERVAL = 15

# 空服达到此秒数后，下次首人上线会播报到 QQ 群（默认 1 小时）
EMPTY_SERVER_THRESHOLD_SECONDS = 3600


class ChatBot:
    def __init__(self, config: Config):
        self.config = config
        self.ai = AIProvider(config.ai)
        self.rcon = RCON(config.rcon)
        self.bot_name = config.bot.name

        events_cfg = getattr(config, "events", None)
        afk_timeout = 300
        if events_cfg and hasattr(events_cfg, "afk_timeout"):
            afk_timeout = events_cfg.afk_timeout

        self.events = EventHandler(
            bot_name=config.bot.name,
            language=config.bot.language,
            rcon=self.rcon,
            afk_timeout=afk_timeout,
        )
        self.stats = PlayerStats(config.server_dir)
        self.qq: QQBridge | None = None
        if config.qq.enabled and config.qq.group_id:
            self.qq = QQBridge(
                api_url=config.qq.api_url,
                group_id=config.qq.group_id,
                ws_port=config.qq.ws_port,
                bot_name=config.bot.name,
                on_qq_message=self._on_qq_message,
            )
        self.system_prompt = build_system_prompt(
            bot_name=config.bot.name,
            language=config.bot.language,
            max_reply_length=config.bot.max_reply_length,
            custom_prompt=config.bot.system_prompt,
        )
        self.qq_system_prompt = build_system_prompt(
            bot_name=config.bot.name,
            language=config.bot.language,
            max_reply_length=500,
            custom_prompt="你现在在QQ群里和玩家聊天，不受Minecraft聊天框字数限制，可以写更详细的回复。",
        )
        memory_path = Path(config.bot.memory_dir)
        if not memory_path.is_absolute():
            memory_path = Path(config.server_dir) / memory_path
        self.memory = Memory(
            memory_dir=memory_path,
            max_history=config.bot.max_history,
            max_facts=config.bot.max_facts,
        )
        self.max_history = config.bot.max_history
        print(f"[MCBot] Memory: {memory_path}")

        registry_path = Path(__file__).parent.parent / "data" / "registry.json"
        try:
            self.registry = Registry(registry_path)
            print(f"[MCBot] Registry: v{self.registry.version} ({len(self.registry.items)} items, {len(self.registry.blocks)} blocks)")
        except Exception as e:
            print(f"[MCBot] Registry disabled: {e}")
            self.registry = None

        # 小方日记推送（周日 22:00，替代原古风史诗 chronicle）
        logs_dir = str(Path(config.server_dir) / "logs")
        self.weekly_diary = WeeklyDiary(
            logs_dir=logs_dir,
            ai_provider=self.ai,
            send_to_qq=self.qq.send_to_qq if self.qq else None,
        )

        # 每周死亡集锦推送（周一 09:00）
        self.weekly_deaths = WeeklyDeaths(
            logs_dir=logs_dir,
            ai_provider=self.ai,
            send_to_qq=self.qq.send_to_qq if self.qq else None,
        )

        # 小方找茬（每小时摇骰子，白天随机触发；期望 2-3 天一次）
        stats_path_for_roast = str(Path(config.server_dir) / "player_stats.json")
        self.random_roast = RandomRoast(
            stats_path=stats_path_for_roast,
            ai_provider=self.ai,
            send_to_qq=self.qq.send_to_qq if self.qq else None,
        )

        # 小方今日预言（8:00 发 / 23:00 验证）
        prophecy_state = str(Path(__file__).parent.parent / "data" / "today_prophecy.json")
        self.daily_prophecy = DailyProphecy(
            stats_path=stats_path_for_roast,
            logs_dir=logs_dir,
            state_path=prophecy_state,
            ai_provider=self.ai,
            send_to_qq=self.qq.send_to_qq if self.qq else None,
        )

        # 玩家留言板（网站发留言，玩家上线时游戏内播报）
        # 同时给网站提供 /api/online 端点（当前在线 + 本次会话时长）
        messages_path = str(Path(__file__).parent.parent / "data" / "messages.json")

        def _online_provider():
            """给 /api/online 用：从 events.online_players + stats 里组装数据。"""
            result = []
            now = time.time()
            players_data = self.stats.data.get("players", {})
            for name in list(self.events.online_players):
                p = players_data.get(name, {})
                join_time = p.get("_join_time")
                session_seconds = int(now - join_time) if join_time else 0
                result.append({
                    "name": name,
                    "session_seconds": session_seconds,
                })
            # 按在线时长降序（最久的在前）
            result.sort(key=lambda x: -x["session_seconds"])
            return result

        self.messageboard = MessageBoard(
            storage_path=messages_path,
            rcon=self.rcon,
            bot_name=self.bot_name,
            online_provider=_online_provider,
            deaths_provider=lambda: self.death_heatmap.list_all(),
        )

        # 死亡热点地图（死亡时异步查 LastDeathLocation，存坐标给前端画热力图）
        deaths_path = str(Path(__file__).parent.parent / "data" / "deaths.json")
        self.death_heatmap = DeathHeatmap(
            storage_path=deaths_path,
            rcon=self.rcon,
        )

        # 游戏内民主投票（游戏内命令：投票 xxx / +1 / -1，30 秒决断）
        self.ingame_vote = InGameVote(
            rcon=self.rcon,
            bot_name=self.bot_name,
        )

        # 玩家地标系统（游戏内命令：标记 / 去哪 / 地标 / 删除地标）
        landmarks_path = str(Path(__file__).parent.parent / "data" / "landmarks.json")
        self.landmarks = LandmarksManager(
            storage_path=landmarks_path,
            rcon=self.rcon,
        )

        # 本周悬案（周三 19:00 推送）
        self.weekly_mystery = WeeklyMystery(
            logs_dir=logs_dir,
            ai_provider=self.ai,
            send_to_qq=self.qq.send_to_qq if self.qq else None,
        )

        # 本周最惨死法投票（周一 10:00 开投 / 周四 23:59 开奖）
        # 结果写到 minecraft-server 目录，已通过 deploy 脚本软链到 /srv/mc/weekly_shame.json
        shame_output = str(Path(config.server_dir) / "weekly_shame.json")
        self.weekly_shame = WeeklyShameVote(
            logs_dir=logs_dir,
            output_path=shame_output,
            send_to_qq=self.qq.send_to_qq if self.qq else None,
        )

        # "首人上线"播报状态：仅在空服 1 小时后首个玩家加入时推送到 QQ 群
        # last_empty_time 记录上次服务器空人的时间戳
        self._last_empty_time = time.time()
        self._online_count = 0

        # 启动时强制断言的 gamerule / 命令（让 keep_inventory 等不会因误操作被关掉）
        startup_cmds = list(getattr(config.bot, "startup_commands", []) or [])
        if startup_cmds:
            threading.Thread(target=self._run_startup_commands,
                             args=(startup_cmds,), daemon=True).start()

    def _run_startup_commands(self, commands: list):
        """启动后带重试地执行一次性命令（MC 服务器可能还在加载世界，需要等）。"""
        # 等 MC 世界加载：最多重试 30 次 × 5 秒 = 2.5 分钟
        for attempt in range(30):
            probe = self.rcon.send("list")
            if probe and "players online" in probe:
                break
            time.sleep(5)
        else:
            print("[MCBot] startup: RCON never came up, skipping startup_commands")
            return
        for cmd in commands:
            out = self.rcon.send(cmd) or ""
            out = out.replace("\x1b[0m", "").strip()
            print(f"[MCBot] startup: /{cmd} -> {out}")

    def _build_prompt_with_facts(self, base_prompt: str, player: str) -> str:
        facts = self.memory.get_facts(player)
        if not facts:
            return base_prompt
        facts_text = "\n".join(f"- {f}" for f in facts)
        if self.config.bot.language == "zh":
            header = f"\n\n## 关于玩家 {player} 你记得的事（长期记忆）\n{facts_text}\n重要：利用这些信息，主动体现你记得他。需要新增记忆时用 [CMD:remember {player} <内容>]，过时了用 [CMD:forget {player} <关键词或序号>]。"
        else:
            header = f"\n\n## What you remember about {player} (long-term memory)\n{facts_text}\nUse these facts naturally. To add: [CMD:remember {player} <fact>]. To remove: [CMD:forget {player} <keyword or index>]."
        return base_prompt + header

    def get_reply(self, player: str, message: str, from_qq: bool = False) -> str:
        """Get AI reply for a player message."""
        history = self.memory.append_history(
            player, "user", f"[{player}]: {message}"
        )

        base = self.qq_system_prompt if from_qq else self.system_prompt
        prompt = self._build_prompt_with_facts(base, player)
        reply = self.ai.chat(history, prompt)
        if reply is None:
            return "..."

        self.memory.append_history(player, "assistant", reply)
        return reply

    def converse(self, player: str, message: str, from_qq: bool = False) -> str:
        """Full tool-use loop: AI reply → execute [CMD:...] → feed results back → repeat.

        Stops when the AI emits no commands, or after MAX_TOOL_ROUNDS rounds.
        Returns the concatenated visible text from all rounds.
        """
        import re as _re

        self.memory.append_history(player, "user", f"[{player}]: {message}")
        base = self.qq_system_prompt if from_qq else self.system_prompt
        prompt = self._build_prompt_with_facts(base, player)

        visible_parts: list[str] = []

        max_rounds = self.config.bot.max_tool_rounds
        for round_idx in range(max_rounds):
            history = self.memory.get_history(player)
            reply = self.ai.chat(history, prompt)
            if reply is None:
                break

            self.memory.append_history(player, "assistant", reply)

            commands = CMD_PATTERN.findall(reply)
            text = CMD_PATTERN.sub("", reply).strip()
            if text:
                visible_parts.append(text)

            if not commands:
                break

            results: list[str] = []
            for cmd in commands:
                cmd = cmd.strip()

                m = REMEMBER_PATTERN.match(cmd)
                if m:
                    target, fact = m.group(1), m.group(2).strip()
                    added = self.memory.add_fact(target, fact)
                    print(f"[MCBot] {'Remembered' if added else 'Already knew'}: {target} -> {fact}")
                    results.append(f"{cmd} -> {'ok' if added else 'duplicate'}")
                    continue
                m = FORGET_PATTERN.match(cmd)
                if m:
                    target, key = m.group(1), m.group(2).strip()
                    removed = self.memory.forget_fact(target, key)
                    print(f"[MCBot] {'Forgot' if removed else 'No match to forget'}: {target} / {key}")
                    results.append(f"{cmd} -> {'ok' if removed else 'no match'}")
                    continue
                m = FIND_PATTERN.match(cmd)
                if m and self.registry is not None:
                    kind = (m.group(1) or "any").lower()
                    query = m.group(2).strip()
                    matches = self.registry.find(query, kind=kind, limit=12)
                    matches_str = ", ".join(matches) if matches else "(no matches)"
                    print(f"[MCBot] Find '{query}' ({kind}): {matches_str}")
                    results.append(f"find {kind} '{query}' -> {matches_str}")
                    continue

                print(f"[MCBot] Executing: /{cmd}")
                result = self.rcon.send(cmd) or ""
                result = _re.sub(r"\x1b\[[0-9;]*m|\[0m", "", result).strip()
                print(f"[MCBot] Result: {result}")
                results.append(f"{cmd} -> {result if result else 'ok'}")

            # Feed results back for next round. If this was the last round,
            # still surface the last visible results inline.
            if round_idx == max_rounds - 1:
                # No more rounds to act on results — append condensed info to text
                brief = " | ".join(r for r in results if r)
                if brief:
                    visible_parts.append(brief)
                break

            result_msg = "[CMD_RESULT]\n" + "\n".join(results)
            self.memory.append_history(player, "user", result_msg)

        return " ".join(p for p in visible_parts if p).strip() or "..."

    def say(self, message: str, forward_qq: bool = True):
        """Send a message to the game chat and optionally forward to QQ."""
        self.rcon.say(self.bot_name, message)
        if forward_qq and self.qq:
            self.qq.forward_mc_event("bot", f"[{self.bot_name}] {message}")

    def _on_qq_message(self, nickname: str, message: str):
        """Handle message from QQ group → AI reply + forward to both MC and QQ."""
        # Strip CQ codes (at mentions etc.)
        import re
        clean_msg = re.sub(r"\[CQ:[^\]]+\]", "", message).strip()
        if not clean_msg:
            return

        # 优先：如果是纯数字 1/2/3 且有活跃投票，走投票记录（不走 AI 不转发）
        if clean_msg in {"1", "2", "3"} and self.weekly_shame._candidates:
            self.weekly_shame.record_vote(nickname, clean_msg)
            return

        # Show QQ message in MC game chat
        self.rcon.say(f"QQ·{nickname}", clean_msg)

        # Get AI reply with longer limit for QQ (tool-use loop)
        qq_player = f"QQ:{nickname}"
        text = self.converse(qq_player, clean_msg, from_qq=True)
        print(f"[MCBot] QQ {nickname} -> {text}")

        if text:
            # Send reply to MC game chat
            self.rcon.say(self.bot_name, text)
            # Send reply back to QQ group
            if self.qq:
                self.qq.send_to_qq(f"[{self.bot_name}] {text}")

    def _status_poller(self):
        """Background thread: poll player states via RCON + check AFK/playtime."""
        while True:
            time.sleep(POLL_INTERVAL)

            if not self.events.online_players:
                continue

            # RCON state polling (health, food, dimension, etc.)
            try:
                messages = self.events.poll_player_states()
                for msg in messages:
                    print(f"[MCBot] Status: {msg}")
                    self.say(msg)
            except Exception as e:
                print(f"[MCBot] Poll error: {e}")

            # AFK check
            afk_messages = self.events.check_afk()
            for msg in afk_messages:
                print(f"[MCBot] AFK: {msg}")
                self.say(msg)

            # Playtime check
            playtime_messages = self.events.check_playtime()
            for msg in playtime_messages:
                print(f"[MCBot] Playtime: {msg}")
                self.say(msg)

    def run(self):
        """Main bot loop."""
        log_path = Path(self.config.server_dir) / self.config.log_file

        print(f"[MCBot] Chat bot started!")
        print(f"[MCBot] Bot name: {self.bot_name}")
        print(f"[MCBot] AI: {self.config.ai.provider} ({self.config.ai.model})")
        print(f"[MCBot] Log: {log_path}")
        print(f"[MCBot] Status polling every {POLL_INTERVAL}s")
        print(f"[MCBot] Events: death roasts, PvP, join/leave, AFK, playtime,")
        print(f"[MCBot]         low HP, hunger, dimension, altitude, level up")

        if not log_path.exists():
            print(f"[MCBot] Waiting for log file: {log_path}")
            while not log_path.exists():
                time.sleep(5)

        # Start QQ bridge if enabled
        if self.qq:
            self.qq.start_listener()
            print(f"[MCBot] QQ bridge enabled (group: {self.config.qq.group_id})")

        # 启动时通过 RCON 同步当前在线人数，避免 bot 重启后触发假的"首人上线"播报
        try:
            resp = self.rcon.send("list") or ""
            m = re.search(r"There are (\d+) of", resp)
            if m:
                self._online_count = int(m.group(1))
                if self._online_count > 0:
                    # 服务器本来就有人 → 不应该立刻播报
                    self._last_empty_time = time.time()
                print(f"[MCBot] Online count synced: {self._online_count}")
        except Exception as e:
            print(f"[MCBot] Online count sync failed: {e}")

        # Start background status poller
        poller = threading.Thread(target=self._status_poller, daemon=True)
        poller.start()

        # 启动小方日记定时器（周日 22:00）
        self.weekly_diary.start()

        # 启动每周死亡集锦定时器（周一 09:00）
        self.weekly_deaths.start()

        # 启动本周最惨投票定时器（周一 10:00 / 周四 23:59）
        self.weekly_shame.start()

        # 启动小方找茬随机定时器
        self.random_roast.start()

        # 启动今日预言定时器（早 8:00 / 晚 23:00）
        self.daily_prophecy.start()

        # 启动本周悬案定时器（周三 19:00）
        self.weekly_mystery.start()

        # 启动留言板 HTTP 服务（接收网站 POST / 提供 GET）
        self.messageboard.start()

        # logrotate 兼容：记录当前打开文件的 inode，定期检查 latest.log 是否被轮转
        # （Minecraft 在日期切换或 stop-start 时会把 latest.log 压成 .gz 并 new 一个）
        import os as _os

        def _open_at_tail(path):
            fh = open(path, "r", encoding="utf-8", errors="ignore")
            fh.seek(0, 2)
            ino = _os.fstat(fh.fileno()).st_ino
            return fh, ino

        f, f_ino = _open_at_tail(log_path)
        print("[MCBot] Monitoring chat...")

        while True:
            line = f.readline()
            if not line:
                time.sleep(0.5)
                # 检查 latest.log 是否被轮转（inode 变化 or 文件比当前 offset 短）
                try:
                    new_stat = _os.stat(log_path)
                    if new_stat.st_ino != f_ino or new_stat.st_size < f.tell():
                        print(f"[MCBot] latest.log 被轮转/截断，重新打开")
                        try:
                            f.close()
                        except Exception:
                            pass
                        # 轮转后新文件从头读（别跳到末尾，否则错过前几秒消息）
                        f = open(log_path, "r", encoding="utf-8", errors="ignore")
                        f_ino = _os.fstat(f.fileno()).st_ino
                except FileNotFoundError:
                    # 文件暂时不存在（轮转中间态），短等后重试
                    time.sleep(1)
                continue

            line = line.strip()
            if not line:
                continue

            # Player chat
            match = CHAT_PATTERN.match(line)
            if match:
                player, message = match.group(1), match.group(2)
                print(f"[MCBot] {player}: {message}")

                # Forward to QQ（即使没 @ 小方也要转发，让 QQ 群看得到游戏内讨论）
                if self.qq:
                    self.qq.forward_mc_event("chat", f"<{player}> {message}")

                # Check AFK return
                return_msg = self.events.on_player_chat(player)
                if return_msg:
                    self.say(return_msg)

                # 游戏内投票命令优先级最高（投票 xxx / +1 / -1）
                vote_reply = self.ingame_vote.try_handle(player, message)
                if vote_reply is not None:
                    if vote_reply:  # 空串表示内部已处理（+1/-1），不需要再 say
                        self.say(vote_reply)
                    continue

                # 地标系统命令匹配（标记 / 去哪 / 地标 / 删除地标）
                landmark_reply = self.landmarks.try_handle(player, message)
                if landmark_reply is not None:
                    self.say(landmark_reply)
                    continue

                # 只有显式召唤小方时才走 AI，避免每句聊天都被回复刷屏
                # 支持格式：@小方 xxx / @小方xxx / 小方xxx / @bot_name xxx
                stripped = message.strip()
                summons = [f"@{self.bot_name}", self.bot_name]
                invoked = False
                query = ""
                for s in summons:
                    if stripped.startswith(s):
                        query = stripped[len(s):].lstrip(" ,，:：").strip()
                        invoked = True
                        break
                if not invoked:
                    continue  # 普通聊天不触发 AI

                if not query:
                    # 被 @ 但没说具体问题，给个礼貌回应而不是塞给 AI
                    self.say("叫我？有啥事直说。")
                    continue

                text = self.converse(player, query)
                print(f"[MCBot] -> {text}")

                if text:
                    self.say(text)
                continue

            # Player join
            match = JOIN_PATTERN.match(line)
            if match:
                player = match.group(1)
                print(f"[MCBot] {player} joined")
                self.stats.on_join(player)
                msg = self.events.on_player_join(player)
                self.say(msg, forward_qq=False)

                # 给上线玩家念出他未听过的留言（稍等 2 秒让欢迎消息先到）
                def _announce_later(p=player):
                    time.sleep(2)
                    try:
                        self.messageboard.announce_to_player(p)
                    except Exception as e:
                        print(f"[MCBot] 留言播报失败: {e}")
                threading.Thread(target=_announce_later, daemon=True).start()

                # 0→1 首人上线播报：仅当服务器空了足够久（默认1小时）后
                # 第一个玩家加入才推送到 QQ 群
                now = time.time()
                empty_duration = now - self._last_empty_time
                was_empty = self._online_count == 0
                self._online_count += 1
                if (was_empty
                        and empty_duration >= EMPTY_SERVER_THRESHOLD_SECONDS
                        and self.qq):
                    self.qq.send_to_qq(
                        f"🎮 {player} 上线了，服务器复活 · 快来一起玩"
                    )
                continue

            # Player leave
            match = LEAVE_PATTERN.match(line)
            if match:
                player = match.group(1)
                print(f"[MCBot] {player} left")
                self.stats.on_leave(player)
                self.events.on_player_leave(player)

                # 更新在线计数；降到 0 时记录"空服起始时间"
                self._online_count = max(0, self._online_count - 1)
                if self._online_count == 0:
                    self._last_empty_time = time.time()
                continue

            # Player death
            match = DEATH_PATTERN.match(line)
            if match:
                player = match.group(1)
                cause = match.group(2)
                print(f"[MCBot] {player} died")
                self.stats.on_death(player, cause)
                # 异步记录死亡坐标（延迟 2s 查 NBT）
                self.death_heatmap.record_death(player, cause)
                msg = self.events.on_player_death(player, line)
                # Only forward to QQ on death streaks (3+)
                recent = len(self.events.death_timestamps.get(player, []))
                forward_qq = recent >= QQ_DEATH_STREAK_THRESHOLD
                self.say(msg, forward_qq=forward_qq)
                continue

            # Advancement
            match = ADVANCEMENT_PATTERN.match(line)
            if match:
                player, advancement = match.group(1), match.group(2)
                print(f"[MCBot] {player} got advancement: {advancement}")
                self.stats.on_advancement(player, advancement)
                msg = self.events.on_advancement(player, advancement)
                # Only forward rare advancements to QQ
                is_rare = advancement in RARE_ADVANCEMENTS
                self.say(msg, forward_qq=is_rare)
                if is_rare and self.qq:
                    self.qq.forward_mc_event("advancement", msg)
