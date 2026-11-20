"""Integer arithmetic helpers matching the firmware."""

from __future__ import annotations


def trunc_div(numerator: int, denominator: int) -> int:
    """Integer division that truncates toward zero, like C.

    Python's ``//`` floors, so ``-45 // 100`` is ``-1`` while C gives
    ``0`` and ``-150 // 100`` is ``-2`` while C gives ``-1``. The firmware
    is written in C, so reproducing its wheel and PWM values bit for bit
    requires this instead of ``//``.
    """
    if denominator == 0:
        raise ZeroDivisionError("trunc_div: denominator is zero")
    quotient = abs(numerator) // abs(denominator)
    if (numerator < 0) != (denominator < 0):
        return -quotient
    return quotient


def clamp(value: int, low: int, high: int) -> int:
    """Clamp an integer into the inclusive range [low, high]."""
    return low if value < low else high if value > high else value
