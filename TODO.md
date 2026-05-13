# TODO · 长期 backlog

不紧急但记下来防忘记的事项。短期任务在 GitHub Issues 或 TaskCreate 里。

## 跨项目联动

### openInvest ↔ mc-chat-bot 的 NapCat 统一

**背景**：用户的 `openInvest`（多资产 AI 投资委员会）项目里也有一份 NapCat / OneBot 接入的代码，跟本项目 `gamebot/core/qq_bridge.py` 功能重叠。

**目标**：把两个项目的 QQ 桥接抽到统一的 Python 包，两边都依赖它，单点维护：
- NapCat WebSocket 连接 + HTTP API 调用
- 群消息收发 + 多群路由
- `[CQ:at,qq=XXX]` 解析 + 群名片查询
- 多 game module / multi-bot 共存（gamebot 已支持 extra_group_ids）

**可能的实现路径**：
- 选项 A：把 `gamebot/core/qq_bridge.py` 抽成独立 PyPI 包（如 `qq-onebot-bridge`），openInvest 当依赖装
- 选项 B：在 monorepo 风格仓库里 vendor 一份，定期 sync
- 选项 C：openInvest 直接 import gamebot 的 core 子模块（需要把 gamebot 也变得可独立 pip install）

**好处**：
1. CQ:at 解析、群名片缓存、多群路由这些逻辑只维护一份
2. 加新游戏 bot 或新业务 bot 都能复用
3. openInvest 的"投资委员会决议自动播报到群"和 mc-chat-bot 的"游戏事件推 QQ 群"逻辑可以共享 send 模式

**状态**：未开始。先把 mc-chat-bot 内的核心能力稳定下来，再启动这个联动。

---

## Memory 系统后续

参见 `gamebot/core/memory/README.md` 的 Phase 2-5。

- [ ] **Phase 2**: SQLite FTS5 全文检索（当前是子串匹配）
- [ ] **Phase 4**: MC bot memory 迁移到 GameMemory（统一存储）
- [ ] **Phase 5**: 老 episodes 自动 summarize 成 facts（防止 episodes.jsonl 无限增长）

---

## DF 模块

### 数据深化

- [ ] **单局成就卡片**（iChartId=468605）接入 `df_match` 输出（"百万富翁/小试牛刀"）
- [ ] **战绩 v2 endpoint**（iChartId=450526）替代 v1，每页 ~180 场 vs v1 的 30 场，拉历史快 6 倍
- [ ] **多用户 RoomId 跨账号匹配**：每个群友各贡献 cookie → 按 RoomId 关联 → 输出"群友对战报告"（隐私设计待评估）

### Memory 利用

- [ ] **战绩自动归档为 episodes**：每次 fetch 战绩时把高光局/翻车局存进 episodes，供 AI 长期回顾
- [ ] **战术习惯学习**：bot 看到某玩家 N 次都在巴克什机密亏损 → 自动 `df_remember` 一条 fact"X 在 Y 图表现差"

---

## MC 模块

- [ ] MC bot memory（每玩家 history / facts）迁移到 GameMemory（Phase 4）
- [ ] 玩家身份与 QQ 号双向映射（解决"玩家 in-game name ↔ QQ 群昵称"问题）

---

## 框架级

- [ ] **加新游戏的 5 步指南**写成实际可运行的脚手架命令（如 `python -m gamebot.create_game <name>`）
- [ ] AI provider 的 model 参数能在运行时切换（不重启）—— 方便 A/B 测试不同 LLM
- [ ] system prompt 模板支持包含别的模板（`{include:another.md}`）—— 复用片段
