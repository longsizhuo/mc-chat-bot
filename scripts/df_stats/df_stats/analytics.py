"""战绩深度分析：多维度透视 / 高光低谷 / 队友分析 / 单局详报 / 建议。

设计原则：每个函数接收 records: list[dict] 直接干活，不重复请求接口。
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Callable, Iterable

from .maps import map_name, operator_name, escape_reason_name
from .parsers import _as_int, format_match


# ---- 通用工具 ----

def _is_success(rec: dict) -> bool:
    """是否撤离成功。"""
    return _as_int(rec.get("EscapeFailReason")) == 1


def _gain(rec: dict) -> int:
    """单场净收益。"""
    return _as_int(rec.get("flowCalGainedPrice"))


def _kills(rec: dict) -> int:
    """击败干员数（不含纯 AI）。"""
    return _as_int(rec.get("KillCount"))


# ---- breakdown：按维度拆分 ----

def breakdown_by(
    records: Iterable[dict],
    key_func: Callable[[dict], str],
    label_func: Callable[[str], str] = lambda x: x,
    min_count: int = 1,
) -> list[dict]:
    """按 key_func 分组，每组算胜率/平均收益/平均击杀。

    返回按 count 倒序排列的 list[dict]，每个 dict 含：
        key, label, count, success, success_rate, avg_gain, total_gain, avg_kill
    """
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        k = key_func(r)
        if k:
            groups[k].append(r)

    rows = []
    for k, group in groups.items():
        n = len(group)
        if n < min_count:
            continue
        success = sum(1 for r in group if _is_success(r))
        total_gain = sum(_gain(r) for r in group)
        total_kill = sum(_kills(r) for r in group)
        rows.append({
            "key": k,
            "label": label_func(k),
            "count": n,
            "success": success,
            "success_rate": success / n * 100,
            "avg_gain": total_gain / n,
            "total_gain": total_gain,
            "avg_kill": total_kill / n,
        })

    rows.sort(key=lambda x: x["count"], reverse=True)
    return rows


def format_breakdown_table(rows: list[dict], title: str) -> str:
    """把 breakdown_by 的输出渲染成对齐表格。"""
    if not rows:
        return f"=== {title} ===\n（没有数据）"

    lines = [f"=== {title} ==="]
    # 表头
    lines.append(
        f"{'名称':<18} {'场次':>5} {'胜率':>6} {'场均收益':>11} {'总收益':>13} {'场均K':>5}"
    )
    lines.append("─" * 70)
    for row in rows:
        # 中文宽字符对齐：粗略按 2 字符宽度估算
        label = row["label"]
        # 计算需要 padding 的视觉宽度（中文按 2，其他按 1）
        visual_width = sum(2 if ord(c) > 127 else 1 for c in label)
        pad = max(0, 18 - visual_width)
        lines.append(
            f"{label}{' ' * pad} "
            f"{row['count']:>5} "
            f"{row['success_rate']:>5.0f}% "
            f"{row['avg_gain']:>+11,.0f} "
            f"{row['total_gain']:>+13,} "
            f"{row['avg_kill']:>5.1f}"
        )
    return "\n".join(lines)


def breakdown_by_map(records: list[dict], min_count: int = 1) -> str:
    rows = breakdown_by(
        records,
        key_func=lambda r: str(r.get("MapId", "")),
        label_func=map_name,
        min_count=min_count,
    )
    return format_breakdown_table(rows, f"🗺️ 按地图拆分（{len(records)} 场）")


def breakdown_by_operator(records: list[dict], min_count: int = 1) -> str:
    rows = breakdown_by(
        records,
        key_func=lambda r: str(_as_int(r.get("ArmedForceId"))),
        label_func=lambda k: operator_name(int(k)) if k.isdigit() else k,
        min_count=min_count,
    )
    return format_breakdown_table(rows, f"🪖 按干员拆分（{len(records)} 场）")


def breakdown_by_hour(records: list[dict]) -> str:
    """按小时分组，看几点战绩最好。"""
    def hour_key(r):
        when = r.get("dtEventTime", "")
        # 格式 "2026-05-13 01:26:17"
        if len(when) >= 13:
            return when[11:13]  # 小时
        return ""

    rows = breakdown_by(
        records,
        key_func=hour_key,
        label_func=lambda h: f"{h}:00-{h}:59" if h else "未知时段",
        min_count=3,  # 少于 3 场的时段忽略
    )
    # 按小时正序展示更直观
    rows.sort(key=lambda x: x["key"])
    return format_breakdown_table(rows, f"🕐 按时段拆分（每段至少 3 场）")


# ---- highlights：高光与翻车 ----

def top_matches(records: list[dict], n: int = 5, ascending: bool = False) -> list[dict]:
    """按净收益排序取 TOP / BOTTOM N 局。

    ascending=False（默认）→ 最赚的几局
    ascending=True       → 最亏的几局
    """
    return sorted(records, key=_gain, reverse=not ascending)[:n]


def format_highlights(records: list[dict], n: int = 5) -> str:
    """高光 + 翻车一起出。"""
    if not records:
        return "（没有数据）"

    best = top_matches(records, n, ascending=False)
    worst = top_matches(records, n, ascending=True)

    lines = ["=== 🏆 最赚的 {} 局 ===".format(n)]
    for r in best:
        lines.append("  " + format_match(r))
    lines.append("")
    lines.append("=== 💸 最亏的 {} 局 ===".format(n))
    for r in worst:
        lines.append("  " + format_match(r))
    return "\n".join(lines)


# ---- teammates：队友分析 ----

def analyze_teammates(records: list[dict]) -> str:
    """统计队友使用情况，按"长期搭档"vs"临时路人"推断。

    判断逻辑：
    - teammateArr 里除自己外没人 → 单排
    - 否则 → 组队
    - 在所有组队场次中，某队友干员 ID 出现率 >= 20% → 判为"长期搭档"
    - 含长期搭档的组队场 → 开黑组队；否则 → 路人匹配
    （注：API 没暴露真实玩家 ID，只能用干员 ID 当代理，会有同好友换干员时误判）
    """
    solo = []
    teamed = []  # 所有组队场（先全收，下面再细分）
    teammate_op_counter: Counter = Counter()
    teammate_outcomes: dict[int, dict] = defaultdict(
        lambda: {"count": 0, "success": 0, "gain": 0}
    )

    for r in records:
        teammates = r.get("teammateArr") or []
        own_op_id = _as_int(r.get("ArmedForceId"))
        # 过滤掉"自己"那条（vopenid=True 且 op_id 一致）
        others = [
            t for t in teammates
            if not (t.get("vopenid") and _as_int(t.get("ArmedForceId")) == own_op_id)
        ]

        if not others:
            solo.append(r)
            continue

        teamed.append(r)
        for t in others:
            op = _as_int(t.get("ArmedForceId"))
            if op:
                teammate_op_counter[op] += 1
                bucket = teammate_outcomes[op]
                bucket["count"] += 1
                if _is_success(r):
                    bucket["success"] += 1
                bucket["gain"] += _gain(r)

    # 推断长期搭档：在组队场中出现率 >= 20% 的队友干员
    REGULAR_THRESHOLD = 0.20
    regular_ops: set[int] = set()
    if teamed:
        for op, cnt in teammate_op_counter.items():
            if cnt / len(teamed) >= REGULAR_THRESHOLD:
                regular_ops.add(op)

    # 再分一次：含长期搭档 → 开黑；不含 → 路人
    squad_with_regular = []
    queue_random = []
    for r in teamed:
        others_ops = {
            _as_int(t.get("ArmedForceId"))
            for t in (r.get("teammateArr") or [])
            if not (t.get("vopenid") and _as_int(t.get("ArmedForceId")) == _as_int(r.get("ArmedForceId")))
        }
        if others_ops & regular_ops:
            squad_with_regular.append(r)
        else:
            queue_random.append(r)

    def _stats(bucket: list[dict]) -> tuple[int, float, int]:
        n = len(bucket)
        if n == 0:
            return 0, 0.0, 0
        succ = sum(1 for r in bucket if _is_success(r))
        gain = sum(_gain(r) for r in bucket)
        return n, succ / n * 100, gain

    s_n, s_rate, s_gain = _stats(solo)
    q_n, q_rate, q_gain = _stats(queue_random)
    sq_n, sq_rate, sq_gain = _stats(squad_with_regular)

    lines = [f"=== 🤝 组队模式拆分（{len(records)} 场）==="]
    lines.append(
        f"  🧍 单排              {s_n:>4} 场  胜率 {s_rate:>4.0f}%  净收益 {s_gain:>+13,}"
    )
    lines.append(
        f"  🎙️ 开黑（含长期搭档）{sq_n:>4} 场  胜率 {sq_rate:>4.0f}%  净收益 {sq_gain:>+13,}"
    )
    lines.append(
        f"  👥 路人队            {q_n:>4} 场  胜率 {q_rate:>4.0f}%  净收益 {q_gain:>+13,}"
    )
    if regular_ops:
        labels = sorted(operator_name(op) for op in regular_ops)
        lines.append(f"  （长期搭档干员：{ '、'.join(labels) }）")

    if teammate_op_counter:
        lines.append("")
        lines.append("=== 常合作的队友干员 TOP 5 ===")
        lines.append(f"  {'干员':<12} {'同场':>5} {'胜率':>6} {'净收益':>13}")
        for op_id, _ in teammate_op_counter.most_common(5):
            b = teammate_outcomes[op_id]
            n = b["count"]
            rate = b["success"] / n * 100 if n else 0
            label = operator_name(op_id)
            visual_width = sum(2 if ord(c) > 127 else 1 for c in label)
            pad = max(0, 12 - visual_width)
            lines.append(
                f"  {label}{' ' * pad} "
                f"{n:>5} "
                f"{rate:>5.0f}% "
                f"{b['gain']:>+13,}"
            )

    return "\n".join(lines)


# ---- match：单局详细战报（自己 + 队友的 KD/英雄/收益）----

def _result_emoji(reason: int) -> str:
    if reason == 1:
        return "✅"
    elif reason in (2, 3):
        return "💀"
    else:
        return "❌"  # 其他 (7/9 撤离失败)


def format_match_detail(rec: dict) -> str:
    """单局完整战报：主玩家 + 全部队友的英雄/击杀/救助/带出/结果。"""
    map_id = rec.get("MapId", "?")
    duration = _as_int(rec.get("DurationS"))
    when = rec.get("dtEventTime", "")[:16]
    own_reason = _as_int(rec.get("EscapeFailReason"))
    own_gain = _gain(rec)

    minutes, seconds = divmod(duration, 60)
    header = (
        f"{when}  {map_name(map_id)}  {minutes:02d}'{seconds:02d}\"  "
        f"{_result_emoji(own_reason)}{escape_reason_name(own_reason)}  "
        f"我的净 {own_gain:+,}"
    )

    own_op = _as_int(rec.get("ArmedForceId"))
    team_rows = []
    own_added = False
    for t in rec.get("teammateArr") or []:
        op_id = _as_int(t.get("ArmedForceId"))
        is_self = bool(t.get("vopenid")) and op_id == own_op and not own_added
        if is_self:
            own_added = True
        team_rows.append({
            "is_self": is_self,
            "op_id": op_id,
            "op_label": operator_name(op_id),
            "reason": _as_int(t.get("EscapeFailReason")),
            "kill": _as_int(t.get("KillCount")),
            "kill_ai": _as_int(t.get("KillAICount")),
            "rescue": _as_int(t.get("Rescue")),
            "final_price": _as_int(t.get("FinalPrice")),
        })
    team_rows.sort(key=lambda x: (not x["is_self"], -x["final_price"]))

    lines = [header, "─" * 72]
    for row in team_rows:
        tag = "我  " if row["is_self"] else "队友"
        op_label = row["op_label"]
        visual_width = sum(2 if ord(c) > 127 else 1 for c in op_label)
        op_pad = max(0, 12 - visual_width)
        lines.append(
            f"  {tag}  {op_label}{' ' * op_pad}  "
            f"{_result_emoji(row['reason'])}  "
            f"K{row['kill']}+AI{row['kill_ai']}  "
            f"救{row['rescue']}  "
            f"带出 {row['final_price']:>10,}"
        )

    return "\n".join(lines)


def format_recent_matches_detail(records: list[dict], n: int = 5) -> str:
    """最近 N 局详细战报，每局一段。"""
    if not records:
        return "（没有数据）"
    return "\n\n".join(format_match_detail(r) for r in records[:n])


# ---- advice：自动生成战术建议 ----

def generate_advice(records: list[dict]) -> str:
    """基于历史数据自动生成可执行的战术建议。"""
    if not records:
        return "（数据不足）"

    n = len(records)
    overall_gain = sum(_gain(r) for r in records)
    overall_success = sum(1 for r in records if _is_success(r)) / n * 100

    lines = [f"💡 基于 {n} 场战绩的建议", "=" * 50]
    lines.append(
        f"📊 总览：{overall_success:.0f}% 撤离率，净收益 {overall_gain:+,}"
        f"（场均 {overall_gain/n:+,.0f}）"
    )
    if overall_gain < 0:
        lines.append("   ⚠️ 整体亏损，下面建议聚焦 \"止血\" 优先于 \"扩大优势\"")
    lines.append("")

    # 1. 地图建议
    map_rows = breakdown_by(
        records,
        key_func=lambda r: str(r.get("MapId", "")),
        label_func=map_name,
        min_count=3,
    )
    if map_rows:
        best_map = max(map_rows, key=lambda x: x["total_gain"])
        worst_map = min(map_rows, key=lambda x: x["total_gain"])
        lines.append("🗺️ 地图选择：")
        lines.append(
            f"   ✅ 多打 「{best_map['label']}」"
            f"（{best_map['count']} 场 / 胜率 {best_map['success_rate']:.0f}% / "
            f"场均 {best_map['avg_gain']:+,.0f}）"
        )
        if worst_map["total_gain"] < 0 and worst_map["key"] != best_map["key"]:
            lines.append(
                f"   ❌ 少打 「{worst_map['label']}」"
                f"（{worst_map['count']} 场 / 胜率 {worst_map['success_rate']:.0f}% / "
                f"场均 {worst_map['avg_gain']:+,.0f}）"
            )
        most_played = max(map_rows, key=lambda x: x["count"])
        if most_played["total_gain"] < 0 and most_played["key"] != worst_map["key"]:
            lines.append(
                f"   ⚠️ 你最常去的「{most_played['label']}」其实在亏"
                f"（{most_played['count']} 场，总亏 {most_played['total_gain']:+,}）"
            )
        lines.append("")

    # 2. 时段建议
    def hour_key(r):
        when = r.get("dtEventTime", "")
        return when[11:13] if len(when) >= 13 else ""

    hour_rows = breakdown_by(records, key_func=hour_key, min_count=5)
    if hour_rows:
        good_hours = [r for r in hour_rows if r["success_rate"] >= 55 and r["avg_gain"] > 0]
        bad_hours = [r for r in hour_rows if r["success_rate"] <= 30 or r["avg_gain"] < -500_000]
        lines.append("🕐 时段选择：")
        if good_hours:
            good_hours.sort(key=lambda x: -x["success_rate"])
            tag = "、".join(f"{r['key']}点(胜{r['success_rate']:.0f}%)" for r in good_hours[:3])
            lines.append(f"   ✅ 黄金时段：{tag}")
        if bad_hours:
            bad_hours.sort(key=lambda x: x["avg_gain"])
            tag = "、".join(f"{r['key']}点(场均{r['avg_gain']:+,.0f})" for r in bad_hours[:3])
            lines.append(f"   ❌ 死亡时段：{tag} —— 这几点真该早睡")
        lines.append("")

    # 3. 干员建议
    op_rows = breakdown_by(
        records,
        key_func=lambda r: str(_as_int(r.get("ArmedForceId"))),
        label_func=lambda k: operator_name(int(k)) if k.isdigit() else k,
        min_count=5,
    )
    if op_rows:
        op_rows_sorted = sorted(op_rows, key=lambda x: -x["avg_gain"])
        best_op = op_rows_sorted[0]
        lines.append("🪖 干员选择：")
        lines.append(
            f"   ✅ {best_op['label']} 是你的本命"
            f"（{best_op['count']} 场 / 胜率 {best_op['success_rate']:.0f}% / "
            f"场均 {best_op['avg_gain']:+,.0f}）"
        )
        worst_op = op_rows_sorted[-1]
        if worst_op["avg_gain"] < -200_000 and worst_op["key"] != best_op["key"]:
            lines.append(
                f"   ❌ 用 {worst_op['label']} 时千万小心"
                f"（{worst_op['count']} 场 / 胜率 {worst_op['success_rate']:.0f}% / "
                f"场均 {worst_op['avg_gain']:+,.0f}）"
            )
        lines.append("")

    # 4. 队友建议
    teammate_outcomes: dict[int, dict] = defaultdict(
        lambda: {"count": 0, "success": 0, "gain": 0}
    )
    for r in records:
        own_op_id = _as_int(r.get("ArmedForceId"))
        others = [
            t for t in (r.get("teammateArr") or [])
            if not (t.get("vopenid") and _as_int(t.get("ArmedForceId")) == own_op_id)
        ]
        for t in others:
            op = _as_int(t.get("ArmedForceId"))
            if op:
                b = teammate_outcomes[op]
                b["count"] += 1
                if _is_success(r):
                    b["success"] += 1
                b["gain"] += _gain(r)

    regulars = [(op, b) for op, b in teammate_outcomes.items() if b["count"] >= 10]
    if regulars:
        regulars.sort(key=lambda x: -x[1]["gain"])
        carry = regulars[0]
        drag = regulars[-1]
        lines.append("🤝 队友匹配：")
        lines.append(
            f"   ✅ 跟 {operator_name(carry[0])} 这位队友打稳赢"
            f"（{carry[1]['count']} 场 / 胜率 {carry[1]['success']/carry[1]['count']*100:.0f}% / "
            f"净 {carry[1]['gain']:+,}）"
        )
        if drag[1]["gain"] < -5_000_000 and drag[0] != carry[0]:
            lines.append(
                f"   ❌ 跟 {operator_name(drag[0])} 这位队友经常翻车"
                f"（{drag[1]['count']} 场 / 胜率 {drag[1]['success']/drag[1]['count']*100:.0f}% / "
                f"净 {drag[1]['gain']:+,}）"
            )
        lines.append("")

    # 5. 撤离失败警告
    fails = [r for r in records if _as_int(r.get("EscapeFailReason")) in (7, 9)]
    if fails:
        fail_loss = sum(_gain(r) for r in fails)
        if fail_loss < -5_000_000:
            lines.append("⚠️ 装备投机警告：")
            lines.append(
                f"   {len(fails)} 局撤离失败（断线/超时/异常）累计亏损 {fail_loss:+,}"
            )
            lines.append(
                f"   平均一局亏 {fail_loss/len(fails):+,.0f} —— "
                f"高级图带高价装备进去要量力，赔率太差"
            )

    return "\n".join(lines)
