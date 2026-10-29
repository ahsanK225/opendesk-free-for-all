"""
OpenDesk Dual-Redundant Global Rendezvous Directory
Enables AnyDesk-style zero-configuration connections between remote computers
across different networks using only 9-digit IDs.
Maps 9-digit OpenDesk IDs to Cloudflare Tunnel endpoints worldwide.

Uses dual-redundant global endpoints:
1. Primary: Cloudflare Edge via ntfy.sh (Ultra-low latency <100ms, worldwide CDN)
2. Secondary: keyvalue.immanuel.co (Public key-value fallback store)
"""

import os
import sys
import re
import base64
import time
import urllib.request
import urllib.parse
import threading
from typing import Optional, Tuple

NTFY_BASE = "https://ntfy.sh"
RENDEZVOUS_APP_KEY = "s460x9wm"
RENDEZVOUS_API_BASE = "https://keyvalue.immanuel.co/api/KeyVal"


def _clean_id(raw_id: str) -> str:
    """Strip all non-alphanumeric characters from host ID."""
    return re.sub(r"[^0-9a-zA-Z]", "", str(raw_id).strip())


def publish_host_rendezvous(host_id: str, tunnel_url: str, timeout: float = 4.0) -> bool:
    """
    Publish this host's 9-digit ID and active Cloudflare Tunnel URL to the global rendezvous registry.
    Publishes concurrently to both Primary (ntfy.sh Cloudflare Edge) and Secondary (keyvalue.immanuel.co).
    """
    clean = _clean_id(host_id)
    url_clean = tunnel_url.strip()
    if not clean or not url_clean:
        return False

    success = False

    # 1. Primary: ntfy.sh Cloudflare Edge
    def pub_ntfy():
        nonlocal success
        try:
            target = f"{NTFY_BASE}/opendesk_node_{clean}"
            req = urllib.request.Request(
                target,
                data=url_clean.encode("utf-8"),
                headers={"User-Agent": "OpenDesk-Rendezvous", "Title": "OpenDesk-Node"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    success = True
        except Exception as e:
            pass

    # 2. Secondary: keyvalue.immanuel.co
    def pub_immanuel():
        nonlocal success
        try:
            safe_val = base64.b64encode(url_clean.encode("utf-8")).decode("utf-8").replace("=", "").replace("/", "-")
            target = f"{RENDEZVOUS_API_BASE}/UpdateValue/{RENDEZVOUS_APP_KEY}/{clean}/{safe_val}"
            req = urllib.request.Request(target, data=b"", headers={"User-Agent": "OpenDesk-Rendezvous"}, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    success = True
        except Exception as e:
            pass

    t1 = threading.Thread(target=pub_ntfy, daemon=True)
    t2 = threading.Thread(target=pub_immanuel, daemon=True)
    t1.start()
    t2.start()
    t1.join(timeout=timeout)
    t2.join(timeout=timeout)

    return success


def _query_ntfy(clean_id: str, timeout: float = 3.5) -> Optional[str]:
    """Query Primary Cloudflare Edge endpoint on ntfy.sh."""
    try:
        url = f"{NTFY_BASE}/opendesk_node_{clean_id}/raw?poll=1"
        req = urllib.request.Request(url, headers={"User-Agent": "OpenDesk-Rendezvous"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            txt = resp.read().decode("utf-8").strip()
            for line in reversed(txt.splitlines()):
                line = line.strip()
                if line.startswith("http://") or line.startswith("https://"):
                    return line
    except Exception:
        pass
    return None


def _query_immanuel(clean_id: str, timeout: float = 3.5) -> Optional[str]:
    """Query Secondary fallback endpoint on keyvalue.immanuel.co."""
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
    except Exception:
        pass
    return None


def resolve_host_rendezvous(target_id: str, timeout: float = 6.0, retries: int = 2) -> Optional[str]:
    """
    Lookup a remote 9-digit OpenDesk ID in the global rendezvous registry to discover its Cloudflare Tunnel endpoint.
    Performs fast dual-redundant query with automatic retry backoff.
    """
    clean = _clean_id(target_id)
    if not clean:
        return None

    for attempt in range(retries):
        # 1. Check Primary (Fastest - Cloudflare Edge)
        found = _query_ntfy(clean, timeout=min(3.0, timeout))
        if found:
            return found

        # 2. Check Secondary (Immanuel KV)
        found = _query_immanuel(clean, timeout=min(3.0, timeout))
        if found:
            return found

        if attempt < retries - 1:
            time.sleep(1.0)

    return None


def parse_connect_target(raw_input: str) -> Tuple[str, Optional[str]]:
    """
    Parse a user-entered remote target into (target_id, ws_url_or_none).
    Supports:
    - 9-digit numerical addresses: '732 364 935', '732364935', '732-364-935'
    - Direct Cloudflare tunnel URLs: 'https://xxx.trycloudflare.com', 'xxx.trycloudflare.com'
    - Host/IP addresses: '192.168.1.50:8080'
    - Target ID with host: '732364935@xxx.trycloudflare.com'
    """
    raw = raw_input.strip()
    if "@" in raw:
        parts = raw.split("@", 1)
        target_id = _clean_id(parts[0])
        host_part = parts[1].strip().replace("https://", "").replace("http://", "").rstrip("/")
        ws_url = f"wss://{host_part}/ws"
        return target_id, ws_url

    if "trycloudflare.com" in raw or "http://" in raw or "https://" in raw or (":" in raw and not raw.startswith("ws")):
        clean_url = raw.replace("https://", "").replace("http://", "").rstrip("/")
        host_part = clean_url.split("/")[0]
        scheme = "ws" if "127.0.0.1" in host_part or "localhost" in host_part else "wss"
        ws_url = f"{scheme}://{host_part}/ws"
        return "remote_host", ws_url

    clean_id = _clean_id(raw)
    return clean_id, None


class RendezvousHeartbeat:
    """Background heartbeat service that periodically updates the host's tunnel URL in the global directory."""
    def __init__(self, host_id_getter, tunnel_url_getter, interval: float = 30.0):
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
        # Initial quick burst to guarantee immediate availability
        time.sleep(1.0)
        for _ in range(2):
            if not self.running:
                return
            try:
                hid = self.host_id_getter()
                turl = self.tunnel_url_getter()
                if hid and turl and hid != "Connecting...":
                    publish_host_rendezvous(hid, turl)
            except Exception:
                pass
            time.sleep(3.0)

        while self.running:
            try:
                host_id = self.host_id_getter()
                tunnel_url = self.tunnel_url_getter()
                if host_id and tunnel_url and host_id != "Connecting...":
                    publish_host_rendezvous(host_id, tunnel_url)
            except Exception as e:
                pass
            time.sleep(self.interval)

    def stop(self):
        self.running = False
