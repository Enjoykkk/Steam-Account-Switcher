"""Парсинг .maFile и генерация Steam Guard кодов (TOTP, тот же алгоритм что в NebulaAuth)."""

import base64
import hashlib
import hmac
import json
import struct
import time
from pathlib import Path


STEAM_GUARD_CHARS = "23456789BCDFGHJKMNPQRTVWXY"


def load_mafile(path):
    text = Path(path).read_text(encoding="utf-8")
    # Некоторые mafile содержат BOM или лишние пробелы
    return json.loads(text.lstrip("﻿").strip())


def generate_steam_guard_code(shared_secret, timestamp=None):
    if timestamp is None:
        timestamp = int(time.time())

    secret = base64.b64decode(shared_secret)
    time_buffer = struct.pack(">Q", timestamp // 30)
    digest = hmac.new(secret, time_buffer, hashlib.sha1).digest()

    start = digest[19] & 0x0F
    code_int = struct.unpack(">I", digest[start:start + 4])[0] & 0x7FFFFFFF

    code = ""
    for _ in range(5):
        code += STEAM_GUARD_CHARS[code_int % len(STEAM_GUARD_CHARS)]
        code_int //= len(STEAM_GUARD_CHARS)
    return code


def seconds_until_next_code():
    return 30 - (int(time.time()) % 30)


def code_from_mafile(path):
    data = load_mafile(path)
    secret = data.get("shared_secret")
    if not secret:
        raise ValueError(f"shared_secret не найден в {path}")
    return generate_steam_guard_code(secret)
