//! Optional native codec callbacks. Installed once before any media worker starts.
use anyhow::{Result, bail};
use std::{ffi::c_void, sync::OnceLock};

#[repr(C)]
#[derive(Default)]
pub struct Buffer {
    pub data: *const u8,
    pub length: usize,
    pub owner: *mut c_void,
}
pub type Encode = unsafe extern "C" fn(*const u8, usize, u32, u32, u8, *mut Buffer) -> bool;
pub type Decode = unsafe extern "C" fn(*const u8, usize, u32, u32, *mut Buffer) -> bool;
pub type Release = unsafe extern "C" fn(*mut c_void);
struct Backend {
    encode: Encode,
    decode: Decode,
    release: Release,
}
static BACKEND: OnceLock<Backend> = OnceLock::new();

/// # Safety
/// Callbacks must remain valid for the process lifetime, be thread safe, and
/// return an owned buffer valid until `release`. Install before creating an app.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn od_set_jpeg_backend(
    encode: Encode,
    decode: Decode,
    release: Release,
) -> bool {
    BACKEND
        .set(Backend {
            encode,
            decode,
            release,
        })
        .is_ok()
}
pub fn name() -> &'static str {
    if BACKEND.get().is_some() {
        "libjpeg-turbo 3.2.1 / native worker"
    } else {
        "Rust JPEG fallback"
    }
}
fn copy_result(
    backend: &Backend,
    buffer: Buffer,
    okay: bool,
    expected: Option<usize>,
) -> Result<Vec<u8>> {
    struct Owned<'a>(&'a Backend, *mut c_void);
    impl Drop for Owned<'_> {
        fn drop(&mut self) {
            if !self.1.is_null() {
                unsafe { (self.0.release)(self.1) };
            }
        }
    }
    let _owner = Owned(backend, buffer.owner);
    if !okay
        || buffer.data.is_null()
        || buffer.owner.is_null()
        || buffer.length == 0
        || buffer.length > 128 * 1024 * 1024
        || expected.is_some_and(|n| n != buffer.length)
    {
        bail!("Native JPEG codec rejected the image");
    }
    Ok(unsafe { std::slice::from_raw_parts(buffer.data, buffer.length) }.to_vec())
}
pub fn encode(bgra: &[u8], w: u32, h: u32, quality: u8) -> Option<Result<Vec<u8>>> {
    let backend = BACKEND.get()?;
    let mut buffer = Buffer::default();
    let okay = unsafe { (backend.encode)(bgra.as_ptr(), bgra.len(), w, h, quality, &mut buffer) };
    Some(copy_result(backend, buffer, okay, None))
}
pub fn decode(jpeg: &[u8], w: u32, h: u32) -> Option<Result<Vec<u8>>> {
    let backend = BACKEND.get()?;
    let mut buffer = Buffer::default();
    let okay = unsafe { (backend.decode)(jpeg.as_ptr(), jpeg.len(), w, h, &mut buffer) };
    Some(copy_result(
        backend,
        buffer,
        okay,
        Some(w as usize * h as usize * 4),
    ))
}
