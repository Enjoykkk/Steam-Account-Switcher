"""解析 .maFile 并生成 Steam Guard 代码（TOTP，与 NebulaAuth 算法一致）。"""

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
    # 部分 mafile 可能包含 BOM 或多余空白
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
        raise ValueError(f"在 {path} 中未找到 shared_secret")
    return generate_steam_guard_code(secret)
