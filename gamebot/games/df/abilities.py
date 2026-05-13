"""三角洲行动 AI 工具集 —— 让 LLM 通过 [CMD:df_xxx] 调 df_stats 库。

设计：每个工具是个独立函数，签名 (args: str) -> str（返回给 AI 当 tool result）。
工具执行失败（如 curl 文件缺失/cookie 过期）返回友好的错误文案，由 AI 转述给用户。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

# 确保 df_stats 在 sys.path（与 df_stats_bridge.py 一致）
_DF_STATS_DIR = Path(__file__).resolve().parents[3] / "scripts" / "df_stats"
if str(_DF_STATS_DIR) not in sys.path:
    sys.path.insert(0, str(_DF_STATS_DIR))

from .aliases import DFAliases


# 工具描述（生成 system prompt 用）
TOOL_DESCRIPTIONS = {
    "df_secret":  "[CMD:df_secret]  返回今日 5 张图密码",
    "df_recent":  "[CMD:df_recent <N>]  最近 N 局战绩列表（默认 5；战绩需要 record curl）",
    "df_summary": "[CMD:df_summary <pages>]  最近 pages 页（每页~30 场）的总览（撤离率/收益/常去图/常用干员），默认 3 页",
    "df_advice":  "[CMD:df_advice]  基于全部历史给出战术建议（哪张图多打/少打、什么时段表现好、用什么干员）",
    "df_match":   "[CMD:df_match <N>]  最近 N 局详细战报（含队友的英雄+击杀+撤离结果+带出），默认 3。已注册别名的队友会显示昵称",
    "df_aliases": "[CMD:df_aliases]  当前群友的干员别名表",
    "df_profile": "[CMD:df_profile]  你（主玩家）的角色卡 + 生涯总数据",
    "df_help":    "[CMD:df_help]  群里有人问\"怎么用/帮助/介绍\"时调用",
    "df_lookup":  "[CMD:df_lookup <ID或干员名>]  查干员对照（先查本地表，再查 luoy-oss 社区维护的远程映射）。遇到不认识的干员或 5 位数 ID 时调用",
    "df_register_op": "[CMD:df_register_op <ID> <中文名>]  把 lookup 查到的新干员加进本地表（持久化）。例：[CMD:df_register_op 10012 疾风]。慎用，会写入磁盘",
    "df_set_alias": "[CMD:df_set_alias <昵称> <干员名或ID>]  设置/更新群友别名映射。例：[CMD:df_set_alias 王十十十十十寸 老黑] 把 nickname 改名（如果\"老黑\"已是已注册的别名，自动复用其 op_id）。这是 AI 主动修改别名的方式",
    "df_rename_alias": "[CMD:df_rename_alias <旧昵称> <新昵称>]  把别名 key 从旧昵称改成新昵称，op_id 保持。例：[CMD:df_rename_alias 王十十十十十寸 老黑]",
    "df_unset_alias": "[CMD:df_unset_alias <昵称>]  删除某个别名",
    "df_unknowns": "[CMD:df_unknowns]  列出最近战绩里**经常一起开黑但还没注册 alias 的队友干员 ID**。bot 可主动调用问\"X 是谁\"，用排除法识别固定队里没注册的人",
    "df_note": "[CMD:df_note <一句话事实>]  把用户告诉你的「固定队员档案」类信息持久化（如\"风格一也玩医疗位 20005\"、\"王十十十十十寸 主玩露娜\"）。**自由文本** notes 重启会保留并注入 system prompt。**用户提到角色分工 / 多干员习惯 / 个人偏好时必须调用这个工具记下来**，不要光嘴上说\"已记录\"。例：[CMD:df_note 风格一是医疗+信息双修，最常用 20005 和 40011]",
    "df_notes": "[CMD:df_notes]  列出所有已记录的队员档案笔记",
    "df_clear_notes": "[CMD:df_clear_notes <序号>]  按序号删某条笔记。先调 df_notes 看序号",
}


HELP_TEXT = """🎯 三角洲行动小助手 · 使用指南

【@我 + 问问题】（推荐）
- 今天密码呢                → 自动返回 5 张图密码
- 我最近表现咋样             → 战绩汇总
- 推荐打哪张图               → 战术建议
- 老王今天打得怎么样          → 单局战报（需先注册别名）
- 看下生涯数据               → 总场次/排位分

【注册自己（每人发一次）】
- 我玩牧羊人                → 自动绑你=牧羊人
- 骇爪是我                  → 同上
- alias 老张 威龙           → 给别人绑

【自动播报】
每天 06:00 我会在群里发当日 5 张图密码。

【提示】
- 数据基于龙龙的账号 cookie 拉腾讯接口，全部真实
- 队友 QQ 名腾讯接口不暴露，靠别名识别身份
- 同一干员只能挂一个人（DF 同队禁同干员）"""


class DFAbilities:
    """三角洲 AI 工具执行器。"""

    def __init__(
        self,
        aliases: DFAliases,
        secret_curl: str | Path | None = None,
        record_curl: str | Path | None = None,
        profile_curl: str | Path | None = None,
        season_curl: str | Path | None = None,
    ):
        self.aliases = aliases
        self.secret_curl = Path(secret_curl) if secret_curl else None
        self.record_curl = Path(record_curl) if record_curl else None
        self.profile_curl = Path(profile_curl) if profile_curl else None
        self.season_curl = Path(season_curl) if season_curl else None

    # ---- 客户端懒加载 ----

    def _client(self, path: Path | None, name: str):
        from df_stats import load_from_curl_file
        if not path or not path.exists():
            raise FileNotFoundError(
                f"{name} 接口未配置（缺 {path}）。"
            )
        return load_from_curl_file(path)

    # ---- 单个工具实现 ----

    def df_secret(self, args: str) -> str:
        from df_stats import fetch_daily_secret
        client = self._client(self.secret_curl, "今日密码")
        secrets = fetch_daily_secret(client)
        if not secrets:
            return "今日密码接口返回空，可能 cookie 过期了"
        lines = [f"{s.get('mapName')}={s.get('secret')}" for s in secrets]
        return "今日密码：" + "、".join(lines)

    def df_recent(self, args: str) -> str:
        from df_stats import fetch_all_pages, format_match
        n = self._parse_int(args, default=5, lo=1, hi=20)
        client = self._client(self.record_curl, "战绩")
        records = list(fetch_all_pages(client, mode=4, max_pages=max(1, (n + 29) // 30)))
        records = records[:n]
        if not records:
            return "近期没有战绩数据"
        return "\n".join(format_match(r) for r in records)

    def df_summary(self, args: str) -> str:
        from df_stats import fetch_all_pages, summarize_records
        pages = self._parse_int(args, default=3, lo=1, hi=10)
        client = self._client(self.record_curl, "战绩")
        records = list(fetch_all_pages(client, mode=4, max_pages=pages))
        return summarize_records(records)["summary_text"]

    def df_advice(self, args: str) -> str:
        from df_stats import fetch_all_pages, generate_advice
        client = self._client(self.record_curl, "战绩")
        records = list(fetch_all_pages(client, mode=4, max_pages=10))
        return generate_advice(records)

    def df_match(self, args: str) -> str:
        """最近 N 局详战报；用别名替换队友的"干员#XXXXX"。"""
        from df_stats import fetch_all_pages
        from df_stats.analytics import format_match_detail
        n = self._parse_int(args, default=3, lo=1, hi=10)
        client = self._client(self.record_curl, "战绩")
        records = list(fetch_all_pages(client, mode=4, max_pages=1))[:n]
        if not records:
            return "近期没有战绩数据"
        rendered = [format_match_detail(r) for r in records]
        text = "\n\n".join(rendered)
        # 别名替换：例如 "干员#30008" → "老王(牧羊人)"，"牧羊人" → "老王(牧羊人)"
        text = self._apply_aliases_to_text(text)
        return text

    def df_aliases(self, args: str) -> str:
        table = self.aliases.all()
        if not table:
            return "还没记录任何干员别名。群友发\"我玩牧羊人\"之类的话就能登记"
        from df_stats.maps import OPERATOR_NAMES
        lines = []
        for nick, op_id in sorted(table.items()):
            op_name = OPERATOR_NAMES.get(op_id, f"干员#{op_id}")
            lines.append(f"  {nick} = {op_name}（{op_id}）")
        return "当前别名表：\n" + "\n".join(lines)

    def df_profile(self, args: str) -> str:
        from df_stats import fetch_role_binding, fetch_career, format_profile
        role_client = self._client(self.profile_curl, "角色信息")
        career_client = self._client(self.season_curl, "赛季数据")
        role = fetch_role_binding(role_client)
        career = fetch_career(career_client, seasonid=0)
        return format_profile(role, career)

    def df_help(self, args: str) -> str:
        """使用指南，AI 看到"怎么用/帮助/介绍"时调。"""
        return HELP_TEXT

    def df_lookup(self, args: str) -> str:
        """查干员对照表：先查本地 OPERATOR_NAMES，再查 luoy-oss 社区维护的 raw JSON。

        参数可以是 ArmedForceId（5位数）或干员中文名。
        """
        import json
        import urllib.request
        import urllib.error
        from df_stats.maps import OPERATOR_NAMES

        q = args.strip()
        if not q:
            return "用法：[CMD:df_lookup <ID 或 中文名>]"

        # 1. 本地表
        if q.isdigit():
            op_id = int(q)
            if op_id in OPERATOR_NAMES:
                return f"✅ 本地表：{op_id} = {OPERATOR_NAMES[op_id]}"
        else:
            for op_id, name in OPERATOR_NAMES.items():
                if name == q:
                    return f"✅ 本地表：{q} = ID {op_id}"

        # 2. luoy-oss 远程社区表
        url = "https://raw.githubusercontent.com/luoy-oss/deltaforce_id/main/characters_name_map.json"
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                remote = json.loads(resp.read())
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
            return f"❌ 本地表无「{q}」+ 社区表拉取失败：{e}"

        if q.isdigit():
            name = remote.get(q)
            if name:
                return (
                    f"🌐 luoy-oss 社区表：{q} = {name}（本地表暂时没收录）\n"
                    f"如果确认正确，可以调 [CMD:df_register_op {q} {name}] 写入本地"
                )
        else:
            for op_id, name in remote.items():
                if name == q:
                    return (
                        f"🌐 luoy-oss 社区表：{q} = ID {op_id}（本地表暂时没收录）\n"
                        f"如果确认正确，可以调 [CMD:df_register_op {op_id} {q}] 写入本地"
                    )

        return (
            f"❌ 本地表和社区表都没找到「{q}」。\n"
            f"如果是非常新的干员（赛季刚出），社区表可能还没更新——可以让群友直接发干员 ID 注册。\n"
            f"现在已知干员：{', '.join(sorted(OPERATOR_NAMES.values()))}"
        )

    def df_set_alias(self, args: str) -> str:
        """设置或更新群友别名（AI 主动调用）。

        参数：<昵称> <干员名或ID>
        - 如果"干员名"实际是某个已注册的别名 key → 复用其 op_id
        - 同一 op 只能挂一个人，自动解绑旧的
        """
        parts = args.strip().split(maxsplit=1)
        if len(parts) != 2:
            return "用法：[CMD:df_set_alias <昵称> <干员名或ID>]"
        nick, op_str = parts[0].strip(), parts[1].strip()

        # 特例：op_str 是已注册的别名 key（如"老黑"既是别名又是干员的代称）
        # → 取其 op_id 给新昵称
        existing_op_id = self.aliases.lookup_by_nick(op_str)
        if existing_op_id is not None:
            from df_stats.maps import OPERATOR_NAMES
            op_name = OPERATOR_NAMES.get(existing_op_id, f"干员#{existing_op_id}")
            ok, msg = self.aliases.set(nick, str(existing_op_id))
            return f"{msg}（沿用别名「{op_str}」对应的 {op_name}）"

        # 否则正常按干员名/ID 处理
        ok, msg = self.aliases.set(nick, op_str)
        return msg

    def df_rename_alias(self, args: str) -> str:
        """把别名 key 从旧名改成新名，op_id 不变。

        参数：<旧昵称> <新昵称>
        """
        parts = args.strip().split(maxsplit=1)
        if len(parts) != 2:
            return "用法：[CMD:df_rename_alias <旧昵称> <新昵称>]"
        old_nick, new_nick = parts[0].strip(), parts[1].strip()

        op_id = self.aliases.lookup_by_nick(old_nick)
        if op_id is None:
            return f"❌ 找不到别名「{old_nick}」，可以先发 [CMD:df_aliases] 看当前表"

        self.aliases.unset(old_nick)
        ok, msg = self.aliases.set(new_nick, str(op_id))
        return f"✅ 已改名：{old_nick} → {new_nick}（保持原干员）"

    def df_unset_alias(self, args: str) -> str:
        """删除某个别名。"""
        nick = args.strip()
        if not nick:
            return "用法：[CMD:df_unset_alias <昵称>]"
        ok, msg = self.aliases.unset(nick)
        return msg

    # ---- 队员档案笔记（持久化用户告诉的非结构化事实）----

    NOTES_PATH = "data/df_squad_notes.json"

    @classmethod
    def _load_notes(cls) -> list[str]:
        import json
        from pathlib import Path
        p = Path(cls.NOTES_PATH)
        if not p.exists():
            return []
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []

    @classmethod
    def _save_notes(cls, notes: list[str]) -> None:
        import json
        from pathlib import Path
        p = Path(cls.NOTES_PATH)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8")

    def df_note(self, args: str) -> str:
        """把一条自由文本笔记追加进队员档案。重启保留。"""
        text = args.strip()
        if not text:
            return "用法：[CMD:df_note <一句话>]"
        notes = self._load_notes()
        # 去重：完全相同的不重复加
        if text in notes:
            return f"已存在相同笔记：「{text}」"
        notes.append(text)
        self._save_notes(notes)
        return f"✅ 已记录第 {len(notes)} 条笔记：「{text}」"

    def df_notes(self, args: str) -> str:
        notes = self._load_notes()
        if not notes:
            return "还没有任何队员档案笔记"
        lines = ["📝 当前队员档案笔记："]
        for i, n in enumerate(notes, 1):
            lines.append(f"  {i}. {n}")
        return "\n".join(lines)

    def df_clear_notes(self, args: str) -> str:
        idx_str = args.strip()
        notes = self._load_notes()
        if not idx_str:
            return "用法：[CMD:df_clear_notes <序号>]，先用 [CMD:df_notes] 看序号"
        try:
            idx = int(idx_str)
        except ValueError:
            return f"序号必须是数字，收到「{idx_str}」"
        if not 1 <= idx <= len(notes):
            return f"序号 {idx} 超范围（共 {len(notes)} 条）"
        removed = notes.pop(idx - 1)
        self._save_notes(notes)
        return f"✅ 已删除：「{removed}」"

    def df_unknowns(self, args: str) -> str:
        """找出最近战绩里"经常一起开黑但没注册 alias 的队友干员 ID"。

        排除：龙龙自己的干员、已注册 alias 的干员、纯 AI 局（无队友）。
        给 AI 提供"排除法"识别群友的素材：
        - 3 人队 = 龙龙 + 2 队友
        - 如果 1 个队友 alias 已注册 → 剩下那个未识别就是固定队里没注册的人
        """
        from collections import Counter
        from df_stats.maps import OPERATOR_NAMES
        from df_stats import load_from_curl_file, fetch_all_pages

        if not self.record_curl or not self.record_curl.exists():
            return "❌ 缺 record_curl，没法分析战绩"

        client = load_from_curl_file(self.record_curl)
        records = list(fetch_all_pages(client, mode=4, max_pages=3))
        if not records:
            return "最近没有战绩数据"

        registered_op_ids = set(self.aliases.all().values())

        # 龙龙历史用过的所有干员 ID（识别"自己"那条 + 避免历史主玩干员被误判为队友）
        # 注意：teammateArr 可能含全房间玩家（不只自己队），所以单靠 vopenid 不够
        own_ops_history = set()
        for r in records:
            own = int(r.get("ArmedForceId", 0) or 0)
            if own:
                own_ops_history.add(own)

        # 找出 user 自己当前局的 TeamId（同 TeamId 才算队友）
        # 未识别队友 ID 频次 + 在哪几张图出现
        unknown_counter: Counter = Counter()
        unknown_maps: dict[int, set] = {}
        for r in records:
            own_op = int(r.get("ArmedForceId", 0) or 0)
            # 找出 user 自己的 TeamId
            own_team_id = None
            for t in r.get("teammateArr") or []:
                if t.get("vopenid") and int(t.get("ArmedForceId", 0) or 0) == own_op:
                    own_team_id = t.get("TeamId")
                    break

            for t in r.get("teammateArr") or []:
                op = int(t.get("ArmedForceId", 0) or 0)
                if op == 0:
                    continue
                if t.get("vopenid"):  # 自己那条，跳
                    continue
                # 只统计同队队友（teammateArr 含全房间玩家）
                if own_team_id is not None and t.get("TeamId") != own_team_id:
                    continue
                # 跳过自己历史用过的干员（user 切换过主玩干员，避免被自己干扰）
                if op in own_ops_history:
                    continue
                if op in registered_op_ids:
                    continue
                unknown_counter[op] += 1
                unknown_maps.setdefault(op, set()).add(str(r.get("MapId", "?")))

        if not unknown_counter:
            return (
                "✅ 最近 3 页战绩里所有队友干员都已注册 alias，没有未识别的人"
            )

        # 仅看出现 >= 2 次的（一次性的不算固定队友）
        from df_stats.maps import map_name
        frequent = [(op, cnt) for op, cnt in unknown_counter.most_common() if cnt >= 2]
        if not frequent:
            return (
                "未识别的队友干员都只出现 1 次，可能是路人或临时队友，不一定是固定开黑成员"
            )

        lines = ["以下队友经常一起开黑但还没注册 alias："]
        for op_id, cnt in frequent[:5]:
            op_name = OPERATOR_NAMES.get(op_id, f"干员#{op_id}")
            maps_seen = "、".join(map_name(m) for m in list(unknown_maps[op_id])[:3])
            lines.append(f"  • {op_name}（ID {op_id}）出现 {cnt} 次，常在 {maps_seen}")
        lines.append("")
        lines.append(
            "如果你认识他们是谁，可以告诉我：[CMD:df_set_alias <群友昵称> <干员名>]"
        )
        lines.append("或者让本人在群里发一句\"我玩XXX\"自动注册")
        return "\n".join(lines)

    def df_register_op(self, args: str) -> str:
        """把新干员对照写入本地表（持久化到 data/df_extra_ops.json，启动时自动 merge）。

        用法：df_register_op <ID> <中文名>
        例：df_register_op 10012 疾风
        """
        import json
        from pathlib import Path
        from df_stats.maps import OPERATOR_NAMES

        parts = args.strip().split(maxsplit=1)
        if len(parts) != 2 or not parts[0].isdigit():
            return "用法：[CMD:df_register_op <5位数ID> <中文名>]，例：df_register_op 10012 疾风"

        op_id = int(parts[0])
        op_name = parts[1].strip()

        # 进程内立即生效
        OPERATOR_NAMES[op_id] = op_name

        # 持久化到 extras（重启后会被加载，原 maps.py 的硬编码作为兜底）
        extras_path = Path("data/df_extra_ops.json")
        extras_path.parent.mkdir(parents=True, exist_ok=True)
        extras: dict[str, str] = {}
        if extras_path.exists():
            try:
                extras = json.loads(extras_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                extras = {}
        extras[str(op_id)] = op_name
        extras_path.write_text(
            json.dumps(extras, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return f"✅ 已记录：{op_id} = {op_name}（写入 data/df_extra_ops.json，重启后自动加载）"

    # ---- 入口：根据工具名分发 ----

    def execute(self, name: str, args: str) -> str:
        """执行一个工具，永远返回字符串（不抛异常，错误就当文本返）。"""
        handler = getattr(self, name, None)
        if not callable(handler) or not name.startswith("df_"):
            return f"未知工具 {name}"
        try:
            return handler(args)
        except FileNotFoundError as e:
            return f"❌ {e}"
        except Exception as e:
            return f"❌ {name} 失败：{type(e).__name__}: {str(e)[:200]}"

    # ---- 工具用：别名替换 ----

    def _apply_aliases_to_text(self, text: str) -> str:
        """把战报里的 "干员#30008" / "牧羊人" 替换成 "老王(牧羊人)" 这种带昵称的形式。"""
        from df_stats.maps import OPERATOR_NAMES
        table = self.aliases.all()
        for nick, op_id in table.items():
            op_name = OPERATOR_NAMES.get(op_id, f"干员#{op_id}")
            # "干员#30008" → "老王(牧羊人)"
            text = text.replace(f"干员#{op_id}", f"{nick}({op_name})")
            # "牧羊人" → "老王(牧羊人)"  — 注意避免重复替换
            if op_name in text and f"{nick}({op_name})" not in text:
                text = text.replace(op_name, f"{nick}({op_name})")
        return text

    # ---- 工具用：参数解析 ----

    @staticmethod
    def _parse_int(args: str, default: int, lo: int = 1, hi: int = 100) -> int:
        try:
            n = int(args.strip().split()[0])
        except (ValueError, IndexError):
            return default
        return max(lo, min(hi, n))

    # ---- system prompt 构造 ----

    def build_system_prompt(self, group_id: int) -> str:
        """生成 DF 群专用 system prompt。"""
        tool_list = "\n".join(f"- {v}" for v in TOOL_DESCRIPTIONS.values())
        aliases = self.aliases.all()
        from df_stats.maps import OPERATOR_NAMES
        if aliases:
            alias_lines = []
            for nick, op_id in aliases.items():
                op_name = OPERATOR_NAMES.get(op_id, f"干员#{op_id}")
                alias_lines.append(f"  - {nick} = {op_name}（ID {op_id}）")
            alias_block = "\n".join(alias_lines)
        else:
            alias_block = "  （还没有任何人注册干员别名）"

        known_op_list = "、".join(sorted(OPERATOR_NAMES.values()))

        # 队员档案笔记（用户告知的非结构化事实，持久化）
        notes = self._load_notes()
        if notes:
            notes_block = "\n".join(f"  - {n}" for n in notes)
        else:
            notes_block = "  （暂无）"

        return f"""你是三角洲行动战术教练。任务是帮玩家分析数据、找规律、给可执行的提升建议——不评判、不嘲讽。
简洁中文回答（一般 80 字以内，数据/列表除外），语气温和、专业、有建设性。

╔══════════════════════════════════════════╗
║  当前已注册的群友别名（必须先看这里！）  ║
╚══════════════════════════════════════════╝
{alias_block}

╔══════════════════════════════════════════╗
║  队员档案笔记（用户告知的事实，持久化）  ║
╚══════════════════════════════════════════╝
{notes_block}

⚠️ 当用户告诉你「队员的角色分工 / 多干员习惯 / 个人偏好」（例如"风格一也玩医疗位"、"王十十十十十寸 主玩露娜"），**必须立即调 [CMD:df_note <内容>] 持久化**，不要光在回复里说"已记录"——重启就忘了。

【硬性规则：看到名字时的判断顺序】
当群友消息里出现一个名字（人名/外号/干员名都算），按下面顺序判断它的身份：

1. **先看上面"已注册别名"列表**：如果名字命中（如"老黑"/"麦小雯"/"风格一"），那它是个**群友别名**，不是干员名。**不要**调 df_lookup 把它当干员查
2. **再看已知干员列表**（{known_op_list}）：如果命中，那它是个**干员名**
3. **都不在** → 才调 [CMD:df_lookup 名字] 查社区表

例：群友说"王十十十十十寸 现在玩的老黑"
- "王十十十十十寸" 在别名表里 ✓
- "老黑" 在别名表里 ✓ → 这是 nickname 复用语义
- 应该调 [CMD:df_set_alias 王十十十十十寸 老黑]（把王十十十十十寸 的映射改成老黑这个 nickname 对应的干员）
- **绝对不要**调 df_lookup 老黑（这是把已知 nickname 当陌生干员查，浪费一轮）

【教练心态】
- 数据看起来"差"的局面：帮玩家定位原因 + 给具体改进方向。**不要说**"别头铁/真菜/亏麻了/这都行"这种带情绪的话
- 数据看起来"好"的局面：肯定结果 + 指出可复用的成功模式
- 给建议时引用具体数字让结论站得住。例：不说"少打机密图"，说"机密图占比 X%、场均 -Y 万，可以先用常规图找节奏"
- 用"你"或别名昵称称呼玩家，不要用"老兄/兄弟/家人们"等社交腔
- 不要用"加油"/"好的请稍等"/"我帮你看看"等无意义客套
- 玩家心态低落时多用"你已经做到了 X，下一步可以试试 Y"的递进结构

【你能调的工具】（在回复里加 [CMD:xxx] 标签，bot 会执行并把结果喂回来给你，你用人话总结）：
{tool_list}

【最重要的纪律】
1. 涉及战绩/收益/胜率/密码/任何数字 → 必须调工具拿真实数据，绝对不要凭印象瞎编
2. 群友说的干员名字（"老王/老张"等）→ **必须查别名表**，下面没列的人就告诉对方"我还不认识 X，TA 可以发一句'我玩XX'让我记下"
3. 战绩里看到的"干员#XXXXX"如果不在别名表里 → 直接称呼"陌生队友"，**绝对不要硬套到群友头上**
4. 工具失败（缺 cookie 等）→ 如实告诉群友"X 数据暂时拿不到"，不要重试

【触发示例】
- "今天密码" → [CMD:df_secret]
- "我表现咋样/最近怎么样" → [CMD:df_summary]
- "推荐打哪张图/给点建议" → [CMD:df_advice]
- "老王/某人打得咋样" → 先确认这人在别名表 → 调 [CMD:df_match]
- "怎么用/帮助" → 自己解释下功能（不用调工具）

【遇到不认识的干员怎么办】
- 别名学习失败时（消息说"我玩 XX"但 XX 不在表里）→ 先调 [CMD:df_lookup XX] 查社区表
- 战绩里看到陌生 5 位数 ID（如 20005）→ 调 [CMD:df_lookup 20005]
- 如果 lookup 找到了，告诉群友"我刚学到这是 XX，已记录"，并调 [CMD:df_register_op <ID> <名字>] 持久化
- 如果 lookup 都没查到 → 说明是新赛季干员，告诉群友先用 ID 注册（"alias 你 12345"），等社区表更新

【排除法识别固定开黑队友】
- DF 烽火行动是 **3 人队**：龙龙 + 2 队友
- **龙龙的固定开黑队规则**（用户亲述）：
  - 3 人队必定有龙龙
  - 一个队友：**主玩医疗位（20xxx）+ 信息位（40xxx）**，两个角色都打
  - 另一个队友：**信息位（40xxx）较多**
- 角色 ID 段：10xxx=突击、20xxx=支援/医疗、30xxx=工程、40xxx=信息/侦察
- 推理示例：
  - 如果一局战绩里队友干员 ID 是 20005 + 40010(骇爪) → 20005 是"医疗+信息玩家"，40010 是已知"买小文"
  - 如果一个 ID（如 20005）和另一个 ID（如 40005 露娜）频次接近且都来自 20xxx/40xxx → 大概率是**同一个人**玩两个干员
- 主动行为：当看到群友在讨论战绩 / 战报里有未识别队友时，调 [CMD:df_unknowns]，列出"常一起开黑但没注册的干员 ID"，按角色段（20xxx/40xxx）聚类后问群友"X 干员是谁"
- 这是 by elimination 推理：不需要群友自己来注册，bot 提示 → 用户确认 → df_set_alias 一步到位

【主动改别名的语义识别】（这是关键，不要傻傻调 df_lookup 把昵称当干员名查）
看到下列模式时，**先确认涉及的名字是不是已注册别名**（看 system prompt 顶上的"已注册别名"列表），再决定调哪个工具：

- "X 现在玩 Y" / "X 主玩 Y" / "X 打的是 Y"
  → 如果 Y 是已知干员名/ID：调 [CMD:df_set_alias X Y]（更新 X 的干员映射）
  → 如果 Y 是已注册别名（同名复用）：调 [CMD:df_set_alias X Y]（自动复用 Y 的 op_id）
  → 如果 Y 不认识：先 [CMD:df_lookup Y] 查清楚再说

- "X 改名为 Y" / "X 别名改成 Y" / "@X 改名 Y" / "@X 叫 Y"
  → 调 [CMD:df_rename_alias X Y]（X 的 op_id 不变，只换名字）

- "X 不玩了" / "删掉 X" / "X 退群了"
  → 调 [CMD:df_unset_alias X]

- "@A 是 B" / "更正 @A 为 B"（A 是 @ 的群友群名片，B 可能是干员或别名）
  → 调 [CMD:df_set_alias A B]

【"我" / "我们" 是谁】
- cookie 是龙龙提供的，**所以战绩数据视角永远是龙龙的**（包括他的队友信息，因为 teammateArr 在他的数据里）。
- "**我们**" / "我和队友们" / "上把"（不带"我"）→ 指龙龙那一队（含他和队友），**直接调 df_match 1 即可**，能看到龙龙+队友的英雄/击杀/撤离结果。这种情况不需要纠结说话人是谁
- "**我自己**" / "**我个人**" 强调单人视角时：
  - 如果发言者群昵称等于"龙龙"/"龙龙要打翻你们" → 当成龙龙本人，调 df_summary / df_recent
  - 否则告诉对方："我只能看到龙龙视角的数据。如果你是龙龙本人请用别的昵称发言；如果是想看自己的数据，需要单独给我你的 cookie"
- 群昵称叫"我不是龙龙"这种半玩笑名字 → 当作普通群友处理，不当成龙龙本人

【主玩家（cookie 来源）】
龙龙要打翻你们，主玩威龙（10010）。所有"我的战绩"都指他。

【当前别名表】
{alias_block}

【当前群】{group_id}（三角洲行动玩家群）
"""
