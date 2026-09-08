import pytest

from app.security import hash_password, new_token, verify_password


def test_hash_is_salted_so_two_hashes_of_one_password_differ():
    assert hash_password("hunter2") != hash_password("hunter2")


def test_verify_accepts_the_original_password():
    assert verify_password("hunter2", hash_password("hunter2"))


def test_verify_rejects_a_wrong_password():
    assert not verify_password("hunter3", hash_password("hunter2"))


def test_the_password_is_not_recoverable_from_the_hash():
    assert "hunter2" not in hash_password("hunter2")


def test_verify_rejects_a_malformed_hash_instead_of_raising():
    for broken in ("", "not-a-hash", "pbkdf2_sha256$abc$x$y", "md5$1$x$y"):
        assert not verify_password("hunter2", broken)


def test_an_empty_password_is_refused_at_the_hashing_step():
    with pytest.raises(ValueError):
        hash_password("")


def test_tokens_are_unique_and_long_enough_to_be_unguessable():
    tokens = {new_token() for _ in range(200)}
    assert len(tokens) == 200
    assert all(len(token) >= 32 for token in tokens)
