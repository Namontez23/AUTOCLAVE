# lib/drivers/buttons.py
"""
Button driver: debounced short/long presses + optional hardware binding.

- Button: per-pin debouncer and event detection.
- ButtonManager: polls all buttons and emits events via callback.

High-level helpers:
- init(event_cb)  -> configure buttons for current environment.
- poll()          -> poll all buttons using hal.hw_esp32.ticks_ms().

On ESP32:
- BTN1  -> config.PIN_BTN1 (default GPIO 14)
- BTN2  -> config.PIN_BTN2 (default GPIO 33)
- Inputs are assumed active-low with pull-ups (pressed == 0).
"""


class Button:
    def __init__(self, pin, name: str):
        self.pin = pin
        self.name = name
        self.last_state = pin.value()
        self.last_change_ms = 0
        self.press_start_ms = None
        # Debounce / timing thresholds (ms)
        self.short_ms = 50
        self.long_ms = 800

    def poll(self, now_ms: int, callback):
        state = self.pin.value()
        if state != self.last_state:
            self.last_state = state
            self.last_change_ms = now_ms
            if state == 0:  # pressed (active-low)
                self.press_start_ms = now_ms
            else:           # released
                if self.press_start_ms is not None:
                    dur = now_ms - self.press_start_ms
                    if dur >= self.long_ms:
                        callback(self.name + "_LONG")
                    elif dur >= self.short_ms:
                        callback(self.name + "_SHORT")
                self.press_start_ms = None


class ButtonManager:
    def __init__(self, buttons):
        self.buttons = buttons
        self.event_cb = None

    def set_callback(self, cb):
        self.event_cb = cb

    def poll(self, now_ms: int):
        if not self.event_cb:
            return
        for b in self.buttons:
            b.poll(now_ms, self.event_cb)


# --- High-level helpers ------------------------------------------------------

try:
    from hal import hw_esp32
    import config
    try:
        import machine  # type: ignore[import-not-found]
    except ImportError:
        machine = None  # type: ignore[assignment]
except ImportError:
    hw_esp32 = None  # type: ignore[assignment]
    config = None  # type: ignore[assignment]
    machine = None  # type: ignore[assignment]

_btn_mgr = None  # type: ignore[assignment]


def init(event_cb) -> None:
    """
    Create ButtonManager and, on ESP32, bind to real GPIO pins.

    event_cb(evt: str) will see events like:
      - "BTN1_SHORT", "BTN1_LONG"
      - "BTN2_SHORT", "BTN2_LONG"
    """
    global _btn_mgr

    buttons = []

    if (
        hw_esp32 is not None
        and hw_esp32.on_real_hw()
        and machine is not None
        and config is not None
    ):
        # Real hardware: wire to GPIO with internal pull-ups.
        b1 = Button(
            machine.Pin(config.PIN_BTN1, machine.Pin.IN, machine.Pin.PULL_UP),
            "BTN1",
        )
        b2 = Button(
            machine.Pin(config.PIN_BTN2, machine.Pin.IN, machine.Pin.PULL_UP),
            "BTN2",
        )
        buttons = [b1, b2]
    else:
        # Desktop / no hardware: keep list empty but still create manager.
        buttons = []

    _btn_mgr = ButtonManager(buttons)
    _btn_mgr.set_callback(event_cb)


def poll() -> None:
    """Poll all buttons once, using current ms ticks."""
    if _btn_mgr is None or hw_esp32 is None:
        return

    now = hw_esp32.ticks_ms()
    _btn_mgr.poll(now)
