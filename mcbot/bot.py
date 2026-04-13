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

CMD_PATTERN = re.compile(r"\[CMD:(.*?)\]")

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
            afk_timeout=afk_timeout,
        )
        self.system_prompt = build_system_prompt(
            bot_name=config.bot.name,
            language=config.bot.language,
            max_reply_length=config.bot.max_reply_length,
            custom_prompt=config.bot.system_prompt,
        )
        self.chat_histories: dict[str, list[dict]] = {}
        self.max_history = config.bot.max_history

    def get_reply(self, player: str, message: str) -> str:
        """Get AI reply for a player message."""
        if player not in self.chat_histories:
            self.chat_histories[player] = []

        history = self.chat_histories[player]
        history.append({"role": "user", "content": f"[{player}]: {message}"})

        if len(history) > self.max_history:
            self.chat_histories[player] = history[-self.max_history :]
            history = self.chat_histories[player]

        reply = self.ai.chat(history, self.system_prompt)
        if reply is None:
            return "..."

        history.append({"role": "assistant", "content": reply})
        return reply

    def process_reply(self, reply: str) -> str:
        """Extract and execute [CMD:...] tags, return text-only reply."""
        commands = CMD_PATTERN.findall(reply)
        text = CMD_PATTERN.sub("", reply).strip()

        for cmd in commands:
            cmd = cmd.strip()
            print(f"[MCBot] Executing: /{cmd}")
            result = self.rcon.send(cmd)
            if result:
                print(f"[MCBot] Result: {result}")

        return text

    def say(self, message: str):
        """Send a message to the game chat."""
        self.rcon.say(self.bot_name, message)

    def _afk_checker(self):
        """Background thread to check for AFK players."""
        while True:
            time.sleep(30)
            messages = self.events.check_afk()
            for msg in messages:
                print(f"[MCBot] AFK: {msg}")
                self.say(msg)

    def run(self):
        """Main bot loop."""
        log_path = Path(self.config.server_dir) / self.config.log_file

        print(f"[MCBot] Chat bot started!")
        print(f"[MCBot] Bot name: {self.bot_name}")
        print(f"[MCBot] AI: {self.config.ai.provider} ({self.config.ai.model})")
        print(f"[MCBot] Log: {log_path}")
        print(f"[MCBot] Events: death roasts, join greetings, AFK detection")

        if not log_path.exists():
            print(f"[MCBot] Waiting for log file: {log_path}")
            while not log_path.exists():
                time.sleep(5)

        # Start AFK checker thread
        afk_thread = threading.Thread(target=self._afk_checker, daemon=True)
        afk_thread.start()

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

                    # Check AFK return
                    return_msg = self.events.on_player_chat(player)
                    if return_msg:
                        self.say(return_msg)

                    reply = self.get_reply(player, message)
                    print(f"[MCBot] -> {reply}")

                    text = self.process_reply(reply)
                    if text:
                        self.say(text)
                    continue

                # Player join
                match = JOIN_PATTERN.match(line)
                if match:
                    player = match.group(1)
                    print(f"[MCBot] {player} joined")
                    msg = self.events.on_player_join(player)
                    self.say(msg)
                    continue

                # Player leave
                match = LEAVE_PATTERN.match(line)
                if match:
                    player = match.group(1)
                    print(f"[MCBot] {player} left")
                    self.events.on_player_leave(player)
                    continue

                # Player death
                match = DEATH_PATTERN.match(line)
                if match:
                    player = match.group(1)
                    print(f"[MCBot] {player} died")
                    msg = self.events.on_player_death(player, line)
                    self.say(msg)
                    continue

                # Advancement
                match = ADVANCEMENT_PATTERN.match(line)
                if match:
                    player, advancement = match.group(1), match.group(2)
                    print(f"[MCBot] {player} got advancement: {advancement}")
                    self.events.player_activity[player] = time.time()
                    lang = self.config.bot.language
                    if lang == "zh":
                        self.say(f"恭喜 {player} 解锁成就 [{advancement}]!")
                    else:
                        self.say(f"GG {player}! Achievement unlocked: [{advancement}]!")
