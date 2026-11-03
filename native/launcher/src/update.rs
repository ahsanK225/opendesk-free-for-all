use anyhow::{Context, Result, bail};
use opendesk_launcher::{Handle, option, wide};
use sha2::{Digest, Sha256};
use std::{
    fs,
    io::Read,
    path::PathBuf,
    time::{Duration, Instant},
};
use windows::{
    Win32::{Foundation::*, Storage::FileSystem::*, System::Threading::*},
    core::PCWSTR,
};
fn required(args: &[String], name: &str) -> Result<String> {
    option(args, name)?.with_context(|| format!("Missing {name}"))
}
fn wait_process(pid: u32) -> Result<()> {
    if pid == 0 || pid == std::process::id() {
        bail!("Invalid update parent")
    }
    unsafe {
        match OpenProcess(PROCESS_SYNCHRONIZE, false, pid) {
            Ok(handle) => {
                let handle = Handle(handle);
                if WaitForSingleObject(handle.0, 30000) != WAIT_OBJECT_0 {
                    bail!("OpenDesk did not close within 30 seconds; the update was not applied")
                }
            }
            Err(error)
                if error.code()
                    == windows::core::HRESULT::from_win32(ERROR_INVALID_PARAMETER.0) => {}
            Err(error) => return Err(error.into()),
        }
    }
    Ok(())
}
fn verify(path: &std::path::Path, expected: &str) -> Result<()> {
    if expected.len() != 64 || !expected.bytes().all(|b| b.is_ascii_hexdigit()) {
        bail!("Invalid update checksum")
    }
    let mut file = fs::File::open(path)?;
    let size = file.metadata()?.len();
    if !(1024..=512 * 1024 * 1024).contains(&size) {
        bail!("Invalid update size")
    }
    let mut magic = [0; 2];
    file.read_exact(&mut magic)?;
    if magic != *b"MZ" {
        bail!("The update is not a Windows executable")
    }
    let mut hash = Sha256::new();
    hash.update(magic);
    let mut buffer = [0; 65536];
    loop {
        let count = file.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        hash.update(&buffer[..count]);
    }
    if hex::encode(hash.finalize()) != expected.to_ascii_lowercase() {
        bail!("The update changed after download; the installed application was preserved")
    }
    Ok(())
}
pub fn run(args: &[String]) -> Result<i32> {
    let source = fs::canonicalize(required(args, "--source")?)?;
    let expected = required(args, "--sha256")?;
    verify(&source, &expected)?;
    wait_process(required(args, "--parent-pid")?.parse()?)?;
    if let Some(pid) = option(args, "--launcher-pid")? {
        wait_process(pid.parse()?)?;
    }
    let own = fs::canonicalize(std::env::current_exe()?)?;
    if source.parent() != own.parent() {
        bail!("The staged update and helper must be in the same directory")
    }
    if let Some(target) = option(args, "--portable-target")? {
        if option(args, "--installer-dir")?.is_some() {
            bail!("Conflicting update modes")
        }
        let target = PathBuf::from(target);
        if !target.is_absolute()
            || !target.is_file()
            || target
                .extension()
                .is_none_or(|v| !v.eq_ignore_ascii_case("exe"))
        {
            bail!("The portable application is unavailable")
        }
        let parent = target.parent().context("Missing portable directory")?;
        let backup = source.with_file_name("previous-portable.exe");
        fs::copy(&target, &backup)?;
        let temporary = parent.join(format!(
            ".opendesk-update-{}-{}.exe",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)?
                .as_nanos()
        ));
        fs::copy(&source, &temporary)?;
        verify(&temporary, &expected)?;
        unsafe {
            MoveFileExW(
                PCWSTR(wide(&temporary.to_string_lossy()).as_ptr()),
                PCWSTR(wide(&target.to_string_lossy()).as_ptr()),
                MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH,
            )?;
        }
        if let Err(error) = std::process::Command::new(&target).spawn() {
            let _ = fs::copy(&backup, &target);
            return Err(error.into());
        }
    } else {
        let directory = fs::canonicalize(required(args, "--installer-dir")?)?;
        if !directory.join("OpenDesk.exe").is_file() || !directory.join("unins000.exe").is_file() {
            bail!("The target is not an installed OpenDesk directory")
        }
        let mut installer = std::process::Command::new(&source)
            .args(["/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"])
            .arg(format!("/DIR={}", directory.display()))
            .spawn()?;
        let started = Instant::now();
        loop {
            if let Some(status) = installer.try_wait()? {
                if !matches!(status.code(), Some(0 | 3010)) {
                    bail!(
                        "The installer returned {:?}. Your device settings were preserved.",
                        status.code()
                    )
                }
                break;
            }
            if started.elapsed() > Duration::from_secs(300) {
                bail!("The installer is still running. Check its window before launching OpenDesk.")
            }
            std::thread::sleep(Duration::from_millis(250));
        }
        std::process::Command::new(directory.join("OpenDesk.exe")).spawn()?;
    }
    Ok(0)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rejects_short_digest_before_opening_a_file() {
        assert!(verify(std::path::Path::new("missing.exe"), "bad").is_err());
    }
}
