use crate::{
    app::Shared,
    store::{self, clean_id},
};
use anyhow::{Context, Result, bail};
use base64::{Engine, engine::general_purpose::STANDARD as B64};
use ed25519_dalek::{Signature, Verifier, VerifyingKey};
use reqwest::{Client, Url};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    path::PathBuf,
    sync::{Arc, atomic::Ordering},
    time::Duration,
};
use tokio::{
    io::{AsyncBufReadExt, BufReader},
    process::Command,
};
const BINARY_SHA: &str = "f096265ec2fcbe9bb6e2d64268db167ced3fcbb83d894bdb9e2fcdb26f2ea7e2";
pub fn http() -> Result<Client> {
    Ok(Client::builder()
        .timeout(Duration::from_secs(7))
        .user_agent("OpenDesk/3.0")
        .build()?)
}
pub fn ws_url(address: &str) -> Result<String> {
    let raw = address.trim();
    let explicit = raw.contains("://");
    let mut url = Url::parse(&if explicit {
        raw.to_owned()
    } else {
        format!("https://{raw}")
    })?;
    if !matches!(url.scheme(), "https" | "http" | "ws" | "wss")
        || url.host_str().is_none()
        || !url.username().is_empty()
        || url.password().is_some()
        || !matches!(url.path(), "" | "/" | "/ws")
        || url.query().is_some()
        || url.fragment().is_some()
    {
        bail!("Invalid remote address")
    }
    let local = url.host_str().is_some_and(|host| {
        host == "localhost"
            || host.parse::<std::net::IpAddr>().is_ok_and(|ip| {
                ip.is_loopback()
                    || match ip {
                        std::net::IpAddr::V4(ip) => ip.is_private() || ip.is_link_local(),
                        std::net::IpAddr::V6(ip) => {
                            ip.is_unique_local() || ip.is_unicast_link_local()
                        }
                    }
            })
    });
    let scheme = if matches!(url.scheme(), "http" | "ws") || (!explicit && local) {
        "ws"
    } else {
        "wss"
    };
    if scheme == "ws" && !local {
        bail!("Public connections require HTTPS/WSS")
    }
    url.set_scheme(scheme)
        .map_err(|_| anyhow::anyhow!("Invalid URL scheme"))?;
    url.set_path("/ws");
    Ok(url.to_string())
}
pub fn read_record(record: &str, id: &str, pinned: Option<&str>) -> Result<(String, String)> {
    let packet: Value = serde_json::from_str(record)?;
    let key = packet["key"].as_str().context("Missing directory key")?;
    if pinned.is_some_and(|p| p != key) {
        bail!("Saved device key changed")
    }
    let bytes: [u8; 32] = B64
        .decode(key)?
        .try_into()
        .map_err(|_| anyhow::anyhow!("Invalid directory key"))?;
    let body = packet["body"]
        .as_str()
        .context("Missing directory record")?;
    if body.len() > 4096 {
        bail!("Oversized directory record")
    }
    VerifyingKey::from_bytes(&bytes)?.verify(
        body.as_bytes(),
        &Signature::from_slice(&B64.decode(packet["signature"].as_str().unwrap_or(""))?)?,
    )?;
    let record: Value = serde_json::from_str(body)?;
    let expires = record["expires"].as_u64().unwrap_or(0);
    let now = store::now();
    let url = Url::parse(record["url"].as_str().unwrap_or(""))?;
    if record["id"] != id
        || expires <= now
        || expires > now + 180
        || url.scheme() != "https"
        || !url
            .host_str()
            .is_some_and(|host| host.ends_with(".trycloudflare.com"))
        || !url.username().is_empty()
        || url.password().is_some()
        || url.port().is_some_and(|p| p != 443)
        || !matches!(url.path(), "" | "/")
        || url.query().is_some()
        || url.fragment().is_some()
    {
        bail!("Directory record is expired or invalid")
    }
    Ok((ws_url(url.as_str())?, key.into()))
}
pub async fn resolve(shared: &Shared, target: &str) -> Result<(String, String, Option<String>)> {
    let (id, address) = if let Some((id, address)) = target.split_once('@') {
        (clean_id(id), address)
    } else {
        ("remote_host".into(), target)
    };
    if address.contains(['.', ':']) || address == "localhost" {
        return Ok((id, ws_url(address)?, None));
    }
    let id = clean_id(target);
    if id.len() != 9 || !id.bytes().all(|b| b.is_ascii_digit()) {
        bail!("Enter a nine-digit device ID or a share URL")
    }
    let pinned = shared.store.lock().unwrap().config["trusted_devices"][&id]
        .as_str()
        .map(str::to_owned);
    let client = http()?;
    for _ in 0..2 {
        if let Ok(response) = client
            .get(format!("https://ntfy.sh/opendesk_node_{id}/raw?poll=1"))
            .send()
            .await
            && let Ok(text) = response.text().await
            && text.len() < 64 * 1024
        {
            for line in text.lines().rev() {
                if let Ok((url, key)) = read_record(line, &id, pinned.as_deref()) {
                    return Ok((id, url, Some(key)));
                }
            }
        }
        if let Ok(response) = client
            .get(format!(
                "https://keyvalue.immanuel.co/api/KeyVal/GetValue/s460x9wm/{id}"
            ))
            .send()
            .await
            && let Ok(text) = response.text().await
            && text.len() < 16 * 1024
        {
            let text = text.trim().trim_matches('"').replace('-', "/");
            let padded = format!("{text}{}", "=".repeat((4 - text.len() % 4) % 4));
            if let Ok(bytes) = B64.decode(padded)
                && let Ok((url, key)) =
                    read_record(&String::from_utf8_lossy(&bytes), &id, pinned.as_deref())
            {
                return Ok((id, url, Some(key)));
            }
        }
    }
    bail!("The desktop is offline or its signed directory record has expired.")
}
fn binary() -> Option<PathBuf> {
    let current = std::env::current_exe().ok()?;
    let directory = current.parent()?;
    let paths = [
        directory.join("bin/cloudflared.exe"),
        directory.join("cloudflared.exe"),
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../bin/cloudflared.exe"),
    ];
    paths.into_iter().find(|path| {
        std::fs::read(path).is_ok_and(|bytes| hex::encode(Sha256::digest(bytes)) == BINARY_SHA)
    })
}
pub async fn tunnel(shared: Arc<Shared>, port: u16) {
    let Some(binary) = binary() else {
        shared.update(|v| {
            v["tunnelMessage"] =
                json!("Verified tunnel binary is unavailable; local access is ready.")
        });
        return;
    };
    let mut delay = 1;
    while !shared.stop.load(Ordering::Acquire) {
        let public = shared.store.lock().unwrap().config["native_settings"]["publicAccess"]
            .as_bool()
            .unwrap_or(true);
        if !public {
            tokio::time::sleep(Duration::from_secs(1)).await;
            continue;
        }
        let mut command = Command::new(&binary);
        command
            .args(["tunnel", "--url", &format!("http://127.0.0.1:{port}")])
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::piped())
            .kill_on_drop(true)
            .creation_flags(0x08000000);
        match command.spawn() {
            Ok(mut process) => {
                let mut lines = BufReader::new(process.stderr.take().unwrap()).lines();
                let mut interval = tokio::time::interval(Duration::from_secs(1));
                let mut url = String::new();
                let mut published = 0;
                loop {
                    tokio::select! {
                                            line=lines.next_line()=>{
                    match line{
                    Ok(Some(line))=>{
                    if let Some(index)=line.find("https://"){
                    let candidate=line[index..].split(|c:char|c.is_whitespace()||c=='|'||c=='"').next().unwrap_or("");if let Ok(parsed)=Url::parse(candidate)&& parsed.host_str().is_some_and(|h|h.ends_with(".trycloudflare.com"))&&parsed.path()=="/"{url=candidate.into();delay=1;shared.update(|v|{v["shareUrl"]=json!(url);v["tunnelMessage"]=Value::Null;});}}},_=>break}},
                                            _=interval.tick()=>{
                                                if shared.stop.load(Ordering::Acquire)||!shared.store.lock().unwrap().config["native_settings"]["publicAccess"].as_bool().unwrap_or(true){let _=process.kill().await;break}
                                                if !url.is_empty()&&store::now().saturating_sub(published)>=30{
                    published=store::now();
                    let (id,record)={
                    let store=shared.store.lock().unwrap();
                    (store.id(),store.directory_record(&url).to_string())}
                    ;
                    tokio::spawn(async move{
                    if let Ok(client)=http(){
                    let first=client.post(format!("https://ntfy.sh/opendesk_node_{id}")).body(record.clone()).send();
                    let encoded=B64.encode(record).replace('=',"").replace('/',"-");
                    let second=client.post(format!("https://keyvalue.immanuel.co/api/KeyVal/UpdateValue/s460x9wm/{id}/{encoded}")).send();
                    let _=tokio::join!(first,second);
                    }
                    }
                    );
                    }

                                            }
                                        }
                }
                let _ = process.kill().await;
                let _ = process.wait().await;
            }
            Err(error) => {
                shared
                    .update(|v| v["tunnelMessage"] = json!(format!("Tunnel unavailable: {error}")));
            }
        }
        shared.update(|v| v["shareUrl"] = json!(""));
        tokio::time::sleep(Duration::from_secs(delay)).await;
        delay = (delay * 2).min(30);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rejects_public_plaintext_and_userinfo() {
        assert!(ws_url("http://example.com").is_err());
        assert!(ws_url("https://a:b@example.com").is_err());
        assert_eq!(ws_url("127.0.0.1:8080").unwrap(), "ws://127.0.0.1:8080/ws");
        assert!(ws_url("https://example.com/unsafe").is_err());
    }
}
