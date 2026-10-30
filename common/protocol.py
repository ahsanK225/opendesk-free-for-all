"""
OpenDesk Communication Protocol
Defines standardized message types, serialization, and packet envelopes for:
- Session Handshake and Authentication
- DeskRT-style Video Frame Streaming (Full & Tile Deltas)
- Remote Input (Mouse, Keyboard, Shortcuts)
- Bidirectional Clipboard Synchronization
- Chunked File Transfer
- P2P Signaling & Relay Fallback
"""

import json
import base64
import time
from typing import Any, Dict, Optional, Union

class MessageType:
    # Signaling / Handshake
    REGISTER = "register"
    REGISTER_RESP = "register_resp"
    CONNECT = "connect"
    CONNECT_RESP = "connect_resp"
    SESSION_REQUEST = "session_request"
    SESSION_ACCEPT = "session_accept"
    SESSION_REJECT = "session_reject"
    P2P_SIGNAL = "p2p_signal"
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    HEARTBEAT = "heartbeat"
    
    # Video Streaming
    VIDEO_INIT = "video_init"
    VIDEO_FULL = "video_full"
    VIDEO_DELTA = "video_delta"
    VIDEO_CONFIG = "video_config"
    
    # Input Handling
    INPUT_MOUSE_MOVE = "mouse_move"
    INPUT_MOUSE_DOWN = "mouse_down"
    INPUT_MOUSE_UP = "mouse_up"
    INPUT_MOUSE_SCROLL = "mouse_scroll"
    INPUT_KEY_DOWN = "key_down"
    INPUT_KEY_UP = "key_up"
    INPUT_SHORTCUT = "shortcut"
    
    # Clipboard
    CLIPBOARD_TEXT = "clipboard_text"
    CLIPBOARD_IMAGE = "clipboard_image"
    
    # Real-Time Voice Communication
    AUDIO_CHUNK = "audio_chunk"
    AUDIO_CONTROL = "audio_control"
    
    # File Transfer
    FILE_LIST_REQ = "file_list_req"
    FILE_LIST_RESP = "file_list_resp"
    FILE_DOWNLOAD_REQ = "file_download_req"
    FILE_UPLOAD_START = "file_upload_start"
    FILE_CHUNK = "file_chunk"
    FILE_COMPLETE = "file_complete"
    FILE_ERROR = "file_error"


def create_packet(msg_type: str, payload: Optional[Dict[str, Any]] = None, **kwargs) -> str:
    """Create a structured JSON packet envelope."""
    data = {
        "type": msg_type,
        "timestamp": time.time(),
        "payload": payload or {}
    }
    if kwargs:
        data["payload"].update(kwargs)
    return json.dumps(data)


def parse_packet(raw_data: Union[str, bytes]) -> Optional[Dict[str, Any]]:
    """Parse a JSON packet envelope, returning None on error."""
    try:
        if isinstance(raw_data, bytes):
            raw_data = raw_data.decode("utf-8")
        return json.loads(raw_data)
    except Exception:
        return None
