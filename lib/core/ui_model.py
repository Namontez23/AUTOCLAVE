# lib/core/ui_model.py
"""
UI model: converts numeric readings + SSR state into 16x4 text lines.

Rendering destination (console vs LCD) is handled by drivers.lcd16x4.
"""

import math
import config
from . import units
LCD_COLS = getattr(config, "LCD_COLS", 16)



def _fmt_float_or_nan(value: float, width: int, prec: int) -> str:
    if value is None or math.isnan(value):
        # Show "NaN" but keep width somewhat sane
        txt = "NaN"
        return txt.rjust(width)
    fmt = f"{{:{width}.{prec}f}}"
    return fmt.format(value)



def _fmt_fixed(value: float, width: int, prec: int, nan_text: str) -> str:
    """
    Format a float to a fixed width/precision; handle NaN/None with nan_text.

    Ensures the returned string is exactly `width` characters (trunc/pad).
    """
    # NaN check: val != val is True only for NaN
    if value is None or (isinstance(value, float) and value != value):
        txt = nan_text
    else:
        fmt = "{:." + str(prec) + "f}"
        txt = fmt.format(value)

    # Normalize width
    if len(txt) < width:
        txt = txt + (" " * (width - len(txt)))
    else:
        txt = txt[:width]
    return txt


def make_status_16x4(
    temp_c: float,
    pressure_kg: float,
    ssr_on: bool,
) -> dict:
    """
    Build a 16x4 status dictionary:

        {
          "line1": "...",  # compact T/P with units
          "line2": "...",  # SSR state
          "line3": "...",  # reserved
          "line4": "...",  # reserved
        }

    Layout (16 chars total):
      line1: "T=xxxxxU P=yyyyy"
        - xxxxx is temp (5 chars) via units.format_temp
        - U is unit ("C" or "F")
        - yyyyy is pressure (5 chars) via units.format_press
    """
    # Normalize to floats / NaN-safe; units helpers will cope.
    t = temp_c if temp_c is not None else float("nan")
    p = pressure_kg if pressure_kg is not None else float("nan")

    t_str = units.format_temp(t)          # 5 chars
    p_str = units.format_press(p)         # 5 chars
    u_str = units.temp_unit_str()         # 1 char

    # 2 + 5 + 1 + 3 + 5 = 16 chars total
    line1 = "T=" + t_str + u_str + " P=" + p_str

    line2 = "SSR:ON " if ssr_on else "SSR:OFF"
    line3 = ""
    line4 = ""

    return {
        "line1": line1.ljust(LCD_COLS)[:LCD_COLS],
        "line2": line2.ljust(LCD_COLS)[:LCD_COLS],
        "line3": line3.ljust(LCD_COLS)[:LCD_COLS],
        "line4": line4.ljust(LCD_COLS)[:LCD_COLS],
    }



