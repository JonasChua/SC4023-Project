"""
Phase 3 (scan): Block-wise scan of column store to build list of row indices
matching (target_year, month in [start_month, end_month], town_id in town_ids).

Aligns with page/block-style access for the report.
"""

from __future__ import annotations

import struct
from pathlib import Path

from page_tracker import PageTracker

# Must match build_colstore.py
FMT_YEAR = "h"
FMT_MONTH = "B"
FMT_TOWN_ID = "B"

SIZE_YEAR = struct.calcsize(FMT_YEAR)
SIZE_MONTH = struct.calcsize(FMT_MONTH)
SIZE_TOWN_ID = struct.calcsize(FMT_TOWN_ID)

# Block size for reading (e.g. 4KB for page-style access)
DEFAULT_BLOCK_BYTES = 4096


def build_index_list(
    colstore_path: Path,
    target_year: int,
    start_month: int,
    end_month: int,
    town_ids: set[int],
    block_bytes: int = DEFAULT_BLOCK_BYTES,
    page_tracker: PageTracker | None = None,
) -> list[int]:
    """
    Scan year, month, town_id columns in blocks; return list of row indices
    where year == target_year, start_month <= month <= end_month, town_id in town_ids.
    """
    year_path = colstore_path / "year.i16"
    month_path = colstore_path / "month.u8"
    town_path = colstore_path / "town_id.u8"

    rows_per_block = block_bytes // (SIZE_YEAR + SIZE_MONTH + SIZE_TOWN_ID)
    if rows_per_block <= 0:
        rows_per_block = 1

    block_year_bytes = rows_per_block * SIZE_YEAR
    block_month_bytes = rows_per_block * SIZE_MONTH
    block_town_bytes = rows_per_block * SIZE_TOWN_ID

    idx_list: list[int] = []
    global_row = 0
    block_index = 0

    with open(year_path, "rb") as fy, open(month_path, "rb") as fm, open(town_path, "rb") as ft:
        while True:
            year_buf = fy.read(block_year_bytes)
            month_buf = fm.read(block_month_bytes)
            town_buf = ft.read(block_town_bytes)
            n = len(year_buf) // SIZE_YEAR
            if n == 0:
                break

            if page_tracker is not None:
                page_tracker.record_scan_block("year", block_index)
                page_tracker.record_scan_block("month", block_index)
                page_tracker.record_scan_block("town_id", block_index)

            for i in range(n):
                year = struct.unpack_from(FMT_YEAR, year_buf, i * SIZE_YEAR)[0]
                month = struct.unpack_from(FMT_MONTH, month_buf, i * SIZE_MONTH)[0]
                town_id = struct.unpack_from(FMT_TOWN_ID, town_buf, i * SIZE_TOWN_ID)[0]
                if (
                    year == target_year
                    and start_month <= month <= end_month
                    and town_id in town_ids
                ):
                    idx_list.append(global_row + i)
            global_row += n
            block_index += 1

    return idx_list
