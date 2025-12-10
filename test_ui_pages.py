# test_ui_pages.py
"""
UI pages demo:

- Uses real sensors + lcd16x4.
- Renders the "status" page using ui_pages.
"""

import sys

try:
    _HERE = __file__
except NameError:
    _HERE = ""
if "/" in _HERE:
    _BASE_DIR = _HERE.rpartition("/")[0] or "."
else:
    _BASE_DIR = "."
_LIB_DIR = _BASE_DIR + "/lib"
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

import config
from drivers import control, sensors, lcd16x4
from core import ui_pages, units
from hal import hw_esp32


def main(iterations: int = 20) -> None:
    control.init()
    sensors.init()
    lcd16x4.init()

    # Ensure units follow config default
    units.set_units(config.DEFAULT_UNITS)

    env = "ESP32" if hw_esp32.on_real_hw() else "desktop"
    print("UI pages demo (env={}):".format(env))

    for i in range(iterations):
        t_c = sensors.read_tc_c()
        p_kg = sensors.read_pressure_kgcm2()
        ssr_on = False  # Phase 0: heater disabled anyway

        status = ui_pages.render_page(
            "status",
            temp_c=t_c,
            pressure_kg=p_kg,
            ssr_on=ssr_on,
            act_state="IDLE",
            step_idx=0,
            step_count=0,
            message="DEMO {:02d}".format(i + 1),
            program_name="NONE",
        )
        lcd16x4.render(status)
        hw_esp32.sleep_ms(500)


if __name__ == "__main__":
    main()
