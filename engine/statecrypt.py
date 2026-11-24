"""Encrypts private state (database incl. comment logs, access token) before it is committed
to the public repo. Key = TOKEN_KEY passphrase stored only as a GitHub Actions secret."""
import base64
import hashlib
import os
from pathlib import Path

from cryptography.fernet import Fernet


def _f():
    pw = os.environ.get("TOKEN_KEY")
    if not pw:
        raise SystemExit("TOKEN_KEY secret missing")
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(pw.encode()).digest()))


def encrypt_file(src: Path, dst: Path):
    dst.write_bytes(_f().encrypt(src.read_bytes()))


def decrypt_file(src: Path, dst: Path):
    dst.write_bytes(_f().decrypt(src.read_bytes()))


def save_token(token: str, path: Path):
    path.write_bytes(_f().encrypt(token.encode()))


def load_token(path: Path):
    return _f().decrypt(path.read_bytes()).decode() if path.exists() else None
