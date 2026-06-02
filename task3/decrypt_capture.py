import argparse
import sys

from crypto_protocol import decrypt_aes128, decrypt_caesar


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Decrypt captured PlutoChat messages when the cipher and key are known."
    )
    parser.add_argument("message", nargs="?", help="Captured encrypted message")
    parser.add_argument(
        "--file",
        "-f",
        help="Read captured messages from a text file, one message per line",
    )
    parser.add_argument(
        "--cipher",
        choices=("aes", "caesar"),
        required=True,
        help="Cipher used by the captured team",
    )
    parser.add_argument(
        "--key",
        required=True,
        help="AES shared secret or Caesar numeric shift",
    )
    return parser


def decrypt_one(message: str, cipher: str, key: str) -> str:
    if cipher == "aes":
        return decrypt_aes128(message.strip(), key)
    return decrypt_caesar(message.strip(), int(key))


def main() -> int:
    args = build_parser().parse_args()
    if args.file:
        with open(args.file, "r", encoding="utf-8") as handle:
            messages = [line.rstrip("\n") for line in handle if line.strip()]
    elif args.message:
        messages = [args.message]
    else:
        messages = [line.rstrip("\n") for line in sys.stdin if line.strip()]

    for message in messages:
        print(decrypt_one(message, args.cipher, args.key))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
