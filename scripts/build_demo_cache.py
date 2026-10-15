"""
Build the offline data used when Earth Engine is unavailable.

  data/demo_cache.csv.gz  monthly series for every preset region x variable
  data/demo_cubes.npz     yearly maps (time-lapse / before-after / trend layers)
                          for the case-file place + variable pairs

Real NASA data is fetched from Google Earth Engine when it is connected; otherwise the
deterministic synthetic data (labelled as such) is stored, so the offline demo always
has something to show. Series progress is saved every few series, so an interrupted
run can be resumed with --missing-only.

Usage (from the project folder):
    python scripts/build_demo_cache.py                  # series + map cubes
    python scripts/build_demo_cache.py --missing-only   # resume: only series not cached yet
    python scripts/build_demo_cache.py --cubes-only     # only the map cubes
    python scripts/build_demo_cache.py --synthetic      # no Earth Engine
"""

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env")

import pandas as pd  # noqa: E402

import demo_data  # noqa: E402
import geoai_engine as ge  # noqa: E402
import nasa_variables as nv  # noqa: E402
import regions  # noqa: E402

MAX_HLS_RADIUS_KM = 25   # 30 m data over huge regions is slow and not what HLS is for
SAVE_EVERY = 3


def fetch(preset_key: str, var_key: str, live: bool) -> pd.DataFrame:
    var = nv.get(var_key)
    region = regions.region_dict(preset_key)
    if live:
        df = ge.get_monthly_series(var_key, region, var.start_year, var.last_year)
        df = df[["date", "value"]].assign(source=f"NASA via Google Earth Engine ({var.collection})")
    else:
        df = demo_data.synthetic_series(var_key, region["lat"], region["lon"], var.start_year, var.last_year)
    return df.assign(preset=preset_key, variable=var_key, retrieved=date.today().isoformat())


def save_series(frames: list) -> pd.DataFrame:
    out = pd.concat(frames, ignore_index=True)[["preset", "variable", "date", "value", "source", "retrieved"]]
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    out["value"] = out["value"].round(6)
    out = out.drop_duplicates(["preset", "variable", "date"], keep="last").sort_values(["preset", "variable", "date"])
    demo_data.CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(demo_data.CACHE_PATH, index=False, compression="gzip")
    return out


def build_series(live: bool, workers: int, missing_only: bool):
    jobs = [
        (p, v) for p in regions.PRESETS for v, var in nv.VARIABLES.items()
        if not (var.preprocess and regions.PRESETS[p]["radius_km"] > MAX_HLS_RADIUS_KM)
    ]
    frames = []
    if missing_only and demo_data.CACHE_PATH.exists():
        old = pd.read_csv(demo_data.CACHE_PATH)
        have = set(zip(old["preset"], old["variable"]))
        jobs = [j for j in jobs if j not in have]
        frames.append(old)
        print(f"Keeping {len(have)} cached series; fetching {len(jobs)} missing")
    t0, done = time.time(), 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(fetch, p, v, live): (p, v) for p, v in jobs}
        for i, fut in enumerate(as_completed(futs), 1):
            p, v = futs[fut]
            try:
                df = fut.result()
                if len(df):
                    frames.append(df)
                    done += 1
                print(f"[{i:3d}/{len(jobs)}] {p:18s} {v:20s} {len(df):4d} rows  ({time.time() - t0:5.0f}s)", flush=True)
            except Exception as e:
                print(f"[{i:3d}/{len(jobs)}] {p:18s} {v:20s} FAILED: {str(e)[:120]}", flush=True)
            if done and done % SAVE_EVERY == 0 and frames:
                save_series(frames)
    if frames:
        out = save_series(frames)
        print(f"Wrote {len(out):,} rows for {out.groupby(['preset', 'variable']).ngroups} series "
              f"to {demo_data.CACHE_PATH} ({demo_data.CACHE_PATH.stat().st_size / 1e6:.2f} MB)")


def cube_jobs():
    """Case-file place + variable pairs (single-place examples and compare stories)."""
    pairs = {(pk, vk) for pk, vk, _, _ in regions.EXAMPLES}
    pairs |= {(pk, s["variable"]) for s in regions.STORIES for pk in s["regions"]}
    # GRACE places also get the sharper GLDAS model maps, so switching measurement there works offline too
    pairs |= {(pk, alt) for pk, vk in list(pairs) if vk == "water_storage"
              for alt in ("water_storage_gldas", "groundwater_gldas")}
    return sorted(pairs)


def build_cubes(live: bool):
    cubes, t0 = {}, time.time()
    for i, (pk, vk) in enumerate(cube_jobs(), 1):
        var = nv.get(vk)
        bounds = ge.change_bounds(regions.region_dict(pk), var)      # the same map area the app asks for
        try:
            if live:
                cube = ge.get_change_cube(vk, bounds, var.start_year, var.last_year)
            else:
                cube = demo_data.synthetic_cube(vk, bounds, var.start_year, var.last_year)
            cubes[(pk, vk)] = cube
            print(f"[cube {i:2d}] {pk:18s} {vk:20s} {len(cube['years'])} years  ({time.time() - t0:5.0f}s)", flush=True)
        except Exception as e:
            print(f"[cube {i:2d}] {pk:18s} {vk:20s} FAILED: {str(e)[:120]}", flush=True)
    if cubes:
        demo_data.save_cubes(cubes)
        print(f"Wrote {len(cubes)} map cubes to {demo_data.CUBES_PATH} ({demo_data.CUBES_PATH.stat().st_size / 1e6:.2f} MB)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--synthetic", action="store_true", help="do not use Earth Engine")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--missing-only", action="store_true", help="keep the existing series cache, fetch only missing series")
    ap.add_argument("--cubes-only", action="store_true", help="only build the map cubes")
    ap.add_argument("--series-only", action="store_true", help="only build the monthly series")
    args = ap.parse_args()

    live = (not args.synthetic) and ge.init_gee()
    print(f"Earth Engine: {ge.EE_STATUS}" if not args.synthetic else "Synthetic mode")
    if not args.series_only:
        build_cubes(live)
    if not args.cubes_only:
        build_series(live, args.workers, args.missing_only)


if __name__ == "__main__":
    main()
