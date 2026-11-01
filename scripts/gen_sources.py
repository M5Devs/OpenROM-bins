#!/usr/bin/env python3
"""Generate SOURCES.md from manifest.json.

The provenance record is derived from the manifest alone so the two can never
drift. Any field the manifest does not carry is written as ``unknown`` rather
than guessed. ``validate_manifest.py`` fails when SOURCES.md differs from
``render_sources()``.
"""
import argparse
import json
import os
import sys

HEADER = "Generated from manifest.json - do not edit by hand"
UNKNOWN = "unknown"
COLUMNS = [
    "Tool",
    "Version",
    "Upstream Repo",
    "Provenance",
    "Source Ref",
    "Source Commit",
    "Toolchain",
    "Patches",
    "Notes",
]


def _value(value):
    if value is None or value == "":
        return UNKNOWN
    return str(value)


def _patches(tool_data):
    patches = tool_data.get("patches")
    if not patches:
        return UNKNOWN
    return ", ".join(str(p.get("path", UNKNOWN)) for p in patches)


def _version(tool_name, tool_data):
    alias = tool_data.get("version_alias_of")
    if alias:
        return f"same as {alias}"
    return _value(tool_data.get("version"))


def render_sources(manifest):
    """Return the full SOURCES.md text for a manifest dict."""
    lines = [
        "# Corresponding Source Code & Provenance Record",
        "",
        HEADER,
        "",
        "This document records the upstream repositories, pinned source references,",
        "commit SHAs, provenance, toolchains and patches for every binary tracked in",
        "`manifest.json`. Fields the manifest does not record are shown as `unknown`.",
        "",
        "| " + " | ".join(COLUMNS) + " |",
        "|" + "|".join(["------"] * len(COLUMNS)) + "|",
    ]

    tools = manifest.get("tools", {})
    for tool_name in sorted(tools):
        tool_data = tools[tool_name]
        row = [
            tool_name,
            _version(tool_name, tool_data),
            _value(tool_data.get("upstream_repo")),
            _value(tool_data.get("provenance")),
            _value(tool_data.get("source_ref")),
            _value(tool_data.get("source_commit")),
            _value(tool_data.get("toolchain")),
            _patches(tool_data),
            _value(tool_data.get("note")),
        ]
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines) + "\n"


def generate(repo_root=None):
    repo_root = repo_root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    manifest_path = os.path.join(repo_root, "manifest.json")
    sources_path = os.path.join(repo_root, "SOURCES.md")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    with open(sources_path, "w", encoding="utf-8") as f:
        f.write(render_sources(manifest))

    print(f"Successfully generated SOURCES.md ({len(manifest.get('tools', {}))} tools).")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate SOURCES.md from manifest.json")
    parser.add_argument("--root", help="repository root (defaults to repo root)")
    args = parser.parse_args(argv)
    generate(args.root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
