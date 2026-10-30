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

    tag = "v1.2.0"
    title = "OpenDesk v1.2.0 - Startup Crash Immunity, Thread-Safe Concurrency & In-App Frameless Window"
    body = """## What's New in OpenDesk v1.2.0

- **🛡️ Startup & Connect Crash Immunity**:
  - Thread-Safe UI Dispatch Queue (`self._ui_queue` + `self.post_ui`): eliminated `RuntimeError: main thread is not in main loop` and `ucrtbase.dll 0xc0000409` buffer overrun crashes caused by cross-thread Tkinter Tcl mutations.
  - Eliminated friend connection crash: decoupled all incoming video packets, status updates, and clipboard notifications from Tcl registration.
  - Re-entrancy guard on window styling preventing Win32 message loop recursion on visible desktop startup.

- **🪟 Seamless In-App Title Bar (CSD - Client-Side Decoration)**:
  - Completely stripped external Windows OS white title bar.
  - Integrated Minimize (`―`), Maximize/Restore (`🗖`/`🗗`), and Close (`✕`) buttons directly into the dark app tab bar with native dark-mode hover states (red close hover).
  - Native smooth Win32 window dragging with Aero snap support.

- **⚡ Instant Hang-Proof Exit**:
  - Multi-stage shutdown: immediate 0ms window hide, background worker cleanup, and clean kernel-level termination (`os._exit(0)`).

- **🎧 Discord-Grade HD Voice & Video Suite**:
  - Studio-grade 48,000 Hz VoIP standard matching Discord and WebRTC (zero resampling distortion).
  - Voice Activity Detection (VAD) with decibel sensitivity threshold slider and ambient noise floor auto-calibration.
  - Push-to-Talk (PTT) mode with customizable shortcut key ([Left Ctrl]).
  - Discord-style "Let's Check" loopback mic test with animated dB VU meter.
  - Advanced Voice Processing: Echo Cancellation, Noise Suppression, and AGC.

- **🚀 Adaptive 60 FPS Fluid Rendering Engine**:
  - Direct RGB BGRX Win32 DIB screen capture.
  - Sub-millisecond motion resampling (`NEAREST`) during movement with automatic stationary `BILINEAR` HD clarity pass.
  - Session toolbar 1-click quality switch between `⚡ 60 FPS Fluid` and `💎 HD Sharp`.

- **🛡️ Authenticode Digital Signatures**:
  - All installer and portable binaries signed with Authenticode SHA-256 and DigiCert RFC 3161 timestamps.
"""
    rel = create_or_get_release(token, tag, title, body)
    upload_url = rel['upload_url']

    existing_asset_names = [a['name'] for a in rel.get('assets', [])]
    print("Existing assets in release:", existing_asset_names)

    files_to_upload = [
        (os.path.join(base_dir, 'OpenDesk_v1.2.0_Portable.exe'), 'OpenDesk_v1.2.0_Portable.exe'),
        (os.path.join(base_dir, 'OpenDesk_Setup_v1.2.0_Installer.exe'), 'OpenDesk_Setup_v1.2.0_Installer.exe')
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
