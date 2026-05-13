# gamebot/core · 平台无关组件

任何 game module 都能用、跟具体游戏无关的基础设施。

## 文件

| 文件 | 用途 |
|---|---|
| `ai_provider.py` | OpenAI 兼容 LLM 客户端（DeepSeek / OpenAI / Anthropic / Ollama / Custom），含 `AIConfig` dataclass + `AIProvider.chat()` |
| `qq_bridge.py` | OneBot 11 协议接入。支持主群 + `extra_group_ids` 多群监听，提供 `send_to_qq()` / `send_to_group(gid, msg)` |

## 什么属于 core

判断标准：**移除任何一个 game module 后，core 文件应该还能跑**。

✅ 属于 core 的例子：
- LLM 调用、tokenization、cache
- QQ / Discord / Telegram 协议接入
- 定时任务调度器（通用模式，不绑定具体业务）
- 群路由 / 权限管理

❌ 不属于 core 的例子：
- RCON（绑 MC）
- 战绩接口调用（绑 DF）
- 死亡吐槽文案（绑 MC）

## 改 core 的注意事项

- core 是所有 game module 的依赖底层。改了要回归测所有 game。
- `QQBridge.on_qq_message` callback 签名是 **`(group_id, nickname, message)`**——历史上是 `(nickname, message)`，2026-05 加了 group_id。改要兼容。
- `AIProvider.chat()` 签名固定为 `(messages, system_prompt) -> str | None`。别加必填参数。
