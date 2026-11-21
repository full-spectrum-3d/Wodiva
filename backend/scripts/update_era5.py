import argparse
import logging
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import xarray as xr

from app.core.config import get_settings
from scripts.era5_common import assemble, chunks, download, jobs_for, last_day_available, write_cube

log = logging.getLogger("era5.update")


def update_once(out: Path, workdir: Path, lag_days: int) -> None:
    end = last_day_available(lag_days)
    if not out.exists():
        raise SystemExit(f"Brak kostki {out}. Uruchom najpierw scripts.build_era5_cube.")
    last = pd.Timestamp(xr.open_zarr(out)["time"].values[-1]).date()
    start = last + timedelta(days=1)
    if start > end:
        log.info("kostka aktualna do %s", last)
        return
    chunk_list = chunks(start, end, "month")
    for chunk in chunk_list:
        for _, _, path in jobs_for(chunk, workdir):
            path.unlink(missing_ok=True)
    download([job for c in chunk_list for job in jobs_for(c, workdir)], workers=4)
    ds = assemble(workdir, chunk_list).sel(time=slice(str(start), str(end)))
    write_cube(ds, out, append=True)


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Dopisanie nowych dni do kostki ERA5-Land")
    parser.add_argument("--out", type=Path, default=settings.era5_cube_path)
    parser.add_argument("--workdir", type=Path, default=settings.era5_cube_path.parent / "era5_raw")
    parser.add_argument("--loop", action="store_true", help="codziennie o 06:00 UTC")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    args.workdir.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            update_once(args.out, args.workdir, settings.era5_lag_days)
        except Exception:
            log.exception("aktualizacja nieudana")
        if not args.loop:
            break
        now = datetime.now(UTC)
        nxt = (now + timedelta(days=1)).replace(hour=6, minute=0, second=0, microsecond=0)
        time.sleep(max(60.0, (nxt - now).total_seconds()))


if __name__ == "__main__":
    main()
