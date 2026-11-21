import argparse
import asyncio
import csv
import statistics
import time
from datetime import date
from pathlib import Path

from app.core.api.analyze import run_analysis
from app.core.http import close_client
from app.core.schemas import AnalyzeRequest
from app.water.parcel import resolve_by_point

POINTS = [
    ("dolnośląskie", 51.05, 16.95),
    ("kujawsko-pomorskie", 52.95, 18.35),
    ("lubelskie", 51.05, 22.85),
    ("lubuskie", 52.05, 15.25),
    ("łódzkie", 51.85, 19.65),
    ("małopolskie", 50.15, 20.25),
    ("mazowieckie", 52.35, 21.55),
    ("opolskie", 50.55, 17.75),
    ("podkarpackie", 50.05, 22.35),
    ("podlaskie", 53.15, 22.85),
    ("pomorskie", 54.05, 18.35),
    ("śląskie", 50.45, 18.95),
    ("świętokrzyskie", 50.65, 20.95),
    ("warmińsko-mazurskie", 53.85, 20.85),
    ("wielkopolskie", 52.25, 17.05),
    ("zachodniopomorskie", 53.45, 15.05),
    ("lubelskie-2", 51.45, 21.95),
    ("wielkopolskie-2", 51.95, 17.95),
    ("mazowieckie-2", 52.95, 20.55),
    ("podlaskie-2", 53.65, 22.15),
]
DATES = [date(2018, 6, 20), date(2019, 6, 10), date(2022, 7, 20), date(2024, 5, 25), date(2017, 7, 5)]
CROPS = ["pszenica_ozima", "kukurydza_ziarno", "rzepak_ozimy", "ziemniak", "burak_cukrowy"]


async def run_one(region: str, lat: float, lon: float, day: date, crop: str) -> dict:
    row = {"region": region, "date": day.isoformat(), "crop": crop}
    started = time.perf_counter()
    try:
        parcel, _ = await resolve_by_point(lat, lon, with_land_use=False)
        report = await run_analysis(AnalyzeRequest(parcel_id=parcel.id, date=day, crop=crop))
        w, s = report.water, report.soil
        row.update(
            parcel_id=parcel.id,
            area_ha=parcel.area_ha,
            seconds=round(time.perf_counter() - started, 1),
            soil_cat=s.iung_category,
            awc_mm=s.awc_mm_100cm,
            kbw_60d=w.climate.kbw_60d_mm,
            kbw_period=w.climate.kbw_period_mm,
            kbw_threshold=w.climate.kbw_threshold_mm,
            kbw_drought=w.climate.kbw_drought,
            available_pct=w.soil_water.available_pct if w.soil_water else None,
            stress_days=w.soil_water.stress_days_season if w.soil_water else None,
            irrigation=report.irrigation.status if report.irrigation else None,
            imgw_station=w.station_check.station_name if w.station_check else None,
            imgw_precip_diff_pct=w.station_check.precip_diff_pct if w.station_check else None,
            error="",
        )
    except Exception as exc:
        row.update(seconds=round(time.perf_counter() - started, 1), error=f"{type(exc).__name__}: {exc}")
    return row


def write_markdown(rows: list[dict], path: Path) -> None:
    ok = [r for r in rows if not r["error"]]
    times = [r["seconds"] for r in ok]
    lines = [
        "# Walidacja – osoba A (meteo, gleba, model wody)",
        "",
        f"Data uruchomienia: {date.today().isoformat()}. Przebiegi: {len(rows)}, udane: {len(ok)}.",
        "",
    ]
    if times:
        lines += [
            f"Czas analizy: mediana {statistics.median(times):.1f} s, maks. {max(times):.1f} s, "
            f"poniżej 30 s: {sum(t < 30 for t in times)}/{len(times)}.",
            "",
        ]
    diffs = [abs(r["imgw_precip_diff_pct"]) for r in ok if r.get("imgw_precip_diff_pct") is not None]
    if diffs:
        lines += [f"Opad model vs IMGW (12 mies.): mediana różnicy {statistics.median(diffs):.0f}%.", ""]
    cols = [
        "region",
        "date",
        "crop",
        "parcel_id",
        "soil_cat",
        "kbw_period",
        "kbw_threshold",
        "kbw_drought",
        "available_pct",
        "stress_days",
        "irrigation",
        "imgw_precip_diff_pct",
        "seconds",
        "error",
    ]
    lines.append("| " + " | ".join(cols) + " |")
    lines.append("|" + "---|" * len(cols))
    for r in rows:
        lines.append("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
    lines += [
        "",
        "Porównanie z IUNG Monitoring Suszy: wpisz ręcznie wynik IUNG (susza tak/nie) dla gminy, uprawy i okresu "
        "w kolumnie `iung` pliku CSV i uruchom ponownie z `--compare`.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def compare_with_iung(csv_path: Path) -> str:
    with csv_path.open(encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r.get("iung") in ("tak", "nie") and r.get("kbw_drought")]
    if not rows:
        return "Brak wierszy z wynikiem IUNG."
    hits = sum((r["kbw_drought"] == "True") == (r["iung"] == "tak") for r in rows)
    return f"Zgodność z IUNG: {hits}/{len(rows)} ({100 * hits / len(rows):.0f}%)."


async def main(out_dir: Path, limit: int | None) -> None:
    jobs = [(reg, lat, lon, DATES[i % len(DATES)], CROPS[i % len(CROPS)]) for i, (reg, lat, lon) in enumerate(POINTS)]
    jobs += [(reg, lat, lon, date.today(), CROPS[i % len(CROPS)]) for i, (reg, lat, lon) in enumerate(POINTS[:5])]
    rows = []
    for job in jobs[:limit]:
        row = await run_one(*job)
        print(row)
        rows.append(row)
    await close_client()
    out_dir.mkdir(parents=True, exist_ok=True)
    keys = sorted({k for r in rows for k in r} | {"iung"})
    with (out_dir / "validation.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)
    write_markdown(rows, out_dir / "validation.md")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Walidacja 20 działek × daty")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[2] / "docs")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--compare", type=Path, help="CSV z uzupełnioną kolumną iung")
    args = parser.parse_args()
    if args.compare:
        print(compare_with_iung(args.compare))
    else:
        asyncio.run(main(args.out, args.limit))
