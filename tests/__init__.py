import os
import tempfile
# Never read or modify a developer's real device identity, trust or password during tests.
os.environ.setdefault('OPENDESK_CONFIG_DIR', tempfile.mkdtemp(prefix='opendesk_tests_'))
os.environ['OPENDESK_SILENT_TEST'] = '1'
