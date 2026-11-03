# Native update delivery

The native application uses complete, SHA-256-verified releases. The old Python source/delta patch updater has been replaced.

1. An explicit check reads the repository's stable `version.json` over HTTPS.
2. The engine accepts a newer stable semantic version and only the exact official GitHub release URL/filename for that version.
3. Download size is bounded and the expected digest is checked before staging a separate native helper.
4. The helper waits for the main process and portable parent to exit, then checks the staged EXE again.
5. Installed builds apply the installer to the existing install directory. Portable builds retain the previous launcher and use atomic replacement before restarting.

Existing configuration and device identity are preserved. Development builds are not overwritten by the updater. Preview releases are separate from the stable update channel. A digest detects a corrupted or mismatched download; it is not a claim of a publicly trusted Authenticode signature.
