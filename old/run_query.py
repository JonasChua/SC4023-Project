"""
Phase 3 (query execution): Build idx_x per x, compute minimum price-per-sqm per (x,y),
output ScanResult_<MatricNum>.csv per spec.
"""

import csv
import struct
from pathlib import Path

from page_tracker import PageTracker
from query_params import get_query_params, get_month_range
from scan import build_index_list

# Column store formats (match build_colstore.py)
FMT_YEAR = "h"
FMT_MONTH = "B"
FMT_TOWN_ID = "B"
FMT_FLOOR_AREA = "f"
FMT_RESALE_PRICE = "i"
FMT_LEASE_YEAR = "h"
FMT_BLOCK_ID = "H"
FMT_FLAT_MODEL_ID = "H"

SIZE_YEAR = struct.calcsize(FMT_YEAR)
SIZE_MONTH = struct.calcsize(FMT_MONTH)
SIZE_TOWN_ID = struct.calcsize(FMT_TOWN_ID)
SIZE_FLOOR_AREA = struct.calcsize(FMT_FLOOR_AREA)
SIZE_RESALE_PRICE = struct.calcsize(FMT_RESALE_PRICE)
SIZE_LEASE_YEAR = struct.calcsize(FMT_LEASE_YEAR)
SIZE_BLOCK_ID = struct.calcsize(FMT_BLOCK_ID)
SIZE_FLAT_MODEL_ID = struct.calcsize(FMT_FLAT_MODEL_ID)

THRESHOLD_PPM = 4725
Y_LO, Y_HI = 80, 150


def load_dict(colstore_path: Path, name: str) -> list[str]:
    """Load dict_<name>.csv; index = id, value = string."""
    path = colstore_path / f"dict_{name}.csv"
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    n = max(int(r["id"]) for r in rows) + 1
    out = [""] * n
    for r in rows:
        out[int(r["id"])] = r["value"]
    return out


def read_full_column(colstore_path: Path, filename: str, fmt: str) -> list:
    """Read entire column file into a list."""
    path = colstore_path / filename
    size = struct.calcsize(fmt)
    out = []
    with open(path, "rb") as f:
        while True:
            b = f.read(size)
            if len(b) < size:
                break
            out.append(struct.unpack(fmt, b)[0])
    return out


def run_query(
    colstore_path: Path,
    matric_str: str,
    output_path: Path | None = None,
    page_tracker: PageTracker | None = None,
) -> tuple[Path, PageTracker]:
    """
    Execute query for the given matriculation number; write ScanResult_<MatricNum>.csv.
    Returns (path to the written file, page_tracker with hits/misses).
    """
    if page_tracker is None:
        page_tracker = PageTracker()
    # Normalize matric for filename: use only alphanumeric (spec: ScanResult_<MatricNum>.csv)
    safe_matric = "".join(c for c in matric_str.strip() if c.isalnum())
    if not safe_matric:
        safe_matric = "MatricNum"
    if output_path is None:
        output_path = colstore_path.parent.parent / f"ScanResult_{safe_matric}.csv"

    target_year, start_month, town_ids = get_query_params(matric_str, colstore_path)

    # Load columns needed for filtering and for output (one-time read)
    year_col = read_full_column(colstore_path, "year.i16", FMT_YEAR)
    month_col = read_full_column(colstore_path, "month.u8", FMT_MONTH)
    town_id_col = read_full_column(colstore_path, "town_id.u8", FMT_TOWN_ID)
    floor_area_col = read_full_column(colstore_path, "floor_area.f32", FMT_FLOOR_AREA)
    resale_price_col = read_full_column(colstore_path, "resale_price.i32", FMT_RESALE_PRICE)
    lease_year_col = read_full_column(colstore_path, "lease_year.i16", FMT_LEASE_YEAR)
    block_id_col = read_full_column(colstore_path, "block_id.u16", FMT_BLOCK_ID)
    flat_model_id_col = read_full_column(colstore_path, "flat_model_id.u16", FMT_FLAT_MODEL_ID)

    dict_town = load_dict(colstore_path, "town")
    dict_block = load_dict(colstore_path, "block")
    dict_flat_model = load_dict(colstore_path, "flat_model")

    rows_out: list[tuple[int, int, dict | None]] = []  # (x, y, row_data or None)

    for x in range(1, 9):
        start_m, end_m = get_month_range(start_month, x)
        idx_x = build_index_list(
            colstore_path, target_year, start_m, end_m, town_ids, page_tracker=page_tracker
        )

        # best_price[y] and best_row_index[y] for y in 80..150
        best_price: list[float] = [float("inf")] * (Y_HI + 1)
        best_row_index: list[int | None] = [None] * (Y_HI + 1)

        for i in idx_x:
            page_tracker.access("floor_area", i, SIZE_FLOOR_AREA)
            page_tracker.access("resale_price", i, SIZE_RESALE_PRICE)
            fa = floor_area_col[i]
            rp = resale_price_col[i]
            if fa <= 0:
                continue
            ppm = rp / fa
            fa_int = int(fa)
            for y in range(Y_LO, min(Y_HI, fa_int) + 1):
                if ppm < best_price[y]:
                    best_price[y] = ppm
                    best_row_index[y] = i

        for y in range(Y_LO, Y_HI + 1):
            if best_row_index[y] is not None and round(best_price[y]) <= THRESHOLD_PPM:
                row_i = best_row_index[y]
                rows_out.append(
                    (
                        x,
                        y,
                        {
                            "year": year_col[row_i],
                            "month": month_col[row_i],
                            "town_id": town_id_col[row_i],
                            "block_id": block_id_col[row_i],
                            "floor_area": floor_area_col[row_i],
                            "flat_model_id": flat_model_id_col[row_i],
                            "lease_year": lease_year_col[row_i],
                            "price_per_sqm": round(best_price[y]),
                        },
                    )
                )
            else:
                rows_out.append((x, y, None))

    # Write CSV: (x,y), Year, Month, Town, Block, Floor_Area, Flat_Model, Lease_Commence_Date, Price_Per_Square_Meter
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "(x, y)",
                "Year",
                "Month",
                "Town",
                "Block",
                "Floor_Area",
                "Flat_Model",
                "Lease_Commence_Date",
                "Price_Per_Square_Meter",
            ]
        )
        for x, y, row_data in rows_out:
            if row_data is None:
                w.writerow([f"({x}, {y})", "No result", "", "", "", "", "", "", ""])  # spec: "No result" when no qualified data
            else:
                town_s = dict_town[row_data["town_id"]] if row_data["town_id"] < len(dict_town) else ""
                block_s = dict_block[row_data["block_id"]] if row_data["block_id"] < len(dict_block) else ""
                flat_s = (
                    dict_flat_model[row_data["flat_model_id"]]
                    if row_data["flat_model_id"] < len(dict_flat_model)
                    else ""
                )
                month_str = f"{row_data['month']:02d}"  # MM format per spec
                w.writerow(
                    [
                        f"({x}, {y})",
                        row_data["year"],
                        month_str,
                        town_s,
                        block_s,
                        row_data["floor_area"],
                        flat_s,
                        row_data["lease_year"],
                        row_data["price_per_sqm"],
                    ]
                )

    return output_path, page_tracker
