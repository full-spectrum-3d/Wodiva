import argparse
import asyncio
import logging
import time
import zipfile
from datetime import date, timedelta
from io import BytesIO

from app.core.http import SourceError, close_client, fetch
from app.water import meteo
from app.water.parcel import resolve_by_id, resolve_by_point
from app.water.sources import era5, imgw, openmeteo, parcels_parquet, soilgrids


async def step(name: str, coro):
    started = time.perf_counter()
    try:
        result = await coro
        print(f"[OK]   {name:<28} {time.perf_counter() - started:5.1f}s  {summary(result)}")
        return result
    except Exception as exc:
        print(f"[BŁĄD] {name:<28} {time.perf_counter() - started:5.1f}s  {type(exc).__name__}: {exc}")
        return None


def summary(result) -> str:
    if hasattr(result, "frame") and hasattr(result, "forecast"):
        f = result.frame
        src = sorted({d.source for d in result.series.days})
        span = f"{len(f)} dni {min(f.index)} – {max(f.index)}"
        return f"{span}, prognoza {len(result.forecast)} dni, źródła ost. 90 dni: {src}"
    if (
        isinstance(result, tuple)
        and len(result) == 2
        and hasattr(result[1], "status")
        and not isinstance(result[0], dict)
    ):
        check, ds = result
        if check is None:
            return f"brak porównania ({ds.note})"
        return (
            f"{check.station_name} {check.distance_km} km, {check.days_compared} dni, opad model "
            f"{check.precip_model_mm} mm vs stacja {check.precip_station_mm} mm ({check.precip_diff_pct}%), "
            f"bias T {check.tmean_bias_c} °C"
        )
    if isinstance(result, tuple) and result and hasattr(result[0], "area_ha"):
        p = result[0]
        uses = ",".join(f"{u.code}{u.soil_class or ''}:{u.share}" for u in p.land_use) or "brak"
        return f"{p.id} {p.area_ha} ha, {p.size_class}, użytki {uses}"
    if hasattr(result, "shape") and result.shape[0] == 0:
        return "pusto (brak danych)"
    if hasattr(result, "shape"):
        return f"{result.shape[0]} dni, {min(result.index)} – {max(result.index)}"
    if isinstance(result, tuple) and result and isinstance(result[0], dict):
        return f"warstwy: {sorted(result[0])}, status {result[1].status}"
    if isinstance(result, dict):
        return str({k: result[k] for k in list(result)[:5]})
    return str(result)[:120]


async def imgw_files(station, start: date, end: date) -> None:
    for path in imgw.archive_files(station, start, end):
        started = time.perf_counter()
        try:
            response = await fetch("imgw", f"{imgw.ARCHIVE}/{path}", retries=0, timeout=15)
            names = zipfile.ZipFile(BytesIO(response.content)).namelist()
            frame = imgw.parse_archive_zip(response.content, station.code)
            took = time.perf_counter() - started
            print(
                f"       {path:<24} {took:4.1f}s {len(response.content) // 1024:>4} KB  "
                f"pliki {names}  wiersze stacji {len(frame)}"
            )
            if len(frame) == 0:
                raw = zipfile.ZipFile(BytesIO(response.content))
                first = next(n for n in raw.namelist() if not n.lower().startswith("s_d_t"))
                print("       pierwszy wiersz:", raw.read(first).decode("cp1250", "replace").splitlines()[0][:160])
        except SourceError as exc:
            print(f"       {path:<24} {time.perf_counter() - started:4.1f}s  {exc}")


async def main(parcel_id: str, lat: float, lon: float) -> None:
    today = date.today()
    await step("ULDK po identyfikatorze", resolve_by_id(parcel_id))
    await step("ULDK po punkcie", resolve_by_point(lat, lon))
    await step("EGiB parquet (zapas)", parcels_parquet.by_id(parcel_id))
    cube = era5.open_cube()
    print(f"[INFO] kostka ERA5: {'jest, do ' + str(era5.cube_end(cube)) if cube is not None else 'brak'}")
    await step("Open-Meteo prognoza", openmeteo.recent_and_forecast(lat, lon))
    month_ago = today - timedelta(days=40)
    await step("Open-Meteo archiwum 30 dni", openmeteo.archive(lat, lon, month_ago, month_ago + timedelta(days=30)))
    station, km = imgw.nearest(lat, lon)
    print(f"[INFO] najbliższa stacja IMGW: {station.name} ({km:.0f} km)")
    await step("IMGW archiwum 2024", imgw.station_daily(station, date(2024, 6, 1), date(2024, 6, 30)))
    print("[INFO] pliki IMGW dla ostatnich 12 miesięcy:")
    await imgw_files(station, today - timedelta(days=365), today)
    await step("IMGW bieżące", imgw.latest_observation(station))
    await step("SoilGrids", soilgrids.query(lat, lon))
    res = await step("Meteo razem (dziś)", meteo.load(lat, lon, today, 10))
    if res is not None:
        await step("Porównanie z IMGW", meteo.station_check(lat, lon, res.frame, today))
    await close_client()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sprawdzenie źródeł danych osoby A na żywo")
    parser.add_argument("--parcel", default="141201_1.0001.6509")
    parser.add_argument("--lat", type=float, default=51.4167)
    parser.add_argument("--lon", type=float, default=21.9667)
    parser.add_argument("--verbose", action="store_true", help="czas każdego zapytania HTTP")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="       %(name)s %(message)s")
    asyncio.run(main(args.parcel, args.lat, args.lon))
