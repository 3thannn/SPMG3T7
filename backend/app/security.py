"""Session-token generation.

This module used to hash passwords too. It no longer does: Supabase Auth checks
credentials now, and it stores them in `auth.users` rather than in this
project's schema. Hashing here as well would mean a second copy of everyone's
password, in a column the schema does not have, verified by code that is not the
one deciding whether sign-in succeeds — three reasons not to keep it.

What is still ours is the session token. `POST /auth/login` issues one of these
after Auth has confirmed who the caller is, and `app.sessions` maps it back. It
is opaque and server-side on purpose, so that signing out can end a session
outright — see the note in `app.sessions`.
"""

import secrets

TOKEN_BYTES = 32


def new_token() -> str:
    """An opaque session token with 256 bits of entropy."""
    return secrets.token_urlsafe(TOKEN_BYTES)
