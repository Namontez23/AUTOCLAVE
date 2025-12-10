# test_sensors.py
"""
Manual sensor sanity test.

Reads:
- Pressure sensor via ADC (volts + kg/cm²)
- Thermocouple via MAX31855:
    * raw 32-bit word
    * decoded thermocouple °C
    * decoded internal (cold junction) °C
    * fault bits

Runs a finite number of iterations so it doesn't trap mpremote forever.
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

from drivers import sensors
from hal import hw_esp32


# ---- Local MAX31855 debug helpers (mirrors sensors._decode_tc_c_from_raw) ---

def _decode_tc_c_from_raw(raw: int) -> float:
    """
    Thermocouple temperature in °C from MAX31855 raw 32-bit word.
    Bits [31:18] -> signed 14-bit, 0.25°C / LSB.
    Returns NaN on fault.
    """
    import math

    # Fault flag
    fault = (raw & 0x00010000) != 0

    # Thermocouple temperature: bits [31:18]
    tc14 = (raw >> 18) & 0x3FFF
    if tc14 & 0x2000:  # sign bit
        tc14 |= 0xC000  # sign-extend to 16 bits

    if fault:
        return float("nan")

    return tc14 * 0.25


def _decode_tc_internal_c(raw: int) -> float:
    """
    Internal (cold junction) temperature in °C from MAX31855 raw 32-bit word.
    Bits [15:4] -> signed 12-bit, 0.0625°C / LSB.
    """
    # 12-bit signed value in bits [15:4]
    t12 = (raw >> 4) & 0x0FFF
    if t12 & 0x800:  # sign bit
        t12 |= 0xF000  # sign-extend to 16 bits (still fits Python int)

    return t12 * 0.0625


def _decode_fault_bits(raw: int) -> dict:
    """
    Extract fault flags from MAX31855 raw 32-bit word.
    """
    fault = (raw & 0x00010000) != 0
    scv = (raw & 0x00000004) != 0  # short to VCC
    scg = (raw & 0x00000002) != 0  # short to GND
    oc  = (raw & 0x00000001) != 0  # open circuit

    return {
        "fault": fault,
        "scv": scv,
        "scg": scg,
        "oc": oc,
    }


def main() -> None:
    print("Sensor test: initializing...")
    sensors.init()

    if not hw_esp32.on_real_hw():
        print("WARNING: Not running on real ESP32 hardware; "
              "you'll just see dummy values.")
    else:
        print("Running on real ESP32 hardware; reading ADC + MAX31855.")

    for i in range(10):
        print("---- Sample", i + 1, "----")

        # High-level readings (what main.py and brain.py use)
        t_c = sensors.read_tc_c()
        p_kg = sensors.read_pressure_kgcm2()

        print("Temp (°C, sensors.read_tc_c):", t_c)
        print("Pressure (kg/cm²):          ", p_kg)

        if hw_esp32.on_real_hw():
            # Pressure debug
            v = hw_esp32.read_pressure_volts()
            print("Pressure volts:            ", v)

            # Thermocouple debug: raw + decoded
            raw_tc = hw_esp32.read_tc_raw32()
            if raw_tc is None:
                print("TC raw:                     None")
            else:
                tc_dec = _decode_tc_c_from_raw(raw_tc)
                cj_dec = _decode_tc_internal_c(raw_tc)
                faults = _decode_fault_bits(raw_tc)

                print("TC raw:                    0x{:08X}".format(raw_tc))
                print("TC thermocouple °C:        ", tc_dec)
                print("TC internal (CJ) °C:       ", cj_dec)
                print(
                    "Faults: fault={fault} scv={scv} scg={scg} oc={oc}".format(
                        **faults
                    )
                )

        hw_esp32.sleep_ms(500)

    print("Sensor test complete.")


if __name__ == "__main__":
    main()
