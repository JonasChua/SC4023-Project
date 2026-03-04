"""
Phase 1: Build the on-disk column store (single pass over CSV).

Reads ResalePricesSingapore.csv line-by-line (streaming, no pandas), parses each row,
appends values to binary column files in the same row order, and maintains
dictionary mappings for Town, Flat_Model, and Block. Writes dict_*.csv at the end
for decoding IDs back to strings in later phases.

Column store layout (data/colstore/):
  year.i16, month.u8, town_id.u8, floor_area.f32, resale_price.i32,
  lease_year.i16, block_id.u16, flat_model_id.u16
  dict_town.csv, dict_flat_model.csv, dict_block.csv
"""

import csv
import os
import struct
from pathlib import Path

# -----------------------------------------------------------------------------
# Paths and config
# -----------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
# Prefer data/raw/ResalePricesSingapore.csv; fallback to repo root
RAW_CSV = PROJECT_ROOT / "data" / "raw" / "ResalePricesSingapore.csv"
if not RAW_CSV.exists():
    RAW_CSV = PROJECT_ROOT / "ResalePricesSingapore.csv"
COLSTORE_DIR = PROJECT_ROOT / "data" / "colstore"

# Binary format per row (one value per column file per row)
# year: int16; month: uint8; town_id: uint8; floor_area: float32; resale_price: int32;
# lease_year: int16; block_id: uint16; flat_model_id: uint16
FMT_YEAR = "h"          # i16
FMT_MONTH = "B"         # u8
FMT_TOWN_ID = "B"       # u8
FMT_FLOOR_AREA = "f"    # f32
FMT_RESALE_PRICE = "i"  # i32
FMT_LEASE_YEAR = "h"    # i16
FMT_BLOCK_ID = "H"      # u16
FMT_FLAT_MODEL_ID = "H" # u16

# Month string "Jan-15" -> (year, month)
MONTH_ABBR = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


def parse_month(month_str: str) -> tuple[int, int]:
    """
    Parse 'Mon-YY' (e.g. 'Jan-15', 'Mar-20') -> (year, month).
    Year: 00-25 -> 2000-2025; 26-99 -> 1926-1999 (for old data if any).
    """
    part = month_str.strip().split("-")
    if len(part) != 2:
        raise ValueError(f"Invalid month string: {month_str!r}")
    abbr, yy = part[0].strip(), part[1].strip()
    month = MONTH_ABBR.get(abbr)
    if month is None:
        raise ValueError(f"Unknown month abbr: {abbr!r}")
    y = int(yy)
    year = 2000 + y if y <= 25 else 1900 + y
    return (year, month)


def dict_assign(m: dict[str, int], s: str) -> int:
    """Assign next id to string if new; return id."""
    s = s.strip()
    if s not in m:
        m[s] = len(m)
    return m[s]


def build_column_store(csv_path: Path, colstore_path: Path) -> int:
    """
    Single pass over CSV: parse each row, append to column files, build dicts.
    Returns number of rows written.
    """
    # Dictionary maps: string -> integer id (assigned in encounter order)
    town_map: dict[str, int] = {}
    flat_model_map: dict[str, int] = {}
    block_map: dict[str, int] = {}

    colstore_path.mkdir(parents=True, exist_ok=True)

    # Open all column files for appending (binary write)
    year_f = open(colstore_path / "year.i16", "wb")
    month_f = open(colstore_path / "month.u8", "wb")
    town_f = open(colstore_path / "town_id.u8", "wb")
    floor_f = open(colstore_path / "floor_area.f32", "wb")
    resale_f = open(colstore_path / "resale_price.i32", "wb")
    lease_f = open(colstore_path / "lease_year.i16", "wb")
    block_f = open(colstore_path / "block_id.u16", "wb")
    flat_model_f = open(colstore_path / "flat_model_id.u16", "wb")

    row_count = 0
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                month_str = row["month"]
                year, month = parse_month(month_str)
                town_id = dict_assign(town_map, row["town"])
                floor_area = float(row["floor_area_sqm"])
                resale_price = int(row["resale_price"])
                lease_year = int(row["lease_commence_date"])
                block_id = dict_assign(block_map, row["block"])
                flat_model_id = dict_assign(flat_model_map, row["flat_model"])
            except (KeyError, ValueError) as e:
                # Skip bad rows or log; for robustness we skip
                continue

            # Append one value per column file (same row order)
            year_f.write(struct.pack(FMT_YEAR, year))
            month_f.write(struct.pack(FMT_MONTH, month))
            town_f.write(struct.pack(FMT_TOWN_ID, town_id))
            floor_f.write(struct.pack(FMT_FLOOR_AREA, floor_area))
            resale_f.write(struct.pack(FMT_RESALE_PRICE, resale_price))
            lease_f.write(struct.pack(FMT_LEASE_YEAR, lease_year))
            block_f.write(struct.pack(FMT_BLOCK_ID, block_id))
            flat_model_f.write(struct.pack(FMT_FLAT_MODEL_ID, flat_model_id))
            row_count += 1

    # Close column files
    year_f.close()
    month_f.close()
    town_f.close()
    floor_f.close()
    resale_f.close()
    lease_f.close()
    block_f.close()
    flat_model_f.close()

    # Write dictionary CSV files: id,string for decoding
    def write_dict_csv(name: str, m: dict[str, int]) -> None:
        # Sort by id so id is the row index
        items = sorted(m.items(), key=lambda x: x[1])
        with open(colstore_path / name, "w", newline="", encoding="utf-8") as out:
            w = csv.writer(out)
            w.writerow(["id", "value"])
            for s, i in items:
                w.writerow([i, s])

    write_dict_csv("dict_town.csv", town_map)
    write_dict_csv("dict_flat_model.csv", flat_model_map)
    write_dict_csv("dict_block.csv", block_map)

    return row_count


def main() -> None:
    if not RAW_CSV.exists():
        print(f"CSV not found: {RAW_CSV}")
        print("Place ResalePricesSingapore.csv in data/raw/ or project root.")
        return
    n = build_column_store(RAW_CSV, COLSTORE_DIR)
    print(f"Phase 1 done: wrote {n} rows to {COLSTORE_DIR}")
    print("Column files: year.i16, month.u8, town_id.u8, floor_area.f32, resale_price.i32, lease_year.i16, block_id.u16, flat_model_id.u16")
    print("Dictionaries: dict_town.csv, dict_flat_model.csv, dict_block.csv")


if __name__ == "__main__":
    main()
