# mc-chat-bot

> 给 Minecraft 服务器加一个会执行指令的 AI 助手

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![DeepSeek](https://img.shields.io/badge/LLM-DeepSeek_/_OpenAI_/_Ollama-blue)](https://deepseek.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)

玩家在游戏聊天框用**中文自然语言**说话，AI 理解意图后通过 **RCON** 执行服务器指令并回复。

<img width="720" alt="AI 一段 prompt 盖出 6 层樱花林豪宅" src="docs/screenshots/ai-built-house.jpg" />

*一段 prompt，AI 盖出来的 6 层豪宅。熔炉、书架立柱、内外双楼梯、照明，一次到位。*

---

## 能做什么

| 玩家说的 | AI 回复 | 执行的指令 |
|---------|---------|-----------|
| "给我 64 个钻石" | 好的，给你 64 钻石！ | `/give <player> diamond 64` |
| "天黑了帮我改白天" | 阳光普照！ | `/time set day` |
| "传送我到 0 64 0" | 嗖！ | `/tp <player> 0 64 0` |
| "给我夜视" | 夜视效果已添加，暗处无忧 | `/effect give <player> night_vision` |
| "召唤一匹马" | 马已就位，请上马！ | `/summon horse ~ ~ ~` |
| "附魔锋利 5" | 锋利 V 已附魔，砍怪去吧！ | `/enchant <player> sharpness 5` |
| "帮我盖一栋 6 层房子，要..." | （动手盖） | 几十次 `/setblock` |

**额外附送**（不消耗 API 额度）：

- 💀 **死亡吐槽**：85+ 条真人撰写文案，16 种死因各有专属
- 🔔 **事件反应**：加入/挂机/低血量/升级/进入地狱或末地 都会被小方吐槽
- 💬 **QQ ↔ 游戏双向桥接**：没开游戏也能在 QQ 群里参与聊天和要东西
- 📜 **每周史诗战报**：周日 22:00 AI 自动生成古风叙事
- ☠️ **每周死亡集锦**：周一 09:00 AI 游戏主播风格复盘

<img width="560" alt="QQ ↔ 游戏双向聊天桥" src="docs/screenshots/qq-bridge-demo.jpg" />

---

## 3 步跑起来

```bash
# 1. 拉代码
git clone https://github.com/longsizhuo/mc-chat-bot.git && cd mc-chat-bot

# 2. 装依赖（Python 3.10+）
pip install -r requirements.txt

# 3. 配置并启动
cp config.example.yml config.yml
# 编辑 config.yml 填 server_dir / ai.api_key / rcon.password
python run.py
```

前置要求：Minecraft Java 服务器已开启 RCON（`server.properties` 里 `enable-rcon=true`），装好 [mcrcon](https://github.com/Tiiffi/mcrcon) 命令行工具。

<details>
<summary>config.yml 关键字段</summary>

```yaml
server_dir: "/你的/minecraft/服务器/路径"

ai:
  provider: "deepseek"      # 或 openai / anthropic / ollama / custom
  api_key: "sk-你的密钥"

rcon:
  password: "你的 rcon 密码"

bot:
  name: "小方"
  language: "zh"            # zh / en

qq:                          # 可选：OneBot11 QQ 桥接
  enabled: false
  api_url: "http://localhost:6100"
  group_id: 1101232433
```

完整配置见 [`config.example.yml`](./config.example.yml)。新手从零部署看 [`docs/QUICK_START.md`](./docs/QUICK_START.md)。

</details>

---

## 架构

```
┌──────────────────────────────────┐
│     Minecraft Fabric 服务端       │
└────────────┬─────────────────────┘
             │
             ├── logs/latest.log ──┐
             │                     │
             ▼                     ▼
       ┌──────────┐          ┌──────────┐
       │ RCON (写)│          │ log (读) │
       └─────┬────┘          └─────┬────┘
             │                     │
             └──────────┬──────────┘
                        │
                ┌───────▼───────┐
                │  mc-chat-bot  │
                │   (Python)    │
                └──┬──────────┬─┘
                   │          │
           ┌───────▼───┐  ┌───▼──────┐
           │ DeepSeek  │  │ OneBot11 │
           │    API    │  │ (NapCat) │
           └───────────┘  └────┬─────┘
                               │
                             QQ 群
```

**关键约束**：AI 在回复中用 `[CMD:...]` 标签发指令，正则提取 + RCON 执行，比强制 JSON 输出稳定得多。

更详细的架构与踩坑记录：[**用 AI 助手运营 MC 服务器的实验记录**](https://involutionhell.com/docs/CommunityShare/Geek/mc-ai-bot-experiment)

---

## 支持的 AI 模型

| Provider | Config `provider` | 备注 |
|----------|-------------------|------|
| DeepSeek | `deepseek` | **推荐**，便宜，中文好 |
| OpenAI | `openai` | 默认 GPT-4o-mini |
| Anthropic | `anthropic` | Claude |
| Ollama | `ollama` | 本地免费，无 API Key |
| 自定义 | `custom` | 任何 OpenAI 兼容 API |

---

## 想直接看效果？

服务器：**mc.involutionhell.com**（26.1.2 + Fabric，离线模式可进）

进去跟小方说一句"你好"，或者让它帮你盖个房子。

---

## 更多

- [**CHANGELOG**](./CHANGELOG.md) · 按 commit 为节点的改动记录
- [**Agent Skill**](./deploy-mcbot/SKILL.md) · 兼容 [Agent Skills](https://agentskills.io)，Claude Code / Cursor 可自动部署
- [**mc-website**](https://github.com/longsizhuo/mc-website) · 服务器官网源码
- **中英双语** · 所有响应文案都有 `zh` / `en` 两套

欢迎 issue / PR / fork。

---

## 许可证

MIT

---

# English

**mc-chat-bot** — AI assistant for your Minecraft server. Players talk in natural language, the bot executes RCON commands and responds.

### Quick start

```bash
git clone https://github.com/longsizhuo/mc-chat-bot.git && cd mc-chat-bot
pip install -r requirements.txt
cp config.example.yml config.yml   # edit server_dir, ai.api_key, rcon.password
python run.py
```

Requires a Minecraft Java server with RCON enabled and [mcrcon](https://github.com/Tiiffi/mcrcon) installed.

### Features

- 🤖 Natural-language chat with a live bot that executes RCON commands
- 🏗️ Builds houses from a single multi-paragraph prompt (tested with a 6-story build)
- 💀 85+ death roasts across 16 death causes (no API cost)
- 💬 Two-way chat bridge between QQ group and in-game
- 📜 Weekly AI-generated server chronicle + deaths digest
- ⚙️ Supports DeepSeek / OpenAI / Anthropic / Ollama / any OpenAI-compatible endpoint

Full architecture writeup: [MC AI Bot Experiment](https://involutionhell.com/docs/CommunityShare/Geek/mc-ai-bot-experiment)

Live server: **mc.involutionhell.com** (26.1.2 + Fabric, offline mode OK).

MIT license.
