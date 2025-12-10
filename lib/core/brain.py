# lib/core/brain.py
"""
Brain: decides heater (SSR) state based on temp/pressure.

Phase 0:
- Implement same *shape* of logic as C brain.c (temp + pressure gates),
  but globally disable heat (SSR always OFF).
- This proves the call chain without risking a live heater.

Phase 0.1:
- Expose the internal "allow_heat" window for UI/debug.
"""

import config
from drivers import sensors, control

# Internal state for UI / introspection
_ssr_on: bool = False
_allow_heat: bool = False  # NEW: last allow_heat decision


def step_once() -> None:
    """
    One control step.
    Phase 0:
      - Read temp/pressure.
      - Compute allow_heat window (same shape as C brain.c).
      - Force SSR OFF regardless, so we get a safe pipeline.
    """
    global _ssr_on, _allow_heat

    t_c = sensors.read_tc_c()
    p_kg = sensors.read_pressure_kgcm2()

    # Conservative pre-PID window (copied concept from C):
    allow_heat = False

    # Temperature gate
    if t_c is not None:
        if 0.0 < t_c < config.APP_MAX_TEMP_C:
            allow_heat = True

    # Pressure gate – fail safe if we don't trust it
    if p_kg is None:
        allow_heat = False
    else:
        if p_kg >= config.APP_MAX_PRESSURE_KGCM2:
            allow_heat = False

    # Remember the window decision for introspection / UI
    _allow_heat = allow_heat

    # Heater policy:
    # - If config.HEAT_ENABLE is False → always OFF (Phase 0 safety).
    # - If True → follow conservative allow_heat window.
    if config.HEAT_ENABLE:
        _ssr_on = allow_heat
    else:
        _ssr_on = False

    # Drive control layer
    control.set_ssr(_ssr_on)


def get_ssr_state() -> bool:
    """Return last SSR state for UI and debugging."""
    return _ssr_on


def get_allow_heat() -> bool:
    """
    Return the last computed allow_heat decision.

    This is "would we allow heat if HEAT_ENABLE were True",
    ignoring the global safety kill switch.
    """
    return _allow_heat
