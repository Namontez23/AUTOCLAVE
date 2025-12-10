# lib/core/actuator.py
"""
Actuator state machine (motor + flip-switch).

Behavior (Phase: auto-cycle prototype):

- Long press on BTN1 or BTN2 calls jog_fwd() / jog_rev().
- For now, BOTH of those trigger the SAME auto-cycle:

    1) Extend for AUTO_EXTEND_MS
    2) Wait (motor stopped) for AUTO_WAIT_MS
    3) Retract for AUTO_RETRACT_MS
    4) Stop and return to IDLE

- While a cycle is running, additional jog_*() calls are ignored.
- This is purely time-based (no limit switches yet), so USE CAREFULLY.

You can tune the timings below without touching the rest of the code.
"""

from drivers import control
from hal import hw_esp32

# ---- Timings (ms) -----------------------------------------------------------

AUTO_EXTEND_MS: int = 10_000   # extend duration
AUTO_WAIT_MS: int = 1_000      # pause at end of travel
AUTO_RETRACT_MS: int = 10_000  # retract duration

# ---- Internal state ---------------------------------------------------------

# States:
#   "IDLE"    -> not moving
#   "EXTEND"  -> driving motor forward
#   "WAIT"    -> motor stopped, holding position
#   "RETRACT" -> driving motor reverse
_state: str = "IDLE"

# Logical direction:
#   +1 = forward, -1 = reverse, 0 = stopped
_dir: int = 0

# Deadline for current phase (ticks_ms timestamp), or None when idle
_until_ms: int | None = None


def init() -> None:
    """
    Initialize actuator state and stop motor.

    Call this once from main() before entering the control loop.
    """
    global _state, _dir, _until_ms
    _state = "IDLE"
    _dir = 0
    _until_ms = None
    control.stop_motor()


# ---- Phase helpers ----------------------------------------------------------

def _start_phase(new_state: str, dir_sign: int, duration_ms: int) -> None:
    """
    Internal helper: start a new phase.

    new_state:
        "EXTEND", "WAIT", "RETRACT", or "IDLE"
    dir_sign:
        +1 = FWD, -1 = REV, 0 = STOP
    duration_ms:
        phase duration in milliseconds; if <=0, the phase will complete
        on the very next step() call.
    """
    global _state, _dir, _until_ms

    _state = new_state

    # Direction + motor drive
    if dir_sign > 0:
        _dir = +1
        control.set_motor(True, False)
    elif dir_sign < 0:
        _dir = -1
        control.set_motor(False, True)
    else:
        _dir = 0
        control.stop_motor()

    # Deadline
    now = hw_esp32.ticks_ms()
    _until_ms = now + max(duration_ms, 0)


def _start_auto_cycle() -> None:
    """
    Kick off the auto extend → wait → retract cycle.

    If we're already in the middle of a cycle, this does nothing.
    """
    # Only allow starting from IDLE for now
    if _state != "IDLE":
        return

    # Phase 1: extend
    _start_phase("EXTEND", dir_sign=+1, duration_ms=AUTO_EXTEND_MS)


# ---- Public API used by main.py --------------------------------------------

def jog_fwd() -> None:
    """
    For now, BOTH jog_fwd() and jog_rev() trigger the same auto-cycle:

        extend -> wait -> retract

    This keeps main.on_button_event() unchanged while we prototype the
    actuator behavior.
    """
    _start_auto_cycle()


def jog_rev() -> None:
    """
    See jog_fwd(); currently identical behavior by design.
    """
    _start_auto_cycle()


def step() -> None:
    """
    Periodic update; must be called from the main loop.

    - Advances the current phase when its deadline expires.
    - Sequences through: EXTEND → WAIT → RETRACT → IDLE.
    """
    global _state, _dir, _until_ms

    if _until_ms is None or _state == "IDLE":
        return

    now = hw_esp32.ticks_ms()
    # Handle wrap-around via subtraction, like MicroPython's own pattern
    if now - _until_ms < 0:
        # Still within current phase window
        return

    # Phase complete → decide next phase
    if _state == "EXTEND":
        # Finished extending -> pause
        _start_phase("WAIT", dir_sign=0, duration_ms=AUTO_WAIT_MS)

    elif _state == "WAIT":
        # Finished waiting -> retract
        _start_phase("RETRACT", dir_sign=-1, duration_ms=AUTO_RETRACT_MS)

    elif _state == "RETRACT":
        # Finished retracting -> all done
        control.stop_motor()
        _state = "IDLE"
        _dir = 0
        _until_ms = None

    else:
        # Unknown state; fail-safe to IDLE
        control.stop_motor()
        _state = "IDLE"
        _dir = 0
        _until_ms = None


def is_moving() -> bool:
    """Return True if we're currently in any non-IDLE phase."""
    return _state != "IDLE"


def get_dir() -> int:
    """
    Get current logical direction:
    -1 = REV, 0 = STOP, +1 = FWD
    """
    return _dir


def get_ui_state() -> str:
    """
    Short string for the UI {ACT} field.

    Returns (4 chars max):
        "IDLE"  - not moving
        "EXT+"  - extending
        "WAIT"  - paused
        "EXT-"  - retracting
    """
    if _state == "IDLE":
        return "IDLE"
    if _state == "EXTEND":
        return "EXT+"
    if _state == "WAIT":
        return "WAIT"
    if _state == "RETRACT":
        return "EXT-"
    return "IDLE"
