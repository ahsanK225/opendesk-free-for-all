"""
Release Manifest Generator for RemoteConnect / OpenDesk
Recursively inspects a release directory, calculates SHA-256 hashes and file sizes,
and produces a standardized versioned manifest.json for incremental distribution.
"""

import os
import sys
import json
import argparse
import time
from typing import List, Dict, Any, Optional

# Add repo root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.incremental_updater import compute_file_sha256, DEFAULT_PRESERVE_PATTERNS


def generate_release_manifest(
    source_dir: str,
    version: str,
    base_url: str,
    app_name: str = "RemoteConnect",
    changelog: Optional[List[str]] = None,
    preserve_patterns: Optional[List[str]] = None,
    exclude_patterns: Optional[List[str]] = None,
    output_file: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate an incremental release manifest dictionary and optionally save to file.
    """
    source_dir = os.path.abspath(source_dir)
    if not os.path.isdir(source_dir):
        raise FileNotFoundError(f"Source release directory not found: {source_dir}")

    preserve_patterns = preserve_patterns or list(DEFAULT_PRESERVE_PATTERNS)
    exclude_patterns = exclude_patterns or [
        "*.pyc",
        "__pycache__/*",
        "*.git*",
        ".update_*",
        "*.pdb",
        "*.tmp",
    ]

    files_list: List[Dict[str, Any]] = []
    total_size = 0

    for root, _, filenames in os.walk(source_dir):
        for fname in sorted(filenames):
            abs_path = os.path.join(root, fname)
            rel_path = os.path.relpath(abs_path, source_dir).replace("\\", "/")

            # Skip manifest itself if present
            if rel_path in ("manifest.json", "version.json"):
                continue

            # Check exclusions
            import fnmatch
            if any(fnmatch.fnmatch(rel_path, pat) or fnmatch.fnmatch(fname, pat) for pat in exclude_patterns):
                continue

            file_size = os.path.getsize(abs_path)
            sha256_hash = compute_file_sha256(abs_path)
            total_size += file_size

            files_list.append({
                "path": rel_path,
                "size": file_size,
                "sha256": sha256_hash,
                "action": "replace",
            })

    manifest: Dict[str, Any] = {
        "app_name": app_name,
        "version": version,
        "release_date": time.strftime("%Y-%m-%d"),
        "base_url": base_url.rstrip("/") + "/",
        "total_install_size": total_size,
        "total_files_count": len(files_list),
        "changelog": changelog or [f"Release {version} with incremental differential updates."],
        "preserve": preserve_patterns,
        "files": files_list,
    }

    if output_file:
        os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        print(f"[ManifestGenerator] Generated manifest for {len(files_list)} files ({total_size / (1024*1024):.2f} MB) -> {output_file}")

    return manifest


def main():
    parser = argparse.ArgumentParser(description="Generate RemoteConnect / OpenDesk Incremental Release Manifest")
    parser.add_argument("--dir", required=True, help="Path to release directory containing files")
    parser.add_argument("--version", required=True, help="Release version (e.g. 1.2.0)")
    parser.add_argument("--base-url", required=True, help="Base CDN or HTTP URL where files are served")
    parser.add_argument("--output", help="Path to save output manifest.json (default: <dir>/manifest.json)")
    parser.add_argument("--app-name", default="RemoteConnect", help="Application Name")
    parser.add_argument("--notes", nargs="*", help="Changelog release notes")

    args = parser.parse_args()
    output_path = args.output or os.path.join(args.dir, "manifest.json")

    generate_release_manifest(
        source_dir=args.dir,
        version=args.version,
        base_url=args.base_url,
        app_name=args.app_name,
        changelog=args.notes,
        output_file=output_path,
    )


if __name__ == "__main__":
    main()
