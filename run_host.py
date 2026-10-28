#!/usr/bin/env python3
"""
OpenDesk Host Desktop Agent Launcher
"""

import sys
import os
import asyncio
import argparse

# Add parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from opendesk.host.agent import HostAgent

def main():
    parser = argparse.ArgumentParser(description="OpenDesk Host Desktop Agent")
    parser.add_argument("--relay", default="ws://localhost:8080/ws", help="Relay server WebSocket URL")
    parser.add_argument("--id", default=None, help="Custom 9-digit ID (e.g. 123 456 789)")
    parser.add_argument("--password", default="", help="Optional session password")
    args = parser.parse_args()

    agent = HostAgent(relay_url=args.relay, host_id=args.id, password=args.password)
    try:
        asyncio.run(agent.start())
    except KeyboardInterrupt:
        print("\nStopping OpenDesk Host Agent...")
        agent.stop()

if __name__ == "__main__":
    main()
