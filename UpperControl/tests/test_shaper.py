import math

import pytest

from mecanum.core.shaper import (
    FLOOR_WHEEL,
    Ema1,
    ShapeConfig,
    Shaper,
    ema_alpha,
    floor_map,
    round_half_away,
)
from mecanum.core.vector import DriveVector


class TestFloorWheel:
    def test_derived_from_firmware_constants(self):
        # ceil(60 * 100 / 399) == 16, the first wheel value the firmware
        # does not raise to PWM_MIN_RUN.
        assert FLOOR_WHEEL == 16

    def test_floor_currently_produces_min_run(self):
        # At 60 % limit and full stick the command must stay under 100.
        assert floor_map(1.0, 0.60) <= 100.0


class TestFloorMap:
    def test_zero_maps_to_zero(self):
        # A centred stick must command a true stop, otherwise the chassis
        # creeps whenever the UI is open.
        assert floor_map(0.0, 1.0) == 0.0

    def test_just_above_zero_starts_at_floor(self):
        # The first nonzero command lands on the floor, skipping the 1..15
        # range that the firmware collapses to a single speed.
        assert round(floor_map(0.001, 1.0)) == FLOOR_WHEEL
        assert round(floor_map(0.001, 0.60)) == FLOOR_WHEEL

    def test_full_stick_reaches_limit(self):
        assert floor_map(1.0, 0.60) == pytest.approx(60.0)
        assert floor_map(1.0, 1.0) == pytest.approx(100.0)

    def test_monotonic(self):
        previous = -1.0
        for i in range(0, 101):
            value = floor_map(i / 100, 0.8)
            assert value >= previous
            previous = value

    def test_limit_below_floor_pins_to_floor(self):
        # The hardware cannot go slower than the floor, so a smaller limit
        # would be raised to the same PWM anyway.
        assert floor_map(0.5, 0.05) == pytest.approx(FLOOR_WHEEL)


class TestEmaAlpha:
    def test_zero_tau_is_transparent(self):
        assert ema_alpha(0.016, 0.0) == 1.0

    def test_alpha_increases_with_dt(self):
        assert ema_alpha(0.010, 0.06) < ema_alpha(0.050, 0.06)

    def test_sixty_hz_matches_expectation(self):
        # 60 Hz, tau 60 ms gives roughly 0.24, which is responsive but
        # still filters mouse jitter.
        assert ema_alpha(1 / 60, 0.06) == pytest.approx(0.243, abs=0.005)


class TestEma1:
    def test_seeds_on_first_update(self):
        axis = Ema1()
        assert axis.update(50.0, 0.3) == 50.0

    def test_moves_toward_target(self):
        axis = Ema1()
        axis.update(0.0, 0.3)
        value = axis.update(100.0, 0.5)
        assert 0.0 < value < 100.0

    def test_never_overshoots(self):
        axis = Ema1()
        axis.update(0.0, 0.5)
        for _ in range(200):
            value = axis.update(100.0, 0.5)
        assert value == pytest.approx(100.0, abs=0.01)

    def test_reset_clears(self):
        axis = Ema1()
        axis.update(80.0, 1.0)
        axis.reset()
        assert axis.value == 0.0


class TestRoundHalfAway:
    def test_halves_round_away_from_zero(self):
        assert round_half_away(0.5) == 1
        assert round_half_away(1.5) == 2
        assert round_half_away(-0.5) == -1
        assert round_half_away(-1.5) == -2

    def test_matches_int_for_whole_numbers(self):
        for value in (-3, 0, 7):
            assert round_half_away(float(value)) == value


class TestShaperTarget:
    def test_zero_input_gives_stop(self):
        shaper = Shaper()
        assert shaper.target(0.0, 0.0, 0.0).is_zero

    def test_pure_forward(self):
        shaper = Shaper(ShapeConfig(speed_limit=0.60))
        vector = shaper.target(1.0, 0.0, 0.0)
        assert vector.forward == pytest.approx(60, abs=1)
        assert vector.right == 0
        assert vector.ccw == 0

    def test_pure_right(self):
        shaper = Shaper(ShapeConfig(speed_limit=0.60))
        vector = shaper.target(0.0, 1.0, 0.0)
        assert vector.right == pytest.approx(60, abs=1)
        assert vector.forward == 0

    def test_rotation_uses_its_own_limit(self):
        shaper = Shaper(ShapeConfig(rotation_limit=0.40))
        vector = shaper.target(0.0, 0.0, 1.0)
        assert vector.ccw == pytest.approx(40, abs=1)

    def test_counter_clockwise_is_positive(self):
        shaper = Shaper()
        assert shaper.target(0.0, 0.0, 1.0).ccw > 0
        assert shaper.target(0.0, 0.0, -1.0).ccw < 0

    def test_small_stick_still_above_floor(self):
        # Anything outside the deadzone must produce motion, because the
        # firmware cannot run slower than PWM_MIN_RUN anyway.
        shaper = Shaper()
        vector = shaper.target(0.02, 0.0, 0.0)
        assert abs(vector.forward) >= FLOOR_WHEEL

    def test_magnitude_preserved_by_unit_circle(self):
        # A diagonal input conditioned to the unit circle must give the
        # same total command magnitude as a straight push.
        shaper = Shaper()
        straight = shaper.target(1.0, 0.0, 0.0)
        diagonal = shaper.target(math.sqrt(0.5), math.sqrt(0.5), 0.0)
        assert straight.translation_magnitude == pytest.approx(
            diagonal.translation_magnitude, rel=0.05
        )


class TestShaperSmooth:
    def test_first_smooth_matches_target(self):
        shaper = Shaper()
        vector = shaper.smooth(DriveVector(60, 0, 0), 1 / 60)
        assert vector.forward == 60

    def test_approaches_target_over_time(self):
        shaper = Shaper(ShapeConfig(filter_tau=0.06))
        target = DriveVector(100, 0, 0)
        shaper.smooth(target, 1 / 60)
        previous = 0
        for _ in range(60):
            value = shaper.smooth(target, 1 / 60).forward
            assert value >= previous
            previous = value
        assert previous == pytest.approx(100, abs=1)

    def test_reset_returns_to_zero(self):
        shaper = Shaper()
        shaper.smooth(DriveVector(80, 0, 0), 1 / 60)
        shaper.reset()
        vector = shaper.smooth(DriveVector(0, 0, 0), 1 / 60)
        assert vector.is_zero


class TestShapeConfigClamp:
    def test_out_of_range_is_clamped(self):
        config = ShapeConfig(deadzone=2.0, speed_limit=5.0, rotation_limit=-1.0).clamped()
        assert config.deadzone == 0.5
        assert config.speed_limit == 1.0
        assert config.rotation_limit == 0.0
