#!/usr/bin/env python3
"""
OpenDesk Relay & Web Server Launcher
"""

import sys
import os
import argparse

# Add parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from opendesk.relay.server import RelayServer

def main():
    parser = argparse.ArgumentParser(description="OpenDesk Signaling & Relay Server")
    parser.add_argument("--host", default="0.0.0.0", help="Binding IP address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on (default: 8080)")
    args = parser.parse_args()

    server = RelayServer(host=args.host, port=args.port)
    print("=" * 60)
    print(f"  OPENDESK SIGNALING & RELAY SERVER RUNNING")
    print(f"  Web Client: http://localhost:{args.port}")
    print(f"  WebSocket:  ws://localhost:{args.port}/ws")
    print("=" * 60)
    server.run()

if __name__ == "__main__":
    main()
