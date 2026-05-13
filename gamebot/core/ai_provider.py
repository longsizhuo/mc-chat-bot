"""通用 LLM provider 抽象 —— OpenAI 兼容 API（DeepSeek/Anthropic/Ollama 等）。

core 层组件，平台无关。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from openai import OpenAI


# OpenAI SDK 默认无超时——一旦上游卡住整个 bot 跟着挂死，群里看起来"静默失败"
# 30 秒是 LLM 平均响应的 5-10 倍，足以给慢请求留余地又能保证卡住时及时报错
DEFAULT_TIMEOUT_SECONDS = 30.0


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

    def __init__(self, config: AIConfig, timeout: float = DEFAULT_TIMEOUT_SECONDS):
        self.config = config
        self.timeout = timeout
        self.client = OpenAI(
            api_key=config.api_key or "ollama",
            base_url=config.base_url,
            timeout=timeout,  # 关键：防止 LLM 上游挂死时 bot 永久阻塞
        )

    def chat(self, messages: list[dict], system_prompt: str) -> Optional[str]:
        """发对话，返回助手回复。失败返回 None（已打详细日志）。"""
        full_messages = [{"role": "system", "content": system_prompt}] + messages
        prompt_chars = sum(len(m.get("content", "")) for m in full_messages)

        t0 = time.time()
        print(
            f"[AIProvider] → {self.config.model} "
            f"({len(full_messages)} msgs, ~{prompt_chars} chars in)"
        )
        try:
            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=full_messages,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                timeout=self.timeout,
            )
        except Exception as e:
            elapsed = time.time() - t0
            print(
                f"[AIProvider] ✗ FAIL after {elapsed:.1f}s: "
                f"{type(e).__name__}: {str(e)[:200]}"
            )
            return None

        elapsed = time.time() - t0
        try:
            content = response.choices[0].message.content
        except (AttributeError, IndexError) as e:
            print(
                f"[AIProvider] ✗ response shape unexpected after {elapsed:.1f}s: "
                f"{type(e).__name__}: {e}"
            )
            return None

        if content is None:
            # reasoning model 把 tokens 全花在 reasoning_content，content 为空
            reasoning = getattr(response.choices[0].message, "reasoning_content", "")
            usage = getattr(response, "usage", None)
            print(
                f"[AIProvider] ✗ empty content after {elapsed:.1f}s "
                f"(可能 max_tokens 太小，reasoning 吃光了): "
                f"reasoning={len(reasoning) if reasoning else 0} chars, usage={usage}"
            )
            return None

        text = content.strip()
        print(f"[AIProvider] ✓ {elapsed:.1f}s, {len(text)} chars out")
        return text
