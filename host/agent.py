"""
OpenDesk Host Agent
Runs on the machine being controlled.
- Captures screen frames via Win32 DIBSection
- Encodes frames via DeskRT Tile & Delta Codec
- Injects remote mouse & keyboard inputs
- Manages bidirectional clipboard sync
- Handles remote file browsing and chunked transfers
- Connects to OpenDesk Relay Server

Latency design:
- Screen capture, JPEG encoding and base64 are executed on a dedicated worker
  thread so the asyncio loop stays free to inject mouse/keyboard events the
  instant they arrive (previously a full-frame encode could stall input).
- The outgoing frame queue keeps only the freshest frame; stale frames are
  dropped instead of being queued (which is what creates growing delay).
- Capture scale, JPEG quality and target FPS adapt automatically to measured
  socket backpressure, so slow internet links stay smooth instead of laggy.
"""

import time
import base64
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Dict, Any, Callable

import aiohttp

try:
    from opendesk.common.protocol import MessageType, create_packet, parse_packet
    from opendesk.common.codec import DeskRTCodec
    from opendesk.host.capture import WindowsScreenCapturer
    from opendesk.host.input_controller import WindowsInputController
    from opendesk.host.clipboard import WindowsClipboard
    from opendesk.host.file_manager import FileManager
    from opendesk.host.audio import AudioEngine
except ImportError:
    from common.protocol import MessageType, create_packet, parse_packet
    from common.codec import DeskRTCodec
    from host.capture import WindowsScreenCapturer
    from host.input_controller import WindowsInputController
    from host.clipboard import WindowsClipboard
    from host.file_manager import FileManager
    from host.audio import AudioEngine


class HostAgent:
    # Adaptive streaming bounds
    MIN_SCALE = 0.5
    MAX_SCALE = 1.0
    MIN_FPS = 24
    MAX_FPS = 60
    MIN_QUALITY = 45
    MAX_QUALITY = 70

    def __init__(self, relay_url: str = "ws://localhost:8080/ws", host_id: Optional[str] = None, password: str = "",
                 on_connection_request: Optional[Callable[[str, str, Callable[[str, bool, Optional[Dict[str, bool]]], None]], None]] = None):
        self.relay_url = relay_url
        self.requested_id = host_id
        self.password = password
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
        self.capturer = WindowsScreenCapturer(scale=0.75)
        self.codec = DeskRTCodec(tile_size=128, quality=70)
        self.input_controller = WindowsInputController()
        self.clipboard = WindowsClipboard(on_change_callback=self._on_local_clipboard_changed)
        self.file_manager = FileManager()
        self.audio_engine = AudioEngine(on_mic_chunk_callback=self._on_mic_audio_chunk)

        self.running = False
        self.active_session = False
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self.session: Optional[aiohttp.ClientSession] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None

        # Target FPS & throttle (adaptive)
        self.target_fps = 60
        self.frame_delay = 1.0 / self.target_fps
        self._clip_queue = asyncio.Queue()
        self._audio_queue = asyncio.Queue()
        self._video_queue = asyncio.Queue(maxsize=2)

        # Adaptive encoder state (applied on the capture thread)
        self._pending_scale = 0.75
        self._pending_quality = 70
        self._send_time_ewma = 0.0
        self._dropped_frames = 0
        self._adapt_at = time.monotonic()
        self._keyframe_requested = False
        self._healthy_streak = 0
        self._client_rtt_ms = -1.0

        # Single-thread executor keeps GDI/desktop affinity stable and serializes codec access
        self._capture_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="opendesk-capture")

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

    def _drain_video_queue(self):
        while True:
            try:
                self._video_queue.get_nowait()
            except Exception:
                break

    def _on_mic_audio_chunk(self, b64_data: str):
        """Callback when local host microphone records an audio block."""
        if not self.running or not self.active_session:
            return

        def _enqueue():
            # 20ms per chunk: anything beyond ~300ms of backlog must be dropped,
            # otherwise a slow link makes the voice stream fall further behind.
            if self._audio_queue.qsize() > 15:
                try:
                    self._audio_queue.get_nowait()
                except Exception:
                    pass
            try:
                self._audio_queue.put_nowait(b64_data)
            except Exception:
                pass

        try:
            if self.loop and self.loop.is_running():
                self.loop.call_soon_threadsafe(_enqueue)
            else:
                _enqueue()
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

    # ------------------------------------------------------------------
    # Capture / encode (runs on the dedicated worker thread)
    # ------------------------------------------------------------------
    def _capture_and_encode(self, force_keyframe: bool):
        if not self.running or not self.active_session:
            return None

        # Apply pending adaptive changes lazily on the capture thread (GDI-safe)
        if abs(self._pending_scale - self.capturer.scale) >= 0.005:
            self.capturer.set_scale(self._pending_scale)
            self.codec.reset()
            force_keyframe = True
        if self._pending_quality != self.codec.quality:
            self.codec.set_quality(self._pending_quality)

        try:
            img, arr_u32 = self.capturer.grab_frame()
            res = self.codec.encode(img, raw_u32=arr_u32, force_keyframe=force_keyframe)
        except Exception as e:
            print(f"[Host] Capture/encode warning: {e}")
            return None

        kind = res["kind"]
        if kind == "full":
            return (MessageType.VIDEO_FULL, {
                "width": res["width"],
                "height": res["height"],
                "frame_id": res["frame_id"],
                "image": base64.b64encode(res["data"]).decode("ascii")
            })
        if kind == "delta":
            tiles = [{
                "x": t["x"],
                "y": t["y"],
                "w": t["w"],
                "h": t["h"],
                "image": base64.b64encode(t["data"]).decode("ascii")
            } for t in res["tiles"]]
            return (MessageType.VIDEO_DELTA, {
                "width": res["width"],
                "height": res["height"],
                "frame_id": res["frame_id"],
                "tiles": tiles
            })
        return None

    def _enqueue_frame(self, packet):
        """Keep at most the freshest frames queued; never build up latency."""
        if self._video_queue.full():
            try:
                self._video_queue.get_nowait()
                self._dropped_frames += 1
                # A dropped frame desyncs the client's tile state - recover with a keyframe
                self._keyframe_requested = True
            except Exception:
                pass
        try:
            self._video_queue.put_nowait(packet)
        except Exception:
            pass

    def _socket_backlog(self) -> int:
        """Bytes still queued in the kernel/socket send buffer (real backpressure)."""
        ws = self.ws
        if ws is None:
            return 0
        try:
            transport = getattr(getattr(ws, "_writer", None), "transport", None)
            if transport is not None:
                return int(transport.get_write_buffer_size() or 0)
        except Exception:
            pass
        return 0

    def _adapt_streaming(self):
        """Tune resolution / quality / FPS from measured socket backpressure."""
        now = time.monotonic()
        if now - self._adapt_at < 1.0:
            return
        self._adapt_at = now

        drops = self._dropped_frames
        self._dropped_frames = 0
        send_ms = self._send_time_ewma
        backlog = self._socket_backlog()
        rtt = self._client_rtt_ms

        # Congestion is visible through dropped frames, a slow send, a growing
        # kernel send buffer, or an inflated client-measured round-trip time
        # (heartbeats queue behind video data, so high RTT == high backlog).
        constrained = (
            drops > 0
            or send_ms > 0.022
            or backlog > 192 * 1024
            or rtt > 250.0
        )
        healthy = (
            drops == 0
            and send_ms < 0.010
            and backlog < 48 * 1024
            and 0.0 <= rtt < 120.0
        )

        if constrained:
            self._healthy_streak = 0
            if self._pending_scale > self.MIN_SCALE:
                self._pending_scale = max(self.MIN_SCALE, round(self._pending_scale - 0.15, 2))
            elif self.target_fps > self.MIN_FPS:
                self.target_fps = max(self.MIN_FPS, self.target_fps - 6)
                self.frame_delay = 1.0 / self.target_fps
            self._pending_quality = max(self.MIN_QUALITY, self._pending_quality - 5)
        elif healthy:
            # Require a sustained healthy streak so recovery never oscillates
            # (every scale change forces a keyframe, which is costly on tunnels).
            self._healthy_streak += 1
            if self._healthy_streak >= 3:
                self._healthy_streak = 0
                if self.target_fps < self.MAX_FPS:
                    self.target_fps = min(self.MAX_FPS, self.target_fps + 6)
                    self.frame_delay = 1.0 / self.target_fps
                elif self._pending_scale < self.MAX_SCALE:
                    self._pending_scale = min(self.MAX_SCALE, round(self._pending_scale + 0.05, 2))
                self._pending_quality = min(self.MAX_QUALITY, self._pending_quality + 2)

    async def _video_sender_worker(self):
        """Transmits queued frames and measures socket backpressure for adaptation."""
        while self.running and self.active_session:
            try:
                msg_type, payload = await self._video_queue.get()
            except asyncio.CancelledError:
                break
            try:
                t0 = time.perf_counter()
                await self._send_packet(msg_type, payload)
                dt = time.perf_counter() - t0
                self._send_time_ewma = dt if self._send_time_ewma == 0.0 else (0.85 * self._send_time_ewma + 0.15 * dt)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[Host] Video sender worker notice: {e}")

    async def _video_stream_loop(self):
        """
        Adaptive screen capture / delta encoding loop.
        Capture+encode runs on a worker thread; the event loop stays responsive
        so remote mouse/keyboard injection is never delayed by JPEG encoding.
        """
        print(f"[Host] Video streaming loop started (target {self.target_fps} FPS).")
        force_keyframe = True
        loop = asyncio.get_running_loop()

        while self.running and self.active_session:
            t0 = time.perf_counter()
            try:
                force = force_keyframe or self._keyframe_requested
                self._keyframe_requested = False
                packet = await loop.run_in_executor(self._capture_executor, self._capture_and_encode, force)
                force_keyframe = False
                if packet is not None:
                    self._enqueue_frame(packet)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[Host] Video loop warning: {e}")
                force_keyframe = True

            self._adapt_streaming()

            elapsed = time.perf_counter() - t0
            remaining = self.frame_delay - elapsed
            if remaining > 0.001:
                await asyncio.sleep(remaining)
            else:
                await asyncio.sleep(0)

        print("[Host] Video streaming loop stopped.")

    async def _audio_stream_loop(self):
        """Streams microphone audio blocks to the remote peer."""
        while self.running and self.active_session:
            try:
                b64_chunk = await self._audio_queue.get()
                if self.active_session and self.permissions.get("audio", True):
                    await self._send_packet(MessageType.AUDIO_CHUNK, {"data": b64_chunk})
            except asyncio.CancelledError:
                break
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

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------
    def _start_stream_tasks(self, allow_audio: bool):
        self._cancel_stream_tasks()
        self._drain_video_queue()
        self._keyframe_requested = True
        self._client_rtt_ms = -1.0
        self._healthy_streak = 0
        self._send_time_ewma = 0.0
        self._pending_scale = 0.75
        self._pending_quality = 70
        self.target_fps = self.MAX_FPS
        self.frame_delay = 1.0 / self.target_fps
        self._video_stream_task = asyncio.create_task(self._video_stream_loop())
        self._video_sender_task = asyncio.create_task(self._video_sender_worker())
        if allow_audio:
            self._audio_stream_task = asyncio.create_task(self._audio_stream_loop())

    def handle_decision(self, client_id: str, accepted: bool, permissions: Optional[Dict[str, bool]] = None):
        """Thread-safe dispatcher for UI connection decision (Accept/Reject)."""
        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(
                asyncio.create_task,
                self._async_handle_decision(client_id, accepted, permissions or {})
            )

    async def _async_handle_decision(self, client_id: str, accepted: bool, permissions: Dict[str, bool]):
        if accepted:
            self.permissions = permissions
            self.input_controller.enabled = bool(permissions.get("input", True))
            allow_audio = bool(permissions.get("audio", True))
            self.active_session = True
            self.codec.reset()
            if allow_audio:
                self.audio_engine.start()

            print(f"[Host] Session accepted for client [{client_id}]. Permissions: {permissions}")
            await self._send_packet(MessageType.SESSION_ACCEPT, {
                "client_id": client_id,
                "permissions": permissions
            })
            self._start_stream_tasks(allow_audio)
        else:
            print(f"[Host] Session declined for client [{client_id}].")
            await self._send_packet(MessageType.SESSION_REJECT, {
                "client_id": client_id,
                "message": "Connection request declined by remote host."
            })

    def _end_session(self):
        self.active_session = False
        self.codec.reset()
        self._cancel_stream_tasks()
        self._drain_video_queue()
        try:
            self.audio_engine.stop()
        except Exception:
            pass

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

        # --- Latency probe echo (client measures real round-trip time) ---
        elif mtype == MessageType.HEARTBEAT:
            client_rtt = payload.get("rtt")
            if isinstance(client_rtt, (int, float)) and client_rtt >= 0:
                self._client_rtt_ms = float(client_rtt)
            await self._send_packet(MessageType.HEARTBEAT, {"t": payload.get("t")})

        # --- Interactive Session Request (AnyDesk-style Incoming Dialog) ---
        elif mtype == MessageType.SESSION_REQUEST:
            client_id = payload.get("client_id")
            display_id = payload.get("display_id", client_id)
            print(f"[Host] Received incoming connection request from [{display_id}].")
            if self.on_connection_request:
                self.on_connection_request(client_id, display_id, self.handle_decision)
            else:
                self.handle_decision(client_id, True, {
                    "input": True, "audio": True, "clipboard": True, "file_transfer": True
                })

        # --- Direct Session Start (Unattended Access or Legacy) ---
        elif mtype == MessageType.SESSION_START:
            client_id = payload.get("client_id")
            print(f"[Host] Incoming connection from client [{client_id}]. Starting stream...")
            self.active_session = True
            self.codec.reset()
            self.input_controller.enabled = True
            self.audio_engine.start()
            self._start_stream_tasks(allow_audio=True)

        elif mtype == MessageType.SESSION_END:
            print("[Host] Client disconnected.")
            self._end_session()

        # --- Keyframe recovery request (client missed a frame) ---
        elif mtype == MessageType.KEYFRAME_REQUEST:
            self._keyframe_requested = True

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
                self.audio_engine.play_chunk(b64_audio)

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
            res = self.file_manager.start_upload(upload_id, target_dir, filename, total_chunks, file_size)
            await self._send_packet(MessageType.FILE_UPLOAD_START, res)

        elif mtype == MessageType.FILE_CHUNK:
            upload_id = payload.get("upload_id")
            chunk_idx = payload.get("chunk_index")
            b64_data = payload.get("data")
            res = self.file_manager.write_upload_chunk(upload_id, chunk_idx, b64_data)
            await self._send_packet(MessageType.FILE_CHUNK, res)

    # ------------------------------------------------------------------
    # Relay connection
    # ------------------------------------------------------------------
    async def _close_ws(self):
        try:
            if self.ws and not self.ws.closed:
                await self.ws.close()
        except Exception:
            pass

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
                    async with session.ws_connect(self.relay_url, max_msg_size=16 * 1024 * 1024,
                                                  heartbeat=20.0) as ws:
                        self.ws = ws
                        await self._send_packet(MessageType.REGISTER, {
                            "role": "host",
                            "id": self.requested_id,
                            "password": self.password
                        })

                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                pkt = parse_packet(msg.data)
                                if pkt:
                                    try:
                                        await self._handle_message(pkt)
                                    except Exception as e:
                                        print(f"[Host] Message handler warning: {e}")
                            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                break
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[Host] Connection error: {e}. Reconnecting in 3s ...")
            finally:
                # A dropped relay socket means no client can receive frames - stop the DSP
                self.ws = None
                if self.active_session:
                    self._end_session()
                try:
                    if self.session and not self.session.closed:
                        await self.session.close()
                except Exception:
                    pass
                self.session = None

            if not self.running:
                break
            await asyncio.sleep(3)

    def stop(self):
        self.running = False
        loop = self.loop
        if loop and loop.is_running():
            try:
                # Task.cancel() must run on the loop thread
                loop.call_soon_threadsafe(self._end_session)
            except Exception:
                self._end_session()
        else:
            self._end_session()
        try:
            self._capture_executor.shutdown(wait=True)
        except Exception:
            pass
        try:
            self.capturer.close()
        except Exception:
            pass
