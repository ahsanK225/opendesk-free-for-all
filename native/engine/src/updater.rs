//! Automatic, hash-verified updates. Application exit and replacement are separate processes.
use crate::{app::Shared, store};
use anyhow::{Context, Result, bail};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    path::PathBuf,
    sync::{Arc, atomic::Ordering},
    time::Duration,
};
use tokio::io::AsyncWriteExt;
const METADATA: &str =
    "https://raw.githubusercontent.com/ahsanK225/opendesk-free-for-all/main/version.json";
const RELEASE: &str = "https://github.com/ahsanK225/opendesk-free-for-all/releases/download/";
const CANCELLED: &str = "Update cancelled.";
fn stable_version(value: &str) -> Option<(u32, u32, u32)> {
    let pieces: Vec<_> = value.split('.').collect();
    if !(2..=3).contains(&pieces.len())
        || pieces
            .iter()
            .any(|v| v.is_empty() || v.len() > 5 || !v.bytes().all(|c| c.is_ascii_digit()))
    {
        return None;
    }
    Some((
        pieces[0].parse().ok()?,
        pieces[1].parse().ok()?,
        pieces.get(2).unwrap_or(&"0").parse().ok()?,
    ))
}
fn validate(value: &Value, portable: bool) -> Result<(String, String, String)> {
    let version = value["version"]
        .as_str()
        .context("The release version is missing")?;
    let next = stable_version(version).context("The release version is invalid")?;
    let current = stable_version(env!("CARGO_PKG_VERSION").split('-').next().unwrap()).unwrap();
    if next < current || (next == current && !env!("CARGO_PKG_VERSION").contains('-')) {
        bail!("You already have the latest version")
    }
    let (url_key, hash_key) = if portable {
        ("download_url", "sha256")
    } else {
        ("installer_url", "installer_sha256")
    };
    let url = value[url_key]
        .as_str()
        .context("The release download is missing")?;
    let filename = if portable {
        format!("OpenDesk_v{version}_Portable.exe")
    } else {
        format!("OpenDesk_Setup_v{version}_Installer.exe")
    };
    if url != format!("{RELEASE}v{version}/{filename}") {
        bail!("The release download does not match the official repository")
    }
    let hash = value[hash_key].as_str().unwrap_or("").to_ascii_lowercase();
    if hash.len() != 64 || !hash.bytes().all(|c| c.is_ascii_hexdigit()) {
        bail!("The release checksum is invalid")
    }
    Ok((version.into(), url.into(), hash))
}
fn client() -> Result<reqwest::Client> {
    Ok(reqwest::Client::builder()
        .dns_resolver(std::sync::Arc::new(crate::net::Resolver))
        .user_agent(concat!("OpenDesk/", env!("CARGO_PKG_VERSION")))
        .https_only(true)
        .connect_timeout(Duration::from_secs(15))
        // A stalled read fails; a slow connection may take as long as it needs.
        .read_timeout(Duration::from_secs(30))
        .build()?)
}
async fn metadata(client: &reqwest::Client) -> Result<Value> {
    let response = client
        .get(METADATA)
        .timeout(Duration::from_secs(20))
        .send()
        .await?
        .error_for_status()?;
    let bytes = response.bytes().await?;
    if bytes.len() > 65536 {
        bail!("The release metadata is too large")
    }
    Ok(serde_json::from_slice(&bytes)?)
}
/// Installing closes the app, so it must not happen while someone is connected in either direction.
fn session_active(shared: &Shared) -> bool {
    let view = shared.view.lock().unwrap();
    view["hostSession"].is_object()
        || view["incoming"].is_object()
        || view["connections"].as_array().is_some_and(|items| items.iter().any(|item| matches!(item["state"].as_str(), Some("connecting" | "connected"))))
}
/// Looks for a release soon after start and every half hour, and installs it by itself when no
/// session is open. Finding nothing stays silent. After a cancel or a failure it waits for the next start.
pub fn check_on_start(shared: Arc<Shared>) {
    if cfg!(test) || !cfg!(feature = "full") || std::env::var_os("OPENDESK_DEV_NO_TUNNEL").is_some() {
        return;
    }
    tokio::spawn(async move {
        tokio::time::sleep(Duration::from_secs(8)).await;
        let mut stopped = false;
        while !shared.stop.load(Ordering::Acquire) {
            if !stopped && !shared.update_busy.swap(true, Ordering::AcqRel) {
                if perform(shared.clone(), false, false).await.is_ok() && !session_active(&shared) {
                    shared.update_cancel.store(false, Ordering::Release);
                    shared.update(|v|v["update"]=json!({"state":"downloading","done":0,"total":0,"message":"Downloading the update…"}));
                    if let Err(error) = perform(shared.clone(), true, true).await {
                        stopped = true;
                        let message = format!("{error:#}");
                        let state = if message != CANCELLED { "failed" } else { "idle" };
                        shared.update(|v| v["update"] = json!({"state":state,"message":message}));
                    }
                }
                shared.update_busy.store(false, Ordering::Release);
            }
            tokio::time::sleep(Duration::from_secs(30 * 60)).await;
        }
    });
}
pub fn start(shared: Arc<Shared>, install: bool) {
    // The published manifest describes the Full edition only.
    if !cfg!(feature = "full") {
        shared.update(|v| v["update"] = json!({"state":"idle","message":"OpenDesk Lite is updated manually by installing a newer Lite package."}));
        return;
    }
    if shared.update_busy.swap(true, Ordering::AcqRel) {
        return;
    }
    shared.update_cancel.store(false, Ordering::Release);
    shared.update(|v|v["update"]=json!({"state":if install{"downloading"}else{"checking"},"done":0,"total":0,"message":if install{"Downloading the update…"}else{"Checking for updates…"}}));
    tokio::spawn(async move {
        let result = perform(shared.clone(), install, false).await;
        if let Err(error) = result {
            let message = format!("{error:#}");
            let state = if install && message != CANCELLED { "failed" } else { "idle" };
            shared.update(|v| v["update"] = json!({"state":state,"message":message}));
        }
        shared.update_busy.store(false, Ordering::Release);
    });
}
async fn perform(shared: Arc<Shared>, install: bool, automatic: bool) -> Result<()> {
    let portable = std::env::var_os("OPENDESK_PORTABLE_LAUNCHER").map(PathBuf::from);
    let client = client()?;
    let value = metadata(&client).await?;
    let (version, url, expected) = validate(&value, portable.is_some())?;
    if !install {
        shared.update(|v|v["update"]=json!({"state":"available","version":version,"notes":value["changelog"],"message":format!("OpenDesk {version} is available.")}));
        return Ok(());
    }
    let executable = std::env::current_exe()?;
    let directory = executable
        .parent()
        .context("The application directory is unavailable")?;
    let helper = directory.join("OpenDeskSetupHelper.exe");
    if !helper.is_file() {
        bail!("The update helper is missing. Repair or reinstall OpenDesk.")
    }
    if portable.is_none() && !directory.join("unins000.exe").is_file() {
        bail!(
            "Updates can be installed from a packaged installation or portable launcher. This is a development build."
        )
    }
    let stage = PathBuf::from(
        std::env::var_os("LOCALAPPDATA").context("Local application data is unavailable")?,
    )
    .join("OpenDesk/updates")
    .join(store::token());
    tokio::fs::create_dir_all(&stage).await?;
    let download = stage.join("release.exe");
    let result=async {
        let mut response=client.get(url).send().await?.error_for_status()?;
        if response.content_length().is_some_and(|n|n>512*1024*1024) { bail!("The update exceeds its size limit") }
        let mut output=tokio::fs::OpenOptions::new().write(true).create_new(true).open(&download).await?;
        let mut hash=Sha256::new();let mut size=0usize;
        let total=response.content_length().unwrap_or(0);let started=std::time::Instant::now();let mut shown=started;
        while let Some(chunk)=response.chunk().await? {
            if shared.update_cancel.swap(false,Ordering::AcqRel){bail!(CANCELLED)}
            size=size.checked_add(chunk.len()).context("Invalid download size")?;if size>512*1024*1024||shared.stop.load(Ordering::Acquire){bail!("Update cancelled or too large")};output.write_all(&chunk).await?;hash.update(&chunk);
            if shown.elapsed()>=Duration::from_millis(200){shown=std::time::Instant::now();let speed=size as f64/started.elapsed().as_secs_f64().max(0.001);shared.update(|v|v["update"]=json!({"state":"downloading","version":version,"done":size,"total":total,"speed":speed,"message":"Downloading the update…"}));}
        }
        shared.update(|v|v["update"]=json!({"state":"verifying","version":version,"done":size,"total":total,"message":"Checking the download…"}));
        output.sync_all().await?;drop(output);
        if size<1024 || hex::encode(hash.finalize())!=expected { bail!("The update checksum did not match. The installed application was preserved.") }
        if automatic&&session_active(&shared){
            shared.update(|v|v["update"]=json!({"state":"waiting","version":version,"message":"The update is ready and installs when this session ends."}));
            while session_active(&shared){if shared.stop.load(Ordering::Acquire){bail!("Update cancelled or too large")};tokio::time::sleep(Duration::from_secs(5)).await;}
        }
        let updater=stage.join("OpenDeskSetupHelper.exe");tokio::fs::copy(helper,&updater).await?;
        let mut process=std::process::Command::new(updater);
        process.args(["--apply","--parent-pid",&std::process::id().to_string(),"--source"]).arg(&download).args(["--sha256",&expected]);
        if let Some(target)=portable { process.arg("--portable-target").arg(target);if let Ok(pid)=std::env::var("OPENDESK_PORTABLE_PID"){process.args(["--launcher-pid",&pid]);} }
        else {process.arg("--installer-dir").arg(directory);}
        use std::os::windows::process::CommandExt;
        process.creation_flags(0x08000000).stdin(std::process::Stdio::null()).stdout(std::process::Stdio::null()).stderr(std::process::Stdio::null()).spawn()?;
        shared.update(|v|{v["update"]=json!({"state":"installing","message":"Restarting to install the verified update…"});v["exitRequested"]=json!(true);});
        Ok::<(),anyhow::Error>(())
    }.await;
    if result.is_err() {
        let _ = tokio::fs::remove_dir_all(&stage).await;
    }
    result
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn sequential_versions_compare_numerically() {
        assert_eq!(stable_version("2.8"), Some((2, 8, 0)));
        assert_eq!(stable_version("2.8.0"), stable_version("2.8"));
        assert!(stable_version("2.9") < stable_version("3.0"));
        assert!(stable_version("2.8") > stable_version("2.0.2"));
        for invalid in ["2", "2.8-alpha", "2..8", "2.8.0.1"] {
            assert!(stable_version(invalid).is_none());
        }
        let value = json!({"version":"99.0","download_url":format!("{RELEASE}v99.0/OpenDesk_v99.0_Portable.exe"),"sha256":"a".repeat(64)});
        assert!(validate(&value, true).is_ok());
    }
    #[test]
    fn rejects_foreign_asset_and_downgrade() {
        let mut value = json!({"version":"99.0.0","download_url":format!("{RELEASE}v99.0.0/OpenDesk_v99.0.0_Portable.exe"),"sha256":"a".repeat(64)});
        assert!(validate(&value, true).is_ok());
        value["download_url"] = json!("https://evil.invalid/app.exe");
        assert!(validate(&value, true).is_err());
        value["version"] = json!("2.0.2");
        assert!(validate(&value, true).is_err());
    }
}
