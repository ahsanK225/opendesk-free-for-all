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
        set_auto_update_enabled
    )
    from opendesk.common.updater import (
        APP_VERSION,
        check_for_updates,
        download_update_file,
        apply_update_and_restart
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
        set_auto_update_enabled
    )
    from common.updater import (
        APP_VERSION,
        check_for_updates,
        download_update_file,
        apply_update_and_restart
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
        tk.Label(left_box, text=f"Update Available: OpenDesk v{remote_ver} is now ready to install!",
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
        dialog.geometry("560x430")
        dialog.minsize(520, 390)
        dialog.configure(bg="#141822")
        dialog.grab_set()

        # Header
        h_frame = tk.Frame(dialog, bg="#141822")
        h_frame.pack(fill="x", padx=20, pady=(16, 4))

        tk.Label(h_frame, text="⚡ OpenDesk Software Update", font=("Segoe UI", 13, "bold"),
                 bg="#141822", fg="#f1f5f9").pack(anchor="w")
        sub_txt = f"A new version v{update_info.get('version', '')} is available! (Installed: v{APP_VERSION} • Released: {update_info.get('release_date', 'Recent')})"
        tk.Label(h_frame, text=sub_txt, font=("Segoe UI", 9), bg="#141822", fg="#22c55e").pack(anchor="w")

        # Changelog Frame
        cl_frame = tk.Frame(dialog, bg="#181c28", bd=1, relief="solid", highlightbackground="#282e3f")
        cl_frame.pack(fill="both", expand=True, padx=20, pady=10)

        tk.Label(cl_frame, text="What's New in this Version:", font=("Segoe UI", 9, "bold"),
                 bg="#181c28", fg="#ef4444").pack(anchor="w", padx=12, pady=(8, 4))

        text_box = tk.Text(cl_frame, font=("Segoe UI", 9), bg="#141822", fg="#cbd5e1",
                           wrap="word", bd=0, padx=10, pady=8)
        text_box.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        text_box.insert("1.0", update_info.get("changelog", "Improvements and bug fixes."))
        text_box.configure(state="disabled")

        # Progress / Status Frame
        prog_frame = tk.Frame(dialog, bg="#141822")
        prog_frame.pack(fill="x", padx=20, pady=(0, 10))

        status_lbl = tk.Label(prog_frame, text="Ready. Click 'Update & Restart' to download and automatically upgrade.",
                              font=("Segoe UI", 8), bg="#141822", fg="#94a3b8")
        status_lbl.pack(anchor="w", pady=(0, 4))

        progress_bar = ttk.Progressbar(prog_frame, orient="horizontal", mode="determinate")
        progress_bar.pack(fill="x")

        # Buttons Row
        btn_row = tk.Frame(dialog, bg="#141822")
        btn_row.pack(fill="x", padx=20, pady=(0, 16))

        cancel_flag = [False]

        def on_cancel():
            cancel_flag[0] = True
            dialog.destroy()

        def start_download():
            apply_btn.configure(state="disabled", text="Downloading...")
            cancel_btn.configure(text="Cancel")

            download_url = update_info.get("download_url", "")
            if not download_url:
                messagebox.showerror("Error", "Download URL not found in update manifest.", parent=dialog)
                return

            def run_dl():
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

                success = download_update_file(download_url, temp_exe, on_progress, cancel_flag=lambda: cancel_flag[0])

                if success and not cancel_flag[0]:
                    dialog.after(0, lambda: [
                        status_lbl.configure(text="Download complete! Restarting OpenDesk into new version...", fg="#22c55e"),
                        dialog.after(800, lambda: apply_update_and_restart(temp_exe))
                    ])
                elif not cancel_flag[0]:
                    dialog.after(0, lambda: [
                        status_lbl.configure(text="Download failed. Please check internet connection.", fg="#ef4444"),
                        apply_btn.configure(state="normal", text="Retry Download")
                    ])

            threading.Thread(target=run_dl, daemon=True).start()

        apply_btn = tk.Button(btn_row, text="🚀 Update & Restart Now", font=("Segoe UI", 9, "bold"),
                              bg="#ef4444", fg="#ffffff", activebackground="#dc2626", activeforeground="#ffffff",
                              bd=0, padx=16, pady=6, cursor="hand2", command=start_download)
        apply_btn.pack(side="left")

        cancel_btn = tk.Button(btn_row, text="Later", font=("Segoe UI", 9),
                               bg="#202534", fg="#cbd5e1", activebackground="#2a3144", activeforeground="#f1f5f9",
                               bd=0, padx=14, pady=6, cursor="hand2", command=on_cancel)
        cancel_btn.pack(side="right")

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
                            highlightbackground="#282e3f", highlightthickness=1, width=220, height=110)
            card.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")
            card.pack_propagate(False)

            top_row = tk.Frame(card, bg="#161924")
            top_row.pack(fill="x", padx=10, pady=(8, 2))

            tk.Label(top_row, text="💻", font=("Segoe UI Emoji", 12), bg="#161924", fg="#ef4444").pack(side="left")

            fav_char = "★" if fav else "☆"
            fav_fg = "#eab308" if fav else "#64748b"
            fav_btn = tk.Button(top_row, text=fav_char, font=("Segoe UI", 10), bg="#161924", fg=fav_fg,
                                activebackground="#161924", activeforeground="#eab308", bd=0, cursor="hand2",
                                command=lambda t=target_id: self._on_toggle_fav(t))
            fav_btn.pack(side="right")

            tk.Label(card, text=alias, font=("Segoe UI", 9, "bold"), bg="#161924", fg="#f1f5f9", anchor="w").pack(fill="x", padx=10)
            tk.Label(card, text=target_id, font=("Consolas", 9), bg="#161924", fg="#ef4444", anchor="w").pack(fill="x", padx=10)
            tk.Label(card, text=f"Last: {last_seen}", font=("Segoe UI", 7), bg="#161924", fg="#64748b", anchor="w").pack(fill="x", padx=10)

            # 1-Click Connect Button
            conn_btn = tk.Button(card, text="Connect ➜", font=("Segoe UI", 8, "bold"), bg="#202534", fg="#f1f5f9",
                                 activebackground="#ef4444", activeforeground="#ffffff", bd=0, padx=8, pady=2, cursor="hand2",
                                 command=lambda t=target_id: self._launch_session(t))
            conn_btn.pack(anchor="e", padx=10, pady=(2, 6))

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

        tk.Label(bottom_bar, text=f"DeskRT 60FPS Delta Engine • 16kHz HD Voice • v{APP_VERSION} (Digitally Signed)",
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
        clean = raw_target.replace(" ", "").replace("-", "").strip()
        if not clean:
            return

        # Record in recent sessions
        add_recent_session(clean)

        # Check if tab already open for this session
        existing = next((t for t in self.tabs if t["id"] == clean), None)
        if existing:
            self.switch_tab(clean)
            return

        formatted = self._format_id(clean)

        # Create new session tab container frame
        session_frame = tk.Frame(self.viewport_container, bg="#000000")

        # Instantiate EmbeddedSessionView directly inside the tab frame
        viewer = EmbeddedSessionView(
            parent=session_frame,
            relay_url=self.relay_url,
            target_id=clean,
            password=password,
            on_close=lambda: self.close_tab(clean)
        )
        viewer.pack(fill="both", expand=True)

        tab_data = {
            "id": clean,
            "title": formatted,
            "type": "session",
            "frame": session_frame,
            "viewer": viewer,
            "btn_frame": None
        }

        self.tabs.append(tab_data)
        self._render_tab_button(tab_data)
        self.switch_tab(clean)

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

    def _open_web(self):
        webbrowser.open(f"http://localhost:{self.port}")

    def _open_settings(self):
        settings_win = tk.Toplevel(self.root)
        settings_win.title("OpenDesk Settings & Network Configuration")
        settings_win.geometry("560x440")
        settings_win.minsize(520, 400)
        settings_win.configure(bg="#141822")
        settings_win.grab_set()

        tk.Label(settings_win, text="⚙️ OpenDesk Settings", font=("Segoe UI", 12, "bold"),
                 bg="#141822", fg="#f1f5f9").pack(anchor="w", padx=20, pady=(16, 6))

        # --- Section 1: Relay WebSocket Configuration ---
        tk.Label(settings_win, text="🌐 Relay WebSocket Server URL:", font=("Segoe UI", 9, "bold"),
                 bg="#141822", fg="#ef4444").pack(anchor="w", padx=20, pady=(6, 2))
        tk.Label(settings_win, text="To connect across a custom VPS or private cloud network, enter the endpoint:",
                 font=("Segoe UI", 8), bg="#141822", fg="#94a3b8").pack(anchor="w", padx=20, pady=(0, 4))

        entry_box = tk.Entry(settings_win, font=("Consolas", 10), bg="#202534", fg="#f1f5f9",
                             insertbackground="#ef4444", bd=1, relief="solid")
        entry_box.pack(fill="x", padx=20, pady=4, ipady=4)
        entry_box.insert(0, self.relay_url)

        # --- Section 2: Software Updates & Maintenance ---
        tk.Label(settings_win, text="🔄 Software Updates & Maintenance:", font=("Segoe UI", 9, "bold"),
                 bg="#141822", fg="#ef4444").pack(anchor="w", padx=20, pady=(14, 2))

        upd_card = tk.Frame(settings_win, bg="#1a1e2b", bd=1, relief="solid", highlightbackground="#282e3f")
        upd_card.pack(fill="x", padx=20, pady=4)

        info_row = tk.Frame(upd_card, bg="#1a1e2b")
        info_row.pack(fill="x", padx=12, pady=(10, 4))
        tk.Label(info_row, text=f"Installed Version: v{APP_VERSION} (Authenticode Signed)", font=("Segoe UI", 9, "bold"),
                 bg="#1a1e2b", fg="#f1f5f9").pack(side="left")

        check_btn = tk.Button(info_row, text="🔄 Check for Updates Now", font=("Segoe UI", 8, "bold"),
                              bg="#202534", fg="#f1f5f9", activebackground="#ef4444", activeforeground="#ffffff",
                              bd=0, padx=10, pady=4, cursor="hand2", command=lambda: self._check_updates_interactive(settings_win))
        check_btn.pack(side="right")

        auto_upd_var = tk.BooleanVar(value=get_auto_update_enabled())
        def on_toggle_auto():
            set_auto_update_enabled(auto_upd_var.get())

        chk = tk.Checkbutton(upd_card, text="Automatically check for updates on startup", variable=auto_upd_var,
                             bg="#1a1e2b", fg="#94a3b8", selectcolor="#141822", activebackground="#1a1e2b",
                             activeforeground="#f1f5f9", font=("Segoe UI", 8), command=on_toggle_auto)
        chk.pack(anchor="w", padx=12, pady=(4, 10))

        def save_and_reconnect():
            new_url = entry_box.get().strip()
            if new_url:
                self.relay_url = new_url
                settings_win.destroy()
                messagebox.showinfo("Saved", f"Relay URL updated to:\n{self.relay_url}\n\nPlease restart OpenDesk to apply.")

        btn_row = tk.Frame(settings_win, bg="#141822")
        btn_row.pack(fill="x", padx=20, pady=16)

        tk.Button(btn_row, text="Save Settings", font=("Segoe UI", 9, "bold"), bg="#ef4444", fg="#ffffff",
                  bd=0, padx=14, pady=6, cursor="hand2", command=save_and_reconnect).pack(side="left")
        tk.Button(btn_row, text="Cancel", font=("Segoe UI", 9), bg="#202534", fg="#f1f5f9",
                  bd=0, padx=14, pady=6, cursor="hand2", command=settings_win.destroy).pack(side="right")

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

    def _on_tunnel_url_ready(self, url: str):
        self.public_url = url
        self.root.after(0, self._update_tunnel_ui)

    def _update_tunnel_ui(self):
        if self.public_url:
            self.internet_link_label.config(text=self.public_url, fg="#9ece6a")
            self.status_badge.config(text="● WORLDWIDE ONLINE", bg="#1f382a", fg="#9ece6a")
            self.bottom_status_label.config(text=f"Global: {self.public_url}")

    def _on_close(self):
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
