# /// script
# requires-python = ">=3.10"
# dependencies = ["geopandas>=1.0", "pyogrio>=0.9", "shapely>=2.0"]
# ///
"""Clip Amazon Mining Watch (AMW) patch detections to Ecuador and save a small file.

WHY: the full AMW file is 113 MB and our cloud workspace cannot download it (source.coop is blocked there).
This script runs on YOUR computer, downloads the file, keeps only the patches inside Ecuador's bounding box
(plus a margin) and writes a few-MB GeoJSON that can be attached to the chat. The bounding box also catches
slivers of Colombia and Peru; the analysis cuts those off later with the real Ecuador border.

RUN (needs uv, https://docs.astral.sh/uv/ ; no repository checkout required):
    uv run clip_amw_ecuador.py
    uv run clip_amw_ecuador.py --src amazon_basin_detections.geojson     # if you already have the big file
Output: amw_ecuador.geojson (next to where you run it; change with --out).

The script changes nothing in the source data: patches keep every original column.
Source: Amazon Mining Watch, Earth Genome / Earthrise Media, CC-BY-4.0.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

URL = "https://data.source.coop/earthgenome/amazon-mining-watch/amazon_basin_detections.geojson"
# sha256 of the file the team downloaded on 2026-10-10 (DOWNLOAD_LOG.csv). A different value is not an error:
# AMW is updated regularly. It only tells us whether we are using the same version as the rest of the project.
KNOWN_SHA256 = "f76555212661a10f9462a430cf91174e3507a872f1bf3e9686fc5465f12a56a8"
# lon/lat bounding box: mainland Ecuador is about -81.1..-75.2 / -5.0..1.5; 0.5 degree margin.
BBOX = (-81.6, -5.5, -74.7, 2.0)


def download(dest: Path) -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 (data-for-good clip script)"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            got = 0
            while chunk := r.read(1 << 20):
                f.write(chunk)
                got += len(chunk)
                if total:
                    print(f"\r  downloaded {got/1e6:6.1f} / {total/1e6:.1f} MB", end="", flush=True)
                else:
                    print(f"\r  downloaded {got/1e6:6.1f} MB", end="", flush=True)
    except (urllib.error.URLError, TimeoutError) as e:
        sys.exit(f"\nDownload failed: {e}\nOpen {URL} in a browser, save the file, and run again with --src <file>.")
    print(f"\n  done in {time.time()-t0:.0f} s")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--src", type=Path, help="local copy of amazon_basin_detections.geojson (skips the download)")
    ap.add_argument("--out", type=Path, default=Path("amw_ecuador.geojson"))
    a = ap.parse_args()

    import pyogrio

    tmp = None
    if a.src:
        src = a.src
        if not src.exists():
            sys.exit(f"File not found: {src}")
    else:
        tmp = tempfile.TemporaryDirectory()
        src = Path(tmp.name) / "amazon_basin_detections.geojson"
        print(f"Downloading {URL}")
        download(src)

    digest = sha256(src)
    print(f"source: {src}  {src.stat().st_size} bytes  sha256={digest}")
    print("  same version as the team's 2026-10-10 download" if digest == KNOWN_SHA256 else
          "  NOTE: differs from the team's 2026-10-10 download (AMW was probably updated); tell Claude")

    print(f"Reading patches inside bbox {BBOX} ...")
    gdf = pyogrio.read_dataframe(src, bbox=BBOX)
    if gdf.empty:
        sys.exit("No patches found in the bounding box: wrong file?")
    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    elif gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(4326)
    gdf.to_file(a.out, driver="GeoJSON")

    print(f"\nwrote {a.out}  ({a.out.stat().st_size/1e6:.1f} MB), {len(gdf)} patches")
    print("columns:", ", ".join(c for c in gdf.columns if c != "geometry"))
    for col in ("onset_year", "status"):
        if col in gdf.columns:
            print(f"{col}: {gdf[col].value_counts(dropna=False).sort_index().to_dict()}")
    print("\nNext: attach this file in the chat.")
    if tmp:
        tmp.cleanup()


if __name__ == "__main__":
    main()
