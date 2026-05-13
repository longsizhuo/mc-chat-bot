"""通用 LLM provider 抽象 —— OpenAI 兼容 API（DeepSeek/Anthropic/Ollama 等）。

core 层组件，平台无关。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from openai import OpenAI


# 各 provider 默认参数
_PROVIDER_DEFAULTS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com/v1",
        "model": "claude-3-5-sonnet-20241022",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "model": "llama3",
    },
    "custom": {},
}


@dataclass
class AIConfig:
    """LLM 调用配置。"""
    provider: str = "deepseek"      # deepseek / openai / anthropic / ollama / custom
    api_key: str = ""
    base_url: str = ""              # 留空走 provider 默认
    model: str = ""                 # 留空走 provider 默认
    temperature: float = 0.8
    max_tokens: int = 200

    def resolve(self) -> None:
        """填充 provider 默认值（base_url / model）。"""
        defaults = _PROVIDER_DEFAULTS.get(self.provider, {})
        if not self.base_url:
            self.base_url = defaults.get("base_url", "")
        if not self.model:
            self.model = defaults.get("model", "")


class AIProvider:
    """OpenAI 兼容 API 客户端，所有支持 OpenAI 协议的 LLM 都能用。"""

    def __init__(self, config: AIConfig):
        self.config = config
        self.client = OpenAI(
            api_key=config.api_key or "ollama",
            base_url=config.base_url,
        )

    def chat(self, messages: list[dict], system_prompt: str) -> Optional[str]:
        """发对话，返回助手回复。失败返回 None。"""
        try:
            full_messages = [{"role": "system", "content": system_prompt}] + messages
            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=full_messages,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"[AIProvider] error: {e}")
            return None
