# gamebot/core/memory · 通用 agent memory

跨游戏共用的 agent memory 模块。设计参考 [Hermes Agent](https://github.com/NousResearch/hermes-agent) 的 MEMORY.md/USER.md + [OpenClaw](https://github.com/openclaw/openclaw) 的 "recall before execution, save after each run"。

## 解决什么问题

之前 DF 模块用了 3 个分散的 JSON 文件存"记忆"：
- `data/df_aliases.json` — 群友昵称 ↔ 干员 ID（1:1）
- `data/df_squad_notes.json` — 自由文本笔记 list
- `data/df_extra_ops.json` — 新干员 ID 表

每个文件 schema 不一样，AI 拿到的 system prompt 把整张 alias 表 + 整张 notes 表都 dump 进去（5000+ 字符），既浪费 token 又不精准。**改 system prompt 要动 3 个文件 + 1 段 Python 代码**。

新设计：**统一 SPO 三元组 + 时序事件流 + 智能检索**。

## 三个核心组件

| 文件 | 职责 |
|---|---|
| `fact_store.py` | **FactStore** — Subject-Predicate-Value 三元组持久化（JSON）。所有结构化事实统一存这里 |
| `episode_log.py` | **EpisodeLog** — 时序事件流（JSONL append-only）。对话/匹配/变更都记一条 |
| `retrieval.py` | **检索** — 按消息内容自动 surface 相关 facts + episodes，给 system prompt 用 |
| `memory.py` | **GameMemory** — facade，把上面三个组合成统一 API |

## API 示例

```python
from gamebot.core.memory import GameMemory

memory = GameMemory(root="data/memory/df")

# 记事实
memory.remember("风格一", "alias_to_op", 40011, source="user:龙龙")
memory.remember("风格一", "also_plays", 20005)
memory.remember("风格一", "preferred_role", "医疗+信息")

# 记事件
memory.add_episode(
    type="match",
    content="航天-绝密 全员撤离 +215万",
    actors=["龙龙", "老黑", "风格一"],
)

# 检索（关于某主体的所有事实）
facts = memory.recall("风格一")
# → [Fact(alias_to_op=40011), Fact(also_plays=20005), ...]

# 智能 surface：根据消息内容自动找相关 facts + episodes
context = memory.context_for_message("风格一最近怎么样")
# → 自动拼接出
#   ### 相关事实
#   • 风格一：alias_to_op=40011, also_plays=20005, preferred_role=医疗+信息
#   ### 最近相关事件
#   • [2026-05-13 18] [match] 航天-绝密 全员撤离 +215万
```

## 数据格式

### `data/memory/<game>/facts.json`

```json
{
  "facts": [
    {
      "fact_id": "a3f5e8c1",
      "subject": "风格一",
      "predicate": "alias_to_op",
      "value": 40011,
      "source": "user:龙龙",
      "confidence": 1.0,
      "added_at": "2026-05-13T18:35:00+00:00",
      "updated_at": "2026-05-13T18:35:00+00:00"
    }
  ]
}
```

### `data/memory/<game>/episodes.jsonl`

每行一个 JSON 对象（append-only）：

```jsonl
{"episode_id":"...","type":"match","actors":["龙龙","老黑"],"content":"航天-绝密 全员撤离 +215万","timestamp":"..."}
{"episode_id":"...","type":"alias_change","actors":["老黑"],"content":"老黑→牧羊人","timestamp":"..."}
```

## 检索策略（Phase 1 简版）

`retrieval.py` 目前用字符串子串 + 简单分词：
1. 从消息文本里抽候选 token（过滤停用词）
2. 跟所有 fact subjects 做完整匹配 / token 交集
3. 命中的 subject 拉所有 facts，按 confidence + 时间排序
4. episodes 按 actor 命中 + content 词频打分

**Phase 2 计划**：上 SQLite FTS5（全文检索）+ 简单语义相似度。API 不变。

## 跨游戏复用

```python
# DF 模块
df_memory = GameMemory(root="data/memory/df")

# MC 模块（未来迁移过来）
mc_memory = GameMemory(root="data/memory/mc")

# 不冲突，各管各的（也可以共用一个 root 实现跨游戏记忆）
```

## 与现有 DF aliases / notes 的兼容关系

Phase 3 会做迁移：

| 旧 | 新 |
|---|---|
| `df_aliases.json: {"老黑": 30008}` | `Fact(subject="老黑", predicate="alias_to_op", value=30008)` |
| `df_squad_notes.json: ["风格一双修医疗+信息"]` | `Fact(subject="风格一", predicate="note", value="...")` + Episode |
| `df_extra_ops.json: {"10012": "疾风"}` | `Fact(subject="op:10012", predicate="chinese_name", value="疾风")` |

迁移脚本会保留旧文件作为备份，新代码只读 memory。

## 设计原则

1. **subject 是宇宙原语**：所有事实都围绕"关于谁/什么"展开
2. **append-only 倾向**：episodes 永远只 append，facts 用 dedupe 避免冗余
3. **不假设单一来源**：source 字段记录"是谁告诉我的"——AI 推断 vs 用户明示要区分
4. **JSON 优先 SQL 第二**：项目规模小，JSON 够用；上 SQL 是为了 FTS 不是为了规模
