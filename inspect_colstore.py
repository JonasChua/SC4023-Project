"""
Helper to inspect the on-disk column store.

Usage:
  python inspect_colstore.py              # summary + first 10 rows
  python inspect_colstore.py -n 20        # first 20 rows
  python inspect_colstore.py --stats     # summary + min/max only, no rows
  python inspect_colstore.py -n 0        # summary only (row count, file sizes)
"""

import argparse
import csv
import struct
import sys
from pathlib import Path

# -----------------------------------------------------------------------------
# Paths and formats (must match build_colstore.py)
# -----------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
COLSTORE_DIR = PROJECT_ROOT / "data" / "colstore"

FMT_YEAR = "h"
FMT_MONTH = "B"
FMT_TOWN_ID = "B"
FMT_FLOOR_AREA = "f"
FMT_RESALE_PRICE = "i"
FMT_LEASE_YEAR = "h"
FMT_BLOCK_ID = "H"
FMT_FLAT_MODEL_ID = "H"

SIZES = {
    "year": struct.calcsize(FMT_YEAR),
    "month": struct.calcsize(FMT_MONTH),
    "town_id": struct.calcsize(FMT_TOWN_ID),
    "floor_area": struct.calcsize(FMT_FLOOR_AREA),
    "resale_price": struct.calcsize(FMT_RESALE_PRICE),
    "lease_year": struct.calcsize(FMT_LEASE_YEAR),
    "block_id": struct.calcsize(FMT_BLOCK_ID),
    "flat_model_id": struct.calcsize(FMT_FLAT_MODEL_ID),
}

COLUMN_FILES = [
    ("year", "year.i16", FMT_YEAR),
    ("month", "month.u8", FMT_MONTH),
    ("town_id", "town_id.u8", FMT_TOWN_ID),
    ("floor_area", "floor_area.f32", FMT_FLOOR_AREA),
    ("resale_price", "resale_price.i32", FMT_RESALE_PRICE),
    ("lease_year", "lease_year.i16", FMT_LEASE_YEAR),
    ("block_id", "block_id.u16", FMT_BLOCK_ID),
    ("flat_model_id", "flat_model_id.u16", FMT_FLAT_MODEL_ID),
]


def load_dict(colstore_path: Path, name: str) -> list[str]:
    """Load dict_<name>.csv; return list where index = id, value = string."""
    path = colstore_path / f"dict_{name}.csv"
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    # id might not be 0..n-1 if we sort; build by id
    n = max(int(r["id"]) for r in rows) + 1
    out = [""] * n
    for r in rows:
        out[int(r["id"])] = r["value"]
    return out


def read_column(colstore_path: Path, filename: str, fmt: str) -> list:
    """Read entire column file into a list of values."""
    path = colstore_path / filename
    if not path.exists():
        return []
    size = struct.calcsize(fmt)
    out = []
    with open(path, "rb") as f:
        while True:
            b = f.read(size)
            if len(b) < size:
                break
            out.append(struct.unpack(fmt, b)[0])
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Inspect column store contents")
    ap.add_argument("-n", "--rows", type=int, default=10, help="Number of rows to print (0 = none)")
    ap.add_argument("--stats", action="store_true", help="Print only summary and min/max, no row dump")
    args = ap.parse_args()

    if not COLSTORE_DIR.exists():
        print(f"Colstore not found: {COLSTORE_DIR}")
        print("Run build_colstore.py first.")
        sys.exit(1)

    # Row count from first column
    year_path = COLSTORE_DIR / "year.i16"
    if not year_path.exists():
        print("Column files not found in", COLSTORE_DIR)
        sys.exit(1)
    n_rows = year_path.stat().st_size // struct.calcsize(FMT_YEAR)

    # Summary
    print("=== Column store summary ===")
    print(f"Directory: {COLSTORE_DIR}")
    print(f"Row count: {n_rows:,}")
    print()
    print("Column files:")
    for name, filename, fmt in COLUMN_FILES:
        path = COLSTORE_DIR / filename
        if path.exists():
            size = path.stat().st_size
            print(f"  {filename}: {size:,} bytes")
    print()
    # Dictionaries
    for d in ["town", "flat_model", "block"]:
        L = load_dict(COLSTORE_DIR, d)
        if L:
            print(f"  dict_{d}.csv: {len(L)} entries")
    print()

    if args.stats or args.rows <= 0:
        if args.stats:
            print("=== Numeric stats (min / max) ===")
            for name, filename, fmt in COLUMN_FILES:
                path = COLSTORE_DIR / filename
                if not path.exists():
                    continue
                vals = read_column(COLSTORE_DIR, filename, fmt)
                if not vals:
                    continue
                if isinstance(vals[0], float):
                    print(f"  {name}: {min(vals):.2f} / {max(vals):.2f}")
                else:
                    print(f"  {name}: {min(vals)} / {max(vals)}")
        return

    # Load dictionaries for decoded view
    town_dec = load_dict(COLSTORE_DIR, "town")
    flat_dec = load_dict(COLSTORE_DIR, "flat_model")
    block_dec = load_dict(COLSTORE_DIR, "block")

    # Load columns (only as many as we need for display)
    n_show = min(args.rows, n_rows)
    cols = {}
    for name, filename, fmt in COLUMN_FILES:
        path = COLSTORE_DIR / filename
        if not path.exists():
            continue
        size = struct.calcsize(fmt)
        vals = []
        with open(path, "rb") as f:
            for _ in range(n_show):
                b = f.read(size)
                if len(b) < size:
                    break
                vals.append(struct.unpack(fmt, b)[0])
        cols[name] = vals

    # Pad to same length
    n_show = min(len(v) for v in cols.values()) if cols else 0
    if n_show == 0:
        print("No rows to display.")
        return

    print(f"=== First {n_show} rows (decoded) ===")
    # Header
    print(f"{'row':>5} | {'year':>4} | {'month':>2} | {'town':<18} | {'floor_area':>6} | {'resale_price':>12} | {'lease':>5} | {'block':<8} | flat_model")
    print("-" * 120)
    for i in range(n_show):
        tid = cols["town_id"][i]
        fid = cols["flat_model_id"][i]
        bid = cols["block_id"][i]
        town_s = town_dec[tid] if tid < len(town_dec) else str(tid)
        flat_s = flat_dec[fid] if fid < len(flat_dec) else str(fid)
        block_s = block_dec[bid] if bid < len(block_dec) else str(bid)
        fa = cols["floor_area"][i]
        rp = cols["resale_price"][i]
        print(f"{i:>5} | {cols['year'][i]:>4} | {cols['month'][i]:>2} | {town_s:<18} | {fa:>6.1f} | {rp:>12} | {cols['lease_year'][i]:>5} | {block_s:<8} | {flat_s}")
    print()


if __name__ == "__main__":
    main()
