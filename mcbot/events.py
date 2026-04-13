"""Player event reactions - no AI needed, uses pre-written messages."""

import random
import re
import time

DEATH_MESSAGES_ZH = {
    "was slain": [
        "{player} 被怪物教训了！下次记得带盾牌",
        "{player} 又送人头了...要不要我给你套装备？",
        "{player} 被揍扁了！需要武器吗？",
    ],
    "burned": [
        "{player} 变成烤肉了...记得带消防桶啊",
        "{player} 太热情了，直接自燃了",
        "{player} 这是在cos烈焰人吗？",
    ],
    "drowned": [
        "{player} 你是旱鸭子吧...要不要水下呼吸药水？",
        "{player} 忘记换气了！",
    ],
    "fell": [
        "{player} 以为自己有翅膀？给你个缓降药水吧",
        "{player} 重力是真实存在的！",
        "{player} 这摔得够狠的...",
    ],
    "was blown": [
        "{player} 被苦力怕表白了（物理）",
        "{player} 和TNT亲密接触了一下",
        "{player} 变成了烟花！",
    ],
    "was shot": [
        "{player} 被当成靶子了...下次带盾牌",
        "{player} 吃了一箭！骷髅的射术又提高了",
    ],
    "starved": [
        "{player} 居然饿死了！这是荒野求生吗？要吃的吗？",
        "{player} 都忘了吃饭...太专注了",
    ],
    "suffocated": [
        "{player} 被夹成饼了！",
        "{player} 你挖矿的时候要注意头顶啊",
    ],
    "hit the ground": [
        "{player} 和大地来了一个深情拥抱",
        "{player} 测试摔落伤害...结论：很高",
    ],
    "tried to swim": [
        "{player} 在岩浆里游泳？大胆的想法",
        "{player} 这不是温泉！是岩浆！",
    ],
    "default": [
        "{player} 又双叒叕死了...",
        "{player} 你还好吗？需要帮助不？",
        "RIP {player}，安息吧（才怪）",
        "{player} 这已经是第几次了？",
    ],
}

DEATH_MESSAGES_EN = {
    "was slain": [
        "{player} got wrecked! Need some gear?",
        "{player} needs combat training...",
    ],
    "burned": [
        "{player} got cooked! Bring a water bucket next time",
        "{player} is now well-done...",
    ],
    "fell": [
        "{player} forgot they can't fly!",
        "{player} gravity check: confirmed",
    ],
    "was blown": [
        "{player} got a Creeper hug!",
        "{player} went boom!",
    ],
    "default": [
        "RIP {player}... need help?",
        "{player} down again! Want some gear?",
    ],
}

JOIN_MESSAGES_ZH = [
    "欢迎 {player}！我是{bot}，你的 AI 助手，有事跟我说~",
    "{player} 来了！今天想玩什么？跟{bot}说一声~",
    "欢迎回来 {player}！{bot}随时为你效劳！",
]

JOIN_MESSAGES_EN = [
    "Welcome {player}! I'm {bot}, your AI assistant. Talk to me!",
    "{player} is here! What's the plan today? Ask {bot}!",
]

AFK_MESSAGES_ZH = [
    "{player} 发呆 {minutes} 分钟了...还活着吗？",
    "{player} 你是不是去吃饭了？都 {minutes} 分钟了",
    "{player} 挂机中...要不要我帮你看家？",
    "有人在吗？{player} 已经站了 {minutes} 分钟的桩了",
]

AFK_MESSAGES_EN = [
    "{player} has been AFK for {minutes} minutes... still there?",
    "Hello? {player}? It's been {minutes} minutes...",
]

AFK_RETURN_ZH = [
    "{player} 终于回来了！欢迎回归",
    "{player} 活过来了！",
]

AFK_RETURN_EN = [
    "{player} is back! Welcome back!",
    "{player} has returned from the void!",
]


class EventHandler:
    """Handles player events with pre-written messages (no AI cost)."""

    def __init__(self, bot_name: str, language: str, afk_timeout: int = 300):
        self.bot_name = bot_name
        self.language = language
        self.afk_timeout = afk_timeout

        # Track player activity: {player: last_active_timestamp}
        self.player_activity: dict[str, float] = {}
        # Track who we already warned about AFK
        self.afk_warned: set[str] = set()
        # Track online players
        self.online_players: set[str] = set()

    def on_player_join(self, player: str) -> str:
        """Generate join message."""
        self.online_players.add(player)
        self.player_activity[player] = time.time()
        self.afk_warned.discard(player)

        messages = JOIN_MESSAGES_ZH if self.language == "zh" else JOIN_MESSAGES_EN
        return random.choice(messages).format(player=player, bot=self.bot_name)

    def on_player_leave(self, player: str):
        """Track player leaving."""
        self.online_players.discard(player)
        self.player_activity.pop(player, None)
        self.afk_warned.discard(player)

    def on_player_chat(self, player: str):
        """Update activity on chat."""
        self.player_activity[player] = time.time()
        if player in self.afk_warned:
            self.afk_warned.discard(player)
            messages = AFK_RETURN_ZH if self.language == "zh" else AFK_RETURN_EN
            return random.choice(messages).format(player=player)
        return None

    def on_player_death(self, player: str, log_line: str) -> str:
        """Generate death roast message."""
        self.player_activity[player] = time.time()
        deaths = DEATH_MESSAGES_ZH if self.language == "zh" else DEATH_MESSAGES_EN

        # Find matching death cause
        for cause, messages in deaths.items():
            if cause == "default":
                continue
            if cause in log_line:
                return random.choice(messages).format(player=player)

        return random.choice(deaths["default"]).format(player=player)

    def check_afk(self) -> list[str]:
        """Check for AFK players, return messages to send."""
        messages = []
        now = time.time()

        for player in list(self.online_players):
            last_active = self.player_activity.get(player, now)
            idle_seconds = now - last_active

            if idle_seconds >= self.afk_timeout and player not in self.afk_warned:
                self.afk_warned.add(player)
                minutes = int(idle_seconds // 60)
                afk_msgs = AFK_MESSAGES_ZH if self.language == "zh" else AFK_MESSAGES_EN
                msg = random.choice(afk_msgs).format(player=player, minutes=minutes)
                messages.append(msg)

        return messages
