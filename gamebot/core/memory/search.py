"""SQLite FTS5 全文检索 —— Phase 2 升级。

子串匹配在 facts 数量上千、episodes 上万后会变慢。FTS5 提供 O(log n) 的
关键词检索 + BM25 排序。本模块按需重建索引（不是源头存储），数据真源
依然在 facts.json 和 episodes.jsonl。

设计选择：
- SQLite 内置，零依赖
- 索引可重建（任意时候 rebuild）
- 中文友好：默认 tokenizer 是 unicode61，对短中文 token 效果一般；
  fallback 时建议先把文本按 jieba 之类分好词写入（本模块暂用 unicode61，
  实测 facts 几千条以内查询命中率够用）
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, Optional

from .fact_store import Fact, FactStore
from .episode_log import Episode, EpisodeLog


def _has_fts5() -> bool:
    """检测当前 SQLite 是否带 FTS5 模块。"""
    try:
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
            return True
        except sqlite3.OperationalError:
            return False
        finally:
            conn.close()
    except Exception:
        return False


HAS_FTS5 = _has_fts5()


class SearchIndex:
    """SQLite FTS5 索引。

    用法：
        idx = SearchIndex("data/memory/df/search.db")
        idx.rebuild_from(fact_store, episode_log)
        results = idx.search("航天 巴克什", top_k=10)
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connect()

    def _connect(self) -> None:
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        if not HAS_FTS5:
            # 退化为普通表 + LIKE 查询
            self.conn.execute(
                """CREATE TABLE IF NOT EXISTS docs (
                    doc_type TEXT, doc_id TEXT, subject TEXT, content TEXT
                )"""
            )
            return
        self.conn.execute(
            """CREATE VIRTUAL TABLE IF NOT EXISTS docs USING fts5(
                doc_type, doc_id, subject, content,
                tokenize='unicode61 remove_diacritics 2'
            )"""
        )

    # ---- 索引构建 ----

    def rebuild_from(self, fact_store: FactStore, episode_log: EpisodeLog) -> dict:
        """从源数据全量重建索引。返回统计字典。"""
        with self.conn:
            self.conn.execute("DELETE FROM docs")
            for f in fact_store.all():
                # fact 的"内容"是 predicate + value 拼起来便于检索
                content = f"{f.predicate} {f.value}"
                self.conn.execute(
                    "INSERT INTO docs (doc_type, doc_id, subject, content) VALUES (?,?,?,?)",
                    ("fact", f.fact_id, f.subject, content),
                )
            for e in episode_log.all():
                subject = " ".join(e.actors) if e.actors else ""
                self.conn.execute(
                    "INSERT INTO docs (doc_type, doc_id, subject, content) VALUES (?,?,?,?)",
                    ("episode", e.episode_id, subject, e.content),
                )
        return {
            "fts5_available": HAS_FTS5,
            "facts_indexed": len(fact_store),
            "episodes_indexed": len(episode_log),
        }

    # ---- 查询 ----

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        """搜出 top_k 条匹配的 doc，按相关性降序。

        返回 list[{doc_type, doc_id, subject, content}].
        """
        query = (query or "").strip()
        if not query:
            return []

        if HAS_FTS5:
            # FTS5 MATCH，自动按 BM25 排序
            try:
                rows = self.conn.execute(
                    "SELECT doc_type, doc_id, subject, content "
                    "FROM docs WHERE docs MATCH ? LIMIT ?",
                    (query, top_k),
                ).fetchall()
                return [dict(r) for r in rows]
            except sqlite3.OperationalError:
                pass  # 查询语法不合 FTS5，fallback 到 LIKE

        # 不支持 FTS5 或查询不合法 → 退化为 LIKE
        pattern = f"%{query}%"
        rows = self.conn.execute(
            "SELECT doc_type, doc_id, subject, content FROM docs "
            "WHERE content LIKE ? OR subject LIKE ? LIMIT ?",
            (pattern, pattern, top_k),
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass
