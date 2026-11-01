# Security Policy

## Reporting issues

If you discover a security vulnerability, a corrupted binary, or a checksum
mismatch in this repository or the SourceForge mirrors, report it privately
through a GitHub security advisory on
[M5Devs/OpenROM-bins](https://github.com/M5Devs/OpenROM-bins) or contact the
maintainers at [M5Devs](https://github.com/M5Devs).

## Verifying binaries

All binaries published to SourceForge are pinned in `manifest.json` and listed in
`checksums.sha256`. Always verify a download before use:

* Linux / macOS: `./scripts/fetch-bins.sh`
* Windows: `.\scripts\fetch-bins.ps1`

Both scripts fail closed: they exit non-zero if the SHA-256 or size does not match
the manifest. `verify-sourceforge.yml` performs the same check against the
published files on a schedule.

## Workflow permissions

Each workflow requests only the scopes it needs:

| Workflow | `permissions:` | Why |
|----------|----------------|-----|
| `ci.yml` | `contents: read` | Read the repo to run tests and the expression guard |
| `check-all-versions.yml` | `contents: read` | Read the manifest to compare upstream versions |
| `check-versions.yml` | `contents: read`, `issues: write` | Read the manifest; open/update an issue on a version change |
| `verify-sourceforge.yml` | `contents: read` | Read the manifest and re-download published files |
| `publish-sourceforge.yml` | `contents: write`, `pull-requests: write` | Commit manifest updates and open the manifest PR |
| `build-saturn-patcher.yml` | `contents: write`, `pull-requests: write` | Call `publish-sourceforge.yml` |
| `build-xgdtool.yml` | `contents: write`, `pull-requests: write` | Call `publish-sourceforge.yml` |
| `fetch_android_bins.yml` | `contents: write`, `pull-requests: write` | Call `publish-sourceforge.yml` |
| `update-chdman.yml` | `contents: write`, `pull-requests: write` | Call `publish-sourceforge.yml` |
| `update-binary.yml` | `contents: write`, `pull-requests: write` | Call `publish-sourceforge.yml` |
| `purge-history.yml` | `contents: write` | Force-push rewritten history to remove committed binaries |

The `contents: write` scopes exist only so the publish path can commit the
regenerated manifest and open a PR; no workflow pushes directly to `main`.

## Secret & key rotation

* Rotate `SF_SSH_PRIVATE_KEY` periodically and remove the old public key from the
  SourceForge account. Update the repository secret at the same time.
* Keep `scripts/sourceforge_known_hosts` in sync with SourceForge's published
  host-key fingerprints; re-verify them after any rotation.
* Treat `SF_USER` as non-secret but keep it consistent with the account that owns
  the upload key.
