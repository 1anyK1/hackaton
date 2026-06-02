# Task 4: Walkie-talkie на ADALM-Pluto

Реализация real-time рации через SDR ADALM-Pluto:

- `tx`: захват голоса с микрофона ноутбука, NBFM-модуляция, отправка IQ в Pluto TX;
- `rx`: прием IQ с Pluto RX, FM-демодуляция, вывод голоса на динамик;
- `trx`: одновременный TX/RX для разнесенных частот.

## Установка

```bash
cd /home/anyk/Hakaton
source venv/bin/activate
pip install -r task4/requirements.txt
```

По умолчанию приложение пробует `sounddevice`, а если в системе нет PortAudio,
переключается на `soundcard` через PulseAudio/PipeWire. Для принудительного выбора:

```bash
python task4/pluto_walkie_talkie.py tx --audio-backend soundcard --freq 915e6
python task4/pluto_walkie_talkie.py rx --audio-backend soundcard --freq 915e6
```

Для `sounddevice` в Linux нужен PortAudio. Если нужен именно этот backend:

```bash
sudo apt install libportaudio2
```

## Проверка аудиоустройств

```bash
python task4/pluto_walkie_talkie.py devices
```

Если микрофон/динамик выбран не тот, передайте имя или индекс:

```bash
python task4/pluto_walkie_talkie.py tx --input-device 3
python task4/pluto_walkie_talkie.py rx --output-device 5
```

## Запуск

Передатчик:

```bash
python task4/pluto_walkie_talkie.py tx --freq 915e6 --tx-gain -20 --meter
```

Приемник:

```bash
python task4/pluto_walkie_talkie.py rx --freq 915e6 --volume 0.7 --meter
```

Полудуплексная рация обычно запускается на двух Pluto: один ноутбук в режиме `tx`, второй в режиме `rx`.
Для одновременной работы на одном узле используйте разнесенные частоты:

```bash
python task4/pluto_walkie_talkie.py trx --tx-freq 915e6 --rx-freq 916e6 --tx-gain -30
```

Работайте только на разрешенных для вашего стенда частотах, с малой мощностью, аттенюаторами, экранированием или в учебной лабораторной среде.

## Основные параметры

- `--uri`: адрес Pluto, по умолчанию `ip:192.168.3.1`;
- `--freq`: общая частота для `tx` или `rx`;
- `--tx-freq`, `--rx-freq`: отдельные частоты для `trx`;
- `--sdr-rate`: частота дискретизации SDR, по умолчанию `960000`;
- `--audio-rate`: частота дискретизации аудио, по умолчанию `48000`;
- `--deviation`: девиация FM, по умолчанию `5000` Гц;
- `--rf-bandwidth`: RF bandwidth Pluto, по умолчанию `200000` Гц;
- `--tx-gain`: аппаратное усиление TX Pluto в dB, по умолчанию `-20`;
- `--gain-mode`: AGC RX, `slow_attack`, `fast_attack` или `manual`;
- `--rx-gain`: ручное усиление RX, используется только с `--gain-mode manual`;
- `--rx-buffer`: размер буфера приема Pluto, по умолчанию `20480` IQ-сэмплов;
- `--audio-backend`: `auto`, `soundcard` или `sounddevice`;
- `--squelch`: простой порог шумоподавителя по RMS IQ.

## Тест DSP без железа

```bash
python task4/test_dsp.py
```

Тест проверяет, что FM-модулятор и демодулятор сохраняют аудиотон при прохождении через IQ-представление.
