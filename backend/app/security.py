"""Password hashing and session-token generation.

Standard library only: PBKDF2-HMAC-SHA256 for passwords, `secrets` for tokens.
A dedicated password library (argon2, bcrypt) would be the production choice,
but it adds a compiled dependency to a project that has no stored accounts to
migrate yet. The encoded format carries its own algorithm and iteration count,
so switching later can verify old hashes while writing new ones.
"""

import base64
import hashlib
import hmac
import secrets

ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 240_000
SALT_BYTES = 16
TOKEN_BYTES = 32


def _encode(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _decode(encoded: str) -> bytes:
    return base64.b64decode(encoded, validate=True)


def hash_password(password: str, *, iterations: int = ITERATIONS) -> str:
    """Hash a password as `pbkdf2_sha256$iterations$salt$digest`, salt per call."""
    if not password:
        raise ValueError("Password must not be empty.")

    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{ALGORITHM}${iterations}${_encode(salt)}${_encode(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    """Check a password against an encoded hash. A malformed hash is a mismatch."""
    try:
        algorithm, iterations, salt, digest = encoded.split("$")
        if algorithm != ALGORITHM:
            return False
        expected = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), _decode(salt), int(iterations)
        )
        # compare_digest, not ==, so a wrong password cannot be found byte by
        # byte from how long the comparison took.
        return hmac.compare_digest(expected, _decode(digest))
    except (ValueError, AttributeError):
        return False


def new_token() -> str:
    """An opaque session token with 256 bits of entropy."""
    return secrets.token_urlsafe(TOKEN_BYTES)
