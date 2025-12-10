# main.py
"""
Main control loop.

Phase 1.x:
- Initialize drivers (control, sensors, LCD).
- Initialize UI controller + buttons.
- Loop:
    * poll buttons -> ui_controller reacts (page cycle, units toggle, actuator jog)
    * brain.step_once()      -> decide SSR (still locked OFF by default)
    * actuator.step()        -> manage timed motor jogs
    * read sensors           -> real MAX31855 + pressure ADC on ESP32
    * build UI page          -> core.ui_controller + core.ui_pages
    * render via lcd16x4     -> console or real LCD

Also exposes:
- main_n_steps(n): same pipeline but runs for N iterations and returns.
  Handy with mpremote so you don't fight an infinite loop.
"""

# --- sys.path bootstrap so CPython and MicroPython can see ./lib ---
import sys


try:
    # __file__ should exist on both CPython and MicroPython when running from a file
    _HERE = __file__
except NameError:
    # Fallback if __file__ is missing (e.g. interactive)
    _HERE = ""

if "/" in _HERE:
    _BASE_DIR = _HERE.rpartition("/")[0] or "."
else:
    _BASE_DIR = "."

_LIB_DIR = _BASE_DIR + "/lib"
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
# ---------------------------------------------------------------------------

import config
from drivers import control, sensors, lcd16x4, buttons
from core import brain, ui_model, units, ui_controller, actuator
from hal import hw_esp32


# Main loop period in milliseconds.
# 100 ms (10 Hz) is a good compromise:
# - Responsive button handling
# - Light load for sensors + LCD.
LOOP_PERIOD_MS = 100


def _print_start_banner(context: str) -> None:
    """
    Small helper so main() and main_n_steps() both print the same startup info.
    """
    env = "ESP32" if hw_esp32.on_real_hw() else "desktop"
    print(
        "PCOOK Phase1 ({}): env={}, HEAT_ENABLE={}, SSR locked {}".format(
            context,
            env,
            config.HEAT_ENABLE,
            "OFF" if not config.HEAT_ENABLE else "windowed",
        )
    )


def _one_step() -> None:
    """
    One iteration of the control + UI pipeline.
    Shared by main() and main_n_steps().
    """
    # 1) Poll buttons first so UI state is up-to-date.
    buttons.poll()

    # 2) Let the brain update SSR based on readings (pre-PID, conservative).
    brain.step_once()

    # 3) Update actuator state machine (timed jogs).
    actuator.step()

    # 4) Get readings for UI
    t_c = sensors.read_tc_c()
    p_kg = sensors.read_pressure_kgcm2()
    ssr = brain.get_ssr_state()
    allow_heat = brain.get_allow_heat()
    act_state = actuator.get_ui_state()

    # 5) Build current page (status / limits / debug) via ui_controller.
    #    Use DEBUG_HINT field so the debug page can show safety info.
    debug_hint = "HEAT_EN={} ALLOW={}".format(
        1 if config.HEAT_ENABLE else 0,
        1 if allow_heat else 0,
    )

    status = ui_controller.make_page(
        temp_c=t_c,
        pressure_kg=p_kg,
        ssr_on=ssr,
        act_state=act_state,
        debug_hint=debug_hint,
    )

    # 6) Render (console or real LCD).
    lcd16x4.render(status)

    # 7) Basic pacing
    hw_esp32.sleep_ms(LOOP_PERIOD_MS)


def main() -> None:
    """
    Infinite run loop (what will eventually be your “real” firmware behavior).

    On ESP32:
      - Uses real sensors via hw_esp32.
      - SSR is hard-locked OFF as long as config.HEAT_ENABLE == False.
      - Buttons drive page cycling, unit toggling, and actuator jogs.
    """
    # Basic init
    control.init()
    sensors.init()
    lcd16x4.init()
    ui_controller.init()
    actuator.init()
    buttons.init(on_button_event)

    _print_start_banner("main")

    while True:
        _one_step()


def main_n_steps(n: int = 20) -> None:
    """
    Development helper:
    - Same pipeline as main(), but runs for N iterations and returns.
    - Great with mpremote + mount so you can run a short test and get
      your shell back without Ctrl-C gymnastics.

    Example from host:

      mpremote connect /dev/ttyUSB0 mount . \
        exec "import sys; sys.modules.pop('main', None); sys.path.insert(0, '/remote'); import main; main.main_n_steps(10)"
    """
    control.init()
    sensors.init()
    lcd16x4.init()
    ui_controller.init()
    actuator.init()
    buttons.init(on_button_event)

    _print_start_banner("main_n_steps")

    for _ in range(n):
        _one_step()


def on_button_event(evt: str) -> None:
    """
    Handle button events mapped from drivers.buttons.

    BTN1_SHORT -> cycle page (status -> limits -> debug -> ...)
    BTN2_SHORT -> toggle units (METRIC <-> USCS)

    BTN1_LONG  -> actuator jog forward
    BTN2_LONG  -> actuator jog reverse
    """
    print("Button event:", evt)

    if evt == "BTN1_SHORT":
        ui_controller.next_page()
    elif evt == "BTN2_SHORT":
        ui_controller.toggle_units()
    elif evt == "BTN1_LONG":
        actuator.jog_fwd()
    elif evt == "BTN2_LONG":
        actuator.jog_rev()
    # Future:
    # elif evt == "BTN1_LONG":
    #     ...
    # elif evt == "BTN2_LONG":
    #     ...
    # etc.


# MicroPython / CPython entry point when run as a script
if __name__ == "__main__":
    main()
