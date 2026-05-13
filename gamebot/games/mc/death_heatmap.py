"""死亡热点地图 - 记录玩家死亡坐标，前端画成热力图。

实现：
1. bot 检测到死亡日志 → 延迟 2 秒查 RCON `data get entity <player> LastDeathLocation`
   （延迟是为了等 Minecraft 把 NBT 更新到死亡位置）
2. 解析输出 → 追加一条 {x, y, z, dimension, player, cause, ts} 到 data/deaths.json
3. 通过 /api/deaths 端点提供给前端画热力图

注意：只能记录从这个功能上线后的死亡。历史死亡没有坐标可找。
"""

import json
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .providers import AIProvider


CST = timezone(timedelta(hours=8))

# LastDeathLocation NBT 输出格式示例：
# Abore has the following entity data: {dimension: "minecraft:overworld", pos: [I; 153, 64, -22]}
NBT_POS_RE = re.compile(r"pos:\s*\[I;\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*\]")
NBT_DIM_RE = re.compile(r'dimension:\s*"(minecraft:[\w_]+)"')

# 保留上限（避免文件无限增长）
MAX_RECORDS = 500

# 等 NBT 更新的延迟（秒）
QUERY_DELAY = 2.0


_LAST_WORDS_PROMPT = (
    "你是一个 Minecraft 服务器的旁白。玩家 {player} 刚刚死亡，死亡原因：{cause}。"
    "请用第一人称为这个玩家生成一句简短的「遗言」，15 字以内，语气可以搞笑、悲壮或荒诞，"
    "要贴合死亡方式。只返回遗言本身，不要引号，不要解释。"
)


class DeathHeatmap:
    """死亡坐标记录器。"""

    def __init__(self, storage_path: str, rcon, ai_provider: Optional["AIProvider"] = None):
        self.storage_path = Path(storage_path)
        self.rcon = rcon
        self.ai = ai_provider
        self._lock = threading.Lock()

    def _load(self) -> list[dict]:
        if not self.storage_path.exists():
            return []
        try:
            data = json.loads(self.storage_path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    def _save(self, data: list[dict]):
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        # 超过上限时保留最新的 MAX_RECORDS 条
        if len(data) > MAX_RECORDS:
            data = sorted(data, key=lambda d: d.get("ts", 0))[-MAX_RECORDS:]
        try:
            self.storage_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    def list_all(self) -> list[dict]:
        with self._lock:
            return self._load()

    def record_death(self, player: str, cause: str):
        """bot 捕获 death 事件时调用。延迟 2 秒后异步查 NBT。"""
        def _do_record():
            try:
                time.sleep(QUERY_DELAY)
                resp = self.rcon.send(f"data get entity {player} LastDeathLocation") or ""
                pos_m = NBT_POS_RE.search(resp)
                if not pos_m:
                    # 玩家下线了或 NBT 没更新，放弃
                    print(f"[DeathHeatmap] {player} 死亡坐标查不到，跳过：{resp[:80]}")
                    return
                x, y, z = int(pos_m.group(1)), int(pos_m.group(2)), int(pos_m.group(3))

                dim_m = NBT_DIM_RE.search(resp)
                dimension = dim_m.group(1) if dim_m else "minecraft:overworld"

                # AI 生成遗言（可选，失败不阻断记录）
                last_words: Optional[str] = None
                if self.ai:
                    try:
                        prompt = _LAST_WORDS_PROMPT.format(player=player, cause=cause)
                        last_words = self.ai.chat(
                            [{"role": "user", "content": prompt}],
                            system_prompt="你是一个 Minecraft 服务器旁白，幽默简洁。",
                        )
                        if last_words:
                            last_words = last_words.strip().strip('"').strip("「」")[:50]
                    except Exception as lwe:
                        print(f"[DeathHeatmap] 遗言生成失败: {lwe}")

                record = {
                    "player": player,
                    "cause": cause,
                    "x": x,
                    "y": y,
                    "z": z,
                    "dimension": dimension,
                    "ts": int(time.time()),
                }
                if last_words:
                    record["last_words"] = last_words
                with self._lock:
                    data = self._load()
                    data.append(record)
                    self._save(data)
                print(f"[DeathHeatmap] 记录 {player} 死于 ({x}, {y}, {z}) @ {dimension}")
            except Exception as e:
                print(f"[DeathHeatmap] 记录失败: {e}")

        threading.Thread(target=_do_record, daemon=True).start()
