"""个人概况 + 赛季历史的格式化输出。

数据源：
- 316964 (个人概况) → bindarea: 角色名、UID、区服
- 317814 (赛季数据，seasonid=0~9+) → userData + careerData
"""

from __future__ import annotations

from urllib.parse import unquote


def _decode_name(name: str) -> str:
    """三角洲的中文名是 URL 编码的，需要解码。"""
    try:
        return unquote(name or "")
    except Exception:
        return name or ""


def _int(v, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _fmt_duration(seconds: int) -> str:
    h, rem = divmod(seconds, 3600)
    m = rem // 60
    return f"{h}h{m:02d}m"


def _pic_url(picurl: str) -> str:
    """头像 ID → CDN URL（从 config.list.cdnFormat 推出来的模板）。"""
    if not picurl:
        return ""
    return f"https://playerhub.df.qq.com/playerhub/60004/object/p_{picurl}.png"


def format_profile(role: dict, career: dict) -> str:
    """个人主页：角色信息 + 生涯总数据。

    role:   fetch_role_binding 的返回
    career: fetch_career(seasonid=0) 的返回（生涯总和）
    """
    name = _decode_name(role.get("FroleName", ""))
    uid = role.get("Fuin", "?")
    area = role.get("Farea", "?")

    user_data = career.get("userData", {}) or {}
    cd = career.get("careerData", {}) or {}

    # 头像
    pic = _pic_url(user_data.get("picurl", ""))

    # 烽火生涯
    sol_total = _int(cd.get("soltotalfght"))
    sol_escape = _int(cd.get("solttotalescape"))
    sol_dur = _int(cd.get("solduration"))
    sol_kill = _int(cd.get("soltotalkill"))
    sol_price = _int(cd.get("totalprice"))
    sol_rank = cd.get("rankpoint", "?")
    sol_escape_ratio = cd.get("solescaperatio", "?")
    sol_kpm = cd.get("avgkillperminute", "?")
    non_asset = _int(cd.get("noncurrentasset"))

    # 全面战场
    tdm_total = _int(cd.get("tdmtotalfight"))
    tdm_win = _int(cd.get("totalwin"))
    tdm_kill = _int(cd.get("tdmtotalkill"))
    tdm_rank = cd.get("tdmrankpoint", "?")
    tdm_dur = _int(cd.get("tdmduration"))
    tdm_ratio = cd.get("tdmsuccessratio", "?")

    lines = [
        "═" * 60,
        f"  🎮 {name}（UID {uid}，区服 {area}）",
        f"  🖼️ {pic}" if pic else "",
        "═" * 60,
        "",
        "🔥 烽火行动 · 生涯",
        f"  总场次：{sol_total:,}    撤离成功：{sol_escape:,}（{sol_escape_ratio}）",
        f"  累计击杀：{sol_kill:,}    场均击杀/分钟：{int(sol_kpm)/100 if str(sol_kpm).isdigit() else sol_kpm}",
        f"  累计带出：{sol_price:,}    固定资产：{non_asset:,}",
        f"  累计时长：{_fmt_duration(sol_dur)}    排位分：{sol_rank}",
        "",
        "⚔️ 全面战场 · 生涯",
        f"  总场次：{tdm_total}    胜利：{tdm_win}（{tdm_ratio}）",
        f"  累计击杀：{tdm_kill}    累计时长：{_fmt_duration(tdm_dur)}",
        f"  排位分：{tdm_rank}",
    ]
    return "\n".join(l for l in lines if l is not None)


def format_seasons(seasons: list[dict]) -> str:
    """所有赛季横向对比。

    seasons: fetch_all_seasons 返回的列表，每项含 seasonid + userData + careerData
    """
    if not seasons:
        return "（没有赛季数据）"

    lines = ["═" * 80]
    lines.append("📅 烽火行动 · 赛季对比")
    lines.append("═" * 80)
    lines.append(
        f"  {'赛季':>4}  {'场次':>5}  {'撤离':>5}  {'撤离率':>6}  "
        f"{'击杀':>5}  {'时长':>7}  备注"
    )
    lines.append("─" * 80)

    # 找撤离率最高/最低的赛季（不含 seasonid=0 生涯总和）
    per_season = [s for s in seasons if s["seasonid"] != 0]
    best_escape = max(per_season, key=lambda s: _parse_pct(s.get("careerData", {}).get("solescaperatio", "0%"))) if per_season else None
    worst_escape = min(per_season, key=lambda s: _parse_pct(s.get("careerData", {}).get("solescaperatio", "0%"))) if per_season else None

    for s in seasons:
        sid = s["seasonid"]
        cd = s.get("careerData", {}) or {}
        label_sid = "生涯" if sid == 0 else f"S{sid}"
        n = _int(cd.get("soltotalfght"))
        esc = _int(cd.get("solttotalescape"))
        ratio = cd.get("solescaperatio", "?")
        kills = _int(cd.get("soltotalkill"))
        dur = _fmt_duration(_int(cd.get("solduration")))

        note = ""
        if sid != 0 and best_escape and sid == best_escape["seasonid"]:
            note = "🏆 巅峰赛季"
        elif sid != 0 and worst_escape and sid == worst_escape["seasonid"]:
            note = "💩 低谷赛季"
        elif sid == 0:
            note = "（全部赛季总和）"

        lines.append(
            f"  {label_sid:>4}  {n:>5,}  {esc:>5,}  {ratio:>6}  "
            f"{kills:>5,}  {dur:>7}  {note}"
        )

    return "\n".join(lines)


def _parse_pct(s: str) -> int:
    """'33%' → 33"""
    try:
        return int(s.rstrip("%"))
    except (ValueError, AttributeError):
        return 0
