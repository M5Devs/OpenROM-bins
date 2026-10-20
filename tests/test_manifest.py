import json
import os
import re
import subprocess
import threading
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
