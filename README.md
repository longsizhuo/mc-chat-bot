# MCBot - Minecraft AI 聊天机器人

Minecraft 服务器 AI 聊天机器人。玩家在游戏内直接跟 AI 对话，AI 还能执行服务器指令（给物品、传送、改天气等）。支持 DeepSeek、OpenAI、Claude、Ollama 等多种模型。
<img width="600" alt="MCBot Cover" src="docs/screenshots/cover.jpg" />

[English](#english)

## 它能做什么？

```
你（游戏聊天）                      MCBot
─────────────────────────────────────────────
"给我64个钻石"                →  好的！钻石来咯~ [+64 Diamond]
"天黑了帮我改白天"             →  阳光普照！[time set day]
"别下雨了"                    →  天气已放晴~ [weather clear]
"传送我到 0 64 0"             →  嗖！已传送 [tp → 0 64 0]
"给我创造模式"                →  创造模式已开启！尽情造吧
"召唤一匹马"                  →  马已就位，请上马！[summon horse]
"给我夜视"                    →  夜视效果已添加，暗处无忧
"附魔锋利5"                   →  锋利 V 已附魔，砍怪去吧！
"设置出生点"                  →  出生点已设置在当前位置
```

玩家用自然语言说话，AI 理解意图后执行 RCON 指令并回复。一条消息搞定。

## 截图

<img width="800" alt="Screenshot 1" src="docs/screenshots/shot1.jpg" />
<img width="800" alt="Screenshot 2" src="docs/screenshots/shot2.jpg" />
<img width="800" alt="Screenshot 3" src="docs/screenshots/shot3.jpg" />
<img width="800" alt="Screenshot 4" src="docs/screenshots/shot4.jpg" />

## 功能

- **AI 聊天** - 在游戏聊天框直接跟 AI 对话
- **能力系统** - AI 可以给物品、传送、改时间天气、加效果、附魔等（通过 RCON）
- **事件反应** - 玩家死亡吐槽、加入欢迎、挂机提醒、成就祝贺（不消耗 API）
- **游戏日备份** - 按游戏内天数自动备份世界存档（睡觉也算）
- **多模型支持** - DeepSeek、OpenAI、Claude、Ollama（本地免费）
- **中英双语** - 支持中文和英文
- **Agent Skill** - 兼容 [Agent Skills](https://agentskills.io) 标准，AI 编程助手可自动部署

## 工作原理

```
玩家在游戏内聊天
        │
        ▼
MCBot 监控服务器日志 (logs/latest.log)
        │
        ├─ 聊天消息 → 发给 AI → 获取回复 → RCON say + 执行 [CMD:...] 标签
        ├─ 玩家加入 → 随机欢迎语（不调 AI）
        ├─ 玩家死亡 → 随机吐槽语（不调 AI）
        ├─ 玩家挂机 → 超时提醒（不调 AI）
        └─ 解锁成就 → 祝贺消息（不调 AI）
```

## 环境要求

- Python 3.10+
- Minecraft Java 版服务器，**RCON 已开启**
- [mcrcon](https://github.com/Tiiffi/mcrcon) 命令行工具
- AI API Key（或 Ollama 本地模型）

> **新手？** 看 [超详细部署指南](docs/QUICK_START.md)，从零开始手把手教你，包括 Python 安装、RCON 开启、常见问题解决。

## 快速开始

### 1. 安装 mcrcon

```bash
git clone https://github.com/Tiiffi/mcrcon.git
cd mcrcon && gcc -o mcrcon mcrcon.c
sudo cp mcrcon /usr/local/bin/
```

### 2. 开启服务器 RCON

编辑 Minecraft 服务器的 `server.properties`：

```properties
enable-rcon=true
rcon.port=25575
rcon.password=你的密码
```

重启服务器。

### 3. 安装 MCBot

```bash
git clone https://github.com/longsizhuo/mc-chat-bot.git
cd mc-chat-bot
pip install -r requirements.txt
```

### 4. 配置

```bash
cp config.example.yml config.yml
```

编辑 `config.yml`：

```yaml
server_dir: "/你的/minecraft/服务器/路径"

ai:
  provider: "deepseek"  # 或 openai, anthropic, ollama, custom
  api_key: "sk-你的密钥"

rcon:
  password: "你的rcon密码"

bot:
  name: "小方"
  language: "zh"  # zh 中文 / en 英文
```

### 5. 运行

```bash
python run.py
```

或设为 systemd 服务（开机自启）：

```bash
sudo tee /etc/systemd/system/mcbot.service > /dev/null << EOF
[Unit]
Description=MCBot - Minecraft AI Chat Bot
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$(pwd)
ExecStart=$(which python3) $(pwd)/run.py -c $(pwd)/config.yml
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now mcbot.service
```

## AI 模型支持

| 模型 | 配置 `provider` | 需要 API Key | 备注 |
|------|----------------|-------------|------|
| DeepSeek | `deepseek` | 是 | 便宜，中文好 |
| OpenAI | `openai` | 是 | 默认 GPT-4o-mini |
| Claude | `anthropic` | 是 | Anthropic |
| Ollama | `ollama` | 否 | 本地模型，免费 |
| 自定义 | `custom` | 看情况 | 任何 OpenAI 兼容 API |

### 使用 Ollama（免费本地模型）

```bash
# 安装 Ollama
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3

# config.yml
ai:
  provider: "ollama"
  model: "llama3"
```

## Bot 能力

> ![Abilities Demo](docs/screenshots/abilities-demo.png)
> *玩家请求钻石，Bot 通过 RCON 给予*

AI 在回复中插入 `[CMD:...]` 标签来执行指令：

| 能力 | 指令 | 玩家示例 |
|------|------|---------|
| 给物品 | `give <玩家> <物品> <数量>` | "给我64个钻石" |
| 改时间 | `time set <值>` | "帮我改成白天" |
| 改天气 | `weather <类型>` | "别下雨了" |
| 传送 | `tp <玩家> <x> <y> <z>` | "传送我到 0 64 0" |
| 游戏模式 | `gamemode <模式> <玩家>` | "给我创造模式" |
| 生成生物 | `summon <生物> ~ ~ ~` | "召唤一匹马" |
| 施加效果 | `effect give <玩家> <效果> <秒>` | "给我夜视" |
| 附魔 | `enchant <玩家> <附魔> <等级>` | "附魔锋利5" |
| 设置出生点 | `spawnpoint <玩家>` | "设置出生点" |

## 事件系统（免费，不调 AI）

> ![Events Demo](docs/screenshots/events-demo.png)
> *死亡吐槽和挂机检测*

所有事件反应使用预设消息，**不消耗 AI API 额度**。

### 日志被动检测

Bot 监控服务器日志，自动响应以下事件：

| 事件 | 触发条件 | 文案数量 | 说明 |
|------|---------|---------|------|
| 死亡吐槽 | 玩家死亡 | **85条**（16种死因） | 岩浆/苦力怕/摔死/溺水/仙人掌等各有专属吐槽 |
| 死亡连击 | 30分钟内多次死亡 | 在第 3/5/8/10 次触发 | 越死越狠，10次解锁"死神的朋友" |
| PvP 击杀 | 玩家击杀玩家 | 6条 | 自动区分玩家 vs 怪物 |
| 首次加入 | 从未见过的玩家名 | 3条 | 新人专属欢迎 + 引导 |
| 加入欢迎 | 玩家上线 | 6条 | 老玩家随机欢迎语 |
| 频繁断线 | 30秒内断连 ≥ 3次 | 4条 | 提示网络问题 |
| 成就祝贺 | 解锁进度 | 5条 | 随机祝贺消息 |

### RCON 主动轮询（每 15 秒）

Bot 通过 RCON 查询玩家实时状态，检测变化并反应：

| 状态 | 触发条件 | 文案数量 | 说明 |
|------|---------|---------|------|
| 低血量预警 | HP ≤ 6（3颗心以下） | 6条 | 从满血降到低血时触发 |
| 饥饿提醒 | 饱食度 ≤ 6 | 6条 | 从饱降到饿时触发 |
| 进入地狱 | 维度变为 `the_nether` | 5条 | 提醒带金甲防猪灵 |
| 进入末地 | 维度变为 `the_end` | 5条 | 祝好运、小心虚空 |
| 回到主世界 | 维度变为 `overworld` | 3条 | 欢迎回家 |
| 高空警告 | Y > 200 | 3条 | 从低处升到高空时触发 |
| 深层警告 | Y < -30 | 4条 | 进入深暗之域提醒小心 Warden |
| 升级通知 | 经验等级到 5/10/15/20/25/30 | 6条 | 30级特别提醒去附魔 |

### 社交/健康类

| 功能 | 触发条件 | 文案数量 | 说明 |
|------|---------|---------|------|
| 挂机检测 | 超过设定时间无活动 | 7条 | 默认 5 分钟，可配置 |
| 挂机回归 | AFK 玩家恢复活动 | 5条 | 聊天或移动时触发 |
| 游玩时长提醒 | 连续在线 1/2/3/4 小时 | 8条 | 提醒休息，越久越严肃 |

## 世界备份

按**游戏内天数**备份 `world/` 目录，而不是现实时间：
- 睡觉跳过的时间也算（推进备份进度）
- 服务器暂停时不浪费备份
- 可配置保留数量（默认 10 份）

```yaml
backup:
  enabled: true
  check_interval: 60   # 每 60 秒检查一次
  max_backups: 10      # 保留最近 10 份
```

回档方法：

```bash
# 停服
sudo systemctl stop minecraft

# 替换存档
cd /你的/minecraft/服务器
mv world world.old
tar xzf backups/world_day42_20260413_120000.tar.gz

# 重启
sudo systemctl start minecraft
```

## 命令行参数

```bash
python run.py -c config.yml          # 指定配置文件
python run.py --no-backup            # 不启用备份
python run.py --backup-only          # 只跑备份，不启动聊天
```

## Agent Skill

本项目包含符合 [Agent Skills](https://agentskills.io) 标准的技能定义（`deploy-mcbot/SKILL.md`）。支持 Agent Skills 的 AI 编程工具（Claude Code、Cursor、Copilot 等）可以自动识别并帮你部署配置 MCBot。

## 许可证

MIT

---

# English

MCBot is an AI-powered chat bot for Minecraft servers. Players talk to the bot in-game, and it responds using LLMs (DeepSeek, OpenAI, Claude, Ollama, etc.). The bot can execute server commands like giving items, teleporting players, and changing the weather via RCON.

## Features

- **AI Chat** - Talk to the bot in Minecraft chat, powered by your choice of LLM
- **Abilities** - Give items, teleport, change time/weather, apply effects, enchant via RCON
- **Event Reactions** - 85+ death roasts, PvP, death streaks, join/leave, AFK, low HP/hunger, dimension change, altitude, level up, playtime reminders (all free, no API cost)
- **World Backup** - Automatic backups based on in-game days, not real-time
- **Multi-provider** - DeepSeek, OpenAI, Anthropic Claude, Ollama (local), or any OpenAI-compatible API
- **Bilingual** - Chinese and English support
- **Agent Skill** - Compatible with [Agent Skills](https://agentskills.io) standard

## Quick Start

```bash
git clone https://github.com/longsizhuo/mc-chat-bot.git
cd mc-chat-bot
pip install -r requirements.txt
cp config.example.yml config.yml
# Edit config.yml with your settings
python run.py
```

See Chinese documentation above for detailed setup instructions.
