"""Independent child processes must not reuse a frozen parent's extraction dir."""
import os


def independent_environment(environment=None):
    env = dict(os.environ if environment is None else environment)
    for key in list(env):
        if key.upper().startswith(('_PYI_', '_MEIPASS')):
            env.pop(key)
        elif key.upper() == 'PSMODULEPATH':
            # Windows PowerShell must initialize its own module search path;
            # an inherited PowerShell 7 path can hide Get-FileHash and friends.
            env.pop(key)
    env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    return env
