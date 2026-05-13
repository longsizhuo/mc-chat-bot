"""按消息内容检索相关 facts + episodes，给 system prompt 智能拼接。

Phase 1：纯字符串匹配（subject / content 子串）。
Phase 2 会换成 SQLite FTS5。但 API 不变。

思路：避免每次都把整张 fact 表 dump 进 prompt（之前 system prompt 5017 字
就是因为这个）。改成"消息里提到谁/什么 → 只 surface 相关的"。
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

from .fact_store import Fact, FactStore
from .episode_log import Episode, EpisodeLog


# 简单分词：抽连续 2+ 字符的中文 / 单词，过滤短停用词
_TOKEN_PATTERN = re.compile(r"[一-鿿]{1,}|[a-zA-Z0-9_]{2,}")
_STOPWORDS = {
    "我", "你", "他", "她", "我们", "你们", "他们",
    "的", "了", "是", "在", "和", "也", "吗", "呢", "啊", "吧",
    "上把", "这把", "那把", "怎么", "什么", "哪个",
}


def _tokenize(text: str) -> set[str]:
    """从文本里抽出候选关键词（去除停用词）。"""
    tokens = set(_TOKEN_PATTERN.findall(text))
    return {t for t in tokens if t not in _STOPWORDS and len(t) >= 2}


def relevant_subjects(text: str, candidates: Iterable[str]) -> set[str]:
    """从消息文本里识别可能涉及的 subject。

    匹配规则（按优先级）：
    1. subject 完整出现在 text 里
    2. text 里有 subject 的任意 token
    """
    text_lower = text.lower()
    tokens = _tokenize(text)
    matched: set[str] = set()

    for s in candidates:
        if not s:
            continue
        # 完整出现
        if s in text or s.lower() in text_lower:
            matched.add(s)
            continue
        # token 部分匹配（subject 也 tokenize 后看交集）
        s_tokens = _tokenize(s)
        if s_tokens & tokens:
            matched.add(s)

    return matched


def _resolve_canonical(fact_store: FactStore, subject: str) -> set[str]:
    """从一个 subject 出发，找出所有"等价"的 subject（顺藤摸瓜）。

    例：消息提到 "王老板" → 查到 canonical_name=王博 → 也要把 "王博" 的事实算上
    例：消息提到 "王博" → 查 also_known_as 列表 → 把 "王老板"、"王十十..." 算上

    返回的 set 包含原 subject + 所有等价别名。
    """
    expanded = {subject}
    queue = [subject]
    while queue:
        cur = queue.pop()
        # 它指向谁（canonical_name → 真名）
        for f in fact_store.find(subject=cur, predicate="canonical_name"):
            if isinstance(f.value, str) and f.value not in expanded:
                expanded.add(f.value)
                queue.append(f.value)
        # 谁指向它（也算等价）
        for f in fact_store.find(predicate="canonical_name", value=cur):
            if f.subject not in expanded:
                expanded.add(f.subject)
                queue.append(f.subject)
        # also_known_as
        for f in fact_store.find(subject=cur, predicate="also_known_as"):
            if isinstance(f.value, str) and f.value not in expanded:
                expanded.add(f.value)
                queue.append(f.value)
        for f in fact_store.find(predicate="also_known_as", value=cur):
            if f.subject not in expanded:
                expanded.add(f.subject)
                queue.append(f.subject)
    return expanded


def retrieve_relevant_facts(
    fact_store: FactStore,
    text: str,
    max_facts: int = 20,
) -> list[Fact]:
    """检索消息相关的 facts。

    1. 找出 text 里提到的 subject
    2. **顺藤摸瓜**：每个匹配的 subject 通过 canonical_name / also_known_as
       关系扩展出等价 subject 集合（王老板 ↔ 王博 ↔ 王十十十十十寸）
    3. 拉所有等价 subject 的 facts
    4. 按 confidence 降序，updated_at 降序取前 N
    """
    all_subjects = fact_store.subjects()
    matched = relevant_subjects(text, all_subjects)
    if not matched:
        return []

    # 扩展每个 matched subject 到它的等价集合
    expanded: set[str] = set()
    for s in matched:
        expanded |= _resolve_canonical(fact_store, s)

    candidates: list[Fact] = []
    for subj in expanded:
        candidates.extend(fact_store.by_subject(subj))

    # 去重 + 排序
    seen: set[str] = set()
    deduped: list[Fact] = []
    for f in sorted(candidates, key=lambda x: (-x.confidence, x.updated_at), reverse=False):
        if f.fact_id in seen:
            continue
        seen.add(f.fact_id)
        deduped.append(f)
    # 再次按相关性排（confidence 降序 + updated_at 降序）
    deduped.sort(key=lambda x: (-x.confidence, x.updated_at), reverse=True)
    return deduped[:max_facts]


def retrieve_relevant_episodes(
    episode_log: EpisodeLog,
    text: str,
    fact_subjects: Optional[set[str]] = None,
    max_episodes: int = 5,
) -> list[Episode]:
    """检索消息相关的 episodes。

    优先级：
    1. content 里包含 text 的 token（子串匹配）
    2. actors 含 text 提到的 subject
    3. 按时间倒序取前 N
    """
    text_tokens = _tokenize(text)
    matched_actors = fact_subjects or set()

    scored: list[tuple[int, Episode]] = []
    for ep in episode_log.all():
        score = 0
        # 内容关键词
        for tok in text_tokens:
            if tok in ep.content:
                score += 2
        # actor 命中
        for actor in ep.actors:
            if actor in matched_actors or actor in text:
                score += 3
        if score > 0:
            scored.append((score, ep))

    # 同分按时间倒序
    scored.sort(key=lambda x: (x[0], x[1].timestamp), reverse=True)
    return [ep for _, ep in scored[:max_episodes]]


def render_facts_block(facts: list[Fact], max_chars: int = 1500) -> str:
    """把 facts 渲染成 system prompt 用的文本块。

    按 subject 分组，每个 subject 一段。
    """
    if not facts:
        return "（暂无相关事实）"

    by_subj: dict[str, list[Fact]] = {}
    for f in facts:
        by_subj.setdefault(f.subject, []).append(f)

    lines = []
    used = 0
    for subj, subj_facts in by_subj.items():
        block = f"• {subj}：\n"
        for f in subj_facts:
            block += f"    - {f.predicate} = {f.value}"
            if f.source != "ai":
                block += f"  [来源: {f.source}]"
            block += "\n"
        if used + len(block) > max_chars:
            lines.append(f"...(还有 {len(facts) - len(lines)} 条因长度限制省略)")
            break
        lines.append(block)
        used += len(block)
    return "".join(lines).rstrip()


def render_episodes_block(episodes: list[Episode], max_chars: int = 800) -> str:
    """把 episodes 渲染成 system prompt 用的文本块。"""
    if not episodes:
        return "（暂无相关事件）"

    lines = []
    used = 0
    for ep in episodes:
        # 时间只保留日期+小时
        time_short = ep.timestamp[:13].replace("T", " ")
        line = f"• [{time_short}] [{ep.type}] {ep.content}\n"
        if used + len(line) > max_chars:
            lines.append("...(更多事件因长度省略)")
            break
        lines.append(line)
        used += len(line)
    return "".join(lines).rstrip()
