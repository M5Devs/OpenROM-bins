#!/usr/bin/env python3
import json
import os
import re
import sys
import jsonschema

def load_json(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)

def validate_manifest():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    manifest_path = os.path.join(repo_root, "manifest.json")
    schema_path = os.path.join(repo_root, "schema", "manifest.schema.json")
    checksums_path = os.path.join(repo_root, "checksums.sha256")
    versions_path = os.path.join(repo_root, "versions.json")

    # 1. Validate JSON schema
    manifest = load_json(manifest_path)
    schema = load_json(schema_path)

    try:
        jsonschema.validate(instance=manifest, schema=schema)
    except jsonschema.ValidationError as e:
        print(f"Manifest schema validation error: {e.message}", file=sys.stderr)
        return False

    tools = manifest.get("tools", {})
    all_paths = set()
    hash_to_paths = {}

    # 2. Check generated files consistency
    gen_checksum_lines = []
    gen_versions = {}

    for tool_name, tool_data in tools.items():
        # Validate tool level required attributes
        if not tool_data.get("version"):
            print(f"Tool '{tool_name}' missing version", file=sys.stderr)
            return False
        if not tool_data.get("license"):
            print(f"Tool '{tool_name}' missing license", file=sys.stderr)
            return False

        gen_versions[tool_name] = tool_data["version"]

        provenance = tool_data.get("provenance")
        if provenance == "built-from-source":
            # For built-from-source, source_commit required if not legacy
            source_commit = tool_data.get("source_commit")
            build_flavor = tool_data.get("build_flavor")
            if tool_name == "nkit":
                if build_flavor != "nativeaot" and build_flavor != "legacy-unknown":
                    print(f"NKit build_flavor must be 'nativeaot' or 'legacy-unknown', got '{build_flavor}'", file=sys.stderr)
                    return False
            if source_commit and not re.match(r"^[0-9a-fA-F]{40}$", source_commit):
                print(f"Tool '{tool_name}' invalid source_commit SHA: {source_commit}", file=sys.stderr)
                return False

        platforms = tool_data.get("platforms", {})
        for plat_key, plat_data in platforms.items():
            path = plat_data["path"]
            sha256 = plat_data["sha256"]

            # Unique path check
            if path in all_paths:
                print(f"Duplicate path in manifest: {path}", file=sys.stderr)
                return False
            all_paths.add(path)

            hash_to_paths.setdefault(sha256, []).append((tool_name, plat_key, path, plat_data))

            # Check NKit single-file rule
            if tool_name == "nkit":
                if "nkit/" in path or "nkds" in path:
                    print(f"Forbidden NKit path structure (must be single file): {path}", file=sys.stderr)
                    return False
                filename = os.path.basename(path)
                if filename not in ["nkit", "nkit.exe"]:
                    print(f"Invalid NKit binary name: {path}", file=sys.stderr)
                    return False

            gen_checksum_lines.append(f"{sha256}  {path}")

    # 3. Check hash sharing rules
    for sha256, entries in hash_to_paths.items():
        if len(entries) > 1:
            for i in range(len(entries)):
                for j in range(i + 1, len(entries)):
                    t1, p1, path1, data1 = entries[i]
                    t2, p2, path2, data2 = entries[j]

                    os1, arch1 = p1.split("/") if "/" in p1 else (p1, "")
                    os2, arch2 = p2.split("/") if "/" in p2 else (p2, "")

                    # Same tool + same OS + different arch -> universal flag required
                    if t1 == t2 and os1 == os2 and arch1 != arch2:
                        if not data1.get("universal") or not data2.get("universal"):
                            print(f"Same tool/OS across arches must specify 'universal: true': {path1} vs {path2}", file=sys.stderr)
                            return False

                    # Identical files across different OSes / entries require explicit 'same_as'
                    if os1 != os2 or t1 != t2:
                        has_same_as = data1.get("same_as") or data2.get("same_as")
                        if not has_same_as:
                            print(f"Shared hash across different OSes/tools requires 'same_as': {path1} vs {path2}", file=sys.stderr)
                            return False

    # 4. Verify checksums.sha256 on disk matches
    gen_checksum_lines.sort(key=lambda line: line.split(None, 1)[1])
    expected_checksums_content = "\n".join(gen_checksum_lines) + "\n"
    with open(checksums_path, "rb") as f:
        actual_checksums_content = f.read().decode("utf-8")

    if actual_checksums_content != expected_checksums_content:
        print("checksums.sha256 is out of date with manifest.json!", file=sys.stderr)
        return False

    # 5. Verify versions.json on disk matches
    sorted_versions = dict(sorted(gen_versions.items()))
    expected_versions_content = json.dumps(sorted_versions, indent=2) + "\n"
    with open(versions_path, "r", encoding="utf-8") as f:
        actual_versions_content = f.read()

    if actual_versions_content != expected_versions_content:
        print("versions.json is out of date with manifest.json!", file=sys.stderr)
        return False

    print("Manifest validation passed successfully!")
    return True

if __name__ == "__main__":
    if not validate_manifest():
        sys.exit(1)
