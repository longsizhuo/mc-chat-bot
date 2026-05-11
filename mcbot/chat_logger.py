"""玩家聊天日志记录 + 词云数据生成。

存储：data/chat_log.json
格式：[{"player": "xxx", "text": "...", "ts": 1700}]
保留上限：10000 条（避免无限增长）

/api/wordcloud 端点从这里读取本周数据，统计词频并返回。
"""

import json
import re
import threading
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path


CST = timezone(timedelta(hours=8))
MAX_LOG_ENTRIES = 10000

# 停用词：过滤掉无意义的高频词
STOPWORDS = {
    "的", "了", "是", "在", "我", "你", "他", "她", "它", "们",
    "和", "与", "也", "都", "就", "很", "这", "那", "有", "吧",
    "啊", "哦", "嗯", "哈", "呢", "吗", "嘛", "哇", "哎", "唉",
    "不", "没", "好", "要", "去", "来", "说", "做", "看", "用",
    "到", "会", "可", "什么", "为什么", "怎么", "然后", "所以",
    "但是", "因为", "如果", "还是", "已经", "现在", "一个", "一下",
    "一直", "这个", "那个", "这里", "那里", "可以", "应该", "觉得",
    "a", "an", "the", "is", "it", "i", "you", "he", "she", "we",
    "at", "in", "on", "to", "of", "for", "and", "or", "but",
    "ok", "no", "yes", "hi", "hey", "lol", "oh", "ah",
}

# 过滤纯标点、数字、单字母
_NOISE_RE = re.compile(r"^[\W\d_]+$|^[a-zA-Z]$")


class ChatLogger:
    """追加聊天记录，提供本周词云数据。"""

    def __init__(self, storage_path: str):
        self.path = Path(storage_path)
        self._lock = threading.Lock()

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
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )

    def record(self, player: str, text: str):
        """记录一条聊天消息（线程安全）。"""
        with self._lock:
            data = self._load()
            data.append({"player": player, "text": text, "ts": int(time.time())})
            if len(data) > MAX_LOG_ENTRIES:
                data = data[-MAX_LOG_ENTRIES:]
            self._save(data)

    def weekly_word_counts(self) -> list[dict]:
        """返回本周（周一 00:00 CST 起）词频，格式 [{text, value, player?}]。"""
        now = datetime.now(CST)
        # 本周周一零点
        week_start = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        week_start_ts = int(week_start.timestamp())

        with self._lock:
            data = self._load()

        counter: Counter[str] = Counter()
        player_word: dict[str, str] = {}  # word -> 最常说这个词的玩家

        player_counter: dict[str, Counter[str]] = {}

        for entry in data:
            if entry.get("ts", 0) < week_start_ts:
                continue
            player = entry.get("player", "")
            text = entry.get("text", "")
            words = _tokenize(text)
            for w in words:
                counter[w] += 1
                if player not in player_counter:
                    player_counter[player] = Counter()
                player_counter[player][w] += 1

        # 找每个词的"代表玩家"（出现次数最多的那个）
        for w in counter:
            best_player = max(player_counter.keys(), key=lambda p: player_counter[p].get(w, 0))
            player_word[w] = best_player

        # 取前 80 个高频词
        top = counter.most_common(80)
        return [
            {"text": w, "value": cnt, "player": player_word.get(w, "")}
            for w, cnt in top
        ]


def _tokenize(text: str) -> list[str]:
    """简单分词：按空格和标点切分，过滤停用词和噪音。"""
    # 去掉 MC 颜色代码（§x）
    text = re.sub(r"§.", "", text)
    # 中文按字或词切（这里按字，适合短聊天）
    tokens: list[str] = []
    # 先按非汉字切
    parts = re.split(r'[\s，。！？、；：\u201c\u201d\u2018\u2019「」【】《》()\[\]{}/\\|@#$%^&*+=\-<>~`]+', text)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # 如果是纯 ASCII，直接作为一个 token
        if part.isascii():
            w = part.lower()
            if len(w) >= 2 and w not in STOPWORDS and not _NOISE_RE.match(w):
                tokens.append(w)
        else:
            # 混合或纯中文：把连续中文字符当词组（2-4 字），单独 ASCII 子串独立处理
            i = 0
            while i < len(part):
                ch = part[i]
                if '\u4e00' <= ch <= '\u9fff':
                    # 取 2 字窗口（简单 bigram，适合游戏聊天短句）
                    bigram = part[i:i+2]
                    if len(bigram) == 2 and bigram not in STOPWORDS:
                        tokens.append(bigram)
                    # 同时也收单字（如果不是停用词）
                    if ch not in STOPWORDS:
                        tokens.append(ch)
                    i += 1
                else:
                    i += 1
    return tokens
