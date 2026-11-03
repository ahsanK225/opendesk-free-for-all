#![windows_subsystem = "windows"]
use anyhow::{Context, Result, bail};
use opendesk_launcher::{Handle, wide};
use sha2::{Digest, Sha256};
use std::{
    fs,
    io::Cursor,
    path::{Path, PathBuf},
    time::Duration,
};
use windows::{
    Win32::{
        Foundation::*,
        System::{LibraryLoader::SetDllDirectoryW, Threading::*},
        UI::WindowsAndMessaging::*,
    },
    core::PCWSTR,
};
const PAYLOAD: &[u8] = include_bytes!(env!("OPENDESK_PAYLOAD_ZIP"));
fn validate_loader_paths(cache: &Path) -> Result<()> {
    let mut archive = zip::ZipArchive::new(Cursor::new(PAYLOAD))?;
    for index in 0..archive.len() {
        let entry = archive.by_index(index)?;
        let name = entry
            .enclosed_name()
            .context("Unsafe runtime package path")?;
        if name
            .extension()
            .is_some_and(|ext| ext.eq_ignore_ascii_case("dll"))
            && cache.join(name).to_string_lossy().encode_utf16().count() >= 248
        {
            bail!(
                "The Windows runtime cache path is too long for Qt plugins. Set OPENDESK_RUNTIME_DIR to a shorter absolute, writable local directory and try again. Your settings were preserved."
            )
        }
    }
    Ok(())
}
fn cache_valid(path: &Path, hash: &str) -> bool {
    if fs::read_to_string(path.join(".opendesk-runtime"))
        .ok()
        .as_deref()
        != Some(hash)
    {
        return false;
    }
    let Ok(mut archive) = zip::ZipArchive::new(Cursor::new(PAYLOAD)) else {
        return false;
    };
    (0..archive.len()).all(|index| {
        archive.by_index(index).is_ok_and(|entry| {
            entry
                .enclosed_name()
                .is_some_and(|name| entry.is_dir() || path.join(name).is_file())
        })
    })
}
fn unpack(base: &Path, path: &Path, hash: &str) -> Result<()> {
    fs::create_dir_all(base)?;
    let nonce = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)?
        .as_nanos();
    let staging = base.join(format!(".staging-{}-{nonce}", std::process::id()));
    if staging.exists() {
        bail!(
            "A previous extraction is incomplete; remove only the OpenDesk staging directory and retry"
        )
    };
    fs::create_dir(&staging)?;
    let result = (|| -> Result<()> {
        let mut archive = zip::ZipArchive::new(Cursor::new(PAYLOAD))?;
        if archive.len() > 5000 {
            bail!("Invalid portable package")
        };
        let mut total = 0u64;
        for index in 0..archive.len() {
            let mut entry = archive.by_index(index)?;
            let name = entry.enclosed_name().context("Unsafe package path")?;
            if entry
                .unix_mode()
                .is_some_and(|mode| mode & 0o170000 == 0o120000)
            {
                bail!("Package links are not allowed")
            };
            total = total
                .checked_add(entry.size())
                .context("Invalid package size")?;
            if total > 1024 * 1024 * 1024 {
                bail!("Portable package is too large")
            };
            let destination = staging.join(name);
            if entry.is_dir() {
                fs::create_dir_all(destination)?;
                continue;
            }
            if let Some(parent) = destination.parent() {
                fs::create_dir_all(parent)?;
            }
            let mut file = fs::OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(&destination)?;
            let copied = std::io::copy(&mut entry, &mut file)?;
            if copied != entry.size() {
                bail!("Truncated portable package")
            };
            // Flush executable code before publication. Hundreds of immutable
            // license/QML files need not each force a separate physical disk flush.
            if destination.extension().is_some_and(|ext| {
                ext.eq_ignore_ascii_case("dll") || ext.eq_ignore_ascii_case("exe")
            }) {
                file.sync_all()?;
            }
        }
        if !staging.join("OpenDesk.exe").is_file() {
            bail!("Native application is missing from the package")
        };
        use std::io::Write;
        let mut marker = fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(staging.join(".opendesk-runtime"))?;
        marker.write_all(hash.as_bytes())?;
        marker.sync_all()?;
        drop(marker);
        if path.exists() {
            let old = base.join(format!(".replaced-{}-{nonce}", std::process::id()));
            if old.exists() {
                bail!("A previous runtime repair needs cleanup")
            };
            fs::rename(path, &old)?;
            if let Err(error) = fs::rename(&staging, path) {
                let _ = fs::rename(&old, path);
                return Err(error.into());
            }
            let canonical = fs::canonicalize(&old)?;
            if canonical.parent() == Some(fs::canonicalize(base)?.as_path()) {
                let _ = fs::remove_dir_all(canonical);
            }
        } else {
            fs::rename(&staging, path)?;
        }
        Ok(())
    })();
    if result.is_err()
        && let (Ok(path), Ok(base)) = (fs::canonicalize(&staging), fs::canonicalize(base))
        && path.parent() == Some(base.as_path())
    {
        let _ = fs::remove_dir_all(path);
    }
    result
}
fn run() -> Result<i32> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let isolated = args.iter().any(|arg| arg == "--config-dir");
    if !isolated && opendesk_launcher::activate_existing()? {
        return Ok(0);
    }
    let hash = hex::encode(Sha256::digest(PAYLOAD));
    let local = std::env::var_os("LOCALAPPDATA")
        .context("Local application data directory is unavailable")?;
    let base = std::env::var_os("OPENDESK_RUNTIME_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from(local).join("OpenDesk/runtimes"));
    if !base.is_absolute() {
        bail!("OPENDESK_RUNTIME_DIR must be an absolute directory path")
    }
    let cache = base.join(format!("3.0.0-{}", &hash[..12]));
    validate_loader_paths(&cache)?;
    let name = opendesk_launcher::instance_name(".extract")?;
    let mutex = Handle(unsafe { CreateMutexW(None, false, PCWSTR(wide(&name).as_ptr()))? });
    let wait = unsafe { WaitForSingleObject(mutex.0, 30000) };
    if wait != WAIT_OBJECT_0 && wait != WAIT_ABANDONED {
        bail!("Another launcher is preparing the runtime. Retry shortly.")
    }
    let force = args.iter().any(|arg| arg == "--repair");
    let prepared = if force || !cache_valid(&cache, &hash) {
        unpack(&base, &cache, &hash)
    } else {
        Ok(())
    };
    unsafe {
        let _ = ReleaseMutex(mutex.0);
    }
    prepared?;
    if !isolated && opendesk_launcher::activate_existing()? {
        return Ok(0);
    }
    let launcher = std::env::current_exe()?;
    let forwarded: Vec<_> = args
        .iter()
        .filter(|arg| !matches!(arg.as_str(), "--repair" | "--no-error-dialog"))
        .collect();
    unsafe {
        SetDllDirectoryW(PCWSTR::null())?;
    }
    let launch_directory = cache.clone();
    let mut command = std::process::Command::new(launch_directory.join("OpenDesk.exe"));
    command
        .args(forwarded)
        .current_dir(&launch_directory)
        .env("OPENDESK_PORTABLE_LAUNCHER", launcher)
        .env("OPENDESK_PORTABLE_PID", std::process::id().to_string());
    for (key, _) in std::env::vars() {
        if key.to_ascii_uppercase().starts_with("_PYI_")
            || key.to_ascii_uppercase().starts_with("_MEIPASS")
            || matches!(
                key.to_ascii_uppercase().as_str(),
                "QT_PLUGIN_PATH" | "QML_IMPORT_PATH" | "QML2_IMPORT_PATH"
            )
        {
            command.env_remove(key);
        }
    }
    let status = command
        .spawn()
        .context("Native desktop could not start")?
        .wait()?;
    if !status.success() {
        bail!(
            "The native desktop exited with code {:?}. Launch this portable executable with --repair to restore its runtime. Your device settings were preserved.",
            status.code()
        )
    }
    Ok(0)
}
fn main() {
    let result = run();
    let code = match result {
        Ok(code) => code,
        Err(error) => {
            let message = format!(
                "OpenDesk could not start.\n\n{error:#}\n\nYour device settings have not been removed."
            );
            if !std::env::args().any(|arg| arg == "--no-error-dialog") {
                unsafe {
                    MessageBoxW(
                        None,
                        PCWSTR(wide(&message).as_ptr()),
                        PCWSTR(wide("OpenDesk launcher").as_ptr()),
                        MB_OK | MB_ICONERROR,
                    );
                }
            }
            eprintln!("{message}");
            1
        }
    };
    std::thread::sleep(Duration::from_millis(10));
    std::process::exit(code)
}
