"""Session tokens.

The password-hashing tests that used to live here went with the hashing itself:
Supabase Auth checks credentials now, and testing that would be testing
Supabase. What is still this project's to get right is the token it hands out
once Auth has said yes.
"""

from app.security import new_token


def test_tokens_are_unique_and_long_enough_to_be_unguessable():
    tokens = {new_token() for _ in range(200)}
    assert len(tokens) == 200
    assert all(len(token) >= 32 for token in tokens)


def test_a_token_is_url_safe_so_it_survives_a_header_and_a_query_string():
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
    assert set(new_token()) <= allowed
