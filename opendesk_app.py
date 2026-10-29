#!/usr/bin/env python3
"""
OpenDesk Standalone Application
Launches a native AnyDesk-styled Windows Desktop GUI with:
- Embedded Signaling & Fallback Relay Server
- Low-latency DeskRT Host Desktop Agent
- Automatic Zero-Config Cloudflare Worldwide Internet Tunneling
"""

import sys
import os
import socket
import threading
import asyncio
import time
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox

# Ensure opendesk directory is in sys.path
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
if hasattr(sys, "_MEIPASS"):
    BASE_DIR = sys._MEIPASS
sys.path.insert(0, BASE_DIR)

from opendesk.relay.server import RelayServer
from opendesk.host.agent import HostAgent
from opendesk.common.tunnel import CloudflareTunnel
from opendesk.common.config import get_persistent_host_id

def find_free_port(start_port=8080):
    """Find an available TCP port, attempting to reuse standard 8080 first."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(('127.0.0.1', start_port))
            return start_port
    except OSError:
        pass

    for port in range(start_port + 1, start_port + 50):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('127.0.0.1', port))
                return port
        except OSError:
            continue
    return start_port

class OpenDeskGUI:
    def __init__(self, root, port):
        self.root = root
        self.port = port
        self.assigned_id = get_persistent_host_id()
        self.relay_url = f"ws://127.0.0.1:{self.port}/ws"
        self.public_url = None
        self.host_agent = None
        self.tunnel = None
        
        self._setup_window()
        self._build_ui()
        self._start_services()

    def _setup_window(self):
        self.root.title("OpenDesk - Remote Desktop")
        self.root.geometry("720x470")
        self.root.minsize(680, 440)
        self.root.configure(bg="#0f1117")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.eval('tk::PlaceWindow . center')

    def _build_ui(self):
        # Header Bar
        header = tk.Frame(self.root, bg="#1a1d27", height=50)
        header.pack(fill="x", side="top")

        brand_frame = tk.Frame(header, bg="#1a1d27")
        brand_frame.pack(side="left", padx=16, pady=10)

        icon_label = tk.Label(brand_frame, text="⚡", font=("Segoe UI Emoji", 16), bg="#1a1d27", fg="#7aa2f7")
        icon_label.pack(side="left")

        title_label = tk.Label(brand_frame, text="OpenDesk", font=("Segoe UI", 14, "bold"), bg="#1a1d27", fg="#c0caf5")
        title_label.pack(side="left", padx=6)

        actions_frame = tk.Frame(header, bg="#1a1d27")
        actions_frame.pack(side="right", padx=16, pady=10)

        self.mic_btn = tk.Button(actions_frame, text="🎙️ Mic: ON", font=("Segoe UI", 8, "bold"), bg="#1f382a", fg="#9ece6a",
                                 activebackground="#2f4a38", activeforeground="#9ece6a", bd=0, padx=8, pady=3, cursor="hand2", command=self._toggle_host_mic)
        self.mic_btn.pack(side="left", padx=(0, 10))

        settings_btn = tk.Button(actions_frame, text="⚙️ Relay Settings", font=("Segoe UI", 8), bg="#24283b", fg="#c0caf5",
                                 activebackground="#2f344d", activeforeground="#7aa2f7", bd=0, padx=8, pady=3, cursor="hand2", command=self._open_settings)
        settings_btn.pack(side="left", padx=(0, 10))

        self.status_badge = tk.Label(actions_frame, text="● STARTING", font=("Segoe UI", 8, "bold"), bg="#24283b", fg="#e0af68", padx=8, pady=2)
        self.status_badge.pack(side="left")

        # Main Dual-Card Container
        cards_container = tk.Frame(self.root, bg="#0f1117")
        cards_container.pack(fill="both", expand=True, padx=20, pady=(16, 10))

        # --- LEFT CARD: This Desk (Your ID) ---
        left_card = tk.Frame(cards_container, bg="#1a1d27", bd=1, relief="solid", highlightbackground="#3b4261", highlightthickness=1)
        left_card.pack(side="left", fill="both", expand=True, padx=(0, 10))

        tk.Label(left_card, text="💻 This Desk", font=("Segoe UI", 12, "bold"), bg="#1a1d27", fg="#c0caf5").pack(anchor="w", padx=16, pady=(14, 2))
        tk.Label(left_card, text="Your 9-digit address for incoming control", font=("Segoe UI", 8), bg="#1a1d27", fg="#565f89").pack(anchor="w", padx=16, pady=(0, 8))

        id_container = tk.Frame(left_card, bg="#24283b", bd=1, relief="solid", highlightbackground="#7aa2f7", highlightthickness=1)
        id_container.pack(fill="x", padx=16, pady=4)

        self.id_label = tk.Label(id_container, text=self.assigned_id, font=("Consolas", 18, "bold"), bg="#24283b", fg="#7aa2f7", pady=8)
        self.id_label.pack()

        copy_btn = tk.Button(left_card, text="📋 Copy ID", font=("Segoe UI", 8, "bold"), bg="#24283b", fg="#c0caf5",
                             activebackground="#2f344d", activeforeground="#7aa2f7", bd=0, padx=12, pady=4, cursor="hand2", command=self._copy_id)
        copy_btn.pack(pady=4)

        # Worldwide Internet Section
        internet_box = tk.Frame(left_card, bg="#1a1d27")
        internet_box.pack(fill="x", padx=16, pady=(8, 4))

        tk.Label(internet_box, text="🌐 Worldwide Internet Access (Any Network):", font=("Segoe UI", 8, "bold"), bg="#1a1d27", fg="#7aa2f7").pack(anchor="w")
        self.internet_link_label = tk.Label(internet_box, text="Activating global tunnel...", font=("Consolas", 8), bg="#24283b", fg="#e0af68", pady=4, padx=6)
        self.internet_link_label.pack(fill="x", pady=3)

        self.copy_link_btn = tk.Button(internet_box, text="🔗 Copy Worldwide Link", font=("Segoe UI", 8), bg="#24283b", fg="#7aa2f7",
                                       activebackground="#2f344d", activeforeground="#89b4fa", bd=0, padx=8, pady=3, cursor="hand2", command=self._copy_internet_link)
        self.copy_link_btn.pack(pady=2)

        # --- RIGHT CARD: Remote Desk (Connect) ---
        right_card = tk.Frame(cards_container, bg="#1a1d27", bd=1, relief="solid", highlightbackground="#3b4261", highlightthickness=1)
        right_card.pack(side="right", fill="both", expand=True, padx=(10, 0))

        tk.Label(right_card, text="🚀 Remote Desk", font=("Segoe UI", 12, "bold"), bg="#1a1d27", fg="#c0caf5").pack(anchor="w", padx=16, pady=(14, 2))
        tk.Label(right_card, text="Enter remote OpenDesk address to control", font=("Segoe UI", 8), bg="#1a1d27", fg="#565f89").pack(anchor="w", padx=16, pady=(0, 10))

        self.remote_entry = tk.Entry(right_card, font=("Consolas", 14), bg="#24283b", fg="#c0caf5",
                                     insertbackground="#7aa2f7", bd=1, relief="solid", highlightbackground="#3b4261", highlightthickness=1)
        self.remote_entry.pack(fill="x", padx=16, pady=4, ipady=5)
        self.remote_entry.insert(0, "")
        self.remote_entry.bind("<Return>", lambda e: self._connect_remote())

        connect_btn = tk.Button(right_card, text="Connect Session", font=("Segoe UI", 10, "bold"), bg="#7aa2f7", fg="#0f1117",
                                activebackground="#89b4fa", activeforeground="#0f1117", bd=0, pady=7, cursor="hand2", command=self._connect_remote)
        connect_btn.pack(fill="x", padx=16, pady=10)

        web_btn = tk.Button(right_card, text="🌐 Open Web Console", font=("Segoe UI", 9), bg="#24283b", fg="#7aa2f7",
                            activebackground="#2f344d", activeforeground="#89b4fa", bd=0, pady=5, cursor="hand2", command=self._open_web)
        web_btn.pack(pady=4)

        # Bottom Bar
        bottom_bar = tk.Frame(self.root, bg="#1a1d27", height=32)
        bottom_bar.pack(fill="x", side="bottom")

        self.bottom_status_label = tk.Label(bottom_bar, text=f"Local Relay: http://localhost:{self.port}", font=("Segoe UI", 8), bg="#1a1d27", fg="#565f89")
        self.bottom_status_label.pack(side="left", padx=16, pady=6)
        
        tk.Label(bottom_bar, text="v1.1.0 (DeskRT & Cloudflare Tunnel Engine)", font=("Segoe UI", 8), bg="#1a1d27", fg="#565f89").pack(side="right", padx=16, pady=6)

    def _copy_id(self):
        clean = self.assigned_id.replace(" ", "")
        if clean and clean != "Connecting...":
            self.root.clipboard_clear()
            self.root.clipboard_append(self.assigned_id)
            messagebox.showinfo("Copied", f"OpenDesk ID {self.assigned_id} copied to clipboard!")

    def _copy_internet_link(self):
        if self.public_url:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.public_url)
            messagebox.showinfo("Copied", f"Worldwide Internet Link copied to clipboard:\n{self.public_url}\n\nSend this link to anyone on any network!")
        else:
            messagebox.showwarning("Pending", "Global internet tunnel is still initializing. Please wait a moment.")

    def _toggle_host_mic(self):
        if not self.host_agent or not hasattr(self.host_agent, "audio_engine") or not self.host_agent.audio_engine:
            return
        engine = self.host_agent.audio_engine
        engine.mic_enabled = not engine.mic_enabled
        if engine.mic_enabled:
            self.mic_btn.config(text="🎙️ Mic: ON", bg="#1f382a", fg="#9ece6a")
        else:
            self.mic_btn.config(text="🔇 Mic: MUTED", bg="#3d2a1f", fg="#e0af68")

    def _connect_remote(self):
        target = self.remote_entry.get().strip()
        if not target:
            messagebox.showwarning("Input Required", "Please enter a valid remote 9-digit OpenDesk ID.")
            return
        clean = target.replace(" ", "")
        url = f"http://localhost:{self.port}/?connect={clean}"
        webbrowser.open(url)

    def _open_web(self):
        webbrowser.open(f"http://localhost:{self.port}")

    def _open_settings(self):
        settings_win = tk.Toplevel(self.root)
        settings_win.title("Relay Server Settings")
        settings_win.geometry("500x240")
        settings_win.configure(bg="#1a1d27")
        settings_win.grab_set()

        tk.Label(settings_win, text="🌐 Network & Relay Server Configuration", font=("Segoe UI", 11, "bold"), bg="#1a1d27", fg="#c0caf5").pack(anchor="w", padx=20, pady=(16, 6))
        tk.Label(settings_win, text="To connect through a custom public cloud VPS (like AnyDesk relay),\nenter your custom WebSocket URL:", font=("Segoe UI", 8), bg="#1a1d27", fg="#565f89", justify="left").pack(anchor="w", padx=20, pady=(0, 10))

        entry_box = tk.Entry(settings_win, font=("Consolas", 10), bg="#24283b", fg="#c0caf5", insertbackground="#7aa2f7", bd=1, relief="solid")
        entry_box.pack(fill="x", padx=20, pady=6, ipady=4)
        entry_box.insert(0, self.relay_url)

        def save_and_reconnect():
            new_url = entry_box.get().strip()
            if new_url:
                self.relay_url = new_url
                settings_win.destroy()
                messagebox.showinfo("Saved", f"Relay URL updated to:\n{self.relay_url}\n\nPlease restart OpenDesk to apply.")

        btn_row = tk.Frame(settings_win, bg="#1a1d27")
        btn_row.pack(fill="x", padx=20, pady=16)

        tk.Button(btn_row, text="Save Settings", font=("Segoe UI", 9, "bold"), bg="#7aa2f7", fg="#0f1117", bd=0, padx=14, pady=6, cursor="hand2", command=save_and_reconnect).pack(side="left")
        tk.Button(btn_row, text="Cancel", font=("Segoe UI", 9), bg="#24283b", fg="#c0caf5", bd=0, padx=14, pady=6, cursor="hand2", command=settings_win.destroy).pack(side="right")

    def _start_services(self):
        # 1. Start Relay Server thread
        def run_relay():
            server = RelayServer(host="0.0.0.0", port=self.port)
            server.run()

        t_relay = threading.Thread(target=run_relay, daemon=True)
        t_relay.start()

        # 2. Start Host Agent thread
        def run_agent():
            time.sleep(0.5)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self.host_agent = HostAgent(relay_url=self.relay_url, host_id=self.assigned_id)
            
            async def monitor_id():
                while True:
                    if self.host_agent.assigned_id:
                        self.assigned_id = self.host_agent.assigned_id
                        self.root.after(0, self._on_agent_online)
                        break
                    await asyncio.sleep(0.2)

            async def main_loop():
                await asyncio.gather(self.host_agent.start(), monitor_id())

            loop.run_until_complete(main_loop())

        t_agent = threading.Thread(target=run_agent, daemon=True)
        t_agent.start()

        # 3. Start Automatic Worldwide Cloudflare Tunnel
        self.tunnel = CloudflareTunnel(local_port=self.port, on_url_ready=self._on_tunnel_url_ready)
        self.tunnel.start()

    def _on_agent_online(self):
        self.id_label.config(text=self.assigned_id)
        if not self.public_url:
            self.status_badge.config(text="● LOCAL READY", bg="#1f382a", fg="#9ece6a")

    def _on_tunnel_url_ready(self, url):
        self.public_url = url
        self.root.after(0, self._update_tunnel_ui)

    def _update_tunnel_ui(self):
        if self.public_url:
            self.internet_link_label.config(text=self.public_url, fg="#9ece6a")
            self.status_badge.config(text="● WORLDWIDE ONLINE", bg="#1f382a", fg="#9ece6a")
            self.bottom_status_label.config(text=f"Global: {self.public_url}")

    def _on_close(self):
        if self.tunnel:
            self.tunnel.stop()
        if self.host_agent:
            self.host_agent.stop()
        self.root.destroy()
        sys.exit(0)

def main():
    port = find_free_port(8080)
    root = tk.Tk()
    app = OpenDeskGUI(root, port)
    root.mainloop()

if __name__ == "__main__":
    main()
