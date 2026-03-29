from ast import literal_eval
from collections.abc import Callable, Mapping
from csv import DictReader
from pathlib import Path
from time import perf_counter
from typing import Any, Literal, Sequence

from column import FloatColumn, StringColumn, UnsignedCharColumn, UnsignedShortColumn
from constants import BLOCK_SIZE, MONTH_ABBR, RAW_CSV
from mapping import map_loader, map_writer

ColumnType = UnsignedCharColumn | UnsignedShortColumn | FloatColumn | StringColumn


class ColumnStore:
    def __init__(
        self,
        types: Sequence[Literal["basic", "compressed", "zone map", "indexed"]],
        colstore_path: Path,
        columns: Mapping[str, ColumnType],
    ) -> None:
        self.colstore_path = colstore_path
        self.columns = columns
        self.types = types
        self._cache: dict[tuple[str, int], list] = {}
        self._composite_index: dict[tuple[Any, Any, Any], list[int]] = {}
        self._file_read_counters: dict[str, int] = {
            col.name: 0 for col in columns.values()
        }
        start = perf_counter()
        self._initialise_column_files()
        self._load_compression_mappings()
        self._initialise_zone_maps()
        self._initialise_composite_index()
        self.initialisation_time = perf_counter() - start
        self.query_execution_time = 0.0

    @property
    def file_read_count(self) -> dict[str, int]:
        return self._file_read_counters

    @staticmethod
    def _parse_month(month_str: str) -> tuple[int, int]:
        """
        Parse 'MMM-YY' (e.g. 'Jan-15', 'Mar-20') -> (year, month).
        """
        part = month_str.strip().split("-")
        if len(part) != 2:
            raise ValueError(f"Invalid month string: {month_str!r}")

        abbr, yy = part[0].strip(), part[1].strip()
        month = MONTH_ABBR.get(abbr)
        if month is None:
            raise ValueError(f"Unknown month abbr: {abbr!r}")

        year = 2000 + int(yy)
        return (year, month)

    def _validate_column_name(self, column_name: str) -> None:
        if column_name not in self.columns:
            raise ValueError(f"Column '{column_name}' not found in column store")

    def _check_columns_exist(self) -> bool:
        """
        Check if all column files exist in the column store.
        """
        for column in self.columns.values():
            if not (self.colstore_path / column.filename).exists():
                return False

            if column.enable_compression_map:
                if not (self.colstore_path / f"{column.name}_map.csv").exists():
                    return False

        return True

    def _initialise_column_files(self) -> None:
        """
        Initialise column files if they don't exist.
        """
        if self._check_columns_exist():
            return

        self.colstore_path.mkdir(parents=True, exist_ok=True)
        column_files = {}
        # Open all column files for writing (binary mode)
        for column in self.columns.values():
            column_file = open(self.colstore_path / column.filename, "wb")
            column_files[column.name] = column_file

        # Read CSV and write to column files
        with open(RAW_CSV, newline="", encoding="utf-8") as csv_file:
            reader = DictReader(csv_file)
            for row in reader:
                for column in self.columns.values():
                    if column.name == "year":
                        month_str = row["month"]
                        year, _ = self._parse_month(month_str)
                        value = year

                    elif column.name == "month":
                        month_str = row["month"]
                        _, month = self._parse_month(month_str)
                        value = month

                    elif column.name in {
                        "floor_area_sqm",
                        "lease_commence_date",
                        "resale_price",
                    }:
                        try:
                            value = literal_eval(row[column.name])
                        except ValueError:
                            value = 0

                    else:
                        value = row[column.name]

                    if column.enable_compression_map:
                        value = column.update_compression_mapping(value)  # type: ignore

                    column_files[column.name].write(column.encode(value))  # type: ignore

        for column_file in column_files.values():
            column_file.close()

        if "basic" in self.types:
            print("Basic column store initialised.")
            return

        # Write mapping files for compressed columns
        for column in self.columns.values():
            if column.enable_compression_map:
                map_writer(self.colstore_path, column.name, column._compression_map)

        print("Compressed column store initialised with mappings.")

    def _load_compression_mappings(self) -> None:
        """
        Load mapping files for compressed columns.
        """
        if "compressed" not in self.types:
            return

        for column in self.columns.values():
            if not column.enable_compression_map:
                continue

            mapping = map_loader(self.colstore_path, column.name)
            column._compression_map = {v: k for k, v in mapping.items()}

    def _initialise_zone_maps(self) -> None:
        """
        Initialise zone maps for all columns if enabled.
        """
        if "zone map" not in self.types:
            return

        for column in self.columns.values():
            if not column.enable_zone_map:
                continue

            for block_index in range(self.get_block_count(column)):
                block_values = self._read_column(
                    column, block_index, disable_cache=True
                )
                if not block_values:
                    break

                column._zone_map.append((min(block_values), max(block_values)))

    def _initialise_composite_index(self) -> None:
        """
        Initialise a composite index mapping (year, month, town) to row indices.
        """
        if "indexed" not in self.types:
            return

        year_col = self.columns.get("year")
        month_col = self.columns.get("month")
        town_col = self.columns.get("town")

        if not (year_col and month_col and town_col):
            return

        years = []
        for block_index in range(self.get_block_count(year_col)):
            years.extend(self._read_column(year_col, block_index, disable_cache=True))

        months = []
        for block_index in range(self.get_block_count(month_col)):
            months.extend(self._read_column(month_col, block_index, disable_cache=True))

        towns = []
        for block_index in range(self.get_block_count(town_col)):
            towns.extend(self._read_column(town_col, block_index, disable_cache=True))

        for row_index, (y, m, t) in enumerate(zip(years, months, towns)):
            key = (y, m, t)
            self._composite_index.setdefault(key, []).append(row_index)

    def query_composite_index(self, year: Any, month: Any, town: Any) -> list[int]:
        """
        Retrieve pre-filtered row indices from the composite index.
        """
        return self._composite_index.get((year, month, town), [])

    def clear_cache(self, column_name: str | None = None) -> None:
        """
        Clear cached blocks for a specific column or all columns.
        """
        if not column_name:
            self._cache.clear()
            return

        keys_to_remove = [key for key in self._cache if key[0] == column_name]
        for key in keys_to_remove:
            del self._cache[key]

    def reset_file_read_counters(self) -> None:
        """
        Reset file read counters for all columns.
        """
        for column_name in self._file_read_counters:
            self._file_read_counters[column_name] = 0

    def get_block_count(self, column: ColumnType) -> int:
        """
        Get the total number of blocks for a given column.
        """
        path = self.colstore_path / column.filename
        if not path.exists():
            return 0

        return (path.stat().st_size + BLOCK_SIZE - 1) // BLOCK_SIZE

    def get_block_index(self, column: ColumnType, row_index: int) -> int:
        """
        Get the block index for a given column and row index.
        """
        return row_index * column.size // BLOCK_SIZE

    def _match_zone_map(
        self, column: ColumnType, block_index: int, predicate: Callable[[Any], bool]
    ) -> bool:
        """
        Check if a block can satisfy the predicate based on its zone map.
        Returns True if the block should be scanned, False if it can be skipped.
        """
        if not column.enable_zone_map:
            return True

        block_min, block_max = column.get_block_zone(block_index)
        if predicate(block_min) or predicate(block_max):
            return True

        try:
            low, high = int(block_min), int(block_max)
            return any(predicate(v) for v in range(low, high + 1))
        except ValueError, TypeError:
            pass

        return False

    def _read_column(
        self, column: ColumnType, block_index: int, disable_cache: bool = False
    ) -> list:
        """
        Read a block of values from a column.
        Returns an empty list if the block is out of range.
        Caches results in memory for faster subsequent access.
        """
        if block_index < 0:
            raise ValueError("Block number must be non-negative")

        # Check cache first
        if not disable_cache and (column.name, block_index) in self._cache:
            return self._cache[(column.name, block_index)]

        path = self.colstore_path / column.filename
        values = []
        if (
            not path.exists()
            or path.stat().st_size == 0
            or path.stat().st_size <= block_index * BLOCK_SIZE
        ):
            return values

        with open(path, "rb") as file:
            file.seek(block_index * BLOCK_SIZE)
            block_data = file.read(BLOCK_SIZE)
            for i in range(0, len(block_data), column.size):
                raw_value = block_data[i : i + column.size]
                if len(raw_value) < column.size:
                    break

                values.append(column.decode(raw_value))

        if not disable_cache:
            self._file_read_counters[column.name] += 1
            self._cache[(column.name, block_index)] = values

        return values

    def scan_column(
        self,
        column: ColumnType,
        predicate: Callable[[Any], bool] | None = None,
        indices: list[int] | None = None,
    ) -> list[int]:
        """
        Scan a column with an optional predicate function and return matching row indices.
        If indices is provided, only check those indices (pre-filtering).
        """
        rows_per_block = BLOCK_SIZE // column.size
        matching_indices = []
        block_indices = None

        for block_index in range(self.get_block_count(column)):
            # Check zone map to skip blocks that cannot satisfy the predicate
            if (
                column.enable_zone_map
                and predicate
                and not self._match_zone_map(column, block_index, predicate)
            ):
                continue

            # If indices is provided, determine which indices fall within the current block for pre-filtering
            if indices is not None:
                block_start = block_index * rows_per_block
                block_end = block_start + rows_per_block
                block_indices = set(i for i in indices if block_start <= i < block_end)
                if not block_indices:
                    continue

            block_values = self._read_column(column, block_index)
            if not block_values:
                break

            for i, value in enumerate(block_values):
                row_index = block_index * rows_per_block + i
                # If indices is provided, only check those indices (pre-filtering)
                if block_indices and row_index not in block_indices:
                    continue

                # Apply predicate if provided
                if predicate is None or predicate(value):
                    matching_indices.append(row_index)

        return matching_indices

    def get_value(self, column: ColumnType, row_index: int):
        """
        Get the value at a specific row index for a given column.
        """
        block_index = self.get_block_index(column, row_index)
        block_values = self._read_column(column, block_index)
        within_block_index = row_index % (BLOCK_SIZE // column.size)

        if within_block_index >= len(block_values):
            raise IndexError(
                f"Row index {row_index} out of range for column '{column.name}'"
            )

        return block_values[within_block_index]

    def print_summary(self) -> None:
        total_block = 0
        total_read = 0
        print(f"{' Column Store Summary ':{'='}^40}")
        print(f"{'Compression:':<15}{'On' if 'compressed' in self.types else 'Off'}")
        print(f"{'Zone Maps:':<15}{'On' if 'zone map' in self.types else 'Off'}")
        print(
            f"{'Indexed:':<15}{'(year, month, town)' if 'indexed' in self.types else 'Off'}\n"
        )

        # Print timing summary
        print(f"{'Phase':<20}{'Time (s)':>20}")
        print(f"{'-' * 40}")
        print(f"{'Initialisation':<20}{self.initialisation_time:>20.3f}")
        print(f"{'Query Execution':<20}{self.query_execution_time:>20.3f}")
        print(f"{'-' * 40}")
        print(
            f"{'Total':<20}{self.initialisation_time + self.query_execution_time:>20.3f}\n"
        )

        # Print column summary
        print(f"{'Column':<20}{'Blocks':>10}{'Read':>10}")
        print(f"{'-' * 40}")
        for column in self.columns.values():
            path = self.colstore_path / column.filename
            if not path.exists():
                continue

            block_count = self.get_block_count(column)
            read_count = self._file_read_counters[column.name]
            print(f"{column.name:<20}{block_count:>10}{read_count:>10}")
            total_block += block_count
            total_read += read_count

        print(f"{'-' * 40}")
        print(f"{'Total':<20}{total_block:>10}{total_read:>10}")
        print(f"{'=' * 40}\n")
