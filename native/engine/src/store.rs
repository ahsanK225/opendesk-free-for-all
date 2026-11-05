use anyhow::{Context, Result, bail};
use base64::{Engine, engine::general_purpose::STANDARD as B64};
use ed25519_dalek::{Signature, Signer, SigningKey, Verifier, VerifyingKey};
use hmac::{Hmac, Mac};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    fs,
    path::{Path, PathBuf},
    time::{SystemTime, UNIX_EPOCH},
};
use windows::{
    Win32::{
        Foundation::{HLOCAL, LocalFree},
        Security::Cryptography::{CRYPT_INTEGER_BLOB, CryptProtectData, CryptUnprotectData},
        Storage::FileSystem::{MOVEFILE_REPLACE_EXISTING, MOVEFILE_WRITE_THROUGH, MoveFileExW},
    },
    core::PCWSTR,
};

pub fn now() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}
pub fn token() -> String {
    let mut bytes = [0u8; 24];
    getrandom::fill(&mut bytes).expect("Windows system random generator");
    hex::encode(bytes)
}
fn wide(value: &std::ffi::OsStr) -> Vec<u16> {
    use std::os::windows::ffi::OsStrExt;
    value.encode_wide().chain(Some(0)).collect()
}

pub fn atomic_write(path: &Path, bytes: &[u8]) -> Result<()> {
    let parent = path.parent().context("Missing configuration directory")?;
    fs::create_dir_all(parent)?;
    let temporary = parent.join(format!(".opendesk-{}.tmp", token()));
    let result = (|| -> Result<()> {
        use std::io::Write;
        let mut file = fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&temporary)?;
        file.write_all(bytes)?;
        file.sync_all()?;
        drop(file);
        unsafe {
            MoveFileExW(
                PCWSTR(wide(temporary.as_os_str()).as_ptr()),
                PCWSTR(wide(path.as_os_str()).as_ptr()),
                MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH,
            )?;
        }
        Ok(())
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temporary);
    }
    result
}

fn crypt(bytes: &[u8], decrypt: bool) -> Result<Vec<u8>> {
    let source = CRYPT_INTEGER_BLOB {
        cbData: bytes.len().try_into()?,
        pbData: bytes.as_ptr() as *mut u8,
    };
    let mut output = CRYPT_INTEGER_BLOB::default();
    unsafe {
        if decrypt {
            CryptUnprotectData(&source, None, None, None, None, 1, &mut output)?;
        } else {
            CryptProtectData(&source, PCWSTR::null(), None, None, None, 1, &mut output)?;
        }
        let result = std::slice::from_raw_parts(output.pbData, output.cbData as usize).to_vec();
        LocalFree(Some(HLOCAL(output.pbData as _)));
        Ok(result)
    }
}
pub fn protect(value: &str) -> Result<String> {
    Ok(format!(
        "dpapi:{}",
        B64.encode(crypt(value.as_bytes(), false)?)
    ))
}
pub fn unprotect(value: &str) -> Result<String> {
    let value = value
        .strip_prefix("dpapi:")
        .context("Credential is not protected")?;
    Ok(String::from_utf8(crypt(&B64.decode(value)?, true)?)?)
}

pub struct Store {
    pub path: PathBuf,
    pub config: Value,
    pub identity: SigningKey,
}
impl Store {
    pub fn load(directory: PathBuf) -> Result<Self> {
        let path = directory.join("config.json");
        let mut config: Value = if path.exists() {
            serde_json::from_slice(&fs::read(&path)?)
                .context("Existing configuration is invalid; it has not been overwritten")?
        } else {
            json!({})
        };
        if !config.is_object() {
            bail!("Existing configuration must be an object")
        }
        let identity = if let Some(value) = config["device_identity"].as_str().map(str::to_owned) {
            let decoded = if value.starts_with("dpapi:") {
                unprotect(&value)?
            } else {
                config["device_identity"] = json!(protect(&value)?);
                value
            };
            SigningKey::from_bytes(
                &B64.decode(decoded)?
                    .try_into()
                    .map_err(|_| anyhow::anyhow!("Invalid device identity"))?,
            )
        } else {
            let mut secret = [0; 32];
            getrandom::fill(&mut secret).map_err(|e| anyhow::anyhow!("{e}"))?;
            let key = SigningKey::from_bytes(&secret);
            config["device_identity"] = json!(protect(&B64.encode(secret))?);
            key
        };
        if let Some(password) = config["unattended_password"]
            .as_str()
            .filter(|s| !s.is_empty() && !s.starts_with("dpapi:"))
            .map(str::to_owned)
        {
            config["unattended_password"] = json!(protect(&password)?);
        }
        let id = clean_id(config["host_id"].as_str().unwrap_or(""));
        if id.len() != 9 || !id.bytes().all(|c| c.is_ascii_digit()) {
            let mut value = [0; 4];
            getrandom::fill(&mut value).map_err(|e| anyhow::anyhow!("{e}"))?;
            config["host_id"] = json!(format_id(
                &(100_000_000 + u32::from_le_bytes(value) % 900_000_000).to_string()
            ));
        }
        if !config["recent_sessions"].is_array() {
            config["recent_sessions"] = json!([]);
        }
        let store = Self {
            path,
            config,
            identity,
        };
        store.save()?;
        Ok(store)
    }
    pub fn save(&self) -> Result<()> {
        atomic_write(&self.path, &serde_json::to_vec_pretty(&self.config)?)
    }
    pub fn id(&self) -> String {
        clean_id(self.config["host_id"].as_str().unwrap_or(""))
    }
    pub fn key(&self) -> String {
        B64.encode(self.identity.verifying_key().as_bytes())
    }
    pub fn fingerprint(&self) -> String {
        hex::encode(Sha256::digest(self.identity.verifying_key().as_bytes()))
    }
    pub fn identity_packet(&self, nonce: &str) -> Value {
        json!({"nonce":nonce,"public_key":self.key(),"signature":B64.encode(self.identity.sign(format!("OpenDesk-v2:{nonce}").as_bytes()).to_bytes())})
    }
    pub fn directory_record(&self, url: &str) -> Value {
        let body = crate::directory::record_body(&self.id(), url, now() + crate::directory::FRESH_FOR);
        json!({"key":self.key(),"signature":B64.encode(self.identity.sign(body.as_bytes()).to_bytes()),"body":body})
    }
    /// The same signed record, short enough for the backup directory's value limit.
    pub fn compact_record(&self, url: &str) -> Option<String> {
        let name = if url.is_empty() { "" } else { url.strip_prefix("https://")?.strip_suffix(".trycloudflare.com")? };
        let expires = now() + crate::directory::FRESH_FOR;
        let signature = self.identity.sign(crate::directory::record_body(&self.id(), url, expires).as_bytes());
        Some(crate::directory::encode_compact(&self.identity.verifying_key().to_bytes(), &signature.to_bytes(), expires as u32, name))
    }
    pub fn password_record(&self) -> Result<Option<Value>> {
        let value = self.config["unattended_password"].as_str().unwrap_or("");
        if value.is_empty() {
            return Ok(None);
        }
        let password = unprotect(value)?;
        if password.is_empty() {
            return Ok(None);
        }
        let mut salt = [0u8; 16];
        getrandom::fill(&mut salt).map_err(|e| anyhow::anyhow!("{e}"))?;
        let mut key = [0u8; 32];
        pbkdf2::pbkdf2_hmac::<Sha256>(password.as_bytes(), &salt, 210_000, &mut key);
        Ok(Some(
            json!({"salt":B64.encode(salt),"iterations":210_000,"key":B64.encode(key)}),
        ))
    }
    pub fn remember(&mut self, id: &str) -> Result<()> {
        let formatted = format_id(id);
        let values = self.config["recent_sessions"].as_array_mut().unwrap();
        let mut recent=values.iter().find(|v|device_reference(v["id"].as_str().unwrap_or(""))==device_reference(id)).cloned().unwrap_or_else(||json!({"id":formatted,"alias":format!("Desktop • {formatted}"),"favorite":false}));
        recent["last_seen"] = json!(now());
        values.retain(|v| device_reference(v["id"].as_str().unwrap_or("")) != device_reference(id));
        values.insert(0, recent);
        values.truncate(100);
        self.save()
    }
}
pub fn clean_id(id: &str) -> String {
    id.chars()
        .filter(|c| !c.is_whitespace() && *c != '-')
        .collect()
}
pub fn format_id(id: &str) -> String {
    let clean = clean_id(id);
    if clean.len() == 9 && clean.bytes().all(|b| b.is_ascii_digit()) {
        format!("{} {} {}", &clean[..3], &clean[3..6], &clean[6..])
    } else {
        id.trim().to_owned()
    }
}
pub fn device_reference(id: &str) -> String {
    let clean = clean_id(id);
    if clean.len() == 9 && clean.bytes().all(|c| c.is_ascii_digit()) {
        clean
    } else {
        id.trim().to_owned()
    }
}
pub fn verify_identity(packet: &Value, nonce: &str) -> Result<String> {
    if packet["nonce"].as_str() != Some(nonce) {
        bail!("Device identity nonce did not match")
    }
    let key = packet["public_key"]
        .as_str()
        .context("Device key is missing")?;
    let key_bytes: [u8; 32] = B64
        .decode(key)?
        .try_into()
        .map_err(|_| anyhow::anyhow!("Invalid device key"))?;
    let signature =
        Signature::from_slice(&B64.decode(packet["signature"].as_str().unwrap_or(""))?)?;
    VerifyingKey::from_bytes(&key_bytes)?
        .verify(format!("OpenDesk-v2:{nonce}").as_bytes(), &signature)?;
    Ok(key.into())
}
pub fn password_proof(password: &str, challenge: &Value) -> Result<String> {
    let iterations = challenge["iterations"]
        .as_u64()
        .context("Missing password derivation parameters")?;
    if !(100_000..=600_000).contains(&iterations) {
        bail!("Invalid password derivation parameters")
    }
    let salt = B64.decode(challenge["salt"].as_str().unwrap_or(""))?;
    if salt.len() != 16 {
        bail!("Invalid password salt")
    }
    let nonce = challenge["nonce"]
        .as_str()
        .context("Missing password nonce")?;
    if nonce.len() > 256 {
        bail!("Invalid password nonce")
    }
    let mut key = [0; 32];
    pbkdf2::pbkdf2_hmac::<Sha256>(password.as_bytes(), &salt, iterations as u32, &mut key);
    let mut mac = Hmac::<Sha256>::new_from_slice(&key)?;
    mac.update(nonce.as_bytes());
    Ok(hex::encode(mac.finalize().into_bytes()))
}
pub fn verify_proof(record: &Value, nonce: &str, proof: &str) -> bool {
    let Ok(key) = B64.decode(record["key"].as_str().unwrap_or("")) else {
        return false;
    };
    let Ok(mut mac) = Hmac::<Sha256>::new_from_slice(&key) else {
        return false;
    };
    mac.update(nonce.as_bytes());
    hex::decode(proof).is_ok_and(|signature| mac.verify_slice(&signature).is_ok())
}

#[cfg(test)]
mod address_tests {
    use super::*;
    #[test]
    fn direct_urls_preserve_hyphens_and_numeric_addresses_share_one_key() {
        let url = "wss://quiet-red-desk.trycloudflare.com/ws";
        assert_eq!(format_id(url), url);
        assert_eq!(device_reference(url), url);
        assert_eq!(
            device_reference("123-456-789"),
            device_reference("123 456 789")
        );
        assert_eq!(format_id("123456789"), "123 456 789");
    }
}
