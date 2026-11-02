"""Local host relay with explicit request, approval and revocation states."""
import asyncio
import json
import os
import secrets
import sys
import time
from collections import defaultdict, deque
from aiohttp import web, WSMsgType
from common.security import verify_proof
from common.identity import device_key, sign_identity

PERMISSIONS = ('input', 'audio', 'clipboard', 'file_transfer')
INPUT = {'mouse_move', 'mouse_down', 'mouse_up', 'mouse_scroll', 'key_down', 'key_up', 'shortcut', 'input_reset'}
CLIENT_MESSAGES = INPUT | {'clipboard_text', 'audio_chunk', 'file_list_req', 'file_download_req',
                         'file_upload_start', 'file_chunk', 'video_config', 'video_ack', 'video_refresh'}
HOST_MESSAGES = {'clipboard_text', 'audio_chunk', 'video_full', 'video_delta', 'file_list_resp',
                 'file_upload_start', 'file_chunk', 'file_complete', 'file_error'}


class RelayServer:
    def __init__(self, host='127.0.0.1', port=8080, web_dir=None, host_token=None):
        self.host, self.port = host, port
        self.host_token = host_token or os.environ.get('OPENDESK_HOST_TOKEN', '')
        base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.dirname(__file__)))
        self.web_dir = web_dir or os.path.join(base, 'web')
        if not web_dir and not os.path.isdir(self.web_dir):
            self.web_dir = os.path.join(sys.prefix,'share','opendesk','web')
        self.peers, self.peer_meta, self.sessions = {}, {}, {}
        self.pending, self.challenges = {}, {}
        self.failures = defaultdict(deque)
        self.identity = device_key()
        self._connections = set()

    def _generate_id(self):
        while True:
            candidate = str(secrets.randbelow(900_000_000) + 100_000_000)
            if candidate not in self.peers:
                return candidate

    async def _send(self, peer, typ, **payload):
        ws = self.peers.get(peer)
        if ws is not None and not ws.closed:
            await ws.send_json({'type': typ, 'payload': payload})

    async def _end(self, peer, reason='Session disconnected.'):
        partner = self.sessions.pop(peer, None)
        if partner:
            self.sessions.pop(partner, None)
            for pid in (peer, partner):
                self.peer_meta.get(pid, {}).pop('permissions', None)
                self.peer_meta.get(pid, {}).pop('session_id', None)
                await self._send(pid, 'session_end', message=reason)
        for client, req in list(self.pending.items()):
            if client == peer or req['host'] == peer:
                self.pending.pop(client, None)
                await self._send(req['host'], 'request_cancelled', request_id=req['id'], client_id=client)
                await self._send(client, 'connect_resp', status='error', message=reason)
        self.challenges.pop(peer, None)

    async def _pair(self, host, client, permissions, request_id=None, unattended=False):
        if host in self.sessions or client in self.sessions:
            await self._send(client, 'connect_resp', status='error', message='Host or client is busy.')
            return
        session_id = secrets.token_urlsafe(24)
        perms = {key: bool(permissions.get(key, False)) for key in PERMISSIONS}
        self.sessions[host], self.sessions[client] = client, host
        for pid in (host, client):
            self.peer_meta[pid].update(permissions=perms, session_id=session_id)
        await self._send(host, 'session_start', client_id=client, session_id=session_id,
                         request_id=request_id, unattended=unattended, permissions=perms)
        await self._send(client, 'connect_resp', status='ok', target_id=host,
                         session_id=session_id, permissions=perms, protocol=2)

    def _allowed(self, peer, typ):
        meta = self.peer_meta[peer]
        allowed = HOST_MESSAGES if meta['role'] == 'host' else CLIENT_MESSAGES
        if typ not in allowed:
            return False
        perms = meta.get('permissions', {})
        gate = ('input' if typ in INPUT else 'audio' if typ.startswith('audio_') else
                'clipboard' if typ.startswith('clipboard_') else
                'file_transfer' if typ.startswith('file_') else None)
        return gate is None or perms.get(gate, False)

    async def handle_ws(self, request):
        from urllib.parse import urlsplit
        origin = request.headers.get('Origin')
        if origin and urlsplit(origin).netloc != request.host:
            raise web.HTTPForbidden(text='Cross-origin WebSocket denied')
        if len(self._connections) >= 64:
            raise web.HTTPServiceUnavailable(text='Connection limit reached')
        ws = web.WebSocketResponse(max_msg_size=8*1024*1024, heartbeat=20, compress=False)
        await ws.prepare(request)
        self._connections.add(ws)
        peer = None
        async def registration_deadline():
            await asyncio.sleep(10)
            if peer is None: await ws.close(code=1008,message=b'Registration timeout')
        deadline_task = asyncio.create_task(registration_deadline())
        recent_messages = deque()
        remote = request.remote or ''
        async def error(message):
            await ws.send_json({'type':'connect_resp', 'payload':{'status':'error', 'message':message}})
        try:
            async for msg in ws:
                now = time.monotonic()
                while recent_messages and now-recent_messages[0]>1: recent_messages.popleft()
                recent_messages.append(now)
                if len(recent_messages)>2000:
                    await ws.close(code=1008,message=b'Message rate exceeded')
                    break
                if msg.type == WSMsgType.BINARY:
                    if peer and peer in self.sessions and self.peer_meta[peer]['role'] == 'host':
                        target = self.peers.get(self.sessions[peer])
                        if target is not None and not target.closed:
                            await target.send_bytes(msg.data)
                    continue
                if msg.type != WSMsgType.TEXT:
                    continue
                try:
                    packet = json.loads(msg.data)
                    if not isinstance(packet, dict) or not isinstance(packet.get('payload', {}), dict):
                        raise ValueError()
                    typ, payload = packet.get('type'), packet.get('payload', {})
                    if not isinstance(typ,str): raise ValueError()
                except (ValueError, TypeError):
                    await error('Malformed packet.')
                    continue
                if typ == 'register':
                    if peer:
                        await error('Already registered.')
                        continue
                    role = payload.get('role', 'client')
                    if role not in ('host', 'client') or payload.get('protocol') != 2:
                        await error('OpenDesk v2 required. Upgrade both devices.')
                        continue
                    if role == 'host':
                        # A tunnel's source can be loopback; authorize with a per-process secret.
                        if not self.host_token or not secrets.compare_digest(str(payload.get('host_token', '')), self.host_token):
                            await error('Host registration is not authorized.')
                            continue
                        requested = str(payload.get('id', '')).replace(' ', '').replace('-', '')
                        if requested and (not requested.isdigit() or len(requested) != 9):
                            await error('Invalid host ID.')
                            continue
                        assigned = requested or self._generate_id()
                    else:
                        assigned = self._generate_id()
                    if assigned in self.peers:
                        await error('ID already registered.')
                        continue
                    record = payload.get('password_record') if role == 'host' else None
                    if record and (not isinstance(record, dict) or not all(k in record for k in ('salt', 'iterations', 'key'))):
                        await error('Invalid authentication record.')
                        continue
                    peer = assigned
                    self.peers[peer] = ws
                    self.peer_meta[peer] = {'role':role, 'password_record':record}
                    await self._send(peer, 'register_resp', status='ok', id=assigned, clean_id=assigned, role=role, protocol=2)
                    continue
                if not peer:
                    await error('Register first.')
                    continue
                if typ == 'identify':
                    nonce = payload.get('nonce','')
                    if isinstance(nonce,str) and 16 <= len(nonce) <= 128:
                        await self._send(peer, 'identity', **sign_identity(self.identity, nonce))
                elif typ == 'host_config'  and self.peer_meta[peer]['role'] == 'host':
                    self.peer_meta[peer]['password_record'] = payload.get('password_record')
                    for client, challenge in list(self.challenges.items()):
                        if challenge['host'] == peer: self.challenges.pop(client, None)
                elif typ == 'heartbeat':
                    await self._send(peer, 'heartbeat', echo=payload.get('sent_at'))
                elif typ == 'connect':
                    if self.peer_meta[peer]['role'] != 'client' or peer in self.sessions or peer in self.pending:
                        await error('Connection already active or pending.')
                        continue
                    target = str(payload.get('target_id', '')).replace(' ', '').replace('-', '').strip()
                    if target == 'remote_host':
                        hosts = [p for p,m in self.peer_meta.items() if m['role'] == 'host']
                        target = hosts[0] if len(hosts) == 1 else target
                    meta = self.peer_meta.get(target)
                    if not meta or meta['role'] != 'host':
                        await error('Host ID not found.')
                        continue
                    if target in self.sessions:
                        await error('Host is busy.')
                        continue
                    attempts = self.failures[remote]
                    now = time.monotonic()
                    while attempts and now-attempts[0] > 60:
                        attempts.popleft()
                    if len(attempts) >= 5:
                        await error('Too many attempts. Retry in one minute.')
                        continue
                    record = meta.get('password_record')
                    if record:
                        previous = self.challenges.pop(peer, None)
                        proof = payload.get('proof')
                        if proof:
                            if not previous or previous['host'] != target or previous['expires'] < now or not verify_proof(record, previous['nonce'], proof):
                                attempts.append(now)
                                await error('Invalid or expired password proof.')
                                continue
                            await self._pair(target, peer, {k:True for k in PERMISSIONS}, unattended=True)
                        else:
                            nonce = secrets.token_urlsafe(32)
                            self.challenges[peer] = {'host':target, 'nonce':nonce, 'expires':now+30}
                            await self._send(peer, 'auth_challenge', target_id=target, salt=record['salt'],
                                             iterations=record['iterations'], nonce=nonce)
                        continue
                    if sum(req['host']==target for req in self.pending.values())>=8:
                        await error('Too many pending requests for this host.')
                        continue
                    request_id = secrets.token_urlsafe(24)
                    self.pending[peer] = {'id':request_id, 'host':target, 'expires':now+60}
                    await self._send(peer, 'connect_resp', status='waiting_approval', target_id=target)
                    await self._send(target, 'session_request', client_id=peer, display_id=peer, request_id=request_id)
                elif typ in ('session_accept', 'session_reject'):
                    client = payload.get('client_id')
                    req = self.pending.get(client)
                    if self.peer_meta[peer]['role'] != 'host' or not req or req['host'] != peer or req['id'] != payload.get('request_id') or req['expires'] < time.monotonic():
                        await error('Invalid session decision.')
                        continue
                    self.pending.pop(client, None)
                    if typ == 'session_accept':
                        await self._pair(peer, client, payload.get('permissions', {}), request_id=req['id'])
                    else:
                        await self._send(client, 'connect_resp', status='rejected', message='Connection declined by host.')
                elif typ == 'session_end':
                    await self._end(peer)
                elif peer in self.sessions and self._allowed(peer, typ):
                    payload['session_id'] = self.peer_meta[peer]['session_id']
                    await self._send(self.sessions[peer], typ, **payload)
        finally:
            deadline_task.cancel()
            self._connections.discard(ws)
            if peer and self.peers.get(peer) is ws:
                await self._end(peer, 'Remote peer disconnected.')
                self.peers.pop(peer, None)
                self.peer_meta.pop(peer, None)
        return ws

    async def _expire_requests(self, app):
        async def expire():
            while True:
                await asyncio.sleep(5)
                for client, req in list(self.pending.items()):
                    if req['expires'] < time.monotonic():
                        await self._end(client, 'Connection request expired.')
        task = asyncio.create_task(expire())
        yield
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    def create_app(self):
        app = web.Application()
        app.cleanup_ctx.append(self._expire_requests)
        app.router.add_get('/ws', self.handle_ws)
        if os.path.isdir(self.web_dir):
            async def index(request):
                return web.FileResponse(os.path.join(self.web_dir, 'index.html'), headers={
                    'X-Content-Type-Options':'nosniff', 'Referrer-Policy':'no-referrer'})
            app.router.add_get('/', index)
            app.router.add_static('/', self.web_dir, show_index=False)
        return app

    def run(self):
        web.run_app(self.create_app(), host=self.host, port=self.port, handle_signals=False)
