from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

# Hardened parameters (OWASP "production" tier):
#   memory_cost 128 MiB · time_cost 4 · parallelism 4
#   hash ≈ 150~250ms on modern hardware — defends against
#   massively parallel offline attacks.
_hasher = PasswordHash((
    Argon2Hasher(
        memory_cost=131072,  # 128 MiB (KiB unit)
        time_cost=4,
        parallelism=4,
    ),
))


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _hasher.verify(plain, hashed)
