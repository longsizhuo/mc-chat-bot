# MCBot Configuration Reference

All options for `config.yml`.

## Top-level

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `server_dir` | string | `"."` | Path to Minecraft server directory |
| `log_file` | string | `"logs/latest.log"` | Relative path to server log file |

## `ai` section

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `provider` | string | `"deepseek"` | AI provider: `deepseek`, `openai`, `anthropic`, `ollama`, `custom` |
| `api_key` | string | `""` | API key (not needed for `ollama`) |
| `base_url` | string | auto | API base URL (auto-filled per provider) |
| `model` | string | auto | Model name (auto-filled per provider) |
| `temperature` | float | `0.8` | Response randomness (0.0-1.0) |
| `max_tokens` | int | `200` | Max tokens per reply |

### Provider defaults

| Provider | `base_url` | `model` |
|----------|-----------|---------|
| `deepseek` | `https://api.deepseek.com` | `deepseek-chat` |
| `openai` | `https://api.openai.com/v1` | `gpt-4o-mini` |
| `anthropic` | `https://api.anthropic.com` | `claude-sonnet-4-20250514` |
| `ollama` | `http://localhost:11434/v1` | `llama3` |

## `rcon` section

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `host` | string | `"localhost"` | RCON host |
| `port` | int | `25575` | RCON port |
| `password` | string | `""` | RCON password (must match `server.properties`) |

## `bot` section

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `name` | string | `"MCBot"` | Bot display name in chat |
| `language` | string | `"zh"` | Language: `zh` (Chinese) or `en` (English) |
| `max_reply_length` | int | `60` | Max characters per reply |
| `max_history` | int | `20` | Chat history per player |
| `system_prompt` | string | `""` | Extra instructions appended to system prompt |

## `events` section

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `player_join` | bool | `true` | Send welcome message on join |
| `player_death` | bool | `true` | Send roast message on death |
| `player_afk` | bool | `true` | Detect and warn AFK players |
| `afk_timeout` | int | `300` | Seconds before player is considered AFK |

## `backup` section

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | bool | `true` | Enable game-day backup |
| `check_interval` | int | `60` | Seconds between day checks |
| `max_backups` | int | `10` | Max backups to keep |
| `backup_dir` | string | `"backups"` | Backup directory (relative to `server_dir`) |
