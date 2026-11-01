import json
import os
import re
import shutil
import subprocess
import threading
import importlib.util
from http.server import HTTPServer, SimpleHTTPRequestHandler
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST_PATH = os.path.join(REPO_ROOT, "manifest.json")
CHECKSUMS_PATH = os.path.join(REPO_ROOT, "checksums.sha256")
VERSIONS_PATH = os.path.join(REPO_ROOT, "versions.json")

def test_manifest_validation_script():
    cmd = ["python3", os.path.join(REPO_ROOT, "scripts", "validate_manifest.py")]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"validate_manifest.py failed: {res.stderr}"

def test_checksum_and_versions_roundtrip():
    # Run gen_checksums.py and check git diff / consistency
    cmd = ["python3", os.path.join(REPO_ROOT, "scripts", "gen_checksums.py")]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"gen_checksums.py failed: {res.stderr}"

    # Verify checksums.sha256 format (64-hex <space><space> path, sorted)
    with open(CHECKSUMS_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()

    assert len(lines) > 0
    paths = []
    for line in lines:
        assert line.endswith("\n") or line.endswith("\r\n")
        line_clean = line.strip()
        assert len(line_clean) > 66
        parts = line_clean.split(None, 1)
        sha, path = parts[0], parts[1]
        assert re.match(r"^[0-9a-fA-F]{64}$", sha)
        paths.append(path)

    assert paths == sorted(paths)

def test_nkit_single_file_rule():
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    nkit_data = manifest["tools"]["nkit"]
    for plat_key, plat_entry in nkit_data["platforms"].items():
        path = plat_entry["path"]
        assert "nkit/" not in path, f"NKit path must not contain subfolder 'nkit/': {path}"
        assert "nkds" not in path, f"NKit path must not reference 'nkds': {path}"
        filename = os.path.basename(path)
        assert filename in ["nkit", "nkit.exe"], f"NKit binary filename must be nkit or nkit.exe: {filename}"

def test_input_validation_regexes():
    # Regexes used in update-binary and other workflows
    tool_regex = re.compile(r"^[a-z0-9-]+$")
    filename_regex = re.compile(r"^[A-Za-z0-9._-]+$")
    sha256_regex = re.compile(r"^[0-9a-fA-F]{64}$")

    assert tool_regex.match("chdman")
    assert tool_regex.match("saturn-patcher")
    assert not tool_regex.match("Tool_Name")

    assert filename_regex.match("XGDTool.exe")
    assert filename_regex.match("extract-xiso")
    assert not filename_regex.match("file;rm -rf /")

    assert sha256_regex.match("a" * 64)
    assert not sha256_regex.match("a" * 63)

@pytest.fixture
def dummy_server(tmp_path):
    # Setup dummy directory layout matching manifest relative path for 1 dummy binary
    os_dir = tmp_path / "linux" / "x86_64"
    os_dir.mkdir(parents=True)
    dummy_bin = os_dir / "saturn-patcher"

    # We will test fetching saturn-patcher for linux/x86_64
    with open(MANIFEST_PATH, "r") as f:
        manifest = json.load(f)

    exp_entry = manifest["tools"]["saturn-patcher"]["platforms"]["linux/x86_64"]
    dummy_data = b"DUMMY_SATURN_PATCHER_BINARY_DATA"

    # Write a test manifest override or mock data
    import hashlib
    actual_sha = hashlib.sha256(dummy_data).hexdigest()

    # Modify dummy manifest in tmp_path
    mock_manifest = json.loads(json.dumps(manifest))
    mock_manifest["tools"]["saturn-patcher"]["platforms"]["linux/x86_64"]["sha256"] = actual_sha
    mock_manifest["tools"]["saturn-patcher"]["platforms"]["linux/x86_64"]["size"] = len(dummy_data)

    manifest_file = tmp_path / "manifest.json"
    with open(manifest_file, "w") as f:
        json.dump(mock_manifest, f)

    dummy_bin.write_bytes(dummy_data)

    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

    os.chdir(tmp_path)
    server = HTTPServer(("127.0.0.1", 0), QuietHandler)
    port = server.server_port

    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()

    yield f"http://127.0.0.1:{port}", tmp_path, manifest_file

    server.shutdown()
    os.chdir(REPO_ROOT)

def test_fetch_bins_script(dummy_server):
    base_url, tmp_dir, manifest_file = dummy_server
    target_dir = tmp_dir / "target"

    env = os.environ.copy()
    env["OPENROM_BINS_BASE_URL"] = base_url

    script_path = os.path.join(REPO_ROOT, "scripts", "fetch-bins.sh")

    # We pass manifest path override via working directory repo root mock
    # Replace manifest in REPO_ROOT temporarily or test with script directly
    cmd = [
        script_path,
        "--tool", "saturn-patcher",
        "--os", "linux",
        "--arch", "x86_64",
        "--target-dir", str(target_dir)
    ]

    # Temporarily copy mock manifest to REPO_ROOT/manifest.json
    with open(MANIFEST_PATH, "rb") as f:
        orig_manifest_content = f.read()

    try:
        with open(MANIFEST_PATH, "wb") as f:
            f.write(manifest_file.read_bytes())

        res = subprocess.run(cmd, env=env, capture_output=True, text=True)
        assert res.returncode == 0, f"fetch-bins.sh failed: {res.stderr}"
        fetched_file = target_dir / "saturn-patcher"
        assert fetched_file.exists()
        assert fetched_file.read_bytes() == b"DUMMY_SATURN_PATCHER_BINARY_DATA"
    finally:
        with open(MANIFEST_PATH, "wb") as f:
            f.write(orig_manifest_content)


# ---------------------------------------------------------------------------
# validate_manifest.py rule coverage
# ---------------------------------------------------------------------------

def _load_validator():
    path = os.path.join(REPO_ROOT, "scripts", "validate_manifest.py")
    spec = importlib.util.spec_from_file_location("validate_manifest_mod", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _base_manifest():
    return {
        "format_version": 1,
        "tools": {
            "demo": {
                "version": "1.0.0",
                "license": "MIT",
                "upstream_repo": "https://github.com/example/demo",
                "provenance": "upstream-release",
                "platforms": {
                    "linux/x86_64": {
                        "path": "linux/x86_64/demo",
                        "sha256": "a" * 64,
                        "size": 100,
                        "executable": True,
                        "status": "ok",
                    }
                },
            }
        },
    }


def _write_root(tmp_path, manifest, checksums=None, versions=None):
    vm = _load_validator()
    root = tmp_path / "repo"
    (root / "schema").mkdir(parents=True, exist_ok=True)
    shutil.copy(
        os.path.join(REPO_ROOT, "schema", "manifest.schema.json"),
        root / "schema" / "manifest.schema.json",
    )
    if checksums is None:
        checksums = vm.expected_checksums(manifest)
    if versions is None:
        versions = vm.expected_versions(manifest)
    (root / "checksums.sha256").write_text(checksums, encoding="utf-8")
    (root / "versions.json").write_text(versions, encoding="utf-8")
    return root


def _validate(manifest, tmp_path, checksums=None, versions=None, strict=False):
    root = _write_root(tmp_path, manifest, checksums, versions)
    vm = _load_validator()
    return vm.validate(manifest, str(root), strict=strict)


def _plat(manifest, tool="demo", key="linux/x86_64"):
    return manifest["tools"][tool]["platforms"][key]


def _assert_error(manifest, tmp_path, needle):
    errors, _ = _validate(manifest, tmp_path)
    assert any(needle in e for e in errors), f"expected {needle!r} in {errors}"


# --- base sanity -----------------------------------------------------------

def test_base_manifest_is_valid(tmp_path):
    errors, warnings = _validate(_base_manifest(), tmp_path)
    assert errors == []
    assert warnings == []


def test_live_repo_manifest_passes():
    cmd = ["python3", os.path.join(REPO_ROOT, "scripts", "validate_manifest.py")]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr


# --- platform key / path rules --------------------------------------------

def test_platform_key_not_allowed(tmp_path):
    m = _base_manifest()
    m["tools"]["demo"]["platforms"]["linux/mips"] = {
        "path": "linux/mips/demo", "sha256": "b" * 64, "size": 1,
        "executable": True, "status": "ok",
    }
    _assert_error(m, tmp_path, "platform key is not allowed")


def test_platform_path_prefix_mismatch(tmp_path):
    m = _base_manifest()
    _plat(m)["path"] = "linux/arm64/demo"
    _assert_error(m, tmp_path, "must equal <os>/<arch>/<basename>")


def test_platform_basename_invalid(tmp_path):
    m = _base_manifest()
    _plat(m)["path"] = "linux/x86_64/de mo"
    _assert_error(m, tmp_path, "basename")


def test_platform_path_traversal(tmp_path):
    m = _base_manifest()
    _plat(m)["path"] = "linux/x86_64/.."
    _assert_error(m, tmp_path, "must not contain '..'")


def test_windows_path_without_exe(tmp_path):
    m = _base_manifest()
    del m["tools"]["demo"]["platforms"]["linux/x86_64"]
    m["tools"]["demo"]["platforms"]["windows/x86_64"] = {
        "path": "windows/x86_64/demo", "sha256": "a" * 64, "size": 100,
        "executable": True, "status": "ok",
    }
    _assert_error(m, tmp_path, "must end with .exe")


def test_sha256_invalid(tmp_path):
    m = _base_manifest()
    _plat(m)["sha256"] = "zz"
    _assert_error(m, tmp_path, "sha256 is not 64 hex characters")


def test_size_zero(tmp_path):
    m = _base_manifest()
    _plat(m)["size"] = 0
    _assert_error(m, tmp_path, "size must be an integer >= 1")


def test_status_mismatch_is_error(tmp_path):
    m = _base_manifest()
    _plat(m)["status"] = "mismatch"
    _assert_error(m, tmp_path, "status is 'mismatch'")


def test_status_unverified_without_note(tmp_path):
    m = _base_manifest()
    _plat(m)["status"] = "unverified"
    _assert_error(m, tmp_path, "status 'unverified' requires a non-empty note")


def test_status_unverified_with_note_is_warning_only(tmp_path):
    m = _base_manifest()
    _plat(m)["status"] = "unverified"
    _plat(m)["note"] = "downloaded by hand"
    errors, warnings = _validate(m, tmp_path)
    assert errors == []
    assert any("unverified" in w for w in warnings)


def _nkit_manifest(path):
    m = _base_manifest()
    m["tools"]["nkit"] = {
        "version": "3.1.0", "license": "MIT",
        "upstream_repo": "https://github.com/Nanook/NKit",
        "provenance": "built-from-source", "build_flavor": "legacy-unknown",
        "platforms": {
            "linux/x86_64": {
                "path": path, "sha256": "c" * 64,
                "size": 5, "executable": True, "status": "ok",
            }
        },
    }
    return m


def test_nkit_path_rules(tmp_path):
    _assert_error(_nkit_manifest("linux/x86_64/nkit/nkit"), tmp_path,
                  "must not contain 'nkit/'")


def test_nkit_basename_must_be_nkit(tmp_path):
    _assert_error(_nkit_manifest("linux/x86_64/nkit-extra"), tmp_path,
                  "must be named nkit or nkit.exe")


def test_nkit_nkds_forbidden(tmp_path):
    m = _base_manifest()
    m["tools"]["nkit"] = {
        "version": "3.1.0", "license": "MIT",
        "upstream_repo": "https://github.com/Nanook/NKit",
        "provenance": "built-from-source", "build_flavor": "legacy-unknown",
        "platforms": {
            "linux/x86_64": {
                "path": "linux/x86_64/nkds", "sha256": "c" * 64,
                "size": 5, "executable": True, "status": "ok",
            }
        },
    }
    _assert_error(m, tmp_path, "must not reference 'nkds'")


# --- same_as rules ---------------------------------------------------------

def _two_platform_manifest():
    m = _base_manifest()
    m["tools"]["demo"]["platforms"]["android/arm64-v8a"] = {
        "path": "android/arm64-v8a/demo", "sha256": "a" * 64, "size": 100,
        "executable": True, "status": "ok", "same_as": "linux/x86_64/demo",
    }
    return m


def test_same_as_valid(tmp_path):
    errors, _ = _validate(_two_platform_manifest(), tmp_path)
    assert errors == []


def test_same_as_missing_path(tmp_path):
    m = _two_platform_manifest()
    _plat(m, key="android/arm64-v8a")["same_as"] = "linux/arm64/does-not-exist"
    _assert_error(m, tmp_path, "does not exist in the manifest")


def test_same_as_other_tool(tmp_path):
    m = _two_platform_manifest()
    m["tools"]["other"] = {
        "version": "1.0.0", "license": "MIT",
        "upstream_repo": "https://github.com/example/other",
        "provenance": "upstream-release",
        "platforms": {"linux/x86_64": {
            "path": "linux/x86_64/other", "sha256": "a" * 64, "size": 100,
            "executable": True, "status": "ok"}},
    }
    _plat(m, key="android/arm64-v8a")["same_as"] = "linux/x86_64/other"
    _assert_error(m, tmp_path, "belongs to a different tool")


def test_same_as_different_sha256(tmp_path):
    m = _two_platform_manifest()
    _plat(m, key="android/arm64-v8a")["sha256"] = "d" * 64
    _assert_error(m, tmp_path, "has a different sha256")


def test_same_as_different_size(tmp_path):
    m = _two_platform_manifest()
    _plat(m, key="android/arm64-v8a")["size"] = 999
    _assert_error(m, tmp_path, "has a different size")


def test_same_as_chain(tmp_path):
    m = _two_platform_manifest()
    m["tools"]["demo"]["platforms"]["android/arm64-v8a"]["same_as"] = "linux/x86_64/demo"
    m["tools"]["demo"]["platforms"]["linux/x86_64"]["same_as"] = "android/arm64-v8a/demo"
    _assert_error(m, tmp_path, "chains/cycles not allowed")


def test_same_as_itself(tmp_path):
    m = _base_manifest()
    _plat(m)["same_as"] = "linux/x86_64/demo"
    _assert_error(m, tmp_path, "same_as points at itself")


# --- universal rules -------------------------------------------------------

def _macos_pair(universal=True, same_hash=True):
    m = _base_manifest()
    del m["tools"]["demo"]["platforms"]["linux/x86_64"]
    m["tools"]["demo"]["platforms"]["macos/arm64"] = {
        "path": "macos/arm64/demo", "sha256": "e" * 64, "size": 10,
        "executable": True, "status": "ok",
    }
    m["tools"]["demo"]["platforms"]["macos/x86_64"] = {
        "path": "macos/x86_64/demo",
        "sha256": ("e" * 64) if same_hash else ("f" * 64),
        "size": 10, "executable": True, "status": "ok",
    }
    if universal:
        for k in ("macos/arm64", "macos/x86_64"):
            m["tools"]["demo"]["platforms"][k]["universal"] = True
    return m


def test_universal_pair_valid(tmp_path):
    errors, _ = _validate(_macos_pair(), tmp_path)
    assert errors == []


def test_universal_on_windows(tmp_path):
    m = _base_manifest()
    _plat(m)["universal"] = True
    _assert_error(m, tmp_path, "'universal' is only allowed for macos")


def test_universal_with_different_hashes(tmp_path):
    m = _macos_pair(universal=True, same_hash=False)
    _assert_error(m, tmp_path, "requires the same sha256 as macos/")


def test_identical_hashes_without_universal(tmp_path):
    m = _macos_pair(universal=False, same_hash=True)
    _assert_error(m, tmp_path, "requires 'universal: true' on both")


# --- tool-level rules ------------------------------------------------------

def test_version_placeholder(tmp_path):
    m = _base_manifest()
    m["tools"]["demo"]["version"] = "0.0.0"
    _assert_error(m, tmp_path, "placeholder version")


def test_version_tbd_placeholder(tmp_path):
    m = _base_manifest()
    m["tools"]["demo"]["version"] = "TBD"
    _assert_error(m, tmp_path, "placeholder version")


def test_toolchain_generic_placeholder(tmp_path):
    m = _base_manifest()
    m["tools"]["demo"]["toolchain"] = "C Compiler"
    _assert_error(m, tmp_path, "generic placeholder")


def test_upstream_repo_must_be_https(tmp_path):
    m = _base_manifest()
    m["tools"]["demo"]["upstream_repo"] = "http://github.com/example/demo"
    _assert_error(m, tmp_path, "must be an https URL")


def test_built_from_source_nativeaot_requires_source_commit(tmp_path):
    m = _base_manifest()
    m["tools"]["nkit"] = {
        "version": "3.1.0", "license": "MIT",
        "upstream_repo": "https://github.com/Nanook/NKit",
        "provenance": "built-from-source", "build_flavor": "nativeaot",
        "platforms": {"linux/x86_64": {
            "path": "linux/x86_64/nkit", "sha256": "c" * 64, "size": 5,
            "executable": True, "status": "ok"}},
    }
    _assert_error(m, tmp_path, "but has no source_commit")


def test_nativeaot_only_for_nkit(tmp_path):
    m = _base_manifest()
    m["tools"]["demo"]["provenance"] = "built-from-source"
    m["tools"]["demo"]["build_flavor"] = "nativeaot"
    m["tools"]["demo"]["source_commit"] = "a" * 40
    m["tools"]["demo"]["source_ref"] = "v1.0.0"
    m["tools"]["demo"]["toolchain"] = "dotnet 10.0.103"
    _assert_error(m, tmp_path, "may not use build_flavor 'nativeaot'")


def test_built_from_source_unpinned_is_warning(tmp_path):
    m = _base_manifest()
    m["tools"]["demo"]["provenance"] = "built-from-source"
    m["tools"]["demo"]["build_flavor"] = "legacy-unknown"
    errors, warnings = _validate(m, tmp_path)
    assert errors == []
    assert any("unpinned source" in w for w in warnings)


def test_patch_path_missing(tmp_path):
    m = _base_manifest()
    m["tools"]["demo"]["provenance"] = "built-from-source"
    m["tools"]["demo"]["build_flavor"] = "release"
    m["tools"]["demo"]["source_commit"] = "a" * 40
    m["tools"]["demo"]["source_ref"] = "v1.0.0"
    m["tools"]["demo"]["toolchain"] = "gcc 13.2.0"
    m["tools"]["demo"]["patches"] = [
        {"path": "demo/0001-missing.patch", "sha256": "a" * 64, "purpose": "fix"}
    ]
    _assert_error(m, tmp_path, "not found under patches/")


# --- version_alias_of ------------------------------------------------------

def test_version_alias_of_missing_tool(tmp_path):
    m = _base_manifest()
    del m["tools"]["demo"]["version"]
    m["tools"]["demo"]["version_alias_of"] = "nope"
    _assert_error(m, tmp_path, "does not exist")


def test_version_alias_of_chain(tmp_path):
    m = _base_manifest()
    m["tools"]["other"] = {
        "version": "1.0.0", "license": "MIT",
        "upstream_repo": "https://github.com/example/other",
        "provenance": "upstream-release",
        "platforms": {"linux/x86_64": {
            "path": "linux/x86_64/other", "sha256": "b" * 64, "size": 1,
            "executable": True, "status": "ok"}},
    }
    del m["tools"]["demo"]["version"]
    m["tools"]["demo"]["version_alias_of"] = "other"
    del m["tools"]["other"]["version"]
    m["tools"]["other"]["version_alias_of"] = "demo"
    _assert_error(m, tmp_path, "is itself an alias")


def test_aliased_tool_absent_from_versions(tmp_path):
    m = _base_manifest()
    m["tools"]["other"] = {
        "version": "1.0.0", "license": "MIT",
        "upstream_repo": "https://github.com/example/other",
        "provenance": "upstream-release",
        "platforms": {"linux/x86_64": {
            "path": "linux/x86_64/other", "sha256": "b" * 64, "size": 1,
            "executable": True, "status": "ok"}},
    }
    del m["tools"]["demo"]["version"]
    m["tools"]["demo"]["version_alias_of"] = "other"
    vm = _load_validator()
    versions_text = vm.expected_versions(m)
    assert "demo" not in json.loads(versions_text)
    assert json.loads(versions_text)["other"] == "1.0.0"
    errors, _ = _validate(m, tmp_path)
    assert errors == []


def test_aliased_tool_in_versions_is_out_of_date(tmp_path):
    m = _base_manifest()
    m["tools"]["other"] = {
        "version": "1.0.0", "license": "MIT",
        "upstream_repo": "https://github.com/example/other",
        "provenance": "upstream-release",
        "platforms": {"linux/x86_64": {
            "path": "linux/x86_64/other", "sha256": "b" * 64, "size": 1,
            "executable": True, "status": "ok"}},
    }
    del m["tools"]["demo"]["version"]
    m["tools"]["demo"]["version_alias_of"] = "other"
    bad_versions = json.dumps({"demo": "1.0.0", "other": "1.0.0"}, indent=2) + "\n"
    errors, _ = _validate(m, tmp_path, versions=bad_versions)
    assert any("versions.json is out of date" in e for e in errors)


# --- generated files -------------------------------------------------------

def test_checksums_crlf_is_error(tmp_path):
    m = _base_manifest()
    vm = _load_validator()
    crlf = vm.expected_checksums(m).replace("\n", "\r\n")
    errors, _ = _validate(m, tmp_path, checksums=crlf)
    assert any("must use LF line endings only" in e for e in errors)


def test_checksums_without_trailing_newline(tmp_path):
    m = _base_manifest()
    vm = _load_validator()
    no_newline = vm.expected_checksums(m).rstrip("\n")
    errors, _ = _validate(m, tmp_path, checksums=no_newline)
    assert any("checksums.sha256 is out of date" in e for e in errors)


def test_versions_out_of_date(tmp_path):
    m = _base_manifest()
    errors, _ = _validate(m, tmp_path, versions='{"demo": "9.9.9"}\n')
    assert any("versions.json is out of date" in e for e in errors)


# --- strict mode -----------------------------------------------------------

def test_strict_promotes_warnings(tmp_path):
    m = _base_manifest()
    m["tools"]["demo"]["provenance"] = "built-from-source"
    m["tools"]["demo"]["build_flavor"] = "legacy-unknown"
    _, warnings = _validate(m, tmp_path, strict=False)
    assert warnings
    strict_errors, strict_warnings = _validate(m, tmp_path, strict=True)
    assert strict_errors
    assert strict_warnings == []


# --- positive live-manifest checks ----------------------------------------

def test_live_android_nkit_same_as_valid():
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    android = manifest["tools"]["nkit"]["platforms"]["android/arm64-v8a"]
    linux = manifest["tools"]["nkit"]["platforms"]["linux/arm64"]
    assert android["same_as"] == "linux/arm64/nkit"
    assert android["sha256"] == linux["sha256"]
    assert android["size"] == linux["size"]


def test_live_macos_universal_pair_valid():
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    for tool, data in manifest["tools"].items():
        arm = data["platforms"].get("macos/arm64")
        x86 = data["platforms"].get("macos/x86_64")
        if arm and arm.get("universal"):
            assert x86 and x86.get("universal")
            assert arm["sha256"] == x86["sha256"]


# --- Task 5: nkit provenance + single-file rules --------------------------

def test_nkit_single_file_rules_apply_for_upstream_release(tmp_path):
    """The nkit path/basename rules must hold for any provenance."""
    m = _base_manifest()
    m["tools"]["nkit"] = {
        "version": "3.1.0", "license": "MIT",
        "upstream_repo": "https://github.com/Nanook/NKit",
        "provenance": "upstream-release",
        "platforms": {
            "linux/x86_64": {
                "path": "linux/x86_64/nkit-extra", "sha256": "c" * 64,
                "size": 5, "executable": True, "status": "ok",
            }
        },
    }
    _assert_error(m, tmp_path, "must be named nkit or nkit.exe")


def test_live_nkit_is_upstream_release_and_not_unpinned():
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["tools"]["nkit"]["provenance"] == "upstream-release"
    spec = importlib.util.spec_from_file_location(
        "validate_manifest",
        os.path.join(REPO_ROOT, "scripts", "validate_manifest.py"),
    )
    vm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vm)
    _, warnings = vm.validate(manifest, REPO_ROOT)
    assert not any("nkit" in w and "unpinned" in w for w in warnings)
