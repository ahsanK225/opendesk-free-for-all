"""
Real-Time Bidirectional Voice Audio Engine for OpenDesk
Handles low-latency microphone capture and speaker playback using PortAudio / sounddevice.
"""

import sys
import queue
import base64
import threading
import numpy as np
from typing import Optional, Callable

SAMPLE_RATE = 16000
CHANNELS = 1
BLOCK_SIZE = 1600  # 100ms per audio block at 16kHz

class AudioEngine:
    def __init__(self, on_mic_chunk_callback: Optional[Callable[[str], None]] = None):
        self.on_mic_chunk_callback = on_mic_chunk_callback
        self.mic_enabled = True
        self.speaker_enabled = True
        self.running = False
        
        self.input_stream = None
        self.output_stream = None
        self.play_queue = queue.Queue(maxsize=100)

    def _mic_callback(self, indata, frames, time_info, status):
        """Called by PortAudio for each incoming microphone audio block."""
        if not self.running or not self.mic_enabled:
            return
        try:
            # indata is numpy int16 array of shape (frames, 1)
            raw_bytes = indata.tobytes()
            b64_audio = base64.b64encode(raw_bytes).decode("ascii")
            if self.on_mic_chunk_callback:
                self.on_mic_chunk_callback(b64_audio)
        except Exception:
            pass

    def _speaker_callback(self, outdata, frames, time_info, status):
        """Called by PortAudio when speakers require audio data to play."""
        if not self.running or not self.speaker_enabled:
            outdata.fill(0)
            return
        try:
            raw_bytes = self.play_queue.get_nowait()
            data = np.frombuffer(raw_bytes, dtype=np.int16)
            if len(data) >= frames:
                outdata[:] = data[:frames].reshape(-1, 1)
            else:
                outdata[:len(data)] = data.reshape(-1, 1)
                outdata[len(data):].fill(0)
        except queue.Empty:
            outdata.fill(0)
        except Exception:
            outdata.fill(0)

    def play_chunk(self, b64_audio: str):
        """Queue an incoming remote audio chunk for speaker playback."""
        if not self.speaker_enabled:
            return
        try:
            raw_bytes = base64.b64decode(b64_audio)
            if self.play_queue.qsize() < 80:
                self.play_queue.put_nowait(raw_bytes)
        except Exception:
            pass

    def _find_best_input_device(self) -> Optional[int]:
        """Detect the best active physical microphone, avoiding disconnected virtual devices."""
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            default_in = sd.default.device[0]

            default_name = devices[default_in]["name"].lower() if default_in is not None and default_in < len(devices) else ""
            is_virtual = any(kw in default_name for kw in ("virtual desktop", "cable", "steam streaming"))

            if is_virtual:
                for idx, dev in enumerate(devices):
                    if dev["max_input_channels"] > 0:
                        name = dev["name"].lower()
                        if any(kw in name for kw in ("bloody", "realtek", "headset", "microphone", "usb")) and not any(kw in name for kw in ("virtual", "cable", "steam")):
                            print(f"[Audio] Selected physical microphone: [{idx}] {dev['name']}")
                            return idx
            return default_in if default_in is not None and default_in >= 0 else None
        except Exception as e:
            print(f"[Audio] Error detecting input device: {e}")
            return None

    def start(self):
        """Start microphone capture and speaker playback streams."""
        try:
            import sounddevice as sd
            self.running = True
            
            # Start speaker stream
            try:
                self.output_stream = sd.OutputStream(
                    samplerate=SAMPLE_RATE,
                    channels=CHANNELS,
                    dtype='int16',
                    blocksize=BLOCK_SIZE,
                    callback=self._speaker_callback
                )
                self.output_stream.start()
            except Exception as e:
                print(f"[Audio] Speaker output init warning: {e}")

            # Start mic stream
            try:
                input_dev = self._find_best_input_device()
                self.input_stream = sd.InputStream(
                    device=input_dev,
                    samplerate=SAMPLE_RATE,
                    channels=CHANNELS,
                    dtype='int16',
                    blocksize=BLOCK_SIZE,
                    callback=self._mic_callback
                )
                self.input_stream.start()
            except Exception as e:
                print(f"[Audio] Microphone input init warning: {e}")

            print("[Audio] Voice communication engine started (16kHz mono).")
        except Exception as e:
            print(f"[Audio] SoundDevice unavailable: {e}")

    def stop(self):
        """Stop audio streams."""
        self.running = False
        if self.input_stream:
            try:
                self.input_stream.stop()
                self.input_stream.close()
            except Exception:
                pass
            self.input_stream = None

        if self.output_stream:
            try:
                self.output_stream.stop()
                self.output_stream.close()
            except Exception:
                pass
            self.output_stream = None

        while not self.play_queue.empty():
            try:
                self.play_queue.get_nowait()
            except Exception:
                break
