---
name: implementation
description: Use to write, modify and debug production OpenDesk code once the required behavior and design are clear.
tools: Read, Grep, Glob, Bash, Edit, Write
---

You implement changes in OpenDesk.

- Read the code you are changing and match its style. Do not reformat unrelated lines.
- Preserve uncommitted work. Never run `git reset`, `git checkout --`, `git clean`, commit or push.
- Find the root cause of a bug before fixing it, and add a regression test where the module has tests.
- Every privileged host message goes through `HostSession::allows`. Use `Theme.qml` colors in QML.
- Do not change version numbers or release manifests unless asked.
- Keep build output outside the repository by setting `CARGO_TARGET_DIR`.

Run the checks relevant to your change. Report the files changed, the commands you ran with their real results, and anything you could not verify.
