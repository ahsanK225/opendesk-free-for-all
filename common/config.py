"""
OpenDesk Configuration Manager
Maintains persistent application settings, including AnyDesk-style persistent host ID,
recent sessions, favorites, and unattended access security.
"""

import os
import json
import random
import time
from typing import Optional, List, Dict, Any

CONFIG_DIR = os.path.expanduser("~/.opendesk")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

def _ensure_config_dir():
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
    except Exception:
        pass

def load_config() -> dict:
    _ensure_config_dir()
    if os.path.isfile(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_config(cfg: dict):
    _ensure_config_dir()
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print(f"[Config] Warning saving config: {e}")

def get_persistent_host_id() -> str:
    """Retrieve or generate a permanent 9-digit OpenDesk ID for this machine."""
    cfg = load_config()
    existing_id = cfg.get("host_id")
    if existing_id and isinstance(existing_id, str) and len(existing_id.replace(" ", "")) == 9:
        return existing_id

    # Generate permanent 9-digit ID
    new_id = f"{random.randint(100, 999)} {random.randint(100, 999)} {random.randint(100, 999)}"
    cfg["host_id"] = new_id
    save_config(cfg)
    return new_id

def get_recent_sessions() -> List[Dict[str, Any]]:
    """Retrieve list of recently connected remote sessions."""
    cfg = load_config()
    recents = cfg.get("recent_sessions")
    if recents is not None:
        return recents

    # Provide initial sample discovery cards
    default_recents = [
        {"id": "524 819 301", "alias": "Studio Workstation", "favorite": True, "last_seen": "Today, 14:20"},
        {"id": "902 411 658", "alias": "Office Laptop", "favorite": False, "last_seen": "Yesterday"},
    ]
    cfg["recent_sessions"] = default_recents
    save_config(cfg)
    return default_recents

def add_recent_session(target_id: str, alias: Optional[str] = None):
    """Add or bump a target ID in the recent sessions history."""
    clean = target_id.replace(" ", "").replace("-", "")
    formatted = f"{clean[:3]} {clean[3:6]} {clean[6:]}" if len(clean) == 9 else target_id
    
    cfg = load_config()
    recents = cfg.get("recent_sessions", [])
    
    # Check if already exists
    existing = None
    for r in recents:
        if r.get("id", "").replace(" ", "") == clean:
            existing = r
            break
            
    current_time_str = time.strftime("%b %d, %H:%M")
    if existing:
        existing["last_seen"] = current_time_str
        if alias:
            existing["alias"] = alias
        recents.remove(existing)
        recents.insert(0, existing)
    else:
        new_entry = {
            "id": formatted,
            "alias": alias or f"Desktop - {formatted}",
            "favorite": False,
            "last_seen": current_time_str
        }
        recents.insert(0, new_entry)
        
    cfg["recent_sessions"] = recents[:20] # Keep last 20
    save_config(cfg)

def toggle_favorite(target_id: str) -> bool:
    """Toggle favorite star for a given session ID."""
    clean = target_id.replace(" ", "").replace("-", "")
    cfg = load_config()
    recents = cfg.get("recent_sessions", [])
    is_fav = False
    for r in recents:
        if r.get("id", "").replace(" ", "") == clean:
            r["favorite"] = not r.get("favorite", False)
            is_fav = r["favorite"]
            break
    cfg["recent_sessions"] = recents
    save_config(cfg)
    return is_fav

def get_unattended_password() -> str:
    cfg = load_config()
    return cfg.get("unattended_password", "")

def set_unattended_password(pw: str):
    cfg = load_config()
    cfg["unattended_password"] = pw
    save_config(cfg)

def get_auto_update_enabled() -> bool:
    """Check if automatic update checks on startup are enabled (default True)."""
    cfg = load_config()
    return cfg.get("auto_update", True)

def set_auto_update_enabled(enabled: bool):
    """Enable or disable automatic update checks on startup."""
    cfg = load_config()
    cfg["auto_update"] = bool(enabled)
    save_config(cfg)

def get_audio_settings() -> Dict[str, Any]:
    """Retrieve saved audio configuration (input/output devices, gain, volumes, Discord-grade voice suite)."""
    cfg = load_config()
    audio = cfg.get("audio", {})
    return {
        "input_device": audio.get("input_device", ""),
        "output_device": audio.get("output_device", ""),
        "mic_gain": float(audio.get("mic_gain", 1.0)),
        "speaker_volume": float(audio.get("speaker_volume", 1.0)),
        "input_mode": audio.get("input_mode", "voice_activity"),  # "voice_activity" | "push_to_talk"
        "vad_sensitivity": float(audio.get("vad_sensitivity", 0.25)),  # 0.0 to 1.0
        "auto_sensitivity": bool(audio.get("auto_sensitivity", True)),
        "ptt_key": audio.get("ptt_key", "Control_L"),
        "noise_suppression": bool(audio.get("noise_suppression", True)),
        "echo_cancellation": bool(audio.get("echo_cancellation", True)),
        "agc_enabled": bool(audio.get("agc_enabled", True)),
        "noise_gate": bool(audio.get("noise_gate", True))
    }

def save_audio_settings(settings: Dict[str, Any]):
    """Save persistent audio preferences to configuration."""
    cfg = load_config()
    cfg["audio"] = settings
    save_config(cfg)
