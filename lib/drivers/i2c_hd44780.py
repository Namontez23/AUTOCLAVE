# lib/drivers/i2c_hd44780.py
"""
Minimal HD44780 16x4 LCD driver over I2C backpack (PCF8574-style).

Assumptions (common backpack mapping):
- PCF8574 P0: RS
- P1: RW
- P2: EN
- P3: Backlight
- P4..P7: D4..D7 (high nibble)

We use 4-bit mode and hardware I2C only (no bit banging), and keep a
simple "print line" API for callers.
"""

from hal import hw_esp32
import config

try:
    from machine import I2C, Pin  # type: ignore[import-not-found]
except ImportError:  # Shouldn't happen on ESP32
    I2C = None  # type: ignore[assignment]
    Pin = None  # type: ignore[assignment]


class I2cLcd:
    # Control bit masks on the PCF8574
    _MASK_RS = 0x01
    _MASK_RW = 0x02
    _MASK_EN = 0x04
    _MASK_BL = 0x08

    # DDRAM base addresses for your 16x4 (20x4-style) layout:
    #   row 0 -> 0x00
    #   row 1 -> 0x40
    #   row 2 -> 0x14
    #   row 3 -> 0x54
    # This avoids the 4-char bleed you’re seeing at the end of lines 1 and 2.
    _LINE_ADDR = [0x00, 0x40, 0x14, 0x54]


    def __init__(
        self,
        i2c_id: int,
        addr: int,
        cols: int = 16,
        rows: int = 4,
        backlight: bool = True,
    ) -> None:
        if not hw_esp32.on_real_hw():
            raise RuntimeError("I2cLcd requires real ESP32 hardware")

        if I2C is None or Pin is None:
            raise RuntimeError("machine.I2C or machine.Pin not available")

        self._cols = cols
        self._rows = rows
        self._addr = addr
        self._backlight = bool(backlight)

        # Create I2C bus
        self._i2c = I2C(
            i2c_id,
            scl=Pin(config.PIN_I2C_SCL),
            sda=Pin(config.PIN_I2C_SDA),
            freq=config.I2C_FREQ_HZ,
        )

        # Basic init sequence for HD44780 in 4-bit mode
        self._init_lcd()

    # --- Low-level helpers ---------------------------------------------------

    def _backlight_mask(self) -> int:
        return self._MASK_BL if self._backlight else 0

    def _write_byte(self, data: int) -> None:
        self._i2c.writeto(self._addr, bytes([data & 0xFF]))

    def _pulse_enable(self, data: int) -> None:
        # EN high then low with small delays
        self._write_byte(data | self._MASK_EN)
        hw_esp32.sleep_ms(1)
        self._write_byte(data & ~self._MASK_EN)
        hw_esp32.sleep_ms(1)

    def _send_nibble(self, nibble: int, rs: bool) -> None:
        """
        Send a high-4 bits nibble; RS selects data/command.
        nibble is assumed to already be in bits 4..7.
        """
        base = nibble & 0xF0
        if rs:
            base |= self._MASK_RS
        base |= self._backlight_mask()

        self._pulse_enable(base)

    def _send_byte(self, value: int, rs: bool) -> None:
        """
        Send one 8-bit value as two 4-bit transfers (high nibble first).
        """
        high = value & 0xF0
        low = (value << 4) & 0xF0
        self._send_nibble(high, rs)
        self._send_nibble(low, rs)

    # --- LCD init + commands -------------------------------------------------

    def _init_lcd(self) -> None:
        """
        Initialize the LCD into 4-bit, 2-line/4-line mode.
        """
        hw_esp32.sleep_ms(50)  # Wait for LCD power-up

        # 3 times 0x30 in 8-bit mode (high nibble only) to reset
        for _ in range(3):
            self._send_nibble(0x30, rs=False)
            hw_esp32.sleep_ms(5)

        # Switch to 4-bit mode
        self._send_nibble(0x20, rs=False)
        hw_esp32.sleep_ms(5)

        # Function set: 4-bit, 2-line (works for 16x4), 5x8 font
        self._command(0x28)
        # Display off
        self._command(0x08)
        # Clear
        self.clear()
        # Entry mode: increment, no shift
        self._command(0x06)
        # Display on, cursor off, blink off
        self._command(0x0C)

    def _command(self, cmd: int) -> None:
        self._send_byte(cmd, rs=False)
        if cmd in (0x01, 0x02):  # Clear or home need extra time
            hw_esp32.sleep_ms(2)

    def _write_char(self, ch: int) -> None:
        self._send_byte(ch, rs=True)

    # --- Public API ----------------------------------------------------------

    def clear(self) -> None:
        self._command(0x01)

    def home(self) -> None:
        self._command(0x02)

    def set_cursor(self, col: int, row: int) -> None:
        if row < 0:
            row = 0
        elif row >= self._rows:
            row = self._rows - 1
        if col < 0:
            col = 0
        elif col >= self._cols:
            col = self._cols - 1

        addr = self._LINE_ADDR[row] + col
        self._command(0x80 | addr)

    def write_line(self, row: int, text: str) -> None:
        if row < 0 or row >= self._rows:
            return
        self.set_cursor(0, row)

        txt = "" if text is None else str(text)
        if len(txt) < self._cols:
            txt = txt + (" " * (self._cols - len(txt)))
        else:
            txt = txt[: self._cols]

        for ch in txt:
            self._write_char(ord(ch))


    def set_backlight(self, on: bool) -> None:
        self._backlight = bool(on)
        # Touch bus so state updates
        self._write_byte(self._backlight_mask())
