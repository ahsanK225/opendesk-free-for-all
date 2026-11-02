from tools.build_policy import application_binaries
a = Analysis(['run_maintenance.py'], pathex=['.'], binaries=[], datas=[], hiddenimports=[],
             hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False)
a.binaries = application_binaries(a.binaries)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='OpenDeskSetupHelper',
          debug=False, strip=False, upx=False, console=False)
