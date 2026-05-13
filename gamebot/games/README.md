# gamebot/games · 每游戏一目录

每个子目录代表一个游戏 / 业务领域的 bot 模块，互相独立。

## 当前已有

| 目录 | 说明 | 状态 |
|---|---|---|
| [`mc/`](./mc/README.md) | Minecraft Fabric 服务器（小方）：RCON + 日志监听 + 死亡吐槽 + 周报 + QQ 桥接 | 生产 |
| [`df/`](./df/README.md) | 三角洲行动：每日密码 + 战绩查询 + 干员别名 + AI 战术建议 | 生产 |

## 加新游戏

参考 [根 CLAUDE.md](../../CLAUDE.md#加新游戏模块的-5-步)。每个 game module 至少要有：

- `__init__.py`
- `bridge.py`（或主入口模块）—— 实现核心桥接，跟 core 的 QQBridge / AIProvider 对接
- `README.md` —— 必须！说明这个游戏 bot 干嘛、用什么接口、怎么配置

## 隔离原则

- 每个 game **不应该 import 其他 game 的代码**。共享逻辑放 `gamebot/core/`。
- 每个 game 通常绑一个 QQ 群（`group_id`），通过 core 的多群路由分流。
- 每个 game 自己管自己的状态文件（`data/<game>_*.json`）。
