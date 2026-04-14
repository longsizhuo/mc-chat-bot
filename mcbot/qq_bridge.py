"""QQ group bridge via OneBot 11 WebSocket + HTTP API."""

import json
import socket
import hashlib
import base64
import struct
import threading
import time
from typing import Callable, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError


class QQBridge:
    """Bridges MC chat events to/from a QQ group via OneBot 11 protocol."""

    def __init__(
        self,
        api_url: str,
        group_id: int,
        ws_port: int = 6101,
        bot_name: str = "MCBot",
        on_qq_message: Optional[Callable[[str, str], None]] = None,
    ):
        self.api_url = api_url.rstrip("/")
        self.group_id = group_id
        self.ws_port = ws_port
        self.bot_name = bot_name
        self.on_qq_message = on_qq_message

    def send_to_qq(self, message: str):
        """Send a message to the QQ group via HTTP API."""
        try:
            data = json.dumps({
                "group_id": self.group_id,
                "message": message,
            }).encode()
            req = Request(
                f"{self.api_url}/send_group_msg",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(req, timeout=5) as resp:
                result = json.loads(resp.read())
                if result.get("retcode") != 0:
                    print(f"[QQ] Send error: {result}")
        except (URLError, OSError, json.JSONDecodeError) as e:
            print(f"[QQ] Send failed: {e}")

    def forward_mc_event(self, event_type: str, message: str):
        """Forward an MC event to QQ group with formatting."""
        prefix = {
            "chat": "💬",
            "join": "📥",
            "leave": "📤",
            "death": "💀",
            "advancement": "🏆",
            "bot": "🤖",
        }.get(event_type, "📢")
        self.send_to_qq(f"{prefix} {message}")

    def _handle_event(self, data: dict):
        """Handle incoming OneBot event."""
        if data.get("post_type") != "message":
            return
        if data.get("message_type") != "group":
            return
        if data.get("group_id") != self.group_id:
            return

        raw_message = data.get("raw_message", "")
        sender = data.get("sender", {})
        nickname = sender.get("card") or sender.get("nickname", "QQ用户")

        if not raw_message.strip():
            return

        # Only respond to messages that @mention the bot
        self_id = data.get("self_id", 0)
        if f"[CQ:at,qq={self_id}]" not in raw_message:
            return

        print(f"[QQ] {nickname}: {raw_message}")

        if self.on_qq_message:
            self.on_qq_message(nickname, raw_message)

    # ---- WebSocket client (connect to NapCat's WS server) ----

    def _ws_connect(self, host: str, port: int, path: str = "/") -> socket.socket:
        """Perform WebSocket handshake."""
        sock = socket.create_connection((host, port), timeout=10)
        key = base64.b64encode(hashlib.sha1(str(time.time()).encode()).digest()[:16]).decode()
        handshake = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n"
            f"\r\n"
        )
        sock.sendall(handshake.encode())
        resp = sock.recv(4096).decode()
        if "101" not in resp:
            raise ConnectionError(f"WS handshake failed: {resp[:100]}")
        return sock

    def _ws_read_frame(self, sock: socket.socket) -> Optional[str]:
        """Read one WebSocket text frame."""
        try:
            header = self._recv_exact(sock, 2)
            if not header:
                return None
            opcode = header[0] & 0x0F
            if opcode == 0x8:  # close
                return None
            if opcode == 0x9:  # ping
                sock.sendall(bytes([0x8A, 0x00]))  # pong
                return ""

            masked = (header[1] & 0x80) != 0
            length = header[1] & 0x7F

            if length == 126:
                raw = self._recv_exact(sock, 2)
                length = struct.unpack(">H", raw)[0]
            elif length == 127:
                raw = self._recv_exact(sock, 8)
                length = struct.unpack(">Q", raw)[0]

            if masked:
                mask = self._recv_exact(sock, 4)
                payload = bytearray(self._recv_exact(sock, length))
                for i in range(length):
                    payload[i] ^= mask[i % 4]
                return payload.decode("utf-8", errors="replace")
            else:
                payload = self._recv_exact(sock, length)
                return payload.decode("utf-8", errors="replace")
        except (socket.timeout, ConnectionError, OSError):
            return None

    def _recv_exact(self, sock: socket.socket, n: int) -> bytes:
        """Receive exactly n bytes."""
        data = b""
        while len(data) < n:
            chunk = sock.recv(n - len(data))
            if not chunk:
                raise ConnectionError("Connection closed")
            data += chunk
        return data

    def _ws_loop(self):
        """Connect to NapCat WS server and process events, reconnect on failure."""
        while True:
            try:
                print(f"[QQ] Connecting to WS server 127.0.0.1:{self.ws_port}...")
                sock = self._ws_connect("127.0.0.1", self.ws_port)
                sock.settimeout(60)
                print(f"[QQ] WebSocket connected!")

                while True:
                    msg = self._ws_read_frame(sock)
                    if msg is None:
                        print("[QQ] WebSocket disconnected")
                        break
                    if not msg:
                        continue
                    try:
                        data = json.loads(msg)
                        self._handle_event(data)
                    except json.JSONDecodeError:
                        pass
            except Exception as e:
                print(f"[QQ] WS error: {e}, reconnecting in 5s...")
            finally:
                try:
                    sock.close()
                except Exception:
                    pass
            time.sleep(5)

    def start_listener(self):
        """Start WebSocket client thread to receive events from NapCat."""
        thread = threading.Thread(target=self._ws_loop, daemon=True)
        thread.start()

    def stop(self):
        pass
