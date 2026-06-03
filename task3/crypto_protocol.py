import base64
import hmac
import hashlib
import os
import struct
from dataclasses import dataclass

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


AES_PREFIX = "AES1:"
CAESAR_PREFIX = "CAE1:"
SNOW3G_PREFIX = "SNOW1:"
LEGACY_AES_PREFIX = "AES0:"


def _radio_b64encode(data: bytes) -> str:
    encoded = base64.urlsafe_b64encode(data).decode("ascii")
    return encoded.replace("X", "~")


def _radio_b64decode(data: str) -> bytes:
    encoded = data.replace("~", "X")
    return base64.urlsafe_b64decode(encoded.encode("ascii"))


def _decode_aes_payload(payload: str) -> bytes:
    if ":" in payload:
        length_text, encoded_payload = payload.split(":", 1)
        payload_length = int(length_text)
        return _radio_b64decode(encoded_payload[:payload_length])

    try:
        return bytes.fromhex(payload)
    except ValueError:
        return _radio_b64decode(payload)


def derive_aes128_key(secret: str) -> bytes:
    """Derive a fixed-length AES-128 key from a shared text secret."""
    if not secret:
        raise ValueError("Encryption key must not be empty")
    return hashlib.sha256(secret.encode("utf-8")).digest()[:16]


def aes_key_candidates(secret: str) -> list[bytes]:
    candidates = [derive_aes128_key(secret)]
    raw = secret.encode("utf-8")
    if len(raw) == 16 and raw not in candidates:
        candidates.append(raw)
    try:
        raw_hex = bytes.fromhex(secret)
    except ValueError:
        raw_hex = b""
    if len(raw_hex) == 16 and raw_hex not in candidates:
        candidates.append(raw_hex)
    return candidates


def derive_key(secret: str, label: str, length: int) -> bytes:
    if not secret:
        raise ValueError("Encryption key must not be empty")
    material = hashlib.sha256((label + ":" + secret).encode("utf-8")).digest()
    while len(material) < length:
        material += hashlib.sha256(material).digest()
    return material[:length]


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

    raw = _decode_aes_payload(payload)
    if len(raw) < 29:
        raise ValueError("AES payload is too short")
    nonce = raw[:12]
    ciphertext = raw[12:]
    last_error = None
    for key in aes_key_candidates(secret):
        try:
            return AESGCM(key).decrypt(nonce, ciphertext, None).decode("utf-8")
        except Exception as error:
            last_error = error
    raise ValueError(
        "AES decrypt failed: wrong key, wrong AES mode, or damaged captured packet"
    ) from last_error


def decrypt_aes128_ctr(payload: str, secret: str) -> str:
    if payload.startswith(AES_PREFIX):
        payload = payload[len(AES_PREFIX):]

    raw = _decode_aes_payload(payload)
    attempts = []
    if len(raw) > 16:
        attempts.append((raw[:16], raw[16:]))
    if len(raw) > 12:
        attempts.append((raw[:12] + b"\x00\x00\x00\x00", raw[12:]))

    if not attempts:
        raise ValueError("AES-CTR payload is too short")

    last_error = None
    for key in aes_key_candidates(secret):
        for counter_block, ciphertext in attempts:
            try:
                cipher = Cipher(algorithms.AES(key), modes.CTR(counter_block))
                decryptor = cipher.decryptor()
                plaintext = decryptor.update(ciphertext) + decryptor.finalize()
                return plaintext.decode("utf-8")
            except Exception as error:
                last_error = error

    raise ValueError(
        "AES-CTR decrypt failed: wrong key, wrong nonce layout, or damaged captured packet"
    ) from last_error


def decrypt_opponent_aes128_cbc(payload: str, secret: str) -> str:
    if payload.startswith(AES_PREFIX):
        payload = payload[len(AES_PREFIX):]

    raw = _radio_b64decode(payload)
    if len(raw) < 32 or len(raw) % 16 != 0:
        raise ValueError("opponent AES-CBC payload must be IV + 16-byte blocks")

    iv, ciphertext = raw[:16], raw[16:]
    cipher = Cipher(algorithms.AES(derive_aes128_key(secret)), modes.CBC(iv))
    decryptor = cipher.decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    plaintext = unpadder.update(padded) + unpadder.finalize()
    return plaintext.decode("utf-8")


def decrypt_opponent_caesar(payload: str, key: str | None = None) -> str:
    if not payload.startswith(CAESAR_PREFIX):
        raise ValueError("Expected CAE1: prefix")
    _, shift_text, body = payload.split(":", 2)
    return caesar_shift(body, -int(shift_text))


def decrypt_opponent_snow3g(payload: str, secret: str) -> str:
    if payload.startswith(SNOW3G_PREFIX):
        payload = payload[len(SNOW3G_PREFIX):]

    raw = _radio_b64decode(payload)
    if len(raw) < 16:
        raise ValueError("opponent Snow3G payload must contain a 16-byte IV")

    iv, ciphertext = raw[:16], raw[16:]
    key = derive_aes128_key(secret)
    cipher = Cipher(algorithms.AES(key), modes.ECB())
    keystream = bytearray()
    while len(keystream) < len(ciphertext):
        encryptor = cipher.encryptor()
        keystream.extend(encryptor.update(iv) + encryptor.finalize())

    plaintext = bytes(c ^ k for c, k in zip(ciphertext, keystream))
    return plaintext.decode("utf-8")


def _rotl32(value: int, shift: int) -> int:
    value &= 0xFFFFFFFF
    return ((value << shift) | (value >> (32 - shift))) & 0xFFFFFFFF


def _snow3g_words(seed: bytes) -> list[int]:
    digest = hashlib.sha512(seed).digest()
    return list(struct.unpack(">16I", digest))


def _snow3g_keystream(secret: str, nonce: bytes, length: int) -> bytes:
    key = derive_key(secret, "snow3g-key", 16)
    state = _snow3g_words(key + nonce)
    r1, r2, r3 = struct.unpack(">3I", hashlib.sha256(key + nonce + b"fsm").digest()[:12])
    output = bytearray()

    while len(output) < length:
        f = (state[15] + r1) & 0xFFFFFFFF
        f ^= r2
        z = f ^ state[0]
        output.extend(struct.pack(">I", z))

        r = (r2 + (r3 ^ state[5])) & 0xFFFFFFFF
        r3 = _rotl32((r1 ^ state[2]) + 0x9E3779B9, 11)
        r2 = _rotl32((r ^ state[11]) + 0x7F4A7C15, 7)
        r1 = _rotl32((f + state[9]) ^ 0xA5A5A5A5, 3)

        feedback = (
            _rotl32(state[0], 8)
            ^ state[2]
            ^ _rotl32(state[11], 16)
            ^ state[15]
            ^ r
        ) & 0xFFFFFFFF
        state = state[1:] + [feedback]

    return bytes(output[:length])


def encrypt_snow3g(message: str, secret: str) -> str:
    plaintext = message.encode("utf-8")
    nonce = os.urandom(16)
    keystream = _snow3g_keystream(secret, nonce, len(plaintext))
    ciphertext = bytes(a ^ b for a, b in zip(plaintext, keystream))
    auth_key = derive_key(secret, "snow3g-auth", 32)
    tag = hmac.new(auth_key, nonce + ciphertext, hashlib.sha256).digest()[:16]
    payload = _radio_b64encode(nonce + tag + ciphertext)
    return f"{SNOW3G_PREFIX}{len(payload)}:{payload}"


def decrypt_snow3g(payload: str, secret: str) -> str:
    if payload.startswith(SNOW3G_PREFIX):
        payload = payload[len(SNOW3G_PREFIX):]
    length_text, encoded_payload = payload.split(":", 1)
    payload_length = int(length_text)
    raw = _radio_b64decode(encoded_payload[:payload_length])
    if len(raw) < 32:
        raise ValueError("SNOW3G payload is too short")
    nonce = raw[:16]
    tag = raw[16:32]
    ciphertext = raw[32:]
    auth_key = derive_key(secret, "snow3g-auth", 32)
    expected_tag = hmac.new(auth_key, nonce + ciphertext, hashlib.sha256).digest()[:16]
    if not hmac.compare_digest(tag, expected_tag):
        raise ValueError("SNOW3G authentication failed")
    keystream = _snow3g_keystream(secret, nonce, len(ciphertext))
    plaintext = bytes(a ^ b for a, b in zip(ciphertext, keystream))
    return plaintext.decode("utf-8")


def caesar_shift(text: str, shift: int) -> str:
    lower_ru = "абвгдеёжзийклмнопрстуфхцчшщъыьэюя"
    upper_ru = lower_ru.upper()
    result = []
    latin_shift = shift % 26
    russian_shift = shift % len(lower_ru)
    for char in text:
        if "a" <= char <= "z":
            result.append(chr((ord(char) - ord("a") + latin_shift) % 26 + ord("a")))
        elif "A" <= char <= "Z":
            result.append(chr((ord(char) - ord("A") + latin_shift) % 26 + ord("A")))
        elif char in lower_ru:
            result.append(lower_ru[(lower_ru.index(char) + russian_shift) % len(lower_ru)])
        elif char in upper_ru:
            result.append(upper_ru[(upper_ru.index(char) + russian_shift) % len(upper_ru)])
        else:
            result.append(char)
    return "".join(result)


def encrypt_caesar(message: str, shift: int) -> str:
    shifted_message = caesar_shift(message, shift)
    payload = _radio_b64encode(shifted_message.encode("utf-8"))
    return f"{CAESAR_PREFIX}{shift % 26}:{len(payload)}:{payload}"


def decrypt_caesar(payload: str, shift: int | None = None) -> str:
    if payload.startswith(CAESAR_PREFIX):
        rest = payload[len(CAESAR_PREFIX):]
        encoded_shift, rest = rest.split(":", 1)
        if shift is None:
            shift = int(encoded_shift)
        if ":" in rest:
            length_text, encoded_payload = rest.split(":", 1)
            payload_length = int(length_text)
            payload = _radio_b64decode(encoded_payload[:payload_length]).decode("utf-8")
        else:
            payload = rest
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
        if self.mode == "snow3g":
            return encrypt_snow3g(message, self.key)
        if self.mode == "caesar":
            return encrypt_caesar(message, int(self.key))
        raise ValueError(f"Unsupported encryption mode: {self.mode}")

    def decrypt(self, payload: str) -> str:
        if self.mode == "none":
            return payload
        if self.mode == "aes" and payload.startswith(AES_PREFIX):
            return decrypt_aes128(payload, self.key)
        if self.mode == "snow3g" and payload.startswith(SNOW3G_PREFIX):
            return decrypt_snow3g(payload, self.key)
        if self.mode == "caesar" and payload.startswith(CAESAR_PREFIX):
            return decrypt_caesar(payload)
        if self.mode == "aes":
            raise ValueError("received packet is not a valid AES packet")
        if self.mode == "caesar":
            raise ValueError("received packet is not a valid Caesar packet")
        if self.mode == "snow3g":
            raise ValueError("received packet is not a valid SNOW3G packet")
        return payload

    @property
    def label(self) -> str:
        if self.mode == "none":
            return "open channel"
        if self.mode == "aes":
            return "AES-128-GCM"
        if self.mode == "snow3g":
            return "Snow3G-style stream cipher"
        if self.mode == "caesar":
            return f"Caesar shift {int(self.key) % 26}"
        return self.mode
