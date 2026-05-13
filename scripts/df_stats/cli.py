#!/usr/bin/env python3
"""三角洲行动战绩 CLI。

用法：
    python cli.py recent              # 最近一页烽火战绩
    python cli.py recent --mode 5     # 全面战场
    python cli.py recent --pages 3    # 拉前 3 页
    python cli.py summary --pages 5   # 5 页汇总
    python cli.py raw                 # 打印原始 JSON（调试用）
    python cli.py probe               # 检查 curl 解析是否正常
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 允许从仓库根目录直接 python cli.py
sys.path.insert(0, str(Path(__file__).parent))

from df_stats import (
    DFClient,
    load_from_curl_file,
    fetch_records,
    fetch_all_pages,
    fetch_career,
    fetch_all_seasons,
    fetch_role_binding,
    fetch_daily_secret,
    format_match,
    summarize_records,
    breakdown_by_map,
    breakdown_by_operator,
    breakdown_by_hour,
    format_highlights,
    analyze_teammates,
    format_recent_matches_detail,
    generate_advice,
    format_profile,
    format_seasons,
)
from df_stats.endpoints import MODE_FENGHUO, MODE_QUANMIAN, MODE_NAMES


DEFAULT_CURL = Path(__file__).parent / "credentials" / "raw_curl.sh"


def _load(curl_path: Path) -> DFClient:
    """加载客户端，失败时打印友好提示。"""
    try:
        return load_from_curl_file(curl_path)
    except FileNotFoundError as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"❌ curl 解析失败：{e}", file=sys.stderr)
        sys.exit(1)


def cmd_probe(args):
    """解析 curl 但不发请求，用于调试 cookie 是否齐全。"""
    client = _load(args.curl)
    print("✅ curl 解析成功")
    print(f"  Base URL    : {client.base_url}")
    print(f"  Method      : {client.method}")
    print(f"  iChartId    : {client.i_chart_id}")
    print(f"  sIdeToken   : {client.s_ide_token}")
    print(f"  openid      : {client.openid}")
    print(f"  acctype     : {client.cookies.get('acctype')}")
    print(f"  appid       : {client.appid}")
    print(f"  access_token: {(client.access_token or '')[:20]}...")
    print(f"  其他 cookies: {[k for k in client.cookies if k not in ('openid', 'acctype', 'appid', 'access_token')]}")
    print(f"  其他 headers: {list(client.headers.keys())}")
    print(f"  base_query  : {client.base_query}")
    if client.base_body_params:
        # 把 body 参数显示出来，但太长的（如 eas_url）截断
        shown = {}
        for k, v in client.base_body_params.items():
            shown[k] = v if len(v) <= 60 else v[:57] + "..."
        print(f"  base_body   : {shown}")
    missing = [
        name for name, val in [
            ("openid", client.openid),
            ("access_token", client.access_token),
            ("iChartId", client.i_chart_id),
            ("sIdeToken", client.s_ide_token),
        ] if not val
    ]
    if missing:
        print(f"\n⚠️ 缺少必要字段：{missing}")
    else:
        print(f"\n✅ 必要字段齐全，可以试着 `python cli.py recent`")


def cmd_recent(args):
    """打印最近 N 页战绩。"""
    client = _load(args.curl)
    mode_name = MODE_NAMES.get(args.mode, str(args.mode))
    print(f"📡 拉取 {mode_name} 战绩，前 {args.pages} 页...\n")

    records = list(fetch_all_pages(client, mode=args.mode, max_pages=args.pages))
    if not records:
        print("（没有战绩数据）")
        return

    for r in records:
        print(format_match(r))
    print(f"\n共 {len(records)} 场")


def cmd_summary(args):
    """聚合统计。"""
    client = _load(args.curl)
    mode_name = MODE_NAMES.get(args.mode, str(args.mode))
    print(f"📡 拉取 {mode_name} 战绩，前 {args.pages} 页...\n")

    records = list(fetch_all_pages(client, mode=args.mode, max_pages=args.pages))
    summary = summarize_records(records)
    print(f"=== {mode_name}战绩汇总 ===")
    print(summary["summary_text"])


def cmd_raw(args):
    """打印原始 JSON 响应，调试用。"""
    client = _load(args.curl)
    resp = client.request({"type": args.mode, "page": args.page})
    print(json.dumps(resp, ensure_ascii=False, indent=2))


def _fetch(args) -> list[dict]:
    """通用：按 mode + pages 拉数据。"""
    client = _load(args.curl)
    return list(fetch_all_pages(client, mode=args.mode, max_pages=args.pages))


def cmd_breakdown(args):
    """按地图 / 干员 / 时段拆分透视。"""
    records = _fetch(args)
    if not records:
        print("（没有数据）")
        return

    if args.dim == "map":
        print(breakdown_by_map(records))
    elif args.dim == "op":
        print(breakdown_by_operator(records))
    elif args.dim == "hour":
        print(breakdown_by_hour(records))
    else:  # all
        print(breakdown_by_map(records))
        print()
        print(breakdown_by_operator(records, min_count=2))
        print()
        print(breakdown_by_hour(records))


def cmd_highlights(args):
    """最赚 / 最亏的若干局。"""
    records = _fetch(args)
    print(format_highlights(records, n=args.top))


def cmd_teammates(args):
    """队友 / 开黑模式分析。"""
    records = _fetch(args)
    print(analyze_teammates(records))


def cmd_match(args):
    """单局详细战报：自己 + 全部队友的英雄/K/D/救助/带出。"""
    records = _fetch(args)
    print(format_recent_matches_detail(records, n=args.count))


def cmd_advice(args):
    """基于历史数据自动生成战术建议。"""
    records = _fetch(args)
    print(generate_advice(records))


def cmd_profile(args):
    """个人主页：角色信息 + 生涯总数据。

    需要两个 curl 文件：
    - --role-curl  抓 iChartId=316964 那个（个人概况/绑定信息）
    - --career-curl 抓 iChartId=317814 那个（赛季数据）
    """
    role_client = _load(args.role_curl)
    career_client = _load(args.career_curl)
    role = fetch_role_binding(role_client)
    career = fetch_career(career_client, seasonid=0)
    print(format_profile(role, career))


def cmd_seasons(args):
    """枚举所有赛季的横向对比表。"""
    client = _load(args.career_curl)
    seasons = fetch_all_seasons(client, max_season=args.max_season)
    print(format_seasons(seasons))


def cmd_secret(args):
    """今日 5 张图密码。"""
    client = _load(args.secret_curl)
    secrets = fetch_daily_secret(client)
    if not secrets:
        print("（接口返回空，cookie 可能过期了）")
        return
    print("🔐 今日地图密码")
    print("=" * 30)
    for item in secrets:
        print(f"  {item.get('mapName', '?'):<8}  →  {item.get('secret', '?')}")


def main():
    p = argparse.ArgumentParser(description="三角洲行动战绩 CLI")
    p.add_argument(
        "--curl",
        type=Path,
        default=DEFAULT_CURL,
        help=f"curl 文件路径（默认 {DEFAULT_CURL}）",
    )

    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("probe", help="检查 curl 解析（不发请求）")
    sp.set_defaults(func=cmd_probe)

    sp = sub.add_parser("recent", help="最近战绩列表")
    sp.add_argument("--mode", type=int, default=MODE_FENGHUO, choices=[4, 5],
                    help="4=烽火（默认） 5=全面战场")
    sp.add_argument("--pages", type=int, default=1, help="拉几页（默认 1）")
    sp.set_defaults(func=cmd_recent)

    sp = sub.add_parser("summary", help="战绩汇总统计")
    sp.add_argument("--mode", type=int, default=MODE_FENGHUO, choices=[4, 5])
    sp.add_argument("--pages", type=int, default=5)
    sp.set_defaults(func=cmd_summary)

    sp = sub.add_parser("raw", help="原始 JSON（调试）")
    sp.add_argument("--mode", type=int, default=MODE_FENGHUO)
    sp.add_argument("--page", type=int, default=1)
    sp.set_defaults(func=cmd_raw)

    sp = sub.add_parser("breakdown", help="多维度透视（地图/干员/时段）")
    sp.add_argument("--mode", type=int, default=MODE_FENGHUO, choices=[4, 5])
    sp.add_argument("--pages", type=int, default=10)
    sp.add_argument(
        "--dim", choices=["map", "op", "hour", "all"], default="all",
        help="维度：map=地图, op=干员, hour=时段, all=全部（默认）",
    )
    sp.set_defaults(func=cmd_breakdown)

    sp = sub.add_parser("highlights", help="最赚 / 最亏的局")
    sp.add_argument("--mode", type=int, default=MODE_FENGHUO, choices=[4, 5])
    sp.add_argument("--pages", type=int, default=10)
    sp.add_argument("--top", type=int, default=5, help="各取 TOP N（默认 5）")
    sp.set_defaults(func=cmd_highlights)

    sp = sub.add_parser("teammates", help="队友 / 开黑模式分析")
    sp.add_argument("--mode", type=int, default=MODE_FENGHUO, choices=[4, 5])
    sp.add_argument("--pages", type=int, default=10)
    sp.set_defaults(func=cmd_teammates)

    sp = sub.add_parser("match", help="单局详细战报（含全部队友）")
    sp.add_argument("--mode", type=int, default=MODE_FENGHUO, choices=[4, 5])
    sp.add_argument("--pages", type=int, default=1)
    sp.add_argument("--count", type=int, default=5, help="显示几局（默认 5）")
    sp.set_defaults(func=cmd_match)

    sp = sub.add_parser("advice", help="基于历史数据生成战术建议")
    sp.add_argument("--mode", type=int, default=MODE_FENGHUO, choices=[4, 5])
    sp.add_argument("--pages", type=int, default=10)
    sp.set_defaults(func=cmd_advice)

    default_role = Path(__file__).parent / "credentials" / "raw_curl_profile.sh"
    default_career = Path(__file__).parent / "credentials" / "raw_curl_season.sh"

    sp = sub.add_parser("profile", help="个人主页：角色名+生涯总数据")
    sp.add_argument("--role-curl", type=Path, default=default_role,
                    help="iChartId=316964 那个 curl（默认 credentials/raw_curl_profile.sh）")
    sp.add_argument("--career-curl", type=Path, default=default_career,
                    help="iChartId=317814 那个 curl（默认 credentials/raw_curl_season.sh）")
    sp.set_defaults(func=cmd_profile)

    sp = sub.add_parser("seasons", help="所有赛季横向对比")
    sp.add_argument("--career-curl", type=Path, default=default_career)
    sp.add_argument("--max-season", type=int, default=12, help="最多扫到第几个赛季（默认 12）")
    sp.set_defaults(func=cmd_seasons)

    default_secret = Path(__file__).parent / "credentials" / "raw_curl_secret.sh"
    sp = sub.add_parser("secret", help="今日 5 张图密码（小程序专属）")
    sp.add_argument("--secret-curl", type=Path, default=default_secret,
                    help="iChartId=316969 method=dfm/center.day.secret 那个 curl")
    sp.set_defaults(func=cmd_secret)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
