"""
OpenDesk Native Desktop Remote Session Viewer
Provides a native AnyDesk-style desktop session window and embedded tab viewport
directly inside OpenDesk without opening an external web browser.
Features:
- Native Canvas rendering of DeskRT video frames (PIL + ImageTk)
- Real-time Win32 mouse coordinate normalization and button injection
- Keyboard event capture and system shortcut actions
- Automatic bidirectional clipboard synchronization
- Integrated real-time voice communication (AudioEngine)
- In-tab embedded session mode or standalone window mode
- Fullscreen mode and session management
"""

import os
import sys
import io
import time
import json
import base64
import asyncio
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Dict, Any, Callable
from PIL import Image, ImageTk
import aiohttp

try:
    from opendesk.common.protocol import MessageType, create_packet, parse_packet
    from opendesk.common.rendezvous import resolve_host_rendezvous, parse_connect_target
    from opendesk.host.audio import AudioEngine
    from opendesk.host.clipboard import WindowsClipboard
except ImportError:
    from common.protocol import MessageType, create_packet, parse_packet
    from common.rendezvous import resolve_host_rendezvous, parse_connect_target
    from host.audio import AudioEngine
    from host.clipboard import WindowsClipboard


class EmbeddedSessionView(tk.Frame):
    """
    Embedded remote desktop viewport frame that renders directly inside
    an AnyDesk-style tab container in the main OpenDesk application window.
    """
    def __init__(self, parent: tk.Widget, relay_url: str, target_id: str,
                 password: str = "", on_close: Optional[Callable[[], None]] = None):
        super().__init__(parent, bg="#000000")
        self.parent = parent
        self.relay_url = relay_url
        self.target_id = target_id.replace(" ", "").replace("-", "").strip()
        self.password = password
        self.on_close_cb = on_close

        # Networking & Asyncio State
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self.session: Optional[aiohttp.ClientSession] = None
        self.running = False
        self.in_session = False
        self._send_queue = None
        self.granted_permissions = {"input": True, "audio": True, "clipboard": True, "file_transfer": True}

        # Display & Video State
        self.remote_width = 1920
        self.remote_height = 1080
        self.remote_image: Optional[Image.Image] = None
        self.tk_photo: Optional[ImageTk.PhotoImage] = None
        self.is_fullscreen = False
        self.canvas_scale = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self._render_pending = False

        # Display Modes & Zoom / Pan State
        self.view_mode = "fit"       # "fit" (Aspect Ratio), "stretch" (Fill Screen), "original" (1:1 Native)
        self.zoom_level = 1.0        # 0.5x to 3.0x
        self.pan_x = 0               # Interactive pan X offset
        self.pan_y = 0               # Interactive pan Y offset
        self.display_width = 1       # Rendered pixel width
        self.display_height = 1      # Rendered pixel height
        self._is_panning = False
        self._pan_start_x = 0
        self._pan_start_y = 0
        self._pan_orig_x = 0
        self._pan_orig_y = 0

        # Subsystems
        self.clipboard = WindowsClipboard(on_change_callback=self._on_local_clipboard_changed)
        self.audio_engine = AudioEngine(on_mic_chunk_callback=self._on_mic_chunk)
        self.audio_active = False

        # Stats
        self.frame_count = 0
        self.fps = 0
        self.last_fps_time = time.time()
        self.rtt_ms = 0

        self._build_ui()
        self._start_connection()

    def _build_ui(self):
        # --- Top Session Toolbar ---
        self.toolbar = tk.Frame(self, bg="#161922", height=40)
        self.toolbar.pack(fill="x", side="top")

        brand_frame = tk.Frame(self.toolbar, bg="#161922")
        brand_frame.pack(side="left", padx=12, pady=5)
        tk.Label(brand_frame, text="⚡ DeskRT", font=("Segoe UI", 10, "bold"), bg="#161922", fg="#ef4444").pack(side="left")

        # Status & Performance Badges
        self.status_badge = tk.Label(self.toolbar, text=f"● Connecting [{self.target_id}]...",
                                     font=("Segoe UI", 9, "bold"), bg="#252a38", fg="#e0af68", padx=8, pady=3)
        self.status_badge.pack(side="left", padx=6)

        self.fps_label = tk.Label(self.toolbar, text="0 FPS", font=("Segoe UI", 8), bg="#161922", fg="#94a3b8")
        self.fps_label.pack(side="left", padx=4)

        self.rtt_label = tk.Label(self.toolbar, text="<10ms", font=("Segoe UI", 8), bg="#161922", fg="#94a3b8")
        self.rtt_label.pack(side="left", padx=4)

        # Actions on Right
        actions_frame = tk.Frame(self.toolbar, bg="#161922")
        actions_frame.pack(side="right", padx=10, pady=5)

        self.voice_btn = tk.Button(actions_frame, text="🎙️ Voice: OFF", font=("Segoe UI", 8, "bold"),
                                   bg="#24283b", fg="#c0caf5", activebackground="#2f344d", activeforeground="#7aa2f7",
                                   bd=0, padx=8, pady=3, cursor="hand2", command=self._toggle_voice)
        self.voice_btn.pack(side="left", padx=3)

        clip_btn = tk.Button(actions_frame, text="📋 Push Clipboard", font=("Segoe UI", 8),
                             bg="#24283b", fg="#c0caf5", activebackground="#2f344d", activeforeground="#7aa2f7",
                             bd=0, padx=8, pady=3, cursor="hand2", command=self._send_clipboard_to_host)
        clip_btn.pack(side="left", padx=3)

        # Shortcuts Menu Button
        self.keys_btn = tk.Menubutton(actions_frame, text="⌨️ Actions ▾", font=("Segoe UI", 8),
                                      bg="#24283b", fg="#c0caf5", activebackground="#2f344d", activeforeground="#7aa2f7",
                                      bd=0, padx=8, pady=3, cursor="hand2")
        self.keys_menu = tk.Menu(self.keys_btn, tearoff=0, bg="#1a1d27", fg="#c0caf5",
                                 activebackground="#24283b", activeforeground="#ef4444")
        self.keys_menu.add_command(label="Task Manager (Ctrl+Shift+Esc)", command=lambda: self._send_shortcut("ctrl_alt_del"))
        self.keys_menu.add_command(label="Windows Key (Start)", command=lambda: self._send_shortcut("win"))
        self.keys_menu.add_command(label="Switch Window (Alt+Tab)", command=lambda: self._send_shortcut("alt_tab"))
        self.keys_btn.config(menu=self.keys_menu)
        self.keys_btn.pack(side="left", padx=3)

        # Display Mode Menu Button (Fit / Stretch / 1:1)
        self.mode_btn = tk.Menubutton(actions_frame, text="📐 Fit ▾", font=("Segoe UI", 8, "bold"),
                                      bg="#24283b", fg="#c0caf5", activebackground="#2f344d", activeforeground="#7aa2f7",
                                      bd=0, padx=8, pady=3, cursor="hand2")
        self.mode_menu = tk.Menu(self.mode_btn, tearoff=0, bg="#1a1d27", fg="#c0caf5",
                                 activebackground="#24283b", activeforeground="#ef4444")
        self.mode_menu.add_command(label="✓ Fit Screen (Aspect Ratio)", command=lambda: self.set_view_mode("fit"))
        self.mode_menu.add_command(label="   Stretch to Fill (No Black Bars)", command=lambda: self.set_view_mode("stretch"))
        self.mode_menu.add_command(label="   1:1 Original Size (Pixel-to-Pixel)", command=lambda: self.set_view_mode("original"))
        self.mode_btn.config(menu=self.mode_menu)
        self.mode_btn.pack(side="left", padx=3)

        # Zoom Controls (- / 100% / +)
        self.zoom_out_btn = tk.Button(actions_frame, text="🔍 -", font=("Segoe UI", 8, "bold"),
                                      bg="#24283b", fg="#c0caf5", activebackground="#2f344d", activeforeground="#7aa2f7",
                                      bd=0, padx=6, pady=3, cursor="hand2", command=self.zoom_out)
        self.zoom_out_btn.pack(side="left", padx=(3, 1))

        self.zoom_val_btn = tk.Button(actions_frame, text="100%", font=("Segoe UI", 8, "bold"),
                                      bg="#1e2230", fg="#38bdf8", activebackground="#252a3a", activeforeground="#7dd3fc",
                                      bd=0, padx=7, pady=3, cursor="hand2", command=self.reset_zoom)
        self.zoom_val_btn.pack(side="left", padx=1)

        self.zoom_in_btn = tk.Button(actions_frame, text="🔍 +", font=("Segoe UI", 8, "bold"),
                                     bg="#24283b", fg="#c0caf5", activebackground="#2f344d", activeforeground="#7aa2f7",
                                     bd=0, padx=6, pady=3, cursor="hand2", command=self.zoom_in)
        self.zoom_in_btn.pack(side="left", padx=(1, 3))

        fs_btn = tk.Button(actions_frame, text="⛶ Fullscreen", font=("Segoe UI", 8),
                           bg="#24283b", fg="#c0caf5", activebackground="#2f344d", activeforeground="#7aa2f7",
                           bd=0, padx=8, pady=3, cursor="hand2", command=self._toggle_fullscreen)
        fs_btn.pack(side="left", padx=3)

        disc_btn = tk.Button(actions_frame, text="Disconnect", font=("Segoe UI", 8, "bold"),
                             bg="#ef4444", fg="#ffffff", activebackground="#dc2626", activeforeground="#ffffff",
                             bd=0, padx=10, pady=3, cursor="hand2", command=self.close)
        disc_btn.pack(side="left", padx=6)

        # --- Viewport Canvas ---
        self.canvas = tk.Canvas(self, bg="#000000", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self._bind_events()

    def _bind_events(self):
        # Resize / Scaling
        self.canvas.bind("<Configure>", self._on_canvas_resize)

        # Mouse Movement & Primary Button
        self.canvas.bind("<Motion>", self._on_mouse_move)
        self.canvas.bind("<Button-1>", self._on_button_1_down)
        self.canvas.bind("<B1-Motion>", self._on_b1_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_button_1_up)

        # Middle Mouse Button (Quick Click = Inject Middle Click; Drag = Pan Viewport)
        self.canvas.bind("<Button-2>", self._on_pan_start)
        self.canvas.bind("<B2-Motion>", self._on_pan_motion)
        self.canvas.bind("<ButtonRelease-2>", self._on_pan_end)

        # Right Mouse Button
        self.canvas.bind("<Button-3>", lambda e: self._on_mouse_button(e, 2, True))
        self.canvas.bind("<ButtonRelease-3>", lambda e: self._on_mouse_button(e, 2, False))

        # Mouse Wheel: Ctrl+Wheel zooms viewport; Standard Wheel scrolls remote host
        self.canvas.bind("<MouseWheel>", self._on_mouse_wheel)

        # Keyboard Events
        self.canvas.bind("<KeyPress>", self._on_key_press)
        self.canvas.bind("<KeyRelease>", self._on_key_release)

        # Focus canvas on click
        self.canvas.bind("<Button-1>", lambda e: self.canvas.focus_set(), add="+")
        self.canvas.focus_set()

    # --- Display Modes, Zoom & Pan Controls ---
    def set_view_mode(self, mode: str):
        """
        Switch display aspect ratio mode:
        - "fit": Automatically fits remote screen preserving aspect ratio (letterbox/pillarbox).
        - "stretch": Stretches remote screen to fill entire canvas (eliminates black bars).
        - "original": Renders at 1:1 native pixel resolution (zero scaling blur).
        """
        if mode not in ("fit", "stretch", "original"):
            return
        self.view_mode = mode

        # Update button text & menu checkmarks
        mode_titles = {
            "fit": "📐 Fit ▾",
            "stretch": "↔ Stretch ▾",
            "original": "1:1 Orig ▾"
        }
        if hasattr(self, "mode_btn") and self.mode_btn.winfo_exists():
            self.mode_btn.config(text=mode_titles.get(mode, "📐 Fit ▾"))

        if hasattr(self, "mode_menu"):
            self.mode_menu.delete(0, "end")
            self.mode_menu.add_command(
                label="✓ Fit Screen (Aspect Ratio)" if mode == "fit" else "   Fit Screen (Aspect Ratio)",
                command=lambda: self.set_view_mode("fit")
            )
            self.mode_menu.add_command(
                label="✓ Stretch to Fill (No Black Bars)" if mode == "stretch" else "   Stretch to Fill (No Black Bars)",
                command=lambda: self.set_view_mode("stretch")
            )
            self.mode_menu.add_command(
                label="✓ 1:1 Original Size (Pixel-to-Pixel)" if mode == "original" else "   1:1 Original Size (Pixel-to-Pixel)",
                command=lambda: self.set_view_mode("original")
            )

        self._clamp_pan()
        self._trigger_render()

    def zoom_in(self, factor: float = 0.25):
        """Increase zoom level by factor."""
        self.set_zoom(self.zoom_level + factor)

    def zoom_out(self, factor: float = 0.25):
        """Decrease zoom level by factor."""
        self.set_zoom(self.zoom_level - factor)

    def reset_zoom(self):
        """Reset zoom to 100% (1.0) and reset pan offsets to (0, 0)."""
        self.zoom_level = 1.0
        self.pan_x = 0
        self.pan_y = 0
        if hasattr(self, "zoom_val_btn") and self.zoom_val_btn.winfo_exists():
            self.zoom_val_btn.config(text="100%")
        self._trigger_render()

    def set_zoom(self, new_zoom: float, center_x: Optional[int] = None, center_y: Optional[int] = None):
        """
        Set zoom level clamped to [0.5, 3.0].
        If center_x and center_y are given, zoom is anchored around that canvas coordinate.
        """
        clamped_zoom = max(0.5, min(3.0, round(new_zoom, 2)))
        if abs(clamped_zoom - self.zoom_level) < 0.001:
            return

        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())
        cx = center_x if center_x is not None else cw // 2
        cy = center_y if center_y is not None else ch // 2

        # Anchor normalized coordinate under (cx, cy) before zoom
        if self.display_width > 0 and self.display_height > 0:
            frame_left = self.offset_x + self.pan_x
            frame_top = self.offset_y + self.pan_y
            norm_anchor_x = (cx - frame_left) / float(self.display_width)
            norm_anchor_y = (cy - frame_top) / float(self.display_height)
        else:
            norm_anchor_x = 0.5
            norm_anchor_y = 0.5

        self.zoom_level = clamped_zoom

        # Update button text
        pct = int(round(self.zoom_level * 100))
        if hasattr(self, "zoom_val_btn") and self.zoom_val_btn.winfo_exists():
            self.zoom_val_btn.config(text=f"{pct}%")

        if self.zoom_level == 1.0 and center_x is None:
            self.pan_x = 0
            self.pan_y = 0
        else:
            rw, rh = max(1, self.remote_width), max(1, self.remote_height)
            if self.view_mode == "stretch":
                new_dw = max(1, int(cw * self.zoom_level))
                new_dh = max(1, int(ch * self.zoom_level))
            elif self.view_mode == "original":
                new_dw = max(1, int(rw * self.zoom_level))
                new_dh = max(1, int(rh * self.zoom_level))
            else:
                base_scale = min(cw / rw, ch / rh)
                new_dw = max(1, int(rw * base_scale * self.zoom_level))
                new_dh = max(1, int(rh * base_scale * self.zoom_level))

            new_offset_x = (cw - new_dw) // 2
            new_offset_y = (ch - new_dh) // 2

            self.pan_x = int(cx - new_offset_x - norm_anchor_x * new_dw)
            self.pan_y = int(cy - new_offset_y - norm_anchor_y * new_dh)

        self._clamp_pan()
        self._trigger_render()

    def _clamp_pan(self):
        """Keep remote display visible and prevent panning excessively out of bounds."""
        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())
        dw = self.display_width
        dh = self.display_height

        if dw > cw:
            max_pan_x = (dw - cw) // 2 + 60
            min_pan_x = -(dw - cw) // 2 - 60
            self.pan_x = max(min_pan_x, min(max_pan_x, self.pan_x))
        else:
            self.pan_x = 0

        if dh > ch:
            max_pan_y = (dh - ch) // 2 + 60
            min_pan_y = -(dh - ch) // 2 - 60
            self.pan_y = max(min_pan_y, min(max_pan_y, self.pan_y))
        else:
            self.pan_y = 0

    # --- Mouse & Keyboard Event Handlers ---
    def _normalize_coords(self, event_x: int, event_y: int):
        """
        Transforms client canvas pixel coordinates back to host normalized coordinates (0.0 to 1.0).
        Guarantees 100% mathematical precision across all display modes (Fit, Stretch, 1:1),
        arbitrary zoom levels (50% to 300%), and pan offsets.
        
        100% Backward Compatible:
        Older hosts (v1.0.0, v1.1.0, v1.1.2, v1.1.5) always receive standard normalized coordinates
        [0.0, 1.0], meaning clicks hit the exact correct pixel on the remote desktop without
        requiring any protocol updates on the host.
        """
        if self.display_width <= 0 or self.display_height <= 0:
            return None, None

        frame_left = self.offset_x + self.pan_x
        frame_top = self.offset_y + self.pan_y

        local_x = event_x - frame_left
        local_y = event_y - frame_top

        if 0 <= local_x <= self.display_width and 0 <= local_y <= self.display_height:
            nx = local_x / float(self.display_width)
            ny = local_y / float(self.display_height)
            return max(0.0, min(1.0, nx)), max(0.0, min(1.0, ny))
        return None, None

    def _on_button_1_down(self, event):
        # If Shift is pressed, start panning!
        if event.state & 0x0001:
            self._on_pan_start(event)
            return
        self._on_mouse_button(event, 0, True)

    def _on_b1_motion(self, event):
        if self._is_panning:
            self._on_pan_motion(event)
        else:
            self._on_mouse_move(event)

    def _on_button_1_up(self, event):
        if self._is_panning:
            self._on_pan_end(event)
            return
        self._on_mouse_button(event, 0, False)

    def _on_pan_start(self, event):
        self._is_panning = True
        self._pan_start_x = event.x
        self._pan_start_y = event.y
        self._pan_orig_x = self.pan_x
        self._pan_orig_y = self.pan_y
        self.canvas.config(cursor="fleur")

    def _on_pan_motion(self, event):
        if not self._is_panning:
            return
        dx = event.x - self._pan_start_x
        dy = event.y - self._pan_start_y
        self.pan_x = self._pan_orig_x + dx
        self.pan_y = self._pan_orig_y + dy
        self._clamp_pan()
        self._trigger_render()

    def _on_pan_end(self, event):
        if self._is_panning:
            dx = abs(event.x - self._pan_start_x)
            dy = abs(event.y - self._pan_start_y)
            # If quick click without significant drag, send middle-click to remote host
            if dx < 4 and dy < 4 and not (event.state & 0x0001):
                self._on_mouse_button(event, 1, True)
                self._on_mouse_button(event, 1, False)
        self._is_panning = False
        self.canvas.config(cursor="")

    def _on_mouse_move(self, event):
        if not self.in_session or not self.granted_permissions.get("input", True):
            return
        nx, ny = self._normalize_coords(event.x, event.y)
        if nx is not None and ny is not None:
            self._send_payload(MessageType.INPUT_MOUSE_MOVE, {"x": nx, "y": ny})

    def _on_mouse_button(self, event, button: int, is_down: bool):
        if not self.in_session or not self.granted_permissions.get("input", True):
            return
        nx, ny = self._normalize_coords(event.x, event.y)
        mtype = MessageType.INPUT_MOUSE_DOWN if is_down else MessageType.INPUT_MOUSE_UP
        payload = {"button": button}
        if nx is not None and ny is not None:
            payload["x"] = nx
            payload["y"] = ny
        self._send_payload(mtype, payload)

    def _on_mouse_wheel(self, event):
        # If Ctrl key is pressed, zoom in / out anchored at mouse position!
        if event.state & 0x0004:
            if event.delta > 0:
                self.set_zoom(self.zoom_level + 0.15, center_x=event.x, center_y=event.y)
            else:
                self.set_zoom(self.zoom_level - 0.15, center_x=event.x, center_y=event.y)
            return

        if not self.in_session or not self.granted_permissions.get("input", True):
            return
        delta_y = -1 if event.delta < 0 else 1
        self._send_payload(MessageType.INPUT_MOUSE_SCROLL, {"delta_x": 0, "delta_y": delta_y})

    def _on_key_press(self, event):
        if not self.in_session or not self.granted_permissions.get("input", True):
            return
        # Intercept Ctrl+V to sync local clipboard to remote host automatically
        if (event.state & 0x0004) and event.keysym.lower() == 'v':
            self._send_clipboard_to_host(auto_paste=True)
            return

        code = self._map_tk_keysym_to_js(event.keysym)
        self._send_payload(MessageType.INPUT_KEY_DOWN, {"code": code, "key": event.char})

    def _on_key_release(self, event):
        if not self.in_session or not self.granted_permissions.get("input", True):
            return
        code = self._map_tk_keysym_to_js(event.keysym)
        self._send_payload(MessageType.INPUT_KEY_UP, {"code": code, "key": event.char})

    def _map_tk_keysym_to_js(self, keysym: str) -> str:
        mapping = {
            "BackSpace": "Backspace", "Tab": "Tab", "Return": "Enter",
            "Shift_L": "ShiftLeft", "Shift_R": "ShiftRight",
            "Control_L": "ControlLeft", "Control_R": "ControlRight",
            "Alt_L": "AltLeft", "Alt_R": "AltRight",
            "Caps_Lock": "CapsLock", "Escape": "Escape", "space": "Space",
            "Prior": "PageUp", "Next": "PageDown", "End": "End", "Home": "Home",
            "Left": "ArrowLeft", "Up": "ArrowUp", "Right": "ArrowRight", "Down": "ArrowDown",
            "Delete": "Delete", "Win_L": "MetaLeft", "Win_R": "MetaRight"
        }
        if keysym in mapping:
            return mapping[keysym]
        if len(keysym) == 1 and keysym.isalnum():
            if keysym.isalpha():
                return f"Key{keysym.upper()}"
            if keysym.isdigit():
                return f"Digit{keysym}"
        return keysym

    # --- Clipboard Synchronization ---
    def _send_clipboard_to_host(self, auto_paste: bool = False):
        try:
            text = self.clipboard_get()
            if text:
                self._send_payload(MessageType.CLIPBOARD_TEXT, {"text": text, "auto_paste": auto_paste})
        except Exception:
            pass

    def _on_local_clipboard_changed(self, text: str):
        if self.in_session and text:
            self._send_payload(MessageType.CLIPBOARD_TEXT, {"text": text, "auto_paste": False})

    # --- Audio / Voice Communication ---
    def _on_mic_chunk(self, b64_chunk: str):
        if self.in_session and self.audio_active:
            self._send_payload(MessageType.AUDIO_CHUNK, {"data": b64_chunk})

    def _toggle_voice(self):
        if not self.in_session:
            return
        self.audio_active = not self.audio_active
        if self.audio_active:
            self.audio_engine.mic_enabled = True
            self.audio_engine.start()
            self.voice_btn.config(text="🎙️ Voice: ON", bg="#1f382a", fg="#9ece6a")
        else:
            self.audio_engine.mic_enabled = False
            self.voice_btn.config(text="🎙️ Voice: OFF", bg="#24283b", fg="#c0caf5")

    def _toggle_fullscreen(self):
        top = self.winfo_toplevel()
        self.is_fullscreen = not self.is_fullscreen
        top.attributes("-fullscreen", self.is_fullscreen)
        if self.is_fullscreen:
            top.bind("<Escape>", lambda e: self._toggle_fullscreen())
        else:
            top.unbind("<Escape>")
        self._on_canvas_resize(None)

    def _send_shortcut(self, name: str):
        if self.in_session:
            self._send_payload(MessageType.INPUT_SHORTCUT, {"name": name})

    # --- Video Frame Rendering ---
    def _on_canvas_resize(self, event):
        if self.remote_image:
            self._trigger_render()

    def _trigger_render(self):
        """Debounce canvas redraws to prevent Tkinter event queue starvation and 'Not Responding' freezes."""
        if self._render_pending or not self.winfo_exists():
            return
        self._render_pending = True
        try:
            self._render_after_id = self.after_idle(self._safe_render_frame)
        except Exception:
            self._render_pending = False

    def _safe_render_frame(self):
        self._render_pending = False
        try:
            if self.winfo_exists():
                self._render_frame()
        except Exception:
            pass

    def _render_frame(self):
        self._render_pending = False
        if not self.remote_image or not self.winfo_exists():
            return
        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())
        rw = max(1, self.remote_width)
        rh = max(1, self.remote_height)

        if self.view_mode == "stretch":
            # Stretch to fill canvas completely (eliminates black bars)
            dw = max(1, int(cw * self.zoom_level))
            dh = max(1, int(ch * self.zoom_level))
            self.offset_x = (cw - dw) // 2
            self.offset_y = (ch - dh) // 2
            self.canvas_scale = dw / float(rw)
        elif self.view_mode == "original":
            # 1:1 Native Resolution (Pixel-for-pixel match)
            dw = max(1, int(rw * self.zoom_level))
            dh = max(1, int(rh * self.zoom_level))
            self.offset_x = (cw - dw) // 2
            self.offset_y = (ch - dh) // 2
            self.canvas_scale = self.zoom_level
        else:  # "fit" (Default - Auto-Adapt Aspect Ratio)
            base_scale = min(cw / float(rw), ch / float(rh))
            self.canvas_scale = base_scale * self.zoom_level
            dw = max(1, int(rw * self.canvas_scale))
            dh = max(1, int(rh * self.canvas_scale))
            self.offset_x = (cw - dw) // 2
            self.offset_y = (ch - dh) // 2

        self.display_width = dw
        self.display_height = dh
        self._clamp_pan()

        final_x = self.offset_x + self.pan_x
        final_y = self.offset_y + self.pan_y

        # Fast Resample with PIL
        resized = self.remote_image.resize((dw, dh), Image.Resampling.BILINEAR)
        self.tk_photo = ImageTk.PhotoImage(resized)

        self.canvas.delete("all")
        self.canvas.create_image(final_x, final_y, anchor="nw", image=self.tk_photo)

        # Update FPS
        self.frame_count += 1
        now = time.time()
        if now - self.last_fps_time >= 1.0:
            self.fps = self.frame_count
            self.frame_count = 0
            self.last_fps_time = now
            self.fps_label.config(text=f"{self.fps} FPS")

    # --- Network WebSocket Engine ---
    def _send_payload(self, msg_type: str, payload: Dict[str, Any]):
        if self.loop and self._send_queue:
            pkt = create_packet(msg_type, payload)
            self.loop.call_soon_threadsafe(self._send_queue.put_nowait, pkt)

    def _start_connection(self):
        self.running = True

        def run_network():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self._send_queue = asyncio.Queue()

            async def send_worker():
                while self.running:
                    pkt = await self._send_queue.get()
                    if self.ws and not self.ws.closed:
                        await self.ws.send_str(pkt)

            async def main_ws():
                # 0. Automatically resolve remote host ID if relay is set to auto or not explicitly provided
                effective_relay = self.relay_url
                if not effective_relay or effective_relay == "auto":
                    if self.winfo_exists():
                        self.after(0, lambda: self.status_badge.config(
                            text=f"● Resolving [{self.target_id}]...", bg="#252a38", fg="#e0af68"
                        ))
                    resolved_url = None
                    try:
                        resolved_url = resolve_host_rendezvous(self.target_id)
                    except Exception as e:
                        print(f"[Viewer] Rendezvous resolution notice: {e}")

                    if resolved_url:
                        clean_host = resolved_url.replace("https://", "").replace("http://", "").rstrip("/")
                        scheme = "ws" if "127.0.0.1" in clean_host or "localhost" in clean_host else "wss"
                        effective_relay = f"{scheme}://{clean_host}/ws"
                    else:
                        if self.winfo_exists():
                            self.after(0, lambda: self._on_connection_error(
                                f"Host [{self.target_id}] is offline or ID not found in global registry.\n\n"
                                f"Ensure the remote OpenDesk app is running on the host machine and connected to the internet."
                            ))
                        return

                if self.winfo_exists():
                    self.after(0, lambda: self.status_badge.config(
                        text=f"● Connecting [{self.target_id}]...", bg="#252a38", fg="#e0af68"
                    ))

                async with aiohttp.ClientSession() as session:
                    self.session = session
                    try:
                        async with session.ws_connect(effective_relay, max_msg_size=16*1024*1024) as ws:
                            self.ws = ws
                            # 1. Register as client
                            await ws.send_str(create_packet(MessageType.REGISTER, {"role": "client"}))

                            # 2. Start sender loop
                            asyncio.create_task(send_worker())

                            async for msg in ws:
                                if msg.type == aiohttp.WSMsgType.TEXT:
                                    pkt = parse_packet(msg.data)
                                    if pkt:
                                        self._handle_incoming_packet(pkt)
                                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                    break
                    except Exception as e:
                        print(f"[Viewer] Connection error: {e}")
                        if self.winfo_exists():
                            self.after(0, lambda: self._on_connection_error(str(e)))

            self.loop.run_until_complete(main_ws())

        t = threading.Thread(target=run_network, daemon=True)
        t.start()

    def _handle_incoming_packet(self, packet: Dict[str, Any]):
        mtype = packet.get("type")
        payload = packet.get("payload", {})

        if mtype == MessageType.REGISTER_RESP:
            self._send_payload(MessageType.CONNECT, {
                "target_id": self.target_id,
                "password": self.password
            })

        elif mtype == MessageType.CONNECT_RESP:
            status = payload.get("status")
            if status == "ok":
                self.in_session = True
                self.granted_permissions = payload.get("permissions", {}) or {"input": True, "audio": True, "clipboard": True, "file_transfer": True}
                if self.winfo_exists():
                    self.after(0, self._on_session_connected)
            elif status == "waiting_approval":
                if self.winfo_exists():
                    self.after(0, lambda: self.status_badge.config(
                        text=f"● Waiting for [{self.target_id}] to accept...",
                        bg="#252a38", fg="#38bdf8"
                    ))
            elif status == "rejected":
                msg = payload.get("message", "Connection request was declined by the remote user.")
                if self.winfo_exists():
                    self.after(0, lambda: self._on_connection_error(f"Connection Declined:\n\n{msg}"))
            else:
                msg = payload.get("message", "Could not connect to host.")
                if self.winfo_exists():
                    self.after(0, lambda: self._on_connection_error(msg))

        elif mtype == MessageType.VIDEO_FULL:
            w = payload.get("width", 1920)
            h = payload.get("height", 1080)
            b64_img = payload.get("image", "")
            if b64_img:
                raw_bytes = base64.b64decode(b64_img)
                img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
                self.remote_width = w
                self.remote_height = h
                self.remote_image = img
                if self.winfo_exists():
                    self.after(0, self._trigger_render)

        elif mtype == MessageType.VIDEO_DELTA:
            if self.remote_image:
                tiles = payload.get("tiles", [])
                for t in tiles:
                    raw_bytes = base64.b64decode(t["image"])
                    tile_img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
                    self.remote_image.paste(tile_img, (t["x"], t["y"]))
                if self.winfo_exists():
                    self.after(0, self._trigger_render)

        elif mtype == MessageType.CLIPBOARD_TEXT:
            text = payload.get("text", "")
            if text:
                self.clipboard.set_text(text)

        elif mtype == MessageType.AUDIO_CHUNK:
            data = payload.get("data")
            if data:
                self.audio_engine.play_chunk(data)

        elif mtype == MessageType.SESSION_END:
            if self.winfo_exists():
                self.after(0, self._on_remote_disconnected)

    def _on_session_connected(self):
        perms = getattr(self, "granted_permissions", {})
        if perms and not perms.get("input", True):
            self.status_badge.config(text=f"● Connected [{self.target_id}] (View Only)", bg="#1f382a", fg="#9ece6a")
        else:
            self.status_badge.config(text=f"● Connected [{self.target_id}]", bg="#1f382a", fg="#9ece6a")
        if perms.get("audio", True):
            self.audio_engine.start()

    def _on_connection_error(self, err_msg: str):
        messagebox.showerror("Connection Error", f"Unable to establish session with [{self.target_id}]:\n\n{err_msg}")
        self.close()

    def _on_remote_disconnected(self):
        messagebox.showinfo("Session Closed", f"Remote session [{self.target_id}] was disconnected.")
        self.close()

    def close(self):
        """Cleanly terminate the session, audio, network, and trigger close callback."""
        self.running = False
        self.in_session = False
        if hasattr(self, "_render_after_id") and self._render_after_id:
            try:
                self.after_cancel(self._render_after_id)
            except Exception:
                pass
        try:
            self.audio_engine.stop()
        except Exception:
            pass
        if self.on_close_cb:
            try:
                self.on_close_cb()
            except Exception:
                pass


class NativeSessionViewer:
    """
    Standalone Toplevel wrapper for EmbeddedSessionView, maintaining
    100% backward compatibility for standalone window invocations.
    """
    def __init__(self, parent: tk.Tk, relay_url: str, target_id: str, password: str = ""):
        self.parent = parent
        self.target_id = target_id.replace(" ", "").replace("-", "").strip()
        self.relay_url = relay_url
        self.password = password

        self.win = tk.Toplevel(self.parent)
        self.win.title(f"OpenDesk - Remote Session [{self.target_id}]")
        self.win.geometry("1280x760")
        self.win.minsize(800, 500)
        self.win.configure(bg="#000000")
        self.win.protocol("WM_DELETE_WINDOW", self._on_close)

        self.view = EmbeddedSessionView(
            parent=self.win,
            relay_url=self.relay_url,
            target_id=self.target_id,
            password=self.password,
            on_close=self._on_close
        )
        self.view.pack(fill="both", expand=True)

    def _map_tk_keysym_to_js(self, keysym: str) -> str:
        return self.view._map_tk_keysym_to_js(keysym)

    def set_view_mode(self, mode: str):
        """Set display aspect ratio mode ("fit", "stretch", "original")."""
        self.view.set_view_mode(mode)

    def zoom_in(self, factor: float = 0.25):
        """Zoom in."""
        self.view.zoom_in(factor)

    def zoom_out(self, factor: float = 0.25):
        """Zoom out."""
        self.view.zoom_out(factor)

    def reset_zoom(self):
        """Reset zoom to 100% and center."""
        self.view.reset_zoom()

    def set_zoom(self, zoom: float):
        """Set explicit zoom level."""
        self.view.set_zoom(zoom)

    def _on_close(self):
        try:
            self.view.close()
        except Exception:
            pass
        try:
            if self.win.winfo_exists():
                self.win.destroy()
        except Exception:
            pass
        if self.parent and self.parent.winfo_exists():
            self.parent.deiconify()
            self.parent.focus_set()
