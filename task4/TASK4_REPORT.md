# Отчет по заданию 4: Walkie-talkie на ADALM-Pluto

## Цель

Реализована C++ рация для ADALM-Pluto SDR:

- TX захватывает звук с микрофона в реальном времени и передает NBFM IQ через Pluto;
- RX принимает IQ с Pluto, демодулирует FM и выводит очищенный голос на динамик.
- Дополнительно добавлен AM/DSB режим для отладки и случаев, когда FM тонет в шуме.

## Файлы

- `cpp/main.cpp` - основная C++ программа;
- `Makefile` - сборка через `make`;
- `CMakeLists.txt` - альтернативная сборка через CMake;
- `README.md` - команды запуска и настройки.

Python-версия удалена, в `task4` используется только C++.

## Архитектура

Используются две runtime-библиотеки:

- PortAudio для микрофона и динамика;
- libiio для управления ADALM-Pluto.

Заголовки `portaudio.h` и `iio.h` не требуются: функции загружаются динамически через `dlopen`.

## TX Pipeline

1. PortAudio читает блоки микрофона `float32` с частотой `48 kHz`.
2. Микрофонный сигнал проходит:
   - DC blocker;
   - каскадный ФНЧ речи;
   - noise gate по `--mic-gate`;
   - AGC к уровню `--mic-target-rms`;
   - мягкий limiter `tanh`.
3. Аудио преобразуется в выбранную модуляцию:

   FM:

   `phase[n] = phase[n-1] + 2*pi*deviation*audio[n]/sdr_rate`

   AM:

   `iq[n] = carrier + depth*audio[n]`

4. Формируется комплексный IQ:

   `iq[n] = exp(j*phase[n])`

5. IQ масштабируется и отправляется в Pluto TX через libiio.

## RX Pipeline

1. libiio читает комплексные IQ-блоки с Pluto RX.
2. IQ проходит каскадный комплексный ФНЧ `--channel-filter`.
3. FM limiter нормализует амплитуду IQ.
4. Демодулятор восстанавливает аудио:

   FM вычисляет фазовую разность:

   `audio[n] = angle(iq[n] * conj(iq[n-1]))`

   AM использует envelope:

   `audio[n] = abs(iq[n])`

5. Сигнал decimate'ится с `2.4 MHz` до `48 kHz`.
6. Аудио разделяется на:
   - речевую полосу `voice`;
   - шумовую верхнюю полосу `noise`.
7. Gate открывается только если `voice > --squelch` и `voice/noise > --noise-ratio`.
8. На динамик отправляется только очищенный голосовой сигнал.

## Сборка

```bash
cd task4
make
```

## Проверка Радиоканала

RX:

```bash
./pluto_walkie_cpp rx --uri ip:192.168.3.1 --freq 915e6 --sdr-rate 2400000 --volume 0.18 --squelch 0 --channel-filter 30000 --rx-audio-cutoff 2200 --meter
```

TX test tone:

```bash
./pluto_walkie_cpp tx --uri ip:192.168.2.1 --freq 915e6 --sdr-rate 2400000 --tx-gain -8 --tx-amplitude 0.8 --tx-tone 1000 --meter
```

## Голосовая Связь

RX:

```bash
./pluto_walkie_cpp rx --uri ip:192.168.3.1 --freq 915e6 --sdr-rate 2400000 --gain-mode manual --rx-gain 12 --volume 0.22 --squelch 0.035 --noise-ratio 1.15 --channel-filter 30000 --rx-audio-cutoff 2200 --meter
```

TX:

```bash
./pluto_walkie_cpp tx --uri ip:192.168.2.1 --freq 915e6 --sdr-rate 2400000 --tx-gain -8 --tx-amplitude 0.8 --mic-gate 0.003 --mic-target-rms 0.16 --tx-audio-cutoff 2600 --meter
```

AM-режим:

```bash
./pluto_walkie_cpp rx --mod am --uri ip:192.168.3.1 --freq 915e6 --sdr-rate 2400000 --gain-mode manual --rx-gain 20 --volume 0.35 --squelch 0.01 --noise-ratio 0.6 --channel-filter 60000 --rx-audio-cutoff 2400 --meter
./pluto_walkie_cpp tx --mod am --uri ip:192.168.2.1 --freq 915e6 --sdr-rate 2400000 --tx-gain -5 --tx-amplitude 0.85 --am-carrier 0.65 --am-depth 0.22 --mic-gate 0.001 --mic-target-rms 0.14 --tx-audio-cutoff 2400 --meter
```

## Практические Замечания

- Частота `2.4 MS/s` выбрана потому, что Pluto через прямой libiio не принимает `960 kS/s`; минимальное значение на стенде около `2.083 MS/s`.
- Перед настройкой микрофона нужно добиться слышимого тестового тона.
- У Pluto более отрицательный `--tx-gain` означает меньшую мощность.
- Для меньшего шума используйте ручной RX gain и узкий `--channel-filter`.
