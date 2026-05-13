"""三角洲行动各业务接口封装。

apifox 文档把不同业务（战绩、资产、流水、改枪码…）都塞在同一个 AMS 入口，
靠 query 参数 type / iChartId / sIdeToken 区分。所以"封装一个接口"实际上
就是固定一组 query 参数模板。
"""

from __future__ import annotations

from typing import Iterator

from .client import DFClient


# type 字段定义（来自 apifox 文档）
MODE_FENGHUO = 4  # 烽火行动（撤离/搜打撤）
MODE_QUANMIAN = 5  # 全面战场（大规模载具 PvP）

MODE_NAMES = {
    MODE_FENGHUO: "烽火行动",
    MODE_QUANMIAN: "全面战场",
}


def fetch_records(
    client: DFClient,
    mode: int = MODE_FENGHUO,
    page: int = 1,
) -> list[dict]:
    """拉单页战绩，返回 data 数组。

    mode: 4=烽火行动，5=全面战场
    page: 从 1 开始
    """
    if mode not in MODE_NAMES:
        raise ValueError(f"未知模式 {mode}，应为 4(烽火) 或 5(全面战场)")

    resp = client.request({"type": mode, "page": page})

    # AMS 标准响应：{ret, iRet, sMsg, jData: {iRet, sMsg, data: [...]}}
    if resp.get("ret") not in (0, "0", None):
        raise RuntimeError(
            f"接口返回错误 ret={resp.get('ret')} msg={resp.get('sMsg')}"
        )

    jdata = resp.get("jData") or {}
    if str(jdata.get("iRet")) not in ("0", "ok"):
        # 有些接口 jData.iRet 用 0/字符串"ok"，区分一下
        msg = jdata.get("sMsg", "")
        if msg and msg != "ok":
            raise RuntimeError(f"jData 错误：{msg}")

    data = jdata.get("data")
    if data is None:
        return []
    if not isinstance(data, list):
        # 有些接口返回 dict 包了一层 list，做下兼容
        for v in data.values() if isinstance(data, dict) else []:
            if isinstance(v, list):
                return v
        return []
    return data


def fetch_all_pages(
    client: DFClient,
    mode: int = MODE_FENGHUO,
    max_pages: int = 5,
) -> Iterator[dict]:
    """翻页拉取直到没数据或达到 max_pages。"""
    for page in range(1, max_pages + 1):
        batch = fetch_records(client, mode=mode, page=page)
        if not batch:
            break
        for item in batch:
            yield item


# ---- 生涯/赛季接口（iChartId=317814，需要单独的 curl）----

def fetch_career(client: DFClient, seasonid: int = 0) -> dict:
    """拉指定赛季的生涯数据。

    seasonid=0 表示"生涯全部赛季总和"。
    返回 dict: {userData: {charac_name, picurl}, careerData: {soltotalfght, ...}}
    """
    resp = client.request({"seasonid": seasonid})
    return resp.get("jData", {})


def fetch_all_seasons(client: DFClient, max_season: int = 12) -> list[dict]:
    """枚举所有赛季，返回非空的赛季列表。"""
    seasons = []
    for sid in range(0, max_season + 1):
        try:
            data = fetch_career(client, seasonid=sid)
            cd = data.get("careerData") or {}
            if cd.get("result") == 0 and cd.get("soltotalfght") not in (None, "0", 0):
                seasons.append({"seasonid": sid, **data})
        except Exception:
            continue
    return seasons


# ---- 角色绑定信息接口（iChartId=316964）----

def fetch_role_binding(client: DFClient) -> dict:
    """拉角色绑定信息（昵称、UID、区服）。"""
    resp = client.request()
    return resp.get("jData", {}).get("bindarea") or {}


# ---- 每日密码接口（iChartId=316969，method=dfm/center.day.secret）----
# 走的是小程序入口（comm.ams.game.qq.com），认证用 qqmini cookies。
# 每天每张图密码不同，玩家进游戏要输。

def fetch_daily_secret(client: DFClient) -> list[dict]:
    """拉今日 5 张图的密码。

    返回 list[dict]，每项含 mapID / mapName / secret。
    示例：[{"mapID": 1, "mapName": "零号大坝", "secret": "2450"}, ...]
    """
    # method 和 param 已在 curl 文件里了，直接发就行
    resp = client.request()
    # 响应结构：jData.data.data.list（嵌套两层）
    data = resp.get("jData", {}).get("data", {}).get("data", {})
    return data.get("list", []) or []
