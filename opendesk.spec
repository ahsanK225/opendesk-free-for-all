# Windows x64 portable build. Run from repository root.
from PyInstaller.utils.hooks import collect_data_files, copy_metadata
from pathlib import Path
import os

runtime = Path('.build-deps')
notices = []
for distribution in ('pillow','numpy','aiohttp','sounddevice','cryptography','cffi','pycparser','dxcam','comtypes'):
    notices += copy_metadata(distribution)
a = Analysis(['opendesk_app.py'], pathex=['.', str(runtime)] if runtime.exists() else ['.'],
    binaries=[],
    datas=[('web','web'),('bin/cloudflared.exe','bin')] + collect_data_files('_sounddevice_data') + notices + [('THIRD_PARTY_NOTICES.md','.'),('LICENSE','.')],
    hiddenimports=['sounddevice','_cffi_backend','client.files','dxcam','dxcam.processor.numpy_processor'],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['pytest','IPython','matplotlib','pandas','scipy'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz,a.scripts,a.binaries,a.datas,[],name='OpenDeskDiagnostic' if os.environ.get('OPENDESK_CONSOLE_BUILD') else 'OpenDesk',debug=False,
    strip=False,upx=False,console=bool(os.environ.get("OPENDESK_CONSOLE_BUILD")),icon='opendesk.ico',version='version_info.txt')
