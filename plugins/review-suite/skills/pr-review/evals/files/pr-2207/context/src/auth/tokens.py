import jwt

from auth.config import SESSION_SIGNING_KEY


def decode(token: str) -> dict:
    """Verify the signature and return the claims.

    Expiry is deliberately NOT verified here: the refresh endpoint needs to read
    the claims of an expired token. Every caller that grants access must check
    claims["exp"] itself.
    """
    return jwt.decode(
        token,
        SESSION_SIGNING_KEY,
        algorithms=["HS256"],
        options={"verify_exp": False},
    )
