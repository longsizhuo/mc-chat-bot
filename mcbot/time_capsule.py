"""时间胶囊 - 网站写一段话 + 选封存天数，到期小方自动推 QQ 群。

存储：data/capsules.json
    [{"id": "...", "author": "xxx", "text": "...", "open_at": 1700000000, "created_at": ..., "delivered": false}]

流程：
1. 网站 POST /api/capsules → 存入 capsules.json
2. 每小时检查一次，到期 + 未 delivered 的推 QQ 群 + 标记 delivered
"""

import json
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Callable


CST = timezone(timedelta(hours=8))

MAX_AUTHOR = 20
MAX_TEXT = 500
MIN_DAYS = 1
MAX_DAYS = 365
MAX_TOTAL = 200


class TimeCapsule:
    """时间胶囊管理器。"""

    def __init__(self, storage_path: str, send_to_qq: Optional[Callable[[str], None]] = None):
        self.storage_path = Path(storage_path)
        self.send_to_qq = send_to_qq
        self._lock = threading.Lock()

    def _load(self) -> list[dict]:
        if not self.storage_path.exists():
            return []
        try:
            d = json.loads(self.storage_path.read_text(encoding="utf-8"))
            return d if isinstance(d, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    def _save(self, data: list[dict]):
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.storage_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    def list_public(self) -> list[dict]:
        """返回公开信息给前端，不泄漏正文（封存中看不到）。"""
        with self._lock:
            now = time.time()
            result = []
            for c in self._load():
                open_at = c.get("open_at", 0)
                is_open = now >= open_at
                result.append({
                    "id": c["id"],
                    "author": c["author"],
                    "created_at": c.get("created_at", 0),
                    "open_at": open_at,
                    "is_open": is_open,
                    "text": c["text"] if is_open else None,
                    "days_left": max(0, int((open_at - now) // 86400)) if not is_open else 0,
                })
            result.sort(key=lambda x: x["open_at"])
            return result

    def post(self, author: str, text: str, days: int) -> tuple[bool, str]:
        author = (author or "").strip()
        text = (text or "").strip()
        if not author or not text:
            return False, "作者和内容都不能为空"
        if len(author) > MAX_AUTHOR:
            return False, f"名字太长（限 {MAX_AUTHOR} 字）"
        if len(text) > MAX_TEXT:
            return False, f"内容太长（限 {MAX_TEXT} 字）"
        if not isinstance(days, int) or days < MIN_DAYS or days > MAX_DAYS:
            return False, f"封存天数必须在 {MIN_DAYS}-{MAX_DAYS} 之间"

        now = time.time()
        record = {
            "id": uuid.uuid4().hex[:8],
            "author": author,
            "text": text,
            "created_at": int(now),
            "open_at": int(now + days * 86400),
            "delivered": False,
        }
        with self._lock:
            data = self._load()
            data.append(record)
            if len(data) > MAX_TOTAL:
                data.sort(key=lambda x: x.get("created_at", 0))
                data = data[-MAX_TOTAL:]
            self._save(data)
        return True, record["id"]

    def check_and_deliver(self):
        """每小时调用：把到期未发的胶囊推到 QQ 群。"""
        now = time.time()
        to_deliver: list[dict] = []
        with self._lock:
            data = self._load()
            changed = False
            for c in data:
                if not c.get("delivered") and now >= c.get("open_at", 0):
                    to_deliver.append(c)
                    c["delivered"] = True
                    changed = True
            if changed:
                self._save(data)

        for c in to_deliver:
            created = datetime.fromtimestamp(c.get("created_at", 0), CST).strftime("%Y-%m-%d")
            msg = (
                f"📦 时间胶囊到期\n\n"
                f"{c['author']} 在 {created} 封存了这句话：\n\n"
                f"{c['text']}"
            )
            print(f"[TimeCapsule] 发送: {c['id']}")
            if self.send_to_qq:
                try:
                    self.send_to_qq(msg)
                except Exception as e:
                    print(f"[TimeCapsule] 发送失败: {e}")

    def _scheduler_loop(self):
        """每小时检查一次。"""
        while True:
            try:
                self.check_and_deliver()
            except Exception as e:
                print(f"[TimeCapsule] 调度出错: {e}")
            time.sleep(3600)

    def start(self):
        t = threading.Thread(target=self._scheduler_loop, daemon=True)
        t.start()
        print("[TimeCapsule] 时间胶囊调度器已启动（每小时检查）")
