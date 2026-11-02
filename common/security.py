"""Password challenges shared by native clients and the local relay."""
import base64
import hashlib
import hmac
import secrets

PBKDF2_ITERATIONS = 210_000


def password_record(password):
    if not password:
        return None
    salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, PBKDF2_ITERATIONS)
    return {'salt': base64.b64encode(salt).decode(), 'iterations': PBKDF2_ITERATIONS,
            'key': base64.b64encode(key).decode()}


def password_proof(password, challenge):
    iterations = int(challenge['iterations'])
    if not 100_000 <= iterations <= 600_000:
        raise ValueError('Invalid password derivation parameters')
    key = hashlib.pbkdf2_hmac('sha256', password.encode(),
                            base64.b64decode(challenge['salt']), iterations)
    return hmac.new(key, challenge['nonce'].encode(), 'sha256').hexdigest()


def verify_proof(record, nonce, proof):
    expected = hmac.new(base64.b64decode(record['key']), nonce.encode(), 'sha256').hexdigest()
    return isinstance(proof, str) and hmac.compare_digest(expected, proof)
