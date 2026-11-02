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
import os
import math
from concurrent.futures import ThreadPoolExecutor
from collections import deque
from PIL import Image
import numpy as np
from common.security import password_record
from common.protocol import encode_video_packet
from typing import Optional, Dict, Any, Callable
import aiohttp

from common.protocol import MessageType, create_packet, parse_packet
from common.codec import DeskRTCodec
from host.capture import AdaptiveScreenCapturer
from host.input_controller import WindowsInputController
from host.clipboard import WindowsClipboard
from host.file_manager import FileManager
from host.audio import AudioEngine

class HostAgent:
    def __init__(self, relay_url: str = "ws://localhost:8080/ws", host_id: Optional[str] = None, password: str = "", host_token: str = "",
                 on_connection_request: Optional[Callable[[str, str, Callable[[str, bool, Optional[Dict[str, bool]]], None]], None]] = None):
        self.relay_url = relay_url
        self.requested_id = host_id
        self.password = password
        self.host_token = host_token or os.environ.get("OPENDESK_HOST_TOKEN", "")
        self.auth_record = password_record(password)
        self.session_id = None
        self.pending_requests = {}
        self.approved_requests = {}
        self._capture_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="screen")
        self._outstanding = deque()
        self._ack_event = asyncio.Event()
        self._force_keyframe = True
        self.max_width = 1600
        self._width_limit = 1600
        self._last_adapt = 0.0
        self._requested_fps = 30
        self._requested_quality = 65
        self._network_rtt = 0.0
        self._network_congested = False
        self._healthy_intervals = 0
        self.assigned_id: Optional[str] = None
        self.on_connection_request = on_connection_request
        
        # Session Permissions
        self.permissions = {
            "input": True,
            "audio": True,
            "clipboard": True,
            "file_transfer": True
        }
        
        # Subsystems
        self.capturer = None
        self.codec = DeskRTCodec(tile_size=128, quality=65)
        self.input_controller = WindowsInputController()
        self.input_controller.enabled = False
        self.clipboard = WindowsClipboard(on_change_callback=self._on_local_clipboard_changed)
        self.file_manager = FileManager()
        self.audio_engine = AudioEngine(on_mic_chunk_callback=self._on_mic_audio_chunk)

        self.running = False
        self.active_session = False
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self.session: Optional[aiohttp.ClientSession] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        
        # Target FPS & throttle (Ultra-Smooth 60 FPS capable)
        self.target_fps = 30
        self.frame_delay = 1.0 / self.target_fps
        self._clip_queue = asyncio.Queue()
        self._audio_queue = asyncio.Queue(maxsize=5)
        self._video_queue = asyncio.Queue(maxsize=1)

        # Worker Task references for clean lifecycle without leaks
        self._video_stream_task: Optional[asyncio.Task] = None
        self._video_sender_task: Optional[asyncio.Task] = None
        self._audio_stream_task: Optional[asyncio.Task] = None

    def _cancel_stream_tasks(self):
        """Cancel active streaming tasks safely on session change or disconnect."""
        for t in (self._video_stream_task, self._video_sender_task, self._audio_stream_task):
            if t and not t.done():
                try:
                    t.cancel()
                except Exception:
                    pass
        self._video_stream_task = None
        self._video_sender_task = None
        self._audio_stream_task = None

    def _on_mic_audio_chunk(self, b64_data: str):
        """Callback when local host microphone records an audio block."""
        if not self.running or not self.active_session:
            return
        try:
            if self.loop and self.loop.is_running():
                self.loop.call_soon_threadsafe(self._queue_audio, b64_data)
            else:
                self._audio_queue.put_nowait(b64_data)
        except Exception:
            pass

    def _queue_audio(self, data):
        if self._audio_queue.full():
            self._audio_queue.get_nowait()
        self._audio_queue.put_nowait(data)

    def _on_local_clipboard_changed(self, text: str):
        """Callback when local host clipboard changes."""
        try:
            self._clip_queue.put_nowait(text)
        except Exception:
            pass

    async def _send_packet(self, msg_type: str, payload: Optional[Dict[str, Any]] = None, **kwargs):
        if self.ws and not self.ws.closed:
            if msg_type.startswith('file_') and payload and payload.get('error'):
                msg_type = MessageType.FILE_ERROR
                payload = {'message':payload['error']}
            pkt = create_packet(msg_type, payload, **kwargs)
            await self.ws.send_str(pkt)

    def _capture_encode(self, force):
        # GDI objects remain on one worker; network/audio never wait for JPEG work.
        if self.capturer is None:
            self.capturer = AdaptiveScreenCapturer()
        img, pixels = self.capturer.grab_frame()
        max_width = self.max_width
        if img.width > max_width:
            height = max(1, round(img.height * max_width / img.width))
            img = img.resize((max_width, height), Image.Resampling.BILINEAR)
            pixels = np.asarray(img.convert('RGBA')).view(np.uint32).reshape((height,max_width))
        self.input_controller.update_screen_size(self.capturer.width, self.capturer.height)
        return self.codec.encode(img, raw_u32=pixels, force_keyframe=force)

    async def _video_stream_loop(self):
        while self.running and self.active_session:
            t0 = time.monotonic()
            try:
                # Keep a small bounded dependency chain; never discard an encoded delta.
                window = min(10,max(3,math.ceil(self.target_fps*self._network_rtt)+1))
                if len(self._outstanding) >= window:
                    self._ack_event.clear()
                    await asyncio.wait_for(self._ack_event.wait(), timeout=3)
                    continue
                force = self._force_keyframe
                self._force_keyframe = False
                frame = await self.loop.run_in_executor(self._capture_executor, self._capture_encode, force)
                if not self.active_session:
                    break
                if frame['kind'] != 'empty':
                    self._outstanding.append((frame['frame_id'], time.monotonic()))
                    await self.ws.send_bytes(encode_video_packet(frame, self.session_id))
                elapsed = time.monotonic()-t0
                self._adapt_stream(elapsed,t0)
                await asyncio.sleep(max(.001, 1/self.target_fps-(time.monotonic()-t0)))
            except asyncio.CancelledError:
                break
            except asyncio.TimeoutError:
                await self._send_packet(MessageType.SESSION_END, message='Viewer stopped acknowledging frames.')
                self._end_session()
            except Exception as exc:
                print(f'[Host] Video error: {exc}')
                self._force_keyframe = True
                await asyncio.sleep(.1)

    def _adapt_stream(self, elapsed, now):
        if now-self._last_adapt < 2: return
        self._last_adapt = now
        if self._network_congested:
            self.max_width = max(640,round(self.max_width*.85))
            self.target_fps = max(10,round(self.target_fps*.8))
            self.codec.set_quality(max(35,self.codec.quality-5))
            self._healthy_intervals = 0
        elif elapsed > .080 and self.max_width > 960:
            self.max_width = max(960,self.max_width-160)
            self.codec.set_quality(max(45,self.codec.quality-5))
            self._healthy_intervals = 0
        else:
            self._healthy_intervals += 1
            if self._healthy_intervals >= 3:
                self.max_width = min(self._width_limit,self.max_width+160)
                self.target_fps = min(self._requested_fps,self.target_fps+5)
                self.codec.set_quality(min(self._requested_quality,self.codec.quality+3))
                self._healthy_intervals = 0
        self._network_congested = False

    def _end_session(self):
        self.active_session = False
        self.session_id = None
        self._network_rtt = 0.0
        self._network_congested = False
        self._healthy_intervals = 0
        self.input_controller.release_all()
        self.input_controller.enabled = False
        self._cancel_stream_tasks()
        self.audio_engine.stop()
        self.file_manager.cancel_all()
        self._outstanding.clear()
        for q in (self._audio_queue, self._clip_queue):
            while not q.empty():
                q.get_nowait()

    async def _audio_stream_loop(self):
        """Streams microphone audio blocks to the remote peer."""
        while self.running and self.active_session:
            try:
                b64_chunk = await self._audio_queue.get()
                if self.active_session and self.permissions.get("audio", True):
                    await self._send_packet(MessageType.AUDIO_CHUNK, {"data": b64_chunk, "sample_rate": 48000, "channels": 1, "format": "pcm_s16le"})
            except Exception:
                pass

    async def _clipboard_sync_loop(self):
        """Monitors clipboard for changes and sends to remote client."""
        while self.running:
            try:
                self.clipboard.check_for_changes()
                while not self._clip_queue.empty():
                    text = self._clip_queue.get_nowait()
                    if self.active_session and self.permissions.get("clipboard", True):
                        await self._send_packet(MessageType.CLIPBOARD_TEXT, {"text": text})
            except Exception:
                pass
            await asyncio.sleep(0.3)

    def handle_decision(self, client_id: str, accepted: bool, permissions: Optional[Dict[str, bool]] = None):
        """Thread-safe dispatcher for UI connection decision (Accept/Reject)."""
        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(
                asyncio.create_task,
                self._async_handle_decision(client_id, accepted, permissions or {})
            )

    async def _async_handle_decision(self, client_id, accepted, permissions):
        request_id = self.pending_requests.pop(client_id, None)
        if not request_id or self.active_session:
            return
        if accepted:
            self.approved_requests[request_id] = dict(permissions)
        await self._send_packet(MessageType.SESSION_ACCEPT if accepted else MessageType.SESSION_REJECT,
                                client_id=client_id, request_id=request_id, permissions=permissions)

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

        elif mtype == MessageType.SESSION_REQUEST:
            client_id = payload.get('client_id')
            if not payload.get('request_id') or self.active_session:
                return
            self.pending_requests[client_id] = payload['request_id']
            if self.on_connection_request:
                self.on_connection_request(client_id, payload.get('display_id', client_id), self.handle_decision)
            else:
                # Headless hosts require an unattended password; never auto-approve.
                self.handle_decision(client_id, False)

        elif mtype == 'request_cancelled':
            self.pending_requests.pop(payload.get('client_id'), None)
            self.approved_requests.pop(payload.get('request_id'), None)

        elif mtype == MessageType.SESSION_START:
            approved = self.approved_requests.pop(payload.get('request_id'), None)
            unattended = payload.get('unattended') and self.auth_record is not None
            if self.active_session or (approved is None and not unattended) or not payload.get('session_id'):
                return
            self.permissions = dict(payload.get('permissions', {})) if unattended else approved
            self.session_id = payload['session_id']
            self.active_session = True
            self.input_controller.enabled = bool(self.permissions.get('input', False))
            self._force_keyframe = True
            self._outstanding.clear()
            self._cancel_stream_tasks()
            self._video_stream_task = asyncio.create_task(self._video_stream_loop())
            if self.permissions.get('audio', False):
                self.audio_engine.start()
                self._audio_stream_task = asyncio.create_task(self._audio_stream_loop())

        elif mtype == MessageType.SESSION_END:
            self._end_session()

        elif not self.active_session or payload.get('session_id') != self.session_id:
            return

        elif mtype == MessageType.INPUT_RESET:
            self.input_controller.release_all()

        elif mtype.startswith(('mouse_', 'key_')) or mtype == MessageType.INPUT_SHORTCUT:
            if not self.permissions.get('input', False):
                return
            methods = {
                'mouse_move': lambda: self.input_controller.move_mouse(payload.get('x',0), payload.get('y',0)),
                'mouse_down': lambda: self.input_controller.mouse_down(payload.get('button',0),payload.get('x'),payload.get('y')),
                'mouse_up': lambda: self.input_controller.mouse_up(payload.get('button',0),payload.get('x'),payload.get('y')),
                'mouse_scroll': lambda: self.input_controller.mouse_scroll(payload.get('delta_x',0),payload.get('delta_y',0)),
                'key_down': lambda: self.input_controller.key_down(payload.get('code',''),payload.get('key','')),
                'key_up': lambda: self.input_controller.key_up(payload.get('code',''),payload.get('key','')),
                'shortcut': lambda: self.input_controller.execute_shortcut(payload.get('name','')),
            }
            if mtype in methods:
                methods[mtype]()

        elif mtype == MessageType.VIDEO_ACK:
            frame_id = payload.get('frame_id', -1)
            reported_rtt = payload.get('rtt_ms',0)
            if isinstance(reported_rtt,(int,float)) and 0 < reported_rtt <= 2000:
                self._network_rtt = reported_rtt/1000
            if self._outstanding and self._network_rtt:
                age = time.monotonic()-self._outstanding[0][1]
                if age > self._network_rtt + max(.08,self._network_rtt*.5):
                    self._network_congested = True
            while self._outstanding and self._outstanding[0][0] <= frame_id:
                self._outstanding.popleft()
            self._ack_event.set()

        elif mtype == MessageType.VIDEO_REFRESH:
            self._outstanding.clear()
            self._ack_event.set()
            self._force_keyframe = True

        elif mtype == MessageType.VIDEO_CONFIG:
            self.target_fps = max(10, min(60, int(payload.get('fps', 30))))
            self.max_width = max(640, min(2560, int(payload.get('max_width', 1600))))
            self._width_limit = self.max_width
            self._requested_fps = self.target_fps
            self._requested_quality = max(10,min(95,int(payload.get('quality',65))))
            self.codec.set_quality(int(payload.get('quality',65)))
            self._force_keyframe = True

        elif mtype.startswith('file_') and not self.permissions.get('file_transfer',False):
            await self._send_packet(MessageType.FILE_ERROR, message='File transfer disabled by host.')

        # --- Clipboard Events ---
        elif mtype == MessageType.CLIPBOARD_TEXT:
            if not self.permissions.get("clipboard", True):
                return
            new_text = payload.get("text", "")
            auto_paste = payload.get("auto_paste", False)
            if new_text:
                self.clipboard.set_text(new_text)
                if auto_paste and self.permissions.get("input", True):
                    if self.loop and self.loop.is_running():
                        self.loop.call_later(0.04, lambda: self.input_controller.execute_shortcut("paste"))
                    else:
                        self.input_controller.execute_shortcut("paste")

        # --- Real-Time Voice Audio Events ---
        elif mtype == MessageType.AUDIO_CHUNK:
            if not self.permissions.get("audio", True):
                return
            b64_audio = payload.get("data")
            if b64_audio:
                self.audio_engine.play_chunk(b64_audio, payload.get("sample_rate", 48000))

        elif mtype == MessageType.AUDIO_CONTROL:
            action = payload.get("action")
            if action == "mute_mic":
                self.audio_engine.mic_enabled = False
            elif action == "unmute_mic":
                self.audio_engine.mic_enabled = True

        # --- File Transfer Events ---
        elif mtype == MessageType.FILE_LIST_REQ:
            if not self.permissions.get("file_transfer", True):
                await self._send_packet(MessageType.FILE_ERROR, {"message": "File transfer disabled by host."})
                return
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
            res = self.file_manager.start_upload(upload_id, target_dir, filename, total_chunks, file_size, payload.get("sha256"))
            await self._send_packet(MessageType.FILE_UPLOAD_START, res)

        elif mtype == MessageType.FILE_CHUNK:
            upload_id = payload.get("upload_id")
            chunk_idx = payload.get("chunk_index")
            b64_data = payload.get("data")
            res = self.file_manager.write_upload_chunk(upload_id, chunk_idx, b64_data)
            await self._send_packet(MessageType.FILE_CHUNK, res)

    async def start(self):
        """Connect to relay and maintain session loop."""
        self.loop = asyncio.get_running_loop()
        self.running = True
        asyncio.create_task(self._clipboard_sync_loop())

        while self.running:
            try:
                async with aiohttp.ClientSession() as session:
                    self.session = session
                    print(f"[Host] Connecting to relay server at {self.relay_url} ...")
                    async with session.ws_connect(self.relay_url, max_msg_size=8*1024*1024, heartbeat=20, compress=0) as ws:
                        self.ws = ws
                        # Register as host
                        await self._send_packet(MessageType.REGISTER, {
                            "role": "host",
                            "id": self.requested_id,
                            "protocol": 2,
                            "host_token": self.host_token,
                            "password_record": self.auth_record
                        })

                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                pkt = parse_packet(msg.data)
                                if pkt:
                                    try:
                                        await self._handle_message(pkt)
                                    except (ValueError, TypeError, KeyError, OSError) as exc:
                                        await self._send_packet(MessageType.FILE_ERROR, message=str(exc))
                            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                break
                self._end_session()
            except Exception as e:
                print(f"[Host] Connection error: {e}. Reconnecting in 3s ...")
                self._end_session()
                await asyncio.sleep(3)

    def update_password(self, password):
        async def change():
            self.auth_record = await asyncio.to_thread(password_record, password)
            await self._send_packet('host_config', password_record=self.auth_record)
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(change(), self.loop)

    def stop(self):
        self.running = False
        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self._end_session)
            if self.ws and not self.ws.closed:
                asyncio.run_coroutine_threadsafe(self.ws.close(), self.loop)
        if self.capturer:
            self._capture_executor.submit(self.capturer.close)
        self._capture_executor.shutdown(wait=False, cancel_futures=True)
