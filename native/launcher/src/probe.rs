#![windows_subsystem = "windows"]
fn main() -> anyhow::Result<()> {
    let directory = std::env::current_exe()?.parent().unwrap().to_path_buf();
    if directory.join(".update-fixture").is_file() {
        std::fs::write(
            directory.join("updated-ready.txt"),
            "native replacement launched",
        )?;
        return Ok(());
    }
    let args: Vec<String> = std::env::args().skip(1).collect();
    let suffix =
        opendesk_launcher::option(&args, "--suffix")?.unwrap_or_else(|| "installer-smoke".into());
    let instance = opendesk_launcher::Instance::new(&suffix)?;
    if let Some(path) = opendesk_launcher::option(&args, "--output")? {
        std::fs::write(
            path,
            format!(
                "{{\"pid\":{},\"primary\":{}}}",
                std::process::id(),
                instance.primary
            ),
        )?;
    }
    if instance.primary {
        let start = std::time::Instant::now();
        while start.elapsed() < std::time::Duration::from_secs(90) {
            if !args.iter().any(|v| v == "--ignore-shutdown") && instance.shutdown_requested() {
                break;
            }
            std::thread::sleep(std::time::Duration::from_millis(25));
        }
    }
    Ok(())
}
