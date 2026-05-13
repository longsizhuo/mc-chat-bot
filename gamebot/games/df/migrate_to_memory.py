"""一次性迁移脚本：把旧的 3 个 JSON 文件导入新的 GameMemory。

旧文件：
- data/df_aliases.json       {昵称: 干员ID}
- data/df_squad_notes.json   ["笔记1", "笔记2", ...]
- data/df_extra_ops.json     {"干员ID": "中文名"}

新存储：
- data/memory/df/facts.json     SPO 三元组
- data/memory/df/episodes.jsonl  时序事件

跑法：python -m gamebot.games.df.migrate_to_memory

幂等：再跑一次不会重复（dedupe 在 FactStore 里）。旧文件不删（保留作为备份），
但 DF 模块 runtime 从今天起只读 memory。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from gamebot.core.memory import GameMemory


def migrate(
    aliases_path: str | Path = "data/df_aliases.json",
    notes_path: str | Path = "data/df_squad_notes.json",
    extra_ops_path: str | Path = "data/df_extra_ops.json",
    memory_root: str | Path = "data/memory/df",
) -> dict:
    """迁移所有旧数据。返回统计字典。"""
    memory = GameMemory(root=memory_root)
    stats = {
        "aliases_imported": 0,
        "notes_imported": 0,
        "extra_ops_imported": 0,
        "before": dict(memory.stats()),
    }

    # 1. aliases.json
    p = Path(aliases_path)
    if p.exists():
        try:
            aliases = json.loads(p.read_text(encoding="utf-8"))
            for nick, op_id in aliases.items():
                memory.remember(
                    subject=nick,
                    predicate="alias_to_op",
                    value=int(op_id),
                    source="migrated:aliases",
                    confidence=1.0,
                )
                stats["aliases_imported"] += 1
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            print(f"[migrate] aliases 加载失败：{e}")

    # 2. squad_notes.json
    p = Path(notes_path)
    if p.exists():
        try:
            notes = json.loads(p.read_text(encoding="utf-8"))
            for note in notes:
                # 简单启发式：从 note 文本里抽出"看起来是 subject 的名字"
                subj = _extract_subject_from_note(note, memory.all_subjects())
                memory.remember(
                    subject=subj,
                    predicate="note",
                    value=note,
                    source="migrated:notes",
                    confidence=0.9,  # 自由文本笔记，没那么 verified
                )
                # 同时作为 episode 记一笔（保留时间线）
                memory.add_episode(
                    type="note_added",
                    content=note,
                    actors=[subj] if subj != "squad" else [],
                    metadata={"migrated": True},
                )
                stats["notes_imported"] += 1
        except (json.JSONDecodeError, TypeError) as e:
            print(f"[migrate] notes 加载失败：{e}")

    # 3. extra_ops.json
    p = Path(extra_ops_path)
    if p.exists():
        try:
            extras = json.loads(p.read_text(encoding="utf-8"))
            for op_id, chinese_name in extras.items():
                memory.remember(
                    subject=f"op:{op_id}",
                    predicate="chinese_name",
                    value=str(chinese_name),
                    source="migrated:extra_ops",
                    confidence=1.0,
                )
                stats["extra_ops_imported"] += 1
        except (json.JSONDecodeError, TypeError) as e:
            print(f"[migrate] extra_ops 加载失败：{e}")

    stats["after"] = dict(memory.stats())
    return stats


def _extract_subject_from_note(note: str, known_subjects: set[str]) -> str:
    """从 note 文本里猜 subject。

    策略：
    1. 看 note 开头是否是某个已知 subject 名字（如"风格一双修..."→ 风格一）
    2. 否则 fallback 为 "squad"（全队事实）
    """
    note_clean = note.strip()
    # 已知 subject 完整出现且在开头
    for s in sorted(known_subjects, key=len, reverse=True):
        if note_clean.startswith(s):
            return s
    # 中文人名启发式：开头 2-5 字的中文，跟在动词前
    m = re.match(r"^([一-鿿]{2,7})(?:是|玩|主|双修|擅长|喜欢|常用)", note_clean)
    if m:
        return m.group(1)
    return "squad"


if __name__ == "__main__":
    stats = migrate()
    print("=== 迁移完成 ===")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
