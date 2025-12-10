# lib/core/actuator.py
"""
Actuator state machine (motor + flip-switch).

Phase 0 actuator:
- Very simple "jog" behavior only.
- Higher-level logic (auto open/close based on program state) will come later.

Behavior:
- BTN1_LONG will call jog_fwd()  (move actuator "forward" for a short time)
- BTN2_LONG will call jog_rev()  (move actuator "reverse" for a short time)
- actuator.step() must be called from the main loop.
- After a fixed duration, the motor is stopped automatically.

This is purely time-based (no limit switches yet).
Use carefully and tune JOG_MS for your hardware.
"""

from drivers import control
from hal import hw_esp32

# How long to run the motor on a jog (ms).
# Start conservative; you can tune this after trying it on real hardware.
JOG_MS = 800

_state: str = "IDLE"   # "IDLE" or "MOVING"
_dir: int = 0          # -1 = REV, 0 = STOP, +1 = FWD
_until_ms: int | None = None


def init() -> None:
    """Initialize actuator state and stop motor."""
    global _state, _dir, _until_ms
    _state = "IDLE"
    _dir = 0
    _until_ms = None
    control.stop_motor()


def _start_move(dir_sign: int) -> None:
    """
    Internal helper: start a timed move.

    dir_sign:
        +1 = FWD
        -1 = REV
        0  = no-op
    """
    global _state, _dir, _until_ms

    if dir_sign == 0:
        return

    now = hw_esp32.ticks_ms()
    _until_ms = now + JOG_MS
    _dir = 1 if dir_sign > 0 else -1
    _state = "MOVING"

    if _dir > 0:
        control.set_motor(True, False)
    else:
        control.set_motor(False, True)


def jog_fwd() -> None:
    """
    Jog actuator in the "forward" direction for JOG_MS.

    Map this to whatever you consider the "close switch" direction.
    """
    _start_move(+1)


def jog_rev() -> None:
    """
    Jog actuator in the "reverse" direction for JOG_MS.

    Map this to whatever you consider the "open switch" direction.
    """
    _start_move(-1)


def step() -> None:
    """
    Periodic update; must be called from the main loop.

    - If we're MOVING and the deadline has passed, stop the motor.
    """
    global _state, _dir, _until_ms

    if _state != "MOVING" or _until_ms is None:
        return

    now = hw_esp32.ticks_ms()
    # Handle wrap-around with simple subtraction (ticks_ms is monotonic in uPy)
    if now - _until_ms >= 0:
        control.stop_motor()
        _state = "IDLE"
        _dir = 0
        _until_ms = None


def is_moving() -> bool:
    """Return True if we're currently in a timed jog."""
    return _state == "MOVING"


def get_dir() -> int:
    """
    Get current logical direction:
    -1 = REV, 0 = STOP, +1 = FWD
    """
    return _dir


def get_ui_state() -> str:
    """
    Short string for the UI {ACT} field.

    Returns:
        "IDLE"  - not moving
        "MOV+"  - moving forward
        "MOV-"  - moving reverse
    """
    if _state != "MOVING":
        return "IDLE"
    if _dir > 0:
        return "MOV+"
    if _dir < 0:
        return "MOV-"
    return "IDLE"
