#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
import subprocess

# Same patterns as scripts/validate_publish_inputs.py, kept local so this
# script stays self-contained (it is copied standalone into test sandboxes).
RE_SHA256 = re.compile(r"[0-9a-fA-F]{64}")
RE_BASENAME = re.compile(r"[A-Za-z0-9._-]+")
RE_VERSION = re.compile(r"[A-Za-z0-9._+-]{1,64}")
RE_SOURCE_REF = re.compile(r"[A-Za-z0-9._/-]{1,128}")
RE_SOURCE_COMMIT = re.compile(r"[0-9a-fA-F]{40}")
RE_TOOLCHAIN = re.compile(r"[A-Za-z0-9 ._()+/,:=@-]{0,160}")
RE_TOOLCHAIN_DIGIT = re.compile(r"\d")
RE_BUILD_FLAVOR = re.compile(r"[a-z0-9-]{0,32}")


def validate_args(args):
    """Raise SystemExit with a message on the first invalid argument."""
    def fail(msg):
        print(f"Error: {msg}", file=sys.stderr)
        sys.exit(1)

    for name, value in [
        ("sha256", args.sha256),
        ("file-path", args.file_path),
        ("version", args.version or ""),
        ("source-ref", args.source_ref or ""),
        ("source-commit", args.source_commit or ""),
        ("toolchain", args.toolchain or ""),
        ("build-flavor", args.build_flavor or ""),
    ]:
        if "\x00" in value or "\n" in value or "\r" in value:
            fail(f"--{name} contains a forbidden control character")

    if not RE_SHA256.fullmatch(args.sha256):
        fail(f"--sha256 must be 64 hex characters, got {args.sha256!r}")

    if args.size < 1:
        fail(f"--size must be >= 1, got {args.size}")

    parts = args.file_path.split("/")
    if len(parts) != 3:
        fail(f"--file-path must be <os>/<arch>/<basename>, got {args.file_path!r}")
    path_os, path_arch, basename = parts
    if path_os != args.os or path_arch != args.arch:
        fail(
            f"--file-path {args.file_path!r} is inconsistent with "
            f"--os {args.os!r} / --arch {args.arch!r}"
        )
    if not RE_BASENAME.fullmatch(basename):
        fail(f"--file-path basename must match ^[A-Za-z0-9._-]+$, got {basename!r}")

    if args.version and not RE_VERSION.fullmatch(args.version):
        fail(f"Invalid --version: {args.version!r}")
    if args.source_ref and not RE_SOURCE_REF.fullmatch(args.source_ref):
        fail(f"Invalid --source-ref: {args.source_ref!r}")
    if args.source_commit and not RE_SOURCE_COMMIT.fullmatch(args.source_commit):
        fail(f"Invalid --source-commit: {args.source_commit!r}")
    if args.toolchain and not RE_TOOLCHAIN.fullmatch(args.toolchain):
        fail(f"Invalid --toolchain: {args.toolchain!r}")
    if args.toolchain and not RE_TOOLCHAIN_DIGIT.search(args.toolchain):
        fail(f"Invalid --toolchain: {args.toolchain!r} (must name a concrete version)")
    if args.build_flavor and not RE_BUILD_FLAVOR.fullmatch(args.build_flavor):
        fail(f"Invalid --build-flavor: {args.build_flavor!r}")

    return basename


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

    basename = validate_args(args)

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

    if plat_entry.get("path"):
        existing_basename = os.path.basename(plat_entry["path"])
        if existing_basename != basename:
            print(
                f"Error: existing manifest entry {platform_key} has basename "
                f"{existing_basename!r}, but the new file is {basename!r}",
                file=sys.stderr,
            )
            sys.exit(1)

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
