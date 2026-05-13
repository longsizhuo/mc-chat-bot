"""gamebot.core.memory —— 通用 agent memory 模块。

参考 Hermes Agent 的 MEMORY.md/USER.md 三层架构 + OpenClaw 的
"recall before execution, save after each run" 思路。

跨游戏共用。每个 game module 拿一个 GameMemory 实例即可。
"""

from .fact_store import Fact, FactStore
from .episode_log import Episode, EpisodeLog
from .memory import GameMemory
from .retrieval import (
    retrieve_relevant_facts,
    retrieve_relevant_episodes,
    render_facts_block,
    render_episodes_block,
)

__all__ = [
    "Fact",
    "FactStore",
    "Episode",
    "EpisodeLog",
    "GameMemory",
    "retrieve_relevant_facts",
    "retrieve_relevant_episodes",
    "render_facts_block",
    "render_episodes_block",
]
