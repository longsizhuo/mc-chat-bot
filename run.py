#!/usr/bin/env python3
"""MCBot - Minecraft AI Chat Bot with RCON skills."""

import argparse
import threading
import sys

from mcbot.config import load_config
from mcbot.bot import ChatBot
from mcbot.backup import DayBackup


def main():
    parser = argparse.ArgumentParser(description="MCBot - Minecraft AI Chat Bot")
    parser.add_argument(
        "-c", "--config",
        default="config.yml",
        help="Path to config file (default: config.yml)",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Disable automatic backup",
    )
    parser.add_argument(
        "--backup-only",
        action="store_true",
        help="Run backup system only (no chat bot)",
    )
    args = parser.parse_args()

    config = load_config(args.config)

    if args.backup_only:
        backup = DayBackup(config)
        backup.run()
        return

    # Start backup in background thread
    if config.backup.enabled and not args.no_backup:
        backup = DayBackup(config)
        backup_thread = threading.Thread(target=backup.run, daemon=True)
        backup_thread.start()
        print("[MCBot] Backup system running in background")

    # Start chat bot (main thread)
    bot = ChatBot(config)
    bot.run()


if __name__ == "__main__":
    main()
