# lib/drivers/lcd16x4.py
"""
16x4 display driver (high level).

Two modes:
- Console fallback (development): just print lines to stdout.
- Real LCD (ESP32, HD44780 over I2C): use i2c_hd44780.I2cLcd.

Callers just pass a status dict; they don't care about the backend.
"""

_use_lcd: bool = False
_lcd = None  # type: ignore[assignment]


def init() -> None:
    """
    Initialize display.

    Policy:
    - If running on ESP32 hardware AND config.LCD_ENABLE is True AND
      LCD init succeeds → use real LCD.
    - Otherwise → stay in console mode.
    """
    global _use_lcd, _lcd
    _use_lcd = False
    _lcd = None

    try:
        from hal import hw_esp32
        import config
        from .i2c_hd44780 import I2cLcd

        if not hw_esp32.on_real_hw():
            # Desktop / CPython: console mode only
            return

        if not getattr(config, "LCD_ENABLE", False):
            # Explicitly disabled in config
            return

        # Create LCD instance
        _lcd = I2cLcd(
            i2c_id=1,
            addr=config.LCD_I2C_ADDR,
            cols=config.LCD_COLS,
            rows=config.LCD_ROWS,
            backlight=config.LCD_BACKLIGHT,
        )
        _use_lcd = True
        print("lcd16x4: using real I2C LCD at 0x{:02X}".format(config.LCD_I2C_ADDR))

    except Exception as e:
        # Any failure -> stay in console mode, but let you know why.
        print("lcd16x4: LCD init failed, falling back to console:", e)
        _use_lcd = False
        _lcd = None


def render(status: dict) -> None:
    """
    Render a 16x4 status dict:
        { "line1": str, "line2": str, "line3": str, "line4": str }
    """
    line1 = str(status.get("line1", ""))
    line2 = str(status.get("line2", ""))
    line3 = str(status.get("line3", ""))
    line4 = str(status.get("line4", ""))

    if not _use_lcd or _lcd is None:
        # Console fallback; never fails.
        print(line1)
        print(line2)
        if line3 or line4:
            print(line3)
            print(line4)
        print("-" * 32)
        return

    # Real LCD mode
    _lcd.write_line(0, line1)
    _lcd.write_line(1, line2)
    _lcd.write_line(2, line3)
    _lcd.write_line(3, line4)
