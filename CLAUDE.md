# Agent Guidelines · mc-chat-bot

> 给所有协助维护本项目的 AI Agent 看的指引。**改代码 = 必须同步改文档**。

## 项目结构（2026-05 重构后）

```
mc-chat-bot/
├── run.py                     ← 入口
├── config.yml                 ← 配置（不入库）
├── config.example.yml         ← 配置模板
├── gamebot/
│   ├── core/                  ← 平台无关：AI provider、QQ bridge
│   └── games/
│       ├── mc/                ← Minecraft bot 主体（原 mcbot/）
│       └── df/                ← 三角洲行动桥接
├── scripts/
│   └── df_stats/              ← 三角洲数据获取库（独立 CLI 工具）
├── data/                      ← 运行时状态（不入库）
└── README.md / CHANGELOG.md / AGENTS.md
```

## 改代码时的硬性约束

### 1. 文档同步规则 ⚠️

**任何代码改动都要同步改对应的文档**：

| 改动范围 | 必须更新 |
|---|---|
| 改 `gamebot/games/<game>/` 内部 | `gamebot/games/<game>/README.md` |
| 加新 `[CMD:xxx]` 工具 / 关键词 | 该 game 的 README + 主 README 命令表（如出现在那） |
| 改 `config.yml` 字段 | `config.example.yml` 注释 + 涉及模块的 README |
| 加新游戏模块 | `gamebot/games/<new>/README.md` + 根 `README.md` 提一句 + `gamebot/games/README.md` 列表 |
| 改公共/对外行为 | 根 `README.md` 对应章节 |
| 大改动（重构、新功能） | `CHANGELOG.md` 条目 |

### 1.5. Prompt 与代码分离原则 ⚠️

**system prompt / 长 LLM 指令模板不要硬编码在 .py 里**，放独立 `.md` 文件：

| 模块 | prompt 文件位置 |
|---|---|
| `gamebot/games/df/` | [`gamebot/games/df/prompt.md`](./gamebot/games/df/prompt.md) |
| 新游戏模块 | `gamebot/games/<name>/prompt.md` |

代码侧只负责：
1. 读模板文件
2. 用 `.format(**placeholders)` 填充动态字段（alias 表、笔记、工具列表等）

好处：**改 prompt 文案不用动 Python，下一条群消息就生效**（每次 build_system_prompt 会重读文件）。

占位符约定：所有 `{xxx}` 在模板里都会被 `.format()` 替换。**字面**花括号要写 `{{` 和 `}}`。

文件顶部用 HTML 注释 `<!-- ... -->` 写"可用占位符清单"和使用说明，运行时这段会被剥掉不进 prompt。

**这是硬规则**：用户多次反馈"push 后必须补开发文档，不能光丢代码"。不写文档的 PR 视为未完工。

### 2. 每个文件夹必须有 README.md

新建任何有意义的子目录（>= 2 个文件且承担独立职责），写一份 5-15 行的 `README.md` 说明：
- 这个目录干什么
- 关键文件的职责
- 链接到上下游（依赖什么 / 被谁依赖）

不写空话。

### 3. 中文注释 / 中文 commit message

代码注释、commit message、README 主体一律用中文。变量名/类名保持英文。

### 4. Commit 规则

- **不要加 `Co-Authored-By Claude` 行**。Maintainer 反复强调过。
- Commit message 格式参考 CHANGELOG：`<type>(<scope>): <一句话>`
- 类型：`feat` / `fix` / `refactor` / `docs` / `chore`
- **每个 push 后必须补 CHANGELOG 条目**（见 AGENTS.md），单独 commit 引用前一个 commit 的 sha
- **工作时间（白天）不要 push 到 main**，contribution graph 会暴露同事；只本地修改

### 5. MC 项目默认不 commit

- mc-chat-bot 和 mc-website 都是开源仓库
- **默认只改不提交**，只有用户明确说 "commit" 才做
- 部署用 `sudo systemctl restart` 是部署操作，不算 git 操作

### 6. 改完代码后必跑

```bash
# 1. import 检查
python3 -c "from gamebot.games.mc.bot import ChatBot; from gamebot.games.df.bridge import DFStatsBridge"

# 2. 重启服务（如果在生产环境改）
sudo systemctl restart mc-chatbot.service
sleep 3
systemctl is-active mc-chatbot.service
journalctl -u mc-chatbot.service --since "10 seconds ago" --no-pager | tail -10
```

看到 `Chat bot started` + 各模块启动信息 = OK。

## 不要做的事

- ❌ 不要 push 到 main 上 force / amend 已发布的 commit
- ❌ 不要给 `data/df_aliases.json` 等运行时状态文件加入 git
- ❌ 不要 commit `credentials/raw_curl*.sh`（含 access_token）
- ❌ 不要修改 `scripts/df_stats/` 跟着升 mcbot ——它是独立 CLI 工具
- ❌ 不要在 prompt 工程里假设玩家身份。**腾讯接口不暴露队友真名**，只能用别名表识别

## 加新游戏模块的 5 步

1. `mkdir gamebot/games/<name>` 建目录
2. 写 `__init__.py` + `bridge.py`（参考 `gamebot/games/df/bridge.py`）
3. 写 `<name>/README.md` 说明功能与配置
4. 在 `gamebot/games/mc/config.py` 加对应 dataclass 字段（或独立配置）
5. 在 `gamebot/games/mc/bot.py` 实例化（参考 DFStatsBridge 的接入方式）
6. 跑一遍上面的"必跑"步骤

## 用户反馈快查表（来自历史对话）

- "不确定先查再下结论"：CVE/库/版本类事实必须先 `WebSearch` 验证，禁止"几乎可以确定/显然是"先判后查
- "CR 反馈自主改"：读完 CR 直接按实际情况改，别列 P0/P1/P2 问用户筛选
- "自主推进不等确认"：用户可能在睡觉，中间步骤别停；完工直接 push/PR/切下个 feature
- "代码必须中文注释"
- "期待感优于催促感"：UI 文案说明"加入后会发生什么"而非命令句
- "腾讯接口隔离群"：DF 功能只在 257381453，MC 群一切如常

完整记忆在用户 `~/.claude/projects/-home-ubuntu/memory/`。
