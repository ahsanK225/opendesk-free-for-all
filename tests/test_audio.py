import unittest
import base64
import sys
import os
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from opendesk.host.audio import AudioEngine, SAMPLE_RATE, BLOCK_SIZE
from opendesk.common.protocol import MessageType, create_packet, parse_packet

class TestAudioEngine(unittest.TestCase):
    def test_audio_engine_packet_creation(self):
        # Generate dummy 100ms 16kHz sine wave audio
        t = np.linspace(0, 0.1, BLOCK_SIZE, endpoint=False)
        waveform = (np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16)
        raw_bytes = waveform.tobytes()
        b64_data = base64.b64encode(raw_bytes).decode("ascii")

        # Test packet serialization
        pkt_str = create_packet(MessageType.AUDIO_CHUNK, {"data": b64_data})
        parsed = parse_packet(pkt_str)
        
        self.assertEqual(parsed["type"], MessageType.AUDIO_CHUNK)
        self.assertIn("data", parsed["payload"])

        # Decode back and verify size
        decoded_bytes = base64.b64decode(parsed["payload"]["data"])
        self.assertEqual(len(decoded_bytes), len(raw_bytes))
        decoded_arr = np.frombuffer(decoded_bytes, dtype=np.int16)
        np.testing.assert_array_equal(waveform, decoded_arr)

    def test_audio_engine_play_queue(self):
        received_chunks = []
        def on_mic(chunk):
            received_chunks.append(chunk)

        engine = AudioEngine(on_mic_chunk_callback=on_mic)
        
        dummy_audio = np.zeros(BLOCK_SIZE, dtype=np.int16).tobytes()
        b64_audio = base64.b64encode(dummy_audio).decode("ascii")

        engine.play_chunk(b64_audio)
        self.assertEqual(engine.play_queue.qsize(), 1)
        
        queued = engine.play_queue.get_nowait()
        self.assertEqual(queued, dummy_audio)

    def test_audio_engine_jitter_purge(self):
        engine = AudioEngine()
        dummy_audio = np.zeros(BLOCK_SIZE, dtype=np.int16).tobytes()
        b64_audio = base64.b64encode(dummy_audio).decode("ascii")

        # Simulate burst of 10 incoming chunks
        for _ in range(10):
            engine.play_chunk(b64_audio)

        # Queue should be capped at <= 3 chunks to prevent VoIP lag
        self.assertLessEqual(engine.play_queue.qsize(), 3)

    def test_audio_control_mute(self):
        engine = AudioEngine()
        self.assertTrue(engine.mic_enabled)
        engine.mic_enabled = False
        self.assertFalse(engine.mic_enabled)

    def test_available_audio_devices(self):
        from opendesk.host.audio import get_available_audio_devices, find_best_input_device_id
        devs = get_available_audio_devices()
        self.assertIn("inputs", devs)
        self.assertIn("outputs", devs)
        self.assertIsInstance(devs["inputs"], list)
        self.assertIsInstance(devs["outputs"], list)

    def test_audio_digital_gain_and_level_callback(self):
        levels = []
        def on_level(lvl):
            levels.append(lvl)

        engine = AudioEngine(on_mic_level_callback=on_level)
        engine.running = True
        engine.set_gain(1.5)
        self.assertEqual(engine.mic_gain, 1.5)

        # Feed synthetic audio into mic callback
        indata = np.full((400, 1), 10000, dtype=np.int16)
        engine._mic_callback(indata, 400, None, None)
        self.assertGreater(len(levels), 0)
        self.assertGreater(levels[0], 0.0)

    def test_continuous_playback_ring_buffer(self):
        engine = AudioEngine()
        engine.running = True
        engine.speaker_enabled = True
        
        # Ingest 16kHz audio chunk
        test_audio = np.full(400, 5000, dtype=np.int16).tobytes()
        b64_audio = base64.b64encode(test_audio).decode("ascii")
        engine.play_chunk(b64_audio)
        
        # Pull frames via speaker callback
        outdata = np.zeros((200, 2), dtype=np.int16)
        engine._speaker_callback(outdata, 200, None, None)
        # Verify samples were rendered to output channels
        self.assertFalse(np.all(outdata == 0))

    def test_discord_vad_sensitivity_cutoff(self):
        chunks = []
        engine = AudioEngine(on_mic_chunk_callback=lambda c: chunks.append(c))
        engine.running = True
        engine.input_mode = "voice_activity"
        engine.auto_sensitivity = False
        engine.vad_sensitivity = 0.50  # Moderate threshold

        # 1. Feed quiet background noise / whisper below threshold
        whisper = np.full((400, 1), 200, dtype=np.int16)
        engine._mic_callback(whisper, 400, None, None)
        self.assertEqual(len(chunks), 0, "Quiet audio below threshold should be muted by VAD")

        # 2. Feed clear voice above threshold
        speech = np.full((400, 1), 8000, dtype=np.int16)
        engine._mic_callback(speech, 400, None, None)
        self.assertGreater(len(chunks), 0, "Voice above threshold should be transmitted")

    def test_discord_push_to_talk(self):
        chunks = []
        engine = AudioEngine(on_mic_chunk_callback=lambda c: chunks.append(c))
        engine.running = True
        engine.input_mode = "push_to_talk"
        engine.push_to_talk_active = False

        speech = np.full((400, 1), 8000, dtype=np.int16)
        
        # When PTT is not held down:
        engine._mic_callback(speech, 400, None, None)
        self.assertEqual(len(chunks), 0, "Audio should not transmit when PTT key is released")

        # When PTT key is held down:
        engine.set_push_to_talk(True)
        engine._mic_callback(speech, 400, None, None)
        self.assertEqual(len(chunks), 1, "Audio should transmit when PTT key is pressed")

    def test_discord_loopback_mic_test(self):
        engine = AudioEngine()
        engine.running = True
        engine.start_loopback_test()
        self.assertTrue(engine.loopback_test_active)

        # Feed mic audio
        speech = np.full((400, 1), 7000, dtype=np.int16)
        engine._mic_callback(speech, 400, None, None)

        # Check that loopback routed audio into play_samples for self-hearing
        with engine.play_lock:
            self.assertGreater(len(engine.play_samples), 0)

        # Stop test
        engine.stop_loopback_test()
        self.assertFalse(engine.loopback_test_active)
        with engine.play_lock:
            self.assertEqual(len(engine.play_samples), 0)

    def test_speaker_callback_mono_1d_safe(self):
        engine = AudioEngine()
        engine.running = True
        engine.speaker_enabled = True

        # Ingest audio chunk
        test_audio = np.full(400, 5000, dtype=np.int16).tobytes()
        engine.play_chunk(base64.b64encode(test_audio).decode("ascii"))

        # 1D buffer (mono PortAudio output device)
        outdata_1d = np.zeros(200, dtype=np.int16)
        # Should execute safely without IndexError or crashing
        try:
            engine._speaker_callback(outdata_1d, 200, None, None)
            success = True
        except Exception:
            success = False
        self.assertTrue(success, "1D PortAudio mono buffer must not raise IndexError")

    def test_thread_safe_image_lock_concurrency(self):
        import threading
        from PIL import Image

        image_lock = threading.Lock()
        base_img = Image.new("RGB", (640, 480), (100, 100, 100))
        tile = Image.new("RGB", (64, 64), (200, 50, 50))
        crashed = [False]

        def writer_thread():
            for i in range(50):
                try:
                    with image_lock:
                        base_img.paste(tile, (10, 10))
                except Exception:
                    crashed[0] = True

        def reader_thread():
            for i in range(50):
                try:
                    with image_lock:
                        _ = base_img.resize((320, 240), Image.Resampling.NEAREST)
                except Exception:
                    crashed[0] = True

        t1 = threading.Thread(target=writer_thread)
        t2 = threading.Thread(target=reader_thread)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertFalse(crashed[0], "Concurrent paste and resize guarded by image_lock must not raise exception")

if __name__ == "__main__":
    unittest.main()
