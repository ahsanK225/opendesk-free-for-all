# OpenDesk 2.0.2 — Windows runtime loading hotfix

Fixes packaging problems that can prevent Python DLL loading on Windows 10. The earlier build environment exposed unrelated Windows 11 CRT/API DLLs to PyInstaller. These OS files are now excluded and build PATH is restricted to Python and Windows.

- The installer deploys the application and its _internal runtime to a permanent installation folder. Installed startup no longer depends on onefile extraction in TEMP.
- Portable remains a standalone executable with corrected dependencies.
- Independent update restarts reset inherited PyInstaller state to avoid reusing an expired extraction directory.
- Installed bundles use an installer update with its own expected SHA-256. Existing settings and device identity are preserved.
- The bounded graceful/force-close installer flow and single-instance launcher remain in place.
- Incorrect hard-coded Authenticode signing claims were removed. These artifacts are unsigned.

Install v2.0.2 over the existing version. No manual Python DLL installation is required. See docs/RELEASE_VALIDATION_2.0.2.md for evidence. Rust/Qt work remains on the separate draft migration branch.
