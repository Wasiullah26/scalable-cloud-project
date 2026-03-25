"""JWT and passwords: bcrypt hashes the SHA-256 of the plain password (fits bcrypt byte limit)."""

import hashlib
import os

import bcrypt
import jwt

JWT_SECRET = os.environ.get("JWT_SECRET", "change-me-in-production")
JWT_ALGORITHM = "HS256"


def _sha256_digest_bytes(plain: str) -> bytes:
    return hashlib.sha256(plain.encode("utf-8")).digest()


def _sha256_hex_ascii_bytes(plain: str) -> bytes:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest().encode("ascii")


def hash_password(password: str) -> str:
    pw = _sha256_digest_bytes(password)
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        h = hashed.encode("utf-8")
    except Exception:
        return False

    for candidate in (
        _sha256_digest_bytes(plain),
        _sha256_hex_ascii_bytes(plain),
        plain.encode("utf-8")[:72],
    ):
        try:
            if bcrypt.checkpw(candidate, h):
                return True
        except Exception:
            continue
    return False


def generate_token(user_id: str) -> str:
    payload = {"sub": user_id}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_user_id_from_token(token: str) -> str:
    payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    return payload.get("sub") or ""
