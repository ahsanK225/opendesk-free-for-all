"""Protocol-v2 authorization, revocation and transport regression tests."""
import asyncio
import unittest
from aiohttp import web, ClientSession
from relay.server import RelayServer
from common.security import password_record, password_proof

class TestRelay(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.relay=RelayServer(host_token='test-only-token')
        self.runner=web.AppRunner(self.relay.create_app())
        await self.runner.setup()
        site=web.TCPSite(self.runner,'127.0.0.1',0)
        await site.start()
        port=site._server.sockets[0].getsockname()[1]
        self.url=f'http://127.0.0.1:{port}/ws'
        self.http=ClientSession()
        self.sockets=[]
    async def asyncTearDown(self):
        for socket in self.sockets: await socket.close()
        await self.http.close()
        await self.runner.cleanup()
    async def send(self, ws, typ, **payload):
        await ws.send_json({'type':typ,'payload':payload})
    async def receive(self, ws):
        return await ws.receive_json(timeout=2)
    async def peer(self, role='client', id=None, password=''):
        ws=await self.http.ws_connect(self.url)
        self.sockets.append(ws)
        await self.send(ws,'register',role=role,id=id,protocol=2,host_token='test-only-token',password_record=password_record(password))
        packet=await self.receive(ws)
        self.assertEqual(packet['type'],'register_resp')
        return ws,packet['payload']['clean_id']
    async def pair(self, permissions=None):
        host,hid=await self.peer('host','111222333')
        client,cid=await self.peer()
        await self.send(client,'connect',target_id=hid)
        self.assertEqual((await self.receive(client))['payload']['status'],'waiting_approval')
        req=(await self.receive(host))['payload']
        await self.send(host,'session_accept',client_id=cid,request_id=req['request_id'],
                        permissions=permissions or {k:True for k in ('input','audio','clipboard','file_transfer')})
        start=await self.receive(host)
        response=await self.receive(client)
        self.assertEqual(start['type'],'session_start')
        self.assertEqual(response['payload']['status'],'ok')
        return host,hid,client,cid
    async def test_interactive_and_binary_stream(self):
        host,hid,client,cid=await self.pair()
        await host.send_bytes(b'ODV2-test')
        self.assertEqual((await client.receive(timeout=2)).data,b'ODV2-test')
        await self.send(client,'mouse_move',x=.5,y=.5,session_id='forged')
        packet=await self.receive(host)
        self.assertEqual(packet['payload']['session_id'],self.relay.peer_meta[hid]['session_id'])
    async def test_client_cannot_accept_or_start(self):
        host,hid=await self.peer('host','111222333',password='test password')
        client,cid=await self.peer()
        await self.send(client,'session_accept',client_id=hid)
        self.assertEqual((await self.receive(client))['payload']['status'],'error')
        await self.send(client,'session_start',client_id=cid)
        await asyncio.sleep(.02)
        self.assertEqual(self.relay.sessions,{})
        with self.assertRaises(asyncio.TimeoutError): await host.receive(timeout=.05)
    async def test_host_registration_requires_secret(self):
        ws=await self.http.ws_connect(self.url); self.sockets.append(ws)
        await self.send(ws,'register',role='host',id='111222333',protocol=2)
        self.assertEqual((await self.receive(ws))['payload']['status'],'error')
        self.assertFalse(self.relay.peers)
    async def test_duplicate_host_id_rejected(self):
        host,hid=await self.peer('host','111222333')
        other=await self.http.ws_connect(self.url); self.sockets.append(other)
        await self.send(other,'register',role='host',id=hid,protocol=2,host_token='test-only-token')
        self.assertEqual((await self.receive(other))['payload']['status'],'error')
        self.assertIs(self.relay.peers[hid],next(iter(self.relay.peers.values())))
    async def test_wrong_id_does_not_fallback(self):
        await self.peer('host','111222333')
        client,cid=await self.peer()
        await self.send(client,'connect',target_id='999999999')
        self.assertEqual((await self.receive(client))['payload']['status'],'error')
        self.assertFalse(self.relay.pending)
    async def test_disconnect_revokes_session(self):
        host,hid,client,cid=await self.pair()
        await self.send(client,'session_end')
        self.assertEqual((await self.receive(client))['type'],'session_end')
        self.assertEqual((await self.receive(host))['type'],'session_end')
        self.assertFalse(self.relay.sessions)
        await self.send(client,'key_down',code='KeyA')
        with self.assertRaises(asyncio.TimeoutError): await host.receive(timeout=.05)
    async def test_permissions_enforced_by_relay(self):
        host,hid,client,cid=await self.pair({'input':False,'file_transfer':False,'audio':False,'clipboard':False})
        for typ in ('key_down','file_download_req','file_upload_start','file_chunk','audio_chunk','clipboard_text'):
            await self.send(client,typ)
        with self.assertRaises(asyncio.TimeoutError): await host.receive(timeout=.05)
    async def test_host_busy(self):
        host,hid,client,cid=await self.pair()
        other,oid=await self.peer()
        await self.send(other,'connect',target_id=hid)
        self.assertIn('busy',(await self.receive(other))['payload']['message'])
        self.assertEqual(self.relay.sessions[hid],cid)
    async def test_password_challenge_and_replay(self):
        host,hid=await self.peer('host','111222333',password='a strong test password')
        client,cid=await self.peer()
        await self.send(client,'connect',target_id=hid)
        challenge=(await self.receive(client))['payload']
        bad=password_proof('wrong',challenge)
        await self.send(client,'connect',target_id=hid,proof=bad)
        self.assertEqual((await self.receive(client))['payload']['status'],'error')
        await self.send(client,'connect',target_id=hid)
        challenge=(await self.receive(client))['payload']
        proof=password_proof('a strong test password',challenge)
        await self.send(client,'connect',target_id=hid,proof=proof)
        self.assertEqual((await self.receive(host))['type'],'session_start')
        self.assertEqual((await self.receive(client))['payload']['status'],'ok')
        await self.send(client,'session_end'); await self.receive(host); await self.receive(client)
        await self.send(client,'connect',target_id=hid,proof=proof)
        self.assertEqual((await self.receive(client))['payload']['status'],'error')
    async def test_rejected_and_expired_decision(self):
        host,hid=await self.peer('host','111222333'); client,cid=await self.peer()
        await self.send(client,'connect',target_id=hid)
        await self.receive(client); req=(await self.receive(host))['payload']
        await self.send(host,'session_accept',client_id=cid,request_id='wrong',permissions={})
        self.assertEqual((await self.receive(host))['payload']['status'],'error')
        self.assertFalse(self.relay.sessions)
        await self.send(host,'session_reject',client_id=cid,request_id=req['request_id'])
        self.assertEqual((await self.receive(client))['payload']['status'],'rejected')
    async def test_malformed_packets_do_not_disconnect(self):
        client,cid=await self.peer()
        for raw in ('[]','null','{"payload":[]}'):
            await client.send_str(raw)
            self.assertEqual((await self.receive(client))['payload']['status'],'error')
        await self.send(client,'heartbeat',sent_at=123)
        self.assertEqual((await self.receive(client))['payload']['echo'],123)
