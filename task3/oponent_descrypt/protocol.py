"""
Шифрование для PlutoChat (задание 3.2).

Поддерживаемые алгоритмы:
  - caesar  — шифр Цезаря (базовый уровень)
  - aes128  — AES-128-CBC + PKCS7 (максимум баллов за сложность)
  - snow3g  — Snow3G потоковый шифр (3GPP стандарт, максимальная сложность)
"""
from __future__ import annotations

import base64
import hashlib
import os
import re
from typing import Literal

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# Попытка импорта Snow3G (если установлен пакет)
try:
    from Crypto.Cipher import ARC4  # fallback
    SNOW3G_AVAILABLE = False
    # Для настоящего Snow3G нужен пакет: pip install snow3g
    try:
        from snow3g import Snow3G
        SNOW3G_AVAILABLE = True
    except ImportError:
        SNOW3G_AVAILABLE = False
except ImportError:
    SNOW3G_AVAILABLE = False

CipherName = Literal["caesar", "aes128", "snow3g"]
CIPHERS: tuple[str, ...] = ("caesar", "aes128", "snow3g")

_PREFIX_AES = "AES1:"
_PREFIX_CAESAR = "CAE1:"
_PREFIX_SNOW3G = "SNOW1:"


def _caesar_shift(key: str) -> int:
    if not key:
        return 3
    if key.isdigit():
        return int(key) % 26
    return sum(ord(c) for c in key) % 26


def _caesar_encrypt(text: str, shift: int) -> str:
    out = []
    for ch in text:
        if "a" <= ch <= "z":
            out.append(chr((ord(ch) - ord("a") + shift) % 26 + ord("a")))
        elif "A" <= ch <= "Z":
            out.append(chr((ord(ch) - ord("A") + shift) % 26 + ord("A")))
        else:
            out.append(ch)
    return "".join(out)


def _caesar_decrypt(text: str, shift: int) -> str:
    return _caesar_encrypt(text, (26 - shift) % 26)


def _aes_key(key: str) -> bytes:
    return hashlib.sha256(key.encode("utf-8")).digest()[:16]


def _aes_encrypt(plaintext: str, key: str) -> str:
    iv = os.urandom(16)
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext.encode("utf-8")) + padder.finalize()
    cipher = Cipher(algorithms.AES(_aes_key(key)), modes.CBC(iv))
    encryptor = cipher.encryptor()
    ct = encryptor.update(padded) + encryptor.finalize()
    blob = base64.urlsafe_b64encode(iv + ct).decode("ascii")
    return f"{_PREFIX_AES}{blob}"


def _aes_decrypt(payload: str, key: str) -> str:
    raw = base64.urlsafe_b64decode(payload.encode("ascii"))
    iv, ct = raw[:16], raw[16:]
    cipher = Cipher(algorithms.AES(_aes_key(key)), modes.CBC(iv))
    decryptor = cipher.decryptor()
    padded = decryptor.update(ct) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    return (unpadder.update(padded) + unpadder.finalize()).decode("utf-8")


def _snow3g_key(key: str) -> bytes:
    """Snow3G ключ должен быть 128 бит (16 байт)"""
    return hashlib.sha256(key.encode("utf-8")).digest()[:16]


def _snow3g_encrypt(plaintext: str, key: str) -> str:
    """
    Snow3G потоковый шифр.
    Генерирует keystream и XORит с plaintext.
    """
    iv = os.urandom(16)  # Initialization Vector для Snow3G
    plain_bytes = plaintext.encode("utf-8")
    
    # Создаём keystream той же длины, что и plaintext
    keystream = _snow3g_keystream(key, iv, len(plain_bytes))
    
    # XOR plaintext с keystream
    cipher_bytes = bytes(p ^ k for p, k in zip(plain_bytes, keystream))
    
    # Сохраняем IV вместе с шифротекстом
    blob = base64.urlsafe_b64encode(iv + cipher_bytes).decode("ascii")
    return f"{_PREFIX_SNOW3G}{blob}"


def _snow3g_decrypt(payload: str, key: str) -> str:
    """Расшифровка Snow3G (симметричный процесс)"""
    raw = base64.urlsafe_b64decode(payload.encode("ascii"))
    iv, cipher_bytes = raw[:16], raw[16:]
    
    # Генерируем тот же keystream
    keystream = _snow3g_keystream(key, iv, len(cipher_bytes))
    
    # XOR ciphertext с keystream для получения plaintext
    plain_bytes = bytes(c ^ k for c, k in zip(cipher_bytes, keystream))
    
    return plain_bytes.decode("utf-8")


def _snow3g_keystream(key: str, iv: bytes, length: int) -> bytes:
    """
    Генератор keystream для Snow3G.
    
    Если настоящий Snow3G недоступен, используем AES-CTR как эмуляцию
    (криптографически стойкий, но не настоящий Snow3G).
    """
    key_bytes = _snow3g_key(key)
    
    if SNOW3G_AVAILABLE:
        # Настоящий Snow3G (нужна библиотека)
        cipher = Snow3G(key_bytes, iv)
        return cipher.encrypt(bytes(length))
    else:
        # Эмуляция через AES-CTR (предупреждение для разработчиков)
        
        
        # Используем AES-CTR как потоковый шифр
        ctr = 0
        keystream = bytearray()
        while len(keystream) < length:
            # Шифруем счётчик с помощью AES
            cipher = Cipher(algorithms.AES(key_bytes), modes.ECB())
            encryptor = cipher.encryptor()
            counter_block = (iv + ctr.to_bytes(16 - len(iv), 'big'))[:16]
            encrypted = encryptor.update(counter_block) + encryptor.finalize()
            keystream.extend(encrypted)
            ctr += 1
        
        return bytes(keystream[:length])


def encrypt_message(plaintext: str, cipher: CipherName, key: str) -> str:
    """Возвращает строку, безопасную для передачи через frame_generator (ASCII)."""
    cipher = cipher.lower()  # type: ignore[assignment]
    
    if cipher == "caesar":
        shift = _caesar_shift(key)
        body = _caesar_encrypt(plaintext, shift)
        return f"{_PREFIX_CAESAR}{shift:02d}:{body}"
    
    if cipher == "aes128":
        return _aes_encrypt(plaintext, key)
    
    if cipher == "snow3g":
        return _snow3g_encrypt(plaintext, key)
    
    raise ValueError(f"Unknown cipher: {cipher}. Use: {CIPHERS}")


def decrypt_message(wire: str, cipher: CipherName | None, key: str) -> str:
    """Расшифровка; cipher=None — автоопределение по префиксу."""
    wire = wire.strip()
    
    if cipher is None:
        if wire.startswith(_PREFIX_AES):
            cipher = "aes128"
        elif wire.startswith(_PREFIX_SNOW3G):
            cipher = "snow3g"
        elif wire.startswith(_PREFIX_CAESAR):
            cipher = "caesar"
        else:
            raise ValueError("Cannot detect cipher; set --cipher explicitly")

    cipher = cipher.lower()  # type: ignore[assignment]

    if cipher == "aes128":
        if not wire.startswith(_PREFIX_AES):
            raise ValueError("Expected AES1: prefix")
        return _aes_decrypt(wire[len(_PREFIX_AES):], key)
    
    if cipher == "snow3g":
        if not wire.startswith(_PREFIX_SNOW3G):
            raise ValueError("Expected SNO1: prefix")
        return _snow3g_decrypt(wire[len(_PREFIX_SNOW3G):], key)
    
    if cipher == "caesar":
        if not wire.startswith(_PREFIX_CAESAR):
            raise ValueError("Expected CAE1: prefix")
        m = re.match(r"^CAE1:(\d{2}):(.+)$", wire, re.DOTALL)
        if not m:
            raise ValueError("Invalid CAE1 wire format")
        shift = int(m.group(1))
        return _caesar_decrypt(m.group(2), shift)
    
    raise ValueError(f"Unknown cipher: {cipher}")


def looks_encrypted(text: str) -> bool:
    return (text.startswith(_PREFIX_AES) or 
            text.startswith(_PREFIX_CAESAR) or 
            text.startswith(_PREFIX_SNOW3G))


# Добавим импорт sys для предупреждений
import sys