from crypto_protocol import (
    ChatCrypto,
    decrypt_aes128,
    decrypt_caesar,
    decrypt_snow3g,
    encrypt_aes128,
    encrypt_caesar,
    encrypt_snow3g,
)


def test_aes_roundtrip_hides_plaintext():
    secret = "team-shared-key"
    message = "Meet at 900 MHz"

    encrypted = encrypt_aes128(message, secret)

    assert encrypted.startswith("AES1:")
    assert message not in encrypted
    assert decrypt_aes128(encrypted, secret) == message


def test_caesar_roundtrip():
    encrypted = encrypt_caesar("Attack at dawn", 7)

    assert encrypted.startswith("CAE1:7:")
    assert decrypt_caesar(encrypted) == "Attack at dawn"


def test_snow3g_roundtrip_hides_plaintext():
    secret = "team-snow-key"
    message = "Snow mode message"

    encrypted = encrypt_snow3g(message, secret)

    assert encrypted.startswith("SNOW1:")
    assert message not in encrypted
    assert decrypt_snow3g(encrypted, secret) == message


def test_chat_crypto_detects_payload_type():
    crypto = ChatCrypto(mode="aes", key="secret")
    encrypted = crypto.encrypt("hello")

    assert crypto.decrypt(encrypted) == "hello"
    try:
        crypto.decrypt("plain text")
    except ValueError:
        pass
    else:
        raise AssertionError("AES mode should reject unencrypted packets")
