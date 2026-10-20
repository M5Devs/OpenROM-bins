#!/usr/bin/env python3
import json
import os

def generate_files():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    manifest_path = os.path.join(repo_root, "manifest.json")
    checksums_path = os.path.join(repo_root, "checksums.sha256")
    versions_path = os.path.join(repo_root, "versions.json")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    checksum_lines = []
    versions_dict = {}

    tools = manifest.get("tools", {})
    for tool_name, tool_data in tools.items():
        if "version" in tool_data:
            versions_dict[tool_name] = tool_data["version"]

        platforms = tool_data.get("platforms", {})
        for plat_key, plat_data in platforms.items():
            path = plat_data["path"]
            sha256 = plat_data["sha256"]
            checksum_lines.append(f"{sha256}  {path}")

    # Sort checksum lines by relative path
    checksum_lines.sort(key=lambda line: line.split(None, 1)[1])

    # Write checksums.sha256 with LF line endings
    checksums_content = "\n".join(checksum_lines) + "\n"
    with open(checksums_path, "wb") as f:
        f.write(checksums_content.encode("utf-8"))

    # Write versions.json (sorted keys, 2 space indent)
    sorted_versions = dict(sorted(versions_dict.items()))
    with open(versions_path, "w", encoding="utf-8") as f:
        json.dump(sorted_versions, f, indent=2)
        f.write("\n")

    print(f"Successfully generated checksums.sha256 ({len(checksum_lines)} entries) and versions.json.")

if __name__ == "__main__":
    generate_files()
