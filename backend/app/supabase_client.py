"""Supabase clients — the backend's single door to the database and to Auth.

Three kinds of client, because they answer to different permissions:

* `admin()` uses the service role key. It bypasses Row Level Security, so it can
  do the things a request cannot do on its own behalf — read another user's row
  to build a directory, write an audit entry. Use it deliberately.
* `anonymous()` uses the anon key with no user attached. It is what sign-in and
  sign-up go through, before there is a user to act as.
* `as_user(token)` uses the anon key with a signed-in user's access token, so
  every query runs under that user's Row Level Security policies. Prefer it:
  a query that the database itself refuses cannot be got wrong by a missing
  check in Python.

Server-side clients never persist or auto-refresh a session. The library's
default is written for a browser, where one client belongs to one person for as
long as the tab is open; here one process serves everybody, and a stored session
would leak one caller's identity into the next caller's request.
"""

from functools import lru_cache

from supabase import Client, ClientOptions, create_client

from app import config

#: A session belongs to a request, not to the process. See the module docstring.
_SERVER_SIDE = ClientOptions(auto_refresh_token=False, persist_session=False)


@lru_cache(maxsize=1)
def admin() -> Client:
    """The service role client. Cached — it holds no per-caller state."""
    return create_client(
        config.supabase_url(),
        config.supabase_service_role_key(),
        options=_SERVER_SIDE,
    )


def anonymous() -> Client:
    """An anon-key client with no user attached, for sign-in and sign-up.

    Built fresh each time rather than cached: the auth client keeps the result
    of a sign-in on the instance, and sharing that between requests would hand
    one caller another's session.
    """
    return create_client(
        config.supabase_url(),
        config.supabase_anon_key(),
        options=_SERVER_SIDE,
    )


def as_user(access_token: str) -> Client:
    """An anon-key client acting as the holder of `access_token`.

    Queries run under that user's Row Level Security policies, so the database
    enforces access rather than trusting this process to have checked.
    """
    client = anonymous()
    client.postgrest.auth(access_token)
    return client


def reset() -> None:
    """Drop the cached admin client — for tests, and after changing credentials."""
    admin.cache_clear()
