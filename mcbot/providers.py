"""AI provider abstraction layer."""

from typing import Optional

from openai import OpenAI

from .config import AIConfig


class AIProvider:
    """Unified AI provider using OpenAI-compatible API."""

    def __init__(self, config: AIConfig):
        self.config = config
        self.client = OpenAI(
            api_key=config.api_key or "ollama",
            base_url=config.base_url,
        )

    def chat(self, messages: list[dict], system_prompt: str) -> Optional[str]:
        """Send chat messages and get a reply."""
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
            print(f"[MCBot] AI API error: {e}")
            return None
