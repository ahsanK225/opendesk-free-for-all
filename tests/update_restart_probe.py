"""Frozen integration fixture for a self-update that outlives its onefile parent."""
import json
import os
from pathlib import Path
import shutil
import sys
from common.updater import apply_update_and_restart, compute_file_sha256

directory = Path(sys.executable).parent
marker = directory / 'restart-marker.json'
output = directory / 'restart-result.json'
if marker.exists():
    output.write_text(json.dumps({'pid': os.getpid(), 'runtime': sys._MEIPASS,
                                 'runtime_exists': Path(sys._MEIPASS).is_dir(),
                                 'previous_runtime': json.loads(marker.read_text())['runtime']}))
else:
    marker.write_text(json.dumps({'runtime': sys._MEIPASS}))
    staged = directory / 'staged-update.exe'
    shutil.copy2(sys.executable, staged)
    apply_update_and_restart(str(staged), expected_sha256=compute_file_sha256(staged))
