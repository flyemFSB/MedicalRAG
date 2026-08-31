"""Argon2 密码哈希适配器检查（recipe §1.2：argon2id）。"""

from medicalrag_infra.auth.password import Argon2PasswordHasher


def test_hash_and_verify_roundtrip():
    hasher = Argon2PasswordHasher()
    encoded = hasher.hash("secret")
    assert encoded != "secret"
    assert encoded.startswith("$argon2id$")
    assert hasher.verify("secret", encoded)


def test_verify_wrong_password_fails():
    hasher = Argon2PasswordHasher()
    encoded = hasher.hash("secret")
    assert not hasher.verify("wrong", encoded)


def test_verify_malformed_hash_fails():
    hasher = Argon2PasswordHasher()
    assert not hasher.verify("secret", "not-a-valid-hash")
