# Task 4: Walkie-talkie на ADALM-Pluto

C++ реализация real-time рации через две SDR ADALM-Pluto:

- `tx`: микрофон ноутбука -> очистка речи -> NBFM -> Pluto TX;
- `rx`: Pluto RX -> фильтрация IQ -> FM-demod -> шумоподавление -> динамик.

Python-версия удалена: в `task4` используется только C++.

## Сборка

```bash
cd /home/anyk/Hakaton/task4
make
```

Используются runtime-библиотеки `libiio.so.0` и `libportaudio.so.2`. Заголовки `iio.h` и `portaudio.h` не нужны, потому что программа грузит функции через `dlopen`.

## Аудиоустройства

```bash
./pluto_walkie_cpp devices
```

Сообщения ALSA/JACK при старте обычно не критичны, если после них программа выводит список устройств или строку `RX C++...` / `TX C++...`.

## Проверка Канала

Сначала проверьте не микрофон, а сам радиоканал. На RX:

```bash
./pluto_walkie_cpp rx --uri ip:192.168.3.1 --freq 915e6 --sdr-rate 2400000 --volume 0.18 --squelch 0 --channel-filter 30000 --rx-audio-cutoff 2200 --meter
```

На TX:

```bash
./pluto_walkie_cpp tx --uri ip:192.168.2.1 --freq 915e6 --sdr-rate 2400000 --tx-gain -8 --tx-amplitude 0.8 --tx-tone 1000 --meter
```

Если тон не слышен, проверьте URI, частоту, антенны/кабель и мощность TX. Для Pluto значение `-5` мощнее, чем `-20`.

Если тон не слышен совсем, проверьте raw IQ на приемнике во время включенного TX:

```bash
iio_readdev -u ip:192.168.3.1 -b 1024 -s 1024 cf-ad9361-lpc voltage0 voltage1 2>/dev/null | od -An -t d2 | head
```

Если значения остаются примерно `-2...2`, приемник почти не видит радиосигнал. В этом случае надо проверять физический тракт: антенны, кабель, разъемы TX/RX, расстояние, частоту и то, что TX запущен на другой Pluto.

## Рабочий Пресет

RX:

```bash
./pluto_walkie_cpp rx --uri ip:192.168.3.1 --freq 915e6 --sdr-rate 2400000 --gain-mode manual --rx-gain 12 --volume 0.22 --squelch 0.035 --noise-ratio 1.15 --channel-filter 30000 --rx-audio-cutoff 2200 --meter
```

TX:

```bash
./pluto_walkie_cpp tx --uri ip:192.168.2.1 --freq 915e6 --sdr-rate 2400000 --tx-gain -8 --tx-amplitude 0.8 --mic-gate 0.003 --mic-target-rms 0.16 --tx-audio-cutoff 2600 --meter
```

Это самый тихий стартовый вариант: узкий IQ-фильтр, низкий речевой ФНЧ, ручной RX gain и squelch по отношению голосовой энергии к шумовой.

## Альтернатива: AM

Если FM-голос тонет в шипении, можно попробовать AM/DSB с несущей. Этот режим менее эффективен по мощности, но проще демодулируется и полезен для отладки слабого стенда.

RX AM:

```bash
./pluto_walkie_cpp rx --mod am --uri ip:192.168.3.1 --freq 915e6 --sdr-rate 2400000 --gain-mode manual --rx-gain 20 --volume 0.35 --squelch 0.01 --noise-ratio 0.6 --channel-filter 60000 --rx-audio-cutoff 2400 --meter
```

TX AM:

```bash
./pluto_walkie_cpp tx --mod am --uri ip:192.168.2.1 --freq 915e6 --sdr-rate 2400000 --tx-gain -5 --tx-amplitude 0.85 --am-carrier 0.65 --am-depth 0.22 --mic-gate 0.001 --mic-target-rms 0.14 --tx-audio-cutoff 2400 --meter
```

Тестовый тон AM:

```bash
./pluto_walkie_cpp tx --mod am --uri ip:192.168.2.1 --freq 915e6 --sdr-rate 2400000 --tx-gain -5 --tx-amplitude 0.85 --tx-tone 1000 --meter
```

После запуска TX смотрите на `TX audio rms`. Для AM желательно `0.12...0.25`. Если видите около `0.4`, звук будет грязным: уменьшите `--mic-target-rms` до `0.12...0.16`.

## Meter

RX meter показывает:

- `iq_rms`: уровень входных IQ;
- `voice`: энергия в речевой полосе;
- `noise`: энергия выше речевой полосы;
- `q`: отношение `voice/noise`;
- `gate`: насколько открыт выходной шумоподавитель;
- `out`: фактический RMS на динамик.

Если `gate` держится около `0`, приемник считает сигнал шумом. Если `gate` близок к `1`, звук пропускается.

## Минимальная Подстройка

- Много шума: `--squelch 0.05`, `--noise-ratio 1.4`, `--rx-audio-cutoff 1800`.
- Голос пропадает: `--squelch 0.015`, `--noise-ratio 0.8`.
- Голос слишком тихий: на TX `--tx-gain -5`; если AM остается чистой, можно поднять `--mic-target-rms` до `0.18`.
- Микрофон подрезает начало слов: `--mic-gate 0.001`.
- Слишком глухо: `--rx-audio-cutoff 2600`.

## Основные Параметры

- `--uri`: адрес Pluto;
- `--freq`: центральная частота;
- `--sdr-rate`: частота SDR, по умолчанию `2400000`, так как Pluto не принимает `960000` напрямую через libiio;
- `--tx-gain`: аппаратный TX gain Pluto, ближе к `0` значит мощнее;
- `--rx-gain`: ручной RX gain при `--gain-mode manual`;
- `--channel-filter`: ФНЧ по комплексному IQ до FM-demod;
- `--rx-audio-cutoff`: аудио-ФНЧ после FM-demod;
- `--tx-audio-cutoff`: ФНЧ микрофона перед FM;
- `--squelch`: минимальный уровень речевой полосы;
- `--noise-ratio`: минимальное отношение `voice/noise` для открытия gate.
