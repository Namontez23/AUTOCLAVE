# lib/drivers/control.py
"""
Control driver: SSR, alarm, motor.

Phase 0:
- Implement only SSR as a tracked boolean.

Phase 0.2:
- Bind SSR to real GPIO via hal.hw_esp32 when available.

Phase 0 actuator:
- Add simple motor direction control (FWD/REV).
- Add alarm control.
"""

_ssr_on: bool = False
_motor_dir: int = 0  # -1 = REV, 0 = STOP, +1 = FWD
_alarm_on: bool = False

try:
    from hal import hw_esp32
    _HAS_HAL = True
except ImportError:
    hw_esp32 = None  # type: ignore[assignment]
    _HAS_HAL = False


def init() -> None:
    """Initialize control state and, on ESP32, configure hardware pins."""
    global _ssr_on, _motor_dir, _alarm_on
    _ssr_on = False
    _motor_dir = 0
    _alarm_on = False

    if _HAS_HAL and hasattr(hw_esp32, "init_io"):
        hw_esp32.init_io()
        # Ensure physical outputs are OFF at boot
        if hasattr(hw_esp32, "write_ssr"):
            hw_esp32.write_ssr(False)
        if hasattr(hw_esp32, "write_motor"):
            hw_esp32.write_motor(False, False)
        if hasattr(hw_esp32, "write_alarm"):
            hw_esp32.write_alarm(False)


# ---- SSR --------------------------------------------------------------------

def set_ssr(on: bool) -> None:
    """
    Set logical SSR state.

    Phase 0.2:
    - Track in a variable.
    - If running on ESP32 (MicroPython), also drive the real SSR GPIO.
    """
    global _ssr_on
    _ssr_on = bool(on)

    if _HAS_HAL and hasattr(hw_esp32, "write_ssr"):
        hw_esp32.write_ssr(_ssr_on)


def get_ssr() -> bool:
    """Return current logical SSR state."""
    return _ssr_on


# ---- Motor ------------------------------------------------------------------

def set_motor(fwd: bool, rev: bool) -> None:
    """
    Drive motor FWD/REV pins.

    - If both fwd and rev are True, treat as STOP (safety).
    - Tracks a simple -1/0/+1 direction for higher layers.
    """
    global _motor_dir

    if fwd and rev:
        fwd = False
        rev = False

    if fwd:
        _motor_dir = +1
    elif rev:
        _motor_dir = -1
    else:
        _motor_dir = 0

    if _HAS_HAL and hasattr(hw_esp32, "write_motor"):
        hw_esp32.write_motor(fwd, rev)


def stop_motor() -> None:
    """Convenience: stop motor (both pins low)."""
    set_motor(False, False)


def get_motor_dir() -> int:
    """
    Get current motor direction:
    -1 = REV, 0 = STOP, +1 = FWD
    """
    return _motor_dir


# ---- Alarm ------------------------------------------------------------------

def set_alarm(on: bool) -> None:
    """Set logical alarm state and drive hardware if available."""
    global _alarm_on
    _alarm_on = bool(on)

    if _HAS_HAL and hasattr(hw_esp32, "write_alarm"):
        hw_esp32.write_alarm(_alarm_on)


def get_alarm() -> bool:
    """Return current alarm state."""
    return _alarm_on
