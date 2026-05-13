"""玩家口头禅 - 扫最近 7 天聊天日志，统计每人最高频词。"""

import gzip
import re
import time
from collections import Counter
from pathlib import Path

# 匹配聊天行
CHAT_RE = re.compile(
    r"\[Server thread/INFO\]: (?:\[Not Secure\] )?<(\w+)> (.+)"
)

# 中英文停用词（高频但无意义）
STOPWORDS = {
    # 中文虚词/常用词
    "的", "了", "是", "在", "我", "你", "他", "她", "它", "我们", "你们", "他们",
    "这", "那", "就", "都", "也", "不", "有", "和", "与", "啊", "吧", "嗯", "哦",
    "哈", "呢", "吗", "呀", "哎", "嗨", "哇", "哟", "哼", "唉", "喔", "哦哦",
    "好", "好的", "可以", "没有", "然后", "因为", "所以", "但是", "如果", "知道",
    "一下", "一个", "什么", "怎么", "为什么", "这个", "那个", "这里", "那里",
    "来", "去", "到", "说", "看", "用", "把", "给", "让", "被", "将", "会", "能",
    "想", "要", "做", "一", "二", "三", "四", "五", "还", "已经", "现在",
    "真的", "对", "嗯嗯", "啊啊", "哈哈", "哈哈哈", "嘿", "哦哦哦",
    # 英文常见词
    "the", "a", "an", "is", "in", "on", "at", "to", "of", "and", "or",
    "for", "with", "it", "i", "you", "he", "she", "we", "they", "that",
    "this", "was", "are", "be", "have", "do", "not", "but", "from",
    "ok", "yeah", "yes", "no", "oh", "uh", "lol", "haha", "hi", "hey",
    # MC 常见但无特征的词
    "服务器", "游戏", "玩", "上线", "下线", "mc", "minecraft",
    # bot 相关（玩家叫 bot 不代表个人口头禅）
    "小方", "小方小方", "bot", "mcbot",
}

# 最短有效词长度（中文按字符，英文按字节）
MIN_WORD_LEN = 2


def _tokenize(text: str) -> list[str]:
    """简单分词：中文按字/双字符切割，英文按空格切割。"""
    tokens = []
    # 先提取英文/数字词
    for word in re.findall(r"[a-zA-Z][a-zA-Z0-9]*", text):
        if len(word) >= MIN_WORD_LEN:
            tokens.append(word.lower())
    # 再提取中文双字符组合（bigram）和单独的中文词（2字以上连续）
    chinese_chunks = re.findall(r"[\u4e00-\u9fff]+", text)
    for chunk in chinese_chunks:
        # 长度 ≥ 2 的连续中文字符串整体保留
        if len(chunk) >= MIN_WORD_LEN:
            tokens.append(chunk)
        # 也加入 bigram（相邻两字），捕捉"卧槽""草泥""牛逼"等
        for i in range(len(chunk) - 1):
            tokens.append(chunk[i:i + 2])
    return tokens


def compute_catchphrases(logs_dir: str | Path, days: int = 7) -> dict[str, str]:
    """扫最近 days 天日志，返回 {player: top_word}。

    只返回有聊天记录的玩家，跳过 bot 账号（小方/bot）。
    """
    logs_dir = Path(logs_dir)
    if not logs_dir.exists():
        return {}

    cutoff = time.time() - days * 86400
    # player -> Counter
    counters: dict[str, Counter] = {}

    for lf in sorted(logs_dir.iterdir()):
        try:
            if lf.stat().st_mtime < cutoff:
                continue
            if not (lf.suffix == ".gz" or lf.name.endswith(".log")):
                continue

            opener = gzip.open if lf.suffix == ".gz" else open
            with opener(lf, "rt", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    m = CHAT_RE.search(line)
                    if not m:
                        continue
                    player, text = m.group(1), m.group(2)
                    # 跳过 bot 自己的消息
                    if player in ("小方", "bot", "MCBot"):
                        continue
                    # 跳过纯数字投票
                    if text.strip().isdigit():
                        continue

                    tokens = _tokenize(text)
                    c = counters.setdefault(player, Counter())
                    for token in tokens:
                        if token not in STOPWORDS and len(token) >= MIN_WORD_LEN:
                            c[token] += 1
        except (OSError, EOFError):
            continue

    result: dict[str, str] = {}
    for player, counter in counters.items():
        if not counter:
            continue
        top_word, _ = counter.most_common(1)[0]
        result[player] = top_word

    return result
