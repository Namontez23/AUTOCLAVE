# test_ssr_gpio.py
"""
Manual SSR sanity test.

Run this on the ESP32 when:
- You have something safe on the SSR output (LED, relay coil, etc.)
- Or the pressure cooker is unplugged.

It will blink SSR ON/OFF a few times, then leave it OFF.
"""

# --- sys.path bootstrap identical to main.py so we can reuse the same layout ---
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
# ---------------------------------------------------------------------------

from drivers import control
from hal import hw_esp32


def main() -> None:
    control.init()
    print("SSR test: blinking 5 times. Ensure load is safe or disconnected.")

    for i in range(5):
        print(f"Cycle {i+1}: ON")
        control.set_ssr(True)
        hw_esp32.sleep_ms(500)

        print(f"Cycle {i+1}: OFF")
        control.set_ssr(False)
        hw_esp32.sleep_ms(500)

    print("SSR test complete. Forcing OFF.")
    control.set_ssr(False)


if __name__ == "__main__":
    main()
