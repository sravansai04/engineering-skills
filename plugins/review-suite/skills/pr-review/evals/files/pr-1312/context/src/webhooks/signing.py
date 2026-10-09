import hashlib
import hmac


def sign(body: str, secret: str) -> str:
    """HMAC-SHA256 of the raw body. No timestamp, so the same body always signs the same."""
    return hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
