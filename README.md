# OpenROM Binaries (M5Devs/OpenROM-bins)

Repository containing metadata, version manifests, and verification tools for third-party binaries used by [OpenROM](https://github.com/M5Devs/OpenROM).

## Architecture & Storage Model
Binaries are **not** hosted in this Git repository. All pre-compiled binaries are hosted externally on **SourceForge** (`openrom-binaries` project). Git holds only machine-readable manifests (`manifest.json`, `checksums.sha256`, `versions.json`), scripts, and automated GitHub workflows.

```text
[Upstream Repos / Build Workflows]
              │
              ▼
    [SourceForge Mirrors] ──(RSync via SSH)──► downloads.sourceforge.net/project/openrom-binaries/
              │
              ▼
  [Automated Manifest PR] ──► manifest.json / checksums.sha256 / versions.json
              │
              ▼
   [Consumer Verification] ──► scripts/fetch-bins.sh / fetch-bins.ps1
```

### Direct Download URL Schema
```text
https://downloads.sourceforge.net/project/openrom-binaries/{os}/{arch}/{binary_name}
```

*Example for Windows x86_64 `chdman.exe`:*
```text
https://downloads.sourceforge.net/project/openrom-binaries/windows/x86_64/chdman.exe
```

## NKit NativeAOT Single-File Policy
NKit is built as a **NativeAOT self-contained single-file native executable**:
- No .NET runtime/framework required on user machines.
- No `nkit/` subdirectory, no `nkds`, no sibling DLL files.
- Path layout: `{os}/{arch}/nkit` (`windows/x86_64/nkit.exe`).

## How Consumers Download and Verify Binaries
Use the provided fetch scripts:

**Linux / macOS / Unix:**
```bash
./scripts/fetch-bins.sh --os linux --arch x86_64 --target-dir ./bin
```

**Windows / PowerShell:**
```powershell
.\scripts\fetch-bins.ps1 -Os "windows" -Arch "x86_64" -TargetDir ".\bin"
```

The scripts download binaries from SourceForge (or `OPENROM_BINS_BASE_URL`), verify SHA-256 and file size against `manifest.json`, and set executable permissions.

## Trust Model & Verification
- **SHA-256 Hashes**: Every binary is pinned to an exact SHA-256 hash in `manifest.json` and `checksums.sha256`.
- **Source Verification**: Tools built from source record the 40-character git commit SHA, build timestamp, toolchain version, and applied patch SHA-256 hashes in `manifest.json`.

## Secrets & Required Permissions
Publishing to SourceForge requires:
- `SF_USER`: SourceForge account username.
- `SF_SSH_PRIVATE_KEY`: Private SSH key registered with the SourceForge account.
- `SF_KNOWN_HOSTS`: Pinned host key fingerprints (defaults to `scripts/sourceforge_known_hosts`).

## License
Each tool is subject to its own upstream open-source license. See [LICENSES/README.md](LICENSES/README.md) and [SOURCES.md](SOURCES.md).
