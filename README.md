# MCBot - Minecraft AI Chat Bot

An AI-powered chat bot for Minecraft servers. Players can talk to the bot in-game, and it responds using LLMs (DeepSeek, OpenAI, Claude, Ollama, etc.). The bot can also execute server commands like giving items, teleporting players, and changing the weather.

[中文说明](#中文说明)

## Screenshots

| AI Chat | Skills in Action |
|---------|-----------------|
| ![AI Chat](docs/screenshots/chat.png) | ![Skills](docs/screenshots/skills.png) |

| Death Roasts | AFK Detection |
|-------------|---------------|
| ![Death](docs/screenshots/death.png) | ![AFK](docs/screenshots/afk.png) |

| Welcome Message | Backup System |
|----------------|---------------|
| ![Welcome](docs/screenshots/welcome.png) | ![Backup](docs/screenshots/backup.png) |

> Replace screenshots with your own! Put them in `docs/screenshots/`.

## Features

- **AI Chat** - Talk to the bot in Minecraft chat, powered by your choice of LLM
- **Skills** - The bot can give items, teleport, change time/weather, apply effects, and more via RCON
- **Event Reactions** - Pre-written responses for deaths (roasts!), joins, AFK detection, and achievements (no API cost)
- **World Backup** - Automatic backups based on in-game days, not real-time
- **Multi-provider** - Supports DeepSeek, OpenAI, Anthropic Claude, Ollama (local), or any OpenAI-compatible API
- **Bilingual** - Chinese and English support

## How It Works

```
Player chats in game
        │
        ▼
MCBot monitors server log (logs/latest.log)
        │
        ├─ Chat message → Send to AI → Get reply → RCON say + execute [CMD:...] tags
        ├─ Player join  → Random welcome message (no AI)
        ├─ Player death → Random roast message (no AI)
        ├─ Player AFK   → Reminder after timeout (no AI)
        └─ Advancement  → Congratulations (no AI)
```

## Requirements

- Python 3.10+
- Minecraft Java Edition server with **RCON enabled**
- [mcrcon](https://github.com/Tiiffi/mcrcon) CLI tool
- An AI API key (or Ollama for local models)

## Quick Start

### 1. Install mcrcon

```bash
git clone https://github.com/Tiiffi/mcrcon.git
cd mcrcon && gcc -o mcrcon mcrcon.c
sudo cp mcrcon /usr/local/bin/
```

### 2. Enable RCON on your Minecraft server

Edit `server.properties`:

```properties
enable-rcon=true
rcon.port=25575
rcon.password=your-password-here
```

Restart the server.

### 3. Install MCBot

```bash
git clone https://github.com/longsizhuo/mc-chat-bot.git
cd mc-chat-bot
pip install -r requirements.txt
```

### 4. Configure

```bash
cp config.example.yml config.yml
```

Edit `config.yml` with your settings:

```yaml
server_dir: "/path/to/your/minecraft-server"

ai:
  provider: "deepseek"  # or openai, anthropic, ollama, custom
  api_key: "sk-your-key"

rcon:
  password: "your-rcon-password"

bot:
  name: "MCBot"
  language: "zh"  # zh or en
```

### 5. Run

```bash
python run.py
```

Or run as a systemd service:

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

## AI Providers

| Provider | Config `provider` | API Key Required | Notes |
|----------|------------------|-----------------|-------|
| DeepSeek | `deepseek` | Yes | Cheap and good for Chinese |
| OpenAI | `openai` | Yes | GPT-4o-mini by default |
| Anthropic | `anthropic` | Yes | Claude |
| Ollama | `ollama` | No | Local models, free |
| Custom | `custom` | Depends | Any OpenAI-compatible API |

### Using Ollama (free, local)

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3

# config.yml
ai:
  provider: "ollama"
  model: "llama3"  # or any model you pulled
```

## Bot Skills

> ![Skills Demo](docs/screenshots/skills-demo.png)
> *Player asks the bot for diamonds, and the bot gives them via RCON*

The AI can execute these commands by including `[CMD:...]` tags in its response:

| Skill | Command | Example |
|-------|---------|---------|
| Give Items | `give <player> <item> <amount>` | "give me 64 diamonds" |
| Set Time | `time set <value>` | "make it daytime" |
| Set Weather | `weather <type>` | "stop the rain" |
| Teleport | `tp <player> <x> <y> <z>` | "tp me to 0 64 0" |
| Game Mode | `gamemode <mode> <player>` | "give me creative mode" |
| Summon | `summon <entity> ~ ~ ~` | "summon a horse" |
| Effects | `effect give <player> <effect> <seconds>` | "give me night vision" |
| Enchant | `enchant <player> <enchant> <level>` | "enchant my sword with sharpness" |
| Spawnpoint | `spawnpoint <player>` | "set my spawn here" |

## Event Reactions (Free, No AI)

> ![Events Demo](docs/screenshots/events-demo.png)
> *Death roasts and AFK detection in action*

These reactions use pre-written messages and don't call the AI API:

- **Death roasts** - Different messages based on death cause (lava, creeper, fall, etc.)
- **Welcome messages** - Random greetings when players join
- **AFK detection** - Warns players after configurable idle time
- **AFK return** - Welcomes back players who were AFK
- **Achievements** - Congratulates players on advancements

## World Backup

Backs up the `world/` directory based on **in-game days**, not real time. This means:
- Sleeping advances the backup schedule
- Server pauses (no players online) don't waste backups
- Configurable retention (default: 10 backups)

```yaml
backup:
  enabled: true
  check_interval: 60   # check every 60 seconds
  max_backups: 10      # keep last 10 backups
```

To restore a backup:

```bash
# Stop the server
sudo systemctl stop minecraft

# Replace world
cd /path/to/minecraft-server
mv world world.old
tar xzf backups/world_day42_20260413_120000.tar.gz

# Restart
sudo systemctl start minecraft
```

## CLI Options

```bash
python run.py -c config.yml          # Use specific config file
python run.py --no-backup            # Disable backup system
python run.py --backup-only          # Run backup only, no chat bot
```

## License

MIT

---

# 中文说明

MCBot 是一个 Minecraft 服务器 AI 聊天机器人。玩家可以在游戏内直接跟 AI 对话，AI 还能执行服务器指令（给物品、传送、改天气等）。

## 功能

- **AI 聊天** - 在游戏聊天框直接跟 AI 对话
- **技能系统** - AI 可以给物品、传送、改时间天气、加效果、附魔等
- **事件反应** - 玩家死亡吐槽、加入欢迎、挂机提醒、成就祝贺（不消耗 API）
- **游戏日备份** - 按游戏内天数自动备份世界存档
- **多模型支持** - DeepSeek、OpenAI、Claude、Ollama（本地免费）
- **中英双语** - 支持中文和英文

## 快速开始

```bash
git clone https://github.com/longsizhuo/mc-chat-bot.git
cd mc-chat-bot
pip install -r requirements.txt
cp config.example.yml config.yml
# 编辑 config.yml 填入你的配置
python run.py
```

详细说明见上方英文文档。
