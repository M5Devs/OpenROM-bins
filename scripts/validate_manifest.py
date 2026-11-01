#!/usr/bin/env python3
"""Validate manifest.json and the files generated from it.

Collects *all* problems instead of stopping at the first one. Errors fail the
run (exit 1); warnings are reported but do not fail unless --strict is used.
Importable from tests: `validate(manifest, root, strict=False) -> (errors, warnings)`.
"""
import argparse
import json
import os
import re
import sys

try:
    import jsonschema
except ImportError:  # pragma: no cover - environment dependent
    jsonschema = None

# Import the SOURCES.md renderer so the validator and the generator cannot drift.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from gen_sources import render_sources
except ImportError:  # pragma: no cover - environment dependent
    render_sources = None

ALLOWED_PLATFORMS = {
    "windows/x86_64",
    "linux/x86_64",
    "linux/arm64",
    "macos/x86_64",
    "macos/arm64",
    "android/arm64-v8a",
}
ALLOWED_STATUS = {"ok", "unverified", "mismatch"}
ALLOWED_PROVENANCE = {"built-from-source", "upstream-release", "npm-package"}

PLACEHOLDER_VERSIONS = {"", "0", "0.0", "0.0.0", "unknown", "tbd", "-", "n/a"}
GENERIC_TOOLCHAINS = {
    "", "-", "n/a", "unknown", "c compiler", "c++ compiler",
    "gcc / cmake", "gcc/cmake", "cmake", "gcc",
}

RE_SHA256 = re.compile(r"[0-9a-fA-F]{64}")
RE_SHA256_OR_SHA512 = re.compile(r"(sha512|sha256)-[A-Za-z0-9+/=]+")
RE_COMMIT = re.compile(r"[0-9a-fA-F]{40}")
RE_BASENAME = re.compile(r"[A-Za-z0-9._-]+")
RE_DIGIT = re.compile(r"\d")


def load_json(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _is_placeholder_version(value):
    return str(value).strip().lower() in PLACEHOLDER_VERSIONS


def _is_generic_toolchain(value):
    text = str(value).strip()
    if text.lower() in GENERIC_TOOLCHAINS:
        return True
    # A real toolchain string names a concrete version number.
    return RE_DIGIT.search(text) is None


def expected_checksums(manifest):
    lines = []
    for tool_data in manifest.get("tools", {}).values():
        for plat_data in tool_data.get("platforms", {}).values():
            lines.append(f"{plat_data['sha256']}  {plat_data['path']}")
    lines.sort(key=lambda line: line.split(None, 1)[1])
    return "\n".join(lines) + "\n"


def expected_versions(manifest):
    versions = {}
    for tool_name, tool_data in manifest.get("tools", {}).items():
        if tool_data.get("version_alias_of"):
            continue
        if "version" in tool_data:
            versions[tool_name] = tool_data["version"]
    return json.dumps(dict(sorted(versions.items())), indent=2) + "\n"


def _validate_schema(manifest, root, errors, warnings):
    schema_path = os.path.join(root, "schema", "manifest.schema.json")
    if jsonschema is None:
        warnings.append("jsonschema is not installed; schema validation skipped")
        return
    if not os.path.exists(schema_path):
        warnings.append(f"schema not found at {schema_path}; schema validation skipped")
        return
    try:
        jsonschema.validate(instance=manifest, schema=load_json(schema_path))
    except jsonschema.ValidationError as exc:
        errors.append(f"manifest schema validation error: {exc.message}")


def _validate_tool_fields(tool_name, tool_data, manifest, root, errors, warnings):
    for required in ("license", "upstream_repo", "provenance"):
        if not tool_data.get(required):
            errors.append(f"tool '{tool_name}' missing {required}")

    version = tool_data.get("version")
    alias = tool_data.get("version_alias_of")
    if alias:
        target = manifest.get("tools", {}).get(alias)
        if target is None:
            errors.append(
                f"tool '{tool_name}' version_alias_of '{alias}' does not exist"
            )
        elif target.get("version_alias_of"):
            errors.append(
                f"tool '{tool_name}' version_alias_of '{alias}' is itself an alias "
                "(alias chains are not allowed)"
            )
    elif version is None:
        errors.append(f"tool '{tool_name}' missing version (or version_alias_of)")

    if version is not None and _is_placeholder_version(version):
        errors.append(f"tool '{tool_name}' has placeholder version {version!r}")

    upstream_repo = tool_data.get("upstream_repo", "")
    if upstream_repo and not str(upstream_repo).startswith("https://"):
        errors.append(
            f"tool '{tool_name}' upstream_repo must be an https URL, got {upstream_repo!r}"
        )

    provenance = tool_data.get("provenance")
    if provenance and provenance not in ALLOWED_PROVENANCE:
        errors.append(f"tool '{tool_name}' invalid provenance {provenance!r}")

    if "toolchain" in tool_data and _is_generic_toolchain(tool_data["toolchain"]):
        errors.append(
            f"tool '{tool_name}' toolchain is a generic placeholder "
            f"{tool_data['toolchain']!r} (must name a concrete version)"
        )

    build_flavor = tool_data.get("build_flavor")
    if build_flavor == "nativeaot" and tool_name != "nkit":
        errors.append(
            f"tool '{tool_name}' may not use build_flavor 'nativeaot' (nkit only)"
        )

    if provenance == "built-from-source":
        if build_flavor is not None and build_flavor != "legacy-unknown":
            for field in ("source_commit", "source_ref", "toolchain"):
                if not tool_data.get(field):
                    errors.append(
                        f"tool '{tool_name}' is built-from-source with "
                        f"build_flavor '{build_flavor}' but has no {field}"
                    )
        if not tool_data.get("source_commit"):
            warnings.append(f"tool '{tool_name}' is built-from-source but unpinned source")
        elif not RE_COMMIT.fullmatch(str(tool_data["source_commit"])):
            errors.append(
                f"tool '{tool_name}' source_commit is not a 40-char hex SHA"
            )
        for patch in tool_data.get("patches", []):
            patch_path = patch.get("path", "")
            if not os.path.exists(os.path.join(root, "patches", patch_path)):
                errors.append(
                    f"tool '{tool_name}' patch '{patch_path}' not found under patches/"
                )
            if not RE_SHA256.fullmatch(str(patch.get("sha256", ""))):
                errors.append(
                    f"tool '{tool_name}' patch '{patch_path}' has an invalid sha256"
                )

    if provenance == "npm-package":
        dist_integrity = tool_data.get("dist_integrity")
        has_package = "package" in tool_data or "npm_package" in tool_data
        refreshed = build_flavor is not None or dist_integrity is not None
        if not refreshed:
            warnings.append(
                f"tool '{tool_name}' is a legacy npm-package entry "
                "(no package/dist_integrity recorded)"
            )
        else:
            if not has_package:
                errors.append(f"npm-package tool '{tool_name}' must declare 'package'")
            if not dist_integrity or not RE_SHA256_OR_SHA512.match(str(dist_integrity)):
                errors.append(
                    f"npm-package tool '{tool_name}' dist_integrity must start with "
                    "'sha512-' or 'sha256-'"
                )


def _validate_platforms(tool_name, tool_data, errors, warnings):
    platforms = tool_data.get("platforms", {})
    if not platforms:
        errors.append(f"tool '{tool_name}' has no platforms")
        return
    for plat_key, plat_data in platforms.items():
        where = f"{tool_name}:{plat_key}"
        if plat_key not in ALLOWED_PLATFORMS:
            errors.append(f"{where} platform key is not allowed")
            continue

        os_name, arch_name = plat_key.split("/")
        path = plat_data.get("path", "")
        parts = str(path).split("/")
        if len(parts) != 3 or parts[0] != os_name or parts[1] != arch_name:
            errors.append(
                f"{where} path {path!r} must equal <os>/<arch>/<basename> for its key"
            )
        else:
            basename = parts[2]
            if not RE_BASENAME.fullmatch(basename):
                errors.append(f"{where} basename {basename!r} is not allowed")
        if ".." in str(path):
            errors.append(f"{where} path {path!r} must not contain '..'")
        if os_name == "windows" and not str(path).endswith(".exe"):
            errors.append(f"{where} windows path {path!r} must end with .exe")

        if not RE_SHA256.fullmatch(str(plat_data.get("sha256", ""))):
            errors.append(f"{where} sha256 is not 64 hex characters")

        size = plat_data.get("size")
        if not isinstance(size, int) or isinstance(size, bool) or size < 1:
            errors.append(f"{where} size must be an integer >= 1")

        status = plat_data.get("status")
        if status not in ALLOWED_STATUS:
            errors.append(f"{where} status {status!r} is not allowed")
        elif status == "mismatch":
            errors.append(f"{where} status is 'mismatch'")
        elif status == "unverified":
            if not plat_data.get("note"):
                errors.append(f"{where} status 'unverified' requires a non-empty note")
            else:
                warnings.append(f"{where} status is 'unverified': {plat_data['note']}")

        if tool_name == "nkit":
            if "nkit/" in str(path):
                errors.append(f"{where} nkit path must not contain 'nkit/'")
            if "nkds" in str(path):
                errors.append(f"{where} nkit path must not reference 'nkds'")
            if parts and os.path.basename(str(path)) not in ("nkit", "nkit.exe"):
                errors.append(f"{where} nkit binary must be named nkit or nkit.exe")


def _validate_same_as(manifest, errors):
    index = {}
    for tool_name, tool_data in manifest.get("tools", {}).items():
        for plat_key, plat_data in tool_data.get("platforms", {}).items():
            path = plat_data.get("path")
            if path:
                index[path] = (tool_name, plat_key, plat_data)

    for tool_name, tool_data in manifest.get("tools", {}).items():
        for plat_key, plat_data in tool_data.get("platforms", {}).items():
            same_as = plat_data.get("same_as")
            if not same_as:
                continue
            where = f"{tool_name}:{plat_key}"
            if same_as == plat_data.get("path"):
                errors.append(f"{where} same_as points at itself")
                continue
            target = index.get(same_as)
            if target is None:
                errors.append(f"{where} same_as '{same_as}' does not exist in the manifest")
                continue
            target_tool, _, target_data = target
            if target_tool != tool_name:
                errors.append(f"{where} same_as '{same_as}' belongs to a different tool")
                continue
            if target_data.get("same_as"):
                errors.append(
                    f"{where} same_as '{same_as}' itself has same_as (chains/cycles not allowed)"
                )
                continue
            if plat_data.get("sha256") != target_data.get("sha256"):
                errors.append(f"{where} same_as '{same_as}' has a different sha256")
            if plat_data.get("size") != target_data.get("size"):
                errors.append(f"{where} same_as '{same_as}' has a different size")


def _validate_hash_sharing(manifest, errors):
    groups = {}
    for tool_name, tool_data in manifest.get("tools", {}).items():
        for plat_key, plat_data in tool_data.get("platforms", {}).items():
            sha = plat_data.get("sha256")
            if sha:
                groups.setdefault(sha, []).append((tool_name, plat_key, plat_data))

    for sha, entries in groups.items():
        if len(entries) < 2:
            continue
        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                t1, k1, d1 = entries[i]
                t2, k2, d2 = entries[j]
                os1 = k1.split("/")[0] if "/" in k1 else k1
                os2 = k2.split("/")[0] if "/" in k2 else k2
                arch1 = k1.split("/")[1] if "/" in k1 else ""
                arch2 = k2.split("/")[1] if "/" in k2 else ""
                where = f"{t1}:{k1} vs {t2}:{k2}"

                if t1 == t2 and os1 == os2 and arch1 != arch2:
                    both_universal = bool(d1.get("universal")) and bool(d2.get("universal"))
                    if not (both_universal and os1 == "macos"):
                        errors.append(
                            f"{where} identical sha256 on two arches requires "
                            "'universal: true' on both (macos only)"
                        )
                elif os1 != os2 or t1 != t2:
                    if not (d1.get("same_as") or d2.get("same_as")):
                        errors.append(
                            f"{where} identical sha256 across OSes/tools requires "
                            "'same_as' on one side"
                        )


def _validate_universal(manifest, errors):
    for tool_name, tool_data in manifest.get("tools", {}).items():
        platforms = tool_data.get("platforms", {})
        for plat_key, plat_data in platforms.items():
            if not plat_data.get("universal"):
                continue
            where = f"{tool_name}:{plat_key}"
            os_name, arch_name = plat_key.split("/", 1) if "/" in plat_key else (plat_key, "")
            if os_name != "macos":
                errors.append(f"{where} 'universal' is only allowed for macos")
                continue
            other_arch = "x86_64" if arch_name == "arm64" else "arm64"
            other = platforms.get(f"macos/{other_arch}")
            if other is None:
                errors.append(f"{where} has 'universal' but no macos/{other_arch} entry")
            elif other.get("sha256") != plat_data.get("sha256"):
                errors.append(
                    f"{where} 'universal' requires the same sha256 as macos/{other_arch}"
                )


def _validate_generated_files(manifest, root, errors):
    checksums_path = os.path.join(root, "checksums.sha256")
    if not os.path.exists(checksums_path):
        errors.append("checksums.sha256 not found")
    else:
        with open(checksums_path, "rb") as f:
            raw = f.read()
        text = raw.decode("utf-8", errors="replace")
        if "\r" in text:
            errors.append("checksums.sha256 must use LF line endings only")
        if text != expected_checksums(manifest):
            errors.append("checksums.sha256 is out of date with manifest.json")

    versions_path = os.path.join(root, "versions.json")
    if not os.path.exists(versions_path):
        errors.append("versions.json not found")
    else:
        with open(versions_path, "r", encoding="utf-8") as f:
            actual = f.read()
        if actual != expected_versions(manifest):
            errors.append("versions.json is out of date with manifest.json")

    sources_path = os.path.join(root, "SOURCES.md")
    if render_sources is None:
        errors.append("gen_sources.py not importable; cannot check SOURCES.md")
    elif not os.path.exists(sources_path):
        errors.append("SOURCES.md not found")
    else:
        with open(sources_path, "r", encoding="utf-8") as f:
            actual_sources = f.read()
        if actual_sources != render_sources(manifest):
            errors.append("SOURCES.md is out of date with manifest.json")


def validate(manifest, root, strict=False):
    """Return (errors, warnings) for a manifest. With strict=True, warnings
    are folded into errors and the warning list is returned empty."""
    errors = []
    warnings = []

    if not isinstance(manifest, dict):
        return (["manifest is not a JSON object"], [])

    _validate_schema(manifest, root, errors, warnings)

    tools = manifest.get("tools")
    if not isinstance(tools, dict) or not tools:
        errors.append("manifest has no 'tools' object")
        tools = {}

    for tool_name, tool_data in tools.items():
        if not isinstance(tool_data, dict):
            errors.append(f"tool '{tool_name}' is not an object")
            continue
        _validate_tool_fields(tool_name, tool_data, manifest, root, errors, warnings)
        _validate_platforms(tool_name, tool_data, errors, warnings)

    _validate_same_as(manifest, errors)
    _validate_hash_sharing(manifest, errors)
    _validate_universal(manifest, errors)
    _validate_generated_files(manifest, root, errors)

    if strict:
        errors = errors + warnings
        warnings = []

    return errors, warnings


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate manifest.json")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="treat warnings as errors (CI currently runs non-strict)",
    )
    parser.add_argument("--manifest", help="path to manifest.json")
    parser.add_argument("--root", help="repository root (defaults to repo root)")
    args = parser.parse_args(argv)

    root = args.root or repo_root()
    manifest_path = args.manifest or os.path.join(root, "manifest.json")

    if not os.path.exists(manifest_path):
        print(f"Error: manifest.json not found at {manifest_path}", file=sys.stderr)
        return 1

    manifest = load_json(manifest_path)
    errors, warnings = validate(manifest, root, strict=args.strict)

    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)

    if errors:
        print(f"Manifest validation FAILED: {len(errors)} error(s), {len(warnings)} warning(s)")
        return 1
    print(f"Manifest validation passed successfully! ({len(warnings)} warning(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
