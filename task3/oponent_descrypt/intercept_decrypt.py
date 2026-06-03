#!/usr/bin/env python3
"""
Перехват и расшифровка (задание 3.3) - МОДИФИЦИРОВАННАЯ ВЕРСИЯ.

Третий участник / вторая команда с Pluto в promiscuous-приёме слушает эфир
и расшифровывает, если известны cipher и key соперника.

Если расшифровка не удалась - показывает префикс и зашифрованное сообщение.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

from pluto_path import setup_pluto_path

setup_pluto_path()

from crypto.protocol import CIPHERS, decrypt_message, looks_encrypted  # noqa: E402
from receiver_module.operation_RX import operation_RX  # noqa: E402
from pluto_radio import configure_ota_chat, connect_pluto  # noqa: E402

MHZ = int(1e6)


def main() -> int:
    p = argparse.ArgumentParser(description="Перехват PlutoChat + расшифровка")
    p.add_argument("--uri", default=os.environ.get("PLUTO_URI"))
    p.add_argument("--ip", default=None)
    p.add_argument("--cipher", choices=[*CIPHERS, "auto"], default="auto")
    p.add_argument("--key", required=True, help="Ключ противника")
    p.add_argument("--rx-lo-mhz", type=int, default=int(os.environ.get("PLUTO_RX_LO_MHZ", "900")))
    p.add_argument("--sample-rate-mhz", type=int, default=10)
    p.add_argument("--bandwidth-mhz", type=int, default=10)
    p.add_argument("--log", default="logs/intercept.log")
    p.add_argument("--show-encrypted", action="store_true", default=True,
                   help="Показывать зашифрованные сообщения даже при ошибке расшифровки")
    p.add_argument("--raw", action="store_true",
                   help="Показывать RAW данные (префикс + сообщение)")
    args = p.parse_args()

    os.makedirs(os.path.dirname(args.log) or ".", exist_ok=True)

    uri = args.uri or (f"ip:{args.ip}" if args.ip else None)
    sdr = connect_pluto(uri, "sniffer")
    configure_ota_chat(sdr)
    sdr.rx_lo = args.rx_lo_mhz * MHZ
    sdr.sample_rate = args.sample_rate_mhz * MHZ
    sdr.rx_rf_bandwidth = args.bandwidth_mhz * MHZ
    sdr.tx_rf_bandwidth = args.bandwidth_mhz * MHZ
    sdr.gain_control_mode_chan0 = "slow_attack"
    sdr.rx_buffer_size = int(2**16)

    print(f"Сниффер на {sdr._uri_used}, RX LO={args.rx_lo_mhz} MHz. Ctrl+C — стоп.")
    print(f"Режим: показ зашифрованных сообщений = {args.show_encrypted}")
    cipher_arg = None if args.cipher == "auto" else args.cipher

    try:
        with open(args.log, "a", encoding="utf-8") as logf:
            while True:
                raw = operation_RX(sdr, False)
                if not raw:
                    time.sleep(0.3)
                    continue
                
                ts = time.strftime("%H:%M:%S")
                
                # Всегда логируем RAW данные
                logf.write(f"[{ts}] RAW: {raw}\n")
                logf.flush()
                
                # Если нужно показать RAW данные в консоли
                if args.raw:
                    print(f"[{ts}] 📡 RAW: {raw}")
                
                # Проверяем, похоже ли на зашифрованное
                if not looks_encrypted(raw):
                    print(f"[{ts}] 📄 ОТКРЫТЫЙ ТЕКСТ: {raw}")
                    continue
                
                # Пытаемся расшифровать
                try:
                    plain = decrypt_message(raw, cipher_arg, args.key)  # type: ignore[arg-type]
                    print(f"[{ts}] 🔓 *** РАСШИФРОВАНО: {plain}")
                    logf.write(f"[{ts}] DECRYPTED: {plain}\n")
                except Exception as exc:
                    # Расшифровка не удалась
                    print(f"[{ts}] 🔒 ЗАШИФРОВАНО (ошибка: {exc})")
                    
                    # Показываем префикс и часть сообщения
                    prefix = raw[:5] if len(raw) > 5 else raw  # Первые 5 символов (AES1:, CAE1:, SNO1:)
                    
                    # Определяем тип префикса
                    if raw.startswith("AES1:"):
                        prefix_type = "AES-128"
                        # Показываем весь шифротекст (если не очень длинный)
                        display_raw = raw[:100] + "..." if len(raw) > 100 else raw
                    elif raw.startswith("CAE1:"):
                        prefix_type = "CAESAR"
                        # Для Цезаря показываем больше (он короче)
                        display_raw = raw[:150] + "..." if len(raw) > 150 else raw
                    elif raw.startswith("SNO1:"):
                        prefix_type = "Snow3G"
                        display_raw = raw[:100] + "..." if len(raw) > 100 else raw
                    else:
                        prefix_type = "UNKNOWN"
                        display_raw = raw[:80] + "..." if len(raw) > 80 else raw
                    
                    print(f"[{ts}] 📋 ТИП: {prefix_type}")
                    print(f"[{ts}] 📋 ПРЕФИКС: {prefix}")
                    print(f"[{ts}] 📋 СООБЩЕНИЕ: {display_raw}")
                    
                    # Если включён режим показа всех зашифрованных
                    if args.show_encrypted:
                        print(f"[{ts}] 🔐 ПОЛНЫЙ ШИФРОТЕКСТ: {raw}")
                    
                    logf.write(f"[{ts}] FAILED_DECRYPT: {raw}\n")
                    logf.write(f"[{ts}] ERROR: {exc}\n")
                    
    except KeyboardInterrupt:
        print("\nОстановлено.")
    return 0


if __name__ == "__main__":
    sys.exit(main())