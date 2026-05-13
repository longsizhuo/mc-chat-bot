# mc-chat-bot 代码 Review · 2026-05-13

Reviewer: Claude Opus 4.7（1M context）
Scope: `gamebot/core/`、`gamebot/games/df/`、`gamebot/games/mc/bot.py`、`scripts/df_stats/cli.py`
Code base size: 约 3,900 行 Python（不含 `mcbot.backup.*/`）

---

## TL;DR

整体结构清楚、注释充足、改造方向正确。但 **memory 子系统大半是"宣传图"**：FTS5 索引和 Phase 5 自动修剪根本没有接入主流程，GameMemory 也只在 DF 里真的用了，MC 只在启动时写了一条 episode 当装饰。DF bridge 的 `_history` 是无锁共享状态，所有 LLM 调用同步阻塞 WS 线程——一个超时拖累全群。最危险的是 `summarize.py:118` 的布尔逻辑写反，过时 episode 不会被裁掉。

---

## P0（必修，影响正确性 / 数据完整性）

### P0-1 `summarize.py:118` — 时区判定写反，时间过滤失效

```python
if ts and (ts.tzinfo or ts.replace(tzinfo=timezone.utc) >= cutoff):
    recent.append(e)
```

**现象**：意图是"有 tz → 直接比 / 无 tz → 当 UTC 比"，但 Python `or` 短路语义下，**只要 `ts.tzinfo` 非 None**（即时间戳带时区，绝大多数情况），整个表达式就是 truthy，根本不再跟 `cutoff` 比较。结果是：**带时区的老 episode 一律被认为是"近 N 天内"**，永远进 `recent`。

`prune_old_episodes` 用了独立逻辑（line 75-78）勉强正确，但 `summarize_into_facts` 的统计完全是错的。

**修法**：
```python
ts_aware = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
if ts_aware >= cutoff:
    recent.append(e)
```

**影响**：`summarize_into_facts` 永远返回"包含全部历史"的统计，weekly_activity fact 的数字是失真的。所幸这个函数目前没有定时调用方，bug 暂无生产影响——但接上调度就立刻翻车。

---

### P0-2 `bot.py:548` — `self.qq.self_id` 是不存在的属性 + 整段死代码

```python
try:
    self_id = self.qq.self_id  # 可能不存在
except AttributeError:
    self_id = 0
```

**现象**：`QQBridge` 类**从来没有定义 `self_id`**（grep 全仓库零结果，event payload 里 `self_id` 只在 `_handle_event` 局部用过）。所以 `try` 块每次都抛 AttributeError，`self_id` 每次都是 0。**而且这个 `self_id` 算完之后整段被注释 "做二次替换去掉" 的代码没了**——即变量 `self_id` 算完后**根本没用**。

**修法**：要么真给 QQBridge 加 `self.self_id` 字段（在 `_handle_event` 看到事件时缓存），要么把这段死代码删掉。注释里"做二次替换"的意图也得补回来或者明确放弃。

**影响**：当前没崩，但是有意图未实现的痕迹。代码 review 角度算"信号噪声"。

---

### P0-3 `bridge.py` `_history` 无锁，跨群消息并发就崩

```python
self._history: list[dict] = []  # 群级共享会话历史
...
self._history.append({"role": "user", ...})
self._trim_history()
reply = self.ai_provider.chat(self._history, system_prompt)
```

**现象**：`_history` 是 `DFStatsBridge` 实例属性，DF 群里所有消息共享一份。目前看是单 WS 线程串行处理，看起来安全；但：

1. **`messageboard` 的 HTTP server** 在另一个线程跑，且其 `chat_provider` 直接复用 `self.ai`（不是 DFBridge）——本身没冲突。但只要 **未来想把 LLM 调用扔进 ThreadPool**（必然要做，下面 P0-4），`_history` 立刻竞态。
2. 群里两个人 1 秒内连续 @ bot：第一条消息进 converse，在 30-120s 的 LLM 等待期间 WS 线程被阻塞，第二条消息得等 LLM 跑完才进。**用户体感 = bot 死了**。

**修法**：要么加 `threading.RLock` 守护 `_history` 的 append/read/trim，要么把"对话历史"也下沉到 GameMemory（episode 形式）然后 converse 每次按"最近 N 条 conversation episode for 当前群"动态构造。后者更干净。

**影响范围**：本来就只服务一个群，QPS 极低，今天还没崩。但加任何"并发请求"或"多群共享 bridge"的优化都会立刻炸。

---

### P0-4 LLM 同步阻塞 WS 线程 → 单次 DF 工具循环最多 120s 全部 QQ 群无响应

```python
# bridge.py:225
for round_idx in range(MAX_TOOL_ROUNDS):   # = 4
    reply = self.ai_provider.chat(...)     # 30s timeout
```

**现象**：DF 一条消息最多 `4 × 30s = 120s`（外加每次工具调用本身的 HTTP 调用）。整段在 `_ws_loop → _handle_event → on_qq_message → df_stats.reply → converse` 调用栈里，全是 `QQBridge` 的同一个 WS 线程。**LLM 卡 / 工具卡 → MC 主群也回不了消息 / 在线名单对账线程跑但消息处理停摆**。

**修法**：在 `_handle_event` 里把 `on_qq_message(...)` 派发到一个 `concurrent.futures.ThreadPoolExecutor`（max_workers=4 就够），并发的同时给每个 group 加 lock（如果一定要保历史一致性）。或者改 asyncio。

```python
# 简化伪代码
self._pool.submit(self.on_qq_message, gid, nickname, raw_message)
```

**影响范围**：高。今天群里只要 DF 的 LLM 卡一次，所有人感知 bot 死了。

---

### P0-5 `fact_store.py:90` 写盘非原子 → 进程崩溃 / 断电时 facts.json 直接腐坏

```python
self.path.write_text(json.dumps(...), encoding="utf-8")
```

**现象**：`Path.write_text` 内部 `open(w) / write / close`，写到一半被 `kill -9` / OOM / 断电会留下空文件或半行 JSON。下次启动 `_load` 里 `json.JSONDecodeError` 触发，**`_facts = {}` 静默重置**——所有 alias / 笔记一次性归零，且日志只有一行 `[FactStore] 加载失败，从空开始`。

**修法**：写临时文件 + atomic rename：
```python
tmp = self.path.with_suffix(".json.tmp")
tmp.write_text(json.dumps(...), encoding="utf-8")
os.replace(tmp, self.path)  # POSIX 上 atomic
```

`episode_log` 用 append-only 文本，单行写正常情况下原子；但 prune_old_episodes 用 `open("w")` 重写也有同样问题，得用同样的 tmp+rename。

**影响范围**：高。alias 表 = 用户花了多次对话累计出来的群友档案，丢一次很难追回。

---

## P1（该修，影响可维护性 / 性能 / 隐私）

### P1-1 FTS5 索引模块（search.py、`GameMemory.search()`）**整套都是死代码**

`grep -rn 'memory.search\|self.memory.search' gamebot/` → 零生产调用。
- `context_for_message` 走的是 `retrieval.py` 的 **线性扫描**（`fact_store.subjects()` + `_resolve_canonical` 4 次 `find`）
- `search.db` 文件在 `data/memory/df/search.db` 里有 24KB，但 `_ensure_search` 永远不会被触发

**建议**：要么删 `search.py` + `__init__` 里的 export，要么在 `retrieve_relevant_facts` 里真用上（数据量真大时切到 FTS5）。**两头都不沾的"半成品基建"是技术负债**。如果短期不接，至少在 README 上写清楚"未启用，备用基建"，别让下个人以为它在工作。

**影响**：当前面积 = 索引文件存在但是过期的（永远不重建），下次真有人调 `search()` 拉的是脏数据。

---

### P1-2 `summarize.py` 的 `prune_old_episodes` / `summarize_into_facts` 也都没接调度

`CLAUDE.md` 写"Phase 5 自动修剪"，**实际没人调它**。`episodes.jsonl` 字面意义无限增长。
今天 656 字节没事，半年后到 100MB → bot 启动时 `EpisodeLog._load` 一次性 `json.loads` 每行，OOM 或启动慢到超时。

**建议**：在 `ChatBot.run()` 里启动一个低频线程（每天 03:00 跑一次），调 `prune_old_episodes(self.df_stats.memory)`。或者在 GameMemory 里加 `if len(self._episodes) > 10000: auto_prune()`。

**影响**：长期可见的崩溃路径，但今天不会出问题。

---

### P1-3 `retrieve_relevant_facts` 性能 O(N×S)，每条消息都跑一遍

`_resolve_canonical` 对每个匹配 subject 做 4 次 `fact_store.find(...)`（每次全表扫描），加上 `by_subject` 也全表扫——上层还要 `fact_store.subjects()` 全表扫一次。

N=facts 总数（当前 65 条），S=展开后 subject 数（典型 3-10），运行复杂度大概 `O(N × (S × hops))` ≈ 几千次比较。**每条 QQ 消息 build_system_prompt 都跑一遍**。

**建议**：在 `FactStore` 内部维护两个反向索引（`_by_subject: dict[str, list[Fact]]`、`_by_predicate: dict[str, list[Fact]]`），CRUD 时同步更新。把 `find()` 改成 O(1) 主索引查 + O(k) 过滤。

**影响**：今天数据少看不出来，过几个月就开始拖。

---

### P1-4 `_apply_aliases_to_text` 替换有顺序依赖 + 重入问题

```python
for nick, op_id in table.items():
    op_name = OPERATOR_NAMES.get(op_id, ...)
    text = text.replace(f"干员#{op_id}", f"{nick}({op_name})")
    if op_name in text and f"{nick}({op_name})" not in text:
        text = text.replace(op_name, f"{nick}({op_name})")
```

**问题**：
1. 当 `op_name = "毒蜂"` 而另一个 `op_name = "毒蜂II"` 存在时，`replace("毒蜂", "X(毒蜂)")` 会把 "毒蜂II" 也部分替换成 "X(毒蜂)II"。
2. 如果两个 nick 都映射到同一个 op_id（理论上 `set()` 防了，但 fact_store 不保证），第二轮替换会重叠：text 里有 `nick1(毒蜂)`，第二轮发现 `f"{nick2}({op_name})" not in text` 为 True，再插一个。
3. dict 迭代顺序不保证，结果不可复现。

**修法**：先按 op_name 长度降序排，用 `re.sub` 加 `\b` 之类的边界（中文没有 word boundary，用负向 lookbehind 排除 `(` 前缀）。或者建临时占位符两阶段替换。

**影响**：低频但确定的展示 bug。

---

### P1-5 `bridge.py:225` 工具循环里**截断结果到 2000 字符**直接丢给 LLM，没标记被截

```python
if len(result) > 2000:
    result = result[:2000] + "\n...(截断)"
```

战绩详情常超 2000 字（10 局 × 全部队友），AI 看到 `...(截断)` 不知道后面是 30 行还是 30000 行，可能基于不完整数据下结论。

**修法**：截断前打日志 + result 头部加 "原长 N 字符，仅展示前 2000"。

**影响**：偶尔 AI 给的建议不全面，群友追问。

---

### P1-6 DF `df_stats/credentials/` 反爬 + cookie 失效感知很弱

`df_secret()` 在 cookie 过期时只会返回 "今日密码接口返回空"，没有主动检测 token 失效再重抓的能力。`scripts/df_stats/cli.py probe` 是手动工具。
**建议**：拉接口失败时把 HTTP 状态/错误体写进 `memory.add_episode("cookie_error", ...)`，群里也加一个 "@小方 检查 cookie" 的工具调用 `df_cookie_status` 主动汇报。

**影响**：cookie 一过期 bot 静默吐空，群友不知道是 cookie 问题还是 bot 问题。

---

### P1-7 group_id 硬编码 `257381453` 散落多处

```
gamebot/games/df/bridge.py:60  注释里写"如 257381453"
gamebot/games/df/README.md:44   group_id: 257381453
config.yml                       group_id: 257381453（实际）
docs/QUICK_START.md              估计也有
```

实际值在 `config.yml`，没有运行时硬编码。**没问题，是文档**。但 README 里写绝对群号容易和 config 漂移。建议 README 里写 `<DF 群号>` 占位符，附"实际配置在 config.yml"。

**影响**：低，主要是新接手的人困惑。

---

### P1-8 `DFAbilities.df_unknowns` 重复拉数据，不复用 `_client`

`df_unknowns` 自己 `from df_stats import load_from_curl_file, fetch_all_pages`，跟同类里其他工具完全独立（其他都用 `self._client(...)`）。维护时改动客户端构造要扫两处。

**修法**：统一走 `self._client(self.record_curl, "战绩")`。

---

### P1-9 隐私：QQ 群名片 + nickname 入 memory 没有脱敏选项

`bridge.reply` → `converse` → `add_episode("conversation", f"{nickname}: {message[:100]}")`。每条消息都把群昵称记入 `episodes.jsonl`。Facts 表里还有别名 ↔ 真名映射。**这是有意为之**（人脸识别要这个），但是：

1. 没有"用户主动遗忘自己"的指令（除了 unalias）
2. `episodes.jsonl` 没有保留窗口（见 P1-2）
3. `data/memory/` 在 `.gitignore` 里，OK。但是没有"导出我所有数据 / 删我所有数据"的工具
4. 群名片本身可能是用户真名（很多群友习惯把群名片设成真名+学号）

**建议**：起码加一个 `[CMD:df_forget_me <昵称>]` 工具，把指定 subject 的所有 facts + 含 actor 的 episodes 全清掉。隐私合规角度这是 GDPR/PIPL 的 "right to be forgotten" 基本要求。

**影响**：低概率高严重度。

---

### P1-10 prompt.md 占位符表过时

`prompt.md` 文件顶部 HTML 注释说：
> {alias_block} — 当前已注册别名表（自动从 data/df_aliases.json 渲染）
> {notes_block} — 队员档案笔记（自动从 data/df_squad_notes.json 渲染）

但是 2026-05-13 后，`alias_block` 来自 `aliases.all()`（已从 memory 读），`notes_block` 来自 `memory.find_facts(predicate="note")`。**注释跟实际不符**，会误导改 prompt 的人去读不存在的旧 JSON。

**修法**：改成 "从 GameMemory.facts 渲染（predicate=alias_to_op / note）"。

---

## P2（可改进，nice-to-have）

### P2-1 `ai_provider.py:68` `api_key or "ollama"` 是个 magic value

provider 是 deepseek 但忘填 key 时，OpenAI client 会被赋予字面字符串 "ollama"，下游报 401 而不是"配置错误"。**应该在 `config.load_config` 里强校验**（已有 `if config.ai.provider != "ollama" and not config.ai.api_key`），那 `ai_provider.py` 里就不用做 fallback。

---

### P2-2 `qq_bridge.py:159` 的 WebSocket 是手写实现

`_ws_connect / _ws_read_frame / _recv_exact` 写得没问题但脆弱（不支持 fragmented frames、不处理大于 64KB 帧外的边界、masked check 顺序、close opcode 不主动回 close 帧）。**为什么不用 `websockets` / `websocket-client` 库？** 现在能跑只是因为 NapCat 发的帧都是单 frame text。

**建议**：换成 `websocket-client` 几十行代码就搞定，还支持自动 ping/pong。如果坚持手写，至少把 ping 帧（0x9）的 payload 原样回传（当前 pong 永远 payload=空，违反 RFC 6455 §5.5.3）。

---

### P2-3 `bot.py:441` `from_qq` 二分 system_prompt 已经够用，但 `qq_player = f"QQ:{nickname}"` 会让每个 QQ 群友都建一份 `memory/history/QQ:xxx.json`

memory 文件没有清理，nickname 变了（群里改名）就是新文件，老文件永远留下。
**建议**：长期看应该把 QQ 群对话历史也下沉到 GameMemory.episodes（按 actor 维度）。

---

### P2-4 `DFStatsConfig` 8 个字段 + `aliases_path` 已经被注释为"保留兼容但内部不用"

```python
aliases_path: str = "data/df_aliases.json"  # 保留参数兼容，但内部已不读
```

死配置项就该删。**保留只会让人误以为"改这个还有用"**。`bridge.py:71` 也是同样情况。Migration 已经做完了，下一个 phase 直接清。

---

### P2-5 `mcbot.backup.1511/` 整个目录留着没意义

迁移完成后保留备份目录情有可原，但 47 个文件常驻 git/工作区会污染搜索结果（grep 全仓库 alias 模式时一堆 backup 假阳性）。已经在 `.gitignore` 里？验证一下。

`.gitignore`: `mcbot.backup.*/` — 已忽略 git，但本地仍在。**建议定个删除日期**（commit 注释里写 "2026-06-01 后删"），到期一刀切。

---

### P2-6 `mc/bot.py` 941 行严重过长，初始化方法占 300+ 行

`ChatBot.__init__` 从 line 96 到 line 406 全是组件实例化。**应该抽 builder pattern**：
- `_init_persistence(config)` → memory, registry, time_capsule, chat_logger
- `_init_schedulers(config)` → weekly_*, daily_*, random_roast
- `_init_external(config)` → qq, df_stats, messageboard
- `_init_providers()` → chat_provider, online_provider, weather_provider 三个内嵌函数

**影响**：今天读懂要 5 分钟，下个 maintainer 想加新组件不知该插哪里。

---

### P2-7 `weather_provider` 等 closure 内嵌在 `__init__` 里

`_weather_cache = {...}` 用闭包持有状态，下次想加单元测试根本测不了——必须 patch 整个 `ChatBot.__init__`。**抽成独立 class** 或独立 module 函数 + dict 参数。

---

### P2-8 `df_stats` 库 `sys.path.insert` 三处重复

`bridge.py / abilities.py / aliases.py` 都重复同一段：
```python
_DF_STATS_DIR = Path(__file__).resolve().parents[3] / "scripts" / "df_stats"
if str(_DF_STATS_DIR) not in sys.path:
    sys.path.insert(0, str(_DF_STATS_DIR))
```

**修法**：要么把 `scripts/df_stats` 改成正经 package（加 `setup.py` / `pyproject.toml`，pip install -e），要么在 `gamebot/games/df/__init__.py` 里集中一处。`sys.path.insert(0, ...)` 在生产里是常见隐患——会让全局 import 顺序意外被影响（如果 df_stats 目录里有跟 stdlib 同名模块）。

---

### P2-9 `EpisodeLog._load` 同步读全部文件，启动慢

文件 100MB 时启动得读全行。memory 设计上 episodes 是 jsonl 就是为了"按需 tail 读"——但实际 `__init__` 直接全 load 到内存的 `_episodes: list`。

**建议**：把"最近 N 条"做成 sqlite 视图或者按月分文件（`episodes-2026-05.jsonl`）。Phase 6 工作。

---

### P2-10 `df_note` 的 subject 抽取启发式（line 320-328）会出错

```python
m = _re.match(r"^([一-鿿]{2,7})(?:是|玩|主|双修|擅长|喜欢|常用)", text)
subj = m.group(1) if m else "squad"
for s in self.memory.all_subjects():
    if text.startswith(s):
        subj = s
        break
```

- "毒蜂是个好干员" 会把 "毒蜂" 当 subject。本意应该是 squad-level 的笔记。
- 第二个 for 循环依赖 `all_subjects()` 的迭代顺序（set），不稳定。
- 如果"龙龙"和"龙龙要打翻你们"同时存在，先匹哪个不可控。

**修法**：要求 AI 调用时显式带 subject（让 prompt 提示"先 df_remember 把 subject 定下，再 df_note"），或者用 LLM 自己抽 subject 而不是正则。

---

## 安全 / 隐私 单独清单

| 项 | 状态 | 评 |
|---|---|---|
| `.env` / `config.yml` / API key | `.gitignore` 已覆盖 | OK |
| `scripts/df_stats/credentials/raw_curl*.sh`（含 access_token） | `.gitignore` 已覆盖 | OK |
| `data/df_aliases.json` 等 9 个运行时文件 | 都在 `.gitignore` | OK |
| `data/memory/` 整个目录 | 在 `.gitignore` | OK |
| QQ 号入 memory | 间接（昵称 / actor） | P1-9 建议加遗忘指令 |
| 腾讯接口防爬 | 单 cookie 长期使用，无 rotate | 卡顿没有自动 backoff |
| 群成员 `get_group_member_info` 调用频率 | 每条 `[CQ:at]` 都现查一次 | 无缓存 → 腾讯可能限流 |
| LLM prompt 注入 | system prompt 含群昵称、消息，未做过滤 | 中等：群友发`}}]}}` 会让 prompt 渲染失败（已经在 `.format` KeyError catch 里有兜底） |
| RCON 密码 | 在 `config.yml`，不入库 | OK |

---

## 整体评分

| 维度 | 分（10 分制） | 注 |
|---|---|---|
| 架构 / 分层 | 7 | core/games 分层清晰，但 game_memory 在 MC 是死代码、search.py 整个废掉 |
| 正确性 | 5 | `summarize.py:118` 时区 bug、`self_id` 不存在、`_apply_aliases` 顺序敏感 |
| 可维护性 | 6 | bot.py 941 行难看、3 处 sys.path hack、`aliases_path` 等死配置 |
| 性能 | 6 | 当前没问题，但 retrieve_relevant_facts 线性扫描 + 写盘非原子 + 同步阻塞 WS |
| 文档 / 注释 | 9 | 中文注释充足、CLAUDE.md/CHANGELOG/README 齐全，是亮点 |
| 安全 / 隐私 | 6 | gitignore 覆盖足，但缺"用户遗忘"指令、prompt 注入未做防护 |
| **综合** | **6.5** | 写得不糙，但有几个隐藏 bomb；现在能跑只是因为负载小 |

---

## 如果只能修 3 个，选这 3 个

1. **P0-3 + P0-4 一起做：DF bridge `_history` 加锁 + 把 WS 事件 dispatch 到 ThreadPool**。当前阻塞 WS 线程的设计是定时炸弹：DF LLM 慢一次 → MC 群体感死机。这是最直接影响用户的问题。

2. **P0-5：facts.json atomic write**。alias 表丢一次群友档案就清零，且只有一行日志。两行代码（`tmp + os.replace`）就能避免不可逆数据丢失。

3. **P1-1 + P1-2：把 FTS5 / Phase 5 prune 这两块**死代码做一个二选一决断**。要么真接进 `ChatBot.run()` 的定时任务，要么从 README 删掉 "Phase 5 自动修剪" 的宣传，搬走 `search.py`。半成品基建是技术债的最大来源——下一个 maintainer 读 README 以为它在工作，结果踩坑。

P0-1 时区 bug 虽然严重但当前没人调它的函数，可以放第 4 位；P0-2 `self_id` 死代码看起来惊悚但实际无影响，最后再清。
