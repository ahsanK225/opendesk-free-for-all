"""Compatibility fix for the pinned DXcam 0.3.0/comtypes ownership contract.

DXcam's release methods explicitly Release() a comtypes-owned pointer and then
drop the pointer, whose destructor releases it a second time. Let comtypes own
the final Release instead. Keep this shim version-scoped until upstream fixes it.
"""


def release_surface(surface):
    surface.interface = None
    surface.texture = None
    surface.width = surface.height = 0


def release_duplication(duplication):
    if duplication.duplicator is not None:
        try:
            duplication.release_frame()
        finally:
            duplication.texture = None
            duplication.duplicator = None


def configure_ownership():
    from importlib.metadata import version
    if version('dxcam') != '0.3.0':
        raise RuntimeError('DXGI adapter requires the tested DXcam 0.3.0 release')
    from dxcam.core.dxgi_duplicator import DXGIDuplicator
    from dxcam.core.stagesurf import StageSurface
    StageSurface.release = release_surface
    DXGIDuplicator.release = release_duplication
