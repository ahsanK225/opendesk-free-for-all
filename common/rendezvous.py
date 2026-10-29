"""
OpenDesk Global Rendezvous Directory
Enables AnyDesk-style zero-configuration connections between remote computers
across different networks using only 9-digit IDs.
Maps 9-digit OpenDesk IDs to Cloudflare Tunnel endpoints worldwide.
"""

import os
import sys
import base64
import time
import urllib.request
import urllib.parse
import threading
from typing import Optional, Tuple

RENDEZVOUS_APP_KEY = "s460x9wm"
RENDEZVOUS_API_BASE = "https://keyvalue.immanuel.co/api/KeyVal"


def publish_host_rendezvous(host_id: str, tunnel_url: str, timeout: float = 6.0) -> bool:
    """
    Publish this host's 9-digit ID and active Cloudflare Tunnel URL to the global rendezvous registry.
    """
    clean_id = host_id.replace(" ", "").replace("-", "").strip()
    if not clean_id or not tunnel_url:
        return False
    try:
        # Base64 encode the tunnel URL to avoid path/slash parsing issues on the API endpoint
        safe_val = base64.b64encode(tunnel_url.strip().encode("utf-8")).decode("utf-8").replace("=", "").replace("/", "-")
        url = f"{RENDEZVOUS_API_BASE}/UpdateValue/{RENDEZVOUS_APP_KEY}/{clean_id}/{safe_val}"
        req = urllib.request.Request(url, data=b"", headers={"User-Agent": "OpenDesk-Rendezvous"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"[Rendezvous] Notice: publish to global directory failed ({e})")
        return False


def resolve_host_rendezvous(target_id: str, timeout: float = 6.0) -> Optional[str]:
    """
    Lookup a remote 9-digit OpenDesk ID in the global rendezvous registry to discover its Cloudflare Tunnel endpoint.
    """
    clean_id = target_id.replace(" ", "").replace("-", "").strip()
    if not clean_id:
        return None
    try:
        url = f"{RENDEZVOUS_API_BASE}/GetValue/{RENDEZVOUS_APP_KEY}/{clean_id}"
        req = urllib.request.Request(url, headers={"User-Agent": "OpenDesk-Rendezvous"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            val_raw = resp.read().decode("utf-8").strip().strip('"')
            if not val_raw or val_raw == "null":
                return None
            padded = val_raw.replace("-", "/") + ("=" * ((4 - len(val_raw) % 4) % 4))
            decoded = base64.b64decode(padded).decode("utf-8")
            if decoded.startswith("http://") or decoded.startswith("https://"):
                return decoded
    except Exception as e:
        print(f"[Rendezvous] Notice: resolve lookup failed for {clean_id} ({e})")
        return None
    return None


def parse_connect_target(raw_input: str) -> Tuple[str, Optional[str]]:
    """
    Parse a user-entered remote target into (target_id, ws_url_or_none).
    Supports:
    - 9-digit numerical addresses: '732 364 935', '732364935'
    - Direct Cloudflare tunnel URLs: 'https://xxx.trycloudflare.com', 'xxx.trycloudflare.com'
    - Host/IP addresses: '192.168.1.50:8080'
    - Target ID with host: '732364935@xxx.trycloudflare.com'
    """
    raw = raw_input.strip()
    if "@" in raw:
        parts = raw.split("@", 1)
        target_id = parts[0].strip().replace(" ", "").replace("-", "")
        host_part = parts[1].strip().replace("https://", "").replace("http://", "").rstrip("/")
        ws_url = f"wss://{host_part}/ws"
        return target_id, ws_url

    if "trycloudflare.com" in raw or "http://" in raw or "https://" in raw or (":" in raw and not raw.startswith("ws")):
        clean_url = raw.replace("https://", "").replace("http://", "").rstrip("/")
        host_part = clean_url.split("/")[0]
        scheme = "ws" if "127.0.0.1" in host_part or "localhost" in host_part else "wss"
        ws_url = f"{scheme}://{host_part}/ws"
        return "remote_host", ws_url

    clean_id = raw.replace(" ", "").replace("-", "")
    return clean_id, None


class RendezvousHeartbeat:
    """Background heartbeat service that periodically updates the host's tunnel URL in the global directory."""
    def __init__(self, host_id_getter, tunnel_url_getter, interval: float = 45.0):
        self.host_id_getter = host_id_getter
        self.tunnel_url_getter = tunnel_url_getter
        self.interval = interval
        self.running = False
        self.thread: Optional[threading.Thread] = None

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        while self.running:
            try:
                host_id = self.host_id_getter()
                tunnel_url = self.tunnel_url_getter()
                if host_id and tunnel_url and host_id != "Connecting...":
                    publish_host_rendezvous(host_id, tunnel_url)
            except Exception as e:
                print(f"[RendezvousHeartbeat] Error: {e}")
            time.sleep(self.interval)

    def stop(self):
        self.running = False
