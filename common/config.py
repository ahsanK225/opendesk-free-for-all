"""
OpenDesk Configuration Manager
Maintains persistent application settings, including AnyDesk-style persistent host ID.
"""

import os
import json
import random
from typing import Optional

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
