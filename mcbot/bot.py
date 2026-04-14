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

CMD_PATTERN = re.compile(r"\[CMD:(.*?)\]")
REMEMBER_PATTERN = re.compile(r"^remember\s+(\S+)\s+(.+)$", re.IGNORECASE)
FORGET_PATTERN = re.compile(r"^forget\s+(\S+)\s+(.+)$", re.IGNORECASE)

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

    def process_reply(self, reply: str) -> str:
        """Extract and execute [CMD:...] tags, return text-only reply with command results."""
        import re as _re
        commands = CMD_PATTERN.findall(reply)
        text = CMD_PATTERN.sub("", reply).strip()
        results = []

        for cmd in commands:
            cmd = cmd.strip()

            m = REMEMBER_PATTERN.match(cmd)
            if m:
                target, fact = m.group(1), m.group(2).strip()
                added = self.memory.add_fact(target, fact)
                print(f"[MCBot] {'Remembered' if added else 'Already knew'}: {target} -> {fact}")
                continue
            m = FORGET_PATTERN.match(cmd)
            if m:
                target, key = m.group(1), m.group(2).strip()
                removed = self.memory.forget_fact(target, key)
                print(f"[MCBot] {'Forgot' if removed else 'No match to forget'}: {target} / {key}")
                continue

            print(f"[MCBot] Executing: /{cmd}")
            result = self.rcon.send(cmd)
            if result:
                # Strip ANSI color codes from RCON output
                result = _re.sub(r"\x1b\[[0-9;]*m|\[0m", "", result).strip()
                print(f"[MCBot] Result: {result}")
                results.append(result)

        if results:
            text = text + " " + " | ".join(results) if text else " | ".join(results)

        return text

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

        # Start background status poller
        poller = threading.Thread(target=self._status_poller, daemon=True)
        poller.start()

        with open(log_path, "r") as f:
            f.seek(0, 2)  # Skip to end
            print("[MCBot] Monitoring chat...")

            while True:
                line = f.readline()
                if not line:
                    time.sleep(0.5)
                    continue

                line = line.strip()
                if not line:
                    continue

                # Player chat
                match = CHAT_PATTERN.match(line)
                if match:
                    player, message = match.group(1), match.group(2)
                    print(f"[MCBot] {player}: {message}")

                    # Forward to QQ
                    if self.qq:
                        self.qq.forward_mc_event("chat", f"<{player}> {message}")

                    # Check AFK return
                    return_msg = self.events.on_player_chat(player)
                    if return_msg:
                        self.say(return_msg)

                    text = self.converse(player, message)
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
                    continue

                # Player leave
                match = LEAVE_PATTERN.match(line)
                if match:
                    player = match.group(1)
                    print(f"[MCBot] {player} left")
                    self.stats.on_leave(player)
                    self.events.on_player_leave(player)
                    continue

                # Player death
                match = DEATH_PATTERN.match(line)
                if match:
                    player = match.group(1)
                    cause = match.group(2)
                    print(f"[MCBot] {player} died")
                    self.stats.on_death(player, cause)
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
