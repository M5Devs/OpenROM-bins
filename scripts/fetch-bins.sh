#!/usr/bin/env bash
# fetch-bins.sh - Download and verify OpenROM binaries from SourceForge/Base URL
# Exit codes:
#   0 - Success
#   1 - Invalid arguments or missing dependency
#   2 - Manifest or checksum error / tool not found
#   3 - Download failed (HTTP 404 / connection error)
#   4 - SHA-256 or size verification mismatch

set -euo pipefail

BASE_URL="${OPENROM_BINS_BASE_URL:-https://downloads.sourceforge.net/project/openrom-binaries}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MANIFEST_PATH="$REPO_ROOT/manifest.json"
TARGET_DIR="."
OS=""
ARCH=""
TOOL=""

usage() {
    echo "Usage: $0 [--os <os>] [--arch <arch>] [--tool <tool>] [--target-dir <dir>]"
    echo "Examples:"
    echo "  $0 --os linux --arch x86_64 --target-dir ./bin"
    echo "  $0 --tool chdman --os windows --arch x86_64"
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --os) OS="$2"; shift 2 ;;
        --arch) ARCH="$2"; shift 2 ;;
        --tool) TOOL="$2"; shift 2 ;;
        --target-dir) TARGET_DIR="$2"; shift 2 ;;
        -h|--help) usage ;;
        *) echo "Unknown option: $1" >&2; usage ;;
    esac
done

if [ ! -f "$MANIFEST_PATH" ]; then
    echo "Error: manifest.json not found at $MANIFEST_PATH" >&2
    exit 2
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "Error: python3 is required" >&2
    exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
    echo "Error: curl is required" >&2
    exit 1
fi

ENTRIES_JSON=$(python3 -c '
import json, sys

manifest_path, os_filter, arch_filter, tool_filter = sys.argv[1:]
with open(manifest_path, "r", encoding="utf-8") as f:
    manifest = json.load(f)

matched = []
for tool_name, tool_data in manifest.get("tools", {}).items():
    if tool_filter and tool_name.lower() != tool_filter.lower():
        continue
    platforms = tool_data.get("platforms", {})
    for plat_key, plat_data in platforms.items():
        plat_os, plat_arch = plat_key.split("/") if "/" in plat_key else (plat_key, "")
        if os_filter and plat_os.lower() != os_filter.lower():
            continue
        if arch_filter and plat_arch.lower() != arch_filter.lower():
            continue
        matched.append({
            "tool": tool_name,
            "platform": plat_key,
            "path": plat_data["path"],
            "sha256": plat_data["sha256"],
            "size": plat_data.get("size", 0)
        })

print(json.dumps(matched))
' "$MANIFEST_PATH" "$OS" "$ARCH" "$TOOL")

NUM_MATCHES=$(python3 -c "import json, sys; print(len(json.loads(sys.argv[1])))" "$ENTRIES_JSON")

if [ "$NUM_MATCHES" -eq 0 ]; then
    echo "No binaries found matching constraints (os=, arch=, tool=)" >&2
    exit 2
fi

echo "Fetching $NUM_MATCHES binary/binaries to target directory: $TARGET_DIR"

mkdir -p "$TARGET_DIR"

compute_sha256() {
    local file="$1"
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$file" | awk '{print $1}'
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$file" | awk '{print $1}'
    else
        python3 -c "import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], 'rb').read()).hexdigest())" "$file"
    fi
}

lines=$(python3 -c '
import json, sys
data = json.loads(sys.argv[1])
for item in data:
    p, s, z = item["path"], item["sha256"], item["size"]
    print(f"{p}|{s}|{z}")
' "$ENTRIES_JSON")

while IFS="|" read -r rel_path exp_sha exp_size; do
    [ -z "$rel_path" ] && continue
    url="$BASE_URL/$rel_path"
    filename=$(basename "$rel_path")
    out_file="$TARGET_DIR/$filename"

    echo "Downloading $rel_path -> $out_file ..."
    if ! curl --retry 5 -fL "$url" -o "$out_file"; then
        echo "Error downloading $url (HTTP 404 or network failure)" >&2
        exit 3
    fi

    act_sha=$(compute_sha256 "$out_file")
    act_size=$(python3 -c "import os, sys; print(os.path.getsize(sys.argv[1]))" "$out_file")

    if [ "$act_sha" != "$exp_sha" ]; then
        echo "SHA-256 mismatch for $rel_path!" >&2
        echo "  Expected: $exp_sha" >&2
        echo "  Actual:   $act_sha" >&2
        rm -f "$out_file"
        exit 4
    fi

    if [ "$exp_size" -gt 0 ] && [ "$act_size" -ne "$exp_size" ]; then
        echo "Size mismatch for $rel_path!" >&2
        echo "  Expected: $exp_size bytes" >&2
        echo "  Actual:   $act_size bytes" >&2
        rm -f "$out_file"
        exit 4
    fi

    if [ "$(uname -s 2>/dev/null)" != "Windows_NT" ]; then
        chmod +x "$out_file"
    fi

    echo "Verified $filename successfully."
done <<< "$lines"
