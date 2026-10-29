"""
OpenDesk Signaling & Fallback Relay Server
Provides:
- Unique 9-digit AnyDesk-style ID registration
- WebRTC P2P Signaling (SDP Offer/Answer & ICE candidate exchange)
- High-Throughput Fallback Relay (tunnels video, input, file & clipboard if P2P fails)
- Built-in HTTP server delivering the responsive Web Client
"""

import os
import sys
import json
import random
import asyncio
from typing import Dict, Any, Optional
from aiohttp import web, WSMsgType

class RelayServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 8080, web_dir: Optional[str] = None):
        self.host = host
        self.port = port
        
        if web_dir:
            self.web_dir = web_dir
        elif hasattr(sys, "_MEIPASS"):
            candidate1 = os.path.join(sys._MEIPASS, "opendesk", "web")
            candidate2 = os.path.join(sys._MEIPASS, "web")
            self.web_dir = candidate1 if os.path.exists(candidate1) else candidate2
        else:
            self.web_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "web"))
        
        # Mapping: peer_id -> WebSocketResponse
        self.peers: Dict[str, web.WebSocketResponse] = {}
        # Mapping: peer_id -> metadata { "role": "host"|"client", "target_id": ..., "auth": ... }
        self.peer_meta: Dict[str, Dict[str, Any]] = {}
        # Mapping: host_id -> client_id (active sessions)
        self.sessions: Dict[str, str] = {}

    def _generate_id(self) -> str:
        """Generate a random 9-digit AnyDesk-style ID."""
        while True:
            candidate = f"{random.randint(100, 999)} {random.randint(100, 999)} {random.randint(100, 999)}"
            clean = candidate.replace(" ", "")
            if clean not in self.peers:
                return candidate

    async def handle_ws(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(max_msg_size=16 * 1024 * 1024)
        await ws.prepare(request)
        peer_id: Optional[str] = None

        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        packet = json.loads(msg.data)
                    except Exception:
                        continue
                        
                    mtype = packet.get("type")
                    payload = packet.get("payload", {})

                    # --- Registration ---
                    if mtype == "register":
                        role = payload.get("role", "host") # "host" or "client"
                        requested_id = payload.get("id")
                        password = payload.get("password", "")
                        
                        if not requested_id:
                            assigned_id = self._generate_id()
                        else:
                            assigned_id = requested_id
                            
                        clean_id = assigned_id.replace(" ", "")
                        peer_id = clean_id
                        self.peers[peer_id] = ws
                        self.peer_meta[peer_id] = {
                            "display_id": assigned_id,
                            "role": role,
                            "password": password
                        }

                        await ws.send_str(json.dumps({
                            "type": "register_resp",
                            "payload": {
                                "status": "ok",
                                "id": assigned_id,
                                "clean_id": clean_id,
                                "role": role
                            }
                        }))

                    # --- Connection Request (Client -> Relay -> Host) ---
                    elif mtype == "connect":
                        raw_target = str(payload.get("target_id", ""))
                        target_id = raw_target.replace(" ", "").replace("-", "").strip()
                        password = payload.get("password", "")
                        
                        target_ws = self.peers.get(target_id)
                        target_meta = self.peer_meta.get(target_id)
                        
                        if not target_ws or target_ws.closed or not target_meta:
                            print(f"[Relay] Connect failed: target '{target_id}' not found. Active peers: {list(self.peers.keys())}")
                            await ws.send_str(json.dumps({
                                "type": "connect_resp",
                                "payload": {"status": "error", "message": f"Host [{raw_target}] is offline or ID not found. Ensure the desktop OpenDesk app is running."}
                            }))
                            continue

                        # Verify password if host explicitly configured one
                        expected_pw = target_meta.get("password")
                        if expected_pw and expected_pw.strip() and expected_pw != password:
                            await ws.send_str(json.dumps({
                                "type": "connect_resp",
                                "payload": {"status": "error", "message": "Invalid password."}
                            }))
                            continue

                        # Pair session
                        self.sessions[target_id] = peer_id
                        self.sessions[peer_id] = target_id

                        # Notify Host of new client
                        await target_ws.send_str(json.dumps({
                            "type": "session_start",
                            "payload": {
                                "client_id": peer_id,
                                "display_id": self.peer_meta[peer_id]["display_id"]
                            }
                        }))

                        # Notify Client of successful pairing
                        await ws.send_str(json.dumps({
                            "type": "connect_resp",
                            "payload": {
                                "status": "ok",
                                "target_id": target_id,
                                "message": "Connected to host. Initiating stream."
                            }
                        }))

                    # --- P2P WebRTC Signaling (Offer / Answer / Candidate) ---
                    elif mtype == "p2p_signal":
                        target = self.sessions.get(peer_id)
                        if target and target in self.peers:
                            await self.peers[target].send_str(json.dumps({
                                "type": "p2p_signal",
                                "payload": payload
                            }))

                    # --- Transparent Relay Fallback (Video, Input, File, Clipboard) ---
                    else:
                        target = self.sessions.get(peer_id)
                        if target and target in self.peers and not self.peers[target].closed:
                            await self.peers[target].send_str(msg.data)

                elif msg.type == WSMsgType.ERROR:
                    break

        finally:
            if peer_id:
                partner = self.sessions.pop(peer_id, None)
                if partner:
                    self.sessions.pop(partner, None)
                    if partner in self.peers and not self.peers[partner].closed:
                        await self.peers[partner].send_str(json.dumps({
                            "type": "session_end",
                            "payload": {"message": "Remote peer disconnected."}
                        }))
                self.peers.pop(peer_id, None)
                self.peer_meta.pop(peer_id, None)

        return ws

    def create_app(self) -> web.Application:
        app = web.Application()
        app.router.add_get("/ws", self.handle_ws)
        
        # Serve web client
        if os.path.exists(self.web_dir):
            index_path = os.path.join(self.web_dir, "index.html")
            if os.path.isfile(index_path):
                async def handle_index(request):
                    return web.FileResponse(index_path)
                app.router.add_get("/", handle_index)
            app.router.add_static("/", path=self.web_dir, name="web", show_index=False)
            
        return app

    def run(self):
        app = self.create_app()
        web.run_app(app, host=self.host, port=self.port)

if __name__ == "__main__":
    server = RelayServer()
    print(f"Starting OpenDesk Relay & Web Server on http://0.0.0.0:8080 ...")
    server.run()
