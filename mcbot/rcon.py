"""Minecraft RCON client using mcrcon CLI."""

import subprocess
from typing import Optional

from .config import RCONConfig


class RCON:
    """RCON client wrapper around mcrcon CLI."""

    def __init__(self, config: RCONConfig):
        self.config = config

    def send(self, command: str) -> Optional[str]:
        """Send a command via RCON and return the response."""
        try:
            result = subprocess.run(
                [
                    "mcrcon",
                    "-H", self.config.host,
                    "-P", str(self.config.port),
                    "-p", self.config.password,
                    command,
                ],
                capture_output=True, text=True, timeout=5,
            )
            return result.stdout.strip()
        except FileNotFoundError:
            print("[MCBot] Error: mcrcon not found. Install it first.")
            print("[MCBot]   git clone https://github.com/Tiiffi/mcrcon.git")
            print("[MCBot]   cd mcrcon && gcc -o mcrcon mcrcon.c && sudo cp mcrcon /usr/local/bin/")
            return None
        except Exception as e:
            print(f"[MCBot] RCON error: {e}")
            return None

    def say(self, name: str, message: str):
        """Send a chat message to the server."""
        for line in message.split("\n"):
            line = line.strip()
            if line:
                self.send(f"say [{name}] {line}")
