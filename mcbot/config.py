"""Configuration loading and validation."""

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class AIConfig:
    provider: str = "deepseek"
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    temperature: float = 0.8
    max_tokens: int = 200

    # Provider defaults
    PROVIDERS = {
        "deepseek": {
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-chat",
        },
        "openai": {
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o-mini",
        },
        "anthropic": {
            "base_url": "https://api.anthropic.com",
            "model": "claude-sonnet-4-20250514",
        },
        "ollama": {
            "base_url": "http://localhost:11434/v1",
            "model": "llama3",
        },
        "custom": {
            "base_url": "",
            "model": "",
        },
    }

    def resolve(self):
        """Fill in defaults based on provider."""
        defaults = self.PROVIDERS.get(self.provider, self.PROVIDERS["custom"])
        if not self.base_url:
            self.base_url = defaults["base_url"]
        if not self.model:
            self.model = defaults["model"]


@dataclass
class RCONConfig:
    host: str = "localhost"
    port: int = 25575
    password: str = ""


@dataclass
class BotConfig:
    name: str = "MCBot"
    language: str = "zh"
    max_reply_length: int = 60
    max_history: int = 20
    system_prompt: str = ""
    memory_dir: str = "memory"
    max_facts: int = 50


@dataclass
class BackupConfig:
    enabled: bool = True
    check_interval: int = 60
    max_backups: int = 10
    backup_dir: str = "backups"


@dataclass
class EventsConfig:
    player_join: bool = True
    player_death: bool = True
    player_afk: bool = True
    afk_timeout: int = 300


@dataclass
class QQConfig:
    enabled: bool = False
    api_url: str = "http://localhost:3000"
    group_id: int = 0
    ws_port: int = 6101


@dataclass
class Config:
    ai: AIConfig = field(default_factory=AIConfig)
    rcon: RCONConfig = field(default_factory=RCONConfig)
    bot: BotConfig = field(default_factory=BotConfig)
    events: EventsConfig = field(default_factory=EventsConfig)
    backup: BackupConfig = field(default_factory=BackupConfig)
    qq: QQConfig = field(default_factory=QQConfig)
    server_dir: str = "."
    log_file: str = "logs/latest.log"


def load_config(path: str) -> Config:
    """Load config from YAML file."""
    config_path = Path(path)
    if not config_path.exists():
        print(f"[MCBot] Config file not found: {path}")
        print(f"[MCBot] Copy config.example.yml to config.yml and edit it.")
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    config = Config()

    # AI
    ai = raw.get("ai", {})
    config.ai = AIConfig(
        provider=ai.get("provider", "deepseek"),
        api_key=ai.get("api_key", ""),
        base_url=ai.get("base_url", ""),
        model=ai.get("model", ""),
        temperature=ai.get("temperature", 0.8),
        max_tokens=ai.get("max_tokens", 200),
    )
    config.ai.resolve()

    # RCON
    r = raw.get("rcon", {})
    config.rcon = RCONConfig(
        host=r.get("host", "localhost"),
        port=r.get("port", 25575),
        password=r.get("password", ""),
    )

    # Bot
    b = raw.get("bot", {})
    config.bot = BotConfig(
        name=b.get("name", "MCBot"),
        language=b.get("language", "zh"),
        max_reply_length=b.get("max_reply_length", 60),
        max_history=b.get("max_history", 20),
        system_prompt=b.get("system_prompt", ""),
        memory_dir=b.get("memory_dir", "memory"),
        max_facts=b.get("max_facts", 50),
    )

    # Backup
    bk = raw.get("backup", {})
    config.backup = BackupConfig(
        enabled=bk.get("enabled", True),
        check_interval=bk.get("check_interval", 60),
        max_backups=bk.get("max_backups", 10),
        backup_dir=bk.get("backup_dir", "backups"),
    )

    # Events
    ev = raw.get("events", {})
    config.events = EventsConfig(
        player_join=ev.get("player_join", True),
        player_death=ev.get("player_death", True),
        player_afk=ev.get("player_afk", True),
        afk_timeout=ev.get("afk_timeout", 300),
    )

    # QQ Bridge
    qq = raw.get("qq", {})
    config.qq = QQConfig(
        enabled=qq.get("enabled", False),
        api_url=qq.get("api_url", "http://localhost:3000"),
        group_id=qq.get("group_id", 0),
        ws_port=qq.get("ws_port", 6101),
    )

    # Server
    config.server_dir = raw.get("server_dir", ".")
    config.log_file = raw.get("log_file", "logs/latest.log")

    # Validation
    if not config.rcon.password:
        print("[MCBot] Warning: RCON password is empty. Set it in config.yml.")

    if config.ai.provider != "ollama" and not config.ai.api_key:
        print("[MCBot] Error: AI api_key is required (except for ollama).")
        sys.exit(1)

    return config
