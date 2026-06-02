# Задание 3: секретный чат на PlutoSDR

## Что было сделано

1. В эту директорию был помещен исходный проект `pluto-chat`.
2. В файл `crypto_protocol.py` был добавлен слой шифрования сообщений.
3. `pluto_chat.py` теперь шифрует исходящие сообщения и расшифровывает входящие зашифрованные сообщения.
4. Для расшифровки перехваченных сообщений добавлена утилита `decrypt_capture.py`.
5. Приемник был доработан: добавлена фильтрация ложных Barker-заголовков внутри кадра, из-за которых длинные AES-пакеты могли повреждаться.

## Протокол шифрования

Основной реализованный протокол: AES-128-GCM.

- префикс сообщения: `AES1:`
- nonce: 12 случайных байт на каждое сообщение
- ключ: первые 16 байт от `SHA-256(shared_password)`
- полезная нагрузка: radio-safe URL Base64 от `nonce + ciphertext + authentication_tag`
- формат пакета: `AES1:<payload_length>:<payload>`

AES-GCM обеспечивает конфиденциальность и контроль целостности: при неправильном ключе или поврежденном ciphertext сообщение не расшифровывается.

Также добавлен режим Caesar для демонстрации перехвата:

- префикс сообщения: `CAE1:<shift>:`
- буквы сдвигаются на выбранное значение
- небуквенные символы передаются без изменений

## Запуск

Установка зависимостей:

```bash
python3 -m pip install -r requirements.txt
sudo apt install libiio0 libiio-utils
```

Запуск чата:

```bash
python3 pluto_chat.py
```

Если виртуальное окружение находится в `../venv`, можно запускать так:

```bash
../venv/bin/python pluto_chat.py
```

Не рекомендуется запускать `sudo python3 pluto_chat.py`, потому что так используется системный Python, а не виртуальное окружение. Если запуск от root все-таки нужен:

```bash
sudo ../venv/bin/python pluto_chat.py
```

Рекомендуемый порядок действий в меню:

```text
1. Add a radio
4. Set Encryption
5. Chat
```

Обе стороны должны использовать одинаковые радионастройки, режим шифрования и ключ.

## Рекомендуемые настройки SDR

Для двух подключенных ADALM-Pluto:

```text
Tx Local Oscillator: 900
Rx Local Oscillator: 900
Sample Rate: 10
Tx-Rx Bandwidth: 10
Tx Gain: -10
Rx Gain Type: Slow Attack
Rx Sample Size 2**N: 16
Tx Sample Size 2**N: 18
```

Через меню:

```text
3. Change Radio Parameters
1 -> 900
2 -> 900
3 -> 10
4 -> 10
5 -> -10
6 -> 2
7 -> 18
8 -> 16
10 -> Back
```

Практические замечания:

- обе стороны не должны отправлять сообщения одновременно;
- после отправки стоит подождать 3-5 секунд;
- если Pluto стоят очень близко, можно уменьшить мощность, например поставить `Tx Gain: -15` или `-30`;
- режим loopback должен быть `0`.

## Перехват и расшифровка

Расшифровка перехваченного AES-сообщения:

```bash
python3 decrypt_capture.py --cipher aes --key "team-password" "AES1:..."
```

Расшифровка сообщения Caesar:

```bash
python3 decrypt_capture.py --cipher caesar --key 7 "CAE1:7:Hahjr ..."
```

Расшифровка нескольких сообщений из файла:

```bash
python3 decrypt_capture.py --cipher aes --key "team-password" --file captured.txt
```

## Измененные файлы

- `pluto_chat.py` - интеграция чата с шифрованием и меню выбора режима.
- `crypto_protocol.py` - реализация AES-128-GCM и Caesar.
- `decrypt_capture.py` - утилита для расшифровки перехваченных сообщений.
- `receiver_module/operation_RX.py` - фильтрация ложных Barker-пиков при приеме.
- `utils/my_radio.py` - настройки PlutoSDR по умолчанию для чата.
- `test_crypto_protocol.py` - тесты round-trip для протокола.
- `requirements.txt` - зависимости проекта.
