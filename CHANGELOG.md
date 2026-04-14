# 更新日志 / Changelog

每一次 `main` 分支推送在这里留一行记录。新的在上面。

格式：`- <commit-short-sha> <YYYY-MM-DD> 类型: 一句话说清楚改了什么、为什么`

类型约定：`feat` 新能力 ·  `fix` 修 bug ·  `docs` 文档 / system prompt ·  `chore` 杂项 ·  `refactor` 重构

---

## 2026-04-14

- **`938b74a` docs**: 新增 `CHANGELOG.md`（本文件）+ `AGENTS.md` 维护者说明，README 链接到 CHANGELOG。规范：每次推送必须追加一行，类型（feat/fix/docs/chore/refactor）+ 一句话说清楚"改了什么、为什么"。经验教训：**新条目写 sha 时填上一次推送的 sha，不要自引用**（amend 会让 sha 飘，持续追 sha 会死循环）。
- **`ed4952c` feat**: 物品/方块 ID **模糊搜索**。从服务器 jar 的 `--reports` 模式 dump 出 26.1.2 完整注册表（1506 items + 1168 blocks），写入 `data/registry.json`。新增 `[CMD:find block <关键词>]` / `[CMD:find item <关键词>]`，在 bot 里拦截不走 RCON，结果作为 `[CMD_RESULT]` 给下一轮。system prompt 要求：对 ID 不确定就先 find。MC 升级时跑 `scripts/dump_registry.sh` 重新生成。
- **`76da4b9` docs**: system prompt 追加"带颜色方块必须带颜色前缀"（`bed`→`red_bed` 等）+ 新版 `setblock` 语法说明（用 `[states]`，禁用 1.12 之前的 data value 写法）。原因：日志里看到过 `Unknown block type 'minecraft:bed'` 和 `torch 4 replace air` 报错。
- **`286a125` fix**: tool-use 最大轮数从硬编码 3 改成配置项 `bot.max_tool_rounds`，默认 10。原因：盖房子需要多次 fill+setblock 调用，3 轮会被截断。
- **`412b1c7` feat**: **多轮 tool-use 循环**。新 `ChatBot.converse()`：AI → 执行 `[CMD:...]` → 结果以 `[CMD_RESULT]` 回灌到历史 → 下一轮。最多 3 轮（见 `286a125` 调到 10）。`tp` 能力新增玩家目标形式（`tp <player> <target_player>`），system prompt 要求名字不全先 `[CMD:list]`，禁止瞎猜。
- **`e7f7e40` docs**: system prompt 写明"本服 26.1.2，gamerule 用 snake_case"（`keep_inventory` 等），避免以后执行 gamerule 时用老的 camelCase 报错。
- **`d782daf` feat**: **持久化记忆**。新 `mcbot/memory.py`：每玩家对话历史存 `memory/history/<player>.json`（重启不失忆）；长期事实存 `memory/facts.json`，每次对话自动注入 system prompt。新增 `[CMD:remember <player> <fact>]` 和 `[CMD:forget <player> <keyword|index>]`（不走 RCON）。配置项：`bot.memory_dir`、`bot.max_facts`。
- **`08af32b` feat**: 小方现在**会盖房子了**。新增 `setblock` / `fill`（含 hollow/outline）/ `clone` / `execute at` 四个能力；system prompt 硬性规则：玩家说"建造/扩建/盖房"时必须动手建、禁止搪塞"自己建才有成就感"，且只能用真实原版方块 ID。
- **`f4b6aff` feat**: QQ 群桥接（OneBot 11 / NapCat），MC 聊天、加入、死亡、稀有成就会转发到 QQ 群；QQ 群消息也会转发进 MC。新增 `PlayerStats` 写 `player_stats.json` 供 mc-website 读取。新增 `list` 能力。README 交叉引用 [mc-website](https://github.com/longsizhuo/mc-website)。
