import argparse
import shutil
import tarfile
import tempfile
from pathlib import Path

import httpx

from app.core.config import get_settings


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Pobranie gotowej kostki ERA5-Land (bez klucza CDS)")
    parser.add_argument("--url", default=settings.era5_cube_url)
    parser.add_argument("--out", type=Path, default=settings.era5_cube_path)
    args = parser.parse_args()
    if not args.url:
        raise SystemExit("Podaj --url albo ERA5_CUBE_URL w .env (link w README).")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "cube.tar.gz"
        with httpx.stream("GET", args.url, follow_redirects=True, timeout=None) as r, archive.open("wb") as fh:
            r.raise_for_status()
            for block in r.iter_bytes(1 << 20):
                fh.write(block)
        with tarfile.open(archive) as tar:
            tar.extractall(tmp, filter="data")
        found = next(Path(tmp).glob("**/*.zarr"))
        if args.out.exists():
            shutil.rmtree(args.out)
        shutil.move(str(found), args.out)
    print(f"Kostka zapisana w {args.out}")


if __name__ == "__main__":
    main()
