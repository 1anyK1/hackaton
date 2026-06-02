import base64
import hashlib
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


AES_PREFIX = "AES1:"
CAESAR_PREFIX = "CAE1:"
LEGACY_AES_PREFIX = "AES0:"


def _radio_b64encode(data: bytes) -> str:
    encoded = base64.urlsafe_b64encode(data).decode("ascii")
    return encoded.replace("X", "~")


def _radio_b64decode(data: str) -> bytes:
    encoded = data.replace("~", "X")
    return base64.urlsafe_b64decode(encoded.encode("ascii"))


def derive_aes128_key(secret: str) -> bytes:
    """Derive a fixed-length AES-128 key from a shared text secret."""
    if not secret:
        raise ValueError("Encryption key must not be empty")
    return hashlib.sha256(secret.encode("utf-8")).digest()[:16]


def encrypt_aes128(message: str, secret: str) -> str:
    key = derive_aes128_key(secret)
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(nonce, message.encode("utf-8"), None)
    payload = _radio_b64encode(nonce + ciphertext)
    return f"{AES_PREFIX}{len(payload)}:{payload}"


def decrypt_aes128(payload: str, secret: str) -> str:
    if payload.startswith(AES_PREFIX):
        payload = payload[len(AES_PREFIX):]
    if payload.startswith(LEGACY_AES_PREFIX):
        payload = payload[len(LEGACY_AES_PREFIX):]

    if ":" in payload:
        length_text, encoded_payload = payload.split(":", 1)
        payload_length = int(length_text)
        encoded_payload = encoded_payload[:payload_length]
        raw = _radio_b64decode(encoded_payload)
    else:
        raw = bytes.fromhex(payload)
    if len(raw) < 29:
        raise ValueError("AES payload is too short")
    nonce = raw[:12]
    ciphertext = raw[12:]
    key = derive_aes128_key(secret)
    return AESGCM(key).decrypt(nonce, ciphertext, None).decode("utf-8")


def caesar_shift(text: str, shift: int) -> str:
    result = []
    shift %= 26
    for char in text:
        if "a" <= char <= "z":
            result.append(chr((ord(char) - ord("a") + shift) % 26 + ord("a")))
        elif "A" <= char <= "Z":
            result.append(chr((ord(char) - ord("A") + shift) % 26 + ord("A")))
        else:
            result.append(char)
    return "".join(result)


def encrypt_caesar(message: str, shift: int) -> str:
    return CAESAR_PREFIX + str(shift % 26) + ":" + caesar_shift(message, shift)


def decrypt_caesar(payload: str, shift: int | None = None) -> str:
    if payload.startswith(CAESAR_PREFIX):
        rest = payload[len(CAESAR_PREFIX):]
        encoded_shift, payload = rest.split(":", 1)
        if shift is None:
            shift = int(encoded_shift)
    if shift is None:
        raise ValueError("Caesar shift is required")
    return caesar_shift(payload, -shift)


@dataclass
class ChatCrypto:
    mode: str = "none"
    key: str = ""

    def encrypt(self, message: str) -> str:
        if self.mode == "none":
            return message
        if self.mode == "aes":
            return encrypt_aes128(message, self.key)
        if self.mode == "caesar":
            return encrypt_caesar(message, int(self.key))
        raise ValueError(f"Unsupported encryption mode: {self.mode}")

    def decrypt(self, payload: str) -> str:
        if payload.startswith(AES_PREFIX):
            return decrypt_aes128(payload, self.key)
        if payload.startswith(CAESAR_PREFIX):
            return decrypt_caesar(payload)
        if self.mode == "aes":
            raise ValueError("received packet is not a valid AES packet")
        if self.mode == "caesar":
            raise ValueError("received packet is not a valid Caesar packet")
        return payload

    @property
    def label(self) -> str:
        if self.mode == "none":
            return "open channel"
        if self.mode == "aes":
            return "AES-128-GCM"
        if self.mode == "caesar":
            return f"Caesar shift {int(self.key) % 26}"
        return self.mode
