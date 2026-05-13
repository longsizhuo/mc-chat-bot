"""GameMemory：FactStore + EpisodeLog 的统一 facade。

跨游戏共用。每个 game module 拿一个 GameMemory 实例即可：
    memory = GameMemory(root="data/memory/df")
    memory.remember("风格一", "alias_to_op", 40011, source="user:龙龙")
    memory.add_episode("conversation", "群友问了上把战绩", actors=["我不是龙龙"])

    # system prompt 智能拼接
    context = memory.context_for_message("@王十十寸 现在玩老黑")
    # → 自动 surface 王十十寸 和 老黑 的相关 facts + 最近 episodes
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .fact_store import Fact, FactStore
from .episode_log import Episode, EpisodeLog
from .retrieval import (
    retrieve_relevant_facts,
    retrieve_relevant_episodes,
    relevant_subjects,
    render_facts_block,
    render_episodes_block,
)
from .search import SearchIndex, HAS_FTS5


class GameMemory:
    """统一 memory facade。

    设计目标：
    - 跨游戏共用：MC bot 和 DF bot 都用同一套 API
    - subject 维度聚合：关于"风格一"的所有事实一次能拉出
    - 按 query 智能 surface：不用每次把所有 facts 都塞 system prompt
    - 时序事件流：对话/匹配/变更都 append，可回溯
    """

    def __init__(self, root: str | Path):
        """root: memory 存储根目录，如 data/memory/df。"""
        self.root = Path(root)
        self.facts = FactStore(self.root / "facts.json")
        self.episodes = EpisodeLog(self.root / "episodes.jsonl")
        # FTS5 索引（可选，lazy build）
        self._search: Optional[SearchIndex] = None

    # ============ Facts API ============

    def remember(
        self,
        subject: str,
        predicate: str,
        value: Any,
        source: str = "ai",
        confidence: float = 1.0,
    ) -> Fact:
        """添加/更新一条事实。dedupe 默认开。"""
        return self.facts.add(subject, predicate, value, source, confidence)

    def forget(self, fact_id: str) -> bool:
        return self.facts.remove(fact_id)

    def forget_where(
        self,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
        value: Any = None,
    ) -> int:
        return self.facts.remove_where(subject, predicate, value)

    def recall(self, subject: str) -> list[Fact]:
        """关于某主体的所有事实。"""
        return self.facts.by_subject(subject)

    def find_facts(
        self,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
        value: Any = None,
    ) -> list[Fact]:
        return self.facts.find(subject, predicate, value)

    def all_subjects(self) -> set[str]:
        return self.facts.subjects()

    # ============ Episodes API ============

    def add_episode(
        self,
        type: str,
        content: str,
        actors: Optional[list[str]] = None,
        metadata: Optional[dict] = None,
    ) -> Episode:
        return self.episodes.append(type, content, actors, metadata)

    def recent_episodes(
        self,
        n: int = 10,
        type: Optional[str] = None,
        actor: Optional[str] = None,
    ) -> list[Episode]:
        return self.episodes.recent(n, type, actor)

    # ============ 智能检索 ============

    def context_for_message(
        self,
        message: str,
        max_facts: int = 20,
        max_episodes: int = 5,
    ) -> str:
        """根据消息内容自动拼接相关 facts + recent episodes 的文本块。

        给 system prompt 用：不要每次把所有 facts dump 进去，按 query 智能 surface。

        返回类似：
            ### 相关事实
            • 风格一：
                - alias_to_op = 40011
                - also_plays = 20005
                ...
            ### 最近相关事件
            • [2026-05-13 18] [match] 航天-绝密 全员撤离...
        """
        facts = retrieve_relevant_facts(self.facts, message, max_facts)
        subjects_in_facts = {f.subject for f in facts}
        episodes = retrieve_relevant_episodes(
            self.episodes, message, subjects_in_facts, max_episodes
        )

        parts = []
        if facts:
            parts.append("### 相关事实\n" + render_facts_block(facts))
        if episodes:
            parts.append("### 最近相关事件\n" + render_episodes_block(episodes))
        return "\n\n".join(parts) if parts else "（没有匹配到任何相关记忆）"

    # ============ FTS5 全文检索（Phase 2 优化）============

    def _ensure_search(self) -> SearchIndex:
        """懒加载 + 自动重建 FTS5 索引。

        触发：第一次调 search() 时建索引；后续可手动 rebuild_search() 重建。
        小数据量下 rebuild 很快（几千条 facts 也就毫秒级）。
        """
        if self._search is None:
            self._search = SearchIndex(self.root / "search.db")
            self._search.rebuild_from(self.facts, self.episodes)
        return self._search

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        """全文检索 facts + episodes。

        返回 list[{doc_type, doc_id, subject, content}]，按 BM25 相关性降序。
        如果 SQLite 没装 FTS5 模块自动退化到 LIKE。
        """
        idx = self._ensure_search()
        return idx.search(query, top_k)

    def rebuild_search(self) -> dict:
        """重建 FTS5 索引（数据大量写入后调用）。"""
        idx = self._ensure_search()
        return idx.rebuild_from(self.facts, self.episodes)

    def stats(self) -> dict:
        """memory 大致统计，调试 / 状态检查用。"""
        return {
            "fact_count": len(self.facts),
            "episode_count": len(self.episodes),
            "subjects": len(self.all_subjects()),
            "fts5": HAS_FTS5,
            "root": str(self.root),
        }
