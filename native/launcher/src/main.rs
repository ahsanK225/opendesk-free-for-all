#![windows_subsystem = "windows"]
mod update;
fn run() -> anyhow::Result<i32> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.iter().any(|v| v == "--apply") {
        return update::run(&args);
    }
    if !args.iter().any(|v| v == "--shutdown") {
        anyhow::bail!("This helper requires --shutdown")
    };
    let timeout = opendesk_launcher::option(&args, "--timeout")?
        .map(|v| v.parse::<f64>())
        .transpose()?
        .unwrap_or(8.0);
    if !timeout.is_finite() {
        anyhow::bail!("Invalid shutdown timeout")
    };
    let scope = opendesk_launcher::option(&args, "--install-dir")?.map(std::path::PathBuf::from);
    let suffix = opendesk_launcher::option(&args, "--instance-suffix")?.unwrap_or_default();
    let left = opendesk_launcher::shutdown(
        args.iter().any(|v| v == "--force"),
        timeout,
        scope.as_deref(),
        &suffix,
    )?;
    if let Some(path) = opendesk_launcher::option(&args, "--result-file")? {
        std::fs::write(
            path,
            format!(
                "{{\"closed\":{},\"remaining_pids\":[{}]}}",
                left.is_empty(),
                left.iter()
                    .map(u32::to_string)
                    .collect::<Vec<_>>()
                    .join(",")
            ),
        )?;
    }
    Ok(if left.is_empty() { 0 } else { 1 })
}
fn main() {
    std::process::exit(match run() {
        Ok(code) => code,
        Err(error) => {
            eprintln!("OpenDesk maintenance: {error:#}");
            if std::env::args().any(|v| v == "--apply")
                && let Ok(exe) = std::env::current_exe()
                && let Some(parent) = exe.parent()
            {
                let _ = std::fs::write(parent.join("update-error.txt"), format!("{error:#}"));
            }
            if std::env::args().any(|v| v == "--apply")
                && !std::env::args().any(|v| v == "--no-error-dialog")
            {
                use windows::{Win32::UI::WindowsAndMessaging::*, core::PCWSTR};
                let message = opendesk_launcher::wide(&format!(
                    "The OpenDesk update could not finish.\n\n{error:#}"
                ));
                let title = opendesk_launcher::wide("OpenDesk update");
                unsafe {
                    MessageBoxW(
                        None,
                        PCWSTR(message.as_ptr()),
                        PCWSTR(title.as_ptr()),
                        MB_OK | MB_ICONERROR,
                    );
                }
            }
            2
        }
    })
}
