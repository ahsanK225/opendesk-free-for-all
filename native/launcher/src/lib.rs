use anyhow::{Context, Result, bail};
use sha2::{Digest, Sha256};
use std::{
    collections::HashSet,
    path::Path,
    time::{Duration, Instant},
};
use windows::{
    Win32::{
        Foundation::*,
        System::{Diagnostics::ToolHelp::*, RemoteDesktop::ProcessIdToSessionId, Threading::*},
    },
    core::PCWSTR,
};
pub fn wide(text: &str) -> Vec<u16> {
    text.encode_utf16().chain(Some(0)).collect()
}
pub fn instance_name(suffix: &str) -> Result<String> {
    let user = std::env::var("USERPROFILE")
        .context("Windows profile directory is unavailable")?
        .replace('/', "\\")
        .to_lowercase();
    Ok(format!(
        "Local\\OpenDesk.{}",
        &hex::encode(Sha256::digest(format!("{user}{suffix}").as_bytes()))[..24]
    ))
}
pub struct Handle(pub HANDLE);
impl Drop for Handle {
    fn drop(&mut self) {
        unsafe {
            if !self.0.is_invalid() {
                let _ = CloseHandle(self.0);
            }
        }
    }
}
pub struct Instance {
    _mutex: Handle,
    pub shutdown: Handle,
    pub activate: Handle,
    pub primary: bool,
}
impl Instance {
    pub fn new(suffix: &str) -> Result<Self> {
        let name = instance_name(suffix)?;
        unsafe {
            SetLastError(WIN32_ERROR(0));
            let mutex = Handle(CreateMutexW(None, false, PCWSTR(wide(&name).as_ptr()))?);
            let primary = GetLastError() != ERROR_ALREADY_EXISTS;
            let shutdown = Handle(CreateEventW(
                None,
                false,
                false,
                PCWSTR(wide(&(name.clone() + ".shutdown")).as_ptr()),
            )?);
            let activate = Handle(CreateEventW(
                None,
                false,
                false,
                PCWSTR(wide(&(name + ".activate")).as_ptr()),
            )?);
            if !primary {
                SetEvent(activate.0)?;
            }
            Ok(Self {
                _mutex: mutex,
                shutdown,
                activate,
                primary,
            })
        }
    }
    pub fn shutdown_requested(&self) -> bool {
        unsafe { WaitForSingleObject(self.shutdown.0, 0) == WAIT_OBJECT_0 }
    }
}
pub fn activate_existing() -> Result<bool> {
    let name = instance_name("")?;
    unsafe {
        let Ok(mutex) = OpenMutexW(
            SYNCHRONIZATION_SYNCHRONIZE,
            false,
            PCWSTR(wide(&name).as_ptr()),
        ) else {
            return Ok(false);
        };
        let _mutex = Handle(mutex);
        let event = Handle(OpenEventW(
            EVENT_MODIFY_STATE,
            false,
            PCWSTR(wide(&(name + ".activate")).as_ptr()),
        )?);
        SetEvent(event.0)?;
        Ok(true)
    }
}
pub fn signal_shutdown(suffix: &str) -> Result<bool> {
    let name = instance_name(suffix)?;
    unsafe {
        let Ok(event) = OpenEventW(
            EVENT_MODIFY_STATE,
            false,
            PCWSTR(wide(&(name + ".shutdown")).as_ptr()),
        ) else {
            return Ok(false);
        };
        let event = Handle(event);
        SetEvent(event.0)?;
        Ok(true)
    }
}
pub fn application_name(name: &str) -> bool {
    let name = name.to_ascii_lowercase();
    if name == "opendesk.exe" {
        return true;
    }
    let Some(version) = name
        .strip_prefix("opendesk_v")
        .and_then(|v| v.strip_suffix("_portable.exe"))
    else {
        return false;
    };
    let parts: Vec<_> = version.split('.').collect();
    parts.len() == 3
        && parts
            .iter()
            .all(|v| !v.is_empty() && v.bytes().all(|b| b.is_ascii_digit()))
}
#[derive(Clone)]
struct Process {
    pid: u32,
    parent: u32,
    name: String,
}
fn snapshot() -> Result<Vec<Process>> {
    unsafe {
        let handle = Handle(CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)?);
        let mut entry = PROCESSENTRY32W {
            dwSize: std::mem::size_of::<PROCESSENTRY32W>() as u32,
            ..Default::default()
        };
        let mut output = Vec::new();
        if Process32FirstW(handle.0, &mut entry).is_ok() {
            loop {
                let end = entry
                    .szExeFile
                    .iter()
                    .position(|v| *v == 0)
                    .unwrap_or(entry.szExeFile.len());
                output.push(Process {
                    pid: entry.th32ProcessID,
                    parent: entry.th32ParentProcessID,
                    name: String::from_utf16_lossy(&entry.szExeFile[..end]),
                });
                if Process32NextW(handle.0, &mut entry).is_err() {
                    break;
                }
            }
        }
        Ok(output)
    }
}
fn normalize(path: &Path) -> String {
    let text = path.to_string_lossy().replace('/', "\\").to_lowercase();
    text.strip_prefix("\\\\?\\")
        .unwrap_or(&text)
        .trim_end_matches('\\')
        .to_owned()
}
fn image(handle: HANDLE) -> Option<String> {
    unsafe {
        let mut size = 32768u32;
        let mut buffer = vec![0u16; size as usize];
        QueryFullProcessImageNameW(
            handle,
            PROCESS_NAME_WIN32,
            windows::core::PWSTR(buffer.as_mut_ptr()),
            &mut size,
        )
        .ok()?;
        Some(String::from_utf16_lossy(&buffer[..size as usize]))
    }
}
fn same_session(pid: u32) -> bool {
    unsafe {
        let mut own = 0;
        let mut other = 0;
        ProcessIdToSessionId(std::process::id(), &mut own).is_ok()
            && ProcessIdToSessionId(pid, &mut other).is_ok()
            && own == other
    }
}
#[derive(Clone)]
struct Target {
    pid: u32,
    path: Option<String>,
    worker: bool,
}
fn targets(scope: Option<&Path>, previous_workers: &[Target]) -> Result<Vec<Target>> {
    let processes = snapshot()?;
    let mut result = Vec::new();
    let mut roots = HashSet::new();
    for process in &processes {
        if process.pid == std::process::id()
            || !application_name(&process.name)
            || !same_session(process.pid)
        {
            continue;
        }
        let path = unsafe { OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, process.pid) }
            .ok()
            .and_then(|handle| {
                let handle = Handle(handle);
                image(handle.0)
            });
        if let Some(scope) = scope
            && !path.as_ref().is_some_and(|p| {
                Path::new(p)
                    .parent()
                    .is_some_and(|dir| normalize(dir) == normalize(scope))
            })
        {
            continue;
        }
        roots.insert(process.pid);
        result.push(Target {
            pid: process.pid,
            path,
            worker: false,
        });
    }
    for process in &processes {
        if !process.name.eq_ignore_ascii_case("cloudflared.exe") || !same_session(process.pid) {
            continue;
        }
        let mut parent = process.parent;
        let mut belongs = false;
        for _ in 0..16 {
            if roots.contains(&parent) {
                belongs = true;
                break;
            }
            if let Some(ancestor) = processes.iter().find(|p| p.pid == parent) {
                if ancestor.parent == parent {
                    break;
                }
                parent = ancestor.parent;
            } else {
                break;
            }
        }
        if belongs {
            let path =
                unsafe { OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, process.pid) }
                    .ok()
                    .and_then(|handle| {
                        let handle = Handle(handle);
                        image(handle.0)
                    });
            result.push(Target {
                pid: process.pid,
                path,
                worker: true,
            });
        }
    }
    for previous in previous_workers {
        if !result.iter().any(|p| p.pid == previous.pid)
            && processes
                .iter()
                .any(|p| p.pid == previous.pid && p.name.eq_ignore_ascii_case("cloudflared.exe"))
        {
            let current =
                unsafe { OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, previous.pid) }
                    .ok()
                    .and_then(|handle| {
                        let handle = Handle(handle);
                        image(handle.0)
                    });
            if current == previous.path {
                result.push(previous.clone());
            }
        }
    }
    Ok(result)
}
pub fn shutdown(force: bool, timeout: f64, scope: Option<&Path>, suffix: &str) -> Result<Vec<u32>> {
    let scope = scope
        .map(|p| std::fs::canonicalize(p).or_else(|_| std::path::absolute(p)))
        .transpose()?;
    let mut initial = targets(scope.as_deref(), &[])?;
    let workers: Vec<_> = initial.iter().filter(|p| p.worker).cloned().collect();
    let _ = signal_shutdown(suffix)?;
    let start = Instant::now();
    let limit = Duration::from_secs_f64(timeout.clamp(2.0, 20.0));
    while start.elapsed() < limit.min(Duration::from_secs(2)) {
        initial = targets(scope.as_deref(), &workers)?;
        if initial.is_empty() {
            return Ok(Vec::new());
        }
        std::thread::sleep(Duration::from_millis(75));
    }
    if force {
        initial.sort_by_key(|p| !p.worker);
        for target in &initial {
            if start.elapsed() >= limit {
                break;
            }
            let Some(expected) = &target.path else {
                continue;
            };
            unsafe {
                if let Ok(handle) = OpenProcess(
                    PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_TERMINATE,
                    false,
                    target.pid,
                ) {
                    let handle = Handle(handle);
                    if image(handle.0).as_ref() == Some(expected) {
                        let _ = TerminateProcess(handle.0, 1);
                    }
                }
            }
        }
    }
    loop {
        let left = targets(scope.as_deref(), &workers)?;
        if left.is_empty() {
            return Ok(Vec::new());
        }
        if start.elapsed() >= limit {
            return Ok(left.into_iter().map(|p| p.pid).collect());
        }
        std::thread::sleep(Duration::from_millis(75));
    }
}
pub fn option(args: &[String], name: &str) -> Result<Option<String>> {
    if let Some(index) = args.iter().position(|v| v == name) {
        let value = args
            .get(index + 1)
            .context("Missing command option value")?;
        if value.starts_with("--") {
            bail!("Missing command option value")
        };
        Ok(Some(value.clone()))
    } else {
        Ok(None)
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn only_application_process_names_are_matched() {
        for name in ["OpenDesk.exe", "OpenDesk_v3.0.0_Portable.exe"] {
            assert!(application_name(name));
        }
        for name in [
            "OpenDeskSetupHelper.exe",
            "OpenDesk_Setup_v3.0.0_Installer.exe",
            "python.exe",
            "other-opendesk.exe",
            "OpenDesk_v3.0_Portable.exe",
        ] {
            assert!(!application_name(name));
        }
    }
    #[test]
    fn windows_paths_compare_case_insensitively() {
        assert_eq!(
            normalize(Path::new(r"\\?\C:\Users\Test\OpenDesk")),
            normalize(Path::new(r"c:\users\test\OpenDesk\"))
        );
    }
}
