import pytest

from mecanum.core.vector import DriveVector
from mecanum.core.wheels import (
    FL,
    FR,
    PWM_MAX_VALUE,
    PWM_MIN_RUN,
    RL,
    RR,
    normalise,
    predict,
    pwm_for_wheel,
    wheel_speeds,
)


class TestWheelSpeeds:
    def test_forward(self):
        # All four wheels turn the same way for pure translation.
        assert wheel_speeds(DriveVector(60, 0, 0)) == (60, 60, 60, 60)

    def test_backward(self):
        assert wheel_speeds(DriveVector(-60, 0, 0)) == (-60, -60, -60, -60)

    def test_strafe_left(self):
        # From the README: 左前 - 右前 + 左后 + 右后 -
        assert wheel_speeds(DriveVector(0, -60, 0)) == (-60, 60, 60, -60)

    def test_strafe_right(self):
        assert wheel_speeds(DriveVector(0, 60, 0)) == (60, -60, -60, 60)

    def test_rotate_ccw(self):
        # README: 左转 左前 - 右前 + 左后 - 右后 +
        assert wheel_speeds(DriveVector(0, 0, 60)) == (-60, 60, -60, 60)

    def test_rotate_cw(self):
        assert wheel_speeds(DriveVector(0, 0, -60)) == (60, -60, 60, -60)

    def test_diagonal(self):
        # forward+right: FL and RR add, FR and RL cancel.
        assert wheel_speeds(DriveVector(40, 40, 0)) == (80, 0, 0, 80)

    def test_combined_translation_and_rotation(self):
        wheels = wheel_speeds(DriveVector(0, 100, 50))
        assert wheels == (50, -50, -150, 150)


class TestNormalise:
    def test_within_range_unchanged(self):
        wheels = (60, 60, 60, 60)
        assert normalise(wheels) == wheels

    def test_exactly_at_limit_unchanged(self):
        assert normalise((100, -100, 100, -100)) == (100, -100, 100, -100)

    def test_over_limit_scaled_down(self):
        # The peak becomes 100 and everything scales proportionally.
        assert normalise((150, -150, -150, 150)) == (100, -100, -100, 100)

    def test_matches_firmware_truncation(self):
        # 50 * 100 / 150 == 33 in C integer arithmetic, not 33.33.
        assert normalise((50, -50, -150, 150)) == (33, -33, -100, 100)


class TestPwmForWheel:
    def test_zero_stays_zero(self):
        # The floor only lifts non-zero values; a stop must stay a stop.
        assert pwm_for_wheel(0) == 0

    def test_full_speed(self):
        assert pwm_for_wheel(100) == PWM_MAX_VALUE

    def test_negative_full_speed(self):
        assert pwm_for_wheel(-100) == -PWM_MAX_VALUE

    def test_small_values_lifted_to_min_run(self):
        # 1..15 would otherwise be a dead range on the chassis.
        for wheel in (1, 5, 15):
            assert abs(pwm_for_wheel(wheel)) == PWM_MIN_RUN

    def test_floor_value_not_lifted(self):
        # 16 maps to 63, just above the floor, so it is left alone.
        assert pwm_for_wheel(16) == 63

    def test_trim_scales(self):
        assert pwm_for_wheel(100, trim_percent=105) == PWM_MAX_VALUE
        assert pwm_for_wheel(50, trim_percent=100) == 199
        assert pwm_for_wheel(50, trim_percent=90) == 179


class TestPredict:
    def test_records_wheels_and_pwm(self):
        model = predict(DriveVector(60, 0, 0))
        assert model.wheels == (60, 60, 60, 60)
        assert model.pwm == (239, 239, 239, 239)

    def test_no_normalisation_loss_when_fits(self):
        assert predict(DriveVector(60, 0, 0)).normalisation_loss == 0.0

    def test_reports_normalisation_loss(self):
        # right+ccw saturates two wheels, so translation is scaled down.
        model = predict(DriveVector(0, 100, 50))
        assert model.peak_wheel == 100
        assert model.normalisation_loss > 0.0

    def test_peak_wheel_never_exceeds_limit(self):
        for forward in range(-100, 101, 25):
            for right in range(-100, 101, 25):
                for ccw in range(-100, 101, 25):
                    model = predict(DriveVector(forward, right, ccw))
                    assert model.peak_wheel <= 100

    def test_floor_reachable_but_never_between(self):
        # Any nonzero PWM the model produces is either at least the floor
        # or exactly what the linear scale gives.
        for wheel in range(-100, 101):
            pwm = pwm_for_wheel(wheel)
            if pwm == 0:
                assert wheel == 0
            elif abs(pwm) < PWM_MIN_RUN:
                pytest.fail(f"wheel {wheel} produced sub-floor PWM {pwm}")
