#!/usr/bin/env python3
import json
import os
import re
import sys

# Mapping tool keys to metadata
TOOL_METADATA = {
    "chdman": {
        "license": "GPL-2.0-or-later OR BSD-3-Clause",
        "upstream_repo": "https://github.com/mamedev/mame",
        "provenance": "npm-package",
        "npm_package": "@emmercm/chdman-*"
    },
    "maxcso": {
        "license": "ISC",
        "upstream_repo": "https://github.com/unknownbrackets/maxcso",
        "provenance": "upstream-release"
    },
    "ecm": {
        "license": "GPL-2.0-only",
        "upstream_repo": "https://github.com/kidoz/ecm",
        "provenance": "upstream-release"
    },
    "unecm": {
        "license": "GPL-2.0-only",
        "upstream_repo": "https://github.com/kidoz/ecm",
        "provenance": "upstream-release"
    },
    "xdelta3": {
        "license": "Apache-2.0",
        "upstream_repo": "https://github.com/jmacd/xdelta",
        "provenance": "upstream-release"
    },
    "nodtool": {
        "license": "MIT OR Apache-2.0",
        "upstream_repo": "https://github.com/encounter/nod",
        "provenance": "upstream-release"
    },
    "extract-xiso": {
        "license": "BSD-4-Clause",
        "upstream_repo": "https://github.com/XboxDev/extract-xiso",
        "provenance": "upstream-release"
    },
    "nkit": {
        "license": "MIT",
        "upstream_repo": "https://github.com/Nanook/NKit",
        "provenance": "built-from-source",
        "build_flavor": "legacy-unknown"
    },
    "saturn-patcher": {
        "license": "GPL-3.0-or-later",
        "upstream_repo": "https://github.com/M5Devs/saturn-patcher",
        "provenance": "built-from-source"
    },
    "xgdtool": {
        "license": "GPL-3.0-only",
        "upstream_repo": "https://github.com/wiredopposite/XGDTool",
        "provenance": "built-from-source"
    }
}

def parse_checksums(filepath):
    entries = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(None, 1)
            if len(parts) == 2:
                sha256, path = parts[0], parts[1]
                entries.append((sha256, path))
    return entries

def main():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    checksums_path = os.path.join(repo_root, "checksums.sha256")
    versions_path = os.path.join(repo_root, "versions.json")
    recon_path = os.path.join(repo_root, "recon_sourceforge_status.json")

    with open(versions_path, "r", encoding="utf-8") as f:
        versions = json.load(f)

    sf_status = {}
    if os.path.exists(recon_path):
        with open(recon_path, "r", encoding="utf-8") as f:
            sf_status = json.load(f)

    checksum_entries = parse_checksums(checksums_path)

    manifest_tools = {}

    for sha256, rel_path in checksum_entries:
        # e.g., android/arm64-v8a/chdman or windows/x86_64/XGDTool.exe
        parts = rel_path.split("/")
        if len(parts) != 3:
            print(f"Skipping unusual path: {rel_path}", file=sys.stderr)
            continue

        os_name, arch_name, filename = parts
        platform_key = f"{os_name}/{arch_name}"

        # Identify tool key
        tool_key = filename
        if filename.endswith(".exe"):
            tool_key = filename[:-4]
        tool_key_lower = tool_key.lower()

        if tool_key_lower not in versions and tool_key_lower not in TOOL_METADATA:
            print(f"Unknown tool for path: {rel_path}", file=sys.stderr)
            continue

        tool_canonical = tool_key_lower
        if tool_canonical not in manifest_tools:
            meta = TOOL_METADATA.get(tool_canonical, {})
            manifest_tools[tool_canonical] = {
                "version": versions.get(tool_canonical, "0.0.0"),
                "license": meta.get("license", "UNKNOWN"),
                "upstream_repo": meta.get("upstream_repo", "https://github.com/M5Devs"),
                "provenance": meta.get("provenance", "upstream-release"),
                "platforms": {}
            }
            if "build_flavor" in meta:
                manifest_tools[tool_canonical]["build_flavor"] = meta["build_flavor"]
            if "npm_package" in meta:
                manifest_tools[tool_canonical]["npm_package"] = meta["npm_package"]

        # Platform details
        size = 0
        if rel_path in sf_status and "size" in sf_status[rel_path]:
            size = sf_status[rel_path]["size"]
        elif rel_path == "windows/x86_64/XGDTool.exe":
            size = 6411776

        plat_entry = {
            "path": rel_path,
            "sha256": sha256,
            "size": size,
            "executable": True,
            "status": "ok"
        }

        # Handle universal / same_as annotations
        if os_name == "macos" and filename in ["extract-xiso", "xdelta3"]:
            plat_entry["universal"] = True

        if os_name == "android":
            # android bins matching linux/arm64
            if filename in ["chdman", "ecm", "nkit", "unecm"]:
                plat_entry["same_as"] = f"linux/arm64/{filename}"
            if filename == "xdelta3":
                plat_entry["version"] = "3.2.2"

        manifest_tools[tool_canonical]["platforms"][platform_key] = plat_entry

    # Sort tools alphabetically
    sorted_tools = dict(sorted(manifest_tools.items()))

    manifest = {
        "format_version": 1,
        "tools": sorted_tools
    }

    out_manifest_path = os.path.join(repo_root, "manifest.json")
    with open(out_manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")

    print(f"Successfully created manifest.json with {len(sorted_tools)} tools.")

if __name__ == "__main__":
    main()
