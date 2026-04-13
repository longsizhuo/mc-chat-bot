---
name: deploy-mcbot
description: Deploy and configure MCBot, a Minecraft AI chat bot with RCON abilities. Use when the user wants to set up MCBot on a Minecraft server, configure AI providers (DeepSeek/OpenAI/Claude/Ollama), enable RCON, manage the bot service, or troubleshoot MCBot issues.
license: MIT
compatibility: Requires Python 3.10+, mcrcon CLI, and a Minecraft Java Edition server with RCON enabled.
metadata:
  author: longsizhuo
  version: "0.1.0"
---

# Deploy MCBot

MCBot is a Minecraft AI chat bot that monitors server logs and responds to players via RCON. It supports multiple AI providers and can execute in-game commands (give items, teleport, change weather, etc.).

## Prerequisites

Before deploying, ensure:
1. A Minecraft Java Edition server is running
2. Python 3.10+ is installed
3. `mcrcon` CLI is installed (see [install guide](references/INSTALL_MCRCON.md))

## Step-by-step deployment

### 1. Clone and install

```bash
git clone https://github.com/longsizhuo/mc-chat-bot.git
cd mc-chat-bot
pip install -r requirements.txt
```

### 2. Enable RCON on the Minecraft server

Edit `server.properties` in the Minecraft server directory:

```properties
enable-rcon=true
rcon.port=25575
rcon.password=<generate-a-secure-password>
```

Then restart the Minecraft server.

### 3. Create config.yml

```bash
cp config.example.yml config.yml
```

Edit `config.yml` with the correct values:
- `server_dir`: absolute path to the Minecraft server directory
- `ai.provider`: one of `deepseek`, `openai`, `anthropic`, `ollama`, `custom`
- `ai.api_key`: the API key for the chosen provider (not needed for `ollama`)
- `rcon.password`: must match `server.properties`
- `bot.name`: the display name in chat
- `bot.language`: `zh` for Chinese, `en` for English

See [references/CONFIG.md](references/CONFIG.md) for all configuration options.

### 4. Test

```bash
python run.py -c config.yml
```

Verify the bot starts without errors. Join the Minecraft server and type something in chat — the bot should respond.

### 5. Run as a systemd service (optional)

```bash
sudo tee /etc/systemd/system/mcbot.service > /dev/null << EOF
[Unit]
Description=MCBot - Minecraft AI Chat Bot
After=network.target

[Service]
Type=simple
User=$(whoami)
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

## Troubleshooting

- **"mcrcon not found"**: Install mcrcon, see [references/INSTALL_MCRCON.md](references/INSTALL_MCRCON.md)
- **"RCON error: Connection refused"**: Check that RCON is enabled in `server.properties` and the server is restarted
- **"AI API error"**: Verify `api_key` and `base_url` in config.yml. For Ollama, ensure Ollama is running locally
- **Bot not responding**: Check that `server_dir` and `log_file` in config.yml point to the correct log file
- **Bot responds but commands don't work**: The player name in game must match exactly (case-sensitive)

## AI Provider quick reference

| Provider | `provider` | `api_key` | Default model |
|----------|-----------|-----------|---------------|
| DeepSeek | `deepseek` | Required | `deepseek-chat` |
| OpenAI | `openai` | Required | `gpt-4o-mini` |
| Anthropic | `anthropic` | Required | `claude-sonnet-4-20250514` |
| Ollama | `ollama` | Not needed | `llama3` |
| Custom | `custom` | Depends | Must specify `model` and `base_url` |
