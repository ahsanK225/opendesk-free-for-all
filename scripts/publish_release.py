import os
import sys
import json
import urllib.request
import subprocess

def get_github_token() -> str:
    p = subprocess.Popen(['git', 'credential', 'fill'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, _ = p.communicate('protocol=https\nhost=github.com\n\n')
    for line in out.splitlines():
        if line.startswith('password='):
            return line.split('=', 1)[1].strip()
    raise RuntimeError("GitHub token not found in git credential manager")

def create_or_get_release(token: str, tag_name: str, name: str, body: str) -> dict:
    headers = {
        'Authorization': f'token {token}',
        'User-Agent': 'OpenDesk-ReleaseBot',
        'Accept': 'application/vnd.github.v3+json'
    }
    # Check if release exists
    get_url = f'https://api.github.com/repos/ahsanK225/opendesk-free-for-all/releases/tags/{tag_name}'
    req = urllib.request.Request(get_url, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
            print(f"Release {tag_name} already exists (ID: {data['id']})")
            return data
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise

    # Create release
    create_url = 'https://api.github.com/repos/ahsanK225/opendesk-free-for-all/releases'
    payload = {
        'tag_name': tag_name,
        'name': name,
        'body': body,
        'draft': False,
        'prerelease': False
    }
    data_bytes = json.dumps(payload).encode('utf-8')
    post_req = urllib.request.Request(create_url, data=data_bytes, headers=headers, method='POST')
    with urllib.request.urlopen(post_req) as resp:
        rel = json.loads(resp.read())
        print(f"Created release {tag_name} (ID: {rel['id']})")
        return rel

def upload_asset(token: str, upload_url_template: str, file_path: str, asset_name: str):
    if not os.path.exists(file_path):
        print(f"Skipping {asset_name}: {file_path} not found")
        return

    # upload_url_template is like "https://uploads.github.com/repos/.../releases/123/assets{?name,label}"
    base_upload_url = upload_url_template.split('{')[0]
    upload_url = f"{base_upload_url}?name={asset_name}"

    file_size = os.path.getsize(file_path)
    print(f"Uploading {asset_name} ({file_size / (1024*1024):.2f} MB)...")

    with open(file_path, 'rb') as f:
        data = f.read()

    headers = {
        'Authorization': f'token {token}',
        'User-Agent': 'OpenDesk-ReleaseBot',
        'Content-Type': 'application/octet-stream',
        'Content-Length': str(len(data))
    }
    req = urllib.request.Request(upload_url, data=data, headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req) as resp:
            res = json.loads(resp.read())
            print(f"✓ Uploaded {asset_name} -> {res.get('browser_download_url')}")
    except urllib.error.HTTPError as e:
        err_body = e.read().decode('utf-8', errors='ignore')
        if 'already_exists' in err_body:
            print(f"Asset {asset_name} already exists in this release.")
        else:
            print(f"Error uploading {asset_name}: {e.code} {err_body}")

def main():
    token = get_github_token()
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

    tag = "v1.1.7"
    title = "OpenDesk v1.1.7 - AnyDesk Incoming Session Request Dialog & Permissions"
    body = """## What's New in OpenDesk v1.1.7

- **AnyDesk-style Incoming Connection Request Dialog**: Displays a prominent, topmost incoming dialog on the host PC accompanied by an audio alert chime.
- **Granular Session Permissions**: Host user can toggle permissions before accepting:
  - Allow Remote Mouse & Keyboard Control (supports View-Only mode)
  - Allow Voice / Audio Call
  - Allow Bidirectional Clipboard Synchronization
  - Allow File Transfer & Browsing
- **Fixed Favorites & Recent Cards**: Resolved clipping bug on Windows display scaling; the Connect button is always clearly visible.
- **Accurate Error Reporting & 1-Click Browser Fallback**: Improved auto-updater to show exact download errors and provide a direct browser link if needed.
- **Dynamic Display Modes & Zoom Controls**: Fit Screen, Stretch to Fill (No Black Bars), 1:1 Original Size, and 50%-300% Zoom.
- **100% Backward Compatibility**: Mathematical coordinate normalization compatible with older host versions.
- **Digitally Signed Binaries**: Authenticode SHA-256 with DigiCert RFC 3161 timestamps.
"""
    rel = create_or_get_release(token, tag, title, body)
    upload_url = rel['upload_url']

    existing_asset_names = [a['name'] for a in rel.get('assets', [])]
    print("Existing assets in release:", existing_asset_names)

    files_to_upload = [
        (os.path.join(base_dir, 'OpenDesk_v1.1.7_Portable.exe'), 'OpenDesk_v1.1.7_Portable.exe'),
        (os.path.join(base_dir, 'OpenDesk_Setup_v1.1.7_Installer.exe'), 'OpenDesk_Setup_v1.1.7_Installer.exe')
    ]

    for fpath, aname in files_to_upload:
        if aname not in existing_asset_names:
            upload_asset(token, upload_url, fpath, aname)
        else:
            print(f"Asset {aname} already uploaded.")

    print("\nVerifying live download URLs...")
    for _, aname in files_to_upload:
        dl_url = f"https://github.com/ahsanK225/opendesk-free-for-all/releases/download/{tag}/{aname}"
        try:
            head_req = urllib.request.Request(dl_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(head_req) as r:
                print(f"✓ {aname} is live! HTTP {r.status} (Size: {r.headers.get('content-length')} bytes)")
        except Exception as e:
            print(f"✗ Check failed for {aname}: {e}")

if __name__ == '__main__':
    main()
