"""Refresh-token rotation: each refresh token can be exchanged once."""
import secrets
import time

SESSION_TTL_SECONDS = 30 * 60


def refresh(store, refresh_token, now=None):
    """Exchange a refresh token for a new access token and refresh token."""
    now = time.time() if now is None else now
    record = store.get(refresh_token)
    if record is None or record["used"]:
        raise PermissionError("refresh token is invalid or already used")
    if now > record["expires_at"]:
        raise PermissionError("refresh token expired")
    new_refresh = secrets.token_urlsafe(32)
    store.put(new_refresh, {
        "user_id": record["user_id"],
        "used": False,
        "expires_at": now + SESSION_TTL_SECONDS,
    })
    store.mark_used(refresh_token)
    return {"access_token": secrets.token_urlsafe(32), "refresh_token": new_refresh}
