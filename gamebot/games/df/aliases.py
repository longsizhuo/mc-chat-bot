"""干员别名映射 —— 把 ArmedForceId 映射成群友昵称。

存储：data/df_aliases.json
格式：{"<nickname>": <ArmedForceId>, ...}
     注：一个干员只能挂一个群友，反之亦然（DF 同队不能选同干员，所以不冲突）

群里发以下任意句式 bot 自动学习：
  - "我玩牧羊人"
  - "牧羊人是我"
  - "alias 老王 牧羊人"
  - "/df alias 老王 30008"
"""

from __future__ import annotations

import difflib
import json
import re
import threading
from pathlib import Path
from typing import Optional

import sys
_DF_STATS_DIR = Path(__file__).resolve().parents[3] / "scripts" / "df_stats"
if str(_DF_STATS_DIR) not in sys.path:
    sys.path.insert(0, str(_DF_STATS_DIR))


def _load_operator_table() -> dict[str, int]:
    """从 df_stats.maps 加载中文名 → ArmedForceId 反向表。"""
    try:
        from df_stats.maps import OPERATOR_NAMES
        return {name: oid for oid, name in OPERATOR_NAMES.items()}
    except Exception:
        return {}


class DFAliases:
    """干员别名管理器。"""

    # 学习句式正则。命中后从分组里抠出昵称和干员名/ID
    # 1. "alias 老王 牧羊人" / "alias 老王 30008"
    PATTERN_ALIAS = re.compile(r"^\s*alias\s+(\S+)\s+(\S+)\s*$", re.IGNORECASE)
    # 2. "我玩XX" / "我是XX" / "我打XX"
    PATTERN_SELF = re.compile(r"^\s*我(?:玩|是|打|用|主)(.+?)\s*$")
    # 3. "XX是我"
    PATTERN_SELF_REV = re.compile(r"^\s*(.+?)是我\s*$")
    # 4. 解除：取消别名 / unalias
    PATTERN_UNALIAS = re.compile(r"^\s*(?:取消别名|unalias)\s*$", re.IGNORECASE)

    def __init__(self, store_path: str | Path):
        self.store_path = Path(store_path)
        self._lock = threading.Lock()
        self._aliases: dict[str, int] = {}  # nickname → ArmedForceId
        self._op_name_to_id = _load_operator_table()
        self._load()

    def _load(self):
        if not self.store_path.exists():
            return
        try:
            data = json.loads(self.store_path.read_text(encoding="utf-8"))
            self._aliases = {k: int(v) for k, v in data.items()}
        except (json.JSONDecodeError, OSError, ValueError) as e:
            print(f"[DFAliases] 加载失败，从空开始：{e}")
            self._aliases = {}

    def _save(self):
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self.store_path.write_text(
            json.dumps(self._aliases, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ---- 查询 ----

    def lookup_by_op_id(self, op_id: int) -> Optional[str]:
        """ArmedForceId → 群友昵称。"""
        with self._lock:
            for nick, oid in self._aliases.items():
                if oid == op_id:
                    return nick
        return None

    def lookup_by_nick(self, nickname: str) -> Optional[int]:
        """群友昵称 → ArmedForceId。"""
        with self._lock:
            return self._aliases.get(nickname)

    def all(self) -> dict[str, int]:
        with self._lock:
            return dict(self._aliases)

    # ---- 学习 / 注销 ----

    def set(self, nickname: str, op_id_or_name: str) -> tuple[bool, str]:
        """记录别名。返回 (是否成功, 反馈文案)。

        模糊匹配：如果"骇爪"打成"害爪"或"牧羊人"打成"牧羊"，自动找最近的干员名。
        """
        op_id: Optional[int] = None
        op_str = op_id_or_name.strip()

        if op_str.isdigit():
            op_id = int(op_str)
        elif op_str in self._op_name_to_id:
            # 精确匹配
            op_id = self._op_name_to_id[op_str]
        else:
            # 模糊匹配：找相似度最高的干员名
            candidates = list(self._op_name_to_id.keys())
            close = difflib.get_close_matches(op_str, candidates, n=1, cutoff=0.5)
            if close:
                op_id = self._op_name_to_id[close[0]]
                # 即使匹配到了，反馈里告诉用户实际是哪个
                op_str = close[0]

        if op_id is None:
            known = "、".join(sorted(self._op_name_to_id.keys())) or "（干员表为空）"
            return False, (
                f"不认识「{op_id_or_name}」这个干员。\n"
                f"已知：{known}\n"
                f"如果是新干员，可以直接发 ID（5位数）注册"
            )

        # 一个干员只能挂一个人 —— 如果其他人已经绑了同一干员，先解绑
        with self._lock:
            for existing_nick, existing_oid in list(self._aliases.items()):
                if existing_oid == op_id and existing_nick != nickname:
                    del self._aliases[existing_nick]
            self._aliases[nickname] = op_id
            self._save()

        op_name = next(
            (n for n, i in self._op_name_to_id.items() if i == op_id),
            f"干员#{op_id}",
        )
        return True, f"✅ 记下了：{nickname} = {op_name}（ID {op_id}）"

    def unset(self, nickname: str) -> tuple[bool, str]:
        with self._lock:
            if nickname not in self._aliases:
                return False, f"{nickname} 还没绑过别名"
            del self._aliases[nickname]
            self._save()
        return True, f"✅ 已解绑：{nickname}"

    # ---- 句式解析 ----

    def try_parse(self, source_nickname: str, message: str) -> Optional[str]:
        """从群消息里识别学习/注销指令。

        识别成功返回反馈文案；未命中返回 None。
        source_nickname: 谁发的这条消息（用作别名）
        """
        m = self.PATTERN_ALIAS.match(message)
        if m:
            target_nick, op_str = m.group(1), m.group(2)
            ok, msg = self.set(target_nick, op_str)
            return msg

        m = self.PATTERN_UNALIAS.match(message)
        if m:
            ok, msg = self.unset(source_nickname)
            return msg

        m = self.PATTERN_SELF.match(message) or self.PATTERN_SELF_REV.match(message)
        if m:
            op_str = m.group(1).strip()
            # 句式简单，避免 "我打牌" 这种误识别 —— 干员名必须在已知表里
            if op_str in self._op_name_to_id or op_str.isdigit():
                ok, msg = self.set(source_nickname, op_str)
                return msg

        return None
