# gamebot/games/mc · Minecraft 服务器 AI 助手"小方"

原 `mcbot/` 整体迁移过来（2026-05-13 refactor）。是 mc-chat-bot 项目主体。

## 入口

`gamebot.games.mc.bot:ChatBot` —— 由根目录 `run.py` 实例化。

## 模块概览

### 核心

| 文件 | 职责 |
|---|---|
| `bot.py` | 主类 `ChatBot`，启动所有子模块、AI converse 循环（`[CMD:xxx]` → RCON 执行） |
| `config.py` | YAML → dataclass 加载，含所有子模块配置 |
| `rcon.py` | mcrcon CLI 封装，向 MC 服务器发指令 |
| `chat_logger.py` | 监听 `logs/latest.log`，解析聊天/死亡/加入/成就/PvP 事件 |
| `events.py` | 事件 → 文案（85+ 死因吐槽 / 加入欢迎 / 成就祝贺等），轮询玩家状态 |
| `abilities.py` | RCON 工具定义（`[CMD:give]` / `[CMD:tp]` / `[CMD:summon]` 等），含 system prompt 模板 |
| `registry.py` | MC 物品/方块 ID 注册表，给 AI 提供模糊查 |
| `memory.py` | 玩家记忆（最近 20 条聊天 / 事实库） |
| `stats.py` | 玩家 stats 解析 |
| `backup.py` | 按游戏天数自动备份 world 目录 |

### 周期推送

| 文件 | 时间 |
|---|---|
| `daily_mood.py` | 每天 09:00 生成小方今日心情（存 `data/today_mood.json`，前端用） |
| `daily_prophecy.py` | 早 08:00 发预言 / 晚 23:00 验证 |
| `daily_stats.py` | 每日数据聚合 |
| `weekly_diary.py` | 周日 22:00 推送本周小方日记 |
| `weekly_deaths.py` | 周一 09:00 推送上周死亡集锦 |
| `weekly_shame_vote.py` | 周一 10:00 开投，周四 23:59 开奖 |
| `weekly_mystery.py` | 周三 19:00 推送本周悬案 |
| `time_capsule.py` | 时间胶囊（按小时检查） |
| `random_roast.py` | 10:00-21:00 每小时摇骰子（3%）随机找茬 |

### 其他玩法

| 文件 | 用途 |
|---|---|
| `bot_deeds.py` | 收集"小方今日壮举"供日记/总结引用 |
| `catchphrase.py` | 从聊天提取玩家口头禅 |
| `death_heatmap.py` | 死亡坐标聚合 |
| `ingame_vote.py` | 游戏内投票（聊天框驱动） |
| `landmarks.py` | 地标管理 |
| `messageboard.py` | 网站留言板 HTTP 服务（`127.0.0.1:6102`） |

### QQ / DF 桥接

- QQ 桥本身在 [`gamebot/core/qq_bridge.py`](../../core/qq_bridge.py)，本目录的 `qq_bridge.py` 是 re-export 兼容入口（refactor 阶段保留）
- DF 桥接在 [`gamebot/games/df/`](../df/README.md)，由 `bot.py` 实例化并挂入

## 配置

完整字段见 [`config.example.yml`](../../../config.example.yml)。

## 改动注意

- 加新 `[CMD:xxx]` ability：改 `abilities.py` 加定义 → 在 `bot.py:converse` 的执行分支加 handler → README 命令表加一行
- 改 system prompt：在 `abilities.py:build_system_prompt`
- 加 cron 任务：参考 `daily_mood.py` 的 `_scheduler_loop` 模式

## 历史

之前是顶层 `mcbot/` 包。2026-05-13 整体迁移到这里以支持多游戏架构。备份在仓库根 `mcbot.backup.<HHMM>/`。
