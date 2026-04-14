# Maintainer Notes

## Every push must add a CHANGELOG entry

Before `git push`, append one line to `CHANGELOG.md` under today's date heading (create the heading if it's the first push of the day). Format:

```
- **`<short-sha>` <type>**: one-sentence what + why.
```

The `<short-sha>` is the sha of the commit that **introduced the change** — write it in, commit the CHANGELOG entry in a follow-up commit, then push both. Do NOT try to self-reference the same commit's own sha (amending to fix it creates a chase; each amend changes the sha).

Type: `feat` (new capability), `fix` (bug), `docs` (README/prompt/docs),
`chore` (tooling/config), `refactor` (no behavior change).

If several commits go out in one push, list them as separate lines (newest on top within the date).

## Registry refresh

After any Minecraft server version bump, regenerate the ID list:

```bash
./scripts/dump_registry.sh
```

This rewrites `data/registry.json` so `[CMD:find]` stays accurate. Commit and log it under `chore`.

## Restart after prompt or ability changes

`mcbot/abilities.py` and `mcbot/bot.py` are loaded at process start. After editing either:

```bash
sudo systemctl restart mc-chatbot.service
```

Config-only changes (`config.yml`) also need a restart.
