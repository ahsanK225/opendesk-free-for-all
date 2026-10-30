#!/usr/bin/env python3
"""
OpenDesk Standalone Application (AnyDesk 8 Experience)
Features:
- AnyDesk-style Multi-Tab Architecture:
  - Top tab strip with [ 🏠 New Connection ], dynamic [ 💻 <ID>  ✕ ] session tabs, and [ + ] button.
  - In-App Embedded Remote Desktop Viewports (Canvas, Win32 input, voice audio, clipboard).
- Left Navigation Sidebar: Home / Discover, Favorites, Recent Sessions, File Transfer, Settings.
- Home Dashboard:
  - Quick Connect Search Bar with prominent AnyDesk Red action button.
  - "This Desk" card featuring persistent 9-digit ID, 1-click copy, and unattended password access.
  - Worldwide Internet Tunneling powered by Cloudflare with 1-click shareable URL.
  - Recent Sessions & Discovery Grid with 1-click reconnect and favorite toggles.
- DeskRT 60 FPS Delta Codec, 16kHz HD Voice Communication, 64-bit Bidirectional Clipboard.
"""

import sys
import os
import socket
import threading
import asyncio
import time
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from typing import Optional, Dict, Any, List

# Ensure opendesk directory and parent are in sys.path
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
PARENT_DIR = os.path.abspath(os.path.join(BASE_DIR, ".."))
if hasattr(sys, "_MEIPASS"):
    BASE_DIR = sys._MEIPASS
    PARENT_DIR = sys._MEIPASS
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

try:
    from opendesk.relay.server import RelayServer
    from opendesk.host.agent import HostAgent
    from opendesk.common.tunnel import CloudflareTunnel
    from opendesk.common.config import (
        get_persistent_host_id,
        get_recent_sessions,
        add_recent_session,
        toggle_favorite,
        get_unattended_password,
        set_unattended_password,
        get_auto_update_enabled,
        set_auto_update_enabled,
        get_audio_settings,
        save_audio_settings
    )
    from opendesk.host.audio import get_available_audio_devices, AudioEngine
    from opendesk.common.updater import (
        APP_VERSION,
        check_for_updates,
        download_update_file,
        apply_update_and_restart
    )
    from opendesk.common.rendezvous import (
        publish_host_rendezvous,
        resolve_host_rendezvous,
        parse_connect_target,
        RendezvousHeartbeat
    )
    from opendesk.client.viewer import EmbeddedSessionView, NativeSessionViewer
except ImportError:
    from relay.server import RelayServer
    from host.agent import HostAgent
    from common.tunnel import CloudflareTunnel
    from common.config import (
        get_persistent_host_id,
        get_recent_sessions,
        add_recent_session,
        toggle_favorite,
        get_unattended_password,
        set_unattended_password,
        get_auto_update_enabled,
        set_auto_update_enabled,
        get_audio_settings,
        save_audio_settings
    )
    from host.audio import get_available_audio_devices, AudioEngine
    from common.updater import (
        APP_VERSION,
        check_for_updates,
        download_update_file,
        apply_update_and_restart
    )
    from common.rendezvous import (
        publish_host_rendezvous,
        resolve_host_rendezvous,
        parse_connect_target,
        RendezvousHeartbeat
    )
    from client.viewer import EmbeddedSessionView, NativeSessionViewer


def find_free_port(start_port=8080) -> int:
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
    def __init__(self, root: tk.Tk, port: int):
        self.root = root
        self.port = port
        self.assigned_id = get_persistent_host_id()
        self.relay_url = f"ws://127.0.0.1:{self.port}/ws"
        self.public_url: Optional[str] = None
        self.host_agent: Optional[HostAgent] = None
        self.tunnel: Optional[CloudflareTunnel] = None
        self.rendezvous_heartbeat: Optional[RendezvousHeartbeat] = None

        # Tab & View State
        # Structure: list of dicts: {"id": str, "title": str, "type": "home" | "session", "frame": Frame, "viewer": view_or_none, "btn_frame": Frame}
        self.tabs: List[Dict[str, Any]] = []
        self.active_tab_id: Optional[str] = None

        # Active Sidebar Section
        self.active_nav_section = "home"

        self._setup_window()
        self._build_top_tab_bar()
        self._build_update_banner()
        self._build_main_body()
        self._build_bottom_status_bar()

        # Initialize Home Tab
        self._create_home_tab()

        # Start Services
        self._start_services()

    def _setup_window(self):
        self.root.title("OpenDesk - AnyDesk Free For All Edition")
        self.root.geometry("1100x700")
        self.root.minsize(880, 560)
        self.root.configure(bg="#0c0e14")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        try:
            self.root.eval('tk::PlaceWindow . center')
        except Exception:
            pass

    # =========================================================================
    # TOP ANYDESK TAB BAR & CONTROLS
    # =========================================================================
    def _build_top_tab_bar(self):
        self.tab_bar_frame = tk.Frame(self.root, bg="#141822", height=42)
        self.tab_bar_frame.pack(fill="x", side="top")

        # Brand / Logo on far left
        brand_frame = tk.Frame(self.tab_bar_frame, bg="#141822")
        brand_frame.pack(side="left", padx=(14, 10), pady=6)
        tk.Label(brand_frame, text="⚡", font=("Segoe UI Emoji", 13), bg="#141822", fg="#ef4444").pack(side="left")
        tk.Label(brand_frame, text="OpenDesk", font=("Segoe UI", 12, "bold"), bg="#141822", fg="#f1f5f9").pack(side="left", padx=4)

        # Tab Items Container
        self.tabs_container = tk.Frame(self.tab_bar_frame, bg="#141822")
        self.tabs_container.pack(side="left", fill="y", padx=4)

        # '+' New Tab Button
        self.plus_btn = tk.Button(self.tab_bar_frame, text="+", font=("Segoe UI", 12, "bold"),
                                  bg="#141822", fg="#94a3b8", activebackground="#1e2230", activeforeground="#ef4444",
                                  bd=0, padx=8, pady=2, cursor="hand2", command=lambda: self.switch_tab("home"))
        self.plus_btn.pack(side="left", padx=2, pady=6)

        # Right Action Buttons & Indicators
        right_actions = tk.Frame(self.tab_bar_frame, bg="#141822")
        right_actions.pack(side="right", padx=12, pady=6)

        self.mic_btn = tk.Button(right_actions, text="🎙️ Mic: ON", font=("Segoe UI", 8, "bold"),
                                 bg="#1f382a", fg="#9ece6a", activebackground="#2f4a38", activeforeground="#9ece6a",
                                 bd=0, padx=8, pady=3, cursor="hand2", command=self._toggle_host_mic)
        self.mic_btn.pack(side="left", padx=4)

        self.status_badge = tk.Label(right_actions, text="● STARTING", font=("Segoe UI", 8, "bold"),
                                     bg="#252a38", fg="#e0af68", padx=8, pady=3)
        self.status_badge.pack(side="left", padx=4)

        settings_btn = tk.Button(right_actions, text="⚙️", font=("Segoe UI", 10),
                                 bg="#141822", fg="#94a3b8", activebackground="#1e2230", activeforeground="#ef4444",
                                 bd=0, padx=6, pady=2, cursor="hand2", command=self._open_settings)
        settings_btn.pack(side="left", padx=4)

    # =========================================================================
    # IN-APP AUTO-UPDATE NOTIFICATION BANNER & MODAL DIALOG
    # =========================================================================
    def _build_update_banner(self):
        self.banner_frame = tk.Frame(self.root, bg="#1e2433", height=38)
        # Hidden by default until an update is detected

    def _show_update_banner(self, update_info: Dict[str, Any]):
        for child in self.banner_frame.winfo_children():
            child.destroy()

        remote_ver = update_info.get("version", "")
        left_box = tk.Frame(self.banner_frame, bg="#1e2433")
        left_box.pack(side="left", padx=14, pady=6)

        tk.Label(left_box, text="⚡", font=("Segoe UI Emoji", 11), bg="#1e2433", fg="#ef4444").pack(side="left")
        if update_info.get("is_incremental") and update_info.get("differential_plan"):
            plan = update_info["differential_plan"]
            banner_txt = f"⚡ Smart Incremental Update v{remote_ver} Ready! ({plan.total_delta_bytes/1024:.0f} KB delta • {plan.bandwidth_saved_pct:.0f}% bandwidth saved)"
        else:
            banner_txt = f"Update Available: OpenDesk v{remote_ver} is now ready to install!"

        tk.Label(left_box, text=banner_txt,
                 font=("Segoe UI", 9, "bold"), bg="#1e2433", fg="#f1f5f9").pack(side="left", padx=6)

        right_box = tk.Frame(self.banner_frame, bg="#1e2433")
        right_box.pack(side="right", padx=14, pady=6)

        upd_btn = tk.Button(right_box, text="🚀 Update Now", font=("Segoe UI", 8, "bold"),
                            bg="#ef4444", fg="#ffffff", activebackground="#dc2626", activeforeground="#ffffff",
                            bd=0, padx=12, pady=2, cursor="hand2", command=lambda: self._open_update_dialog(update_info))
        upd_btn.pack(side="left", padx=4)

        dismiss_btn = tk.Button(right_box, text="✕", font=("Segoe UI", 8),
                                bg="#1e2433", fg="#64748b", activebackground="#1e2433", activeforeground="#f1f5f9",
                                bd=0, padx=6, pady=2, cursor="hand2", command=self.banner_frame.pack_forget)
        dismiss_btn.pack(side="left")

        # Pack beneath top tab bar
        self.banner_frame.pack(fill="x", side="top", after=self.tab_bar_frame)

    def _open_update_dialog(self, update_info: Dict[str, Any]):
        import tempfile
        dialog = tk.Toplevel(self.root)
        dialog.title("OpenDesk In-App Software Update")
        dialog.geometry("600x530")
        dialog.minsize(540, 480)
        dialog.configure(bg="#141822")
        dialog.transient(self.root)
        dialog.grab_set()

        # Center on screen or root
        try:
            self.root.update_idletasks()
            rw = self.root.winfo_width()
            rh = self.root.winfo_height()
            rx = self.root.winfo_rootx()
            ry = self.root.winfo_rooty()
            dw, dh = 600, 530
            x = max(0, rx + (rw - dw) // 2)
            y = max(0, ry + (rh - dh) // 2)
            dialog.geometry(f"{dw}x{dh}+{x}+{y}")
        except Exception:
            pass

        # 1. Header (TOP)
        h_frame = tk.Frame(dialog, bg="#141822")
        h_frame.pack(side="top", fill="x", padx=22, pady=(16, 6))

        tk.Label(h_frame, text="⚡ OpenDesk Software Update", font=("Segoe UI", 14, "bold"),
                 bg="#141822", fg="#f1f5f9").pack(anchor="w")

        is_inc = update_info.get("is_incremental", False)
        diff_plan = update_info.get("differential_plan")

        if is_inc and diff_plan:
            kb_delta = diff_plan.total_delta_bytes / 1024
            sub_txt = f"📦 Smart Incremental Update v{diff_plan.target_version} Available! (Installed: v{APP_VERSION})\nDownload Size: {kb_delta:.1f} KB (Saved {diff_plan.bandwidth_saved_pct:.1f}% bandwidth • Skipped {len(diff_plan.to_skip)} unchanged files)"
        else:
            sub_txt = f"A new version v{update_info.get('version', '')} is available! (Installed: v{APP_VERSION} • Released: {update_info.get('release_date', 'Recent')})"
        tk.Label(h_frame, text=sub_txt, font=("Segoe UI", 9), bg="#141822", fg="#22c55e", justify="left").pack(anchor="w", pady=(2, 0))

        # 2. Bottom Buttons Row (PACKED FIRST TO BOTTOM - 100% GUARANTEED VISIBLE)
        btn_row = tk.Frame(dialog, bg="#141822")
        btn_row.pack(side="bottom", fill="x", padx=22, pady=(12, 18))

        cancel_flag = [False]

        def on_cancel():
            cancel_flag[0] = True
            dialog.destroy()

        def start_download():
            apply_btn.configure(state="disabled", text="⏳ Downloading Update...")
            cancel_btn.configure(text="Cancel")

            def run_dl():
                if is_inc and diff_plan:
                    from common.incremental_updater import IncrementalUpdater
                    from common.updater import get_install_dir

                    def on_delta_prog(downloaded, total, cur_file, idx, total_files):
                        pct = int((downloaded / total) * 100) if total > 0 else 50
                        txt = f"Downloading delta ({idx}/{total_files}): {cur_file} ({downloaded/1024:.1f} KB / {total/1024:.1f} KB)"
                        dialog.after(0, lambda: [
                            progress_bar.configure(value=pct),
                            status_lbl.configure(text=txt, fg="#f1f5f9")
                        ])

                    inc = IncrementalUpdater(install_dir=get_install_dir(), manifest_url="", current_version=APP_VERSION)
                    success, staging_or_err = inc.download_delta(diff_plan, progress_callback=on_delta_prog, cancel_flag=lambda: cancel_flag[0])

                    if success and not cancel_flag[0]:
                        dialog.after(0, lambda: [
                            status_lbl.configure(text="✓ SHA-256 hashes verified! Applying staged files...", fg="#22c55e"),
                        ])
                        apply_ok, msg = inc.apply_staged_update(diff_plan, staging_or_err)
                        if apply_ok:
                            dialog.after(0, lambda: [
                                status_lbl.configure(text="✓ Update applied! Relaunching in 1 second...", fg="#22c55e"),
                                dialog.after(800, lambda: apply_update_and_restart(sys.executable))
                            ])
                        else:
                            dialog.after(0, lambda: [
                                status_lbl.configure(text=f"Failed to apply: {msg}", fg="#ef4444"),
                                apply_btn.configure(state="normal", text="Retry Update")
                            ])
                    elif not cancel_flag[0]:
                        dialog.after(0, lambda: [
                            status_lbl.configure(text=f"Download failed: {staging_or_err}", fg="#ef4444"),
                            apply_btn.configure(state="normal", text="Retry Update")
                        ])
                    return

                # Fallback full binary download
                download_url = update_info.get("download_url", "")
                if not download_url:
                    messagebox.showerror("Error", "Download URL not found in update manifest.", parent=dialog)
                    return

                temp_dir = tempfile.gettempdir()
                temp_exe = os.path.join(temp_dir, f"OpenDesk_v{update_info.get('version', '')}_new.exe")

                def on_progress(downloaded, total):
                    if total > 0:
                        pct = int((downloaded / total) * 100)
                        mb_dl = downloaded / (1024 * 1024)
                        mb_tot = total / (1024 * 1024)
                        txt = f"Downloading: {mb_dl:.1f} MB / {mb_tot:.1f} MB ({pct}%)"
                        dialog.after(0, lambda: [
                            progress_bar.configure(value=pct),
                            status_lbl.configure(text=txt, fg="#f1f5f9")
                        ])

                err_holder = []
                success = download_update_file(download_url, temp_exe, on_progress, cancel_flag=lambda: cancel_flag[0], error_holder=err_holder)

                if success and not cancel_flag[0]:
                    dialog.after(0, lambda: [
                        status_lbl.configure(text="✓ Download complete! Relaunching into new version in 1 second...", fg="#22c55e"),
                        dialog.after(800, lambda: apply_update_and_restart(temp_exe))
                    ])
                elif not cancel_flag[0]:
                    err_msg = err_holder[0] if err_holder else "Download failed. Please check internet connection."
                    dialog.after(0, lambda: [
                        status_lbl.configure(text=f"Failed: {err_msg}", fg="#ef4444"),
                        apply_btn.configure(state="normal", text="📥 Retry Download"),
                        browser_btn.pack(side="left", padx=6)
                    ])

            threading.Thread(target=run_dl, daemon=True).start()

        btn_text = "⚡ Apply Smart Incremental Update" if (is_inc and diff_plan) else "📥 Download & Update Now (Restart OpenDesk)"
        apply_btn = tk.Button(btn_row, text=btn_text, font=("Segoe UI", 10, "bold"),
                              bg="#22c55e", fg="#0f172a", activebackground="#16a34a", activeforeground="#ffffff",
                              bd=0, padx=18, pady=8, cursor="hand2", command=start_download)
        apply_btn.pack(side="left")

        browser_btn = tk.Button(btn_row, text="🌐 Open Releases Page", font=("Segoe UI", 9, "bold"),
                                bg="#1e293b", fg="#38bdf8", activebackground="#334155", activeforeground="#7dd3fc",
                                bd=0, padx=12, pady=8, cursor="hand2",
                                command=lambda: webbrowser.open("https://github.com/ahsanK225/opendesk-free-for-all/releases"))

        cancel_btn = tk.Button(btn_row, text="Later", font=("Segoe UI", 9),
                               bg="#202534", fg="#cbd5e1", activebackground="#2a3144", activeforeground="#f1f5f9",
                               bd=0, padx=14, pady=8, cursor="hand2", command=on_cancel)
        cancel_btn.pack(side="right")

        # 3. Progress / Status Frame (PACKED ABOVE BUTTONS)
        prog_frame = tk.Frame(dialog, bg="#141822")
        prog_frame.pack(side="bottom", fill="x", padx=22, pady=(0, 6))

        status_lbl = tk.Label(prog_frame, text="Click 'Download & Update Now' to download and automatically restart.",
                              font=("Segoe UI", 8), bg="#141822", fg="#94a3b8")
        status_lbl.pack(anchor="w", pady=(0, 4))

        progress_bar = ttk.Progressbar(prog_frame, orient="horizontal", mode="determinate")
        progress_bar.pack(fill="x")

        # 4. Changelog Frame (Fills middle area with Scrollbar)
        cl_frame = tk.Frame(dialog, bg="#181c28", bd=1, relief="solid", highlightbackground="#282e3f")
        cl_frame.pack(side="top", fill="both", expand=True, padx=22, pady=(6, 10))

        tk.Label(cl_frame, text="What's New in this Version:", font=("Segoe UI", 9, "bold"),
                 bg="#181c28", fg="#ef4444").pack(anchor="w", padx=12, pady=(8, 4))

        text_container = tk.Frame(cl_frame, bg="#141822")
        text_container.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        scrollbar = tk.Scrollbar(text_container)
        scrollbar.pack(side="right", fill="y")

        text_box = tk.Text(text_container, font=("Segoe UI", 9), bg="#141822", fg="#cbd5e1",
                           wrap="word", bd=0, padx=10, pady=8, yscrollcommand=scrollbar.set)
        text_box.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=text_box.yview)

        text_box.insert("1.0", update_info.get("changelog", "Improvements and bug fixes."))
        text_box.configure(state="disabled")

    def _check_updates_interactive(self, parent_win):
        check_win = tk.Toplevel(parent_win)
        check_win.title("Checking for Updates...")
        check_win.geometry("360x130")
        check_win.configure(bg="#141822")
        check_win.grab_set()

        tk.Label(check_win, text="🔄 Checking for OpenDesk Updates...", font=("Segoe UI", 10, "bold"),
                 bg="#141822", fg="#f1f5f9").pack(pady=(20, 8))

        lbl_status = tk.Label(check_win, text="Contacting GitHub update server...", font=("Segoe UI", 8),
                              bg="#141822", fg="#94a3b8")
        lbl_status.pack()

        def do_check():
            info = check_for_updates(current_version=APP_VERSION)
            def on_done():
                try:
                    check_win.destroy()
                except Exception:
                    pass
                if info and info.get("available"):
                    self._open_update_dialog(info)
                elif info and not info.get("available"):
                    messagebox.showinfo("Up to Date", f"You are running the latest version of OpenDesk (v{APP_VERSION}).\n\nNo updates are needed at this time.", parent=parent_win)
                else:
                    messagebox.showwarning("Update Check", "Unable to reach the update server. Please check your internet connection.", parent=parent_win)

            check_win.after(0, on_done)

        threading.Thread(target=do_check, daemon=True).start()

    # =========================================================================
    # MAIN BODY: SIDEBAR + CONTENT VIEWPORT
    # =========================================================================
    def _build_main_body(self):
        self.body_frame = tk.Frame(self.root, bg="#0c0e14")
        self.body_frame.pack(fill="both", expand=True)

        # Left Navigation Sidebar
        self.sidebar_frame = tk.Frame(self.body_frame, bg="#12151e", width=70)
        self.sidebar_frame.pack(side="left", fill="y")
        self.sidebar_frame.pack_propagate(False)

        self._build_sidebar_items()

        # Viewport Frame Container (Holds active tab frames)
        self.viewport_container = tk.Frame(self.body_frame, bg="#0c0e14")
        self.viewport_container.pack(side="left", fill="both", expand=True)

    def _build_sidebar_items(self):
        items = [
            ("home", "🏠\nHome"),
            ("favorites", "⭐\nFavorites"),
            ("recent", "🕒\nRecent"),
            ("files", "📁\nFiles"),
            ("settings", "⚙️\nSettings")
        ]
        self.sidebar_buttons = {}

        for key, label_text in items:
            btn_frame = tk.Frame(self.sidebar_frame, bg="#12151e", height=54)
            btn_frame.pack(fill="x", pady=2)
            btn_frame.pack_propagate(False)

            # Red indicator line on left
            indicator = tk.Frame(btn_frame, bg="#12151e", width=3)
            indicator.pack(side="left", fill="y")

            btn = tk.Button(btn_frame, text=label_text, font=("Segoe UI", 8),
                            bg="#12151e", fg="#94a3b8", activebackground="#1a1e2b", activeforeground="#f1f5f9",
                            bd=0, cursor="hand2", command=lambda k=key: self._on_sidebar_click(k))
            btn.pack(side="left", fill="both", expand=True)

            self.sidebar_buttons[key] = {"frame": btn_frame, "indicator": indicator, "button": btn}

        self._update_sidebar_active("home")

    def _on_sidebar_click(self, key: str):
        self._update_sidebar_active(key)
        if key == "settings":
            self._open_settings()
        elif key in ("home", "favorites", "recent"):
            self.switch_tab("home")
            if hasattr(self, "recent_filter_var"):
                if key == "favorites":
                    self.recent_filter_var.set("favorites")
                elif key == "recent":
                    self.recent_filter_var.set("all")
                self._render_recent_grid()

    def _update_sidebar_active(self, active_key: str):
        self.active_nav_section = active_key
        for key, widgets in self.sidebar_buttons.items():
            if key == active_key:
                widgets["frame"].configure(bg="#1a1e2b")
                widgets["indicator"].configure(bg="#ef4444")
                widgets["button"].configure(bg="#1a1e2b", fg="#ffffff", font=("Segoe UI", 8, "bold"))
            else:
                widgets["frame"].configure(bg="#12151e")
                widgets["indicator"].configure(bg="#12151e")
                widgets["button"].configure(bg="#12151e", fg="#94a3b8", font=("Segoe UI", 8))

    # =========================================================================
    # TAB MANAGEMENT SYSTEM
    # =========================================================================
    def _create_home_tab(self):
        home_frame = tk.Frame(self.viewport_container, bg="#0c0e14")
        self._build_home_dashboard(home_frame)

        tab_data = {
            "id": "home",
            "title": "New Connection",
            "type": "home",
            "frame": home_frame,
            "viewer": None,
            "btn_frame": None
        }
        self.tabs.append(tab_data)
        self._render_tab_button(tab_data)
        self.switch_tab("home")

    def _render_tab_button(self, tab_data: Dict[str, Any]):
        tab_id = tab_data["id"]
        btn_frame = tk.Frame(self.tabs_container, bg="#141822")
        btn_frame.pack(side="left", padx=2, pady=4)
        tab_data["btn_frame"] = btn_frame

        # Tab text button
        display_title = "🏠 New Connection" if tab_id == "home" else f"💻 {tab_data['title']}"
        tab_btn = tk.Button(btn_frame, text=display_title, font=("Segoe UI", 9),
                            bg="#141822", fg="#94a3b8", activebackground="#1e2230", activeforeground="#f1f5f9",
                            bd=0, padx=10, pady=4, cursor="hand2", command=lambda: self.switch_tab(tab_id))
        tab_btn.pack(side="left")
        tab_data["tab_btn"] = tab_btn

        # Close '✕' button for remote session tabs
        if tab_id != "home":
            close_btn = tk.Button(btn_frame, text="✕", font=("Segoe UI", 8),
                                  bg="#141822", fg="#64748b", activebackground="#ef4444", activeforeground="#ffffff",
                                  bd=0, padx=6, pady=4, cursor="hand2", command=lambda: self.close_tab(tab_id))
            close_btn.pack(side="left")
            tab_data["close_btn"] = close_btn

        # Bottom indicator underline (hidden until active)
        indicator = tk.Frame(btn_frame, bg="#141822", height=2)
        indicator.pack(fill="x", side="bottom")
        tab_data["indicator"] = indicator

    def switch_tab(self, tab_id: str):
        # Hide all tab frames and un-highlight tabs
        for t in self.tabs:
            t["frame"].pack_forget()
            if t.get("btn_frame"):
                t["btn_frame"].configure(bg="#141822")
                t["tab_btn"].configure(bg="#141822", fg="#94a3b8", font=("Segoe UI", 9))
                t["indicator"].configure(bg="#141822")
                if "close_btn" in t:
                    t["close_btn"].configure(bg="#141822", fg="#64748b")

        # Activate selected tab
        selected = next((t for t in self.tabs if t["id"] == tab_id), None)
        if selected:
            self.active_tab_id = tab_id
            selected["frame"].pack(fill="both", expand=True)
            if selected.get("btn_frame"):
                selected["btn_frame"].configure(bg="#1e2230")
                selected["tab_btn"].configure(bg="#1e2230", fg="#ffffff", font=("Segoe UI", 9, "bold"))
                selected["indicator"].configure(bg="#ef4444")
                if "close_btn" in selected:
                    selected["close_btn"].configure(bg="#1e2230", fg="#94a3b8")

        if tab_id == "home":
            self._update_sidebar_active("home")
            self._render_recent_grid()

    def close_tab(self, tab_id: str):
        target = next((t for t in self.tabs if t["id"] == tab_id), None)
        if not target or tab_id == "home":
            return

        # Remove from tabs list first to prevent recursive re-entry
        self.tabs.remove(target)

        # 1. Close viewer if running (clear callback to prevent cycle)
        if target.get("viewer"):
            viewer = target["viewer"]
            viewer.on_close_cb = None
            try:
                viewer.close()
            except Exception:
                pass

        # 2. Destroy widgets
        try:
            target["frame"].destroy()
        except Exception:
            pass
        try:
            target["btn_frame"].destroy()
        except Exception:
            pass

        # 3. Switch to previous tab or home
        if self.active_tab_id == tab_id:
            next_tab = self.tabs[-1]["id"] if self.tabs else "home"
            self.switch_tab(next_tab)

    # =========================================================================
    # HOME DASHBOARD (ANYDESK STYLE)
    # =========================================================================
    def _build_home_dashboard(self, parent_frame: tk.Frame):
        # Top Quick Connect Search Bar
        connect_bar_container = tk.Frame(parent_frame, bg="#161924", height=60)
        connect_bar_container.pack(fill="x", padx=20, pady=(16, 12))

        search_inner = tk.Frame(connect_bar_container, bg="#161924")
        search_inner.pack(fill="x", padx=16, pady=10)

        tk.Label(search_inner, text="Enter Remote Address:", font=("Segoe UI", 10, "bold"),
                 bg="#161924", fg="#f1f5f9").pack(side="left", padx=(0, 10))

        self.remote_entry = tk.Entry(search_inner, font=("Consolas", 13), bg="#202534", fg="#f1f5f9",
                                     insertbackground="#ef4444", bd=1, relief="solid",
                                     highlightbackground="#2d354a", highlightthickness=1)
        self.remote_entry.pack(side="left", fill="x", expand=True, padx=(0, 10), ipady=4)
        self.remote_entry.bind("<Return>", lambda e: self._connect_session())

        # Password Entry (Optional Unattended)
        self.password_entry = tk.Entry(search_inner, font=("Segoe UI", 10), bg="#202534", fg="#f1f5f9",
                                       insertbackground="#ef4444", bd=1, relief="solid", show="*",
                                       highlightbackground="#2d354a", highlightthickness=1, width=12)
        self.password_entry.pack(side="left", padx=(0, 10), ipady=4)
        self.password_entry.bind("<Return>", lambda e: self._connect_session())

        connect_btn = tk.Button(search_inner, text="Connect Session", font=("Segoe UI", 10, "bold"),
                                bg="#ef4444", fg="#ffffff", activebackground="#dc2626", activeforeground="#ffffff",
                                bd=0, padx=16, pady=6, cursor="hand2", command=self._connect_session)
        connect_btn.pack(side="left")

        # Two-Column Hero Grid
        hero_container = tk.Frame(parent_frame, bg="#0c0e14")
        hero_container.pack(fill="x", padx=20, pady=(0, 12))

        # --- LEFT CARD: This Desk (Your ID) ---
        this_desk_card = tk.Frame(hero_container, bg="#161924", bd=1, relief="solid",
                                  highlightbackground="#282e3f", highlightthickness=1)
        this_desk_card.pack(side="left", fill="both", expand=True, padx=(0, 8))

        h_frame = tk.Frame(this_desk_card, bg="#161924")
        h_frame.pack(fill="x", padx=16, pady=(12, 2))
        tk.Label(h_frame, text="💻 This Desk", font=("Segoe UI", 11, "bold"), bg="#161924", fg="#f1f5f9").pack(side="left")
        tk.Label(h_frame, text="Ready for incoming control", font=("Segoe UI", 8), bg="#161924", fg="#22c55e").pack(side="right")

        # Big Persistent Address Box
        id_box = tk.Frame(this_desk_card, bg="#202534", bd=1, relief="solid",
                          highlightbackground="#ef4444", highlightthickness=1)
        id_box.pack(fill="x", padx=16, pady=8)

        formatted_id = self._format_id(self.assigned_id)
        self.id_label = tk.Label(id_box, text=formatted_id, font=("Consolas", 20, "bold"),
                                 bg="#202534", fg="#f87171", pady=6)
        self.id_label.pack()

        # Action Buttons Row
        act_row = tk.Frame(this_desk_card, bg="#161924")
        act_row.pack(fill="x", padx=16, pady=4)

        tk.Button(act_row, text="📋 Copy Address", font=("Segoe UI", 8, "bold"), bg="#24283b", fg="#c0caf5",
                  activebackground="#2f344d", activeforeground="#ef4444", bd=0, padx=12, pady=4, cursor="hand2",
                  command=self._copy_id).pack(side="left", padx=(0, 6))

        tk.Button(act_row, text="🔒 Set Unattended Password", font=("Segoe UI", 8), bg="#24283b", fg="#c0caf5",
                  activebackground="#2f344d", activeforeground="#ef4444", bd=0, padx=10, pady=4, cursor="hand2",
                  command=self._prompt_unattended_password).pack(side="left")

        # Worldwide Tunnel Row
        tunnel_row = tk.Frame(this_desk_card, bg="#161924")
        tunnel_row.pack(fill="x", padx=16, pady=(8, 12))

        tk.Label(tunnel_row, text="🌐 Worldwide Internet Access:", font=("Segoe UI", 8, "bold"),
                 bg="#161924", fg="#3b82f6").pack(anchor="w")
        self.internet_link_label = tk.Label(tunnel_row, text="Activating global tunnel...",
                                            font=("Consolas", 8), bg="#202534", fg="#e0af68", pady=3, padx=6)
        self.internet_link_label.pack(fill="x", pady=2)

        self.copy_link_btn = tk.Button(tunnel_row, text="🔗 Copy Worldwide Share Link", font=("Segoe UI", 8),
                                       bg="#24283b", fg="#3b82f6", activebackground="#2f344d", activeforeground="#60a5fa",
                                       bd=0, padx=8, pady=3, cursor="hand2", command=self._copy_internet_link)
        self.copy_link_btn.pack(pady=2)

        # --- RIGHT CARD: Engine Capabilities & Quick Invite ---
        right_card = tk.Frame(hero_container, bg="#161924", bd=1, relief="solid",
                              highlightbackground="#282e3f", highlightthickness=1)
        right_card.pack(side="right", fill="both", expand=True, padx=(8, 0))

        tk.Label(right_card, text="⚡ Performance & Subsystems", font=("Segoe UI", 11, "bold"),
                 bg="#161924", fg="#f1f5f9").pack(anchor="w", padx=16, pady=(12, 6))

        features = [
            ("⚡ DeskRT Codec", "60 FPS Tile Delta Video Stream with adaptive JPEG compression"),
            ("🎙️ PortAudio Voice", "Automatic Bloody Gaming Audio mic selection & 16kHz low-latency audio"),
            ("📋 64-Bit Clipboard", "Bidirectional Windows Clipboard auto-sync with Ctrl+V support"),
            ("🌐 Zero-Config Tunnel", "Cloudflare Worldwide Gateway enabling control across any network"),
            ("🛡️ Digitally Signed", "SHA-256 Authenticode certificate with DigiCert RFC 3161 timestamp")
        ]

        for feat_title, feat_desc in features:
            f_frame = tk.Frame(right_card, bg="#161924")
            f_frame.pack(fill="x", padx=16, pady=2)
            tk.Label(f_frame, text=feat_title, font=("Segoe UI", 8, "bold"), bg="#161924", fg="#ef4444", width=18, anchor="w").pack(side="left")
            tk.Label(f_frame, text=feat_desc, font=("Segoe UI", 8), bg="#161924", fg="#94a3b8", anchor="w").pack(side="left", fill="x", expand=True)

        # Web Console Quick Action
        web_btn = tk.Button(right_card, text="🌐 Open Browser Fallback Console", font=("Segoe UI", 8),
                            bg="#24283b", fg="#3b82f6", activebackground="#2f344d", activeforeground="#60a5fa",
                            bd=0, padx=10, pady=4, cursor="hand2", command=self._open_web)
        web_btn.pack(anchor="w", padx=16, pady=(8, 12))

        # --- BOTTOM SECTION: Recent Sessions & Discovery Grid ---
        recent_header_frame = tk.Frame(parent_frame, bg="#0c0e14")
        recent_header_frame.pack(fill="x", padx=20, pady=(6, 4))

        tk.Label(recent_header_frame, text="Recent Sessions & Favorites", font=("Segoe UI", 11, "bold"),
                 bg="#0c0e14", fg="#f1f5f9").pack(side="left")

        # Filter Variable
        self.recent_filter_var = tk.StringVar(value="all")
        filter_all = tk.Radiobutton(recent_header_frame, text="All", variable=self.recent_filter_var, value="all",
                                    bg="#0c0e14", fg="#94a3b8", selectcolor="#161924", activebackground="#0c0e14",
                                    indicatoron=0, bd=0, padx=8, pady=2, cursor="hand2", command=self._render_recent_grid)
        filter_all.pack(side="right", padx=2)

        filter_fav = tk.Radiobutton(recent_header_frame, text="⭐ Favorites", variable=self.recent_filter_var, value="favorites",
                                    bg="#0c0e14", fg="#94a3b8", selectcolor="#161924", activebackground="#0c0e14",
                                    indicatoron=0, bd=0, padx=8, pady=2, cursor="hand2", command=self._render_recent_grid)
        filter_fav.pack(side="right", padx=2)

        # Recent Sessions Card Grid Frame
        self.recent_grid_container = tk.Frame(parent_frame, bg="#0c0e14")
        self.recent_grid_container.pack(fill="both", expand=True, padx=20, pady=(4, 10))

        self._render_recent_grid()

    def _render_recent_grid(self):
        for child in self.recent_grid_container.winfo_children():
            child.destroy()

        recents = get_recent_sessions()
        filter_mode = self.recent_filter_var.get() if hasattr(self, "recent_filter_var") else "all"

        if filter_mode == "favorites":
            recents = [r for r in recents if r.get("favorite")]

        if not recents:
            empty_lbl = tk.Label(self.recent_grid_container, text="No sessions found. Enter an address above to connect.",
                                 font=("Segoe UI", 9), bg="#0c0e14", fg="#64748b", pady=20)
            empty_lbl.pack()
            return

        # Render cards in a responsive grid (up to 4 per row)
        grid_frame = tk.Frame(self.recent_grid_container, bg="#0c0e14")
        grid_frame.pack(fill="x")

        row = 0
        col = 0
        max_cols = 4

        for item in recents:
            target_id = item.get("id", "")
            alias = item.get("alias", f"Desktop - {target_id}")
            fav = item.get("favorite", False)
            last_seen = item.get("last_seen", "")

            card = tk.Frame(grid_frame, bg="#161924", bd=1, relief="solid",
                            highlightbackground="#282e3f", highlightthickness=1, width=230, height=138)
            card.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")
            card.pack_propagate(False)

            top_row = tk.Frame(card, bg="#161924")
            top_row.pack(fill="x", padx=10, pady=(8, 2))

            tk.Label(top_row, text="💻", font=("Segoe UI Emoji", 12), bg="#161924", fg="#ef4444").pack(side="left")

            fav_char = "★" if fav else "☆"
            fav_fg = "#eab308" if fav else "#64748b"
            fav_btn = tk.Button(top_row, text=fav_char, font=("Segoe UI", 11), bg="#161924", fg=fav_fg,
                                activebackground="#161924", activeforeground="#eab308", bd=0, cursor="hand2",
                                command=lambda t=target_id: self._on_toggle_fav(t))
            fav_btn.pack(side="right")

            lbl_alias = tk.Label(card, text=alias, font=("Segoe UI", 9, "bold"), bg="#161924", fg="#f1f5f9", anchor="w")
            lbl_alias.pack(fill="x", padx=10)
            lbl_id = tk.Label(card, text=target_id, font=("Consolas", 9), bg="#161924", fg="#ef4444", anchor="w")
            lbl_id.pack(fill="x", padx=10)
            lbl_seen = tk.Label(card, text=f"Last: {last_seen}", font=("Segoe UI", 7), bg="#161924", fg="#64748b", anchor="w")
            lbl_seen.pack(fill="x", padx=10)

            # Bottom Action Row with prominent, unclipped 1-Click Connect Button
            act_row = tk.Frame(card, bg="#161924")
            act_row.pack(fill="x", side="bottom", padx=10, pady=(0, 8))

            conn_btn = tk.Button(act_row, text="Connect ➜", font=("Segoe UI", 8, "bold"), bg="#ef4444", fg="#ffffff",
                                 activebackground="#dc2626", activeforeground="#ffffff", bd=0, padx=10, pady=3, cursor="hand2",
                                 command=lambda t=target_id: self._launch_session(t))
            conn_btn.pack(side="right")

            # Make entire card clickable for instant connection
            card.config(cursor="hand2")
            for w in (card, lbl_alias, lbl_id, lbl_seen):
                w.bind("<Button-1>", lambda e, t=target_id: self._launch_session(t))

            col += 1
            if col >= max_cols:
                col = 0
                row += 1

    def _on_toggle_fav(self, target_id: str):
        toggle_favorite(target_id)
        self._render_recent_grid()

    # =========================================================================
    # BOTTOM STATUS BAR
    # =========================================================================
    def _build_bottom_status_bar(self):
        bottom_bar = tk.Frame(self.root, bg="#12151e", height=30)
        bottom_bar.pack(fill="x", side="bottom")

        self.bottom_status_label = tk.Label(bottom_bar, text=f"Local Relay: http://localhost:{self.port}",
                                            font=("Segoe UI", 8), bg="#12151e", fg="#64748b")
        self.bottom_status_label.pack(side="left", padx=14, pady=4)

        tk.Label(bottom_bar, text=f"DeskRT 60FPS Delta Engine • 48kHz Discord HD Voice • v{APP_VERSION} (Digitally Signed)",
                 font=("Segoe UI", 8), bg="#12151e", fg="#64748b").pack(side="right", padx=14, pady=4)

    # =========================================================================
    # SESSION CONNECTION & TAB EMBEDDING
    # =========================================================================
    def _connect_session(self):
        raw_target = self.remote_entry.get().strip()
        pw = self.password_entry.get().strip() if hasattr(self, "password_entry") else ""
        if not raw_target:
            messagebox.showwarning("Input Required", "Please enter a valid remote 9-digit OpenDesk ID.")
            return
        self._launch_session(raw_target, pw)

    def _launch_session(self, raw_target: str, password: str = ""):
        parsed_id, direct_ws_url = parse_connect_target(raw_target)
        if not parsed_id:
            return

        # Record in recent sessions
        add_recent_session(parsed_id)

        # Check if tab already open for this session
        existing = next((t for t in self.tabs if t["id"] == parsed_id), None)
        if existing:
            self.switch_tab(parsed_id)
            return

        formatted = self._format_id(parsed_id)

        # Determine effective relay URL
        my_clean_id = self.assigned_id.replace(" ", "").replace("-", "").strip()
        if direct_ws_url:
            effective_relay = direct_ws_url
        elif parsed_id == my_clean_id:
            effective_relay = self.relay_url
        else:
            effective_relay = "auto"

        # Create new session tab container frame
        session_frame = tk.Frame(self.viewport_container, bg="#000000")

        # Instantiate EmbeddedSessionView directly inside the tab frame
        viewer = EmbeddedSessionView(
            parent=session_frame,
            relay_url=effective_relay,
            target_id=parsed_id,
            password=password,
            on_close=lambda: self.close_tab(parsed_id)
        )
        viewer.pack(fill="both", expand=True)

        tab_data = {
            "id": parsed_id,
            "title": formatted,
            "type": "session",
            "frame": session_frame,
            "viewer": viewer,
            "btn_frame": None
        }

        self.tabs.append(tab_data)
        self._render_tab_button(tab_data)
        self.switch_tab(parsed_id)

    # =========================================================================
    # ACTIONS, DIALOGS & CLIPBOARD
    # =========================================================================
    def _format_id(self, raw_id: str) -> str:
        clean = raw_id.replace(" ", "").replace("-", "")
        if len(clean) == 9:
            return f"{clean[:3]} {clean[3:6]} {clean[6:]}"
        return raw_id

    def _copy_id(self):
        clean = self.assigned_id.replace(" ", "")
        if clean and clean != "Connecting...":
            self.root.clipboard_clear()
            self.root.clipboard_append(self.assigned_id)
            messagebox.showinfo("Copied", f"OpenDesk Address {self.assigned_id} copied to clipboard!")

    def _copy_internet_link(self):
        if self.public_url:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.public_url)
            messagebox.showinfo("Copied", f"Worldwide Internet Link copied to clipboard:\n{self.public_url}\n\nSend this link to anyone on any network for instant remote assistance!")
        else:
            messagebox.showwarning("Pending", "Global internet tunnel is still initializing. Please wait a moment.")

    def _prompt_unattended_password(self):
        current_pw = get_unattended_password()
        new_pw = simpledialog.askstring("Unattended Access", "Enter password for unattended remote access:\n(Leave empty to disable)",
                                        parent=self.root, show="*")
        if new_pw is not None:
            set_unattended_password(new_pw)
            status_txt = "Password updated successfully!" if new_pw else "Unattended password disabled."
            messagebox.showinfo("Security", status_txt)

    def _toggle_host_mic(self):
        if not self.host_agent or not hasattr(self.host_agent, "audio_engine") or not self.host_agent.audio_engine:
            return
        engine = self.host_agent.audio_engine
        engine.mic_enabled = not engine.mic_enabled
        if engine.mic_enabled:
            self.mic_btn.config(text="🎙️ Mic: ON", bg="#1f382a", fg="#9ece6a")
        else:
            self.mic_btn.config(text="🔇 Mic: MUTED", bg="#3d2a1f", fg="#e0af68")

    def _on_incoming_connection_request(self, client_id: str, display_id: str, on_decision: Callable):
        """Dispatches incoming AnyDesk connection request dialog to Tkinter UI main thread."""
        if self.root and self.root.winfo_exists():
            self.root.after(0, lambda: self._show_incoming_connection_dialog(client_id, display_id, on_decision))
        else:
            on_decision(client_id, False, {})

    def _show_incoming_connection_dialog(self, client_id: str, display_id: str, on_decision: Callable):
        """AnyDesk-style Incoming Session Request Dialog with permission toggles and audio chime."""
        # 1. Play alert sound chime
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            pass

        # 2. Build AnyDesk-style modal dialog
        dialog = tk.Toplevel(self.root)
        dialog.title("OpenDesk - Incoming Connection Request")
        dialog.geometry("460x390")
        dialog.minsize(440, 380)
        dialog.maxsize(520, 440)
        dialog.configure(bg="#141822")
        dialog.attributes("-topmost", True)
        dialog.lift()

        # Center dialog relative to main window
        try:
            dialog.update_idletasks()
            x = self.root.winfo_x() + (self.root.winfo_width() - 460) // 2
            y = self.root.winfo_y() + (self.root.winfo_height() - 390) // 2
            dialog.geometry(f"460x390+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

        allow_input_var = tk.BooleanVar(value=True)
        allow_audio_var = tk.BooleanVar(value=True)
        allow_clipboard_var = tk.BooleanVar(value=True)
        allow_file_var = tk.BooleanVar(value=True)

        responded = [False]

        def respond(accepted: bool):
            if not responded[0]:
                responded[0] = True
                perms = {
                    "input": allow_input_var.get(),
                    "audio": allow_audio_var.get(),
                    "clipboard": allow_clipboard_var.get(),
                    "file_transfer": allow_file_var.get(),
                } if accepted else {}
                try:
                    dialog.destroy()
                except Exception:
                    pass
                on_decision(client_id, accepted, perms)

        dialog.protocol("WM_DELETE_WINDOW", lambda: respond(False))

        # Header Frame
        header = tk.Frame(dialog, bg="#181c2b", padx=20, pady=12)
        header.pack(fill="x")

        icon_row = tk.Frame(header, bg="#181c2b")
        icon_row.pack(fill="x")
        tk.Label(icon_row, text="⚡ Incoming Connection Request", font=("Segoe UI", 12, "bold"),
                 bg="#181c2b", fg="#ef4444").pack(side="left")

        clean_disp = self._format_id(display_id)
        tk.Label(header, text=f"Remote Client: {clean_disp}", font=("Segoe UI", 11, "bold"),
                 bg="#181c2b", fg="#f1f5f9").pack(anchor="w", pady=(6, 2))
        tk.Label(header, text="A remote user is requesting access to view and control your desktop.",
                 font=("Segoe UI", 8), bg="#181c2b", fg="#94a3b8").pack(anchor="w")

        # Permissions Card
        perms_card = tk.Frame(dialog, bg="#1a1e2b", bd=1, relief="solid", highlightbackground="#282e3f", highlightthickness=1)
        perms_card.pack(fill="both", expand=True, padx=20, pady=10)

        tk.Label(perms_card, text="🛡️ Granted Permissions for this Session:", font=("Segoe UI", 9, "bold"),
                 bg="#1a1e2b", fg="#38bdf8").pack(anchor="w", padx=14, pady=(8, 4))

        cb1 = tk.Checkbutton(perms_card, text="Allow Remote Mouse & Keyboard Control", variable=allow_input_var,
                             font=("Segoe UI", 9), bg="#1a1e2b", fg="#f1f5f9", selectcolor="#141822",
                             activebackground="#1a1e2b", activeforeground="#f1f5f9")
        cb1.pack(anchor="w", padx=14, pady=2)

        cb2 = tk.Checkbutton(perms_card, text="Allow Real-Time Audio / Voice Call", variable=allow_audio_var,
                             font=("Segoe UI", 9), bg="#1a1e2b", fg="#f1f5f9", selectcolor="#141822",
                             activebackground="#1a1e2b", activeforeground="#f1f5f9")
        cb2.pack(anchor="w", padx=14, pady=2)

        cb3 = tk.Checkbutton(perms_card, text="Allow Bidirectional Clipboard Synchronization", variable=allow_clipboard_var,
                             font=("Segoe UI", 9), bg="#1a1e2b", fg="#f1f5f9", selectcolor="#141822",
                             activebackground="#1a1e2b", activeforeground="#f1f5f9")
        cb3.pack(anchor="w", padx=14, pady=2)

        cb4 = tk.Checkbutton(perms_card, text="Allow File Transfer & Directory Browsing", variable=allow_file_var,
                             font=("Segoe UI", 9), bg="#1a1e2b", fg="#f1f5f9", selectcolor="#141822",
                             activebackground="#1a1e2b", activeforeground="#f1f5f9")
        cb4.pack(anchor="w", padx=14, pady=2)

        # Action Buttons Row
        btn_frame = tk.Frame(dialog, bg="#141822", padx=20, pady=12)
        btn_frame.pack(fill="x", side="bottom")

        accept_btn = tk.Button(btn_frame, text="✓ Accept Connection", font=("Segoe UI", 10, "bold"),
                               bg="#22c55e", fg="#0f172a", activebackground="#16a34a", activeforeground="#ffffff",
                               bd=0, padx=18, pady=8, cursor="hand2", command=lambda: respond(True))
        accept_btn.pack(side="left")

        reject_btn = tk.Button(btn_frame, text="✕ Dismiss / Reject", font=("Segoe UI", 10, "bold"),
                               bg="#ef4444", fg="#ffffff", activebackground="#dc2626", activeforeground="#ffffff",
                               bd=0, padx=16, pady=8, cursor="hand2", command=lambda: respond(False))
        reject_btn.pack(side="right")

    def _open_web(self):
        webbrowser.open(f"http://localhost:{self.port}")

    def _open_settings(self):
        settings_win = tk.Toplevel(self.root)
        settings_win.title("OpenDesk Settings & Voice Configuration")
        settings_win.geometry("620x760")
        settings_win.minsize(580, 680)
        settings_win.configure(bg="#141822")
        settings_win.grab_set()

        tk.Label(settings_win, text="⚙️ OpenDesk Settings & Discord HD Voice Suite", font=("Segoe UI", 12, "bold"),
                 bg="#141822", fg="#f1f5f9").pack(anchor="w", padx=20, pady=(14, 4))

        # --- Section 1: Relay WebSocket Configuration ---
        tk.Label(settings_win, text="🌐 Relay WebSocket Server URL:", font=("Segoe UI", 9, "bold"),
                 bg="#141822", fg="#ef4444").pack(anchor="w", padx=20, pady=(4, 2))
        entry_box = tk.Entry(settings_win, font=("Consolas", 10), bg="#202534", fg="#f1f5f9",
                             insertbackground="#ef4444", bd=1, relief="solid")
        entry_box.pack(fill="x", padx=20, pady=(2, 6), ipady=3)
        entry_box.insert(0, self.relay_url)

        # --- Section 2: Discord-Grade Voice & Audio Suite ---
        tk.Label(settings_win, text="🎧 Voice & Video Settings (Discord-Grade HD Audio):", font=("Segoe UI", 9, "bold"),
                 bg="#141822", fg="#ef4444").pack(anchor="w", padx=20, pady=(6, 2))

        audio_card = tk.Frame(settings_win, bg="#1a1e2b", bd=1, relief="solid", highlightbackground="#282e3f")
        audio_card.pack(fill="x", padx=20, pady=2)

        devs = get_available_audio_devices()
        in_names = [d["name"] for d in devs.get("inputs", [])] or ["Default System Microphone"]
        out_names = [d["name"] for d in devs.get("outputs", [])] or ["Default System Speaker"]
        audio_cfg = get_audio_settings()

        # Input & Output Device Dropdowns (2 columns)
        dev_row = tk.Frame(audio_card, bg="#1a1e2b")
        dev_row.pack(fill="x", padx=14, pady=(6, 4))

        in_box = tk.Frame(dev_row, bg="#1a1e2b")
        in_box.pack(side="left", fill="x", expand=True, padx=(0, 6))
        tk.Label(in_box, text="INPUT DEVICE", font=("Segoe UI", 8, "bold"), bg="#1a1e2b", fg="#94a3b8").pack(anchor="w")
        in_combo = ttk.Combobox(in_box, values=in_names, state="readonly", font=("Segoe UI", 9))
        in_combo.pack(fill="x", pady=(2, 0))
        saved_in = audio_cfg.get("input_device", "")
        if saved_in in in_names:
            in_combo.set(saved_in)
        elif in_names:
            in_combo.current(0)

        out_box = tk.Frame(dev_row, bg="#1a1e2b")
        out_box.pack(side="right", fill="x", expand=True, padx=(6, 0))
        tk.Label(out_box, text="OUTPUT DEVICE", font=("Segoe UI", 8, "bold"), bg="#1a1e2b", fg="#94a3b8").pack(anchor="w")
        out_combo = ttk.Combobox(out_box, values=out_names, state="readonly", font=("Segoe UI", 9))
        out_combo.pack(fill="x", pady=(2, 0))
        saved_out = audio_cfg.get("output_device", "")
        if saved_out in out_names:
            out_combo.set(saved_out)
        elif out_names:
            out_combo.current(0)

        # Volume Sliders Row (Input Volume & Output Volume)
        sliders_row = tk.Frame(audio_card, bg="#1a1e2b")
        sliders_row.pack(fill="x", padx=14, pady=(2, 4))

        gain_box = tk.Frame(sliders_row, bg="#1a1e2b")
        gain_box.pack(side="left", fill="x", expand=True, padx=(0, 6))
        tk.Label(gain_box, text="INPUT VOLUME", font=("Segoe UI", 8, "bold"), bg="#1a1e2b", fg="#94a3b8").pack(anchor="w")
        gain_scale = tk.Scale(gain_box, from_=50, to=200, orient="horizontal",
                              bg="#1a1e2b", fg="#38bdf8", troughcolor="#141822", highlightthickness=0, bd=0)
        gain_scale.set(int(audio_cfg.get("mic_gain", 1.0) * 100))
        gain_scale.pack(fill="x", pady=2)

        vol_box = tk.Frame(sliders_row, bg="#1a1e2b")
        vol_box.pack(side="right", fill="x", expand=True, padx=(6, 0))
        tk.Label(vol_box, text="OUTPUT VOLUME", font=("Segoe UI", 8, "bold"), bg="#1a1e2b", fg="#94a3b8").pack(anchor="w")
        vol_scale = tk.Scale(vol_box, from_=0, to=100, orient="horizontal",
                             bg="#1a1e2b", fg="#38bdf8", troughcolor="#141822", highlightthickness=0, bd=0)
        vol_scale.set(int(audio_cfg.get("speaker_volume", 1.0) * 100))
        vol_scale.pack(fill="x", pady=2)

        # Discord-Style "Let's Check" Mic Test (Pipes local mic to headphones in real-time)
        test_frame = tk.Frame(audio_card, bg="#141822", bd=1, relief="solid", highlightbackground="#2d3345")
        test_frame.pack(fill="x", padx=14, pady=6)

        tk.Label(test_frame, text="MIC TEST — Having mic issues? Click to hear yourself in real-time:",
                 font=("Segoe UI", 8), bg="#141822", fg="#94a3b8").pack(anchor="w", padx=10, pady=(6, 2))

        test_row = tk.Frame(test_frame, bg="#141822")
        test_row.pack(fill="x", padx=10, pady=(2, 8))

        test_engine_ref = [None]
        test_canvas = tk.Canvas(test_row, height=18, bg="#0d1117", highlightthickness=1, highlightbackground="#2d3345")
        test_canvas.pack(side="left", fill="x", expand=True, padx=(0, 10))
        vu_bar = test_canvas.create_rectangle(0, 0, 0, 18, fill="#10b981", outline="")

        def on_test_level(level: float):
            if test_canvas.winfo_exists():
                cw = max(1, test_canvas.winfo_width())
                w = max(0, min(cw, int(level * cw)))
                color = "#ef4444" if level > 0.85 else ("#f59e0b" if level > 0.65 else "#10b981")
                test_canvas.coords(vu_bar, 0, 0, w, 18)
                test_canvas.itemconfig(vu_bar, fill=color)

        def toggle_mic_test():
            if test_engine_ref[0] is None:
                try:
                    chosen_mic = in_combo.get()
                    chosen_spk = out_combo.get()
                    chosen_gain = float(gain_scale.get()) / 100.0
                    chosen_vol = float(vol_scale.get()) / 100.0
                    engine = AudioEngine(on_mic_level_callback=on_test_level)
                    engine.preferred_input = chosen_mic
                    engine.preferred_output = chosen_spk
                    engine.set_gain(chosen_gain)
                    engine.set_speaker_volume(chosen_vol)
                    engine.start_loopback_test()
                    test_engine_ref[0] = engine
                    test_btn.config(text="⏹️ Stop Testing", bg="#ef4444", fg="#ffffff")
                except Exception as e:
                    messagebox.showerror("Audio Test Error", f"Could not initialize loopback mic test: {e}")
            else:
                try:
                    test_engine_ref[0].stop_loopback_test()
                    test_engine_ref[0].stop()
                except Exception:
                    pass
                test_engine_ref[0] = None
                test_btn.config(text="🎙️ Let's Check", bg="#202534", fg="#f1f5f9")
                if test_canvas.winfo_exists():
                    test_canvas.coords(vu_bar, 0, 0, 0, 18)

        test_btn = tk.Button(test_row, text="🎙️ Let's Check", font=("Segoe UI", 8, "bold"),
                             bg="#202534", fg="#f1f5f9", activebackground="#ef4444", activeforeground="#ffffff",
                             bd=0, padx=14, pady=4, cursor="hand2", command=toggle_mic_test)
        test_btn.pack(side="right")

        # Discord-Style Input Mode (Voice Activity vs Push to Talk)
        input_mode_var = tk.StringVar(value=audio_cfg.get("input_mode", "voice_activity"))
        auto_vad_var = tk.BooleanVar(value=audio_cfg.get("auto_sensitivity", True))

        mode_row = tk.Frame(audio_card, bg="#1a1e2b")
        mode_row.pack(fill="x", padx=14, pady=(4, 2))
        tk.Label(mode_row, text="INPUT MODE:", font=("Segoe UI", 8, "bold"), bg="#1a1e2b", fg="#94a3b8").pack(side="left")

        rb1 = tk.Radiobutton(mode_row, text="Voice Activity", variable=input_mode_var, value="voice_activity",
                             bg="#1a1e2b", fg="#f1f5f9", selectcolor="#141822", activebackground="#1a1e2b",
                             activeforeground="#f1f5f9", font=("Segoe UI", 8))
        rb1.pack(side="left", padx=8)

        rb2 = tk.Radiobutton(mode_row, text="Push to Talk [Ctrl]", variable=input_mode_var, value="push_to_talk",
                             bg="#1a1e2b", fg="#f1f5f9", selectcolor="#141822", activebackground="#1a1e2b",
                             activeforeground="#f1f5f9", font=("Segoe UI", 8))
        rb2.pack(side="left", padx=8)

        # VAD Sensitivity Controls
        vad_box = tk.Frame(audio_card, bg="#1a1e2b")
        vad_box.pack(fill="x", padx=14, pady=(2, 4))
        
        vad_chk = tk.Checkbutton(vad_box, text="Automatically determine input sensitivity (Discord Standard)",
                                 variable=auto_vad_var, bg="#1a1e2b", fg="#94a3b8", selectcolor="#141822",
                                 activebackground="#1a1e2b", activeforeground="#f1f5f9", font=("Segoe UI", 8))
        vad_chk.pack(anchor="w")

        vad_scale = tk.Scale(vad_box, from_=0, to=100, orient="horizontal",
                             bg="#1a1e2b", fg="#10b981", troughcolor="#141822", highlightthickness=0, bd=0)
        vad_scale.set(int(audio_cfg.get("vad_sensitivity", 0.25) * 100))
        vad_scale.pack(fill="x", pady=2)

        # Discord Voice Processing Checkboxes
        echo_var = tk.BooleanVar(value=audio_cfg.get("echo_cancellation", True))
        noise_var = tk.BooleanVar(value=audio_cfg.get("noise_suppression", True))
        agc_var = tk.BooleanVar(value=audio_cfg.get("agc_enabled", True))

        proc_row = tk.Frame(audio_card, bg="#1a1e2b")
        proc_row.pack(fill="x", padx=14, pady=(2, 8))

        tk.Checkbutton(proc_row, text="Echo Cancellation", variable=echo_var,
                       bg="#1a1e2b", fg="#94a3b8", selectcolor="#141822", activebackground="#1a1e2b",
                       activeforeground="#f1f5f9", font=("Segoe UI", 8)).pack(side="left", padx=(0, 10))

        tk.Checkbutton(proc_row, text="Noise Suppression (Fan/Hum)", variable=noise_var,
                       bg="#1a1e2b", fg="#94a3b8", selectcolor="#141822", activebackground="#1a1e2b",
                       activeforeground="#f1f5f9", font=("Segoe UI", 8)).pack(side="left", padx=(0, 10))

        tk.Checkbutton(proc_row, text="Auto Gain Control (AGC)", variable=agc_var,
                       bg="#1a1e2b", fg="#94a3b8", selectcolor="#141822", activebackground="#1a1e2b",
                       activeforeground="#f1f5f9", font=("Segoe UI", 8)).pack(side="left")

        def on_settings_close():
            if test_engine_ref[0] is not None:
                try:
                    test_engine_ref[0].stop_loopback_test()
                    test_engine_ref[0].stop()
                except Exception:
                    pass
                test_engine_ref[0] = None
            settings_win.destroy()

        settings_win.protocol("WM_DELETE_WINDOW", on_settings_close)

        # --- Section 3: Software Updates & Maintenance ---
        tk.Label(settings_win, text="🔄 Software Updates & Maintenance:", font=("Segoe UI", 9, "bold"),
                 bg="#141822", fg="#ef4444").pack(anchor="w", padx=20, pady=(6, 2))

        upd_card = tk.Frame(settings_win, bg="#1a1e2b", bd=1, relief="solid", highlightbackground="#282e3f")
        upd_card.pack(fill="x", padx=20, pady=2)

        info_row = tk.Frame(upd_card, bg="#1a1e2b")
        info_row.pack(fill="x", padx=12, pady=(6, 2))
        tk.Label(info_row, text=f"Installed Version: v{APP_VERSION} (Authenticode Signed)", font=("Segoe UI", 9, "bold"),
                 bg="#1a1e2b", fg="#f1f5f9").pack(side="left")

        check_btn = tk.Button(info_row, text="🔄 Check Updates Now", font=("Segoe UI", 8, "bold"),
                              bg="#202534", fg="#f1f5f9", activebackground="#ef4444", activeforeground="#ffffff",
                              bd=0, padx=10, pady=3, cursor="hand2", command=lambda: self._check_updates_interactive(settings_win))
        check_btn.pack(side="right")

        auto_upd_var = tk.BooleanVar(value=get_auto_update_enabled())
        def on_toggle_auto():
            set_auto_update_enabled(auto_upd_var.get())

        chk = tk.Checkbutton(upd_card, text="Automatically check for updates on startup", variable=auto_upd_var,
                             bg="#1a1e2b", fg="#94a3b8", selectcolor="#141822", activebackground="#1a1e2b",
                             activeforeground="#f1f5f9", font=("Segoe UI", 8), command=on_toggle_auto)
        chk.pack(anchor="w", padx=12, pady=(2, 6))

        def save_and_reconnect():
            if test_engine_ref[0] is not None:
                try:
                    test_engine_ref[0].stop_loopback_test()
                    test_engine_ref[0].stop()
                except Exception:
                    pass
                test_engine_ref[0] = None

            # 1. Save persistent audio settings with full Discord suite
            new_audio = {
                "input_device": in_combo.get(),
                "output_device": out_combo.get(),
                "mic_gain": float(gain_scale.get()) / 100.0,
                "speaker_volume": float(vol_scale.get()) / 100.0,
                "input_mode": input_mode_var.get(),
                "vad_sensitivity": float(vad_scale.get()) / 100.0,
                "auto_sensitivity": auto_vad_var.get(),
                "ptt_key": "Control_L",
                "noise_suppression": noise_var.get(),
                "echo_cancellation": echo_var.get(),
                "agc_enabled": agc_var.get(),
                "noise_gate": True
            }
            save_audio_settings(new_audio)

            if hasattr(self, "host_agent") and self.host_agent and hasattr(self.host_agent, "audio_engine") and self.host_agent.audio_engine:
                self.host_agent.audio_engine.preferred_input = new_audio["input_device"]
                self.host_agent.audio_engine.preferred_output = new_audio["output_device"]
                self.host_agent.audio_engine.set_gain(new_audio["mic_gain"])
                self.host_agent.audio_engine.set_speaker_volume(new_audio["speaker_volume"])

            # 2. Save relay URL if modified
            new_url = entry_box.get().strip()
            settings_win.destroy()
            if new_url and new_url != self.relay_url:
                self.relay_url = new_url
                messagebox.showinfo("Saved", f"Preferences saved!\nRelay URL updated to:\n{self.relay_url}\n\nPlease restart OpenDesk to apply new relay.")
            else:
                messagebox.showinfo("Saved", "OpenDesk voice configuration & preferences saved successfully!")

        btn_row = tk.Frame(settings_win, bg="#141822")
        btn_row.pack(fill="x", padx=20, pady=14)

        tk.Button(btn_row, text="Save Settings", font=("Segoe UI", 9, "bold"), bg="#ef4444", fg="#ffffff",
                  bd=0, padx=16, pady=6, cursor="hand2", command=save_and_reconnect).pack(side="left")
        tk.Button(btn_row, text="Cancel", font=("Segoe UI", 9), bg="#202534", fg="#f1f5f9",
                  bd=0, padx=14, pady=6, cursor="hand2", command=on_settings_close).pack(side="right")

    # =========================================================================
    # BACKGROUND ENGINE SERVICES
    # =========================================================================
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
            unattended_pw = get_unattended_password()
            self.host_agent = HostAgent(
                relay_url=self.relay_url,
                host_id=self.assigned_id,
                password=unattended_pw,
                on_connection_request=self._on_incoming_connection_request
            )

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

        # 4. Background Automatic Update Check (if enabled)
        def run_update_check():
            time.sleep(2.5)
            try:
                if get_auto_update_enabled():
                    info = check_for_updates(current_version=APP_VERSION)
                    if info and info.get("available"):
                        self.root.after(0, lambda: self._show_update_banner(info))
            except Exception as e:
                print(f"[OpenDesk] Background update check notice: {e}")

        t_upd = threading.Thread(target=run_update_check, daemon=True)
        t_upd.start()

    def _on_agent_online(self):
        formatted = self._format_id(self.assigned_id)
        self.id_label.config(text=formatted)
        if not self.public_url:
            self.status_badge.config(text="● LOCAL READY", bg="#1f382a", fg="#9ece6a")
        else:
            threading.Thread(target=lambda: publish_host_rendezvous(self.assigned_id, self.public_url), daemon=True).start()

    def _on_tunnel_url_ready(self, url: str):
        self.public_url = url
        self.root.after(0, self._update_tunnel_ui)
        if self.assigned_id and url:
            threading.Thread(target=lambda: publish_host_rendezvous(self.assigned_id, url), daemon=True).start()
            if self.rendezvous_heartbeat is None:
                self.rendezvous_heartbeat = RendezvousHeartbeat(
                    host_id_getter=lambda: self.assigned_id,
                    tunnel_url_getter=lambda: self.public_url,
                    interval=30.0
                )
                self.rendezvous_heartbeat.start()

    def _update_tunnel_ui(self):
        if self.public_url:
            self.internet_link_label.config(text=self.public_url, fg="#9ece6a")
            self.status_badge.config(text="● WORLDWIDE ONLINE", bg="#1f382a", fg="#9ece6a")
            self.bottom_status_label.config(text=f"Global: {self.public_url}")

    def _on_close(self):
        if hasattr(self, "rendezvous_heartbeat") and self.rendezvous_heartbeat:
            try:
                self.rendezvous_heartbeat.stop()
            except Exception:
                pass

        # Stop all embedded session viewers
        for t in self.tabs:
            if t.get("viewer"):
                try:
                    t["viewer"].close()
                except Exception:
                    pass

        try:
            if self.tunnel:
                self.tunnel.stop()
        except Exception:
            pass
        try:
            if self.host_agent:
                self.host_agent.stop()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass
        time.sleep(0.05)
        sys.exit(0)


def main():
    port = find_free_port(8080)
    root = tk.Tk()
    app = OpenDeskGUI(root, port)
    root.mainloop()


if __name__ == "__main__":
    main()
