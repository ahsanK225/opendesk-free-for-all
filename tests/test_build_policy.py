import unittest
from unittest.mock import patch
from tools.build_policy import application_binaries
from common.process_environment import independent_environment
from common.updater import select_update_artifact


class TestPackaging(unittest.TestCase):
    def test_foreign_windows_runtime_is_never_bundled(self):
        names=['python311.dll','VCRUNTIME140.dll','VCRUNTIME140_1.dll','ucrtbase.dll',
               'api-ms-win-crt-runtime-l1-1-0.dll','ext-ms-win-test.dll',r'nested\API-MS-WIN-CORE-FILE.dll']
        entries=[(name,'foreign-sdk-path','BINARY') for name in names]
        self.assertEqual([e[0] for e in application_binaries(entries)],names[:3])

    def test_independent_process_drops_stale_extraction_state(self):
        original={'PATH':'system','_PYI_APPLICATION_HOME_DIR':'deleted-temp','_PYI_PARENT_PROCESS_LEVEL':'1',
                  '_MEIPASS2':'deleted-temp','PYINSTALLER_RESET_ENVIRONMENT':'0','PSModulePath':'incompatible-core-modules'}
        env=independent_environment(original)
        self.assertEqual(env,{'PATH':'system','PYINSTALLER_RESET_ENVIRONMENT':'1'})
        self.assertIn('_PYI_APPLICATION_HOME_DIR',original)

    def test_installed_bundle_requires_installer_and_its_digest(self):
        info={'installer_url':'setup','installer_sha256':'setup-hash','download_url':'portable','sha256':'portable-hash'}
        with patch('sys.frozen',True,create=True),patch('sys.executable',r'C:\OpenDesk\OpenDesk.exe'),patch('sys._MEIPASS',r'C:\OpenDesk\_internal',create=True):
            self.assertEqual(select_update_artifact(info),('setup','setup-hash',True))
        with patch('sys.frozen',True,create=True),patch('sys._MEIPASS',r'C:\Temp\_MEI123',create=True):
            self.assertEqual(select_update_artifact(info),('portable','portable-hash',False))
