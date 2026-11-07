use anyhow::{Context, Result, bail};
use std::ffi::c_void;
use windows::{
    Win32::{
        Foundation::*,
        Graphics::{
            Direct3D::*,
            Direct3D11::*,
            Dxgi::{Common::*, *},
            Gdi::*,
        },
        System::Com::*,
        UI::WindowsAndMessaging::*,
    },
    core::Interface,
};

struct Surface {
    screen: HDC,
    memory: HDC,
    bitmap: HBITMAP,
    previous: HGDIOBJ,
    bits: *mut c_void,
    width: u32,
    height: u32,
}
impl Surface {
    fn new(width: u32, height: u32) -> Result<Self> {
        unsafe {
            if width == 0
                || height == 0
                || width > 16384
                || height > 16384
                || u64::from(width) * u64::from(height) > 64 * 1024 * 1024
            {
                bail!("Unsupported desktop dimensions")
            }
            let screen = GetDC(None);
            if screen.is_invalid() {
                bail!("Desktop DC is unavailable")
            };
            let memory = CreateCompatibleDC(Some(screen));
            if memory.is_invalid() {
                ReleaseDC(None, screen);
                bail!("Capture DC is unavailable")
            }
            let info = BITMAPINFO {
                bmiHeader: BITMAPINFOHEADER {
                    biSize: std::mem::size_of::<BITMAPINFOHEADER>() as u32,
                    biWidth: width as i32,
                    biHeight: -(height as i32),
                    biPlanes: 1,
                    biBitCount: 32,
                    biCompression: BI_RGB.0,
                    ..Default::default()
                },
                ..Default::default()
            };
            let mut bits = std::ptr::null_mut();
            let bitmap =
                match CreateDIBSection(Some(screen), &info, DIB_RGB_COLORS, &mut bits, None, 0) {
                    Ok(bitmap) => bitmap,
                    Err(error) => {
                        let _ = DeleteDC(memory);
                        ReleaseDC(None, screen);
                        return Err(error.into());
                    }
                };
            let previous = SelectObject(memory, HGDIOBJ(bitmap.0));
            Ok(Self {
                screen,
                memory,
                bitmap,
                previous,
                bits,
                width,
                height,
            })
        }
    }
    fn cursor(&self) {
        unsafe {
            let mut cursor = CURSORINFO {
                cbSize: std::mem::size_of::<CURSORINFO>() as u32,
                ..Default::default()
            };
            if GetCursorInfo(&mut cursor).is_ok() && cursor.flags == CURSOR_SHOWING {
                let mut icon = ICONINFO::default();
                if GetIconInfo(HICON(cursor.hCursor.0), &mut icon).is_ok() {
                    let _ = DrawIconEx(
                        self.memory,
                        cursor.ptScreenPos.x - icon.xHotspot as i32,
                        cursor.ptScreenPos.y - icon.yHotspot as i32,
                        HICON(cursor.hCursor.0),
                        0,
                        0,
                        0,
                        None,
                        DI_NORMAL,
                    );
                    if !icon.hbmColor.is_invalid() {
                        let _ = DeleteObject(HGDIOBJ(icon.hbmColor.0));
                    }
                    if !icon.hbmMask.is_invalid() {
                        let _ = DeleteObject(HGDIOBJ(icon.hbmMask.0));
                    }
                }
            }
        }
    }
    fn pixels(&self) -> Vec<u8> {
        let bgra = unsafe {
            std::slice::from_raw_parts(
                self.bits as *const u8,
                self.width as usize * self.height as usize * 4,
            )
        };
        bgra.to_vec()
    }
}
impl Drop for Surface {
    fn drop(&mut self) {
        unsafe {
            SelectObject(self.memory, self.previous);
            let _ = DeleteObject(HGDIOBJ(self.bitmap.0));
            let _ = DeleteDC(self.memory);
            ReleaseDC(None, self.screen);
        }
    }
}
struct Duplication {
    device: ID3D11Device,
    context: ID3D11DeviceContext,
    duplication: IDXGIOutputDuplication,
    staging: Option<ID3D11Texture2D>,
}
impl Duplication {
    fn new() -> Result<Self> {
        unsafe {
            let factory: IDXGIFactory1 = CreateDXGIFactory1()?;
            for index in 0..16 {
                let Ok(adapter) = factory.EnumAdapters1(index) else {
                    break;
                };
                for output_index in 0..16 {
                    let Ok(output) = adapter.EnumOutputs(output_index) else {
                        break;
                    };
                    let description = output.GetDesc()?;
                    if !description.AttachedToDesktop.as_bool()
                        || description.DesktopCoordinates.left != 0
                        || description.DesktopCoordinates.top != 0
                    {
                        continue;
                    }
                    let mut device = None;
                    let mut context = None;
                    let adapter: IDXGIAdapter = adapter.cast()?;
                    D3D11CreateDevice(
                        &adapter,
                        D3D_DRIVER_TYPE_UNKNOWN,
                        HMODULE::default(),
                        D3D11_CREATE_DEVICE_BGRA_SUPPORT,
                        Some(&[D3D_FEATURE_LEVEL_11_0, D3D_FEATURE_LEVEL_10_1]),
                        D3D11_SDK_VERSION,
                        Some(&mut device),
                        None,
                        Some(&mut context),
                    )?;
                    let device = device.context("D3D11 device was not created")?;
                    let context = context.context("D3D11 context was not created")?;
                    let output: IDXGIOutput1 = output.cast()?;
                    return Ok(Self {
                        duplication: output.DuplicateOutput(&device)?,
                        device,
                        context,
                        staging: None,
                    });
                }
            }
            bail!("Desktop Duplication is unavailable for the primary monitor")
        }
    }
    fn grab(&mut self, surface: &Surface) -> Result<bool> {
        unsafe {
            let mut info = DXGI_OUTDUPL_FRAME_INFO::default();
            let mut resource = None;
            match self
                .duplication
                .AcquireNextFrame(0, &mut info, &mut resource)
            {
                Ok(()) => {}
                Err(error) if error.code() == DXGI_ERROR_WAIT_TIMEOUT => return Ok(false),
                Err(error) => return Err(error.into()),
            }
            let result = (|| -> Result<bool> {
                let texture: ID3D11Texture2D =
                    resource.context("Empty duplication resource")?.cast()?;
                let mut desc = D3D11_TEXTURE2D_DESC::default();
                texture.GetDesc(&mut desc);
                if desc.Width != surface.width || desc.Height != surface.height {
                    bail!("Desktop dimensions changed")
                }
                if self.staging.is_none() {
                    let copy = D3D11_TEXTURE2D_DESC {
                        Usage: D3D11_USAGE_STAGING,
                        BindFlags: 0,
                        CPUAccessFlags: D3D11_CPU_ACCESS_READ.0 as u32,
                        MiscFlags: 0,
                        SampleDesc: DXGI_SAMPLE_DESC {
                            Count: 1,
                            Quality: 0,
                        },
                        ..desc
                    };
                    let mut staging = None;
                    self.device
                        .CreateTexture2D(&copy, None, Some(&mut staging))?;
                    self.staging = staging;
                }
                let staging = self.staging.as_ref().context("No staging texture")?;
                self.context.CopyResource(staging, &texture);
                let mut mapped = D3D11_MAPPED_SUBRESOURCE::default();
                self.context
                    .Map(staging, 0, D3D11_MAP_READ, 0, Some(&mut mapped))?;
                for row in 0..desc.Height as usize {
                    std::ptr::copy_nonoverlapping(
                        (mapped.pData as *const u8).add(row * mapped.RowPitch as usize),
                        (surface.bits as *mut u8).add(row * desc.Width as usize * 4),
                        desc.Width as usize * 4,
                    );
                }
                self.context.Unmap(staging, 0);
                Ok(true)
            })();
            let released = self.duplication.ReleaseFrame();
            if result.is_ok() {
                released?;
            }
            result
        }
    }
}
pub struct Capture {
    surface: Surface,
    duplication: Option<Duplication>,
    com: bool,
    pub backend: &'static str,
    retry: std::time::Instant,
    captured: bool,
}
impl Capture {
    pub fn new() -> Result<Self> {
        let com = unsafe { CoInitializeEx(None, COINIT_MULTITHREADED) }.is_ok();
        let width = unsafe { GetSystemMetrics(SM_CXSCREEN) } as u32;
        let height = unsafe { GetSystemMetrics(SM_CYSCREEN) } as u32;
        let surface = Surface::new(width, height)?;
        let duplication = Duplication::new().ok();
        let backend = if duplication.is_some() { "DXGI" } else { "GDI" };
        Ok(Self {
            surface,
            duplication,
            com,
            backend,
            retry: std::time::Instant::now(),
            captured: false,
        })
    }
    pub fn grab(&mut self) -> Result<Option<(u32, u32, Vec<u8>)>> {
        let width = unsafe { GetSystemMetrics(SM_CXSCREEN) } as u32;
        let height = unsafe { GetSystemMetrics(SM_CYSCREEN) } as u32;
        if width != self.surface.width || height != self.surface.height {
            self.duplication = None;
            self.surface = Surface::new(width, height)?;
            self.duplication = Duplication::new().ok();
            self.captured = false;
        }
        if self.duplication.is_none() && self.retry.elapsed() > std::time::Duration::from_secs(1) {
            self.retry = std::time::Instant::now();
            self.duplication = Duplication::new().ok();
        }
        if let Some(duplication) = &mut self.duplication {
            match duplication.grab(&self.surface) {
                Ok(false) if self.captured => return Ok(None),
                Ok(false) => {
                    // Desktop duplication need not emit an initial update on an idle desktop.
                    // Supply a real baseline instead of leaving the first viewer frame blank.
                    unsafe {
                        BitBlt(
                            self.surface.memory,
                            0,
                            0,
                            width as i32,
                            height as i32,
                            Some(self.surface.screen),
                            0,
                            0,
                            SRCCOPY | CAPTUREBLT,
                        )?;
                    }
                    self.backend = "GDI baseline / DXGI";
                }
                Ok(true) => self.backend = "DXGI",
                Err(_) => {
                    self.duplication = None;
                    self.backend = "GDI";
                    unsafe {
                        BitBlt(
                            self.surface.memory,
                            0,
                            0,
                            width as i32,
                            height as i32,
                            Some(self.surface.screen),
                            0,
                            0,
                            SRCCOPY | CAPTUREBLT,
                        )?;
                    }
                }
            }
        } else {
            self.backend = "GDI";
            unsafe {
                BitBlt(
                    self.surface.memory,
                    0,
                    0,
                    width as i32,
                    height as i32,
                    Some(self.surface.screen),
                    0,
                    0,
                    SRCCOPY | CAPTUREBLT,
                )?;
            }
        }
        self.surface.cursor();
        self.captured = true;
        Ok(Some((width, height, self.surface.pixels())))
    }
}
impl Drop for Capture {
    fn drop(&mut self) {
        drop(self.duplication.take());
        if self.com {
            unsafe {
                CoUninitialize();
            }
        }
    }
}
