# OpenROM-bins

Metadata, licenses, and checksums for third-party binaries used in [OpenROM](https://github.com/M5Devs/OpenROM).

## Storage & Mirrors

Due to binary size considerations, pre-compiled binaries are hosted externally on **SourceForge**:
🔗 **[Download Binaries from SourceForge](https://sourceforge.net/projects/openrom-binaries/files/)**

### Direct Download URL Structure
Binaries can be fetched directly using the following URL schema:
```text
https://downloads.sourceforge.net/project/openrom-binaries/{os}/{arch}/{binary_name}
```

*Example for Windows x86_64 `chdman.exe`:*
```text
https://downloads.sourceforge.net/project/openrom-binaries/windows/x86_64/chdman.exe
```

## Integrity & Verification

All binaries are verified against the SHA-256 hashes listed in `checksums.sha256`.

To verify locally:
```bash
sha256sum -c checksums.sha256
```

## Licenses

Each binary is subject to its own open-source license. See [LICENSES/](LICENSES/).
