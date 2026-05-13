"""三角洲行动 API HTTP 客户端（基于解析后的 curl）。

设计思想：不预设域名/路径，因为社区 API 文档没明确给（appid=101491592 推测是 AMS 入口
comm.ams.game.qq.com，但实际抓包可能走不同 CDN）。
让用户先抓一次包确定 base URL，之后改 query 参数就能复用同一份认证。
"""

from __future__ import annotations

import gzip
import json
import zlib
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode, parse_qsl
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from .curl_parser import ParsedCurl, parse_curl


class DFClient:
    """三角洲战绩 HTTP 客户端。

    一次抓包 → 复用 base URL + cookie + headers，调用时改 query 或 body 参数。
    AMS 接口对 GET / POST 都用同一个 path，type / page / item 这些业务参数
    可能在 query 里（GET）也可能在 body 里（POST form），由 method 决定。
    """

    def __init__(self, parsed: ParsedCurl):
        self.base_url = parsed.base_url
        self.method = parsed.method
        # 默认 headers 取抓包里的（含 Referer、UA 等），但 Cookie 单独管
        self.headers = {
            k: v for k, v in parsed.headers.items() if k.lower() != "cookie"
        }
        self.cookies = dict(parsed.cookies)
        # 抓包里的 query 作为基础参数
        self.base_query = dict(parsed.query)
        # 抓包里的 form-encoded body 解析成 dict，调用时可覆盖
        # 注意：parse_qsl 会做一次 percent-decode（%25→%），urlencode 会再编回去，
        # 所以双重编码的字段（如 eas_url）能完整 round-trip。
        self.base_body_params: dict[str, str] = {}
        if parsed.body:
            self.base_body_params = dict(parse_qsl(parsed.body, keep_blank_values=True))

    # ---- 关键参数提取 ----

    @property
    def openid(self) -> Optional[str]:
        return self.cookies.get("openid")

    @property
    def access_token(self) -> Optional[str]:
        return self.cookies.get("access_token")

    @property
    def appid(self) -> Optional[str]:
        return self.cookies.get("appid")

    @property
    def i_chart_id(self) -> Optional[str]:
        """AMS 接口的图表 ID（决定走哪个后端 handler）。可能在 query 或 body。"""
        return self.base_query.get("iChartId") or self.base_body_params.get("iChartId")

    @property
    def s_ide_token(self) -> Optional[str]:
        """AMS 接口的图表令牌。"""
        return self.base_query.get("sIdeToken") or self.base_body_params.get("sIdeToken")

    # ---- 发请求 ----

    def request(
        self,
        overrides: Optional[dict[str, Any]] = None,
        timeout: float = 15.0,
    ) -> dict:
        """发请求，返回解析后的 JSON dict。

        overrides: 业务参数覆盖（如 type=4, page=2）。会按 method 自动路由：
        POST 进 body，GET 进 query。
        """
        query = dict(self.base_query)
        body_params = dict(self.base_body_params)

        if overrides:
            normalized = {k: str(v) for k, v in overrides.items()}
            if self.method == "POST":
                body_params.update(normalized)
            else:
                query.update(normalized)

        url = self.base_url
        if query:
            url = f"{url}?{urlencode(query)}"

        headers = dict(self.headers)
        # 不让 urllib 自动加，全部手写覆盖
        if self.cookies:
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        # 抓包里可能写了 Accept-Encoding: br，但 urllib 不支持 brotli，强制改成 gzip
        if "Accept-Encoding" in headers:
            headers["Accept-Encoding"] = "gzip, deflate"

        # body 编码：POST 用 form-encoded（哪怕原抓包是 GET 也按 POST 处理时走 form）
        data: Optional[bytes] = None
        if self.method == "POST":
            if body_params:
                data = urlencode(body_params).encode("utf-8")
                headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
            elif self.body:
                # 没参数化的 body，原样发
                data = self.body.encode("utf-8")

        req = Request(url, data=data, headers=headers, method=self.method)

        try:
            with urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                encoding = resp.headers.get("Content-Encoding", "").lower()
                if encoding == "gzip":
                    raw = gzip.decompress(raw)
                elif encoding == "deflate":
                    raw = zlib.decompress(raw)
                text = raw.decode("utf-8", errors="replace")
        except HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(
                f"HTTP {e.code} {e.reason}\nURL: {url}\nBody: {body}"
            ) from e
        except URLError as e:
            raise RuntimeError(f"网络错误：{e.reason}\nURL: {url}") from e

        # 腾讯 AMS 经常返回 JSONP 风格的 callback(...) 包装，剥掉
        text = text.strip()
        if text.startswith("callback(") or text.startswith("jsonpCallback("):
            text = text[text.index("(") + 1 : text.rindex(")")]

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"响应不是合法 JSON：\n{text[:500]}"
            ) from e


def load_from_curl_file(path: str | Path) -> DFClient:
    """从 raw_curl.sh 文件读取并构造客户端。"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"找不到 curl 文件：{p}\n"
            f"请把 DevTools 复制的 cURL 整段粘到此文件。"
            f"参考 credentials/raw_curl.sh.example"
        )
    parsed = parse_curl(p.read_text(encoding="utf-8"))
    return DFClient(parsed)
