"""三角洲行动数据桥接 - 调度每日密码播报 + 响应群内查询命令。

复用 daily_mood.py 的调度模式：每分钟 tick 一次，到点拉数据并推送到 QQ 群。
"""

from __future__ import annotations

import re
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

from .aliases import DFAliases
from .abilities import DFAbilities
from gamebot.core.memory import GameMemory


CMD_PATTERN = re.compile(r"\[CMD:(df_\w+)\s*(.*?)\]")
MAX_TOOL_ROUNDS = 4   # AI 工具调用最大轮次（防死循环）

# AI 容易出"光承诺不调用"的回复（如"我调一下"、"稍等让我查查"）。
# 命中这些 pattern + 没真 [CMD:...] 时，给它一次重试机会强制调工具。
_INTENT_TO_CALL_TOOL = re.compile(
    r"(我[来去]?(?:查|调|看|拉)|稍等|让我(?:查|看|调)|我帮你看|马上(?:查|看))",
    re.IGNORECASE,
)


CST = timezone(timedelta(hours=8))

# df_stats 库不在 mcbot 包内，临时加 sys.path（路径相对于本文件）
_DF_STATS_DIR = Path(__file__).resolve().parents[3] / "scripts" / "df_stats"
if str(_DF_STATS_DIR) not in sys.path:
    sys.path.insert(0, str(_DF_STATS_DIR))


def _format_secret_msg(secrets: list[dict]) -> str:
    """5 张图密码 → 群消息文案。"""
    if not secrets:
        return "🔐 今日地图密码暂未生成（接口空数据，可能 cookie 失效了）"
    lines = ["🔐 今日三角洲地图密码"]
    for item in secrets:
        name = item.get("mapName", "?")
        code = item.get("secret", "?")
        lines.append(f"  {name}：{code}")
    return "\n".join(lines)


class DFStatsBridge:
    """三角洲行动数据 → 指定 QQ 群桥接。

    职责：
    - 每天指定时刻拉今日密码并推到三角洲群（不是 MC 群）
    - 只响应该群内关键词查询（"今日密码" 等），其他群消息一律忽略
    - cookie 失效时给出友好提示

    group_id: 三角洲群号（如 257381453），所有 DF 功能仅限这个群
    send_to_group: 函数，签名 (group_id, message) → None；通常来自 QQBridge.send_to_group
    """

    KEYWORDS = ("今日密码", "三角洲密码", "地图密码", "df密码", "df secret")

    def __init__(
        self,
        secret_curl: str | Path,
        group_id: int,
        send_to_group: Optional[Callable[[int, str], None]],
        aliases_path: str | Path = "data/df_aliases.json",  # 保留参数兼容，但内部已不读
        broadcast_hour: int = 6,
        enabled: bool = True,
        # 可选：其他接口的 curl，给 AI 工具调用用
        record_curl: str | Path | None = None,
        profile_curl: str | Path | None = None,
        season_curl: str | Path | None = None,
        # 可选：AI provider（如果传了，bot 在 DF 群能聊天 + 调工具）
        ai_provider=None,
        history_max: int = 12,
        # 新：memory 根目录（fact_store + episode_log）
        memory_root: str | Path = "data/memory/df",
    ):
        self.secret_curl = Path(secret_curl)
        self.group_id = group_id
        self.send_to_group = send_to_group
        self.broadcast_hour = broadcast_hour
        self.enabled = enabled
        self._last_broadcast_date: Optional[str] = None
        # 通用 agent memory（fact 三元组 + 事件流）
        self.memory = GameMemory(root=memory_root)
        # 干员别名管理器（包装 memory）
        self.aliases = DFAliases(self.memory)
        # AI 工具集
        self.abilities = DFAbilities(
            aliases=self.aliases,
            memory=self.memory,
            secret_curl=secret_curl,
            record_curl=record_curl,
            profile_curl=profile_curl,
            season_curl=season_curl,
        )
        # AI provider（None 表示不启用 AI，只走关键词/别名）
        self.ai_provider = ai_provider
        self.history_max = history_max
        # 群级共享会话历史（不是 per-user，因为 DF 群里大家一起讨论）
        self._history: list[dict] = []
        # _history 是共享可变状态，多线程并发写会撕裂。所有读写都要持锁
        self._history_lock = threading.Lock()

    # ---- 拉数据 ----

    def _fetch(self) -> list[dict]:
        """调用 df_stats 库拉今日密码。

        懒导入避免 mcbot 启动时强依赖 df_stats（curl 文件可能还没准备好）。
        """
        from df_stats import load_from_curl_file, fetch_daily_secret

        if not self.secret_curl.exists():
            raise FileNotFoundError(
                f"未配置 secret_curl 文件：{self.secret_curl}"
            )
        client = load_from_curl_file(self.secret_curl)
        return fetch_daily_secret(client)

    # ---- 关键词响应（QQ 群命中关键词时调用）----

    def handle_keyword(self, source_group_id: int, message: str) -> Optional[str]:
        """如果消息来自配置的三角洲群且命中关键词，返回回复文案；否则返回 None。"""
        if not self.enabled:
            return None
        # 严格隔离：非三角洲群一律不响应
        if source_group_id != self.group_id:
            return None
        msg_lower = message.lower().strip()
        if not any(kw in msg_lower for kw in self.KEYWORDS):
            return None

        try:
            secrets = self._fetch()
            return _format_secret_msg(secrets)
        except FileNotFoundError as e:
            return f"❌ 还没配置 df_stats，请联系管理员：{e}"
        except Exception as e:
            return f"❌ 拉密码失败：{type(e).__name__}: {e}"

    def reply(
        self,
        source_group_id: int,
        source_nickname: str,
        message: str,
        at_qq_list: Optional[list[int]] = None,
    ) -> bool:
        """处理一条群消息：

        1. 不归我管的群直接返回 False
        2. 优先尝试别名学习（"我玩牧羊人" / "更正—@老王 为 麦小雯"）
        3. 然后尝试关键词查询（"今日密码"等）
        4. 都没命中且配置了 AI → 走 LLM converse 循环（带 df 工具）
        命中任何一种返回 True；都不命中返回 False

        at_qq_list: 该消息 @ 了哪些 QQ 号（CQ:at 解析出的列表）。
                    用于"更正—@某人 为 牧羊人"这种带 @ 引用的别名设置。
        """
        if not self.enabled or source_group_id != self.group_id:
            return False

        # 1. 别名学习（regex 简单识别）
        alias_reply = self.aliases.try_parse(
            source_nickname, message, at_qq_list=at_qq_list
        )
        if alias_reply:
            if self.send_to_group:
                self.send_to_group(source_group_id, alias_reply)
            return True

        # 2. 关键词查询（快速通道，不走 AI 省 token）
        keyword_reply = self.handle_keyword(source_group_id, message)
        if keyword_reply is not None:
            if self.send_to_group:
                self.send_to_group(source_group_id, keyword_reply)
            return True

        # 3. AI converse（带 df 工具调用）
        if self.ai_provider:
            ai_reply = self.converse(source_nickname, message)
            if ai_reply:
                if self.send_to_group:
                    self.send_to_group(source_group_id, ai_reply)
                return True

        return False

    # ---- AI 工具循环（核心）----

    def converse(self, nickname: str, message: str) -> str:
        """让 LLM 处理一条消息，期间可以调 [CMD:df_xxx] 工具。

        每一步打详细日志，**不让 LLM 失败静默化**——卡住的话能直接从
        journalctl 看到卡在哪个 round / tool 上。
        """
        if not self.ai_provider:
            print(f"[DFStats] ai_provider 未配置，跳过 AI 处理")
            return ""

        import time as _time
        t_start = _time.time()
        print(f"[DFStats] converse start | nickname={nickname!r} | msg={message[:60]!r}")

        with self._history_lock:
            self._history.append({
                "role": "user",
                "content": f"[{nickname}]: {message}",
            })
            self._trim_history_locked()

        # 把当前消息传给 prompt builder 做智能 memory 检索
        system_prompt = self.abilities.build_system_prompt(self.group_id, user_message=message)
        visible_parts: list[str] = []
        # 同时把这条用户消息记为 episode（便于回顾"谁问过什么"）
        self.memory.add_episode(
            type="conversation",
            content=f"{nickname}: {message[:100]}",
            actors=[nickname],
        )

        for round_idx in range(MAX_TOOL_ROUNDS):
            # 拷贝 history 出锁外传给 LLM（不在锁里耗时几秒做 HTTP 调用）
            with self._history_lock:
                history_snapshot = list(self._history)
            print(f"[DFStats] round {round_idx+1}/{MAX_TOOL_ROUNDS} | history={len(history_snapshot)} msgs")
            reply = self.ai_provider.chat(history_snapshot, system_prompt)
            if reply is None:
                print(f"[DFStats] round {round_idx+1} AI 返回 None，循环终止")
                break

            with self._history_lock:
                self._history.append({"role": "assistant", "content": reply})

            commands = CMD_PATTERN.findall(reply)
            visible = CMD_PATTERN.sub("", reply).strip()
            if visible:
                visible_parts.append(visible)
                print(f"[DFStats] round {round_idx+1} visible={len(visible)} chars, cmds={len(commands)}")
            else:
                print(f"[DFStats] round {round_idx+1} no visible text, cmds={len(commands)}")

            if not commands:
                # 检测"光承诺不调用"：AI 说"我去查"但没真带 [CMD:...] —— push 它真调
                if visible and _INTENT_TO_CALL_TOOL.search(visible) and round_idx < MAX_TOOL_ROUNDS - 1:
                    print(f"[DFStats] round {round_idx+1} 检测到承诺无调用，push AI 真调工具")
                    with self._history_lock:
                        self._history.append({
                            "role": "user",
                            "content": "[system] 你刚说要查/调工具，但没在回复里加 [CMD:xxx] 标签。bot 看不到 CMD 就不会执行任何工具。请直接在下一条回复里写 [CMD:xxx]（同一条消息里），不要再光说不调。",
                        })
                    # 移除刚才的承诺式回复，避免让群友看到没用的"我调一下"
                    visible_parts.pop()
                    continue
                break

            results = []
            for tool_name, tool_args in commands:
                tool_name = tool_name.strip()
                tool_args = tool_args.strip()
                t_tool = _time.time()
                print(f"[DFStats] tool call: {tool_name} {tool_args!r}")
                result = self.abilities.execute(tool_name, tool_args)
                tool_elapsed = _time.time() - t_tool
                print(f"[DFStats]   ✓ {tool_name} done in {tool_elapsed:.1f}s, result={len(result)} chars")
                if len(result) > 2000:
                    # 明确标注截断让 AI 知道（之前是悄悄截断）
                    truncated_marker = f"\n...[结果过长，bot 截断了后 {len(result) - 2000} 字符，AI 看不到]"
                    result = result[:2000] + truncated_marker
                results.append(f"[{tool_name} 结果]\n{result}")

            tool_msg = "\n\n".join(results)
            with self._history_lock:
                self._history.append({
                    "role": "user",
                    "content": f"[tool_results]\n{tool_msg}",
                })

            if round_idx == MAX_TOOL_ROUNDS - 1:
                visible_parts.append(f"（工具调用次数已达上限）")
                print(f"[DFStats] 达到 MAX_TOOL_ROUNDS={MAX_TOOL_ROUNDS}，停止")

        with self._history_lock:
            self._trim_history_locked()
        final = "\n\n".join(p for p in visible_parts if p).strip()
        total_elapsed = _time.time() - t_start
        print(
            f"[DFStats] converse done in {total_elapsed:.1f}s, "
            f"final reply {len(final)} chars"
        )
        if not final:
            # 不让"..."这种空回复静默掉，明确告诉群友 AI 挂了
            return "（AI 暂时没回，请稍后再试或看服务器日志）"
        return final

    def _trim_history_locked(self):
        """保留最近 N 条历史，防止上下文无限增长。**调用前必须持 _history_lock**。"""
        if len(self._history) > self.history_max:
            self._history = self._history[-self.history_max:]

    def _trim_history(self):
        """保留最近 N 条历史。线程安全版本，给 reply() 入口处调用用。"""
        with self._history_lock:
            self._trim_history_locked()

    # ---- 定时播报 ----

    def _broadcast_today(self):
        """拉今日密码并推到三角洲群。"""
        if not self.send_to_group:
            print("[DFStats] send_to_group 未配置，跳过广播")
            return
        try:
            secrets = self._fetch()
            msg = _format_secret_msg(secrets)
            self.send_to_group(self.group_id, msg)
            print(f"[DFStats] 已广播今日密码到群 {self.group_id}：{[s.get('secret') for s in secrets]}")
        except Exception as e:
            print(f"[DFStats] 广播失败：{type(e).__name__}: {e}")
            if self.send_to_group:
                self.send_to_group(
                    self.group_id,
                    f"⚠️ 今日地图密码拉取失败（{type(e).__name__}），可能 cookie 过期了",
                )

    def _scheduler_loop(self):
        while True:
            now = datetime.now(CST)
            today = now.strftime("%Y-%m-%d")
            if now.hour == self.broadcast_hour and self._last_broadcast_date != today:
                self._last_broadcast_date = today
                self._broadcast_today()
            time.sleep(60)

    def start(self):
        """启动后台线程。"""
        if not self.enabled:
            print("[DFStats] 桥接未启用，跳过启动")
            return
        t = threading.Thread(target=self._scheduler_loop, daemon=True)
        t.start()
        print(
            f"[DFStats] 已启动：每日 {self.broadcast_hour:02d}:00 广播地图密码；"
            f"关键词触发：{', '.join(self.KEYWORDS)}"
        )
