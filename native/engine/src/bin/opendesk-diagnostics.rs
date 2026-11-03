fn main() -> anyhow::Result<()> {
    let args: Vec<String> = std::env::args().collect();
    let report = opendesk_engine::diagnostics::report(args.iter().any(|arg| arg == "--capture"))?;
    let text = serde_json::to_string_pretty(&report)?;
    if let Some(index) = args.iter().position(|arg| arg == "--output") {
        std::fs::write(
            args.get(index + 1)
                .ok_or_else(|| anyhow::anyhow!("Missing output path"))?,
            &text,
        )?;
    }
    println!("{text}");
    Ok(())
}
