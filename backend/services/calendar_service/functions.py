import time
import hmac
import hashlib
import base64
import json
from core.config import settings

STATE_SECRET = (settings.GOOGLE_STATE_SECRET or "").strip().strip('"').strip("'")
ALGO = hashlib.sha256


def create_state(sub: str, ttl_seconds=300) -> str:
    payload = {"sub": sub, "exp": int(time.time()) + ttl_seconds}
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
    sig = hmac.new(STATE_SECRET.encode(), raw, ALGO).digest()
    return base64.urlsafe_b64encode(raw + b"." + sig).decode().rstrip("=")


def verify_state(token: str) -> dict:
    try:
        pad = "=" * (-len(token) % 4)
        data = base64.urlsafe_b64decode(token + pad)
    except Exception as e:
        raise ValueError(f"base64 error: {e}")

    try:
        raw, sig = data.rsplit(b".", 1)
    except Exception:
        raise ValueError("format error: missing dot separator")

    expected = hmac.new(STATE_SECRET.encode(), raw, ALGO).digest()
    if not hmac.compare_digest(sig, expected):
        raise ValueError("bad signature")

    try:
        payload = json.loads(raw)
    except Exception as e:
        raise ValueError(f"json error: {e}")

    if payload.get("exp", 0) < int(time.time()):
        raise ValueError("expired")

    return payload
