# lib/hal/hw_esp32.py
"""
ESP32 hardware abstraction.

Phase 0:
- Time helpers (ticks / sleep) so main loop doesn't depend on CPython vs uPy.

Phase 0.2:
- Minimal GPIO binding for SSR output.

Phase 0.3:
- ADC + SPI helpers for pressure sensor and MAX31855 thermocouple.

NEW (Phase 0 actuator):
- Motor FWD/REV outputs.
- Alarm output.

Desktop (CPython):
- All hardware helpers become safe no-ops; sensors layer will fall back to
  dummy values because on_real_hw() returns False.
"""

import time

try:
    import machine  # type: ignore[import-not-found]
    _REAL_HW = True
except ImportError:  # CPython, or non-ESP32 interpreter
    machine = None  # type: ignore[assignment]
    _REAL_HW = False

# SSR pin handle (MicroPython only)
_ssr_pin = None

# Motor pins
_motor_fwd_pin = None
_motor_rev_pin = None

# Alarm pin
_alarm_pin = None

# Pressure sensor ADC handle
_pressure_adc = None

# Thermocouple MAX31855 SPI + CS
_tc_spi = None
_tc_cs = None


def on_real_hw() -> bool:
    """Return True when running on MicroPython/ESP32 with machine module."""
    return _REAL_HW


def ticks_ms() -> int:
    """Return milliseconds since boot."""
    try:
        return time.ticks_ms()  # type: ignore[attr-defined]
    except AttributeError:
        # CPython fallback
        return int(time.time() * 1000)


def sleep_ms(ms: int) -> None:
    """Sleep for the given number of milliseconds."""
    try:
        time.sleep_ms(ms)  # type: ignore[attr-defined]
    except AttributeError:
        time.sleep(ms / 1000.0)


def init_io() -> None:
    """
    Initialize low-level IO (SSR pin, motor pins, alarm).

    On CPython (no `machine`), this is a no-op so desktop tests still work.
    """
    global _ssr_pin, _motor_fwd_pin, _motor_rev_pin, _alarm_pin

    if not _REAL_HW:
        _ssr_pin = None
        _motor_fwd_pin = None
        _motor_rev_pin = None
        _alarm_pin = None
        return

    import config  # local import to avoid cycles at module import time

    # ----- SSR -----
    _ssr_pin = machine.Pin(config.PIN_SSR, machine.Pin.OUT)
    # Respect active-high polarity; OFF means logical False.
    _ssr_pin.value(0 if config.SSR_ACTIVE_HIGH else 1)

    # ----- Motor FWD/REV -----
    # Assumption: active-high drive (1=ON, 0=OFF).
    _motor_fwd_pin = machine.Pin(config.PIN_MOTOR_FWD, machine.Pin.OUT)
    _motor_rev_pin = machine.Pin(config.PIN_MOTOR_REV, machine.Pin.OUT)
    _motor_fwd_pin.value(0)
    _motor_rev_pin.value(0)

    # ----- Alarm -----
    _alarm_pin = machine.Pin(config.PIN_ALARM, machine.Pin.OUT)
    if getattr(config, "ALARM_ACTIVE_HIGH", True):
        _alarm_pin.value(0)  # OFF
    else:
        _alarm_pin.value(1)  # OFF (active-low)


def write_ssr(on: bool) -> None:
    """
    Drive the physical SSR output.

    - On MicroPython: writes to the configured GPIO.
    - On CPython / no machine: no-op, but keeps API surface consistent.
    """
    if _ssr_pin is None:
        return

    import config

    if config.SSR_ACTIVE_HIGH:
        _ssr_pin.value(1 if on else 0)
    else:
        _ssr_pin.value(0 if on else 1)


def write_motor(fwd: bool, rev: bool) -> None:
    """
    Drive motor direction pins.

    Policy:
    - Never drive both FWD and REV at once.
    - If both requested True, we treat it as STOP (both low).
    - Active-high assumed for both pins.
    """
    global _motor_fwd_pin, _motor_rev_pin

    if _motor_fwd_pin is None or _motor_rev_pin is None:
        return

    # Safety: never allow both directions simultaneously
    if fwd and rev:
        fwd = False
        rev = False

    _motor_fwd_pin.value(1 if fwd else 0)
    _motor_rev_pin.value(1 if rev else 0)


def write_alarm(on: bool) -> None:
    """
    Drive alarm output.

    Active polarity is taken from config.ALARM_ACTIVE_HIGH.
    """
    global _alarm_pin

    if _alarm_pin is None:
        return

    import config

    if getattr(config, "ALARM_ACTIVE_HIGH", True):
        _alarm_pin.value(1 if on else 0)
    else:
        _alarm_pin.value(0 if on else 1)


# ---- Pressure ADC helpers ---------------------------------------------------

def init_pressure_adc() -> None:
    """Configure ADC channel for the pressure sensor (GPIO32)."""
    global _pressure_adc

    if not _REAL_HW:
        _pressure_adc = None
        return

    import config

    pin = machine.Pin(config.PIN_PRESSURE_ADC)
    adc = machine.ADC(pin)
    # ESP32 ADC: 0–4095 range typically; atten 11dB gives ~0–3.3V
    adc.atten(machine.ADC.ATTN_11DB)  # type: ignore[attr-defined]
    adc.width(machine.ADC.WIDTH_12BIT)  # type: ignore[attr-defined]

    _pressure_adc = adc


def read_pressure_volts():
    """
    Read pressure ADC and convert to volts.

    Returns float volts, or None if ADC not available.
    """
    if _pressure_adc is None:
        return None

    # 12-bit ADC: 0–4095 counts, approximate 3.3V full-scale.
    raw = _pressure_adc.read()
    if raw is None:
        return None

    return (raw / 4095.0) * 3.3


# ---- MAX31855 thermocouple helpers -----------------------------------------

def init_tc_spi() -> None:
    """Initialize SPI + CS for MAX31855."""
    global _tc_spi, _tc_cs

    if not _REAL_HW:
        _tc_spi = None
        _tc_cs = None
        return

    import config

    # MAX31855 is read-only, SPI mode 0, up to ~5 MHz comfortably.
    _tc_spi = machine.SPI(
        1,
        baudrate=1_000_000,
        polarity=0,
        phase=0,
        sck=machine.Pin(config.PIN_SPI_SCLK),
        mosi=machine.Pin(config.PIN_SPI_MOSI),
        miso=machine.Pin(config.PIN_SPI_MISO),
    )
    _tc_cs = machine.Pin(config.PIN_TC_CS, machine.Pin.OUT)
    _tc_cs.value(1)  # CS idle high


def read_tc_raw32():
    """
    Read 32-bit raw value from MAX31855.

    Returns:
        int 32-bit sample, or None on error / not initialized.
    """
    if _tc_spi is None or _tc_cs is None:
        return None

    buf = bytearray(4)
    _tc_cs.value(0)
    try:
        _tc_spi.readinto(buf)
    finally:
        _tc_cs.value(1)

    # Combine 4 bytes into 32-bit int, big-endian
    value = (buf[0] << 24) | (buf[1] << 16) | (buf[2] << 8) | buf[3]
    return value
