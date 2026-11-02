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
import struct
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
    VIDEO_ACK = "video_ack"
    VIDEO_REFRESH = "video_refresh"
    
    # Input Handling
    INPUT_MOUSE_MOVE = "mouse_move"
    INPUT_MOUSE_DOWN = "mouse_down"
    INPUT_MOUSE_UP = "mouse_up"
    INPUT_MOUSE_SCROLL = "mouse_scroll"
    INPUT_KEY_DOWN = "key_down"
    INPUT_KEY_UP = "key_up"
    INPUT_SHORTCUT = "shortcut"
    INPUT_RESET = "input_reset"
    
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
    return json.dumps(data, separators=(",", ":"))


def parse_packet(raw_data: Union[str, bytes]) -> Optional[Dict[str, Any]]:
    """Parse a JSON packet envelope, returning None on error."""
    try:
        if isinstance(raw_data, bytes):
            if raw_data.startswith(b'ODV2'):
                return decode_video_packet(raw_data)
            raw_data = raw_data.decode("utf-8")
        packet = json.loads(raw_data)
        if not isinstance(packet, dict) or not isinstance(packet.get('payload', {}), dict):
            return None
        return packet
    except Exception:
        return None


def encode_video_packet(frame, session_id):
    """Binary JPEG payloads avoid base64 expansion and per-tile JSON strings."""
    payload = {k: frame[k] for k in ('width', 'height', 'frame_id')}
    payload['session_id'] = session_id
    images = [frame] if frame['kind'] == 'full' else frame['tiles']
    body, tiles, offset = [], [], 0
    for item in images:
        raw = item['data']
        tile = {k:item[k] for k in ('x','y','w','h') if k in item}
        tile.update(offset=offset, length=len(raw))
        tiles.append(tile)
        body.append(raw)
        offset += len(raw)
    payload['tiles'] = tiles
    header = json.dumps({'type':'video_full' if frame['kind']=='full' else 'video_delta',
                         'payload':payload}, separators=(',', ':')).encode()
    return b'ODV2' + struct.pack('!I', len(header)) + header + b''.join(body)


def decode_video_packet(raw):
    if len(raw) < 8:
        raise ValueError('Truncated video packet')
    size = struct.unpack('!I', raw[4:8])[0]
    if not 0 < size <= 65536 or 8+size > len(raw):
        raise ValueError('Invalid video header')
    packet = json.loads(raw[8:8+size])
    payload, body = packet['payload'], memoryview(raw)[8+size:]
    if packet['type'] not in ('video_full', 'video_delta') or not 0 < payload['width'] <= 16384 or not 0 < payload['height'] <= 16384:
        raise ValueError('Invalid video dimensions')
    for tile in payload['tiles']:
        start, length = tile.pop('offset'), tile.pop('length')
        if start < 0 or length <= 0 or start+length > len(body):
            raise ValueError('Invalid image range')
        tile['image'] = bytes(body[start:start+length])
    if packet['type'] == 'video_full':
        payload['image'] = payload.pop('tiles')[0]['image']
    return packet
