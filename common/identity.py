"""Persistent Ed25519 device identity and native trust-on-first-use checks."""
import base64
import hashlib
import sys
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, PublicFormat, NoEncryption
from common.config import load_config, save_config, _CONFIG_LOCK
from common.credentials import protect, unprotect


def device_key():
    with _CONFIG_LOCK:
        cfg = load_config()
        stored = cfg.get('device_identity')
        if stored:
            encoded = unprotect(stored) if stored.startswith('dpapi:') else stored
            return Ed25519PrivateKey.from_private_bytes(base64.b64decode(encoded))
        key = Ed25519PrivateKey.generate()
        encoded = base64.b64encode(key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption())).decode()
        cfg['device_identity'] = protect(encoded) if sys.platform=='win32' else encoded
        save_config(cfg)
        return key


def public_key(key):
    return base64.b64encode(key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)).decode()


def fingerprint(encoded):
    return hashlib.sha256(base64.b64decode(encoded)).hexdigest()


def sign_identity(key, nonce):
    return {'public_key':public_key(key), 'nonce':nonce,
            'signature':base64.b64encode(key.sign(('OpenDesk-v2:'+nonce).encode())).decode()}


def verify_identity(packet, nonce):
    if packet.get('nonce') != nonce:
        raise ValueError('Identity nonce mismatch')
    key = packet['public_key']
    Ed25519PublicKey.from_public_bytes(base64.b64decode(key)).verify(
        base64.b64decode(packet['signature']), ('OpenDesk-v2:'+nonce).encode())
    return key


def trusted_key(device):
    return load_config().get('trusted_devices',{}).get(device)


def trust_device(device, key):
    with _CONFIG_LOCK:
        cfg = load_config()
        cfg.setdefault('trusted_devices',{})[device] = key
        save_config(cfg)
