//! Application-scoped DNS recovery; TLS always verifies the original hostname.
use anyhow::{Context, Result, bail};
use futures_util::{StreamExt, stream::FuturesUnordered};
use serde_json::Value;
use std::{
    collections::HashMap,
    net::{IpAddr, SocketAddr},
    sync::{Mutex, OnceLock},
    time::{Duration, Instant},
};
use tokio::net::TcpStream;
use tokio_tungstenite::{MaybeTlsStream, WebSocketStream};

type Cache = Mutex<HashMap<String, (Instant, Vec<IpAddr>)>>;
static CACHE: OnceLock<Cache> = OnceLock::new();
fn cache() -> &'static Cache {
    CACHE.get_or_init(|| Mutex::new(HashMap::new()))
}
pub fn invalidate(host: &str) {
    cache().lock().unwrap().remove(host);
}
pub fn parse_answers(value: &Value) -> Result<(Vec<IpAddr>, u64)> {
    if value["Status"] != 0 {
        bail!("The DNS service has no usable record for this address")
    }
    let mut ips = Vec::new();
    let mut ttl = 60;
    if let Some(answers) = value["Answer"].as_array() {
        for answer in answers.iter().take(32) {
            let kind = answer["type"].as_u64().unwrap_or(0);
            if let Some(ip) = answer["data"]
                .as_str()
                .and_then(|s| s.parse::<IpAddr>().ok())
                && ((kind == 1 && ip.is_ipv4()) || (kind == 28 && ip.is_ipv6()))
                && !ips.contains(&ip)
            {
                ips.push(ip);
                ttl = ttl.min(answer["TTL"].as_u64().unwrap_or(1).clamp(1, 60));
            }
        }
    }
    if ips.is_empty() {
        bail!("No network addresses were returned")
    }
    Ok((ips, ttl))
}
async fn encrypted_lookup(host: &str) -> Result<Vec<IpAddr>> {
    // Bootstrap IPs bypass a failing OS resolver while certificate checks still
    // authenticate cloudflare-dns.com / dns.google over HTTPS.
    let client = reqwest::Client::builder()
        .https_only(true)
        .connect_timeout(Duration::from_secs(3))
        .timeout(Duration::from_secs(5))
        .resolve("cloudflare-dns.com", SocketAddr::from(([1, 1, 1, 1], 443)))
        .resolve("dns.google", SocketAddr::from(([8, 8, 8, 8], 443)))
        .build()?;
    for endpoint in [
        "https://cloudflare-dns.com/dns-query",
        "https://dns.google/resolve",
    ] {
        let response = client
            .get(endpoint)
            .header("Accept", "application/dns-json")
            .query(&[("name", host), ("type", "A")])
            .send()
            .await;
        if let Ok(response) = response
            && response.status().is_success()
            && response.content_length().is_none_or(|n| n <= 65536)
            && let Ok(bytes) = response.bytes().await
            && bytes.len() <= 65536
            && let Ok(value) = serde_json::from_slice::<Value>(&bytes)
            && let Ok((ips, ttl)) = parse_answers(&value)
        {
            let mut entries = cache().lock().unwrap();
            if entries.len() >= 256 {
                entries.retain(|_, (until, _)| *until > Instant::now());
                if entries.len() >= 256 {
                    entries.clear();
                }
            }
            entries.insert(
                host.into(),
                (Instant::now() + Duration::from_secs(ttl), ips.clone()),
            );
            return Ok(ips);
        }
    }
    bail!(
        "Cannot resolve desktop address {host}. Check your connection or request a fresh share link."
    )
}
pub async fn addresses(host: &str, port: u16) -> Result<Vec<SocketAddr>> {
    let host = host.trim_matches(['[', ']']);
    if let Ok(ip) = host.parse::<IpAddr>() {
        return Ok(vec![SocketAddr::new(ip, port)]);
    }
    let cached = cache()
        .lock()
        .unwrap()
        .get(host)
        .filter(|(until, _)| *until > Instant::now())
        .map(|(_, ips)| ips.clone());
    if let Some(ips) = cached {
        return Ok(ips
            .into_iter()
            .map(|ip| SocketAddr::new(ip, port))
            .collect());
    }
    if let Ok(Ok(values)) = tokio::time::timeout(
        Duration::from_secs(2),
        tokio::net::lookup_host((host, port)),
    )
    .await
    {
        let mut values: Vec<_> = values.collect();
        values.sort_by_key(|a| a.is_ipv6());
        values.dedup();
        if !values.is_empty() {
            return Ok(values);
        }
    }
    Ok(encrypted_lookup(host)
        .await?
        .into_iter()
        .map(|ip| SocketAddr::new(ip, port))
        .collect())
}
pub struct Resolver;
impl reqwest::dns::Resolve for Resolver {
    fn resolve(&self, name: reqwest::dns::Name) -> reqwest::dns::Resolving {
        let host = name.as_str().to_owned();
        Box::pin(async move {
            let values = addresses(&host, 0).await.map_err(|e| {
                Box::new(std::io::Error::other(e.to_string()))
                    as Box<dyn std::error::Error + Send + Sync>
            })?;
            Ok(Box::new(values.into_iter()) as reqwest::dns::Addrs)
        })
    }
}
pub type Socket = WebSocketStream<MaybeTlsStream<TcpStream>>;
pub async fn connect(address: &str) -> Result<Socket> {
    let url = reqwest::Url::parse(address)?;
    if !matches!(url.scheme(), "ws" | "wss") {
        bail!("Invalid desktop connection scheme")
    }
    let host = url.host_str().context("Desktop address is missing")?;
    let port = url
        .port_or_known_default()
        .context("Desktop port is missing")?;
    let values = addresses(host, port).await?;
    let mut attempts = FuturesUnordered::new();
    for (index, address) in values.into_iter().take(6).enumerate() {
        attempts.push(async move {
            tokio::time::sleep(Duration::from_millis(index as u64 * 200)).await;
            tokio::time::timeout(Duration::from_secs(4), TcpStream::connect(address)).await
        });
    }
    let mut connected = None;
    while let Some(result) = attempts.next().await {
        if let Ok(Ok(stream)) = result {
            connected = Some(stream);
            break;
        }
    }
    let Some(stream) = connected else {
        invalidate(host);
        bail!(
            "The desktop could not be reached. Check that the host is online and its share link is current."
        )
    };
    drop(attempts);
    stream.set_nodelay(true)?;
    match tokio::time::timeout(
        Duration::from_secs(10),
        tokio_tungstenite::client_async_tls(address, stream),
    )
    .await
    {
        Ok(Ok((socket, _))) => Ok(socket),
        Ok(Err(tokio_tungstenite::tungstenite::Error::Http(response)))
            if response.status().is_server_error() =>
        {
            bail!(
                "The host's internet link is not ready or has expired. Request a fresh share link and reconnect."
            )
        }
        Ok(Err(error)) => bail!("Secure desktop connection failed: {error}"),
        Err(_) => bail!(
            "The desktop did not answer the secure connection request. Retry or use its LAN address."
        ),
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    #[test]
    fn dns_answers_are_typed_bounded_and_ttl_limited() {
        let(ips,ttl)=parse_answers(&json!({"Status":0,"Answer":[{"type":5,"data":"alias.example","TTL":1000},{"type":1,"data":"104.16.230.132","TTL":300},{"type":1,"data":"104.16.230.132","TTL":300},{"type":28,"data":"::1","TTL":10}]})).unwrap();
        assert_eq!(ips.len(), 2);
        assert_eq!(ttl, 10);
        assert!(parse_answers(&json!({"Status":3})).is_err());
        assert!(
            parse_answers(&json!({"Status":0,"Answer":[{"type":1,"data":"not-an-ip"}]})).is_err()
        );
    }
    #[tokio::test]
    #[ignore = "needs internet access"]
    async fn encrypted_lookup_works_without_the_operating_system_resolver() {
        assert!(!encrypted_lookup("ntfy.sh").await.unwrap().is_empty());
    }
    #[tokio::test]
    async fn local_literal_address_needs_no_dns() {
        assert_eq!(
            addresses("127.0.0.1", 8123).await.unwrap(),
            vec![SocketAddr::from(([127, 0, 0, 1], 8123))]
        );
    }
}
