#!/usr/bin/env python3
"""Validate the publish-sourceforge workflow inputs before any side effect.

Inputs are read only from environment variables so no workflow expression is
ever interpolated into a shell command. Exits non-zero on the first violation.
"""
import json
import os
import re
import sys

ALLOWED_OS = {"windows", "linux", "macos", "android"}
ALLOWED_ARCH = {"x86_64", "arm64", "arm64-v8a"}
ALLOWED_COMBOS = {
    ("windows", "x86_64"),
    ("linux", "x86_64"),
    ("linux", "arm64"),
    ("macos", "x86_64"),
    ("macos", "arm64"),
    ("android", "arm64-v8a"),
}

RE_TOOL = re.compile(r"[a-z0-9-]{1,40}")
RE_ARTIFACT = re.compile(r"[A-Za-z0-9._-]{1,100}")
RE_VERSION = re.compile(r"[A-Za-z0-9._+-]{1,64}")
RE_SOURCE_REF = re.compile(r"[A-Za-z0-9._/-]{1,128}")
RE_SOURCE_COMMIT = re.compile(r"[0-9a-fA-F]{40}")
RE_TOOLCHAIN = re.compile(r"[A-Za-z0-9 ._()+/,:=-]{0,160}")
RE_BUILD_FLAVOR = re.compile(r"[a-z0-9-]{0,32}")


class InputError(Exception):
    pass


def _check_no_control(name, value):
    for bad in ("\x00", "\n", "\r"):
        if bad in value:
            raise InputError(f"{name} contains a forbidden control character")


def _check_regex(name, value, regex, label):
    if not regex.fullmatch(value):
        raise InputError(f"Invalid {name}: {value!r} (must match {label})")


def load_manifest_tools():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    manifest_path = os.path.join(repo_root, "manifest.json")
    if not os.path.exists(manifest_path):
        raise InputError(f"manifest.json not found at {manifest_path}")
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    return manifest.get("tools", {})


def validate(env):
    os_val = env.get("IN_OS", "")
    arch_val = env.get("IN_ARCH", "")
    tool_val = env.get("IN_TOOL", "")
    artifact_val = env.get("IN_ARTIFACT", "")
    version_val = env.get("IN_VERSION", "")
    source_ref_val = env.get("IN_SOURCE_REF", "")
    source_commit_val = env.get("IN_SOURCE_COMMIT", "")
    toolchain_val = env.get("IN_TOOLCHAIN", "")
    build_flavor_val = env.get("IN_BUILD_FLAVOR", "")
    dry_run_val = env.get("IN_DRY_RUN", "")

    for name, value in [
        ("os", os_val),
        ("arch", arch_val),
        ("tool", tool_val),
        ("artifact_name", artifact_val),
        ("version", version_val),
        ("source_ref", source_ref_val),
        ("source_commit", source_commit_val),
        ("toolchain", toolchain_val),
        ("build_flavor", build_flavor_val),
        ("dry_run", dry_run_val),
    ]:
        _check_no_control(name, value)

    if os_val not in ALLOWED_OS:
        raise InputError(f"Invalid os: {os_val!r}")
    if arch_val not in ALLOWED_ARCH:
        raise InputError(f"Invalid arch: {arch_val!r}")
    if (os_val, arch_val) not in ALLOWED_COMBOS:
        raise InputError(f"Unsupported os/arch combination: {os_val}/{arch_val}")

    _check_regex("tool", tool_val, RE_TOOL, "^[a-z0-9-]{1,40}$")
    tools = load_manifest_tools()
    if tool_val not in tools:
        raise InputError(f"Tool {tool_val!r} is not present in manifest.json")

    _check_regex("artifact_name", artifact_val, RE_ARTIFACT, "^[A-Za-z0-9._-]{1,100}$")

    if version_val:
        _check_regex("version", version_val, RE_VERSION, "^[A-Za-z0-9._+-]{1,64}$")
    if source_ref_val:
        _check_regex("source_ref", source_ref_val, RE_SOURCE_REF, "^[A-Za-z0-9._/-]{1,128}$")
    if source_commit_val:
        _check_regex("source_commit", source_commit_val, RE_SOURCE_COMMIT, "^[0-9a-fA-F]{40}$")
    _check_regex("toolchain", toolchain_val, RE_TOOLCHAIN, "^[A-Za-z0-9 ._()+/,:=-]{0,160}$")
    _check_regex("build_flavor", build_flavor_val, RE_BUILD_FLAVOR, "^[a-z0-9-]{0,32}$")

    if dry_run_val not in ("true", "false"):
        raise InputError(f"Invalid dry_run: {dry_run_val!r} (must be 'true' or 'false')")


def main():
    try:
        validate(os.environ)
    except InputError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        sys.exit(1)
    print("Inputs validated successfully.")


if __name__ == "__main__":
    main()
