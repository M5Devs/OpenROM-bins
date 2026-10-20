# Security Policy

## Reporting Vulnerabilities
If you discover a security vulnerability or corrupted binary integrity issue in this repository or the SourceForge mirrors, please report it immediately by opening a security advisory or contacting the maintainers at [M5Devs](https://github.com/M5Devs).

## Binary Verification
All binaries published to SourceForge are verified against `manifest.json` and `checksums.sha256`. Consumers should always verify downloaded binaries using:

- Linux / macOS: `./scripts/fetch-bins.sh`
- Windows: `.\scripts\fetch-bins.ps1`

## Secret & Key Rotation
- SSH deployment keys (`SF_SSH_PRIVATE_KEY`) and SourceForge host fingerprints (`scripts/sourceforge_known_hosts`) must be periodically rotated and updated.
- Workflow permissions are configured strictly to `permissions: contents: read` or minimal required scopes.
