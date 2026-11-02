"""Publish reviewed artifacts with gh; never extract or print stored credentials."""
import argparse
import json
from pathlib import Path
import subprocess


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('artifacts',type=Path)
    parser.add_argument('--repo',default='ahsanK225/opendesk-free-for-all')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    version=json.loads((root/'version.json').read_text(encoding='utf-8-sig'))['version']
    names=[f'OpenDesk_v{version}_Portable.exe',f'OpenDesk_Setup_v{version}_Installer.exe','SHA256SUMS.txt','version.json']
    files=[args.artifacts/name for name in names]
    for file in files:
        if not file.is_file(): parser.error('Missing artifact: '+str(file))
    subprocess.run(['gh','release','create','v'+version,*map(str,files),'--repo',args.repo,
                    '--verify-tag','--title','OpenDesk '+version+' — Performance and security upgrade',
                    '--notes-file',str(root/'RELEASE_NOTES.md'),'--draft'],check=True)
    print('Draft release created. Verify uploaded digests, then publish the draft with gh release edit.')

if __name__=='__main__': main()
