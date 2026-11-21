import math
from datetime import date

import numpy as np

SIGMA = 4.903e-9
ALBEDO = 0.23


def sat_vp(t: np.ndarray | float) -> np.ndarray | float:
    return 0.6108 * np.exp(17.27 * t / (t + 237.3))


def wind_10_to_2(u10: np.ndarray | float) -> np.ndarray | float:
    return u10 * 4.87 / math.log(67.8 * 10 - 5.42)


def pressure_from_elevation(z: float) -> float:
    return 101.3 * ((293 - 0.0065 * z) / 293) ** 5.26


def elevation_from_pressure(p_kpa: np.ndarray | float) -> np.ndarray | float:
    return (293 - 293 * (np.asarray(p_kpa) / 101.3) ** (1 / 5.26)) / 0.0065


def extraterrestrial_radiation(lat_deg: float, doy: np.ndarray | int) -> np.ndarray | float:
    phi = math.radians(lat_deg)
    j = np.asarray(doy, dtype=float)
    dr = 1 + 0.033 * np.cos(2 * math.pi * j / 365)
    delta = 0.409 * np.sin(2 * math.pi * j / 365 - 1.39)
    ws = np.arccos(np.clip(-math.tan(phi) * np.tan(delta), -1.0, 1.0))
    return (
        (24 * 60 / math.pi)
        * 0.0820
        * dr
        * (ws * math.sin(phi) * np.sin(delta) + math.cos(phi) * np.cos(delta) * np.sin(ws))
    )


def et0_pm(
    tmax: np.ndarray | float,
    tmin: np.ndarray | float,
    rs: np.ndarray | float,
    u2: np.ndarray | float,
    lat_deg: float,
    doy: np.ndarray | int,
    pressure_kpa: np.ndarray | float | None = None,
    elevation_m: float | None = None,
    tdew: np.ndarray | float | None = None,
    ea: np.ndarray | float | None = None,
) -> np.ndarray | float:
    tmax = np.asarray(tmax, dtype=float)
    tmin = np.asarray(tmin, dtype=float)
    t = (tmax + tmin) / 2
    if pressure_kpa is None:
        pressure_kpa = pressure_from_elevation(elevation_m or 0.0)
    p = np.asarray(pressure_kpa, dtype=float)
    z = elevation_m if elevation_m is not None else elevation_from_pressure(p)
    gamma = 0.000665 * p
    delta = 4098 * sat_vp(t) / (t + 237.3) ** 2
    es = (sat_vp(tmax) + sat_vp(tmin)) / 2
    if ea is None:
        ea = sat_vp(np.asarray(tdew, dtype=float)) if tdew is not None else sat_vp(tmin)
    ea = np.minimum(np.asarray(ea, dtype=float), es)
    ra = extraterrestrial_radiation(lat_deg, doy)
    rso = (0.75 + 2e-5 * np.asarray(z)) * ra
    rs = np.asarray(rs, dtype=float)
    ratio = np.clip(np.where(rso > 0, rs / np.where(rso > 0, rso, 1), 0.5), 0.25, 1.0)
    rns = (1 - ALBEDO) * rs
    rnl = (
        SIGMA
        * (((tmax + 273.16) ** 4 + (tmin + 273.16) ** 4) / 2)
        * (0.34 - 0.14 * np.sqrt(ea))
        * (1.35 * ratio - 0.35)
    )
    rn = rns - rnl
    u2 = np.asarray(u2, dtype=float)
    num = 0.408 * delta * rn + gamma * (900 / (t + 273)) * u2 * (es - ea)
    den = delta + gamma * (1 + 0.34 * u2)
    return np.maximum(num / den, 0.0)


def et0_for_days(
    days: list[date],
    tmax: np.ndarray,
    tmin: np.ndarray,
    rs: np.ndarray,
    wind10: np.ndarray,
    tdew: np.ndarray,
    pressure_kpa: np.ndarray,
    lat_deg: float,
) -> np.ndarray:
    doy = np.array([d.timetuple().tm_yday for d in days])
    pressure = np.where(np.isnan(pressure_kpa), 100.0, pressure_kpa)
    wind = np.where(np.isnan(wind10), 3.0, wind10)
    tdew = np.where(np.isnan(tdew), tmin - 2.0, tdew)
    return et0_pm(tmax, tmin, rs, wind_10_to_2(wind), lat_deg, doy, pressure_kpa=pressure, tdew=tdew)
