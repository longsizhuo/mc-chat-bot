"""玩家留言板 - 网站写留言，玩家上线时小方在游戏里念出来。

架构：
- 本模块启动一个简易 HTTP server（127.0.0.1:6102），用 Python 内建 http.server
- Caddy 把 mc.involutionhell.com/api/messages 反代到这个端口
- 网站 POST 留言 / GET 读取
- bot 在玩家 join 事件时调 announce_to_player() 播报未读留言

存储：data/messages.json
格式：[{"id": "...", "author": "xxx", "text": "...", "ts": 1700, "read_by": ["player1"]}]

防刷：
- 单条 text 上限 200 字
- 1 分钟内同一 author 只能发 1 条
- 总留言上限 100 条（超过自动清理最老的）
"""

import json
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional


CST = timezone(timedelta(hours=8))

# HTTP 服务配置
LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = 6102

# 防刷限制
MAX_TEXT_LENGTH = 200
MAX_AUTHOR_LENGTH = 20
MIN_POST_INTERVAL = 60  # 秒
MAX_TOTAL_MESSAGES = 100


class MessageStore:
    """文件持久化 + 并发安全的留言存储。"""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self._last_post_time: dict[str, float] = {}  # author -> ts

    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    def _save(self, data: list[dict]):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    def list_all(self) -> list[dict]:
        with self._lock:
            # 倒序：最新的在前
            return sorted(self._load(), key=lambda m: m.get("ts", 0), reverse=True)

    def post(self, author: str, text: str, recipient: str = "") -> tuple[bool, str]:
        """返回 (成功?, 错误或 message_id)。recipient 空串=广播给所有人。"""
        author = (author or "").strip()
        text = (text or "").strip()
        recipient = (recipient or "").strip()
        if not author or not text:
            return False, "作者和内容都不能为空"
        if len(author) > MAX_AUTHOR_LENGTH:
            return False, f"名字太长（限 {MAX_AUTHOR_LENGTH} 字内）"
        if len(recipient) > MAX_AUTHOR_LENGTH:
            return False, f"收件人名字太长（限 {MAX_AUTHOR_LENGTH} 字内）"
        if len(text) > MAX_TEXT_LENGTH:
            return False, f"内容太长（限 {MAX_TEXT_LENGTH} 字内）"

        now = time.time()
        with self._lock:
            last = self._last_post_time.get(author, 0)
            if now - last < MIN_POST_INTERVAL:
                wait = int(MIN_POST_INTERVAL - (now - last))
                return False, f"发得太快了，{wait} 秒后再试"
            self._last_post_time[author] = now

            data = self._load()
            msg_id = uuid.uuid4().hex[:8]
            data.append({
                "id": msg_id,
                "author": author,
                "text": text,
                "recipient": recipient,  # 空串 = 广播给所有上线玩家
                "ts": int(now),
                "read_by": [],
            })
            # 超过上限时保留最新的 MAX_TOTAL_MESSAGES 条
            if len(data) > MAX_TOTAL_MESSAGES:
                data.sort(key=lambda m: m.get("ts", 0))
                data = data[-MAX_TOTAL_MESSAGES:]
            self._save(data)
            return True, msg_id

    def get_unread_for(self, player: str) -> list[dict]:
        """返回指定玩家尚未听过、且收件人匹配的留言（不修改状态）。
        recipient 空串 → 广播，所有玩家都听得到；否则只有指定玩家听。"""
        with self._lock:
            data = self._load()
            result = []
            for m in data:
                if player in m.get("read_by", []):
                    continue
                r = m.get("recipient", "").strip()
                # 收件人匹配：空串广播 or 精确匹配（忽略大小写，因为离线模式大小写易错）
                if r == "" or r.lower() == player.lower():
                    result.append(m)
            return result

    def mark_read(self, player: str, message_ids: list[str]):
        """把若干留言对指定玩家标记为已读。"""
        if not message_ids:
            return
        with self._lock:
            data = self._load()
            changed = False
            for m in data:
                if m["id"] in message_ids and player not in m.get("read_by", []):
                    m.setdefault("read_by", []).append(player)
                    changed = True
            if changed:
                self._save(data)


class MessageBoard:
    """留言板门面：HTTP server + 玩家 join 事件回调 + 在线状态 API。"""

    def __init__(
        self,
        storage_path: str,
        rcon,
        bot_name: str = "小方",
        online_provider=None,  # Optional[Callable[[], list[dict]]]，返回 [{name, session_seconds}]
        deaths_provider=None,  # Optional[Callable[[], list[dict]]]，返回死亡坐标列表
    ):
        self.store = MessageStore(Path(storage_path))
        self.rcon = rcon
        self.bot_name = bot_name
        self.online_provider = online_provider
        self.deaths_provider = deaths_provider
        self._http_server: Optional[HTTPServer] = None

    # ========== HTTP ==========

    def _make_handler(self):
        store = self.store
        online_provider = self.online_provider
        deaths_provider = self.deaths_provider

        class Handler(BaseHTTPRequestHandler):
            # 静音默认 stdout 日志，避免污染 bot 日志
            def log_message(self, *args, **kwargs):
                pass

            def _json_response(self, code: int, payload: dict):
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                # 允许同源即可，Caddy 反代同源
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                # /api/deaths - 死亡坐标列表（给热力图用）
                if self.path.startswith("/api/deaths"):
                    if deaths_provider:
                        try:
                            deaths = deaths_provider() or []
                        except Exception:
                            deaths = []
                    else:
                        deaths = []
                    return self._json_response(200, {
                        "ok": True,
                        "count": len(deaths),
                        "deaths": deaths,
                    })

                # /api/online - 返回在线玩家 + 本次在线时长
                if self.path.startswith("/api/online"):
                    if online_provider:
                        try:
                            players = online_provider() or []
                        except Exception:
                            players = []
                    else:
                        players = []
                    return self._json_response(200, {
                        "ok": True,
                        "count": len(players),
                        "players": players,
                    })

                if self.path.startswith("/api/messages"):
                    messages = store.list_all()
                    # 不暴露 read_by 细节给前端
                    pub = [
                        {"id": m["id"], "author": m["author"], "text": m["text"],
                         "recipient": m.get("recipient", ""),
                         "ts": m["ts"], "read_count": len(m.get("read_by", []))}
                        for m in messages
                    ]
                    return self._json_response(200, {"ok": True, "messages": pub})
                self._json_response(404, {"ok": False, "error": "not found"})

            def do_POST(self):
                if self.path.startswith("/api/messages"):
                    length = int(self.headers.get("Content-Length", 0) or 0)
                    if length > 2048:
                        return self._json_response(413, {"ok": False, "error": "payload 过大"})
                    raw = self.rfile.read(length)
                    try:
                        payload = json.loads(raw.decode("utf-8"))
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        return self._json_response(400, {"ok": False, "error": "JSON 格式错误"})

                    ok, result = store.post(
                        author=payload.get("author", ""),
                        text=payload.get("text", ""),
                        recipient=payload.get("recipient", ""),
                    )
                    if ok:
                        return self._json_response(200, {"ok": True, "id": result})
                    return self._json_response(400, {"ok": False, "error": result})
                self._json_response(404, {"ok": False, "error": "not found"})

        return Handler

    def _run_http(self):
        handler = self._make_handler()
        try:
            self._http_server = HTTPServer((LISTEN_HOST, LISTEN_PORT), handler)
            print(f"[MessageBoard] HTTP 服务已启动（{LISTEN_HOST}:{LISTEN_PORT}）")
            self._http_server.serve_forever()
        except OSError as e:
            print(f"[MessageBoard] HTTP 启动失败: {e}")

    # ========== 玩家 join 触发 ==========

    def announce_to_player(self, player: str):
        """玩家上线时调用：念出他未听过的留言，逐条 RCON say。"""
        unread = self.store.get_unread_for(player)
        if not unread:
            return
        # 最多一次性念 5 条，免得刷屏
        to_say = unread[-5:]
        for m in to_say:
            date = datetime.fromtimestamp(m.get("ts", 0), CST).strftime("%m-%d %H:%M")
            # 定向留言 vs 广播留言，措辞不同
            if m.get("recipient"):
                text = f"{m['author']} 在 {date} 专门留话给 {m['recipient']}：{m['text']}"
            else:
                text = f"{m['author']} 在 {date} 留了句话：{m['text']}"
            try:
                self.rcon.say(self.bot_name, text)
            except Exception as e:
                print(f"[MessageBoard] 播报失败: {e}")
                return
        self.store.mark_read(player, [m["id"] for m in to_say])
        if len(unread) > 5:
            try:
                self.rcon.say(self.bot_name, f"（还有 {len(unread) - 5} 条旧留言，上网站看）")
            except Exception:
                pass

    def start(self):
        t = threading.Thread(target=self._run_http, daemon=True)
        t.start()
        print("[MessageBoard] 留言板模块已启动")
