"""DFAliases —— 干员别名管理。

2026-05-13 重构：底层从独立 JSON 文件改成 gamebot.core.memory.GameMemory，
但保持外部 API 不变（bridge / abilities 不用改）。

存储模型（在 memory.facts）：
    Fact(subject=<昵称>, predicate="alias_to_op", value=<干员ID>)
    + 可选 canonical_name / also_known_as 描述多重昵称关系

句式解析（"我玩牧羊人" / "@老王 为 牧羊人" 等）逻辑保留。
"""

from __future__ import annotations

import difflib
import re
import sys
from pathlib import Path
from typing import Optional

# 让 df_stats 库可导入
_DF_STATS_DIR = Path(__file__).resolve().parents[3] / "scripts" / "df_stats"
if str(_DF_STATS_DIR) not in sys.path:
    sys.path.insert(0, str(_DF_STATS_DIR))

from gamebot.core.memory import GameMemory


def _load_operator_table() -> dict[str, int]:
    """从 df_stats.maps 加载中文名 → ArmedForceId 反向表。"""
    try:
        from df_stats.maps import OPERATOR_NAMES
        return {name: oid for oid, name in OPERATOR_NAMES.items()}
    except Exception:
        return {}


class DFAliases:
    """干员别名管理器（memory backend 版）。

    所有数据都存在 GameMemory.facts 里，predicate="alias_to_op"。
    """

    # 学习句式正则（跟旧版保持一致，方便 bridge.reply 兼容）
    PATTERN_ALIAS = re.compile(r"^\s*alias\s+(\S+)\s+(\S+)\s*$", re.IGNORECASE)
    PATTERN_SELF = re.compile(r"^\s*我(?:玩|是|打|用|主)(.+?)\s*$")
    PATTERN_SELF_REV = re.compile(r"^\s*(.+?)是我\s*$")
    PATTERN_UNALIAS = re.compile(r"^\s*(?:取消别名|unalias)\s*$", re.IGNORECASE)
    PATTERN_AT_ASSIGN = re.compile(r"@(\S+?)\s*(?:为|是|改为|改成|=)\s*(\S+)")

    def __init__(self, memory: GameMemory):
        self.memory = memory
        self._op_name_to_id = _load_operator_table()

    # ============ 跟旧版兼容的查询 API ============

    def all(self) -> dict[str, int]:
        """返回 {昵称: 干员ID} 字典（兼容旧版）。"""
        result: dict[str, int] = {}
        for f in self.memory.find_facts(predicate="alias_to_op"):
            try:
                result[f.subject] = int(f.value)
            except (ValueError, TypeError):
                continue
        return result

    def lookup_by_nick(self, nickname: str) -> Optional[int]:
        """昵称 → 干员 ID。"""
        facts = self.memory.find_facts(subject=nickname, predicate="alias_to_op")
        if not facts:
            return None
        try:
            return int(facts[0].value)
        except (ValueError, TypeError):
            return None

    def lookup_by_op_id(self, op_id: int) -> Optional[str]:
        """干员 ID → 昵称（取第一条）。"""
        facts = self.memory.find_facts(predicate="alias_to_op", value=op_id)
        if not facts:
            return None
        return facts[0].subject

    # ============ 增删改 ============

    def set(self, nickname: str, op_id_or_name: str, source: str = "user") -> tuple[bool, str]:
        """注册/更新别名。返回 (是否成功, 反馈文案)。

        支持：op_id_or_name 是数字 ID / 已知干员名 / 已知昵称（复用其 op_id）
        """
        op_str = op_id_or_name.strip()
        op_id: Optional[int] = None

        # 1. 数字 ID
        if op_str.isdigit():
            op_id = int(op_str)
        # 2. 已知干员名
        elif op_str in self._op_name_to_id:
            op_id = self._op_name_to_id[op_str]
        else:
            # 3. 已注册的别名 key？（复用语义）
            existing = self.lookup_by_nick(op_str)
            if existing is not None:
                op_id = existing
            else:
                # 4. 模糊匹配干员名（容错打错）
                candidates = list(self._op_name_to_id.keys())
                close = difflib.get_close_matches(op_str, candidates, n=1, cutoff=0.5)
                if close:
                    op_id = self._op_name_to_id[close[0]]
                    op_str = close[0]

        if op_id is None:
            known = "、".join(sorted(self._op_name_to_id.keys())) or "（干员表为空）"
            return False, (
                f"不认识「{op_id_or_name}」这个干员。\n"
                f"已知：{known}\n"
                f"如果是新干员，可以直接发 ID（5位数）注册"
            )

        # 一个干员只能挂一个人（DF 同队禁同干员）—— 先解绑旧的
        existing_owners = self.memory.find_facts(predicate="alias_to_op", value=op_id)
        for f in existing_owners:
            if f.subject != nickname:
                self.memory.forget(f.fact_id)

        # 删除该昵称之前的 alias_to_op（如果有）
        self.memory.forget_where(subject=nickname, predicate="alias_to_op")
        # 写新的
        self.memory.remember(
            subject=nickname,
            predicate="alias_to_op",
            value=op_id,
            source=source,
        )
        # 记一笔 episode
        self.memory.add_episode(
            type="alias_change",
            content=f"{nickname} → 干员#{op_id}",
            actors=[nickname],
            metadata={"op_id": op_id, "source": source},
        )

        try:
            from df_stats.maps import OPERATOR_NAMES
            op_name = OPERATOR_NAMES.get(op_id, f"干员#{op_id}")
        except Exception:
            op_name = f"干员#{op_id}"
        return True, f"✅ 记下了：{nickname} = {op_name}（ID {op_id}）"

    def unset(self, nickname: str) -> tuple[bool, str]:
        removed = self.memory.forget_where(subject=nickname, predicate="alias_to_op")
        if removed == 0:
            return False, f"{nickname} 还没绑过别名"
        self.memory.add_episode(
            type="alias_change",
            content=f"删除 {nickname} 的 alias",
            actors=[nickname],
        )
        return True, f"✅ 已解绑：{nickname}"

    # ============ 句式解析（跟旧版完全一致）============

    def try_parse(
        self,
        source_nickname: str,
        message: str,
        at_qq_list: Optional[list[int]] = None,
    ) -> Optional[str]:
        """从群消息里识别学习/注销指令。"""
        m = self.PATTERN_ALIAS.match(message)
        if m:
            target_nick, op_str = m.group(1), m.group(2)
            ok, msg = self.set(target_nick, op_str, source=f"user:{source_nickname}")
            return msg

        m = self.PATTERN_UNALIAS.match(message)
        if m:
            ok, msg = self.unset(source_nickname)
            return msg

        m = self.PATTERN_AT_ASSIGN.search(message)
        if m:
            target_nick, op_str = m.group(1), m.group(2)
            ok, msg = self.set(target_nick, op_str, source=f"user:{source_nickname}")
            return msg

        m = self.PATTERN_SELF.match(message) or self.PATTERN_SELF_REV.match(message)
        if m:
            op_str = m.group(1).strip()
            if op_str in self._op_name_to_id or op_str.isdigit():
                ok, msg = self.set(source_nickname, op_str, source=f"user:{source_nickname}")
                return msg

        return None
