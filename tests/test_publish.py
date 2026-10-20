import json
import os
import re
import shutil
import subprocess
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST_PATH = os.path.join(REPO_ROOT, "manifest.json")
CHECKSUMS_PATH = os.path.join(REPO_ROOT, "checksums.sha256")
VERSIONS_PATH = os.path.join(REPO_ROOT, "versions.json")

def test_update_manifest_entry_script(tmp_path):
    # Copy repo files into isolated tmp_path
    tmp_repo = tmp_path / "repo"
    tmp_repo.mkdir()

    shutil.copy(MANIFEST_PATH, tmp_repo / "manifest.json")
    shutil.copy(CHECKSUMS_PATH, tmp_repo / "checksums.sha256")
    shutil.copy(VERSIONS_PATH, tmp_repo / "versions.json")

    scripts_dir = tmp_repo / "scripts"
    scripts_dir.mkdir()
    shutil.copy(os.path.join(REPO_ROOT, "scripts", "update_manifest_entry.py"), scripts_dir / "update_manifest_entry.py")
    shutil.copy(os.path.join(REPO_ROOT, "scripts", "gen_checksums.py"), scripts_dir / "gen_checksums.py")

    dummy_sha = "1" * 64

    cmd = [
        "python3", str(scripts_dir / "update_manifest_entry.py"),
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

    res = subprocess.run(cmd, cwd=tmp_repo, capture_output=True, text=True)
    assert res.returncode == 0, f"update_manifest_entry.py failed: {res.stderr}"

    with open(tmp_repo / "manifest.json", "r", encoding="utf-8") as f:
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
