"""
OpenDesk Native Desktop Remote Session Viewer
Provides a native AnyDesk-style desktop session window directly inside OpenDesk
without opening an external web browser.
Features:
- Native Canvas rendering of DeskRT video frames (PIL + ImageTk)
- Real-time Win32 mouse coordinate normalization and button injection
- Keyboard event capture and system shortcut actions
- Automatic bidirectional clipboard synchronization
- Integrated real-time voice communication (AudioEngine)
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
from typing import Optional, Dict, Any
from PIL import Image, ImageTk
import aiohttp

from opendesk.common.protocol import MessageType, create_packet, parse_packet
from opendesk.host.audio import AudioEngine
from opendesk.host.clipboard import WindowsClipboard

class NativeSessionViewer:
    def __init__(self, parent: tk.Tk, relay_url: str, target_id: str, password: str = ""):
        self.parent = parent
        self.relay_url = relay_url
        self.target_id = target_id.replace(" ", "").replace("-", "").strip()
        self.password = password

        # Networking & Asyncio State
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self.session: Optional[aiohttp.ClientSession] = None
        self.running = False
        self.in_session = False
        self._send_queue = None

        # Display & Video State
        self.remote_width = 1920
        self.remote_height = 1080
        self.remote_image: Optional[Image.Image] = None
        self.tk_photo: Optional[ImageTk.PhotoImage] = None
        self.is_fullscreen = False
        self.canvas_scale = 1.0
        self.offset_x = 0
        self.offset_y = 0

        # Subsystems
        self.clipboard = WindowsClipboard(on_change_callback=self._on_local_clipboard_changed)
        self.audio_engine = AudioEngine(on_mic_chunk_callback=self._on_mic_chunk)
        self.audio_active = False

        # Stats
        self.frame_count = 0
        self.fps = 0
        self.last_fps_time = time.time()
        self.last_ping_time = 0.0
        self.rtt_ms = 0

        self._build_window()
        self._start_connection()

    def _build_window(self):
        self.win = tk.Toplevel(self.parent)
        self.win.title(f"OpenDesk - Remote Session [{self.target_id}]")
        self.win.geometry("1280x760")
        self.win.minsize(800, 500)
        self.win.configure(bg="#0f1117")
        self.win.protocol("WM_DELETE_WINDOW", self._on_close)

        # --- Top Toolbar ---
        self.toolbar = tk.Frame(self.win, bg="#1a1d27", height=42)
        self.toolbar.pack(fill="x", side="top")

        brand_frame = tk.Frame(self.toolbar, bg="#1a1d27")
        brand_frame.pack(side="left", padx=12, pady=6)
        tk.Label(brand_frame, text="⚡ OpenDesk", font=("Segoe UI", 11, "bold"), bg="#1a1d27", fg="#7aa2f7").pack(side="left")

        # Stats Pills
        self.status_badge = tk.Label(self.toolbar, text="● Connecting...", font=("Segoe UI", 9, "bold"), bg="#24283b", fg="#e0af68", padx=8, pady=3)
        self.status_badge.pack(side="left", padx=8)

        self.fps_label = tk.Label(self.toolbar, text="0 FPS", font=("Segoe UI", 8), bg="#1a1d27", fg="#565f89")
        self.fps_label.pack(side="left", padx=4)

        self.rtt_label = tk.Label(self.toolbar, text="0ms", font=("Segoe UI", 8), bg="#1a1d27", fg="#565f89")
        self.rtt_label.pack(side="left", padx=4)

        # Actions on Right
        actions_frame = tk.Frame(self.toolbar, bg="#1a1d27")
        actions_frame.pack(side="right", padx=12, pady=6)

        self.voice_btn = tk.Button(actions_frame, text="🎙️ Voice: OFF", font=("Segoe UI", 8, "bold"), bg="#24283b", fg="#c0caf5",
                                   activebackground="#2f344d", activeforeground="#7aa2f7", bd=0, padx=8, pady=3, cursor="hand2", command=self._toggle_voice)
        self.voice_btn.pack(side="left", padx=4)

        clip_btn = tk.Button(actions_frame, text="📋 Push Clipboard", font=("Segoe UI", 8), bg="#24283b", fg="#c0caf5",
                             activebackground="#2f344d", activeforeground="#7aa2f7", bd=0, padx=8, pady=3, cursor="hand2", command=self._send_clipboard_to_host)
        clip_btn.pack(side="left", padx=4)

        # Shortcuts Menu Button
        self.keys_btn = tk.Menubutton(actions_frame, text="⌨️ Actions ▾", font=("Segoe UI", 8), bg="#24283b", fg="#c0caf5",
                                      activebackground="#2f344d", activeforeground="#7aa2f7", bd=0, padx=8, pady=3, cursor="hand2")
        self.keys_menu = tk.Menu(self.keys_btn, tearoff=0, bg="#1a1d27", fg="#c0caf5", activebackground="#24283b", activeforeground="#7aa2f7")
        self.keys_menu.add_command(label="Task Manager (Ctrl+Shift+Esc)", command=lambda: self._send_shortcut("ctrl_alt_del"))
        self.keys_menu.add_command(label="Windows Key (Start)", command=lambda: self._send_shortcut("win"))
        self.keys_menu.add_command(label="Switch Window (Alt+Tab)", command=lambda: self._send_shortcut("alt_tab"))
        self.keys_btn.config(menu=self.keys_menu)
        self.keys_btn.pack(side="left", padx=4)

        fs_btn = tk.Button(actions_frame, text="⛶ Fullscreen", font=("Segoe UI", 8), bg="#24283b", fg="#c0caf5",
                           activebackground="#2f344d", activeforeground="#7aa2f7", bd=0, padx=8, pady=3, cursor="hand2", command=self._toggle_fullscreen)
        fs_btn.pack(side="left", padx=4)

        disc_btn = tk.Button(actions_frame, text="Disconnect", font=("Segoe UI", 8, "bold"), bg="#f7768e", fg="#0f1117",
                             activebackground="#db4b4b", activeforeground="#ffffff", bd=0, padx=10, pady=3, cursor="hand2", command=self._on_close)
        disc_btn.pack(side="left", padx=6)

        # --- Viewport Canvas ---
        self.canvas = tk.Canvas(self.win, bg="#000000", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self._bind_events()

    def _bind_events(self):
        # Resize / Scaling
        self.canvas.bind("<Configure>", self._on_canvas_resize)

        # Mouse Events
        self.canvas.bind("<Motion>", self._on_mouse_move)
        self.canvas.bind("<Button-1>", lambda e: self._on_mouse_button(e, 0, True))
        self.canvas.bind("<ButtonRelease-1>", lambda e: self._on_mouse_button(e, 0, False))
        self.canvas.bind("<Button-2>", lambda e: self._on_mouse_button(e, 1, True))
        self.canvas.bind("<ButtonRelease-2>", lambda e: self._on_mouse_button(e, 1, False))
        self.canvas.bind("<Button-3>", lambda e: self._on_mouse_button(e, 2, True))
        self.canvas.bind("<ButtonRelease-3>", lambda e: self._on_mouse_button(e, 2, False))
        self.canvas.bind("<MouseWheel>", self._on_mouse_wheel)

        # Keyboard Events
        self.canvas.bind("<KeyPress>", self._on_key_press)
        self.canvas.bind("<KeyRelease>", self._on_key_release)

        # Focus canvas on click
        self.canvas.bind("<Button-1>", lambda e: self.canvas.focus_set(), add="+")
        self.canvas.focus_set()

    # --- Mouse & Keyboard Event Handlers ---
    def _normalize_coords(self, event_x: int, event_y: int):
        if self.canvas_scale <= 0:
            return None, None
        local_x = event_x - self.offset_x
        local_y = event_y - self.offset_y
        dw = int(self.remote_width * self.canvas_scale)
        dh = int(self.remote_height * self.canvas_scale)

        if 0 <= local_x <= dw and 0 <= local_y <= dh and dw > 0 and dh > 0:
            return local_x / dw, local_y / dh
        return None, None

    def _on_mouse_move(self, event):
        if not self.in_session:
            return
        nx, ny = self._normalize_coords(event.x, event.y)
        if nx is not None and ny is not None:
            self._send_payload(MessageType.INPUT_MOUSE_MOVE, {"x": nx, "y": ny})

    def _on_mouse_button(self, event, button: int, is_down: bool):
        if not self.in_session:
            return
        nx, ny = self._normalize_coords(event.x, event.y)
        mtype = MessageType.INPUT_MOUSE_DOWN if is_down else MessageType.INPUT_MOUSE_UP
        payload = {"button": button}
        if nx is not None and ny is not None:
            payload["x"] = nx
            payload["y"] = ny
        self._send_payload(mtype, payload)

    def _on_mouse_wheel(self, event):
        if not self.in_session:
            return
        # In Windows Tkinter, delta is typically 120 or -120
        delta_y = -1 if event.delta < 0 else 1
        self._send_payload(MessageType.INPUT_MOUSE_SCROLL, {"delta_x": 0, "delta_y": delta_y})

    def _on_key_press(self, event):
        if not self.in_session:
            return
        # Intercept Ctrl+V to sync local clipboard to remote host automatically
        if (event.state & 0x0004) and event.keysym.lower() == 'v':
            self._send_clipboard_to_host(auto_paste=True)
            return

        code = self._map_tk_keysym_to_js(event.keysym)
        self._send_payload(MessageType.INPUT_KEY_DOWN, {"code": code, "key": event.char})

    def _on_key_release(self, event):
        if not self.in_session:
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
            text = self.win.clipboard_get()
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
        self.is_fullscreen = not self.is_fullscreen
        self.win.attributes("-fullscreen", self.is_fullscreen)
        if self.is_fullscreen:
            self.win.bind("<Escape>", lambda e: self._toggle_fullscreen())
        else:
            self.win.unbind("<Escape>")
        self._on_canvas_resize(None)

    def _send_shortcut(self, name: str):
        if self.in_session:
            self._send_payload(MessageType.INPUT_SHORTCUT, {"name": name})

    # --- Video Frame Rendering ---
    def _on_canvas_resize(self, event):
        if self.remote_image:
            self._render_frame()

    def _render_frame(self):
        if not self.remote_image or not self.win.winfo_exists():
            return
        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())
        rw, rh = self.remote_width, self.remote_height

        self.canvas_scale = min(cw / rw, ch / rh)
        dw = max(1, int(rw * self.canvas_scale))
        dh = max(1, int(rh * self.canvas_scale))
        self.offset_x = (cw - dw) // 2
        self.offset_y = (ch - dh) // 2

        # Fast Resample
        resized = self.remote_image.resize((dw, dh), Image.Resampling.BILINEAR)
        self.tk_photo = ImageTk.PhotoImage(resized)

        self.canvas.delete("all")
        self.canvas.create_image(self.offset_x, self.offset_y, anchor="nw", image=self.tk_photo)

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
                async with aiohttp.ClientSession() as session:
                    self.session = session
                    try:
                        async with session.ws_connect(self.relay_url, max_msg_size=16*1024*1024) as ws:
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
                        self.win.after(0, lambda: self._on_connection_error(str(e)))

            self.loop.run_until_complete(main_ws())

        t = threading.Thread(target=run_network, daemon=True)
        t.start()

    def _handle_incoming_packet(self, packet: Dict[str, Any]):
        mtype = packet.get("type")
        payload = packet.get("payload", {})

        if mtype == MessageType.REGISTER_RESP:
            # Successfully registered, request connection to target
            self._send_payload(MessageType.CONNECT, {
                "target_id": self.target_id,
                "password": self.password
            })

        elif mtype == MessageType.CONNECT_RESP:
            status = payload.get("status")
            if status == "ok":
                self.in_session = True
                self.win.after(0, self._on_session_connected)
            else:
                msg = payload.get("message", "Could not connect to host.")
                self.win.after(0, lambda: self._on_connection_error(msg))

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
                self.win.after(0, self._render_frame)

        elif mtype == MessageType.VIDEO_DELTA:
            if self.remote_image:
                tiles = payload.get("tiles", [])
                for t in tiles:
                    raw_bytes = base64.b64decode(t["image"])
                    tile_img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
                    self.remote_image.paste(tile_img, (t["x"], t["y"]))
                self.win.after(0, self._render_frame)

        elif mtype == MessageType.CLIPBOARD_TEXT:
            text = payload.get("text", "")
            if text:
                self.clipboard.set_text(text)

        elif mtype == MessageType.AUDIO_CHUNK:
            data = payload.get("data")
            if data:
                self.audio_engine.play_chunk(data)

        elif mtype == MessageType.SESSION_END:
            self.win.after(0, self._on_remote_disconnected)

    def _on_session_connected(self):
        self.status_badge.config(text=f"● Connected [{self.target_id}]", bg="#1f382a", fg="#9ece6a")
        # Automatically pre-start speaker so incoming host audio plays cleanly
        self.audio_engine.start()

    def _on_connection_error(self, err_msg: str):
        messagebox.showerror("Connection Error", f"Unable to establish session with [{self.target_id}]:\n\n{err_msg}")
        self._on_close()

    def _on_remote_disconnected(self):
        messagebox.showinfo("Session Closed", "Remote host closed the session.")
        self._on_close()

    def _on_close(self):
        self.running = False
        self.in_session = False
        try:
            self.audio_engine.stop()
        except Exception:
            pass
        try:
            if self.win.winfo_exists():
                self.win.destroy()
        except Exception:
            pass
        self.parent.deiconify()
        self.parent.focus_set()
