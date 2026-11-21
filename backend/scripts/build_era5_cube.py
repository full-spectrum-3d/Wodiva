import argparse
import logging
from datetime import date
from pathlib import Path

from app.core.config import get_settings
from scripts.era5_common import assemble, chunks, download, jobs_for, last_day_available, write_cube


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Budowa kostki ERA5-Land dla Polski (Zarr)")
    parser.add_argument("--start", type=date.fromisoformat, default=date.fromisoformat(settings.era5_start))
    parser.add_argument("--end", type=date.fromisoformat, default=last_day_available(settings.era5_lag_days))
    parser.add_argument("--out", type=Path, default=settings.era5_cube_path)
    parser.add_argument("--workdir", type=Path, default=settings.era5_cube_path.parent / "era5_raw")
    parser.add_argument("--chunk", choices=["year", "month"], default="year")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--only-assemble", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    args.workdir.mkdir(parents=True, exist_ok=True)
    chunk_list = chunks(args.start, args.end, args.chunk)
    if not args.only_assemble:
        jobs = [job for c in chunk_list for job in jobs_for(c, args.workdir)]
        download(jobs, args.workers)
    ds = assemble(args.workdir, chunk_list)
    ds = ds.sel(time=slice(str(args.start), str(args.end)))
    write_cube(ds, args.out)


if __name__ == "__main__":
    main()
