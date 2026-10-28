"""
OpenDesk Host Agent
Runs on the machine being controlled.
- Captures screen frames via Win32 DIBSection
- Encodes frames via DeskRT Tile & Delta Codec
- Injects remote mouse & keyboard inputs
- Manages bidirectional clipboard sync
- Handles remote file browsing and chunked transfers
- Connects to OpenDesk Relay Server
"""

import sys
import time
import json
import base64
import asyncio
import threading
from typing import Optional, Dict, Any
import aiohttp

from opendesk.common.protocol import MessageType, create_packet, parse_packet
from opendesk.common.codec import DeskRTCodec
from opendesk.host.capture import WindowsScreenCapturer
from opendesk.host.input_controller import WindowsInputController
from opendesk.host.clipboard import WindowsClipboard
from opendesk.host.file_manager import FileManager
from opendesk.host.audio import AudioEngine

class HostAgent:
    def __init__(self, relay_url: str = "ws://localhost:8080/ws", host_id: Optional[str] = None, password: str = ""):
        self.relay_url = relay_url
        self.requested_id = host_id
        self.password = password
        self.assigned_id: Optional[str] = None
        
        # Subsystems
        self.capturer = WindowsScreenCapturer()
        self.codec = DeskRTCodec(tile_size=128, quality=70)
        self.input_controller = WindowsInputController()
        self.clipboard = WindowsClipboard(on_change_callback=self._on_local_clipboard_changed)
        self.file_manager = FileManager()
        self.audio_engine = AudioEngine(on_mic_chunk_callback=self._on_mic_audio_chunk)

        self.running = False
        self.active_session = False
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Target FPS & throttle
        self.target_fps = 30
        self.frame_delay = 1.0 / self.target_fps
        self._clip_queue = asyncio.Queue()
        self._audio_queue = asyncio.Queue()

    def _on_mic_audio_chunk(self, b64_data: str):
        """Callback when local host microphone records an audio block."""
        try:
            self._audio_queue.put_nowait(b64_data)
        except Exception:
            pass

    def _on_local_clipboard_changed(self, text: str):
        """Callback when local host clipboard changes."""
        try:
            self._clip_queue.put_nowait(text)
        except Exception:
            pass

    async def _send_packet(self, msg_type: str, payload: Optional[Dict[str, Any]] = None, **kwargs):
        if self.ws and not self.ws.closed:
            pkt = create_packet(msg_type, payload, **kwargs)
            await self.ws.send_str(pkt)

    async def _video_stream_loop(self):
        """High-performance frame capture and delta streaming loop."""
        print("[Host] Video streaming loop started.")
        force_keyframe = True

        while self.running and self.active_session:
            t0 = time.perf_counter()
            try:
                # 1. Grab desktop frame
                img = self.capturer.grab()
                
                # 2. Encode with DeskRT-style tile & delta compression
                res = self.codec.encode(img, force_keyframe=force_keyframe)
                force_keyframe = False

                # 3. Transmit if frame has changes
                if res["kind"] == "full":
                    b64 = base64.b64encode(res["data"]).decode("ascii")
                    await self._send_packet(MessageType.VIDEO_FULL, {
                        "width": res["width"],
                        "height": res["height"],
                        "frame_id": res["frame_id"],
                        "image": b64
                    })
                elif res["kind"] == "delta":
                    encoded_tiles = []
                    for t in res["tiles"]:
                        encoded_tiles.append({
                            "x": t["x"],
                            "y": t["y"],
                            "w": t["w"],
                            "h": t["h"],
                            "image": base64.b64encode(t["data"]).decode("ascii")
                        })
                    await self._send_packet(MessageType.VIDEO_DELTA, {
                        "width": res["width"],
                        "height": res["height"],
                        "frame_id": res["frame_id"],
                        "tiles": encoded_tiles
                    })

            except Exception as e:
                print(f"[Host] Video loop warning: {e}")
                force_keyframe = True

            # Throttle to target FPS
            elapsed = time.perf_counter() - t0
            sleep_time = max(0.001, self.frame_delay - elapsed)
            await asyncio.sleep(sleep_time)

        print("[Host] Video streaming loop stopped.")

    async def _audio_stream_loop(self):
        """Streams microphone audio blocks to the remote peer."""
        while self.running and self.active_session:
            try:
                b64_chunk = await self._audio_queue.get()
                if self.active_session:
                    await self._send_packet(MessageType.AUDIO_CHUNK, {"data": b64_chunk})
            except Exception:
                pass

    async def _clipboard_sync_loop(self):
        """Monitors clipboard for changes and sends to remote client."""
        while self.running:
            try:
                self.clipboard.check_for_changes()
                while not self._clip_queue.empty():
                    text = self._clip_queue.get_nowait()
                    if self.active_session:
                        await self._send_packet(MessageType.CLIPBOARD_TEXT, {"text": text})
            except Exception:
                pass
            await asyncio.sleep(0.3)

    async def _handle_message(self, packet: Dict[str, Any]):
        mtype = packet.get("type")
        payload = packet.get("payload", {})

        # --- Registration Response ---
        if mtype == MessageType.REGISTER_RESP:
            self.assigned_id = payload.get("id")
            print("\n" + "=" * 50)
            print(f"  OPENDESK HOST IS READY!")
            print(f"  Your OpenDesk ID: \033[1;32m{self.assigned_id}\033[0m")
            print(f"  Relay Server: {self.relay_url}")
            print(f"  Client Web UI: http://localhost:8080")
            print("=" * 50 + "\n")

        # --- Session Start / End ---
        elif mtype == MessageType.SESSION_START:
            client_id = payload.get("client_id")
            print(f"[Host] Incoming connection from client [{client_id}]. Starting stream...")
            self.active_session = True
            self.codec.reset()
            self.audio_engine.start()
            # Start streaming loops
            asyncio.create_task(self._video_stream_loop())
            asyncio.create_task(self._audio_stream_loop())

        elif mtype == MessageType.SESSION_END:
            print("[Host] Client disconnected.")
            self.active_session = False
            self.codec.reset()
            self.audio_engine.stop()

        # --- Input Events ---
        elif mtype == MessageType.INPUT_MOUSE_MOVE:
            self.input_controller.move_mouse(payload.get("x", 0), payload.get("y", 0))

        elif mtype == MessageType.INPUT_MOUSE_DOWN:
            self.input_controller.mouse_down(
                payload.get("button", 0),
                payload.get("x"),
                payload.get("y")
            )

        elif mtype == MessageType.INPUT_MOUSE_UP:
            self.input_controller.mouse_up(
                payload.get("button", 0),
                payload.get("x"),
                payload.get("y")
            )

        elif mtype == MessageType.INPUT_MOUSE_SCROLL:
            self.input_controller.mouse_scroll(
                payload.get("delta_x", 0),
                payload.get("delta_y", 0)
            )

        elif mtype == MessageType.INPUT_KEY_DOWN:
            self.input_controller.key_down(
                payload.get("code", ""),
                payload.get("key", "")
            )

        elif mtype == MessageType.INPUT_KEY_UP:
            self.input_controller.key_up(
                payload.get("code", ""),
                payload.get("key", "")
            )

        elif mtype == MessageType.INPUT_SHORTCUT:
            self.input_controller.execute_shortcut(payload.get("name", ""))

        # --- Clipboard Events ---
        elif mtype == MessageType.CLIPBOARD_TEXT:
            new_text = payload.get("text", "")
            if new_text:
                self.clipboard.set_text(new_text)

        # --- Real-Time Voice Audio Events ---
        elif mtype == MessageType.AUDIO_CHUNK:
            b64_audio = payload.get("data")
            if b64_audio:
                self.audio_engine.play_chunk(b64_audio)

        elif mtype == MessageType.AUDIO_CONTROL:
            action = payload.get("action")
            if action == "mute_mic":
                self.audio_engine.mic_enabled = False
            elif action == "unmute_mic":
                self.audio_engine.mic_enabled = True

        # --- File Transfer Events ---
        elif mtype == MessageType.FILE_LIST_REQ:
            target_path = payload.get("path")
            res = self.file_manager.list_directory(target_path)
            await self._send_packet(MessageType.FILE_LIST_RESP, res)

        elif mtype == MessageType.FILE_DOWNLOAD_REQ:
            file_path = payload.get("path")
            chunk_idx = payload.get("chunk_index", 0)
            res = self.file_manager.read_file_chunk(file_path, chunk_idx)
            await self._send_packet(MessageType.FILE_CHUNK, res)

        elif mtype == MessageType.FILE_UPLOAD_START:
            upload_id = payload.get("upload_id")
            target_dir = payload.get("target_dir")
            filename = payload.get("filename")
            total_chunks = payload.get("total_chunks")
            file_size = payload.get("file_size")
            res = self.file_manager.start_upload(upload_id, target_dir, filename, total_chunks, file_size)
            await self._send_packet(MessageType.FILE_UPLOAD_START, res)

        elif mtype == MessageType.FILE_CHUNK:
            upload_id = payload.get("upload_id")
            chunk_idx = payload.get("chunk_index")
            b64_data = payload.get("data")
            res = self.file_manager.write_upload_chunk(upload_id, chunk_idx, b64_data)
            await self._send_packet(MessageType.FILE_CHUNK, res)

    async def start(self):
        """Connect to relay and maintain session loop."""
        self.running = True
        asyncio.create_task(self._clipboard_sync_loop())

        while self.running:
            try:
                async with aiohttp.ClientSession() as session:
                    self.session = session
                    print(f"[Host] Connecting to relay server at {self.relay_url} ...")
                    async with session.ws_connect(self.relay_url, max_msg_size=16*1024*1024) as ws:
                        self.ws = ws
                        # Register as host
                        await self._send_packet(MessageType.REGISTER, {
                            "role": "host",
                            "id": self.requested_id,
                            "password": self.password
                        })

                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                pkt = parse_packet(msg.data)
                                if pkt:
                                    await self._handle_message(pkt)
                            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                break
            except Exception as e:
                print(f"[Host] Connection error: {e}. Reconnecting in 3s ...")
                self.active_session = False
                await asyncio.sleep(3)

    def stop(self):
        self.running = False
        self.active_session = False
        self.audio_engine.stop()
        self.capturer.close()
