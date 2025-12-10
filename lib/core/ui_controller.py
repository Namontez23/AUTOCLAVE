# lib/core/ui_controller.py
"""
UI controller: tracks which LCD page is active and responds to button events.

Responsibilities:
- Remember which page is currently selected (status / limits / debug).
- Own the current units mode via core.units.
- Provide a helper to build the current page dict for lcd16x4.render().
"""

from . import ui_pages, units
import config

# Order of pages when cycling with BTN1
_PAGES = ["status", "limits", "debug"]
_page_idx = 0


def init() -> None:
    """
    Initialize UI controller state:
    - Reset to first page.
    - Ensure units follow config.DEFAULT_UNITS.
    """
    global _page_idx
    _page_idx = 0
    units.set_units(config.DEFAULT_UNITS)


def current_page_id() -> str:
    """Return the current page ID (e.g. 'status')."""
    return _PAGES[_page_idx]


def next_page() -> None:
    """Advance to the next page in the list (wrap around)."""
    global _page_idx
    _page_idx = (_page_idx + 1) % len(_PAGES)


def toggle_units() -> None:
    """Toggle units between METRIC and USCS."""
    cur = units.get_units()
    if cur == units.UNITS_METRIC:
        units.set_units(units.UNITS_USCS)
    else:
        units.set_units(units.UNITS_METRIC)


def make_page(
    temp_c: float,
    pressure_kg: float,
    ssr_on: bool,
    act_state: str = "IDLE",
    step_idx: int = 0,
    step_count: int = 0,
    message: str = "",
    program_name: str = "NONE",
    debug_hint: str = "",
) -> dict:
    """
    Build a 4-line dict for whichever page is currently active.
    """
    return ui_pages.render_page(
        page_id=current_page_id(),
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
