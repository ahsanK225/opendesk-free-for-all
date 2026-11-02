"""Fail releases containing OS DLLs from a foreign build SDK."""
import argparse
from pathlib import Path, PureWindowsPath
import re
from tools.build_policy import application_binaries


def audit(target):
    target = Path(target)
    if target.is_dir():
        names = [str(p.relative_to(target / '_internal')) for p in (target / '_internal').rglob('*') if p.is_file()]
    else:
        from PyInstaller.archive.readers import CArchiveReader
        names = list(CArchiveReader(str(target)).toc)
    forbidden = [name for name in names if not application_binaries([(name, '', '')])]
    python = any(re.fullmatch(r'python3\d+\.dll', PureWindowsPath(name).name.lower()) for name in names)
    if forbidden or not python:
        raise RuntimeError(f'Invalid runtime package {target.name}: python={python}, forbidden={forbidden}')
    return {'artifact': target.name, 'python_dll': python, 'forbidden': forbidden}


def main():
    import json
    parser = argparse.ArgumentParser()
    parser.add_argument('targets', nargs='+')
    args = parser.parse_args()
    print(json.dumps([audit(target) for target in args.targets], indent=2))


if __name__ == '__main__':
    main()
