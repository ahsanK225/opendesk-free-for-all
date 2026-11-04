use anyhow::Result;
use serde_json::Value;
use std::collections::HashSet;
use windows::Win32::{
    Foundation::{GlobalFree, HANDLE, HGLOBAL, HWND},
    System::{DataExchange::*, Memory::*},
    UI::{Input::KeyboardAndMouse::*, WindowsAndMessaging::*},
};
static CLIPBOARD_OWNER: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);
pub fn set_window(window: usize) {
    CLIPBOARD_OWNER.store(window, std::sync::atomic::Ordering::Release);
}

pub fn key_code(vk: u16) -> String {
    match vk {
        0x41..=0x5a => format!("Key{}", char::from_u32(vk as u32).unwrap()),
        0x30..=0x39 => format!("Digit{}", char::from_u32(vk as u32).unwrap()),
        0x70..=0x87 => format!("F{}", vk - 0x6f),
        96..=105 => format!("Numpad{}", vk - 96),
        19 => "Pause".into(),
        20 => "CapsLock".into(),
        44 => "PrintScreen".into(),
        93 => "ContextMenu".into(),
        106 => "NumpadMultiply".into(),
        107 => "NumpadAdd".into(),
        108 => "NumpadComma".into(),
        109 => "NumpadSubtract".into(),
        110 => "NumpadDecimal".into(),
        111 => "NumpadDivide".into(),
        144 => "NumLock".into(),
        145 => "ScrollLock".into(),
        186 => "Semicolon".into(),
        187 => "Equal".into(),
        188 => "Comma".into(),
        189 => "Minus".into(),
        190 => "Period".into(),
        191 => "Slash".into(),
        192 => "Backquote".into(),
        219 => "BracketLeft".into(),
        220 => "Backslash".into(),
        221 => "BracketRight".into(),
        222 => "Quote".into(),
        226 => "IntlBackslash".into(),
        8 => "Backspace".into(),
        9 => "Tab".into(),
        13 => "Enter".into(),
        16 | 160 | 161 => "Shift".into(),
        17 | 162 | 163 => "Control".into(),
        18 | 164 | 165 => "Alt".into(),
        27 => "Escape".into(),
        32 => "Space".into(),
        33 => "PageUp".into(),
        34 => "PageDown".into(),
        35 => "End".into(),
        36 => "Home".into(),
        37 => "ArrowLeft".into(),
        38 => "ArrowUp".into(),
        39 => "ArrowRight".into(),
        40 => "ArrowDown".into(),
        45 => "Insert".into(),
        46 => "Delete".into(),
        91 => "MetaLeft".into(),
        92 => "MetaRight".into(),
        _ => String::new(),
    }
}
fn resolve_key(payload: &Value) -> Option<u16> {
    if let Some(vk) = payload["vk"].as_u64().filter(|v| (1..=255).contains(v)) {
        return Some(vk as u16);
    }
    let code = payload["code"].as_str().unwrap_or("");
    if let Some(c) = code
        .strip_prefix("Key")
        .filter(|s| s.len() == 1 && s.as_bytes()[0].is_ascii_alphabetic())
    {
        return Some(c.as_bytes()[0].to_ascii_uppercase() as u16);
    }
    if let Some(c) = code
        .strip_prefix("Numpad")
        .filter(|s| s.len() == 1 && s.as_bytes()[0].is_ascii_digit())
    {
        return Some(96 + u16::from(c.as_bytes()[0] - b'0'));
    }
    if let Some(c) = code
        .strip_prefix("Digit")
        .filter(|s| s.len() == 1 && s.as_bytes()[0].is_ascii_digit())
    {
        return Some(c.as_bytes()[0] as u16);
    }
    if let Some(number) = code
        .strip_prefix('F')
        .and_then(|v| v.parse::<u16>().ok())
        .filter(|n| (1..=24).contains(n))
    {
        return Some(0x6f + number);
    }
    let name = if code.is_empty() {
        payload["key"].as_str().unwrap_or("")
    } else {
        code
    };
    let vk = match name {
        "Pause" => 19,
        "CapsLock" => 20,
        "PrintScreen" => 44,
        "ContextMenu" => 93,
        "NumpadMultiply" => 106,
        "NumpadAdd" => 107,
        "NumpadComma" => 108,
        "NumpadSubtract" => 109,
        "NumpadDecimal" => 110,
        "NumpadDivide" => 111,
        "NumpadEnter" => 13,
        "NumLock" => 144,
        "ScrollLock" => 145,
        "Semicolon" => 186,
        "Equal" => 187,
        "Comma" => 188,
        "Minus" => 189,
        "Period" => 190,
        "Slash" => 191,
        "Backquote" => 192,
        "BracketLeft" => 219,
        "Backslash" => 220,
        "BracketRight" => 221,
        "Quote" => 222,
        "IntlBackslash" => 226,
        "Backspace" => 8,
        "Tab" => 9,
        "Enter" | "Return" => 13,
        "Shift" | "ShiftLeft" => 160,
        "ShiftRight" => 161,
        "Control" | "ControlLeft" => 162,
        "ControlRight" => 163,
        "Alt" | "AltLeft" => 164,
        "AltRight" => 165,
        "Escape" => 27,
        "Space" | " " => 32,
        "PageUp" => 33,
        "PageDown" => 34,
        "End" => 35,
        "Home" => 36,
        "ArrowLeft" => 37,
        "ArrowUp" => 38,
        "ArrowRight" => 39,
        "ArrowDown" => 40,
        "Insert" => 45,
        "Delete" => 46,
        "Meta" | "MetaLeft" => 91,
        "MetaRight" => 92,
        _ => {
            let key = payload["key"].as_str().unwrap_or("");
            if key.len() == 1 && key.as_bytes()[0].is_ascii_alphanumeric() {
                key.as_bytes()[0].to_ascii_uppercase() as u16
            } else {
                return None;
            }
        }
    };
    Some(vk)
}
#[derive(Default)]
pub struct Input {
    keys: HashSet<u16>,
    buttons: HashSet<u8>,
    last_cursor: Option<(i32, i32)>,
    local_moved: Option<std::time::Instant>,
    remote_target: Option<(i32, i32)>,
    restore: Option<(i32, i32)>,
}
/// How long the person at this PC keeps the cursor after they last moved it.
const LOCAL_PRIORITY: std::time::Duration = std::time::Duration::from_millis(1000);
/// Windows has one cursor. A held or pressed remote button needs it; otherwise the person here wins.
fn follows_remote(pressed: bool, local_active: bool) -> bool {
    pressed || !local_active
}
fn cursor() -> Option<(i32, i32)> {
    let mut point = windows::Win32::Foundation::POINT::default();
    unsafe { GetCursorPos(&mut point) }.ok()?;
    Some((point.x, point.y))
}
impl Input {
    fn key(vk: u16, up: bool) {
        let extended = matches!(vk, 33..=40 | 45 | 46 | 91 | 92 | 144 | 163 | 165);
        let flags = (if up {
            KEYEVENTF_KEYUP
        } else {
            KEYBD_EVENT_FLAGS(0)
        }) | (if extended {
            KEYEVENTF_EXTENDEDKEY
        } else {
            KEYBD_EVENT_FLAGS(0)
        });
        let input = INPUT {
            r#type: INPUT_KEYBOARD,
            Anonymous: INPUT_0 {
                ki: KEYBDINPUT {
                    wVk: VIRTUAL_KEY(vk),
                    dwFlags: flags,
                    ..Default::default()
                },
            },
        };
        unsafe {
            SendInput(&[input], std::mem::size_of::<INPUT>() as i32);
        }
    }
    fn mouse(flags: MOUSE_EVENT_FLAGS, data: u32) {
        let input = INPUT {
            r#type: INPUT_MOUSE,
            Anonymous: INPUT_0 {
                mi: MOUSEINPUT {
                    dwFlags: flags,
                    mouseData: data,
                    ..Default::default()
                },
            },
        };
        unsafe {
            SendInput(&[input], std::mem::size_of::<INPUT>() as i32);
        }
    }
    /// Any cursor change OpenDesk did not make came from the person at this PC.
    fn observe(&mut self) -> bool {
        let now = cursor();
        if let (Some(last), Some(seen)) = (self.last_cursor, now)
            && ((last.0 - seen.0).abs() > 1 || (last.1 - seen.1).abs() > 1)
        {
            self.local_moved = Some(std::time::Instant::now());
        }
        self.last_cursor = now;
        self.local_moved.is_some_and(|moved| moved.elapsed() < LOCAL_PRIORITY)
    }
    fn place(&mut self, position: (i32, i32)) {
        unsafe {
            let _ = SetCursorPos(position.0, position.1);
        }
        self.last_cursor = Some(position);
    }
    pub fn release_all(&mut self) {
        self.restore = None;
        for vk in self.keys.drain() {
            Self::key(vk, true)
        }
        for button in self.buttons.drain() {
            Self::mouse(
                match button {
                    1 => MOUSEEVENTF_MIDDLEUP,
                    2 => MOUSEEVENTF_RIGHTUP,
                    _ => MOUSEEVENTF_LEFTUP,
                },
                0,
            )
        }
    }
    pub fn handle(&mut self, typ: &str, payload: &Value) {
        match typ {
            "mouse_move" | "mouse_down" | "mouse_up" => {
                let local_active = self.observe();
                let pressed = typ != "mouse_move" || !self.buttons.is_empty();
                if let (Some(x), Some(y)) = (payload["x"].as_f64(), payload["y"].as_f64())
                    && x.is_finite()
                    && y.is_finite()
                {
                    let target = unsafe {
                        let width = GetSystemMetrics(SM_CXSCREEN);
                        let height = GetSystemMetrics(SM_CYSCREEN);
                        (
                            (x.clamp(0.0, 1.0) * (width - 1) as f64) as i32,
                            (y.clamp(0.0, 1.0) * (height - 1) as f64) as i32,
                        )
                    };
                    self.remote_target = Some(target);
                    if follows_remote(pressed, local_active) {
                        if local_active && typ == "mouse_down" && self.buttons.is_empty() {
                            self.restore = cursor();
                        }
                        self.place(target);
                    }
                }
                if typ != "mouse_move" {
                    let button = payload["button"].as_u64().unwrap_or(0).min(2) as u8;
                    let down = typ == "mouse_down";
                    let flags = match (button, down) {
                        (1, true) => MOUSEEVENTF_MIDDLEDOWN,
                        (1, false) => MOUSEEVENTF_MIDDLEUP,
                        (2, true) => MOUSEEVENTF_RIGHTDOWN,
                        (2, false) => MOUSEEVENTF_RIGHTUP,
                        (_, true) => MOUSEEVENTF_LEFTDOWN,
                        (_, false) => MOUSEEVENTF_LEFTUP,
                    };
                    Self::mouse(flags, 0);
                    if down {
                        self.buttons.insert(button);
                    } else {
                        self.buttons.remove(&button);
                        if self.buttons.is_empty()
                            && let Some(position) = self.restore.take()
                        {
                            self.place(position);
                        }
                    }
                }
            }
            "mouse_scroll" => {
                let back = if self.observe() { cursor() } else { None };
                if let (Some(_), Some(target)) = (back, self.remote_target) {
                    self.place(target);
                }
                for (name, flag, factor) in [
                    ("delta_y", MOUSEEVENTF_WHEEL, -120.0),
                    ("delta_x", MOUSEEVENTF_HWHEEL, 120.0),
                ] {
                    if let Some(value) = payload[name].as_f64().filter(|n| n.is_finite()) {
                        Self::mouse(flag, (value.clamp(-100.0, 100.0) * factor) as i32 as u32);
                    }
                }
                if let Some(position) = back {
                    self.place(position);
                }
            }
            "key_down" | "key_up" => {
                if let Some(vk) = resolve_key(payload) {
                    let up = typ == "key_up";
                    Self::key(vk, up);
                    if up {
                        self.keys.remove(&vk);
                    } else {
                        self.keys.insert(vk);
                    }
                }
            }
            "input_reset" => self.release_all(),
            "shortcut" => {
                let name = payload["name"]
                    .as_str()
                    .or(payload["shortcut"].as_str())
                    .unwrap_or("");
                let keys: &[u16] = match name {
                    "copy" => &[162, 67],
                    "paste" => &[162, 86],
                    "cut" => &[162, 88],
                    "select_all" => &[162, 65],
                    "alt_tab" => &[164, 9],
                    "task_manager" | "ctrl_alt_del" => &[162, 160, 27],
                    _ => &[],
                };
                for key in keys {
                    Self::key(*key, false)
                }
                for key in keys.iter().rev() {
                    Self::key(*key, true)
                }
            }
            _ => {}
        }
    }
}
impl Drop for Input {
    fn drop(&mut self) {
        self.release_all();
    }
}
pub struct Clipboard {
    sequence: u32,
}
struct ClipboardGuard;
impl Drop for ClipboardGuard {
    fn drop(&mut self) {
        unsafe {
            let _ = CloseClipboard();
        }
    }
}
impl Clipboard {
    pub fn new() -> Self {
        Self {
            sequence: unsafe { GetClipboardSequenceNumber() },
        }
    }
    pub fn set(&mut self, text: &str) -> Result<()> {
        if text.len() > 1024 * 1024 {
            return Ok(());
        }
        let data: Vec<u16> = text
            .split('\0')
            .next()
            .unwrap_or("")
            .encode_utf16()
            .chain(Some(0))
            .collect();
        unsafe {
            let owner = CLIPBOARD_OWNER.load(std::sync::atomic::Ordering::Acquire);
            if owner == 0 {
                anyhow::bail!("Clipboard window is not initialized")
            };
            OpenClipboard(Some(HWND(owner as _)))?;
            let _guard = ClipboardGuard;
            let memory = GlobalAlloc(GMEM_MOVEABLE, data.len() * 2)?;
            let pointer = GlobalLock(memory);
            if pointer.is_null() {
                let _ = GlobalFree(Some(memory));
                anyhow::bail!("Clipboard memory is unavailable")
            };
            std::ptr::copy_nonoverlapping(data.as_ptr(), pointer as *mut u16, data.len());
            let _ = GlobalUnlock(memory);
            if let Err(error) = EmptyClipboard() {
                let _ = GlobalFree(Some(memory));
                return Err(error.into());
            };
            if let Err(error) = SetClipboardData(13, Some(HANDLE(memory.0))) {
                let _ = GlobalFree(Some(memory));
                return Err(error.into());
            }
            self.sequence = GetClipboardSequenceNumber();
        }
        Ok(())
    }
    pub fn poll(&mut self) -> Option<String> {
        unsafe {
            let sequence = GetClipboardSequenceNumber();
            if sequence == self.sequence {
                return None;
            }
            if OpenClipboard(None).is_err() {
                return None;
            }
            let _guard = ClipboardGuard;
            let handle = GetClipboardData(13).ok()?;
            let memory = HGLOBAL(handle.0);
            let size = GlobalSize(memory);
            if size == 0 || size > 2 * 1024 * 1024 {
                return None;
            }
            let pointer = GlobalLock(memory);
            if pointer.is_null() {
                return None;
            }
            let slice = std::slice::from_raw_parts(pointer as *const u16, size / 2);
            let length = slice.iter().position(|v| *v == 0).unwrap_or(slice.len());
            let text = String::from_utf16_lossy(&slice[..length]);
            let _ = GlobalUnlock(memory);
            self.sequence = sequence;
            Some(text)
        }
    }
}
impl Default for Clipboard {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod pointer_tests {
    use super::follows_remote;
    #[test]
    fn the_person_here_keeps_the_cursor_unless_a_remote_button_needs_it() {
        assert!(follows_remote(false, false));
        assert!(!follows_remote(false, true));
        assert!(follows_remote(true, true));
    }
}
#[cfg(test)]
mod key_tests {
    use super::*;
    use serde_json::json;
    #[test]
    fn browser_punctuation_and_keypad_codes_roundtrip_to_windows_keys() {
        for vk in [
            19, 20, 44, 93, 96, 97, 105, 106, 107, 108, 109, 110, 111, 144, 145, 186, 187, 188,
            189, 190, 191, 192, 219, 220, 221, 222, 226,
        ] {
            let code = key_code(vk);
            assert!(!code.is_empty());
            assert_eq!(resolve_key(&json!({"code":code})), Some(vk));
        }
        assert_eq!(
            resolve_key(&json!({"code":"Semicolon","key":";"})),
            Some(VK_OEM_1.0)
        );
    }
    #[test]
    fn malformed_key_names_do_not_become_unrelated_virtual_keys() {
        assert_eq!(resolve_key(&json!({"code":"Key!"})), None);
        assert_eq!(resolve_key(&json!({"code":"Keyé"})), None);
        assert_eq!(resolve_key(&json!({"code":"DigitX"})), None);
        assert_eq!(resolve_key(&json!({"key":";"})), None);
        assert_eq!(resolve_key(&json!({"code":"KeyA"})), Some(65));
    }
}
