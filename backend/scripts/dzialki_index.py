import argparse
import email.utils
import json
import os
import sys
import time
from pathlib import Path

import duckdb
import httpx
import numpy as np
import shapely
from pyproj import Transformer
from shapely import wkb, wkt
from shapely.geometry import Point, mapping

URL = "https://opendata.geoportal.gov.pl/InneDane/latest_exports/eziudp_wfs/PARQUET/0_dzialki.parquet"
WOJ = ("02", "04", "06", "08", "10", "12", "14", "16", "18", "20", "22", "24", "26", "28", "30", "32")
COLUMNS = (
    "id_dzialki, numer_dzialki, nazwa_obrebu, numer_obrebu, numer_jednostki, nazwa_gminy, data, "
    "pole_ewidencyjne, klasouzytki_egib, grupa_rejestrowa, pozostale_atrybuty, czas_pozyskania"
)
TO_2180 = Transformer.from_crs(4326, 2180, always_xy=True)
TO_4326 = Transformer.from_crs(2180, 4326, always_xy=True)


def download(dest: Path, url: str = URL) -> bool:
    part = dest.with_suffix(dest.suffix + ".part")
    headers = {}
    if dest.exists() and not part.exists():
        headers["If-Modified-Since"] = email.utils.formatdate(dest.stat().st_mtime, usegmt=True)
    offset = part.stat().st_size if part.exists() else 0
    if offset:
        headers["Range"] = f"bytes={offset}-"
    with httpx.stream("GET", url, headers=headers, timeout=60, follow_redirects=True) as response:
        if response.status_code == 304:
            print("plik jest aktualny")
            return False
        if response.status_code == 200:
            offset = 0
        elif response.status_code != 206:
            response.raise_for_status()
        total = offset + int(response.headers.get("content-length", 0))
        done, last = offset, time.time()
        with part.open("ab" if offset else "wb") as out:
            for chunk in response.iter_bytes(8 * 1024 * 1024):
                out.write(chunk)
                done += len(chunk)
                if time.time() - last > 5:
                    print(f"{done / 1e9:.2f} / {total / 1e9:.2f} GB", flush=True)
                    last = time.time()
        modified = response.headers.get("last-modified")
    os.replace(part, dest)
    if modified:
        stamp = email.utils.parsedate_to_datetime(modified).timestamp()
        os.utime(dest, (stamp, stamp))
    print(f"pobrano {dest} ({dest.stat().st_size / 1e9:.2f} GB)")
    return True


def _connect(memory: str = "4GB") -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute(f"SET memory_limit = '{memory}'")
    con.execute("SET preserve_insertion_order = false")
    return con


def build(source: Path, out_dir: Path, memory: str = "4GB") -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    con = _connect(memory)
    con.execute(f"SET temp_directory = '{(out_dir / '_tmp').as_posix()}'")
    src = source.as_posix()
    for woj in WOJ:
        target = out_dir / f"woj_{woj}.parquet"
        tmp = target.with_suffix(".tmp")
        started = time.time()
        con.execute(
            f"""
            COPY (
                SELECT {COLUMNS},
                       geometry_bbox.xmin AS xmin, geometry_bbox.ymin AS ymin,
                       geometry_bbox.xmax AS xmax, geometry_bbox.ymax AS ymax,
                       geometry
                FROM read_parquet('{src}')
                WHERE starts_with(id_dzialki, '{woj}')
                ORDER BY id_dzialki
            ) TO '{tmp.as_posix()}' (FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 20000)
            """
        )
        os.replace(tmp, target)
        count = con.execute(f"SELECT count(*) FROM read_parquet('{target.as_posix()}')").fetchone()[0]
        print(f"woj {woj}: {count} działek, {time.time() - started:.0f} s", flush=True)
    other = con.execute(
        f"SELECT count(*) FROM read_parquet('{src}') WHERE NOT list_contains({list(WOJ)}, left(id_dzialki, 2))"
    ).fetchone()[0]
    if other:
        print(f"uwaga: {other} działek z nieznanym kodem województwa pominięto")


def _row(names: list[str], values: tuple, geometry: bool = True) -> dict:
    row = dict(zip(names, values, strict=True))
    raw = row.pop("geometry", None)
    if geometry and raw is not None:
        geom = wkb.loads(bytes(raw))
        row["geometry_2180"] = geom.wkt
        row["geometry_4326"] = mapping(_to_4326(geom))
    return row


def _to_4326(geom):
    return shapely.transform(geom, lambda c: np.column_stack(TO_4326.transform(c[:, 0], c[:, 1])))


def _query(con, sql: str, params: list, geometry: bool = True) -> list[dict]:
    cursor = con.execute(sql, params)
    names = [d[0] for d in cursor.description]
    return [_row(names, values, geometry) for values in cursor.fetchall()]


def by_id(index: Path, parcel_id: str) -> dict | None:
    target = index / f"woj_{parcel_id[:2]}.parquet"
    if not target.exists():
        return None
    rows = _query(_connect(), f"SELECT * FROM read_parquet('{target.as_posix()}') WHERE id_dzialki = ?", [parcel_id])
    return rows[0] if rows else None


def by_point(index: Path, lat: float, lon: float) -> dict | None:
    x, y = TO_2180.transform(lon, lat)
    point = Point(x, y)
    rows = _query(
        _connect(),
        f"SELECT * FROM read_parquet('{(index / 'woj_*.parquet').as_posix()}') "
        "WHERE xmin <= ? AND xmax >= ? AND ymin <= ? AND ymax >= ?",
        [x, x, y, y],
    )
    for row in rows:
        if wkt.loads(row["geometry_2180"]).covers(point):
            return row
    return None


def by_commune(index: Path, woj: str, commune: str, limit: int = 50) -> list[dict]:
    target = index / f"woj_{woj}.parquet"
    return _query(
        _connect(),
        f"SELECT id_dzialki, numer_dzialki, nazwa_obrebu, nazwa_gminy, pole_ewidencyjne "
        f"FROM read_parquet('{target.as_posix()}') WHERE nazwa_gminy ILIKE ? ORDER BY id_dzialki LIMIT ?",
        [commune, limit],
        geometry=False,
    )


def _show(result) -> None:
    if result is None or result == []:
        print("nie znaleziono")
        return
    print(json.dumps(result, ensure_ascii=False, indent=1, default=str)[:20000])


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Działki EGiB dla całej Polski: pobieranie, indeks, wyszukiwanie")
    parser.add_argument("--plik", type=Path, default=Path("dzialki.parquet"))
    parser.add_argument("--indeks", type=Path, default=Path("dzialki_indeks"))
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("pobierz")
    build_cmd = sub.add_parser("indeks")
    build_cmd.add_argument("--pamiec", default="4GB")
    find_id = sub.add_parser("id")
    find_id.add_argument("id_dzialki")
    find_point = sub.add_parser("punkt")
    find_point.add_argument("lat", type=float)
    find_point.add_argument("lon", type=float)
    commune = sub.add_parser("gmina")
    commune.add_argument("woj")
    commune.add_argument("nazwa")
    commune.add_argument("--limit", type=int, default=50)
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    started = time.time()
    if args.cmd == "pobierz":
        download(args.plik)
    elif args.cmd == "indeks":
        build(args.plik, args.indeks, args.pamiec)
    elif args.cmd == "id":
        _show(by_id(args.indeks, args.id_dzialki))
    elif args.cmd == "punkt":
        _show(by_point(args.indeks, args.lat, args.lon))
    elif args.cmd == "gmina":
        _show(by_commune(args.indeks, args.woj, args.nazwa, args.limit))
    print(f"czas: {time.time() - started:.2f} s", file=sys.stderr)


if __name__ == "__main__":
    main()
