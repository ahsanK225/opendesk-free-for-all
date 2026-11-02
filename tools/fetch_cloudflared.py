"""Fetch a pinned official Cloudflare binary and verify its release asset digest."""
import hashlib
import os
import shutil
import urllib.request
from pathlib import Path

VERSION='2026.9.3'
SHA256='f096265ec2fcbe9bb6e2d64268db167ced3fcbb83d894bdb9e2fcdb26f2ea7e2'
URL=f'https://github.com/cloudflare/cloudflared/releases/download/{VERSION}/cloudflared-windows-amd64.exe'

def digest(path):
    with open(path,'rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()

def main():
    target=Path(__file__).resolve().parents[1]/'bin'/'cloudflared.exe'
    if target.exists() and digest(target)==SHA256: return
    installed=shutil.which('cloudflared')
    if installed and digest(installed)==SHA256:
        shutil.copy2(installed,target)
        return
    temporary=target.with_suffix('.download')
    try:
        with urllib.request.urlopen(URL,timeout=60) as source, open(temporary,'wb') as destination:
            shutil.copyfileobj(source,destination)
        if digest(temporary)!=SHA256: raise ValueError('Cloudflare release digest mismatch')
        os.replace(temporary,target)
    finally:
        if temporary.exists(): temporary.unlink()

if __name__=='__main__': main()
