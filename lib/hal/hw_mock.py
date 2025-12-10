# lib/hal/hw_mock.py
"""
Mock HAL for desktop / unit tests.

Currently unused, but here as a placeholder so imports don't break
if we decide to swap HAL implementations later.
"""

import time


def ticks_ms() -> int:
    return int(time.time() * 1000)


def sleep_ms(ms: int) -> None:
    time.sleep(ms / 1000.0)
