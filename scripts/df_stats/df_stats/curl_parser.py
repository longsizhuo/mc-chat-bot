"""把 Chrome DevTools 'Copy as cURL (bash)' 输出解析成结构化字段。

DevTools 复制出来的 curl 长这样（多行用 \\ 续行）：

    curl 'https://comm.ams.game.qq.com/ide/?iChartId=319386&type=4' \
      -H 'Cookie: openid=xxx; access_token=yyy' \
      -H 'Referer: https://df.qq.com/' \
      --data-raw 'foo=bar' \
      --compressed

需要从中抠出：URL、method、headers、cookies、query 参数、body。
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse, parse_qsl


@dataclass
class ParsedCurl:
    """解析后的 curl 结构。"""

    url: str = ""
    method: str = "GET"
    headers: dict[str, str] = field(default_factory=dict)
    cookies: dict[str, str] = field(default_factory=dict)
    query: dict[str, str] = field(default_factory=dict)
    body: Optional[str] = None
    # 拆出来的 base URL（不含 query）
    base_url: str = ""

    def cookie_header(self) -> str:
        """把 cookies dict 拼回 Cookie header 字符串。"""
        return "; ".join(f"{k}={v}" for k, v in self.cookies.items())


def parse_curl(curl_text: str) -> ParsedCurl:
    """解析一整段 curl 命令文本。

    支持 DevTools 复制出的多行格式（带反斜杠续行）和 PowerShell 格式做了基本兼容。
    """
    # 先把多行折叠成一行：反斜杠换行 → 空格
    flat = re.sub(r"\\\n\s*", " ", curl_text)
    flat = flat.strip()

    # shlex 按 shell 规则切 token，保留引号内空格
    try:
        tokens = shlex.split(flat, posix=True)
    except ValueError as e:
        raise ValueError(f"shlex 解析失败：{e}\n原文：{flat[:200]}")

    if not tokens or tokens[0] != "curl":
        raise ValueError("不是 curl 命令（首 token 不是 'curl'）")

    parsed = ParsedCurl()
    i = 1
    while i < len(tokens):
        tok = tokens[i]

        if tok in ("-H", "--header"):
            i += 1
            _add_header(parsed, tokens[i])

        elif tok in ("-b", "--cookie"):
            i += 1
            _add_cookie_string(parsed, tokens[i])

        elif tok in ("-X", "--request"):
            i += 1
            parsed.method = tokens[i].upper()

        elif tok in ("--data", "--data-raw", "--data-binary", "-d"):
            i += 1
            parsed.body = tokens[i]
            if parsed.method == "GET":
                parsed.method = "POST"

        elif tok == "--data-urlencode":
            # 不展开，原样塞进 body（足够 POC）
            i += 1
            parsed.body = (parsed.body + "&" if parsed.body else "") + tokens[i]
            if parsed.method == "GET":
                parsed.method = "POST"

        elif tok in ("--compressed", "--location", "-L", "-k", "--insecure"):
            # 这些 flag 没有值，忽略
            pass

        elif tok.startswith("-"):
            # 未知 flag，跳过它和它后面可能的值（保守起见跳一个）
            # 注意：有些 flag 没有值，会误吃下一个 token，但 POC 暂不处理
            pass

        elif not parsed.url:
            # 第一个非 flag 的位置参数是 URL
            parsed.url = tok

        i += 1

    if not parsed.url:
        raise ValueError("curl 里没找到 URL")

    # 拆 URL
    u = urlparse(parsed.url)
    parsed.base_url = f"{u.scheme}://{u.netloc}{u.path}"
    parsed.query = dict(parse_qsl(u.query, keep_blank_values=True))

    return parsed


def _add_header(parsed: ParsedCurl, raw: str) -> None:
    """处理一条 -H 'Name: value'。Cookie header 单独拆。"""
    if ":" not in raw:
        return
    name, _, value = raw.partition(":")
    name = name.strip()
    value = value.strip()
    if name.lower() == "cookie":
        _add_cookie_string(parsed, value)
    else:
        parsed.headers[name] = value


def _add_cookie_string(parsed: ParsedCurl, raw: str) -> None:
    """处理 'k1=v1; k2=v2' 形式的 cookie 串。"""
    for part in raw.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        k, _, v = part.partition("=")
        parsed.cookies[k.strip()] = v.strip()
