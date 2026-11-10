"""Password hashing with scrypt from the standard library."""
import hashlib
import hmac
import secrets

N, R, P = 2**14, 8, 1  # scrypt cost settings (about 16 MB of memory per hash)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=N, r=R, p=P)
    return f"scrypt${N}${R}${P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt_hex, digest_hex = stored.split("$")
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex),
                                n=int(n), r=int(r), p=int(p))
    except (ValueError, TypeError):
        return False  # malformed stored hash: treat as a wrong password
    return hmac.compare_digest(digest.hex(), digest_hex)
