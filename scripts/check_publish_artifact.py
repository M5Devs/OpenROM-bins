#!/usr/bin/env python3
"""Verify the downloaded artifact for a publish run.

Enforces the exactly-one-file rule for every tool, filename character rules,
the nkit and windows filename rules, and consistency with an existing manifest
entry for the same tool and platform. Writes target_file/filename/sha256/size
to GITHUB_OUTPUT and exits non-zero on any violation.
"""
import glob
import hashlib
import json
import os
import re
import sys

ARTIFACT_GLOB = "download_artifact/**"
RE_FILENAME = re.compile(r"[A-Za-z0-9._-]+")


class ArtifactError(Exception):
    pass


def find_files(root=ARTIFACT_GLOB):
    return sorted(
        f for f in glob.glob(root, recursive=True) if os.path.isfile(f)
    )


def load_manifest_entry(tool, os_name, arch_name):
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    manifest_path = os.path.join(repo_root, "manifest.json")
    if not os.path.exists(manifest_path):
        raise ArtifactError(f"manifest.json not found at {manifest_path}")
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    tool_data = manifest.get("tools", {}).get(tool, {})
    return tool_data.get("platforms", {}).get(f"{os_name}/{arch_name}")


def check(files, tool, os_name, arch_name, existing_entry):
    if len(files) != 1:
        raise ArtifactError(
            f"Expected exactly 1 file in the artifact, found {len(files)}: {files}"
        )

    target_file = files[0]
    filename = os.path.basename(target_file)

    if not RE_FILENAME.fullmatch(filename):
        raise ArtifactError(
            f"Artifact filename {filename!r} must match ^[A-Za-z0-9._-]+$"
        )

    if tool == "nkit" and filename not in ("nkit", "nkit.exe"):
        raise ArtifactError(f"NKit binary filename invalid: {filename!r}")

    if os_name == "windows" and not filename.endswith(".exe"):
        raise ArtifactError(f"Windows artifact must end with .exe: {filename!r}")

    if existing_entry is not None:
        expected = os.path.basename(existing_entry.get("path", ""))
        if expected and filename != expected:
            raise ArtifactError(
                f"Artifact filename {filename!r} does not match manifest entry "
                f"basename {expected!r}"
            )

    return target_file, filename


def write_outputs(path, target_file, filename):
    size = os.path.getsize(target_file)
    with open(target_file, "rb") as f:
        sha256 = hashlib.sha256(f.read()).hexdigest()
    with open(path, "a", encoding="utf-8") as out:
        out.write(f"target_file={target_file}\n")
        out.write(f"filename={filename}\n")
        out.write(f"sha256={sha256}\n")
        out.write(f"size={size}\n")
    return sha256, size


def main():
    tool = os.environ.get("TOOL", "")
    os_name = os.environ.get("TARGET_OS", "")
    arch_name = os.environ.get("TARGET_ARCH", "")
    github_output = os.environ.get("GITHUB_OUTPUT")

    try:
        files = find_files()
        for f in files:
            print(f"  {f}: {os.path.getsize(f)} bytes")
        existing_entry = load_manifest_entry(tool, os_name, arch_name)
        target_file, filename = check(files, tool, os_name, arch_name, existing_entry)
    except ArtifactError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        sys.exit(1)

    if github_output:
        sha256, size = write_outputs(github_output, target_file, filename)
    else:
        with open(target_file, "rb") as f:
            sha256 = hashlib.sha256(f.read()).hexdigest()
        size = os.path.getsize(target_file)

    print(f"Artifact OK: {filename} ({size} bytes, sha256={sha256})")


if __name__ == "__main__":
    main()
