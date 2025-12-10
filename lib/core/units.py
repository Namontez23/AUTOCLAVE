# lib/core/units.py

import config

UNITS_METRIC = 0
UNITS_USCS   = 1

# Start from config.DEFAULT_UNITS so your config file is the single point of truth.
_current_units = config.DEFAULT_UNITS


def set_units(mode: int) -> None:
    global _current_units
    _current_units = mode


def get_units() -> int:
    return _current_units


def format_temp(temp_c: float) -> str:
    """
    5-char temp, 1 decimal: "121.0"
    Works in both metric and USCS.
    """
    # NaN / None guard
    if temp_c is None:
        return "  NaN "
    try:
        v = float(temp_c)
    except (TypeError, ValueError):
        return "  NaN "

    if _current_units == UNITS_METRIC:
        return "{:5.1f}".format(v)
    else:
        temp_f = v * 9.0 / 5.0 + 32.0
        return "{:5.1f}".format(temp_f)


def temp_unit_str() -> str:
    return "C" if _current_units == UNITS_METRIC else "F"


def format_press(press_kgcm2: float) -> str:
    """
    Format pressure from kg/cm² base into:
    - Metric: kg/cm² with 2 decimals.
    - USCS: psi with 1 decimal.
    """
    if press_kgcm2 is None:
        return "  NaN "
    try:
        v = float(press_kgcm2)
    except (TypeError, ValueError):
        return "  NaN "

    if _current_units == UNITS_METRIC:
        return "{:5.2f}".format(v)
    else:
        psi = v * 14.223  # kg/cm² → psi approx
        return "{:5.1f}".format(psi)


def press_unit_str() -> str:
    return "kg" if _current_units == UNITS_METRIC else "psi"


def units_name() -> str:
    return "METRIC" if _current_units == UNITS_METRIC else "USCS"
