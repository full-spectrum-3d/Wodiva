import pytest

from app.water.engine.et0 import et0_pm, extraterrestrial_radiation, pressure_from_elevation, wind_10_to_2


def test_fao56_example_18_brussels():
    et0 = et0_pm(
        tmax=21.5,
        tmin=12.3,
        rs=22.07,
        u2=2.078,
        lat_deg=50.8,
        doy=187,
        elevation_m=100,
        ea=1.409,
    )
    assert float(et0) == pytest.approx(3.9, abs=0.1)


def test_extraterrestrial_radiation_example_8():
    assert float(extraterrestrial_radiation(-20.0, 246)) == pytest.approx(32.2, abs=0.2)


def test_wind_conversion_example_14():
    assert wind_10_to_2(3.2) == pytest.approx(2.4, abs=0.05)


def test_pressure_example_2():
    assert pressure_from_elevation(1800) == pytest.approx(81.8, abs=0.1)


def test_et0_never_negative():
    assert float(et0_pm(-5, -12, 1.0, 1.0, 52.0, 10, elevation_m=100, tdew=-6)) >= 0
