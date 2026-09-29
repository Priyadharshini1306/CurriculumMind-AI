import os

os.environ["JWT_SECRET"] = "test-secret"

from app.core.security import create_token, decode_token, hash_password, verify_password


def test_password_hash_roundtrip():
    h = hash_password("correct horse")
    assert h != "correct horse"
    assert verify_password("correct horse", h)
    assert not verify_password("wrong", h)


def test_token_roundtrip():
    claims = decode_token(create_token("u1", "LEARNER", "s1"))
    assert claims["sub"] == "u1" and claims["sid"] == "s1"
    assert decode_token("garbage") is None
