# -*- coding: utf-8 -*-
"""Замер уровня микрофона во время синтезированной речи (для подбора порога)."""

import time
from ctypes import POINTER, cast

from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioMeterInformation

dev = AudioUtilities.GetMicrophone()
meter = cast(dev.Activate(IAudioMeterInformation._iid_, CLSCTX_ALL, None),
             POINTER(IAudioMeterInformation))

values = []
start = time.monotonic()
while time.monotonic() - start < 14:
    values.append(meter.GetPeakValue())
    time.sleep(0.05)

values_sorted = sorted(values)
n = len(values_sorted)
print("samples:", n)
print("min {} / median {} / p90 {} / max {}".format(
    round(values_sorted[0], 4), round(values_sorted[n // 2], 4),
    round(values_sorted[int(n * 0.9)], 4), round(values_sorted[-1], 4)))
# грубая оценка: сколько времени уровень выше порогов
for th in (0.005, 0.01, 0.02, 0.03, 0.05, 0.1):
    above = sum(1 for v in values if v >= th)
    print("  >= %.3f : %.0f%% времени" % (th, 100 * above / n))