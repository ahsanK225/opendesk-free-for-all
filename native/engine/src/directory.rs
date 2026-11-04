use crate::{
    app::Shared,
    store::{self, clean_id},
};
use anyhow::{Context, Result, bail};
use base64::{Engine, engine::general_purpose::{STANDARD as B64, URL_SAFE_NO_PAD}};
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
/// Viewers up to 3.0 only accept a record while `expires` is in the future.
pub const FRESH_FOR: u64 = 120;
/// Newer viewers keep using a record this long, so the host can publish rarely.
const VALID_FOR: u64 = 12 * 3600;
/// PC clocks can be wrong by minutes or hours. A record is signed and the address still has to
/// prove its key, so a clock difference alone must not hide a desktop.
const CLOCK_ROOM: u64 = 24 * 3600;
const COMPACT_PREFIX: &str = "OD1";
const COMPACT_FIXED: usize = 134;
pub fn record_body(id: &str, url: &str, expires: u64) -> String {
    format!(r#"{{"expires":{expires},"id":"{id}","url":"{url}","valid_until":{}}}"#, expires - FRESH_FOR + VALID_FOR)
}
pub fn encode_compact(key: &[u8; 32], signature: &[u8; 64], expires: u32, name: &str) -> String {
    let mut fixed = Vec::with_capacity(100);
    fixed.extend_from_slice(key);
    fixed.extend_from_slice(signature);
    fixed.extend_from_slice(&expires.to_be_bytes());
    format!("{COMPACT_PREFIX}{}{name}", URL_SAFE_NO_PAD.encode(fixed))
}
/// Rebuilds the full signed record, which then passes the normal checks.
fn decode_compact(text: &str, id: &str) -> Option<String> {
    let text = text.strip_prefix(COMPACT_PREFIX)?;
    if text.len() <= COMPACT_FIXED || !text.is_char_boundary(COMPACT_FIXED) { return None }
    let (fixed, name) = text.split_at(COMPACT_FIXED);
    if name.len() > 63 || !name.bytes().all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-') { return None }
    let fixed = URL_SAFE_NO_PAD.decode(fixed).ok()?;
    if fixed.len() != 100 { return None }
    let expires = u32::from_be_bytes(fixed[96..100].try_into().ok()?) as u64;
    if expires < FRESH_FOR { return None }
    let body = record_body(id, &format!("https://{name}.trycloudflare.com"), expires);
    Some(json!({"key":B64.encode(&fixed[..32]),"signature":B64.encode(&fixed[32..96]),"body":body}).to_string())
}
/// Whether a value read from the backup directory is a usable signed record.
#[cfg(test)]
pub fn backup_value_is_usable(text: &str, id: &str) -> bool {
    let text = serde_json::from_str::<String>(text).unwrap_or(text.into());
    decode_compact(&text, id).is_some_and(|record| read_record(&record, id, None).is_ok_and(|found| found.until > store::now()))
}
/// How often to publish to the primary directory, which allows 250 messages a day per address.
fn publish_interval(url_age: u64) -> u64 {
    if url_age < 1800 { 30 } else { 600 }
}
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
#[derive(Clone)]
struct Found {
    url: String,
    key: String,
    expires: u64,
    until: u64,
}
fn read_record(record: &str, id: &str, pinned: Option<&str>) -> Result<Found> {
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
    let until = record["valid_until"].as_u64().unwrap_or(expires).max(expires);
    let now = store::now();
    let url = Url::parse(record["url"].as_str().unwrap_or(""))?;
    if record["id"] != id
        || until > now + VALID_FOR + CLOCK_ROOM
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
        bail!("Directory record is invalid")
    }
    Ok(Found { url: url.as_str().into(), key: key.into(), expires, until })
}
/// Signed records from the primary directory's feed, and a recent unsigned address from an old host.
fn read_feed(text: &str, id: &str, pinned: Option<&str>, now: u64) -> (Vec<Found>, Option<String>) {
    let (mut found, mut old) = (Vec::new(), None);
    for line in text.lines().rev() {
        let Ok(message) = serde_json::from_str::<Value>(line) else { continue };
        let Some(record) = message["message"].as_str().filter(|_| message["event"] == "message") else { continue };
        if let Ok(record) = read_record(record, id, pinned) { found.push(record) }
        else if old.is_none() && now.saturating_sub(message["time"].as_u64().unwrap_or(0)) <= 180 { old = legacy_endpoint(record) }
    }
    (found, old)
}
async fn healthy(client: &Client, url: &str) -> bool {
    match client.get(format!("{}/health", url.trim_end_matches('/'))).timeout(Duration::from_secs(5)).send().await {
        Ok(r) if r.status().is_success() => r.json::<Value>().await.is_ok_and(|v| v["app"] == "OpenDesk" && v["protocol"] == 2),
        _ => false,
    }
}
/// The newest addresses still in date, best first, without repeats.
fn candidates(found: &[Found], now: u64) -> Vec<Found> {
    let mut list: Vec<Found> = found.iter().filter(|f| f.until > now).cloned().collect();
    list.sort_by_key(|f| std::cmp::Reverse(f.expires));
    let mut seen = std::collections::HashSet::new();
    list.retain(|f| seen.insert(f.url.clone()));
    list.truncate(3);
    list
}
/// A long-lived record can point at an old tunnel, so ask the address before using it.
async fn pick(client: &Client, found: &[Found]) -> Option<Found> {
    let now = store::now();
    let list = candidates(found, now);
    let probes: Vec<_> = list.iter().map(|f| { let (client, url) = (client.clone(), f.url.clone()); tokio::spawn(async move { healthy(&client, &url).await }) }).collect();
    for (found, probe) in list.iter().zip(probes) {
        if probe.await.unwrap_or(false) { return Some(found.clone()) }
    }
    list.into_iter().next().filter(|f| f.expires > now)
}
async fn fetch_text(client:&Client,url:&str,maximum:usize)->Result<String>{
    // One directory can take over 10 seconds to answer.
    let mut response=client.get(url).timeout(Duration::from_secs(15)).header("Cache-Control","no-cache").send().await?.error_for_status()?;
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
    let (mut reached,mut seen)=(false,0);
    for attempt in 0..2{
        if attempt>0{tokio::time::sleep(Duration::from_millis(1500)).await;}
        let primary=format!("https://ntfy.sh/opendesk_node_{id}/json?poll=1&since=12h");
        let secondary=format!("https://keyvalue.immanuel.co/api/KeyVal/GetValue/s460x9wm/{id}");
        let backup={let client=client.clone();tokio::spawn(async move{fetch_text(&client,&secondary,16*1024).await})};
        let (mut found,mut old)=(Vec::new(),None);
        if let Ok(text)=fetch_text(&client,&primary,1024*1024).await{
            reached=true;
            (found,old)=read_feed(&text,&id,pinned.as_deref(),store::now());
            if let Some(best)=pick(&client,&found).await{return Ok((id,ws_url(&best.url)?,Some(best.key)))}
        }
        if let Ok(Ok(text))=backup.await{
            reached=true;
            let text=serde_json::from_str::<String>(&text).unwrap_or(text);
            let record=decode_compact(&text,&id).or_else(||{
                let text=text.replace('-',"/");
                let padded=format!("{text}{}","=".repeat((4-text.len()%4)%4));
                B64.decode(padded).ok().and_then(|bytes|String::from_utf8(bytes).ok())
            });
            if let Some(record)=record{
                match read_record(&record,&id,pinned.as_deref()){
                    Ok(record)=>{
                        let new=!found.iter().any(|f|f.url==record.url);
                        found.push(record);
                        if new&&let Some(best)=pick(&client,&found).await{return Ok((id,ws_url(&best.url)?,Some(best.key)))}
                    }
                    Err(_)=>if old.is_none(){old=legacy_endpoint(&record);}
                }
            }
        }
        seen=found.iter().map(|f|f.expires.saturating_sub(FRESH_FOR)).max().unwrap_or(0).max(seen);
        // This is an unverified address hint, not identity trust. Modern peers
        // still prove their key; legacy peers require explicit compatibility consent,
        // are refused for a saved device and never receive a password.
        if let Some(url)=old{return Ok((id,url,None))}
    }
    if !reached{bail!("Could not reach the OpenDesk directory from this network. Check your internet connection and try again, or use a share link.")}
    if seen>0{
        let minutes=store::now().saturating_sub(seen)/60;
        bail!("Desktop {id} was last online about {minutes} min ago and does not answer now. On that PC, OpenDesk must be open, the PC awake and connected to the internet, with Internet access on.")
    }
    bail!("Desktop {id} has not been online in the last 12 hours. Check the ID. On that PC, open OpenDesk with Internet access on and wait a minute.")
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
/// Retries brief failures; a refusal such as the daily limit will not pass in seconds.
pub(crate) async fn post(url: String, body: Option<String>) -> Result<()> {
    let client = http()?;
    let mut last = None;
    for attempt in 0..3 {
        if attempt > 0 { tokio::time::sleep(Duration::from_secs(5)).await; }
        let request = match &body {
            Some(body) => client.post(&url).body(body.clone()),
            // The backup directory refuses a request without this header.
            None => client.post(&url).header(reqwest::header::CONTENT_LENGTH, 0),
        };
        match request.send().await {
            Ok(response) if response.status().is_success() => return Ok(()),
            Ok(response) if response.status().is_client_error() => bail!("Directory refused the record: {}", response.status()),
            Ok(response) => last = Some(anyhow::anyhow!("Directory error: {}", response.status())),
            Err(error) => last = Some(error.into()),
        }
    }
    Err(last.context("Directory was not tried")?)
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
                let (mut published, mut stored, mut born) = (0, 0, 0);
                let mut ready=false;
                let mut answered=std::time::Instant::now();
                let mut probe:Option<tokio::task::JoinHandle<bool>>=None;
                let mut checked=std::time::Instant::now()-Duration::from_secs(30);
                loop {
                    tokio::select! {
                                            line=lines.next_line()=>{
                    match line{
                    Ok(Some(line))=>{
                    if let Some(index)=line.find("https://"){
                    let candidate=line[index..].split(|c:char|c.is_whitespace()||c=='|'||c=='"').next().unwrap_or("");if let Ok(parsed)=Url::parse(candidate)&& parsed.host_str().is_some_and(|h|h.ends_with(".trycloudflare.com"))&&parsed.path()=="/"&&candidate!=url{url=candidate.into();delay=1;ready=false;published=0;stored=0;born=store::now();answered=std::time::Instant::now();if let Some(task)=probe.take(){task.abort();}checked=std::time::Instant::now()-Duration::from_secs(30);shared.update(|v|{v["shareUrl"]=json!("");v["tunnelMessage"]=json!("Preparing the internet link; LAN connections are available.");});}}},_=>break}},
                                            _=interval.tick()=>{
                                                if shared.stop.load(Ordering::Acquire)||!shared.store.lock().unwrap().config["native_settings"]["publicAccess"].as_bool().unwrap_or(true){let _=process.kill().await;break}
                                                if probe.as_ref().is_some_and(|task|task.is_finished()){
                                                    ready=probe.take().unwrap().await.unwrap_or(false);
                                                    if ready{answered=std::time::Instant::now();}
                                                    shared.update(|v|{v["shareUrl"]=json!(if ready{url.as_str()}else{""});v["tunnelMessage"]=json!(if ready{"Internet link ready."}else{"The internet link is not reachable yet. Retrying; LAN connections are available."});});
                                                }
                                                // A tunnel can stay dead after sleep or a network change, and only a new one recovers.
                                                if !ready&&answered.elapsed()>=Duration::from_secs(180){let _=process.kill().await;break}
                                                if !url.is_empty()&&probe.is_none()&&checked.elapsed()>=Duration::from_secs(10){
                                                    checked=std::time::Instant::now();let candidate=url.clone();
                                                    probe=Some(tokio::spawn(async move{let Ok(client)=http()else{return false};healthy(&client,&candidate).await}));
                                                }
                                                if ready&&store::now().saturating_sub(published)>=publish_interval(store::now().saturating_sub(born)){
                    published=store::now();
                    let (id,record)={let store=shared.store.lock().unwrap();(store.id(),store.directory_record(&url).to_string())};
                    tokio::spawn(async move{let _=post(format!("https://ntfy.sh/opendesk_node_{id}"),Some(record)).await;});
                    }
                                                if ready&&store::now().saturating_sub(stored)>=300{
                    stored=store::now();
                    let (id,record)={let store=shared.store.lock().unwrap();(store.id(),store.compact_record(&url))};
                    if let Some(record)=record{tokio::spawn(async move{let _=post(format!("https://keyvalue.immanuel.co/api/KeyVal/UpdateValue/s460x9wm/{id}/{record}"),None).await;});}
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
    const ID: &str = "123456789";
    const URL: &str = "https://calm-river-open-desk.trycloudflare.com";
    fn signing() -> ed25519_dalek::SigningKey { ed25519_dalek::SigningKey::from_bytes(&[7; 32]) }
    fn signed(url: &str, expires: u64) -> String {
        use ed25519_dalek::Signer;
        let key = signing();
        let body = record_body(ID, url, expires);
        json!({"key":B64.encode(key.verifying_key().to_bytes()),"signature":B64.encode(key.sign(body.as_bytes()).to_bytes()),"body":body}).to_string()
    }
    fn feed(records: &[(String, u64)]) -> String {
        records.iter().map(|(message, time)| json!({"event":"message","time":time,"message":message}).to_string()).collect::<Vec<_>>().join("\n")
    }
    #[test]
    fn a_record_stays_usable_after_the_short_window_old_viewers_need() {
        let now = store::now();
        let found = read_record(&signed(URL, now - 3600), ID, None).unwrap();
        assert!(found.expires <= now && found.until > now);
        assert_eq!(candidates(&[found], now).len(), 1);
        let old = signed(URL, now - VALID_FOR - 60);
        assert!(candidates(&[read_record(&old, ID, None).unwrap()], now).is_empty());
    }
    #[test]
    fn a_host_whose_clock_is_ahead_is_still_found() {
        let now = store::now();
        for ahead in [360, 3 * 3600, 23 * 3600] {
            let found = read_record(&signed(URL, now + ahead), ID, None).unwrap();
            assert_eq!(candidates(&[found], now).len(), 1, "{ahead}");
        }
        assert!(read_record(&signed(URL, now + 3 * CLOCK_ROOM), ID, None).is_err());
    }
    #[test]
    fn records_from_hosts_up_to_3_0_keep_working() {
        use ed25519_dalek::Signer;
        let (now, key) = (store::now(), signing());
        let make = |expires: u64| { let body = json!({"id":ID,"url":URL,"expires":expires}).to_string(); json!({"key":B64.encode(key.verifying_key().to_bytes()),"signature":B64.encode(key.sign(body.as_bytes()).to_bytes()),"body":body}).to_string() };
        assert_eq!(candidates(&[read_record(&make(now + 100), ID, None).unwrap()], now).len(), 1);
        assert!(candidates(&[read_record(&make(now - 1), ID, None).unwrap()], now).is_empty());
    }
    #[test]
    fn a_new_record_also_satisfies_the_check_in_viewers_up_to_3_0() {
        let now = store::now();
        let record: Value = serde_json::from_str(&signed(URL, now + FRESH_FOR)).unwrap();
        let body: Value = serde_json::from_str(record["body"].as_str().unwrap()).unwrap();
        let expires = body["expires"].as_u64().unwrap();
        assert!(expires > now && expires <= now + 180);
        assert_eq!(body["id"], ID);
        assert_eq!(body["url"], URL);
    }
    #[test]
    fn the_compact_record_fits_the_backup_directory_and_is_still_verified() {
        use ed25519_dalek::Signer;
        let (now, key) = (store::now(), signing());
        let expires = now + FRESH_FOR;
        let name = "calm-river-open-desk";
        let signature = key.sign(record_body(ID, URL, expires).as_bytes()).to_bytes();
        let text = encode_compact(&key.verifying_key().to_bytes(), &signature, expires as u32, name);
        assert!(COMPACT_PREFIX.len() + COMPACT_FIXED + 63 <= 206);
        let found = read_record(&decode_compact(&text, ID).unwrap(), ID, None).unwrap();
        assert_eq!(found.url.trim_end_matches('/'), URL);
        assert!(found.until > now);
        // Another ID, or a changed address, breaks the signature.
        assert!(read_record(&decode_compact(&text, "987654321").unwrap(), "987654321", None).is_err());
        let changed = encode_compact(&key.verifying_key().to_bytes(), &signature, expires as u32, "evil-river-open-desk");
        assert!(read_record(&decode_compact(&changed, ID).unwrap(), ID, None).is_err());
        // The name cannot reach any other host.
        let mut dotted = text.clone();
        dotted.push_str(".example.com/");
        assert!(decode_compact(&dotted, ID).is_none());
        assert!(decode_compact("OD1short", ID).is_none());
        assert!(decode_compact("something else", ID).is_none());
    }
    #[test]
    fn the_newest_signed_address_comes_first_whatever_the_feed_order() {
        let now = store::now();
        let older = "https://older-river.trycloudflare.com";
        let text = feed(&[(signed(URL, now + 100), now), (signed(older, now - 500), now), (signed(older, now - 900), now), ("not a record".into(), now)]);
        let (found, old) = read_feed(&text, ID, None, now);
        assert!(old.is_none());
        let list = candidates(&found, now);
        assert_eq!(list.len(), 2);
        assert_eq!(list[0].url.trim_end_matches('/'), URL);
        assert_eq!(list[1].url.trim_end_matches('/'), older);
    }
    #[test]
    fn a_pinned_device_ignores_records_from_another_key() {
        let now = store::now();
        let (found, _) = read_feed(&feed(&[(signed(URL, now + 100), now)]), ID, Some("another key"), now);
        assert!(found.is_empty());
    }
    #[test]
    fn an_unsigned_address_from_an_old_host_must_be_recent() {
        let now = store::now();
        assert!(read_feed(&feed(&[(URL.into(), now - 30)]), ID, None, now).1.is_some());
        assert!(read_feed(&feed(&[(URL.into(), now - 3600)]), ID, None, now).1.is_none());
    }
    #[test]
    fn publishing_stays_inside_the_daily_limit_for_a_tunnel_that_stays_up() {
        let day = (0..86400u64).fold((0u64, 0u64), |(count, last), age| if age == 0 || age - last >= publish_interval(age) { (count + 1, age) } else { (count, last) }).0;
        assert!(day < 250, "{day}");
    }
}
