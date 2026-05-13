# 更新日志 / Changelog

每一次 `main` 分支推送在这里留一行记录。新的在上面。

格式：`- <commit-short-sha> <YYYY-MM-DD> 类型: 一句话说清楚改了什么、为什么`

类型约定：`feat` 新能力 ·  `fix` 修 bug ·  `docs` 文档 / system prompt ·  `chore` 杂项 ·  `refactor` 重构

---

## 2026-05-13

- **`d39f0a6` feat(df)**: 加 df_unknowns 工具按"3 人固定队-已注册 alias"排除法识别群里没注册 alias 的队友干员 ID。修两个数据 bug：(1) teammateArr 含全房间玩家（不只自己队），加 TeamId 过滤；(2) 跳过 own_ops_history 而不光是 vopenid（user 切过主玩干员：威龙→疾风）。把用户亲述的"3 人固定队规则（医疗+信息位 / 信息位）"和角色段映射（10xxx=突击/20xxx=支援医疗/30xxx=工程/40xxx=信息侦察）写入 system prompt，bot 能主动推理"#20005 出现 50 次 + 20xxx 段 → 很可能是医疗位队友"，问群友确认即可 set_alias。
- **`7c67eff` fix(df)**: "我们/上把"被"我歧义处理"过度拦截导致 bot 拒答战绩查询。修：把"我"分成"我们"和"我自己"两种语义，"我们/上把"直接调 df_match 1 拿队伍视角战报；"我自己"才走单人识别分支；显式说明"我不是龙龙"这种半玩笑昵称当普通群友处理。顺手把 config.yml ai.max_tokens 从 200 调到 800（不入库）。
- **`ce390ed` fix(df)**: bot 把已注册昵称当陌生干员瞎调 df_lookup 的 bug。群友实测："@王十十十十十寸 现在玩的老黑"——bot 居然调 `df_lookup '老黑'` 当干员查（老黑明明在 alias 表里=牧羊人）。修：(1) system prompt 把已注册别名列表移到顶部，加硬性判断顺序（名字先查别名表→再查干员表→都没有才调 lookup）；(2) 加三个 alias 操作工具 `df_set_alias` / `df_rename_alias` / `df_unset_alias`，AI 可主动改 alias 表；(3) 加多种语义识别指引（"X 现在玩 Y" / "X 改名 Y" / "@A 是 B" 等）；(4) 加"我"歧义处理（cookie 只龙龙一份，其他人说"我"不要瞎查）。
- **`3100fc1` feat(df)**: DF bot 三处改进。(1) AI 人设从"毒舌分析师"改成"战术教练"，system prompt 显式禁用"别头铁/真菜"等评判式用词，给具体可执行建议而不嘲讽；(2) 修 CQ:at 主语丢失 bug——core/qq_bridge.py 加 `resolve_at_mentions()` 调 OneBot 把 `[CQ:at,qq=XXX]` 换成 `@群名片`，aliases.py 加 `@老王 为 牧羊人` / `更正—@老王 为 麦小雯` 句式识别；(3) 加 `df_lookup` / `df_register_op` 工具，bot 遇到不认识的干员/陌生 5 位数 ID 时自动查 luoy-oss 远程社区表，学到新干员可持久化到 `data/df_extra_ops.json`。顺手补 OPERATOR_NAMES：10012=疾风（S5 突击新干员）。
- **`21f3f12` feat+refactor**: 三角洲行动 QQ bot + gamebot/ 三层架构。新增 `scripts/df_stats/` CLI（封装腾讯 AMS：战绩/生涯/9 个赛季/每日密码，9 个分析命令），新增 `gamebot/games/df/` 桥接（定时 06:00 播报密码 + 关键词触发 + 干员别名"我玩XX"模糊匹配 + AI tool 调用 `[CMD:df_*]`），严格群隔离（DF 功能限定 257381453 群）。同时把 `mcbot/` 整体 refactor 成 `gamebot/{core,games/{mc,df}}` 三层架构：`core/` 放 LLM provider + OneBot QQ 桥（平台无关），`games/mc/` 是原 mcbot 整体迁移（28 个文件，相对 import 全保留），`games/df/` 是新模块。修复 refactor 引入的 `Path(__file__).parent.parent` 路径 bug（影响 8 处 `data/*.json` runtime state）。新增 `CLAUDE.md` 强调改代码必须同步改文档 + 每个子目录补 README.md。配置文件新增 `df_stats:` 段（4 个 curl 路径 + 别名表 + 广播时刻），`qq:` 段新增 `extra_group_ids`。

---

## 2026-04-14

- **`659b0ff` feat**: bot 启动时自动重新断言 gamerule。观察到 `keep_inventory` 会被某种途径悄悄关掉（世界重载？手动误操作？），不查根因了，改为每次 bot 启动时重新跑一遍 `gamerule keep_inventory true`（并可通过 `bot.startup_commands: [...]` 配置任意命令列表）。新建了一个 daemon 线程等 RCON 就绪（最多 30×5s 重试），然后顺序执行。
- **`8dd113f` docs**: system prompt 补上**多方块 / 连接型方块**的建筑规则（中英）。原因：longlong 盖小洋房时，门只放下半扇（因为门是 2 格高，必须 `half=lower` + `half=upper` 两次 setblock），玻璃窗放在墙的内侧一格导致"玻璃悬在墙里"的诡异视觉（窗户必须直接覆盖掉墙面那一格，不要塞进室内）。补了门、床、窗、楼梯、壁挂火把的 state 写法和坐标注意事项。
- **`938b74a` docs**: 新增 `CHANGELOG.md`（本文件）+ `AGENTS.md` 维护者说明，README 链接到 CHANGELOG。规范：每次推送必须追加一行，类型（feat/fix/docs/chore/refactor）+ 一句话说清楚"改了什么、为什么"。经验教训：**新条目写 sha 时填上一次推送的 sha，不要自引用**（amend 会让 sha 飘，持续追 sha 会死循环）。
- **`ed4952c` feat**: 物品/方块 ID **模糊搜索**。从服务器 jar 的 `--reports` 模式 dump 出 26.1.2 完整注册表（1506 items + 1168 blocks），写入 `data/registry.json`。新增 `[CMD:find block <关键词>]` / `[CMD:find item <关键词>]`，在 bot 里拦截不走 RCON，结果作为 `[CMD_RESULT]` 给下一轮。system prompt 要求：对 ID 不确定就先 find。MC 升级时跑 `scripts/dump_registry.sh` 重新生成。
- **`76da4b9` docs**: system prompt 追加"带颜色方块必须带颜色前缀"（`bed`→`red_bed` 等）+ 新版 `setblock` 语法说明（用 `[states]`，禁用 1.12 之前的 data value 写法）。原因：日志里看到过 `Unknown block type 'minecraft:bed'` 和 `torch 4 replace air` 报错。
- **`286a125` fix**: tool-use 最大轮数从硬编码 3 改成配置项 `bot.max_tool_rounds`，默认 10。原因：盖房子需要多次 fill+setblock 调用，3 轮会被截断。
- **`412b1c7` feat**: **多轮 tool-use 循环**。新 `ChatBot.converse()`：AI → 执行 `[CMD:...]` → 结果以 `[CMD_RESULT]` 回灌到历史 → 下一轮。最多 3 轮（见 `286a125` 调到 10）。`tp` 能力新增玩家目标形式（`tp <player> <target_player>`），system prompt 要求名字不全先 `[CMD:list]`，禁止瞎猜。
- **`e7f7e40` docs**: system prompt 写明"本服 26.1.2，gamerule 用 snake_case"（`keep_inventory` 等），避免以后执行 gamerule 时用老的 camelCase 报错。
- **`d782daf` feat**: **持久化记忆**。新 `mcbot/memory.py`：每玩家对话历史存 `memory/history/<player>.json`（重启不失忆）；长期事实存 `memory/facts.json`，每次对话自动注入 system prompt。新增 `[CMD:remember <player> <fact>]` 和 `[CMD:forget <player> <keyword|index>]`（不走 RCON）。配置项：`bot.memory_dir`、`bot.max_facts`。
- **`08af32b` feat**: 小方现在**会盖房子了**。新增 `setblock` / `fill`（含 hollow/outline）/ `clone` / `execute at` 四个能力；system prompt 硬性规则：玩家说"建造/扩建/盖房"时必须动手建、禁止搪塞"自己建才有成就感"，且只能用真实原版方块 ID。
- **`f4b6aff` feat**: QQ 群桥接（OneBot 11 / NapCat），MC 聊天、加入、死亡、稀有成就会转发到 QQ 群；QQ 群消息也会转发进 MC。新增 `PlayerStats` 写 `player_stats.json` 供 mc-website 读取。新增 `list` 能力。README 交叉引用 [mc-website](https://github.com/longsizhuo/mc-website)。
