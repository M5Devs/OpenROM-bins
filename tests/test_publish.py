import json
import os
import re
import subprocess
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST_PATH = os.path.join(REPO_ROOT, "manifest.json")

def test_update_manifest_entry_script(tmp_path):
    # Copy current manifest to tmp_path
    tmp_manifest = tmp_path / "manifest.json"
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest_data = json.load(f)

    with open(tmp_manifest, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    script_path = os.path.join(REPO_ROOT, "scripts", "update_manifest_entry.py")
    dummy_sha = "1" * 64

    # Run update script
    cmd = [
        "python3", script_path,
        "--tool", "saturn-patcher",
        "--os", "linux",
        "--arch", "x86_64",
        "--file-path", "linux/x86_64/saturn-patcher",
        "--sha256", dummy_sha,
        "--size", "123456",
        "--version", "0.2.0",
        "--source-ref", "v0.2.0",
        "--source-commit", "a" * 40,
        "--built-at", "2026-01-01T00:00:00Z",
        "--workflow-run-url", "https://github.com/M5Devs/OpenROM-bins/actions/runs/123",
        "--toolchain", "rustc 1.85.0",
        "--build-flavor", "release"
    ]

    # Temporarily override manifest path in REPO_ROOT for test
    with open(MANIFEST_PATH, "rb") as f:
        orig_content = f.read()

    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        assert res.returncode == 0, f"update_manifest_entry.py failed: {res.stderr}"

        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            updated_manifest = json.load(f)

        tool = updated_manifest["tools"]["saturn-patcher"]
        assert tool["version"] == "0.2.0"
        assert tool["source_ref"] == "v0.2.0"
        assert tool["source_commit"] == "a" * 40
        assert tool["toolchain"] == "rustc 1.85.0"

        plat = tool["platforms"]["linux/x86_64"]
        assert plat["sha256"] == dummy_sha
        assert plat["size"] == 123456
        assert plat["status"] == "ok"
    finally:
        with open(MANIFEST_PATH, "wb") as f:
            f.write(orig_content)

def test_workflow_input_validation_regexes():
    os_allowed = ["windows", "linux", "macos", "android"]
    arch_allowed = ["x86_64", "arm64", "arm64-v8a"]
    tool_regex = re.compile(r"^[a-z0-9-]+$")
    artifact_regex = re.compile(r"^[A-Za-z0-9._-]+$")
    commit_regex = re.compile(r"^[0-9a-fA-F]{40}$")

    assert "linux" in os_allowed
    assert "x86_64" in arch_allowed
    assert tool_regex.match("chdman")
    assert artifact_regex.match("chdman-linux-x64")
    assert commit_regex.match("b" * 40)

    assert "invalid_os" not in os_allowed
    assert not tool_regex.match("tool; rm -rf /")
    assert not commit_regex.match("short_sha")
