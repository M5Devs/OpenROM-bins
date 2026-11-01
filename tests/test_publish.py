import json
import os
import re
import shutil
import subprocess
import importlib.util
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


# ---------------------------------------------------------------------------
# validate_publish_inputs.py
# ---------------------------------------------------------------------------

SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
VALIDATOR = os.path.join(SCRIPTS_DIR, "validate_publish_inputs.py")
ARTIFACT_CHECKER = os.path.join(SCRIPTS_DIR, "check_publish_artifact.py")
UPDATE_ENTRY = os.path.join(SCRIPTS_DIR, "update_manifest_entry.py")


def _run_validator(**overrides):
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("IN_"):
            del env[key]
    env.update(overrides)
    return subprocess.run(
        ["python3", VALIDATOR], capture_output=True, text=True, env=env
    )


def _valid_inputs(**overrides):
    base = {
        "IN_OS": "linux",
        "IN_ARCH": "x86_64",
        "IN_TOOL": "chdman",
        "IN_ARTIFACT": "chdman-linux-x86_64",
        "IN_DRY_RUN": "true",
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize(
    "overrides",
    [
        {"IN_OS": "windows", "IN_ARCH": "x86_64", "IN_TOOL": "nkit",
         "IN_ARTIFACT": "nkit-windows-x86_64"},
        {"IN_OS": "linux", "IN_ARCH": "arm64", "IN_TOOL": "saturn-patcher",
         "IN_ARTIFACT": "saturn-patcher-linux-arm64"},
        {"IN_OS": "android", "IN_ARCH": "arm64-v8a", "IN_TOOL": "chdman",
         "IN_ARTIFACT": "android-chdman"},
        {"IN_OS": "macos", "IN_ARCH": "arm64", "IN_TOOL": "xgdtool",
         "IN_ARTIFACT": "xgdtool-macos-arm64",
         "IN_VERSION": "1.0.0", "IN_SOURCE_REF": "v1.0.0",
         "IN_SOURCE_COMMIT": "a" * 40,
         "IN_TOOLCHAIN": "rustc 1.85.0 (x86_64-unknown-linux-musl)",
         "IN_BUILD_FLAVOR": "release"},
    ],
)
def test_validate_publish_inputs_accepts_valid(overrides):
    res = _run_validator(**_valid_inputs(**overrides))
    assert res.returncode == 0, res.stderr


@pytest.mark.parametrize(
    "overrides",
    [
        {"IN_OS": "solaris"},                                    # unknown os
        {"IN_ARCH": "mips"},                                     # unknown arch
        {"IN_OS": "windows", "IN_ARCH": "arm64"},                # bad combo
        {"IN_OS": "linux", "IN_ARCH": "arm64-v8a"},              # bad combo
        {"IN_TOOL": "does-not-exist"},                           # unknown tool
        {"IN_TOOL": "XGDTool"},                                  # uppercase tool
        {"IN_TOOL": "chdman; rm -rf /"},                         # tool injection
        {"IN_VERSION": "1.0; echo pwned"},                       # version injection
        {"IN_VERSION": "$(id)"},                                 # version cmdsubst
        {"IN_VERSION": "`id`"},                                  # version backtick
        {"IN_VERSION": "1.0\nGITHUB_ENV=x"},                     # embedded newline
        {"IN_SOURCE_REF": "v1 0"},                               # source_ref spaces
        {"IN_SOURCE_REF": "..;"},                                # source_ref metachars
        {"IN_SOURCE_COMMIT": "a" * 39},                          # short commit
        {"IN_SOURCE_COMMIT": "z" * 40},                          # non-hex commit
        {"IN_TOOLCHAIN": "gcc; rm -rf /"},                       # toolchain semicolon
        {"IN_TOOLCHAIN": "$(whoami)"},                           # toolchain cmdsubst
        {"IN_BUILD_FLAVOR": "NativeAOT"},                        # uppercase flavor
        {"IN_BUILD_FLAVOR": "a" * 33},                           # flavor too long
        {"IN_DRY_RUN": "yes"},                                   # dry_run not boolean
        {"IN_DRY_RUN": ""},                                      # dry_run empty
        {"IN_ARTIFACT": "bad name"},                             # artifact spaces
        {"IN_ARTIFACT": "a/b"},                                  # artifact slash
    ],
)
def test_validate_publish_inputs_rejects_invalid(overrides):
    res = _run_validator(**_valid_inputs(**overrides))
    assert res.returncode != 0, f"expected rejection for {overrides}"


# ---------------------------------------------------------------------------
# check_publish_artifact.py
# ---------------------------------------------------------------------------

def _run_artifact_checker(tmp_path, files, tool, os_name, arch):
    art = tmp_path / "download_artifact"
    art.mkdir(exist_ok=True)
    for name in files:
        target = art / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"x")
    out = tmp_path / "github_output.txt"
    env = os.environ.copy()
    env.update(
        {"TOOL": tool, "TARGET_OS": os_name, "TARGET_ARCH": arch,
         "GITHUB_OUTPUT": str(out)}
    )
    return subprocess.run(
        ["python3", ARTIFACT_CHECKER],
        capture_output=True, text=True, cwd=tmp_path, env=env,
    )


@pytest.mark.parametrize(
    "files,tool,os_name,arch",
    [
        (["nkit.exe"], "nkit", "windows", "x86_64"),
        (["chdman"], "chdman", "android", "arm64-v8a"),
        (["saturn-patcher"], "saturn-patcher", "linux", "arm64"),
        (["XGDTool"], "xgdtool", "linux", "x86_64"),
    ],
)
def test_artifact_checker_accepts_single_file(tmp_path, files, tool, os_name, arch):
    res = _run_artifact_checker(tmp_path, files, tool, os_name, arch)
    assert res.returncode == 0, res.stderr


@pytest.mark.parametrize(
    "files,tool,os_name,arch",
    [
        ([], "chdman", "linux", "x86_64"),                       # zero files
        (["chdman", "xgdtool"], "chdman", "linux", "x86_64"),    # two files
        (["nkit-3.exe"], "nkit", "windows", "x86_64"),           # nkit bad name
        (["chdman"], "chdman", "windows", "x86_64"),             # windows no .exe
        (["notchdman"], "chdman", "linux", "x86_64"),            # manifest mismatch
    ],
)
def test_artifact_checker_rejects_invalid(tmp_path, files, tool, os_name, arch):
    res = _run_artifact_checker(tmp_path, files, tool, os_name, arch)
    assert res.returncode != 0, f"expected rejection for {files}"


def test_artifact_checker_nested_file_still_enforced(tmp_path):
    # A single file nested in a subdirectory is still exactly one file, but its
    # basename must satisfy the rules.
    res = _run_artifact_checker(tmp_path, ["sub/chdman"], "chdman", "linux", "x86_64")
    assert res.returncode == 0, res.stderr


# ---------------------------------------------------------------------------
# update_manifest_entry.py argument hardening
# ---------------------------------------------------------------------------

def _setup_update_repo(tmp_path):
    tmp_repo = tmp_path / "repo"
    tmp_repo.mkdir()
    shutil.copy(MANIFEST_PATH, tmp_repo / "manifest.json")
    shutil.copy(CHECKSUMS_PATH, tmp_repo / "checksums.sha256")
    shutil.copy(VERSIONS_PATH, tmp_repo / "versions.json")
    scripts_dir = tmp_repo / "scripts"
    scripts_dir.mkdir()
    shutil.copy(UPDATE_ENTRY, scripts_dir / "update_manifest_entry.py")
    shutil.copy(
        os.path.join(SCRIPTS_DIR, "gen_checksums.py"),
        scripts_dir / "gen_checksums.py",
    )
    return tmp_repo, scripts_dir


def _run_update_entry(scripts_dir, tmp_repo, **overrides):
    args = {
        "--tool": "saturn-patcher",
        "--os": "linux",
        "--arch": "x86_64",
        "--file-path": "linux/x86_64/saturn-patcher",
        "--sha256": "1" * 64,
        "--size": "123456",
        "--built-at": "2026-01-01T00:00:00Z",
    }
    args.update(overrides)
    cmd = ["python3", str(scripts_dir / "update_manifest_entry.py")]
    for key, value in args.items():
        cmd += [key, value]
    return subprocess.run(cmd, cwd=tmp_repo, capture_output=True, text=True)


@pytest.mark.parametrize(
    "overrides",
    [
        {"--sha256": "zz"},                                      # bad sha256
        {"--sha256": "a" * 63},                                  # short sha256
        {"--size": "0"},                                         # size zero
        {"--size": "-5"},                                        # negative size
        {"--file-path": "macos/arm64/saturn-patcher"},           # os/arch mismatch
        {"--file-path": "linux/x86_64/.."},                      # path traversal
        {"--file-path": "linux/x86_64/../evil"},                 # path traversal
        {"--file-path": "linux/x86_64"},                         # too few segments
        {"--file-path": "linux/x86_64/sub/name"},                # too many segments
        {"--version": "1.0; echo pwned"},                        # version injection
        {"--source-commit": "a" * 39},                           # short commit
        {"--toolchain": "gcc; rm -rf /"},                        # toolchain injection
        {"--build-flavor": "NativeAOT"},                         # bad flavor
    ],
)
def test_update_manifest_entry_rejects_invalid(tmp_path, overrides):
    tmp_repo, scripts_dir = _setup_update_repo(tmp_path)
    before = (tmp_repo / "manifest.json").read_bytes()
    res = _run_update_entry(scripts_dir, tmp_repo, **overrides)
    assert res.returncode != 0, f"expected rejection for {overrides}"
    assert (tmp_repo / "manifest.json").read_bytes() == before, "manifest was modified"


# ---------------------------------------------------------------------------
# toolchain rule: publish-inputs and manifest validators must agree
# ---------------------------------------------------------------------------

NPM_TOOLCHAINS = [
    "npm @emmercm/chdman-linux-x64@0.289.0",
    "npm @emmercm/chdman-linux-arm64@0.289.0",
    "npm @emmercm/chdman-darwin-x64@0.289.0",
    "npm @emmercm/chdman-darwin-arm64@0.289.0",
    "npm @emmercm/chdman-win32-x64@0.289.0",
]


@pytest.mark.parametrize("toolchain", NPM_TOOLCHAINS)
def test_publish_inputs_accepts_npm_toolchain(toolchain):
    res = _run_validator(**_valid_inputs(IN_TOOLCHAIN=toolchain))
    assert res.returncode == 0, res.stderr


@pytest.mark.parametrize("toolchain", NPM_TOOLCHAINS + ["rustc 1.85.0", "gcc 14.2.0"])
def test_toolchain_passes_both_validators(toolchain):
    """The string accepted by validate_publish_inputs must also pass the
    manifest validator's toolchain rule (a concrete version must be present)."""
    res = _run_validator(**_valid_inputs(IN_TOOLCHAIN=toolchain))
    assert res.returncode == 0, res.stderr

    spec = importlib.util.spec_from_file_location(
        "validate_manifest", os.path.join(SCRIPTS_DIR, "validate_manifest.py")
    )
    vm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vm)
    assert not vm._is_generic_toolchain(toolchain), (
        f"manifest validator rejects {toolchain!r}"
    )


@pytest.mark.parametrize(
    "toolchain",
    [
        "C Compiler",                       # no version digit
        "gcc",                              # no version digit
        "npm package @emmercm/chdman-*",    # wildcard, no version
        "npm @emmercm/chdman",              # no version
    ],
)
def test_publish_inputs_rejects_versionless_toolchain(toolchain):
    res = _run_validator(**_valid_inputs(IN_TOOLCHAIN=toolchain))
    assert res.returncode != 0, f"expected rejection for {toolchain!r}"
