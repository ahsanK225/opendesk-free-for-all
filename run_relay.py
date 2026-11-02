#!/usr/bin/env python3
"""
OpenDesk Relay & Web Server Launcher
"""

import sys
import os
import argparse

# Add parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from relay.server import RelayServer

def main():
    parser = argparse.ArgumentParser(description="OpenDesk Signaling & Relay Server")
    parser.add_argument("--host", default="127.0.0.1", help="Binding IP address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on (default: 8080)")
    parser.add_argument("--host-token", default=os.environ.get("OPENDESK_HOST_TOKEN", ""), help="Required shared secret for host registration")
    args = parser.parse_args()
    if not args.host_token:
        parser.error("Set OPENDESK_HOST_TOKEN or --host-token before starting a relay")

    server = RelayServer(host=args.host, port=args.port, host_token=args.host_token)
    print("=" * 60)
    print(f"  OPENDESK SIGNALING & RELAY SERVER RUNNING")
    print(f"  Web Client: http://localhost:{args.port}")
    print(f"  WebSocket:  ws://localhost:{args.port}/ws")
    print("=" * 60)
    server.run()

if __name__ == "__main__":
    main()
