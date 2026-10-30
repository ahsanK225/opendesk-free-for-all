import os
import sys
import json
import time
import urllib.request
import subprocess

def get_github_token() -> str:
    p = subprocess.Popen(['git', 'credential', 'fill'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, _ = p.communicate('protocol=https\nhost=github.com\n\n')
    for line in out.splitlines():
        if line.startswith('password='):
            return line.split('=', 1)[1].strip()
    raise RuntimeError("GitHub token not found in git credential manager")

def main():
    token = get_github_token()
    headers = {
        'Authorization': f'token {token}',
        'User-Agent': 'OpenDesk-ReleaseBot',
        'Accept': 'application/vnd.github.v3+json'
    }

    # Fetch release
    req = urllib.request.Request('https://api.github.com/repos/ahsanK225/opendesk-free-for-all/releases/tags/v1.2.0', headers=headers)
    with urllib.request.urlopen(req) as resp:
        rel = json.loads(resp.read())

    print(f"Found release ID: {rel['id']}")
    upload_url_template = rel['upload_url']
    base_upload_url = upload_url_template.split('{')[0]

    # Delete old assets
    for a in rel.get('assets', []):
        print(f"Deleting old asset {a['name']} (ID: {a['id']})...")
        del_req = urllib.request.Request(f"https://api.github.com/repos/ahsanK225/opendesk-free-for-all/releases/assets/{a['id']}", headers=headers, method='DELETE')
        with urllib.request.urlopen(del_req) as del_resp:
            print(f"Deleted {a['name']}: HTTP {del_resp.status}")

    # Files to upload
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    files = [
        ('OpenDesk_Setup_v1.2.0_Installer.exe', os.path.join(base_dir, 'OpenDesk_Setup_v1.2.0_Installer.exe')),
        ('OpenDesk_v1.2.0_Portable.exe', os.path.join(base_dir, 'OpenDesk_v1.2.0_Portable.exe'))
    ]

    for aname, fpath in files:
        size = os.path.getsize(fpath)
        print(f"Uploading {aname} ({size / (1024*1024):.2f} MB)...")
        with open(fpath, 'rb') as f:
            data = f.read()
        u_headers = {
            'Authorization': f'token {token}',
            'User-Agent': 'OpenDesk-ReleaseBot',
            'Content-Type': 'application/octet-stream',
            'Content-Length': str(len(data))
        }
        u_req = urllib.request.Request(f"{base_upload_url}?name={aname}", data=data, headers=u_headers, method='POST')
        
        uploaded = False
        for attempt in range(1, 4):
            try:
                with urllib.request.urlopen(u_req, timeout=120) as u_resp:
                    u_data = json.loads(u_resp.read())
                    print(f"✓ Successfully uploaded {aname} -> {u_data.get('browser_download_url')}")
                    uploaded = True
                    break
            except Exception as e:
                print(f"[Attempt {attempt}/3] Upload error for {aname}: {e}. Retrying in 3 seconds...")
                time.sleep(3)
        if not uploaded:
            raise RuntimeError(f"Failed to upload {aname} after 3 attempts")

    print("\nVerifying live download URLs...")
    for aname, _ in files:
        dl_url = f"https://github.com/ahsanK225/opendesk-free-for-all/releases/download/v1.2.0/{aname}"
        try:
            head_req = urllib.request.Request(dl_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(head_req) as r:
                print(f"✓ {aname} is live! HTTP {r.status} (Size: {r.headers.get('content-length')} bytes)")
        except Exception as e:
            print(f"✗ Check failed for {aname}: {e}")

if __name__ == '__main__':
    main()
