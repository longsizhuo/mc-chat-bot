# gamebot · 通用游戏 bot 框架

把 MC bot 抽出来的三层架构：**core 平台无关 + games 每个游戏一个模块**。

## 目录

```
gamebot/
├── core/                   ← 平台无关组件
│   ├── ai_provider.py      LLM 抽象（OpenAI 兼容协议，含 AIConfig dataclass）
│   └── qq_bridge.py        OneBot 11 协议接入，支持主群 + 多个副群
└── games/                  ← 每个游戏一个独立模块
    ├── mc/                 Minecraft Fabric 服务器（RCON + 日志监听 + 事件）
    └── df/                 三角洲行动（接腾讯 AMS 接口 + 关键词 + 别名）
```

## 设计原则

1. **core 严格平台无关**：能用在任何 OneBot 群、任何 LLM、任何游戏。改 core 要审慎，可能影响所有 game module。
2. **games 各自独立**：互不依赖。一个 game 挂了不影响别的。
3. **入口在 `games/mc/bot.py:ChatBot`**：因为 MC bot 是主体，DF / 未来游戏作为子桥接挂进 ChatBot。后续如果有多个独立的非 MC 游戏，可能需要进一步把启动逻辑提到 core。

## 加新游戏的 5 步

见根目录 [`CLAUDE.md`](../CLAUDE.md#加新游戏模块的-5-步)。

## 数据流

```
QQ 群消息 → core/qq_bridge → games/mc/bot.py:_on_qq_message
                                       │
                          ┌────────────┴──────────────┐
                          │                           │
                  source_group_id ==           source_group_id ==
                  MC 主群（默认逻辑）          DF 群（df.bridge.reply）
                          │                           │
                          ▼                           ▼
                     AI tool-use 循环              关键词 → 别名 → AI tool-use
                  （工具走 RCON）              （工具走 df_stats 库）
```

## 入口

`run.py`（根目录）→ `gamebot.games.mc.bot.ChatBot`。

## 重构历史

- 2026-05-13：从单一 `mcbot/` 拆出三层架构。备份在 `mcbot.backup.<HHMM>/`，验证稳定后可删。
