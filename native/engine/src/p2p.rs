//! Direct connections addressed by device key: UDP with hole punching, or a relay when that
//! fails. A QUIC stream carries the existing WebSocket protocol unchanged, so approval,
//! identity and permissions work exactly as they do for every other route.
use crate::app::Shared;
use anyhow::{Context, Result, anyhow, bail};
use base64::{Engine, engine::general_purpose::STANDARD as B64};
use iroh::{Endpoint, EndpointId, SecretKey, endpoint::presets};
use serde_json::json;
use std::{
    sync::{Arc, atomic::Ordering},
    time::Duration,
};
use tokio::{
    io::copy_bidirectional,
    net::{TcpListener, TcpStream},
    sync::Semaphore,
};
const ALPN: &[u8] = b"opendesk/1";
const DIAL_TIMEOUT: Duration = Duration::from_secs(8);
const MAX_INCOMING: usize = 8;

async fn endpoint(shared: &Shared) -> Result<&Endpoint> {
    shared
        .peer
        .get_or_try_init(|| async {
            let secret = shared.store.lock().unwrap().identity.to_bytes();
            Endpoint::builder(presets::N0)
                .secret_key(SecretKey::from_bytes(&secret))
                .alpns(vec![ALPN.to_vec()])
                .bind()
                .await
                .map_err(|error| anyhow!("Direct connections are unavailable: {error}"))
        })
        .await
}
fn public_access(shared: &Shared) -> bool {
    shared.store.lock().unwrap().config["native_settings"]["publicAccess"]
        .as_bool()
        .unwrap_or(true)
}
/// Whether this PC can be reached through the relay, which is what other PCs dial first.
pub async fn wait_online(shared: &Shared) -> bool {
    match endpoint(shared).await {
        Ok(peer) => tokio::time::timeout(Duration::from_secs(15), peer.online()).await.is_ok(),
        Err(_) => false,
    }
}
/// Passes each incoming stream to the host's own loopback listener, as the tunnel does.
pub async fn serve(shared: Arc<Shared>, port: u16) {
    let peer = match endpoint(&shared).await {
        Ok(peer) => peer.clone(),
        Err(error) => {
            shared.update(|v| v["peerMessage"] = json!(error.to_string()));
            return;
        }
    };
    let limit = Arc::new(Semaphore::new(MAX_INCOMING));
    while !shared.stop.load(Ordering::Acquire) {
        let incoming = tokio::select! {
            incoming = peer.accept() => incoming,
            _ = tokio::time::sleep(Duration::from_secs(1)) => continue,
        };
        let Some(incoming) = incoming else { break };
        let Ok(permit) = limit.clone().try_acquire_owned() else {
            incoming.refuse();
            continue;
        };
        if !public_access(&shared) {
            incoming.refuse();
            continue;
        }
        tokio::spawn(async move {
            let _permit = permit;
            let _ = forward_incoming(incoming, port).await;
        });
    }
    let _ = tokio::time::timeout(Duration::from_secs(1), peer.close()).await;
}
async fn forward_incoming(incoming: iroh::endpoint::Incoming, port: u16) -> Result<()> {
    let connection = incoming.await.map_err(|error| anyhow!("{error}"))?;
    let (send, receive) = connection.accept_bi().await?;
    let mut local = TcpStream::connect(("127.0.0.1", port)).await?;
    local.set_nodelay(true)?;
    let mut remote = tokio::io::join(receive, send);
    let _ = copy_bidirectional(&mut local, &mut remote).await;
    connection.close(0u32.into(), b"done");
    Ok(())
}
/// Connects to a device key and returns a one-use local WebSocket address that leads to it.
pub async fn dial(shared: &Arc<Shared>, device_key: &str, connection_key: &str) -> Result<String> {
    if std::env::var_os("OPENDESK_DEV_NO_TUNNEL").is_some() {
        bail!("Direct connections are off in this run")
    }
    let bytes: [u8; 32] = B64
        .decode(device_key)?
        .try_into()
        .map_err(|_| anyhow!("Invalid device key"))?;
    let id = EndpointId::from_bytes(&bytes).map_err(|error| anyhow!("{error}"))?;
    let peer = endpoint(shared).await?;
    if peer.id() == id {
        bail!("This is the device you are using")
    }
    let connection = tokio::time::timeout(DIAL_TIMEOUT, peer.connect(id, ALPN))
        .await
        .context("The desktop did not answer directly")?
        .map_err(|error| anyhow!("{error}"))?;
    let listener = TcpListener::bind(("127.0.0.1", 0)).await?;
    let port = listener.local_addr()?.port();
    let (shared, key) = (shared.clone(), connection_key.to_owned());
    tokio::spawn(async move {
        let Ok(Ok((mut local, _))) = tokio::time::timeout(Duration::from_secs(20), listener.accept()).await else {
            connection.close(0u32.into(), b"unused");
            return;
        };
        drop(listener);
        let _ = local.set_nodelay(true);
        let Ok((send, receive)) = connection.open_bi().await else { return };
        let watcher = {
            let (connection, shared, key) = (connection.clone(), shared.clone(), key.clone());
            tokio::spawn(async move {
                loop {
                    let selected = connection.paths().iter().find(|path| path.is_selected()).map(|path| (path.is_relay(), path.rtt()));
                    if let Some((relay, rtt)) = selected {
                        shared.connection(&key, |v| {
                            v["route"] = json!(if relay { "Relay" } else { "Direct" });
                            v["routeMs"] = json!(rtt.as_millis() as u64);
                        });
                    }
                    tokio::time::sleep(Duration::from_secs(2)).await;
                }
            })
        };
        let mut remote = tokio::io::join(receive, send);
        let _ = copy_bidirectional(&mut local, &mut remote).await;
        watcher.abort();
        connection.close(0u32.into(), b"done");
    });
    Ok(format!("ws://127.0.0.1:{port}/ws"))
}
