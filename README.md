# OpenROM-bins

Pre-compiled third-party binaries for [OpenROM](https://github.com/M5Devs/OpenROM).

## Structure

```
windows/
├── x86_64/     ← Windows x64 binaries
└── arm64/      ← Windows ARM64 binaries (future)
linux/
├── x86_64/     ← Linux x64 binaries
└── arm64/      ← Linux ARM64 binaries (light tools only)
macos/
├── arm64/      ← macOS Apple Silicon binaries
└── x86_64/     ← macOS Intel binaries
```

## Usage

The OpenROM CI clones this repo at build time:
```bash
git clone --depth 1 https://github.com/M5Devs/OpenROM-bins bins/
```

## Licenses

Each binary is subject to its own license. See [LICENSES/](LICENSES/).
