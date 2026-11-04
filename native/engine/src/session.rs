//! Authorization state is owned by the engine, never inferred from UI state.
use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct Permissions {
    pub input: bool,
    pub audio: bool,
    pub clipboard: bool,
    pub file_transfer: bool,
}
impl Permissions {
    /// Lite builds have no voice or file transfer, whatever a peer or the UI requests.
    pub fn for_edition(self) -> Self {
        if cfg!(feature = "full") {
            self
        } else {
            Self {
                audio: false,
                file_transfer: false,
                ..self
            }
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Request {
    pub id: String,
    pub peer: String,
    pub deadline_ms: u64,
}
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Active {
    pub id: String,
    pub peer: String,
    pub permissions: Permissions,
}
#[derive(Debug, Default)]
pub struct HostSession {
    pending: Option<Request>,
    active: Option<Active>,
}
#[derive(Debug, PartialEq, Eq)]
pub enum AuthorizationError {
    Busy,
    Invalid,
    Expired,
    Mismatch,
}

impl HostSession {
    pub fn request(
        &mut self,
        id: String,
        peer: String,
        now_ms: u64,
    ) -> Result<(), AuthorizationError> {
        self.expire(now_ms);
        if self.pending.is_some() || self.active.is_some() {
            return Err(AuthorizationError::Busy);
        }
        if id.len() < 16 || id.len() > 128 || peer.is_empty() || peer.len() > 128 {
            return Err(AuthorizationError::Invalid);
        }
        self.pending = Some(Request {
            id,
            peer,
            deadline_ms: now_ms.saturating_add(60_000),
        });
        Ok(())
    }

    pub fn approve(
        &mut self,
        request_id: &str,
        session_id: String,
        permissions: Permissions,
        now_ms: u64,
    ) -> Result<&Active, AuthorizationError> {
        let request = self.pending.as_ref().ok_or(AuthorizationError::Mismatch)?;
        if request.id != request_id {
            return Err(AuthorizationError::Mismatch);
        }
        if now_ms >= request.deadline_ms {
            self.pending = None;
            return Err(AuthorizationError::Expired);
        }
        if session_id.len() < 16 || session_id.len() > 128 {
            return Err(AuthorizationError::Invalid);
        }
        let request = self.pending.take().unwrap();
        self.active = Some(Active {
            id: session_id,
            peer: request.peer,
            permissions,
        });
        Ok(self.active.as_ref().unwrap())
    }

    pub fn reject(&mut self, request_id: &str) -> bool {
        if self.pending.as_ref().is_some_and(|r| r.id == request_id) {
            self.pending = None;
            true
        } else {
            false
        }
    }

    pub fn expire(&mut self, now_ms: u64) {
        if self
            .pending
            .as_ref()
            .is_some_and(|r| now_ms >= r.deadline_ms)
        {
            self.pending = None;
        }
    }

    pub fn revoke(&mut self) -> Option<Active> {
        self.pending = None;
        self.active.take()
    }

    pub fn allows(&self, peer: &str, session: &str, message: &str) -> bool {
        let Some(active) = &self.active else {
            return false;
        };
        if active.peer != peer || active.id != session {
            return false;
        }
        match message {
            "mouse_move" | "mouse_down" | "mouse_up" | "mouse_scroll" | "key_down" | "key_up"
            | "shortcut" => active.permissions.input,
            "audio_chunk" | "audio_control" => active.permissions.audio,
            "clipboard_text" => active.permissions.clipboard,
            "file_list_req" | "file_download_req" | "file_upload_start" | "file_chunk" => {
                active.permissions.file_transfer
            }
            "video_ack" | "video_refresh" | "video_config" | "input_reset" | "session_end" => true,
            _ => false,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn edition_limits_voice_and_files_only_in_lite() {
        let all = Permissions {
            input: true,
            audio: true,
            clipboard: true,
            file_transfer: true,
        };
        let limited = all.for_edition();
        assert!(limited.input && limited.clipboard);
        assert_eq!(limited.audio, cfg!(feature = "full"));
        assert_eq!(limited.file_transfer, cfg!(feature = "full"));
    }
    const REQUEST: &str = "request-0123456789";
    const SESSION: &str = "session-0123456789";
    fn active() -> HostSession {
        let mut host = HostSession::default();
        host.request(REQUEST.into(), "peer".into(), 0).unwrap();
        host.approve(
            REQUEST,
            SESSION.into(),
            Permissions {
                input: true,
                ..Default::default()
            },
            1,
        )
        .unwrap();
        host
    }
    #[test]
    fn approval_is_bound_to_request() {
        let mut host = HostSession::default();
        host.request(REQUEST.into(), "peer".into(), 0).unwrap();
        assert_eq!(
            host.approve("wrong", SESSION.into(), Permissions::default(), 1),
            Err(AuthorizationError::Mismatch)
        );
        assert!(
            host.approve(REQUEST, SESSION.into(), Permissions::default(), 2)
                .is_ok()
        );
    }
    #[test]
    fn approval_expires_at_deadline() {
        let mut host = HostSession::default();
        host.request(REQUEST.into(), "peer".into(), 10).unwrap();
        assert_eq!(
            host.approve(REQUEST, SESSION.into(), Permissions::default(), 60_010),
            Err(AuthorizationError::Expired)
        );
    }
    #[test]
    fn active_host_rejects_new_peer() {
        assert_eq!(
            active().request(REQUEST.into(), "attacker".into(), 2),
            Err(AuthorizationError::Busy)
        );
    }
    #[test]
    fn denies_wrong_peer_and_session() {
        let host = active();
        assert!(!host.allows("attacker", SESSION, "mouse_move"));
        assert!(!host.allows("peer", "old-session", "mouse_move"));
        assert!(host.allows("peer", SESSION, "mouse_move"));
    }
    #[test]
    fn defaults_deny_and_unknown_types_deny() {
        let host = active();
        for message in [
            "audio_chunk",
            "clipboard_text",
            "file_chunk",
            "register",
            "session_accept",
        ] {
            assert!(!host.allows("peer", SESSION, message));
        }
    }
    #[test]
    fn revoke_immediately_denies_and_cancels() {
        let mut host = active();
        assert!(host.revoke().is_some());
        assert!(!host.allows("peer", SESSION, "video_ack"));
        host.request(REQUEST.into(), "peer".into(), 4).unwrap();
        host.revoke();
        assert_eq!(
            host.approve(REQUEST, SESSION.into(), Permissions::default(), 5),
            Err(AuthorizationError::Mismatch)
        );
    }
}
