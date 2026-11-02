import os
import threading
import unittest
from unittest.mock import patch,Mock
from common.launcher import APP_NAME,shutdown_running,SingleInstance
from common.ui import UiDispatcher


class TestUiDispatch(unittest.TestCase):
    def test_visual_burst_keeps_only_latest_and_critical_order(self):
        ui=UiDispatcher(); results=[]
        for i in range(10000): ui.post(results.append,i,key='meter')
        ui.post(results.append,'important')
        ui.drain()
        self.assertEqual(results,['important',9999])
        self.assertFalse(ui.pending())

    def test_dispatch_budget_prevents_event_loop_starvation(self):
        ui=UiDispatcher(); values=[]
        for i in range(100): ui.post(values.append,i)
        self.assertEqual(ui.drain(max_items=5),5)
        self.assertTrue(ui.pending())
        self.assertEqual(values,list(range(5)))


class TestShutdown(unittest.TestCase):
    def test_process_name_scope(self):
        for name in ('OpenDesk.exe','OpenDesk_v2.0.0_Portable.exe'):
            self.assertIsNotNone(APP_NAME.fullmatch(name))
        for name in ('OpenDeskSetupHelper.exe','OpenDesk_Setup_v2.0.1_Installer.exe','notopendesk.exe','python.exe'):
            self.assertIsNone(APP_NAME.fullmatch(name))

    def test_graceful_shutdown_does_not_force_kill(self):
        with patch('common.launcher.signal_shutdown') as signal,patch('common.launcher.matching_processes',return_value=[]),patch('common.launcher.subprocess.run') as run:
            self.assertEqual(shutdown_running(force=True),[])
            signal.assert_called_once()
            run.assert_not_called()

    def test_force_kill_rechecks_pid_identity(self):
        clock=[0]
        def sleep(n): clock[0]+=n
        with patch('common.launcher.signal_shutdown'),patch('common.launcher.time.monotonic',side_effect=lambda:clock[0]),patch('common.launcher.time.sleep',side_effect=sleep),patch('common.launcher.matching_processes',return_value=[(123,'C:\\OpenDesk.exe')]),patch('common.launcher.process_path',return_value='C:\\other.exe'),patch('common.launcher.subprocess.run') as run:
            self.assertTrue(shutdown_running(force=True,timeout=2))
            run.assert_not_called()

    @unittest.skipUnless(os.name=='nt','Windows named events')
    def test_single_instance_activation_event(self):
        import uuid
        suffix=str(uuid.uuid4())
        first=SingleInstance(suffix); second=SingleInstance(suffix)
        try:
            self.assertTrue(first.primary)
            self.assertFalse(second.primary)
            self.assertEqual(first.poll(),'activate')
        finally: second.close(); first.close()

    def test_render_releases_snapshot_lock_before_tcl_upload(self):
        from client.viewer import EmbeddedSessionView
        from PIL import Image
        # A lightweight view exercises the real render method without opening hardware.
        view=Mock()
        view.image_lock=threading.Lock()
        view.remote_image=Image.new('RGB',(64,64))
        view.canvas.winfo_width.return_value=64
        view.canvas.winfo_height.return_value=64
        view._safe_exists.return_value=True
        view.view_mode='fit'; view.zoom_level=1
        view.pan_x=view.pan_y=0
        view.tk_photo=None; view.canvas_img_id=None; view.frame_count=0
        def photo(image):
            self.assertFalse(view.image_lock.locked())
            return Mock()
        with patch('client.viewer.ImageTk.PhotoImage',side_effect=photo):
            EmbeddedSessionView._render_frame(view)
        self.assertEqual(view.frame_count,1)
