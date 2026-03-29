from csv import DictWriter
from time import perf_counter
from typing import Any

from constants import DIGIT_TO_TOWN, PROJECT_ROOT
from store import ColumnStore


class QueryParser:
    def __init__(self, matric_str: str):
        self.matric_str = matric_str
        self.digits = self.get_digits(matric_str)
        self.target_year = self._parse_target_year()
        self.start_month = self._parse_start_month()
        self.town_names = self._parse_town_names()

    def _parse_target_year(self) -> int:
        """
        Last digit of target year matches last digit of matric.
        e.g. 0->2020, 1->2021, ..., 4->2024, 5->2015, ..., 9->2019.
        """
        if not self.digits:
            raise ValueError("Matriculation number has no digits")

        last = self.digits[-1]
        return last + (2010 if last >= 5 else 2020)

    def _parse_start_month(self) -> int:
        """
        Second-last digit of matric; 0 means October (10).
        """
        if len(self.digits) < 2:
            raise ValueError("Matriculation number must have at least two digits")

        d = self.digits[-2]
        return 10 if d == 0 else d

    def _parse_town_names(self) -> set[str]:
        """
        Set of town names corresponding to all digits in the matric.
        """
        return {DIGIT_TO_TOWN[d] for d in self.digits if d in DIGIT_TO_TOWN}

    @staticmethod
    def get_digits(matric_str: str) -> list[int]:
        """
        Extract all digits from matriculation number
        (e.g. A5656567B -> [5, 6, 5, 6, 5, 6, 7]).
        """
        return [int(c) for c in matric_str if c.isdigit()]

    @staticmethod
    def get_end_month(start_month: int, x: int) -> int:
        """
        For a given x (number of months), return the end month.
        end_month is capped at 12 (same calendar year only).
        """
        return min(12, start_month + x - 1)


class QueryEngine:
    def __init__(self, colstore: ColumnStore, matric_str: str):
        self.colstore = colstore
        self.results = dict()
        self.query = QueryParser(matric_str)

    def filter_year_index(
        self, year: int, indices: list[int] | None = None
    ) -> list[int]:
        """
        Get list of row indices matching the year.
        """
        year_col = self.colstore.columns["year"]
        return self.colstore.scan_column(year_col, lambda v: v == year, indices)

    def filter_month_index(
        self, start_month: int, end_month: int, indices: list[int] | None = None
    ) -> list[int]:
        """
        Get list of row indices matching the month range.
        """
        month_col = self.colstore.columns["month"]
        return self.colstore.scan_column(
            month_col, lambda v: start_month <= v <= end_month, indices
        )

    def filter_town_index(
        self, town_names: set[str], indices: list[int] | None = None
    ) -> list[int]:
        """
        Get list of row indices matching the town names.
        If town column has mapping enabled, map town names to IDs first for faster comparison.
        """
        town_col = self.colstore.columns["town"]
        town_name_mappings = (
            {town_col.map_value(t, -1) for t in town_names}
            if town_col.enable_compression_map
            else town_names
        )
        return self.colstore.scan_column(
            town_col, lambda v: v in town_name_mappings, indices
        )

    def filter_minimum_floor_area_index(
        self, minimum_floor_area: int, indices: list[int] | None = None
    ) -> list[int]:
        """
        Get list of row indices matching the minimum floor area.
        """
        floor_area_col = self.colstore.columns["floor_area_sqm"]
        return self.colstore.scan_column(
            floor_area_col, lambda v: v >= minimum_floor_area, indices
        )

    def select_minimum_price_per_floor_area(
        self, indices: list[int]
    ) -> tuple[int, float]:
        """
        From the given indices, find the index with the minimum price per floor area.
        """
        min_ppm = float("inf")
        best_index = -1
        floor_area_col = self.colstore.columns["floor_area_sqm"]
        price_col = self.colstore.columns["resale_price"]

        for i in indices:
            floor_area = self.colstore.get_value(floor_area_col, i)
            price = self.colstore.get_value(price_col, i)
            if floor_area > 0:  # Avoid division by zero
                ppm = price / floor_area
                if ppm < min_ppm:
                    min_ppm = ppm
                    best_index = i

        return best_index, min_ppm

    def select_row_data(self, row_index: int) -> dict[str, Any]:
        """
        For a given row index, return a dictionary of column name to value for that row.
        """
        row_data = {}
        for column_name, column in self.colstore.columns.items():
            value = self.colstore.get_value(column, row_index)
            if column.enable_compression_map and isinstance(value, int):
                value = column.unmap_value(value)

            row_data[column_name] = value

        return row_data

    def execute_query(self):
        """
        Execute the query based on the matriculation number and store results.
        """
        start = perf_counter()
        target_year = self.query.target_year
        start_month = self.query.start_month
        town_names = self.query.town_names

        # Minimum floor area y ranges from 80 to 150
        for y in range(80, 151):
            # Number of consecutive months to consider for each x (1 to 8)
            for x in range(1, 9):
                end_month = self.query.get_end_month(start_month, x)
                if "indexed" in self.colstore.types:
                    indices = []
                    town_col = self.colstore.columns["town"]
                    for month in range(start_month, end_month + 1):
                        for town in town_names:
                            if town_col.enable_compression_map:
                                town_id = town_col.map_value(town, -1)
                                if town_id == -1:
                                    print(f"Unknown town: {town}")
                                    continue

                            else:
                                town_id = town

                            indices.extend(
                                self.colstore.query_composite_index(
                                    target_year, month, town_id
                                )
                            )
                else:
                    indices = self.filter_year_index(target_year)
                    indices = self.filter_month_index(start_month, end_month, indices)
                    indices = self.filter_town_index(town_names, indices)

                indices = self.filter_minimum_floor_area_index(y, indices)
                best_index, min_ppm = self.select_minimum_price_per_floor_area(indices)
                row_data = (
                    self.select_row_data(best_index) if best_index != -1 else None
                )
                self.results[(x, y)] = (
                    {**row_data, "price_per_sqm": round(min_ppm)} if row_data else None
                )

        self.colstore.query_execution_time = perf_counter() - start

    def export_results(self) -> None:
        """
        Export the query results into ScanResult_<matric_str>.csv file.
        """
        result_dir = PROJECT_ROOT / "result"
        result_dir.mkdir(parents=True, exist_ok=True)
        output_path = result_dir / f"ScanResult_{self.query.matric_str}.csv"
        with output_path.open("w", newline="") as csvfile:
            fieldnames = [
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
            writer = DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            for (x, y), data in self.results.items():
                # print(f"{x=} {y=}")
                if data is not None:
                    writer.writerow(
                        {
                            "(x, y)": f"({x}, {y})",
                            "Year": data["year"],
                            "Month": data["month"],
                            "Town": data["town"],
                            "Block": data["block"],
                            "Floor_Area": data["floor_area_sqm"],
                            "Flat_Model": data["flat_model"],
                            "Lease_Commence_Date": data["lease_commence_date"],
                            "Price_Per_Square_Meter": data["price_per_sqm"],
                        }
                    )

        print(f"Results exported to {output_path.relative_to(PROJECT_ROOT)}")
