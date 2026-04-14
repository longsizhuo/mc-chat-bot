#!/bin/bash
# Dump the Minecraft block/item registry directly from the server jar.
# Re-run this after a Minecraft version bump so [CMD:find] stays accurate.
#
# Usage: ./scripts/dump_registry.sh [server_dir] [java_bin]

set -euo pipefail

SERVER_DIR="${1:-/home/ubuntu/minecraft-server}"
JAVA_BIN="${2:-/home/ubuntu/.sdkman/candidates/java/25.0.2-graal/bin/java}"
JAR="${SERVER_DIR}/server.jar"
OUT_DIR="$(cd "$(dirname "$0")/.." && pwd)/data"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

if [ ! -f "$JAR" ]; then
  echo "server.jar not found at $JAR" >&2
  exit 1
fi

echo "Dumping registry from $JAR ..."
cd "$TMP"
"$JAVA_BIN" -DbundlerMainClass=net.minecraft.data.Main -jar "$JAR" --reports >/dev/null

REG="$TMP/generated/reports/registries.json"
[ -f "$REG" ] || { echo "registries.json missing" >&2; exit 1; }

python3 - "$REG" "$OUT_DIR/registry.json" << 'PY'
import json, sys
src, dst = sys.argv[1], sys.argv[2]
d = json.load(open(src))
# Guess the MC version from the containing dir name, fallback "unknown"
out = {
    "version": "unknown",
    "items": sorted(k.replace("minecraft:", "") for k in d["minecraft:item"]["entries"].keys()),
    "blocks": sorted(k.replace("minecraft:", "") for k in d["minecraft:block"]["entries"].keys()),
}
json.dump(out, open(dst, "w"), ensure_ascii=False, indent=2)
print(f"Wrote {dst}: items={len(out['items'])} blocks={len(out['blocks'])}")
PY
