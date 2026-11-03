//! The C++ bridge owns each handle; returned strings/frames have explicit releases.
use crate::app::{App, Frame};
use std::{
    ffi::{CStr, CString, c_char, c_void},
    path::PathBuf,
    sync::{Arc, atomic::Ordering},
};

fn string(value: impl AsRef<str>) -> *mut c_char {
    CString::new(value.as_ref())
        .map(CString::into_raw)
        .unwrap_or(std::ptr::null_mut())
}
#[unsafe(no_mangle)]
pub extern "C" fn od_diagnostics(capture: bool) -> *mut c_char {
    let value = match crate::diagnostics::report(capture) {
        Ok(value) => value,
        Err(error) => serde_json::json!({"error":format!("{error:#}")}),
    };
    string(value.to_string())
}
#[unsafe(no_mangle)]
pub extern "C" fn od_set_window_handle(window: usize) {
    crate::platform::set_window(window);
}

/// # Safety
/// `directory` must be null or a valid nul-terminated UTF-8 string for this call.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn od_create(directory: *const c_char) -> *mut App {
    std::panic::catch_unwind(|| {
        let path = if directory.is_null() {
            std::env::var("OPENDESK_CONFIG_DIR")
                .map(PathBuf::from)
                .unwrap_or_else(|_| {
                    PathBuf::from(std::env::var("USERPROFILE").unwrap_or_default())
                        .join(".opendesk")
                })
        } else {
            PathBuf::from(
                unsafe { CStr::from_ptr(directory) }
                    .to_string_lossy()
                    .as_ref(),
            )
        };
        match App::create(path) {
            Ok(app) => Box::into_raw(Box::new(app)),
            Err(error) => {
                eprintln!("OpenDesk engine: {error:#}");
                std::ptr::null_mut()
            }
        }
    })
    .unwrap_or(std::ptr::null_mut())
}
/// # Safety
/// A non-null handle must be owned by the caller and released exactly once.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn od_destroy(app: *mut App) {
    if !app.is_null() {
        drop(unsafe { Box::from_raw(app) });
    }
}
/// # Safety
/// `app` is live and `command` is a valid nul-terminated UTF-8 string.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn od_command(app: *const App, command: *const c_char) {
    if app.is_null() || command.is_null() {
        return;
    }
    let bytes = unsafe { CStr::from_ptr(command) }.to_bytes();
    if bytes.len() > 128 * 1024 {
        return;
    }
    if let Ok(value) = serde_json::from_slice(bytes) {
        unsafe { &*app }.command(value);
    }
}
/// # Safety
/// The handle must remain live; release non-null output using `od_string_free`.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn od_poll(app: *const App) -> *mut c_char {
    let Some(app) = (unsafe { app.as_ref() }) else {
        return std::ptr::null_mut();
    };
    let revision = app.shared.revision.load(Ordering::Acquire);
    if app.last_poll.swap(revision, Ordering::Relaxed) == revision {
        return std::ptr::null_mut();
    }
    string(app.shared.view.lock().unwrap().to_string())
}
/// # Safety
/// The string was returned by this library and has not been freed.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn od_string_free(value: *mut c_char) {
    if !value.is_null() {
        drop(unsafe { CString::from_raw(value) });
    }
}

#[repr(C)]
pub struct FrameView {
    pub data: *const u8,
    pub length: usize,
    pub width: u32,
    pub height: u32,
    pub generation: u64,
    pub owner: *mut c_void,
}
/// # Safety
/// Valid live app, UTF-8 session key and writable output pointer are required.
/// Release output.owner using `od_frame_release` after the pixel view is unused.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn od_frame_acquire(
    app: *const App,
    key: *const c_char,
    output: *mut FrameView,
) -> bool {
    if app.is_null() || key.is_null() || output.is_null() {
        return false;
    }
    let app = unsafe { &*app };
    let key = unsafe { CStr::from_ptr(key) }.to_string_lossy();
    let frames = app.shared.frames.lock().unwrap();
    let Some(frame) = frames.get(key.as_ref()) else {
        return false;
    };
    let owner = Box::new(frame.clone());
    unsafe {
        *output = FrameView {
            data: frame.pixels.as_ptr(),
            length: frame.pixels.len(),
            width: frame.width,
            height: frame.height,
            generation: frame.generation,
            owner: Box::into_raw(owner) as *mut c_void,
        };
    }
    true
}
/// # Safety
/// The owner was acquired above and is released exactly once after all reads.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn od_frame_release(owner: *mut c_void) {
    if !owner.is_null() {
        drop(unsafe { Box::from_raw(owner as *mut Arc<Frame>) });
    }
}
