"""Player event reactions and status monitoring - no AI needed."""

import random
import re
import time

# ============================================================
# 死亡吐槽
# ============================================================

DEATH_MESSAGES_ZH = {
    "was slain by": [
        "{player} 被怪物教训了！下次记得带盾牌",
        "{player} 又送人头了...要不要我给你套装备？",
        "{player} 被揍扁了！需要武器吗？",
        "{player} 你打不过就跑啊！",
        "{player} 战术性阵亡（确信）",
        "{player} 这波是怪物的MVP",
        "{player} 建议提升一下走位技术",
        "{player} 你知道盾牌怎么用吗？",
    ],
    "burned": [
        "{player} 变成烤肉了...记得带消防桶啊",
        "{player} 太热情了，直接自燃了",
        "{player} 这是在cos烈焰人吗？",
        "{player} 烤{player}，外焦里嫩，来一份？",
        "{player} 温馨提示：火是烫的",
        "{player} 抗火药水了解一下？",
    ],
    "drowned": [
        "{player} 你是旱鸭子吧...要不要水下呼吸药水？",
        "{player} 忘记换气了！",
        "{player} 水里的东西不好惹啊",
        "{player} 建议学一下游泳",
        "{player} 氧气是好东西，希望你也有",
        "{player} 潜水冠军...反面的",
    ],
    "fell": [
        "{player} 以为自己有翅膀？给你个缓降药水吧",
        "{player} 重力是真实存在的！",
        "{player} 这摔得够狠的...",
        "{player} 从天而降！帅了一秒",
        "{player} 牛顿在此表示满意",
        "{player} 你听说过水桶MLG吗？",
        "{player} 落地成盒！",
    ],
    "was blown up": [
        "{player} 被苦力怕表白了（物理）",
        "{player} 和TNT亲密接触了一下",
        "{player} 变成了烟花！",
        "{player} 嘭！一切化为灰烬",
        "{player} 苦力怕：嗨~想我了吗？",
        "{player} 温馨提示：听到嘶嘶声要跑",
        "{player} 原地起飞，但没有降落伞",
    ],
    "was shot": [
        "{player} 被当成靶子了...下次带盾牌",
        "{player} 吃了一箭！骷髅的射术又提高了",
        "{player} 箭如雨下，你如靶心",
        "{player} 你是在练习接箭术吗？",
        "{player} 建议：别站着不动",
        "{player} 要不要给你一面盾？",
    ],
    "starved": [
        "{player} 居然饿死了！这是荒野求生吗？要吃的吗？",
        "{player} 都忘了吃饭...太专注了",
        "{player} 在MC里饿死真的很少见...",
        "{player} 你知道牛可以杀了吃肉吗？",
        "{player} 温饱问题都解决不了！",
        "{player} 这游戏有食物的你知道吧？",
    ],
    "suffocated": [
        "{player} 被夹成饼了！",
        "{player} 你挖矿的时候要注意头顶啊",
        "{player} 建议：别往沙子下面挖",
        "{player} 物理引擎表示：质量守恒",
        "{player} 你被方块物理学制裁了",
    ],
    "hit the ground": [
        "{player} 和大地来了一个深情拥抱",
        "{player} 测试摔落伤害...结论：很高",
        "{player} 脸先着地...疼不？",
        "{player} 鞘翅是好东西，但得会用",
        "{player} 重力测试完毕，结果：致死",
        "{player} 地面赢了",
    ],
    "tried to swim in lava": [
        "{player} 在岩浆里游泳？大胆的想法",
        "{player} 这不是温泉！是岩浆！",
        "{player} 岩浆：欢迎光临",
        "{player} 你的泡澡水温度有点高",
        "{player} 提示：橙色的液体不是橙汁",
        "{player} 下次试试水？真的，普通的水",
    ],
    "was killed": [
        "{player} 被干掉了...",
        "{player} 领了便当",
        "{player} 又回重生点了",
        "{player} 你和死亡很有缘分啊",
    ],
    "withered away": [
        "{player} 被凋零效果带走了...",
        "{player} 凋零：你好，再见",
        "{player} 建议：别碰凋零骷髅",
    ],
    "was impaled": [
        "{player} 被扎成了刺猬",
        "{player} 三叉戟的威力你感受到了吧",
    ],
    "walked into a cactus": [
        "{player} 仙人掌：别碰我！",
        "{player} 你以为仙人掌是装饰品？",
        "{player} 被扎得嗷嗷叫",
    ],
    "was pricked": [
        "{player} 被扎了！看路啊！",
        "{player} 甜浆果丛虽然甜，但是扎人",
    ],
    "default": [
        "{player} 又双叒叕死了...",
        "{player} 你还好吗？需要帮助不？",
        "RIP {player}，安息吧（才怪）",
        "{player} 这已经是第几次了？",
        "{player} 你在cosplay苦力怕吗？动不动就没了",
        "{player} 死亡...是另一段冒险的开始！",
        "{player} 你的床还在吧？",
        "{player} 嘛...每个大佬都是从菜鸡开始的",
    ],
}

DEATH_MESSAGES_EN = {
    "was slain by": [
        "{player} got wrecked! Need some gear?",
        "{player} needs combat training...",
        "{player} forgot how to fight!",
    ],
    "burned": [
        "{player} got cooked! Bring a water bucket next time",
        "{player} is now well-done...",
        "{player} fire resistance potion, maybe?",
    ],
    "drowned": [
        "{player} forgot to breathe!",
        "{player} should learn to swim...",
    ],
    "fell": [
        "{player} forgot they can't fly!",
        "{player} gravity check: confirmed",
        "{player} tried to MLG... and failed",
    ],
    "was blown up": [
        "{player} got a Creeper hug!",
        "{player} went boom!",
        "{player} heard ssssss... too late",
    ],
    "was shot": [
        "{player} became target practice",
        "{player} ate an arrow. Yum.",
    ],
    "starved": [
        "{player} starved?! In MINECRAFT?!",
        "{player} forgot food exists...",
    ],
    "tried to swim in lava": [
        "{player} that's not a hot tub!",
        "{player} lava ≠ pool",
    ],
    "hit the ground": [
        "{player} lost a fight with gravity",
        "{player} faceplanted hard",
    ],
    "default": [
        "RIP {player}... need help?",
        "{player} down again! Want some gear?",
        "{player} back to respawn!",
        "F in chat for {player}",
    ],
}

# ============================================================
# 频繁死亡 - 死亡次数越多吐槽越狠
# ============================================================

DEATH_STREAK_ZH = {
    3: [
        "{player} 你今天已经死了 {count} 次了...要不要开和平模式？",
        "{player} 三连死！要不要我帮你降难度？",
        "{player} 帽子戏法！（死亡版）",
    ],
    5: [
        "{player} 第 {count} 次了！你在挑战速死记录吗？",
        "{player} 五杀！哦等等，是被杀五次",
        "{player} 死亡五连击！建议回家种田",
    ],
    8: [
        "{player} 第 {count} 次...我真的很担心你",
        "{player} 你是不是在故意整我？",
        "{player} 我已经无话可说了...给你全套钻石装？",
    ],
    10: [
        "{player} 死了 {count} 次！恭喜解锁成就【死神的朋友】",
        "{player} 十连死...传奇！要不要直接创造模式？",
    ],
}

DEATH_STREAK_EN = {
    3: [
        "{player} died {count} times today... peaceful mode?",
        "{player} death hat trick!",
    ],
    5: [
        "{player} pentakill! Oh wait, YOU died 5 times",
        "{player} 5 deaths! Maybe try farming?",
    ],
    10: [
        "{player} {count} deaths! Achievement unlocked: Death's BFF",
    ],
}

# ============================================================
# PvP 击杀
# ============================================================

PVP_MESSAGES_ZH = [
    "{killer} 击杀了 {victim}！PvP 之王！",
    "{killer} 把 {victim} 送回了重生点",
    "{victim} 被 {killer} 教做人了",
    "{killer} vs {victim}：胜者 {killer}！",
    "{killer} 对 {victim} 实施了物理说服",
    "{victim} 在 {killer} 面前不堪一击",
]

PVP_MESSAGES_EN = [
    "{killer} slayed {victim}! PvP king!",
    "{killer} sent {victim} to respawn",
    "{killer} wins against {victim}!",
]

# ============================================================
# 加入/离开
# ============================================================

JOIN_MESSAGES_ZH = [
    "欢迎 {player}！我是{bot}，你的 AI 助手，有事跟我说~",
    "{player} 来了！今天想玩什么？跟{bot}说一声~",
    "欢迎回来 {player}！{bot}随时为你效劳！",
    "{player} 上线了！又是元气满满的一天",
    "叮~ {player} 已上线，冒险继续！",
    "{player} 出现了！世界又多了一份危险（划掉）精彩",
]

JOIN_MESSAGES_EN = [
    "Welcome {player}! I'm {bot}, your AI assistant. Talk to me!",
    "{player} is here! What's the plan today?",
    "Welcome back {player}! Let the adventure continue!",
    "{player} has entered the chat!",
]

FIRST_JOIN_ZH = [
    "欢迎新玩家 {player}！第一次来？有问题随时问{bot}！",
    "{player} 第一次来到这个世界！祝你冒险愉快~",
    "新人 {player} 驾到！需要新手礼包吗？跟{bot}说！",
]

FIRST_JOIN_EN = [
    "Welcome new player {player}! First time? Ask {bot} anything!",
    "{player} joined for the first time! Good luck out there!",
]

# ============================================================
# 挂机
# ============================================================

AFK_MESSAGES_ZH = [
    "{player} 发呆 {minutes} 分钟了...还活着吗？",
    "{player} 你是不是去吃饭了？都 {minutes} 分钟了",
    "{player} 挂机中...要不要我帮你看家？",
    "有人在吗？{player} 已经站了 {minutes} 分钟的桩了",
    "{player} 进入了冥想模式（{minutes}分钟）",
    "{player} 疑似灵魂出窍 {minutes} 分钟了",
    "{player} 的角色已经长蘑菇了（{minutes}分钟）",
]

AFK_MESSAGES_EN = [
    "{player} AFK for {minutes} minutes... still there?",
    "Hello? {player}? It's been {minutes} minutes...",
    "{player} went AFK. Mushrooms are growing on them.",
]

AFK_RETURN_ZH = [
    "{player} 终于回来了！欢迎回归",
    "{player} 活过来了！",
    "{player} 灵魂归位！",
    "{player} 结束冥想，重返战场",
    "{player} 回来了！以为你卸载了呢",
]

AFK_RETURN_EN = [
    "{player} is back! Welcome back!",
    "{player} has returned from the void!",
    "{player} soul has re-entered the body!",
]

# ============================================================
# 低血量
# ============================================================

LOW_HEALTH_ZH = [
    "{player} 你快没血了！要回血吗？",
    "{player} 血量告急！赶紧吃东西！",
    "{player} 你现在只剩 {health} 血了...小心点！",
    "{player} 半条命都不到了，悠着点！",
    "{player} 危！赶紧找个安全的地方回血",
    "{player} 你这血量，一只鸡都能把你啄死",
]

LOW_HEALTH_EN = [
    "{player} you're low HP! Need healing?",
    "{player} only {health} HP left... be careful!",
    "{player} one hit away from death!",
]

# ============================================================
# 饥饿
# ============================================================

LOW_FOOD_ZH = [
    "{player} 肚子要饿扁了，给你面包？",
    "{player} 该吃饭了！再不吃就要饿死了",
    "{player} 你的肚子在咕咕叫了",
    "{player} 温馨提示：杀牛可以获得牛肉",
    "{player} 饿了就说，别硬撑",
    "{player} 饥荒模拟器是你吗？",
]

LOW_FOOD_EN = [
    "{player} you're starving! Want some food?",
    "{player} eat something before you starve!",
    "{player} your hunger bar is crying",
]

# ============================================================
# 维度切换
# ============================================================

DIMENSION_ENTER_ZH = {
    "minecraft:the_nether": [
        "{player} 进入了地狱！小心岩浆和猪灵",
        "{player} 欢迎来到地狱！温度有点高哦",
        "{player} 地狱冒险开始！记得带金甲防猪灵",
        "{player} 下界到了，注意脚下岩浆",
        "{player} 你进地狱了！别挖石英挖上瘾忘了回家",
    ],
    "minecraft:the_end": [
        "{player} 进入了末地！终末之战开始！",
        "{player} 欢迎来到末地！小心末影龙和虚空",
        "{player} 末地到了...千万别往下看",
        "{player} 勇者 {player} 挑战末影龙！",
        "{player} 进入了终极领域，祝你好运！",
    ],
    "minecraft:overworld": [
        "{player} 回到了主世界！欢迎回家",
        "{player} 安全着陆主世界！",
        "{player} 回来了！地狱/末地好玩吗？",
    ],
}

DIMENSION_ENTER_EN = {
    "minecraft:the_nether": [
        "{player} entered the Nether! Watch for lava!",
        "{player} welcome to hell! Bring gold armor!",
    ],
    "minecraft:the_end": [
        "{player} entered the End! Good luck with the dragon!",
        "{player} don't look down...",
    ],
    "minecraft:overworld": [
        "{player} is back in the Overworld! Welcome home!",
    ],
}

# ============================================================
# 高度/深度
# ============================================================

ALTITUDE_ZH = {
    "high": [
        "{player} 你飞这么高干嘛？Y={y}！小心摔死",
        "{player} 已到达云层之上 (Y={y})，注意安全",
        "{player} 在 Y={y} 的高空！是在造空中城堡吗？",
    ],
    "deep": [
        "{player} 深入地底 Y={y}...小心 Warden！",
        "{player} 你挖得好深 (Y={y})！深暗之域很危险",
        "{player} Y={y}！注意监守者，别发出声音！",
        "{player} 在 Y={y} 的深处挖矿...注意古城遗迹",
    ],
}

ALTITUDE_EN = {
    "high": [
        "{player} at Y={y}! Don't look down!",
        "{player} building a sky base? (Y={y})",
    ],
    "deep": [
        "{player} deep at Y={y}... watch out for the Warden!",
        "{player} mining at Y={y}, be quiet near sculk!",
    ],
}

# ============================================================
# 升级
# ============================================================

LEVELUP_ZH = [
    "{player} 升到了 {level} 级！",
    "{player} 等级 {level} 了！去附魔台试试运气？",
    "{player} 恭喜升到 {level} 级！继续加油！",
]

LEVELUP_30_ZH = [
    "{player} 到 {level} 级了！完美的附魔等级！",
    "{player} 30级！赶紧去附魔，别浪费经验！",
    "{player} 满级附魔解锁！快去附魔台",
]

LEVELUP_EN = [
    "{player} reached level {level}!",
    "{player} level {level}! Try enchanting?",
]

# ============================================================
# 频繁断线
# ============================================================

RECONNECT_SPAM_ZH = [
    "{player} 又断线了...网络不好吗？",
    "{player} 反复断连中，要不要找个安全点传送？",
    "{player} 你的网线是不是被猫咬了？",
    "{player} MC服务器：我是旋转门吗？",
]

RECONNECT_SPAM_EN = [
    "{player} keeps disconnecting... network issues?",
    "{player} connection unstable. Want a safe tp?",
]

# ============================================================
# 游玩时长
# ============================================================

PLAYTIME_ZH = {
    60: [
        "{player} 已经玩了 1 小时了，记得休息哦~",
        "{player} 一小时了！喝口水吧",
    ],
    120: [
        "{player} 连续玩了 2 小时！该起来活动一下了",
        "{player} 两小时了！眼睛还好吗？",
        "{player} 适度游戏益脑，沉迷游戏伤身（2小时了）",
    ],
    180: [
        "{player} 3 小时了！肝帝认证！但真的该休息了",
        "{player} 你已经肝了 3 小时...身体第一啊",
    ],
    240: [
        "{player} 4 小时！传奇肝帝！求你休息一下",
        "{player} 连续 4 小时...你不累吗？！",
    ],
}

PLAYTIME_EN = {
    60: [
        "{player} 1 hour in! Take a break~",
    ],
    120: [
        "{player} 2 hours! Stretch and drink water!",
    ],
    180: [
        "{player} 3 hours! Legend, but please rest!",
    ],
}

# ============================================================
# 成就
# ============================================================

ADVANCEMENT_ZH = [
    "恭喜 {player} 解锁成就 [{advancement}]！",
    "{player} 获得了 [{advancement}]！太强了",
    "叮~ {player} 达成成就 [{advancement}]！",
    "{player} 成就 [{advancement}] 已解锁！继续探索！",
    "{player} 牛啊！[{advancement}] get！",
]

ADVANCEMENT_EN = [
    "GG {player}! Achievement [{advancement}] unlocked!",
    "{player} got [{advancement}]! Nice!",
    "Achievement get! {player} earned [{advancement}]!",
]


class EventHandler:
    """Handles player events with pre-written messages (no AI cost)."""

    def __init__(self, bot_name: str, language: str, rcon=None, afk_timeout: int = 300):
        self.bot_name = bot_name
        self.language = language
        self.rcon = rcon
        self.afk_timeout = afk_timeout

        # Player tracking
        self.player_activity: dict[str, float] = {}
        self.afk_warned: set[str] = set()
        self.online_players: set[str] = set()
        self.known_players: set[str] = set()  # 见过的所有玩家

        # Death streak tracking
        self.death_counts: dict[str, int] = {}
        self.death_timestamps: dict[str, list[float]] = {}

        # Reconnect tracking
        self.leave_timestamps: dict[str, float] = {}
        self.reconnect_counts: dict[str, int] = {}

        # Playtime tracking
        self.join_times: dict[str, float] = {}
        self.playtime_warned: dict[str, set[int]] = {}  # {player: {60, 120, ...}}

        # RCON state tracking
        self.player_states: dict[str, dict] = {}
        # {player: {health, food, dimension, y, xp_level, last_check}}

    # ==================== Log-based events ====================

    def on_player_join(self, player: str) -> str:
        """Generate join message."""
        self.online_players.add(player)
        self.player_activity[player] = time.time()
        self.join_times[player] = time.time()
        self.playtime_warned[player] = set()
        self.afk_warned.discard(player)
        self.reconnect_counts.pop(player, None)

        # Check reconnect spam
        last_leave = self.leave_timestamps.get(player, 0)
        if time.time() - last_leave < 30:
            count = self.reconnect_counts.get(player, 0) + 1
            self.reconnect_counts[player] = count
            if count >= 3:
                msgs = RECONNECT_SPAM_ZH if self.language == "zh" else RECONNECT_SPAM_EN
                self.reconnect_counts[player] = 0
                return random.choice(msgs).format(player=player)

        # First join ever?
        if player not in self.known_players:
            self.known_players.add(player)
            msgs = FIRST_JOIN_ZH if self.language == "zh" else FIRST_JOIN_EN
            return random.choice(msgs).format(player=player, bot=self.bot_name)

        self.known_players.add(player)
        msgs = JOIN_MESSAGES_ZH if self.language == "zh" else JOIN_MESSAGES_EN
        return random.choice(msgs).format(player=player, bot=self.bot_name)

    def on_player_leave(self, player: str):
        """Track player leaving."""
        self.online_players.discard(player)
        self.player_activity.pop(player, None)
        self.afk_warned.discard(player)
        self.leave_timestamps[player] = time.time()
        self.join_times.pop(player, None)
        self.playtime_warned.pop(player, None)
        self.player_states.pop(player, None)

    def on_player_chat(self, player: str) -> str | None:
        """Update activity on chat."""
        self.player_activity[player] = time.time()
        if player in self.afk_warned:
            self.afk_warned.discard(player)
            msgs = AFK_RETURN_ZH if self.language == "zh" else AFK_RETURN_EN
            return random.choice(msgs).format(player=player)
        return None

    def on_player_death(self, player: str, log_line: str) -> str:
        """Generate death roast message."""
        self.player_activity[player] = time.time()

        # Track death count
        now = time.time()
        self.death_counts[player] = self.death_counts.get(player, 0) + 1
        if player not in self.death_timestamps:
            self.death_timestamps[player] = []
        self.death_timestamps[player].append(now)

        # Clean old timestamps (only count deaths in last 30 min)
        cutoff = now - 1800
        self.death_timestamps[player] = [
            t for t in self.death_timestamps[player] if t > cutoff
        ]
        recent_deaths = len(self.death_timestamps[player])

        # Check PvP first (priority over streak)
        pvp_match = re.search(r"was slain by (\w+)", log_line)
        if pvp_match:
            killer = pvp_match.group(1)
            if killer in self.online_players:
                msgs = PVP_MESSAGES_ZH if self.language == "zh" else PVP_MESSAGES_EN
                return random.choice(msgs).format(killer=killer, victim=player)

        # Check death streak (only trigger at exact thresholds to avoid spam)
        streak_msgs = DEATH_STREAK_ZH if self.language == "zh" else DEATH_STREAK_EN
        if recent_deaths in streak_msgs:
            return random.choice(streak_msgs[recent_deaths]).format(
                player=player, count=recent_deaths
            )

        # Regular death message
        deaths = DEATH_MESSAGES_ZH if self.language == "zh" else DEATH_MESSAGES_EN
        for cause, messages in deaths.items():
            if cause == "default":
                continue
            if cause in log_line:
                return random.choice(messages).format(player=player)

        return random.choice(deaths["default"]).format(player=player)

    def on_advancement(self, player: str, advancement: str) -> str:
        """Generate advancement message."""
        self.player_activity[player] = time.time()
        msgs = ADVANCEMENT_ZH if self.language == "zh" else ADVANCEMENT_EN
        return random.choice(msgs).format(player=player, advancement=advancement)

    # ==================== AFK check ====================

    def check_afk(self) -> list[str]:
        """Check for AFK players."""
        messages = []
        now = time.time()

        for player in list(self.online_players):
            last_active = self.player_activity.get(player, now)
            idle_seconds = now - last_active

            if idle_seconds >= self.afk_timeout and player not in self.afk_warned:
                self.afk_warned.add(player)
                minutes = int(idle_seconds // 60)
                msgs = AFK_MESSAGES_ZH if self.language == "zh" else AFK_MESSAGES_EN
                messages.append(
                    random.choice(msgs).format(player=player, minutes=minutes)
                )

        return messages

    # ==================== Playtime check ====================

    def check_playtime(self) -> list[str]:
        """Check for long play sessions."""
        messages = []
        now = time.time()
        thresholds = PLAYTIME_ZH if self.language == "zh" else PLAYTIME_EN

        for player in list(self.online_players):
            join_time = self.join_times.get(player)
            if join_time is None:
                continue

            play_minutes = (now - join_time) / 60
            warned = self.playtime_warned.get(player, set())

            for threshold_min, msgs in sorted(thresholds.items()):
                if play_minutes >= threshold_min and threshold_min not in warned:
                    warned.add(threshold_min)
                    messages.append(random.choice(msgs).format(player=player))

            self.playtime_warned[player] = warned

        return messages

    # ==================== RCON state polling ====================

    def _parse_player_data(self, raw: str) -> dict | None:
        """Parse RCON 'data get entity' response."""
        try:
            state = {}
            # Health
            m = re.search(r"Health:\s*([\d.]+)f", raw)
            if m:
                state["health"] = float(m.group(1))
            # Food
            m = re.search(r"foodLevel:\s*(\d+)", raw)
            if m:
                state["food"] = int(m.group(1))
            # Dimension
            m = re.search(r'Dimension:\s*"([^"]+)"', raw)
            if m:
                state["dimension"] = m.group(1)
            # Position Y
            m = re.search(r"Pos:\s*\[[\d.Eed+-]+d?,\s*([\d.Eed+-]+)d?,", raw)
            if m:
                state["y"] = float(m.group(1))
            # XP Level
            m = re.search(r"XpLevel:\s*(\d+)", raw)
            if m:
                state["xp_level"] = int(m.group(1))
            return state if state else None
        except Exception:
            return None

    def poll_player_states(self) -> list[str]:
        """Poll all online players via RCON and generate status messages."""
        if not self.rcon:
            return []

        messages = []

        for player in list(self.online_players):
            result = self.rcon.send(f"data get entity {player}")
            if not result:
                continue

            new_state = self._parse_player_data(result)
            if not new_state:
                continue

            old_state = self.player_states.get(player, {})
            msgs = self._compare_states(player, old_state, new_state)
            messages.extend(msgs)

            # Update activity if position changed
            old_y = old_state.get("y")
            new_y = new_state.get("y")
            if old_y is not None and new_y is not None and abs(old_y - new_y) > 1:
                self.player_activity[player] = time.time()
                if player in self.afk_warned:
                    self.afk_warned.discard(player)
                    afk_msgs = AFK_RETURN_ZH if self.language == "zh" else AFK_RETURN_EN
                    messages.append(random.choice(afk_msgs).format(player=player))

            self.player_states[player] = new_state

        return messages

    def _compare_states(self, player: str, old: dict, new: dict) -> list[str]:
        """Compare old and new states, generate messages for changes."""
        messages = []

        # Low health (< 6 HP = 3 hearts)
        health = new.get("health", 20)
        old_health = old.get("health", 20)
        if health <= 6 and old_health > 6:
            msgs = LOW_HEALTH_ZH if self.language == "zh" else LOW_HEALTH_EN
            messages.append(
                random.choice(msgs).format(player=player, health=f"{health:.0f}")
            )

        # Low food (< 6)
        food = new.get("food", 20)
        old_food = old.get("food", 20)
        if food <= 6 and old_food > 6:
            msgs = LOW_FOOD_ZH if self.language == "zh" else LOW_FOOD_EN
            messages.append(random.choice(msgs).format(player=player))

        # Dimension change
        new_dim = new.get("dimension")
        old_dim = old.get("dimension")
        if new_dim and old_dim and new_dim != old_dim:
            dim_msgs = DIMENSION_ENTER_ZH if self.language == "zh" else DIMENSION_ENTER_EN
            if new_dim in dim_msgs:
                messages.append(
                    random.choice(dim_msgs[new_dim]).format(player=player)
                )

        # Altitude warnings
        y = new.get("y")
        old_y = old.get("y")
        if y is not None and old_y is not None:
            alt_msgs = ALTITUDE_ZH if self.language == "zh" else ALTITUDE_EN
            # High altitude (> 200, entering from below)
            if y > 200 and old_y <= 200:
                messages.append(
                    random.choice(alt_msgs["high"]).format(player=player, y=int(y))
                )
            # Deep underground (< -30, entering from above)
            if y < -30 and old_y >= -30:
                messages.append(
                    random.choice(alt_msgs["deep"]).format(player=player, y=int(y))
                )

        # Level up
        new_level = new.get("xp_level", 0)
        old_level = old.get("xp_level", 0)
        if new_level > old_level and new_level > 0:
            if new_level >= 30:
                msgs = LEVELUP_30_ZH if self.language == "zh" else LEVELUP_EN
            else:
                msgs = LEVELUP_ZH if self.language == "zh" else LEVELUP_EN
            # Only announce at milestones to avoid spam
            if new_level >= 30 or new_level in (5, 10, 15, 20, 25):
                messages.append(
                    random.choice(msgs).format(player=player, level=new_level)
                )

        return messages
