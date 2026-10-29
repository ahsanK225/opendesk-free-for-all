import os
import sys
import unittest
import base64
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from common.rendezvous import (
    publish_host_rendezvous,
    resolve_host_rendezvous,
    parse_connect_target,
    RendezvousHeartbeat
)

class TestRendezvous(unittest.TestCase):
    def test_parse_connect_target(self):
        # 9-digit space-separated ID
        tid, ws = parse_connect_target("732 364 935")
        self.assertEqual(tid, "732364935")
        self.assertIsNone(ws)

        # 9-digit hyphen-separated ID
        tid, ws = parse_connect_target("732-364-935")
        self.assertEqual(tid, "732364935")
        self.assertIsNone(ws)

        # Direct Cloudflare Tunnel URL
        tid, ws = parse_connect_target("https://super-cool-tunnel.trycloudflare.com")
        self.assertEqual(tid, "remote_host")
        self.assertEqual(ws, "wss://super-cool-tunnel.trycloudflare.com/ws")

        # Target ID with host
        tid, ws = parse_connect_target("732364935@super-cool-tunnel.trycloudflare.com")
        self.assertEqual(tid, "732364935")
        self.assertEqual(ws, "wss://super-cool-tunnel.trycloudflare.com/ws")

    @patch("urllib.request.urlopen")
    def test_publish_and_resolve_mock(self, mock_urlopen):
        # Mock publish
        mock_resp_pub = MagicMock()
        mock_resp_pub.status = 200
        mock_resp_pub.__enter__.return_value = mock_resp_pub
        mock_urlopen.return_value = mock_resp_pub

        pub_ok = publish_host_rendezvous("732 364 935", "https://friendly-host.trycloudflare.com")
        self.assertTrue(pub_ok)

        # Mock resolve
        encoded_val = base64.b64encode(b"https://friendly-host.trycloudflare.com").decode().replace("=", "").replace("/", "-")
        mock_resp_res = MagicMock()
        mock_resp_res.read.return_value = f'"{encoded_val}"'.encode()
        mock_resp_res.__enter__.return_value = mock_resp_res
        mock_urlopen.return_value = mock_resp_res

        found_url = resolve_host_rendezvous("732 364 935")
        self.assertEqual(found_url, "https://friendly-host.trycloudflare.com")

    @patch("urllib.request.urlopen")
    def test_resolve_not_found(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'null'
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        res = resolve_host_rendezvous("000000000")
        self.assertIsNone(res)

    def test_heartbeat_lifecycle(self):
        call_count = 0
        def dummy_getter():
            nonlocal call_count
            call_count += 1
            return "123456789"

        hb = RendezvousHeartbeat(dummy_getter, lambda: "https://test.trycloudflare.com", interval=0.1)
        hb.start()
        self.assertTrue(hb.running)
        hb.stop()
        self.assertFalse(hb.running)

if __name__ == "__main__":
    unittest.main()
