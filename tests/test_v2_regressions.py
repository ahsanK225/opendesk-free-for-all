import asyncio
import base64
import hashlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock, AsyncMock
import numpy as np
from PIL import Image
from common.protocol import encode_video_packet, parse_packet
from common.identity import sign_identity, verify_identity
from common.incremental_updater import IncrementalUpdater, DifferentialPlan, managed_path
from common.updater import download_update_file, apply_update_and_restart
from host.file_manager import FileManager
from host.audio import AudioEngine
from host.agent import HostAgent
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


class TestWireAndVoice(unittest.TestCase):
    def test_binary_keyframe_and_delta_roundtrip(self):
        for kind in ('full','delta'):
            image=Image.new('RGB',(128,128),'red')
            buffer=io.BytesIO(); image.save(buffer,format='JPEG')
            data=buffer.getvalue()
            frame={'kind':kind,'width':128,'height':128,'frame_id':12,'data':data,
                   'tiles':[{'x':0,'y':0,'w':128,'h':128,'data':data}]}
            packet=parse_packet(encode_video_packet(frame,'test-session'))
            payload=packet['payload']
            self.assertEqual(payload['session_id'],'test-session')
            actual=payload['image'] if kind=='full' else payload['tiles'][0]['image']
            self.assertEqual(actual,data)
    def test_malformed_video_does_not_decode(self):
        for packet in (b'ODV2',b'ODV2\xff\xff\xff\xff',b'ODV2\0\0\0\1!'):
            self.assertIsNone(parse_packet(packet))
    def test_explicit_rate_preserves_voice_duration(self):
        engine=AudioEngine(); engine.output_samplerate=48000
        # Browser's old 2048-sample/16k block must become 6144 output samples.
        pcm=np.full(2048,1000,dtype=np.int16)
        engine.play_chunk(base64.b64encode(pcm.tobytes()).decode(),16000)
        # Latency cap keeps the newest 120ms; never infer rate from packet length.
        self.assertEqual(len(engine.play_samples),5760)
        engine.play_samples=np.empty(0,dtype=np.int16)
        pcm=np.full(960,1000,dtype=np.int16)
        engine.play_chunk(base64.b64encode(pcm.tobytes()).decode(),48000)
        self.assertEqual(len(engine.play_samples),960)
    def test_bad_audio_is_rejected(self):
        engine=AudioEngine()
        for data,rate in [('!',48000),('AA==',48000),('AAAA',12345)]:
            engine.play_chunk(data,rate)
        self.assertEqual(len(engine.play_samples),0)
    def test_loopback_is_local_and_does_not_transmit(self):
        sent=[]
        engine=AudioEngine(on_mic_chunk_callback=sent.append)
        engine.running=True
        engine.loopback_test_active=True
        engine._mic_callback(np.full((960,1),7000,dtype=np.int16),960,None,None)
        self.assertGreater(len(engine.play_samples),0)
        self.assertEqual(sent,[])
    def test_identity_replay_and_tamper(self):
        key=Ed25519PrivateKey.generate(); nonce='test-nonce-for-identity'
        packet=sign_identity(key,nonce)
        self.assertEqual(verify_identity(packet,nonce),packet['public_key'])
        with self.assertRaises(Exception): verify_identity(packet,nonce+'x')
        packet['signature']=base64.b64encode(b'x'*64).decode()
        with self.assertRaises(Exception): verify_identity(packet,nonce)


class TestTransferSafety(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.root=Path(self.temporary.name)/'shared'; self.root.mkdir()
        self.manager=FileManager(str(self.root))
    def tearDown(self):
        self.manager.cancel_all(); self.temporary.cleanup()
    def test_paths_cannot_escape(self):
        for filename in ('../escape','..\\escape','C:\\escape', '/escape','stream:ads'):
            with self.assertRaises(ValueError): self.manager.start_upload('test',str(self.root),filename,1,1)
        with self.assertRaises(ValueError): self.manager.list_directory(str(self.root.parent))
        with self.assertRaises(ValueError): self.manager.read_file_chunk(str(self.root.parent/'secret'),0)
    def test_chunk_index_and_size_validated(self):
        self.manager.start_upload('test',str(self.root),'safe',1,2)
        with self.assertRaises(ValueError): self.manager.write_upload_chunk('test',9,'QUE=')
        with self.assertRaises(ValueError): self.manager.write_upload_chunk('test',0,'QQ==')
        result=self.manager.write_upload_chunk('test',0,'QUE=')
        self.assertEqual(result['status'],'complete')
        self.assertEqual((self.root/'safe').read_bytes(),b'AA')
    def test_bad_hash_keeps_existing_file(self):
        (self.root/'safe').write_bytes(b'original')
        self.manager.start_upload('test',str(self.root),'safe',1,1,'0'*64)
        with self.assertRaises(ValueError): self.manager.write_upload_chunk('test',0,'QQ==')
        self.assertEqual((self.root/'safe').read_bytes(),b'original')
        self.assertFalse(self.manager.active_transfers)
    def test_empty_file_and_cancel(self):
        self.manager.start_upload('empty',str(self.root),'empty',1,0,hashlib.sha256(b'').hexdigest())
        result=self.manager.write_upload_chunk('empty',0,'')
        self.assertEqual(result['status'],'complete')
        self.assertEqual((self.root/'empty').stat().st_size,0)
        self.manager.start_upload('part',str(self.root),'partial',2,65537)
        self.manager.write_upload_chunk('part',0,base64.b64encode(b'x'*65536).decode())
        self.manager.cancel_all()
        self.assertFalse(list(self.root.glob('*.part_*')))


class TestHostAuthorization(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.patchers=[patch('host.agent.WindowsInputController'),patch('host.agent.WindowsClipboard'),patch('host.agent.AudioEngine')]
        for patcher in self.patchers: patcher.start()
        self.agent=HostAgent(host_token='test')
        self.agent.loop=asyncio.get_running_loop()
        self.agent._send_packet=AsyncMock()
        self.agent.file_manager=Mock()
    async def asyncTearDown(self):
        self.agent.running=False
        self.agent._end_session()
        self.agent._capture_executor.shutdown(wait=True,cancel_futures=True)
        for patcher in self.patchers: patcher.stop()
    async def test_no_access_before_approval_or_wrong_session(self):
        for active,sid in [(False,'session'),(True,'wrong')]:
            self.agent.active_session=active; self.agent.session_id='session'
            await self.agent._handle_message({'type':'file_download_req','payload':{'path':'private','session_id':sid}})
            await self.agent._handle_message({'type':'key_down','payload':{'code':'KeyA','session_id':sid}})
        self.agent.file_manager.read_file_chunk.assert_not_called()
        self.agent.input_controller.key_down.assert_not_called()
    async def test_every_file_handler_checks_permission(self):
        self.agent.active_session=True; self.agent.session_id='session'
        self.agent.permissions={'file_transfer':False}
        for typ in ('file_list_req','file_download_req','file_upload_start','file_chunk'):
            await self.agent._handle_message({'type':typ,'payload':{'session_id':'session'}})
        self.assertFalse(self.agent.file_manager.method_calls)
        self.assertEqual(self.agent._send_packet.await_count,4)
    async def test_forged_start_is_not_approved(self):
        await self.agent._handle_message({'type':'session_start','payload':{'session_id':'forged','request_id':'forged'}})
        self.assertFalse(self.agent.active_session)
    async def test_disconnect_releases_input_and_clears_permissions(self):
        self.agent.active_session=True; self.agent.session_id='session'
        await self.agent._handle_message({'type':'session_end','payload':{}})
        self.assertFalse(self.agent.active_session)
        self.assertIsNone(self.agent.session_id)
        self.agent.input_controller.release_all.assert_called()
        self.assertFalse(self.agent.input_controller.enabled)
    async def test_network_feedback_reduces_stream_load_and_recovers(self):
        self.agent._network_congested=True
        self.agent._adapt_stream(.02,10)
        self.assertLess(self.agent.max_width,1600)
        self.assertLess(self.agent.target_fps,30)
        reduced=self.agent.target_fps
        for now in (12,14,16): self.agent._adapt_stream(.02,now)
        self.assertGreater(self.agent.target_fps,reduced)
        self.assertLessEqual(self.agent.target_fps,self.agent._requested_fps)

    async def test_backpressure_keeps_at_most_three_dependent_frames(self):
        self.agent.running=self.agent.active_session=True
        self.agent.session_id='session'; self.agent.target_fps=60
        self.agent.ws=Mock(); self.agent.ws.send_bytes=AsyncMock()
        count=[0]
        def capture(force):
            count[0]+=1
            return {'kind':'full','width':2,'height':2,'frame_id':count[0],'data':b'jpeg'}
        self.agent._capture_encode=capture
        task=asyncio.create_task(self.agent._video_stream_loop())
        await asyncio.sleep(.15)
        self.assertEqual(self.agent.ws.send_bytes.await_count,3)
        await self.agent._handle_message({'type':'video_ack','payload':{'session_id':'session','frame_id':2}})
        await asyncio.sleep(.08)
        self.assertEqual(self.agent.ws.send_bytes.await_count,5)
        self.assertEqual([x[0] for x in self.agent._outstanding],[3,4,5])
        task.cancel(); await asyncio.gather(task,return_exceptions=True)


class TestUpdateSafety(unittest.TestCase):
    def test_missing_digest_is_not_downloaded(self):
        with patch('urllib.request.urlopen') as request:
            self.assertFalse(download_update_file('https://github.com/anything','unused'))
            request.assert_not_called()
    def test_update_paths_are_contained(self):
        with tempfile.TemporaryDirectory() as base:
            for name in ('../escape','/escape','C:\\escape','foo/../../escape','foo:ads'):
                with self.assertRaises(ValueError): managed_path(base,name)
            self.assertEqual(managed_path(base,'safe/file'),os.path.join(base,'safe','file'))
    def test_unowned_files_are_not_deleted(self):
        with tempfile.TemporaryDirectory() as base:
            Path(base,'personal.txt').write_text('keep')
            updater=IncrementalUpdater(base,'')
            self.assertEqual(updater.compute_differential({'files':[]}).to_delete,[])
    def test_partial_apply_removes_new_files_on_rollback(self):
        with tempfile.TemporaryDirectory() as base:
            staging=Path(base,'.update_staging'); staging.mkdir()
            (staging/'new').write_bytes(b'new')
            (staging/'bad').write_bytes(b'bad')
            plan=DifferentialPlan('1','2',to_download=[
                {'path':'new','sha256':hashlib.sha256(b'new').hexdigest()},
                {'path':'bad','sha256':'0'*64}])
            ok,error=IncrementalUpdater(base,'').apply_staged_update(plan,str(staging))
            self.assertFalse(ok)
            self.assertFalse(Path(base,'new').exists())


class TestDXGIOwnership(unittest.TestCase):
    def test_com_pointer_is_released_once(self):
        from host.dxgi import release_surface, release_duplication
        released=[]
        class Pointer:
            def __del__(self): released.append(1)
            def Release(self): raise AssertionError('Never manually Release a comtypes-owned pointer')
        class Surface: pass
        surface=Surface(); surface.texture=Pointer(); surface.interface=Pointer()
        release_surface(surface)
        self.assertEqual(len(released),2)
        duplicate=Surface(); duplicate.duplicator=Pointer(); duplicate.texture=Pointer()
        duplicate.release_frame=Mock()
        release_duplication(duplicate)
        duplicate.release_frame.assert_called_once()
        self.assertEqual(len(released),4)
    def test_discovery_record_is_signed_and_bound_to_id(self):
        from common.rendezvous import _directory_record, _read_directory_record
        record=_directory_record('111222333','https://test.trycloudflare.com')
        resolved=_read_directory_record(record,'111222333')
        self.assertEqual(resolved,'https://test.trycloudflare.com')
        self.assertTrue(resolved.public_key)
        self.assertIsNone(_read_directory_record(record,'999999999'))
        self.assertIsNone(_read_directory_record(record.replace('test.trycloudflare','evil.trycloudflare'),'111222333'))
