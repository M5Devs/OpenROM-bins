#!/usr/bin/env python3
import argparse
import json
import os
import sys
import subprocess

def main():
    parser = argparse.ArgumentParser(description="Update manifest.json entry and regenerate checksums")
    parser.add_argument("--tool", required=True, help="Canonical tool key (e.g., chdman, nkit)")
    parser.add_argument("--os", required=True, help="Target OS (e.g., linux, windows, macos, android)")
    parser.add_argument("--arch", required=True, help="Target Arch (e.g., x86_64, arm64, arm64-v8a)")
    parser.add_argument("--file-path", required=True, help="Relative path of the binary (e.g., linux/x86_64/nkit)")
    parser.add_argument("--sha256", required=True, help="Computed SHA-256 hash")
    parser.add_argument("--size", type=int, required=True, help="File size in bytes")
    parser.add_argument("--version", help="Tool version")
    parser.add_argument("--source-ref", help="Upstream tag or ref")
    parser.add_argument("--source-commit", help="40-char git commit SHA")
    parser.add_argument("--built-at", help="ISO timestamp of build")
    parser.add_argument("--workflow-run-url", help="GitHub Actions run URL")
    parser.add_argument("--toolchain", help="Compiler / toolchain version used")
    parser.add_argument("--build-flavor", help="Build flavor e.g. nativeaot")

    args = parser.parse_args()

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    manifest_path = os.path.join(repo_root, "manifest.json")

    if not os.path.exists(manifest_path):
        print(f"Error: manifest.json not found at {manifest_path}", file=sys.stderr)
        sys.exit(1)

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    tool_key = args.tool.lower()
    platform_key = f"{args.os}/{args.arch}"

    tools = manifest.setdefault("tools", {})
    if tool_key not in tools:
        print(f"Error: Tool '{tool_key}' not present in manifest.json", file=sys.stderr)
        sys.exit(1)

    tool_data = tools[tool_key]

    if args.version:
        tool_data["version"] = args.version
    if args.source_ref:
        tool_data["source_ref"] = args.source_ref
    if args.source_commit:
        tool_data["source_commit"] = args.source_commit
    if args.built_at:
        tool_data["built_at"] = args.built_at
    if args.workflow_run_url:
        tool_data["workflow_run_url"] = args.workflow_run_url
    if args.toolchain:
        tool_data["toolchain"] = args.toolchain
    if args.build_flavor:
        tool_data["build_flavor"] = args.build_flavor

    platforms = tool_data.setdefault("platforms", {})
    plat_entry = platforms.get(platform_key, {})

    plat_entry["path"] = args.file_path
    plat_entry["sha256"] = args.sha256
    plat_entry["size"] = args.size
    plat_entry["executable"] = True
    plat_entry["status"] = "ok"

    platforms[platform_key] = plat_entry

    # Save manifest.json
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")

    # Regenerate checksums.sha256 and versions.json
    gen_script = os.path.join(repo_root, "scripts", "gen_checksums.py")
    subprocess.check_call([sys.executable, gen_script])

    print(f"Updated manifest entry for {tool_key} ({platform_key}) successfully.")

if __name__ == "__main__":
    main()
