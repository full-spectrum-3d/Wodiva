import numpy as np


def saxton_rawls(sand_pct: float, clay_pct: float, om_pct: float) -> tuple[float, float]:
    s = np.clip(sand_pct, 0, 100) / 100
    c = np.clip(clay_pct, 0, 60) / 100
    om = float(np.clip(om_pct, 0, 8))
    t1500 = -0.024 * s + 0.487 * c + 0.006 * om + 0.005 * s * om - 0.013 * c * om + 0.068 * s * c + 0.031
    wp = t1500 + (0.14 * t1500 - 0.02)
    t33 = -0.251 * s + 0.195 * c + 0.011 * om + 0.006 * s * om - 0.027 * c * om + 0.452 * s * c + 0.299
    fc = t33 + (1.283 * t33**2 - 0.374 * t33 - 0.015)
    wp = float(np.clip(wp, 0.01, 0.45))
    fc = float(np.clip(fc, wp + 0.02, 0.6))
    return fc, wp


def usda_texture(sand: float, silt: float, clay: float) -> str:
    if silt + 1.5 * clay < 15:
        return "piasek"
    if silt + 1.5 * clay < 30 or (silt + 2 * clay < 30 and sand > 70):
        return "piasek gliniasty"
    if clay >= 40:
        return "ił" if silt < 40 and sand <= 45 else "ił pylasty"
    if clay >= 27:
        return "glina ilasta" if sand <= 45 else "glina piaszczysto-ilasta"
    if clay >= 20 and sand > 45:
        return "glina piaszczysto-ilasta"
    if silt >= 80 and clay < 12:
        return "pył"
    if silt >= 50:
        return "glina pylasta"
    if sand > 52 or (clay < 7 and silt < 50):
        return "glina piaszczysta"
    return "glina"


def iung_category_from_texture(sand: float, clay: float) -> str:
    if clay < 5 and sand >= 80:
        return "I"
    if clay < 10 and sand >= 65:
        return "II"
    if clay >= 20:
        return "IV"
    return "III"


IUNG_DEFAULT_LAYERS = {
    "I": (88.0, 3.0, 0.6),
    "II": (72.0, 7.0, 0.9),
    "III": (45.0, 14.0, 1.2),
    "IV": (30.0, 26.0, 1.5),
}
