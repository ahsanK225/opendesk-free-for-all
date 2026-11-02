"""Run PyInstaller without unrelated SDK DLL directories on PATH."""
import os
import sys
from tools.build_policy import clean_build_path


def main():
    os.environ['PATH'] = clean_build_path()
    from PyInstaller.__main__ import run
    run(sys.argv[1:])


if __name__ == '__main__':
    main()
