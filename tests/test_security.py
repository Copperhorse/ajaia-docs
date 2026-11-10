from app.security import hash_password, verify_password


def test_correct_password_verifies():
    assert verify_password("secret", hash_password("secret"))


def test_wrong_password_fails():
    assert not verify_password("nope", hash_password("secret"))


def test_same_password_gets_different_hashes():
    assert hash_password("secret") != hash_password("secret")  # random salt


def test_malformed_stored_hash_is_rejected_not_crash():
    assert not verify_password("secret", "garbage")
