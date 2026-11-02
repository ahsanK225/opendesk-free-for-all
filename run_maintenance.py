"""Installer helper: no GUI/audio/media dependencies and no blocking error dialogs."""
if __name__ == '__main__':
    try:
        from common.launcher import shutdown_main
        result=shutdown_main()
    except Exception:
        result=2
    raise SystemExit(result)
