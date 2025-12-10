# lib/config.py
"""
Global config: pins, units, safety limits, timing.

This is the MicroPython spiritual twin of app_pins.h (+ some Kconfig bits).
We keep it simple in Phase 0 and expand as we port more of the C project.
"""

# ===== Units =====
UNITS_METRIC = 0   # kg/cm², °C
UNITS_USCS   = 1   # psi, °F

# Match your C default (APP_DEFAULT_UNITS)
DEFAULT_UNITS = UNITS_USCS  # change to UNITS_METRIC if you like

# ===== Safety ceilings (copied from app_pins.h) =====
APP_MAX_PRESSURE_KGCM2: float = 1.41   # ~20 psi
APP_MAX_TEMP_C: float = 125.0          # hard ceiling for control logic (pre-PID)

# ===== GPIO assignments (from app_pins.h) =====
# Outputs
PIN_SSR: int       = 13
PIN_MOTOR_FWD: int = 25
PIN_MOTOR_REV: int = 26
PIN_ALARM: int     = 17

# Output polarity (active-high in your C build)
SSR_ACTIVE_HIGH: bool   = True
ALARM_ACTIVE_HIGH: bool = True

# Buttons
PIN_BTN1: int = 14
PIN_BTN2: int = 33

# ===== Pressure sensor (ADC1 on GPIO32) =====
# Mirror your C calibration:
#   APP_PRESSURE_ADC_CH     -> GPIO32
#   APP_PRESSURE_V_PIN_MIN  -> 0.334f
#   APP_PRESSURE_V_PIN_MAX  -> 2.997f
#   APP_PRESSURE_P_MIN_KGCM2 -> 0.0f
#   APP_PRESSURE_P_MAX_KGCM2 -> 2.10f
PIN_PRESSURE_ADC: int = 32  # GPIO32 on ESP32

PRESSURE_V_PIN_MIN: float = 0.334   # V at 0 kg/cm²
PRESSURE_V_PIN_MAX: float = 2.997   # V at full-scale

PRESSURE_P_MIN_KGCM2: float = 0.0
PRESSURE_P_MAX_KGCM2: float = 2.10  # ~30 psi full-scale, safety ceiling is lower

# ===== Thermocouple (MAX31855 over SPI) =====
PIN_SPI_SCLK: int = 18
PIN_SPI_MISO: int = 19
PIN_SPI_MOSI: int = 23
PIN_TC_CS: int    = 27  # thermocouple CS

# ===== I2C (for future LCD, etc.) =====
PIN_I2C_SDA: int = 21
PIN_I2C_SCL: int = 22
I2C_FREQ_HZ: int = 400_000  # 400 kHz

# ===== Feature flags =====
# Global heater enable for development.
# - False: SSR is always forced OFF by brain (safe default).
# - True:  SSR follows conservative allow_heat window.
HEAT_ENABLE: bool = False

# ===== LCD configuration =====
# 16x4 HD44780 over I2C PCF8574 backpack
LCD_ENABLE: bool = True

# I2C backpack address (you saw 0x27 in your scan)
LCD_I2C_ADDR: int = 0x27

# Geometry
LCD_COLS: int = 20
LCD_ROWS: int = 4

# Backlight control (the driver always keeps it on for now)
LCD_BACKLIGHT: bool = True
