"""玩家地标系统 - 游戏内用口令 `标记`/`去哪`/`地标` 管理共享地标。

所有命令都在游戏聊天框里玩家主动触发，不走 QQ，不是推送：

- `标记 <地名>` → 把玩家当前坐标存为地标
- `去哪 <地名>` → 显示该地标方向和距离（用 title actionbar）
- `地标` 或 `地标列表` → 列出所有地标

存储在 data/landmarks.json，格式：
    {"大宅院": {"x": 153.5, "y": 64.0, "z": -22.1, "by": "Abore", "date": "2026-04-15"}}
"""

import json
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


CST = timezone(timedelta(hours=8))

# data get entity <player> Pos 的返回格式：Pos: [X.Yd, X.Yd, X.Yd]
POS_RE = re.compile(r"Pos:\s*\[\s*(-?\d+\.?\d*)d?\s*,\s*(-?\d+\.?\d*)d?\s*,\s*(-?\d+\.?\d*)d?\s*\]")

# 游戏内命令正则
CMD_MARK = re.compile(r"^标记\s+(.+)$")
CMD_NAV = re.compile(r"^去哪\s+(.+)$")
CMD_LIST = re.compile(r"^地标(?:列表)?$")
CMD_REMOVE = re.compile(r"^删除地标\s+(.+)$")


class LandmarksManager:
    """管理玩家自建地标，响应游戏内命令。"""

    def __init__(self, storage_path: str, rcon):
        self.storage_path = Path(storage_path)
        self.rcon = rcon

    # ========== 持久化 ==========

    def _load(self) -> dict:
        if not self.storage_path.exists():
            return {}
        try:
            data = json.loads(self.storage_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self, data: dict):
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.storage_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    # ========== 工具 ==========

    def _get_player_position(self, player: str) -> Optional[tuple[float, float, float]]:
        """通过 RCON 查询玩家当前坐标。玩家必须在线。"""
        resp = self.rcon.send(f"data get entity {player} Pos") or ""
        m = POS_RE.search(resp)
        if not m:
            return None
        return (float(m.group(1)), float(m.group(2)), float(m.group(3)))

    def _bearing_text(self, dx: float, dz: float) -> str:
        """把 (dx, dz) 方向换算成中文八方位。
        Minecraft 坐标：+X 东，-X 西，+Z 南，-Z 北。"""
        angle = math.degrees(math.atan2(dx, -dz))  # 0 = 北, 顺时针
        if angle < 0:
            angle += 360
        # 八方位分段（每 45 度）
        dirs = ["北", "东北", "东", "东南", "南", "西南", "西", "西北"]
        idx = int(((angle + 22.5) % 360) // 45)
        return dirs[idx]

    # ========== 命令处理 ==========

    def try_handle(self, player: str, message: str) -> Optional[str]:
        """尝试识别命令。返回要回复的文本；如果不是命令返回 None。"""
        msg = message.strip()

        # 列表
        if CMD_LIST.match(msg):
            return self._handle_list()

        # 标记 <地名>
        m = CMD_MARK.match(msg)
        if m:
            return self._handle_mark(player, m.group(1).strip())

        # 去哪 <地名>
        m = CMD_NAV.match(msg)
        if m:
            return self._handle_nav(player, m.group(1).strip())

        # 删除地标 <地名>
        m = CMD_REMOVE.match(msg)
        if m:
            return self._handle_remove(player, m.group(1).strip())

        return None

    def _handle_mark(self, player: str, name: str) -> str:
        if not name:
            return "语法：标记 <地名>"
        if len(name) > 20:
            return "地名太长（限 20 字内）"

        pos = self._get_player_position(player)
        if pos is None:
            return f"查不到 {player} 的坐标，你需要在线才能标记。"

        x, y, z = pos
        data = self._load()
        existed = name in data
        data[name] = {
            "x": round(x, 1),
            "y": round(y, 1),
            "z": round(z, 1),
            "by": player,
            "date": datetime.now(CST).strftime("%Y-%m-%d"),
        }
        self._save(data)
        verb = "更新" if existed else "保存"
        return (
            f"已{verb}地标「{name}」→ 坐标 "
            f"({int(x)}, {int(y)}, {int(z)})，由 {player} 标记"
        )

    def _handle_nav(self, player: str, name: str) -> str:
        if not name:
            return "语法：去哪 <地名>。输入「地标」查看所有可去的地方"

        data = self._load()
        if name not in data:
            all_names = list(data.keys())
            if not all_names:
                return "还没有任何地标。用「标记 <地名>」在当前位置打点"
            return f"没有「{name}」这个地标。现有的：{', '.join(all_names)}"

        pos = self._get_player_position(player)
        if pos is None:
            return f"查不到 {player} 的坐标，你需要在线。"

        px, _, pz = pos
        landmark = data[name]
        lx, ly, lz = landmark["x"], landmark["y"], landmark["z"]
        dx = lx - px
        dz = lz - pz
        distance = int(math.sqrt(dx * dx + dz * dz))
        direction = self._bearing_text(dx, dz)

        # 同时用 title 显示方向给玩家（actionbar 不打扰视线）
        title_text = f'"§a→ {name}: {direction} {distance}格"'
        self.rcon.send(
            f"title {player} actionbar {title_text}"
        )

        return (
            f"「{name}」在你 {direction} 方向 {distance} 格外，"
            f"坐标 ({int(lx)}, {int(ly)}, {int(lz)})，由 {landmark.get('by', '?')} 标记"
        )

    def _handle_list(self) -> str:
        data = self._load()
        if not data:
            return "还没有任何地标。用「标记 <地名>」在当前位置打点"

        # 按标记日期倒序，展示最多 10 个
        items = sorted(
            data.items(),
            key=lambda kv: kv[1].get("date", ""),
            reverse=True,
        )[:10]
        lines = [f"当前共 {len(data)} 个地标："]
        for name, info in items:
            lines.append(
                f"  · {name}  ({int(info['x'])}, {int(info['y'])}, {int(info['z'])}) "
                f"by {info.get('by', '?')}"
            )
        if len(data) > 10:
            lines.append(f"  ...（还有 {len(data) - 10} 个）")
        return "\n".join(lines)

    def _handle_remove(self, player: str, name: str) -> str:
        data = self._load()
        if name not in data:
            return f"没有「{name}」这个地标"
        # 谁标的谁才能删（防止误删别人的标记）
        by = data[name].get("by")
        if by and by != player:
            return f"「{name}」是 {by} 标的，只有他能删"
        del data[name]
        self._save(data)
        return f"已删除地标「{name}」"
