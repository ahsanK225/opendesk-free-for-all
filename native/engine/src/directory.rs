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
        .connect_timeout(Duration::from_secs(4))
        .dns_resolver(Arc::new(crate::net::Resolver))
        .user_agent(concat!("OpenDesk/", env!("CARGO_PKG_VERSION")))
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
async fn fetch_text(client:&Client,url:&str,maximum:usize)->Result<String>{
    let mut response=client.get(url).header("Cache-Control","no-cache").send().await?.error_for_status()?;
    if response.content_length().is_some_and(|n|n>maximum as u64){bail!("Directory response exceeds its size limit")}
    let mut data=Vec::new();
    while let Some(chunk)=response.chunk().await?{if data.len().saturating_add(chunk.len())>maximum{bail!("Directory response exceeds its size limit")};data.extend_from_slice(&chunk);}
    Ok(String::from_utf8(data)?)
}
pub fn legacy_endpoint(record:&str)->Option<String>{
    let text=serde_json::from_str::<String>(record).unwrap_or_else(|_|record.trim().into());
    let url=Url::parse(&text).ok()?;
    if url.scheme()!="https"||!url.host_str().is_some_and(|h|h.ends_with(".trycloudflare.com"))||url.port().is_some_and(|p|p!=443){return None}
    ws_url(&text).ok()
}
pub async fn resolve(shared: &Shared, target: &str) -> Result<(String, String, Option<String>)> {
    let (id,address)=if let Some((id,address))=target.split_once('@'){(clean_id(id),address)}else{("remote_host".into(),target)};
    if address.contains(['.',':'])||address=="localhost"{return Ok((id,ws_url(address)?,None))}
    let id=clean_id(target);
    if id.len()!=9||!id.bytes().all(|b|b.is_ascii_digit()){bail!("Enter a nine-digit device ID or a share URL")}
    let pinned=shared.store.lock().unwrap().config["trusted_devices"][&id].as_str().map(str::to_owned);
    let client=http()?;
    for attempt in 0..2{
        if attempt>0{tokio::time::sleep(Duration::from_millis(350)).await;}
        let primary=format!("https://ntfy.sh/opendesk_node_{id}/raw?poll=1&since=3m");
        let secondary=format!("https://keyvalue.immanuel.co/api/KeyVal/GetValue/s460x9wm/{id}");
        let (one,two)=tokio::join!(fetch_text(&client,&primary,512*1024),fetch_text(&client,&secondary,16*1024));
        let mut old=None;
        if let Ok(text)=one{for line in text.lines().rev(){
            if let Ok((url,key))=read_record(line,&id,pinned.as_deref()){return Ok((id,url,Some(key)))}
            if old.is_none(){old=legacy_endpoint(line);}
        }}
        if let Ok(text)=two{
            let text=serde_json::from_str::<String>(&text).unwrap_or(text).replace('-',"/");
            let padded=format!("{text}{}","=".repeat((4-text.len()%4)%4));
            if let Ok(bytes)=B64.decode(padded)&&let Ok(record)=String::from_utf8(bytes){
                if let Ok((url,key))=read_record(&record,&id,pinned.as_deref()){return Ok((id,url,Some(key)))}
                if old.is_none(){old=legacy_endpoint(&record);}
            }
        }
        // This is an unverified address hint, not identity trust. Modern peers
        // still prove their key; legacy peers require explicit compatibility consent,
        // are refused for a saved device and never receive a password.
        if let Some(url)=old{return Ok((id,url,None))}
    }
    bail!("Desktop {id} is not reachable through its current internet address. Check Internet access on the host, or use its latest share link/LAN address.")
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
            .args(["tunnel", "--no-autoupdate", "--protocol", "http2", "--edge-ip-version", "4", "--url", &format!("http://127.0.0.1:{port}")])
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::piped())
            .kill_on_drop(true)
            .creation_flags(0x08000000).kill_on_drop(true);
        match command.spawn() {
            Ok(mut process) => {
                let mut lines = BufReader::new(process.stderr.take().unwrap()).lines();
                let mut interval = tokio::time::interval(Duration::from_secs(1));
                let mut url = String::new();
                let mut published = 0;
                let mut ready=false;
                let mut probe:Option<tokio::task::JoinHandle<bool>>=None;
                let mut checked=std::time::Instant::now()-Duration::from_secs(30);
                loop {
                    tokio::select! {
                                            line=lines.next_line()=>{
                    match line{
                    Ok(Some(line))=>{
                    if let Some(index)=line.find("https://"){
                    let candidate=line[index..].split(|c:char|c.is_whitespace()||c=='|'||c=='"').next().unwrap_or("");if let Ok(parsed)=Url::parse(candidate)&& parsed.host_str().is_some_and(|h|h.ends_with(".trycloudflare.com"))&&parsed.path()=="/"&&candidate!=url{url=candidate.into();delay=1;ready=false;if let Some(task)=probe.take(){task.abort();}checked=std::time::Instant::now()-Duration::from_secs(30);shared.update(|v|{v["shareUrl"]=json!("");v["tunnelMessage"]=json!("Preparing the internet link; LAN connections are available.");});}}},_=>break}},
                                            _=interval.tick()=>{
                                                if shared.stop.load(Ordering::Acquire)||!shared.store.lock().unwrap().config["native_settings"]["publicAccess"].as_bool().unwrap_or(true){let _=process.kill().await;break}
                                                if probe.as_ref().is_some_and(|task|task.is_finished()){
                                                    ready=probe.take().unwrap().await.unwrap_or(false);
                                                    shared.update(|v|{v["shareUrl"]=json!(if ready{url.as_str()}else{""});v["tunnelMessage"]=json!(if ready{"Internet link ready."}else{"The internet link is not reachable yet. Retrying; LAN connections are available."});});
                                                }
                                                if !url.is_empty()&&probe.is_none()&&checked.elapsed()>=Duration::from_secs(10){
                                                    checked=std::time::Instant::now();let candidate=url.clone();
                                                    probe=Some(tokio::spawn(async move{let Ok(client)=http()else{return false};match client.get(format!("{}/health",candidate.trim_end_matches('/'))).timeout(Duration::from_secs(5)).send().await{Ok(r) if r.status().is_success()=>r.json::<Value>().await.is_ok_and(|v|v["app"]=="OpenDesk"&&v["protocol"]==2),_=>false}}));
                                                }
                                                if ready&&store::now().saturating_sub(published)>=30{
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
                if let Some(task)=probe{task.abort();}
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
