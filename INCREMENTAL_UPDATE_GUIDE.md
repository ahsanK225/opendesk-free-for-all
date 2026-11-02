# Update distribution in v2

The packaged desktop application uses complete, SHA-256-verified EXE updates from the official GitHub release path. Source checkouts update through Git. The manifest must include `version`, `download_url` and `sha256`; `build.ps1` generates an artifact manifest after compilation. Publish immutable versioned assets and commit the matching manifest. The main process closes before the external helper copies files. An unsigned manifest does not independently protect against compromise of the GitHub release account.

`common/incremental_updater.py` remains a tested standalone library. It validates canonical paths under its install/staging/backup roots, checks each file hash at download and apply, preserves configured files, deletes only previously owned paths, and rolls back additions/overwrites on failure. It is not enabled for running monolithic desktop builds.

Use `scripts/publish_release.py <artifact-directory>` to create a draft after pushing a version tag. Verify uploaded hashes and release notes, then publish the draft. Existing release asset replacement is disabled by the legacy helper. Release signing requires a supplied trusted certificate; the build never installs a self-signed trust root.
