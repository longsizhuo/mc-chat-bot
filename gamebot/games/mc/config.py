"""Configuration loading and validation."""

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

# AIConfig 已迁移到 gamebot/core/ai_provider.py（refactor phase 2）
# 这里 re-export 保持向后兼容
from gamebot.core.ai_provider import AIConfig


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
    max_tool_rounds: int = 10
    startup_commands: list = field(default_factory=lambda: ["gamerule keep_inventory true"])


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
    group_id: int = 0          # MC 主群
    ws_port: int = 6101
    extra_group_ids: list = field(default_factory=list)  # 额外监听的群（DF 群等）


@dataclass
class DFStatsConfig:
    """三角洲行动数据桥接配置。"""
    enabled: bool = False
    # 三角洲群号 —— 所有 DF 功能仅限这个群响应
    group_id: int = 0
    # 抓包文件路径（绝对路径或相对于 mc-chat-bot 工作目录）
    secret_curl: str = "scripts/df_stats/credentials/raw_curl_secret.sh"
    # 战绩/角色/赛季 curl（可选，AI 工具用；缺了的工具会优雅失败）
    record_curl: str = "scripts/df_stats/credentials/raw_curl.sh"
    profile_curl: str = "scripts/df_stats/credentials/raw_curl_profile.sh"
    season_curl: str = "scripts/df_stats/credentials/raw_curl_season.sh"
    # 干员别名表（2026-05 已迁移到 GameMemory，此字段保留供向后兼容；新代码看 memory_root）
    aliases_path: str = "data/df_aliases.json"
    # Agent memory 根目录（fact_store + episode_log）
    memory_root: str = "data/memory/df"
    # 每天几点广播今日密码（CST，0-23）
    broadcast_hour: int = 6
    # 是否启用 AI 闲聊 + 工具调用
    enable_ai: bool = True


@dataclass
class Config:
    ai: AIConfig = field(default_factory=AIConfig)
    rcon: RCONConfig = field(default_factory=RCONConfig)
    bot: BotConfig = field(default_factory=BotConfig)
    events: EventsConfig = field(default_factory=EventsConfig)
    backup: BackupConfig = field(default_factory=BackupConfig)
    qq: QQConfig = field(default_factory=QQConfig)
    df_stats: DFStatsConfig = field(default_factory=DFStatsConfig)
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
        max_tool_rounds=b.get("max_tool_rounds", 10),
        startup_commands=b.get("startup_commands", ["gamerule keep_inventory true"]),
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
        extra_group_ids=list(qq.get("extra_group_ids", []) or []),
    )

    # DFStats Bridge（三角洲行动数据桥接）
    dfs = raw.get("df_stats", {})
    config.df_stats = DFStatsConfig(
        enabled=dfs.get("enabled", False),
        group_id=dfs.get("group_id", 0),
        secret_curl=dfs.get("secret_curl", "scripts/df_stats/credentials/raw_curl_secret.sh"),
        record_curl=dfs.get("record_curl", "scripts/df_stats/credentials/raw_curl.sh"),
        profile_curl=dfs.get("profile_curl", "scripts/df_stats/credentials/raw_curl_profile.sh"),
        season_curl=dfs.get("season_curl", "scripts/df_stats/credentials/raw_curl_season.sh"),
        aliases_path=dfs.get("aliases_path", "data/df_aliases.json"),
        memory_root=dfs.get("memory_root", "data/memory/df"),
        broadcast_hour=dfs.get("broadcast_hour", 6),
        enable_ai=dfs.get("enable_ai", True),
    )

    # DF 群自动加进 QQ 监听列表（如果用户没显式加）
    if config.df_stats.enabled and config.df_stats.group_id:
        if config.df_stats.group_id not in config.qq.extra_group_ids:
            config.qq.extra_group_ids.append(config.df_stats.group_id)

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
