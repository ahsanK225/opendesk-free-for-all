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

if __name__ == "__main__":
    unittest.main()
