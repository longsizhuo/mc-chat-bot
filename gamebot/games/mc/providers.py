"""向后兼容入口 —— AIProvider 已迁移到 gamebot/core/ai_provider.py（refactor phase 2）。"""

from gamebot.core.ai_provider import AIProvider, AIConfig

__all__ = ["AIProvider", "AIConfig"]
