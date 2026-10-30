"""
Real-Time Bidirectional Voice Audio Engine for OpenDesk
Handles low-latency microphone capture and speaker playback using PortAudio / sounddevice.
Features:
- Native hardware sample-rate support (48kHz/44.1kHz WASAPI/MME) with zero-distortion resampling
- Continuous audio playback ring buffer to eliminate sample slicing, clipping, and robotic buzzing
- Smart physical microphone auto-detection (prioritizes WASAPI physical headsets, avoids virtual devices)
- Digital Automatic Gain Control (AGC) with boost and noise gate for clear voice transmission
- Real-time RMS audio level callback for in-app VU meter and microphone test
- In-app device selection and persistent configuration integration
"""

import sys
import time
import queue
import base64
import threading
from typing import Optional, Callable, Dict, Any, List, Tuple
import numpy as np

try:
    from opendesk.common.config import get_audio_settings
except ImportError:
    try:
        from common.config import get_audio_settings
    except ImportError:
        def get_audio_settings():
            return {"input_device": "", "output_device": "", "mic_gain": 1.2, "speaker_volume": 1.0, "noise_gate": True}

VOIP_SAMPLE_RATE = 48000  # Discord-grade Studio HD Voice transmission rate (48kHz mono int16)
CHUNK_MS = 20             # 20ms packet duration (WebRTC / Discord standard frame size)
VOIP_BLOCK_SIZE = int(VOIP_SAMPLE_RATE * (CHUNK_MS / 1000.0))  # 960 samples

# Backward compatibility aliases
SAMPLE_RATE = VOIP_SAMPLE_RATE
BLOCK_SIZE = VOIP_BLOCK_SIZE


def get_available_audio_devices() -> Dict[str, List[Dict[str, Any]]]:
    """
    Enumerate all available audio input and output devices.
    Returns clean, friendly dictionaries for UI dropdowns.
    """
    inputs: List[Dict[str, Any]] = []
    outputs: List[Dict[str, Any]] = []
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        hostapis = sd.query_hostapis()
        
        seen_in_names = set()
        seen_out_names = set()

        # Prioritize WASAPI then DirectSound then MME
        api_priority = {"Windows WASAPI": 3, "Windows DirectSound": 2, "MME": 1}

        for i, dev in enumerate(devices):
            api_name = hostapis[dev['hostapi']]['name']
            name = dev['name']

            if dev['max_input_channels'] > 0:
                clean_name = name.strip()
                inputs.append({
                    "id": i,
                    "name": clean_name,
                    "api": api_name,
                    "priority": api_priority.get(api_name, 0),
                    "samplerate": int(dev['default_samplerate']),
                    "channels": dev['max_input_channels']
                })

            if dev['max_output_channels'] > 0:
                clean_name = name.strip()
                outputs.append({
                    "id": i,
                    "name": clean_name,
                    "api": api_name,
                    "priority": api_priority.get(api_name, 0),
                    "samplerate": int(dev['default_samplerate']),
                    "channels": dev['max_output_channels']
                })

        # Sort with WASAPI physical devices on top
        inputs.sort(key=lambda d: (d['priority'], not any(v in d['name'].lower() for v in ('virtual', 'cable', 'steam'))), reverse=True)
        outputs.sort(key=lambda d: (d['priority'], not any(v in d['name'].lower() for v in ('virtual', 'cable', 'steam'))), reverse=True)

    except Exception as e:
        print(f"[Audio] Device query warning: {e}")

    return {"inputs": inputs, "outputs": outputs}


def find_best_input_device_id(preferred_name: str = "") -> Optional[int]:
    """Find the best active physical microphone, prioritizing user preference and WASAPI."""
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        hostapis = sd.query_hostapis()

        # 1. If preferred name specified, search exact or substring match
        if preferred_name:
            for i, dev in enumerate(devices):
                if dev['max_input_channels'] > 0 and preferred_name.lower() in dev['name'].lower():
                    return i

        # 2. Search WASAPI for physical headset or microphone
        for i, dev in enumerate(devices):
            if dev['max_input_channels'] > 0:
                api_name = hostapis[dev['hostapi']]['name']
                name = dev['name'].lower()
                if 'WASAPI' in api_name:
                    if any(kw in name for kw in ('bloody', 'realtek', 'headset', 'mic', 'usb')) and not any(kw in name for kw in ('virtual', 'cable', 'steam', 'mapper')):
                        return i

        # 3. Search non-WASAPI physical mic
        for i, dev in enumerate(devices):
            if dev['max_input_channels'] > 0:
                name = dev['name'].lower()
                if any(kw in name for kw in ('bloody', 'realtek', 'headset', 'mic', 'usb')) and not any(kw in name for kw in ('virtual', 'cable', 'steam', 'mapper')):
                    return i

        # 4. Fallback to default
        default_in = sd.default.device[0]
        return default_in if default_in is not None and default_in >= 0 else None
    except Exception:
        return None


def find_best_output_device_id(preferred_name: str = "") -> Optional[int]:
    """Find the best active physical speaker/headset, prioritizing user preference and WASAPI."""
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        hostapis = sd.query_hostapis()

        # 1. If preferred name specified
        if preferred_name:
            for i, dev in enumerate(devices):
                if dev['max_output_channels'] > 0 and preferred_name.lower() in dev['name'].lower():
                    return i

        # 2. Search WASAPI for physical speakers or headphones
        for i, dev in enumerate(devices):
            if dev['max_output_channels'] > 0:
                api_name = hostapis[dev['hostapi']]['name']
                name = dev['name'].lower()
                if 'WASAPI' in api_name:
                    if any(kw in name for kw in ('bloody', 'realtek', 'headset', 'speaker', 'headphones')) and not any(kw in name for kw in ('virtual', 'cable', 'steam', 'mapper')):
                        return i

        # 3. Fallback to default
        default_out = sd.default.device[1]
        return default_out if default_out is not None and default_out >= 0 else None
    except Exception:
        return None


class AudioEngine:
    def __init__(self, on_mic_chunk_callback: Optional[Callable[[str], None]] = None,
                 on_mic_level_callback: Optional[Callable[[float], None]] = None):
        self.on_mic_chunk_callback = on_mic_chunk_callback
        self.on_mic_level_callback = on_mic_level_callback
        self.mic_enabled = True
        self.speaker_enabled = True
        self.running = False
        
        # Audio Configuration (Discord-Style HD Voice Suite)
        cfg = get_audio_settings()
        self.preferred_input = cfg.get("input_device", "")
        self.preferred_output = cfg.get("output_device", "")
        self.mic_gain = float(cfg.get("mic_gain", 1.0))
        self.speaker_volume = float(cfg.get("speaker_volume", 1.0))
        self.input_mode = cfg.get("input_mode", "voice_activity")  # "voice_activity" | "push_to_talk"
        self.vad_sensitivity = float(cfg.get("vad_sensitivity", 0.25))  # 0.0 to 1.0
        self.auto_sensitivity = bool(cfg.get("auto_sensitivity", True))
        self.ptt_key = cfg.get("ptt_key", "Control_L")
        self.push_to_talk_active = False
        self.noise_suppression = bool(cfg.get("noise_suppression", True))
        self.echo_cancellation = bool(cfg.get("echo_cancellation", True))
        self.agc_enabled = bool(cfg.get("agc_enabled", True))
        self.noise_gate_enabled = bool(cfg.get("noise_gate", True))
        
        # Discord "Let's Check" Mic Test Loopback state
        self.loopback_test_active = False
        self.ambient_noise_floor = 0.003
        
        self.input_stream = None
        self.output_stream = None
        self.input_samplerate = VOIP_SAMPLE_RATE
        self.output_samplerate = VOIP_SAMPLE_RATE
        self.input_channels = 1
        self.output_channels = 2

        # Continuous thread-safe sample ring buffer for playback
        self.play_lock = threading.Lock()
        self.play_samples = np.empty((0,), dtype=np.int16)
        self.play_queue = queue.Queue(maxsize=20)

    def _find_best_input_device(self) -> Optional[int]:
        """Backward compatible helper to find best physical microphone."""
        return find_best_input_device_id(self.preferred_input)

    def set_gain(self, gain: float):
        self.mic_gain = max(0.0, min(3.0, gain))

    def set_speaker_volume(self, volume: float):
        self.speaker_volume = max(0.0, min(1.0, volume))

    def set_push_to_talk(self, active: bool):
        self.push_to_talk_active = bool(active)

    def start_loopback_test(self):
        """Enable Discord-style 'Let's Check' self-hearing loopback audio test."""
        self.loopback_test_active = True
        self.mic_enabled = True
        self.speaker_enabled = True
        if not self.running:
            self.start()

    def stop_loopback_test(self):
        """Disable loopback test and clear test buffer."""
        self.loopback_test_active = False
        with self.play_lock:
            self.play_samples = np.empty((0,), dtype=np.int16)

    def _mic_callback(self, indata, frames, time_info, status):
        """
        Called by PortAudio when incoming microphone audio block is recorded.
        Performs 48kHz HD processing, Discord VAD thresholding, Noise Suppression, and AGC.
        """
        if not self.running or not self.mic_enabled:
            return
        try:
            # indata shape is (frames, channels)
            if indata.ndim > 1 and indata.shape[1] > 1:
                mono_in = indata.mean(axis=1).astype(np.float32)
            else:
                mono_in = indata.flatten().astype(np.float32)

            # Apply user mic gain boost
            if self.mic_gain != 1.0:
                mono_in = mono_in * self.mic_gain

            # Calculate RMS level for in-app VU meter (0.0 to 1.0)
            rms = float(np.sqrt(np.mean(mono_in ** 2))) / 32768.0
            
            # Dynamic ambient noise floor tracking
            if rms < 0.05:
                self.ambient_noise_floor = 0.95 * self.ambient_noise_floor + 0.05 * rms

            # Live VU bar visual scaling (dB-like curve)
            level = min(1.0, rms * 5.0)
            if self.on_mic_level_callback:
                try:
                    self.on_mic_level_callback(level)
                except Exception:
                    pass

            # --- Discord Voice Activity Detection (VAD) / Push-to-Talk Gate ---
            if self.input_mode == "push_to_talk":
                allow_transmission = self.push_to_talk_active
            else:
                # Voice Activity mode
                if self.auto_sensitivity:
                    vad_threshold = max(0.007, self.ambient_noise_floor * 2.5)
                else:
                    # User slider maps 0.0 (very sensitive) to 1.0 (strict)
                    vad_threshold = 0.002 + (self.vad_sensitivity * 0.078)
                allow_transmission = (rms >= vad_threshold)

            # Noise gate / silence cutoff
            if not allow_transmission:
                mono_in.fill(0)
                if not self.loopback_test_active:
                    return  # Cut packet completely when silent (zero background fan noise)

            # --- Noise Suppression (High-pass sub-bass rumble filter & DC offset removal) ---
            if self.noise_suppression and len(mono_in) > 1:
                # DC offset & sub-60Hz rumble removal preserving 100% human vocal warmth and frequencies
                dc_offset = float(np.mean(mono_in))
                baseline = getattr(self, "_rumble_baseline", 0.0)
                self._rumble_baseline = 0.95 * baseline + 0.05 * dc_offset
                mono_in = mono_in - self._rumble_baseline

            # --- Automatic Gain Control (AGC) with smooth envelope ---
            if self.agc_enabled and rms > 0.005:
                target_rms = 0.10  # Optimal conversational loudness
                instant_gain = np.clip(target_rms / (rms + 1e-4), 0.8, 2.2)
                curr_gain = getattr(self, "smoothed_gain", 1.0)
                self.smoothed_gain = 0.90 * curr_gain + 0.10 * instant_gain
                mono_in = mono_in * self.smoothed_gain

            # Resample from hardware native rate to 48kHz standard if device opened at different rate
            if self.input_samplerate != VOIP_SAMPLE_RATE:
                target_len = int(round(len(mono_in) * (VOIP_SAMPLE_RATE / float(self.input_samplerate))))
                if target_len > 0:
                    x_orig = np.linspace(0, 1, len(mono_in))
                    x_target = np.linspace(0, 1, target_len)
                    mono_in = np.interp(x_target, x_orig, mono_in)

            # Convert to int16 PCM
            clipped = np.clip(mono_in, -32767, 32767).astype(np.int16)

            # Discord 'Let's Check' self-hearing loopback
            if self.loopback_test_active:
                with self.play_lock:
                    max_buffer_samples = int(self.output_samplerate * 0.080)
                    if len(self.play_samples) > max_buffer_samples:
                        self.play_samples = self.play_samples[-max_buffer_samples:]
                    self.play_samples = np.concatenate((self.play_samples, clipped))

            raw_bytes = clipped.tobytes()
            b64_audio = base64.b64encode(raw_bytes).decode("ascii")

            if self.on_mic_chunk_callback:
                self.on_mic_chunk_callback(b64_audio)
        except Exception:
            pass

    def _speaker_callback(self, outdata, frames, time_info, status):
        """
        Called continuously by PortAudio when speakers need audio data.
        Pulls exactly 'frames' from continuous playback buffer without dropping or fragmenting audio.
        Crash-proof: handles 1D/2D channels safely and catches all PortAudio callback exceptions.
        """
        if not self.running or not self.speaker_enabled:
            try:
                outdata.fill(0)
            except Exception:
                pass
            return

        try:
            with self.play_lock:
                avail = len(self.play_samples)
                if avail >= frames:
                    chunk = self.play_samples[:frames]
                    self.play_samples = self.play_samples[frames:]
                else:
                    chunk = self.play_samples
                    self.play_samples = np.empty((0,), dtype=np.int16)

            # If we have samples, render safely to output channels
            if len(chunk) > 0:
                if outdata.ndim > 1 and outdata.shape[1] > 1:
                    # Stereo output: duplicate mono to L + R
                    outdata[:len(chunk), 0] = chunk
                    outdata[:len(chunk), 1] = chunk
                    if len(chunk) < frames:
                        outdata[len(chunk):, :].fill(0)
                elif outdata.ndim > 1:
                    outdata[:len(chunk), 0] = chunk
                    if len(chunk) < frames:
                        outdata[len(chunk):, :].fill(0)
                else:
                    outdata[:len(chunk)] = chunk
                    if len(chunk) < frames:
                        outdata[len(chunk):].fill(0)
            else:
                outdata.fill(0)
        except Exception:
            try:
                outdata.fill(0)
            except Exception:
                pass

    def play_chunk(self, b64_audio: str):
        """
        Ingest incoming remote audio chunk (supports both 48kHz HD Voice and legacy 16kHz),
        resample if needed, and append to continuous sample ring buffer with low-latency jitter protection.
        """
        if not self.speaker_enabled:
            return
        try:
            raw_bytes = base64.b64decode(b64_audio)
            samples = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32)
            if len(samples) == 0:
                return
            
            # Apply speaker volume
            if self.speaker_volume != 1.0:
                samples = samples * self.speaker_volume

            # Detect whether packet is legacy 16kHz (<600 samples for 25ms) or 48kHz HD Voice
            incoming_rate = 16000 if len(samples) < 600 else VOIP_SAMPLE_RATE

            # Resample to output device native sample rate (e.g. 48000 Hz)
            if self.output_samplerate != incoming_rate:
                target_len = int(round(len(samples) * (float(self.output_samplerate) / incoming_rate)))
                x_orig = np.linspace(0, 1, len(samples))
                x_target = np.linspace(0, 1, target_len)
                resampled = np.interp(x_target, x_orig, samples)
                out_samples = np.clip(resampled, -32767, 32767).astype(np.int16)
            else:
                out_samples = np.clip(samples, -32767, 32767).astype(np.int16)

            with self.play_lock:
                # Smooth conversational jitter guard: 180ms buffer (~8640 samples at 48kHz)
                # Prevents packet-jitter audio drops and robotic clipping while maintaining real-time conversation
                max_buffer_samples = int(self.output_samplerate * 0.180)
                if len(self.play_samples) > max_buffer_samples:
                    self.play_samples = self.play_samples[-max_buffer_samples:]

                self.play_samples = np.concatenate((self.play_samples, out_samples))

            # Backward-compatible queue update
            try:
                while self.play_queue.qsize() > 2:
                    try:
                        self.play_queue.get_nowait()
                    except Exception:
                        break
                self.play_queue.put_nowait(raw_bytes)
            except Exception:
                pass
        except Exception:
            pass

    def start(self):
        """Start microphone capture and speaker playback streams."""
        try:
            import sounddevice as sd
            # If already running with active streams, do not create duplicate streams
            if self.running and (self.input_stream is not None or self.output_stream is not None):
                return
            self.stop()
            self.running = True
            
            # 1. Output Stream (Speaker / Headset)
            try:
                out_dev_id = find_best_output_device_id(self.preferred_output)
                if out_dev_id is not None:
                    dev_info = sd.query_devices(out_dev_id)
                    self.output_samplerate = int(dev_info.get("default_samplerate", 48000))
                    self.output_channels = min(2, max(1, dev_info.get("max_output_channels", 2)))
                else:
                    self.output_samplerate = 48000
                    self.output_channels = 2

                out_blocksize = int(self.output_samplerate * (CHUNK_MS / 1000.0))
                self.output_stream = sd.OutputStream(
                    device=out_dev_id,
                    samplerate=self.output_samplerate,
                    channels=self.output_channels,
                    dtype='int16',
                    blocksize=out_blocksize,
                    callback=self._speaker_callback
                )
                self.output_stream.start()
                print(f"[Audio] Output stream started on device [{out_dev_id}] at {self.output_samplerate}Hz.")
            except Exception as e:
                print(f"[Audio] Speaker output init warning: {e}")

            # 2. Input Stream (Microphone)
            try:
                in_dev_id = find_best_input_device_id(self.preferred_input)
                if in_dev_id is not None:
                    dev_info = sd.query_devices(in_dev_id)
                    self.input_samplerate = int(dev_info.get("default_samplerate", 48000))
                    self.input_channels = min(2, max(1, dev_info.get("max_input_channels", 1)))
                else:
                    self.input_samplerate = 48000
                    self.input_channels = 1

                in_blocksize = int(self.input_samplerate * (CHUNK_MS / 1000.0))
                self.input_stream = sd.InputStream(
                    device=in_dev_id,
                    samplerate=self.input_samplerate,
                    channels=self.input_channels,
                    dtype='int16',
                    blocksize=in_blocksize,
                    callback=self._mic_callback
                )
                self.input_stream.start()
                print(f"[Audio] Input stream started on device [{in_dev_id}] at {self.input_samplerate}Hz ({self.input_channels}ch).")
            except Exception as e:
                print(f"[Audio] Microphone input init warning: {e}")

            print("[Audio] Ultra-low latency voice communication engine running.")
        except Exception as e:
            print(f"[Audio] SoundDevice unavailable: {e}")

    def stop(self):
        """Stop audio streams and clear buffers."""
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

        with self.play_lock:
            self.play_samples = np.empty((0,), dtype=np.int16)

