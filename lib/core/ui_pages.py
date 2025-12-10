# lib/core/ui_pages.py
"""
UI pages and template expansion for 16x4 LCD.

- Pages are defined as data (id + up to 4 template strings).
- Placeholders like {TEMP}, {PUNIT}, {STEP_IDX} are replaced
  from a context dict.
- Each expanded line is truncated/padded to exactly 16 chars.

NEW:
- If text files exist in ./ui_templates/<page_id>.txt, those lines
  override the built-in defaults for that page.
  This lets you tweak the LCD layout without touching Python code.
"""

from . import units
import config
import sys

# ---------- Locate project root + ui_templates directory ---------------------

try:
    _HERE = __file__
except NameError:
    _HERE = ""

if "/" in _HERE:
    # Example: /remote/lib/core/ui_pages.py -> /remote
    root, _, _ = _HERE.partition("/lib/")
    _PROJECT_ROOT = root or "."
else:
    # Fallback (interactive / odd loader)
    _PROJECT_ROOT = "."

# Folder on the device (absolute-ish, relative to project root)
_UI_TEMPLATE_DIR = _PROJECT_ROOT + "/ui_templates"

# ---------- Built-in defaults (used if no txt override) ----------------------

_DEFAULT_PAGES = {
    "status": {
        "id": "status",
        "lines": [
            "T:{TEMP}{TUNIT} P:{PRESS}{PUNIT}",
            "SSR:{SSR} ACT:{ACT}",
            "Step {STEP_IDX}/{STEP_COUNT}",
            "{MESSAGE}",
        ],
    },
    "limits": {
        "id": "limits",
        "lines": [
            "MaxT:{APP_MAX_TEMP}{TUNIT}",
            "MaxP:{APP_MAX_PRESS}{PUNIT}",
            "Units:{UNITS_NAME}",
            "Program:{PROGRAM_NAME}",
        ],
    },
    "debug": {
        "id": "debug",
        "lines": [
            "TEMP_RAW:{TEMP}",
            "PRESS_RAW:{PRESS}",
            "SSR:{SSR} ACT:{ACT}",
            "{DEBUG_HINT}",
        ],
    },
}

# This is what callers use. We’ll populate it from defaults,
# then layer in any txt overrides we find.
PAGES = {}


# ---------- Small filesystem loader -----------------------------------------

def _load_page_from_file(page_id: str) -> list | None:
    """
    Try to load a page template from ./ui_templates/<page_id>.txt
    """
    path = "{}/{}.txt".format(_UI_TEMPLATE_DIR, page_id)
    try:
        f = open(path, "r")
    except OSError:
        # Optional: uncomment for debugging:
        # print("ui_pages: no template for", page_id, "at", path, ":", e)
        return None

    try:
        raw_lines = f.read().splitlines()
    finally:
        f.close()

    lines = raw_lines[:4]
    if len(lines) < 4:
        lines += [""] * (4 - len(lines))
    return lines



def _init_pages() -> None:
    """
    Initialize PAGES from defaults, then apply any txt overrides.
    """
    global PAGES
    # Start from defaults (shallow copy is fine since we replace 'lines' wholesale).
    PAGES = {}
    for pid, meta in _DEFAULT_PAGES.items():
        PAGES[pid] = {
            "id": meta["id"],
            "lines": list(meta["lines"]),
        }

    # Try to override each known page from filesystem.
    for pid in list(PAGES.keys()):
        lines = _load_page_from_file(pid)
        if lines is not None:
            PAGES[pid]["lines"] = lines


# Initialize immediately on import
_init_pages()

# ---------- Core template engine --------------------------------------------

def _expand_line(tmpl: str, ctx: dict, width=None) -> str:
    """
    Replace {NAME} tokens with ctx["NAME"] (or "?") and
    clamp to exactly `width` characters (defaults to config.LCD_COLS).
    """
    if width is None:
        # Fallback to 16 if LCD_COLS is missing for some reason
        width = getattr(config, "LCD_COLS", 16)

    out = []
    i = 0
    L = len(tmpl or "")

    while i < L and len(out) < width:
        ch = tmpl[i]
        if ch == "{":
            end = tmpl.find("}", i + 1)
            if end == -1:
                # No closing brace; treat as literal
                out.append("{")
                i += 1
            else:
                key = tmpl[i + 1 : end]
                val = ctx.get(key, "?")
                s = str(val)
                for c in s:
                    if len(out) >= width:
                        break
                    out.append(c)
                i = end + 1
        else:
            out.append(ch)
            i += 1

    # Pad with spaces if needed
    while len(out) < width:
        out.append(" ")

    return "".join(out[:width])


def build_context(
    temp_c: float,
    pressure_kg: float,
    ssr_on: bool,
    act_state: str = "",
    step_idx: int = 0,
    step_count: int = 0,
    message: str = "",
    program_name: str = "",
    debug_hint: str = "",
) -> dict:
    """
    Build a context dict for templates from basic primitives.
    Later, autoclave_brain will call this with a richer state object.
    """
    temp_txt = units.format_temp(temp_c if temp_c is not None else float("nan"))
    press_txt = units.format_press(
        pressure_kg if pressure_kg is not None else float("nan")
    )

    ctx = {
        "TEMP": temp_txt,                         # numeric part
        "TUNIT": units.temp_unit_str(),
        "PRESS": press_txt,
        "PUNIT": units.press_unit_str(),
        "SSR": "ON" if ssr_on else "OFF",
        "ACT": act_state or "--",
        "STEP_IDX": step_idx if step_idx else 0,
        "STEP_COUNT": step_count if step_count else 0,
        "MESSAGE": message or "",
        "UNITS_NAME": units.units_name(),
        "PROGRAM_NAME": program_name or "-",
        "APP_MAX_TEMP": "{:.1f}".format(config.APP_MAX_TEMP_C),
        "APP_MAX_PRESS": "{:.2f}".format(config.APP_MAX_PRESSURE_KGCM2),
        "DEBUG_HINT": debug_hint or "",
        # Add more over time (PID_OUT, SETPOINT, etc.)
    }

    return ctx


def render_page(
    page_id: str,
    temp_c: float,
    pressure_kg: float,
    ssr_on: bool,
    act_state: str = "",
    step_idx: int = 0,
    step_count: int = 0,
    message: str = "",
    program_name: str = "",
    debug_hint: str = "",
) -> dict:
    """
    Expand a page into a 4-line dict suitable for lcd16x4.render().

    NOTE: We now reload the txt template on every call if it exists.
    This lets you tweak ui_templates/<page_id>.txt without rebooting.
    """
    # Start from built-in default
    meta = _DEFAULT_PAGES.get(page_id)
    if meta is None:
        cols = getattr(config, "LCD_COLS", 16)
        line1 = "UNKNOWN PAGE".ljust(cols)[:cols]
        line2 = ("id=" + page_id).ljust(cols)[:cols]
        blank = " " * cols
        return {
            "line1": line1,
            "line2": line2,
            "line3": blank,
            "line4": blank,
        }


    # Try to override from filesystem each time
    file_lines = _load_page_from_file(page_id)
    if file_lines is not None:
        lines = file_lines
    else:
        lines = meta["lines"]

    ctx = build_context(
        temp_c=temp_c,
        pressure_kg=pressure_kg,
        ssr_on=ssr_on,
        act_state=act_state,
        step_idx=step_idx,
        step_count=step_count,
        message=message,
        program_name=program_name,
        debug_hint=debug_hint,
    )

    cols = getattr(config, "LCD_COLS", 16)
    blank = " " * cols

    # Ensure exactly 4 entries
    l1 = _expand_line(lines[0], ctx, cols) if len(lines) > 0 else blank
    l2 = _expand_line(lines[1], ctx, cols) if len(lines) > 1 else blank
    l3 = _expand_line(lines[2], ctx, cols) if len(lines) > 2 else blank
    l4 = _expand_line(lines[3], ctx, cols) if len(lines) > 3 else blank

    return {
        "line1": l1,
        "line2": l2,
        "line3": l3,
        "line4": l4,
    }


