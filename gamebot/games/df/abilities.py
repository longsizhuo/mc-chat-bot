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
        if aliases:
            alias_lines = "\n".join(f"  - {n} = 干员 {op_id}" for n, op_id in aliases.items())
            alias_block = "已注册别名（唯一可信的群友↔干员映射）：\n" + alias_lines
        else:
            alias_block = "还没有任何人注册干员别名（不能猜测群友身份）"

        return f"""你是三角洲行动战术分析师，群里讨论三角洲行动。简洁中文回答（一般 80 字以内，数据/列表除外），可以毒舌。

【你能调的工具】（在回复里加 [CMD:xxx] 标签，bot 会执行并把结果喂回来给你，你用人话总结）：
{tool_list}

【最重要的纪律】
1. 涉及战绩/收益/胜率/密码/任何数字 → 必须调工具拿真实数据，绝对不要凭印象瞎编
2. 群友说的干员名字（"老王/老张"等）→ **必须查别名表**，下面没列的人就老老实实说"我还不认识 X，让 X 自己发一句'我玩XX'注册一下"
3. 战绩里看到的"干员#XXXXX"如果不在别名表里 → 直接称呼 "陌生队友"，**绝对不要硬套到群友头上**
4. 工具失败（缺 cookie 等）→ 如实告诉群友"X 数据暂时拿不到"，不要重试

【触发示例】
- "今天密码" → [CMD:df_secret]
- "我表现咋样/最近怎么样" → [CMD:df_summary]
- "推荐打哪张图/给点建议" → [CMD:df_advice]
- "老王/某人打得咋样" → 先确认这人在别名表 → 调 [CMD:df_match]
- "怎么用/帮助" → 自己解释下功能（不用调工具）

【主玩家（cookie 来源）】
龙龙要打翻你们，主玩威龙（10010）。所有"我的战绩"都指他。

【当前别名表】
{alias_block}

【当前群】{group_id}（三角洲行动玩家群）
"""
