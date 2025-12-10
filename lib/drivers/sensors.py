# lib/drivers/sensors.py
"""
Sensors driver: thermocouple + pressure.

Phase 0:
- Return dummy values so we can exercise the pipeline.

Phase 0.2:
- Map real pressure ADC voltage -> kg/cm² using config calibration.

Phase 0.3:
- Read real thermocouple via MAX31855 over SPI.

Desktop (CPython):
- Still uses dummy values so the pipeline runs without hardware.
"""

import math
import config
from hal import hw_esp32

# Simple demo defaults / desktop fallback
_temp_c: float = 25.0
_pressure_kg: float = 0.5


def init() -> None:
    """
    Initialize sensor layer.

    Desktop:
    - Reset dummy values.

    MicroPython:
    - Reset dummy values.
    - Initialize ADC + SPI for real sensors.
    """
    global _temp_c, _pressure_kg
    _temp_c = 25.0
    _pressure_kg = 0.5

    if hw_esp32.on_real_hw():
        hw_esp32.init_pressure_adc()
        hw_esp32.init_tc_spi()


# ---- Pressure mapping (Phase 0.2) ------------------------------------------

def _map_voltage_to_kgcm2(v: float) -> float:
    """
    Mirror sensors.c: volts at pin -> kg/cm² using metric-centered mapping.
    """
    span_v = config.PRESSURE_V_PIN_MAX - config.PRESSURE_V_PIN_MIN
    if span_v <= 0.0:
        return float("nan")

    ratio = (v - config.PRESSURE_V_PIN_MIN) / span_v
    if ratio < 0.0:
        ratio = 0.0
    elif ratio > 1.0:
        ratio = 1.0

    span_p = config.PRESSURE_P_MAX_KGCM2 - config.PRESSURE_P_MIN_KGCM2
    return config.PRESSURE_P_MIN_KGCM2 + ratio * span_p


def read_pressure_kgcm2() -> float:
    """Return pressure in kg/cm² (real ADC on board, dummy on desktop)."""
    if not hw_esp32.on_real_hw():
        # Desktop: keep old dummy behavior
        return _pressure_kg

    volts = hw_esp32.read_pressure_volts()
    if volts is None:
        return float("nan")

    return _map_voltage_to_kgcm2(volts)


# ---- Thermocouple MAX31855 (Phase 0.3) -------------------------------------

def _decode_tc_c_from_raw(raw: int) -> float:
    """
    Port of tc_max31855.c thermocouple temperature decoding.

    Returns:
        Thermocouple temperature in °C, or NaN if fault.
    """
    # Fault bits
    fault = (raw & 0x00010000) != 0
    # scv = (raw & 0x00000004) != 0
    # scg = (raw & 0x00000002) != 0
    # oc  = (raw & 0x00000001) != 0

    # Thermocouple temperature: bits [31:18], signed 14-bit, 0.25°C/LSB
    tc14 = (raw >> 18) & 0x3FFF
    if tc14 & 0x2000:  # sign bit
        tc14 |= 0xC000  # sign-extend to 16 bits

    if fault:
        return float("nan")

    return tc14 * 0.25


def read_tc_c() -> float:
    """Return thermocouple temperature in °C (real MAX31855 or dummy)."""
    if not hw_esp32.on_real_hw():
        # Desktop: dummy constant (or your ramp if you want).
        # global _temp_c
        # _temp_c += 0.2
        # return _temp_c
        return _temp_c

    raw = hw_esp32.read_tc_raw32()
    if raw is None:
        return float("nan")

    return _decode_tc_c_from_raw(raw)
