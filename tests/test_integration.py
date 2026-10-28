"""
Integration Tests for OpenDesk
Spins up the Relay server and tests Host registration,
Client session pairing, video packet relay, input handling, and clipboard sync.
"""

import unittest
import asyncio
import json
import threading
import time
import sys
import os
import aiohttp
from aiohttp import web

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from opendesk.relay.server import RelayServer
from opendesk.common.protocol import MessageType, create_packet, parse_packet

TEST_PORT = 9876
TEST_URL = f"http://127.0.0.1:{TEST_PORT}/ws"

class TestOpenDeskIntegration(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        # Run relay server in background thread with its own event loop
        cls.server = RelayServer(host="127.0.0.1", port=TEST_PORT)
        cls.loop = asyncio.new_event_loop()
        
        def run_srv():
            asyncio.set_event_loop(cls.loop)
            app = cls.server.create_app()
            runner = web.AppRunner(app)
            cls.loop.run_until_complete(runner.setup())
            site = web.TCPSite(runner, "127.0.0.1", TEST_PORT)
            cls.loop.run_until_complete(site.start())
            cls.loop.run_forever()

        cls.thread = threading.Thread(target=run_srv, daemon=True)
        cls.thread.start()
        time.sleep(0.5)

    async def test_full_session_handshake_and_relay(self):
        async with aiohttp.ClientSession() as session:
            # 1. Host Connects & Registers
            async with session.ws_connect(TEST_URL) as host_ws:
                await host_ws.send_str(create_packet(MessageType.REGISTER, {
                    "role": "host",
                    "id": "111 222 333",
                    "password": "secret"
                }))
                host_resp_raw = await host_ws.receive_str()
                host_resp = parse_packet(host_resp_raw)
                self.assertEqual(host_resp["type"], MessageType.REGISTER_RESP)
                self.assertEqual(host_resp["payload"]["clean_id"], "111222333")

                # 2. Client Connects & Registers
                async with session.ws_connect(TEST_URL) as client_ws:
                    await client_ws.send_str(create_packet(MessageType.REGISTER, {
                        "role": "client"
                    }))
                    client_resp_raw = await client_ws.receive_str()
                    client_resp = parse_packet(client_resp_raw)
                    self.assertEqual(client_resp["type"], MessageType.REGISTER_RESP)

                    # 3. Client requests connection with wrong password -> should fail
                    await client_ws.send_str(create_packet(MessageType.CONNECT, {
                        "target_id": "111 222 333",
                        "password": "wrong_password"
                    }))
                    fail_resp_raw = await client_ws.receive_str()
                    fail_resp = parse_packet(fail_resp_raw)
                    self.assertEqual(fail_resp["payload"]["status"], "error")

                    # 4. Client requests connection with valid password -> should succeed
                    await client_ws.send_str(create_packet(MessageType.CONNECT, {
                        "target_id": "111 222 333",
                        "password": "secret"
                    }))
                    # Client receives connect_resp
                    succ_resp_raw = await client_ws.receive_str()
                    succ_resp = parse_packet(succ_resp_raw)
                    self.assertEqual(succ_resp["payload"]["status"], "ok")

                    # Host receives session_start
                    session_start_raw = await host_ws.receive_str()
                    session_start = parse_packet(session_start_raw)
                    self.assertEqual(session_start["type"], MessageType.SESSION_START)

                    # 5. Host sends DeskRT delta video frame -> Client receives it
                    sample_delta = {
                        "width": 1920,
                        "height": 1080,
                        "tiles": [{"x": 0, "y": 0, "w": 128, "h": 128, "image": "fakejpegbase64"}]
                    }
                    await host_ws.send_str(create_packet(MessageType.VIDEO_DELTA, sample_delta))
                    video_recv_raw = await client_ws.receive_str()
                    video_recv = parse_packet(video_recv_raw)
                    self.assertEqual(video_recv["type"], MessageType.VIDEO_DELTA)
                    self.assertEqual(video_recv["payload"]["width"], 1920)

                    # 6. Client sends remote input event -> Host receives it
                    await client_ws.send_str(create_packet(MessageType.INPUT_MOUSE_MOVE, {"x": 0.5, "y": 0.5}))
                    input_recv_raw = await host_ws.receive_str()
                    input_recv = parse_packet(input_recv_raw)
                    self.assertEqual(input_recv["type"], MessageType.INPUT_MOUSE_MOVE)
                    self.assertEqual(input_recv["payload"]["x"], 0.5)

                    # 7. Host sends clipboard sync -> Client receives it
                    await host_ws.send_str(create_packet(MessageType.CLIPBOARD_TEXT, {"text": "Copied from Host"}))
                    clip_recv_raw = await client_ws.receive_str()
                    clip_recv = parse_packet(clip_recv_raw)
                    self.assertEqual(clip_recv["type"], MessageType.CLIPBOARD_TEXT)
                    self.assertEqual(clip_recv["payload"]["text"], "Copied from Host")

if __name__ == "__main__":
    unittest.main()
