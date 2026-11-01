# Third-Party Licenses

This repository tracks pre-compiled binaries from the following third-party
projects. Each binary is subject to its own open-source license. The license
column matches the `license` field in `manifest.json` verbatim.

| Binary | License | Upstream Source Repo | Notes |
|--------|---------|----------------------|-------|
| chdman | GPL-2.0-or-later OR BSD-3-Clause | [mamedev/mame](https://github.com/mamedev/mame) | Distributed via `@emmercm/chdman-*` npm packages |
| ecm | GPL-2.0-only | [kidoz/ecm](https://github.com/kidoz/ecm) | Upstream project `kidoz/ecm` |
| unecm | GPL-2.0-only | [kidoz/ecm](https://github.com/kidoz/ecm) | Same upstream project as `ecm` |
| extract-xiso | BSD-4-Clause | [XboxDev/extract-xiso](https://github.com/XboxDev/extract-xiso) | Modified 4-clause BSD |
| maxcso | ISC | [unknownbrackets/maxcso](https://github.com/unknownbrackets/maxcso) | Upstream ISC license |
| nkit | MIT | [Nanook/NKit](https://github.com/Nanook/NKit) | One file per platform (`nkit` / `nkit.exe`); provenance unverified |
| nodtool | MIT OR Apache-2.0 | [encounter/nod](https://github.com/encounter/nod) | Dual-licensed MIT/Apache-2.0 |
| saturn-patcher | GPL-3.0-or-later | [ralfguth/saturn-patcher-egui](https://github.com/ralfguth/saturn-patcher-egui) | Built from source with Rust |
| xdelta3 | Apache-2.0 | [jmacd/xdelta](https://github.com/jmacd/xdelta) | Upstream Apache-2.0 license |
| xgdtool | GPL-3.0-only | [wiredopposite/XGDTool](https://github.com/wiredopposite/XGDTool) | Built from source with C++/CMake |

The license strings above are taken from `manifest.json`. Where the manifest
holds an SPDX expression (for example `MIT OR Apache-2.0`) both options are
listed. Upstream `LICENSE` files are not vendored in this repository; consult
the linked upstream repositories for the full license text.
