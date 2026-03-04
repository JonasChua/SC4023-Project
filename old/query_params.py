"""
Phase 2: Derive query conditions from matriculation number.

Spec (Semester_Group_Project.pdf):
- Target year: last digit of matric = last digit of year. 2025 is not allowed as target year.
- Start month: second-last digit of matric; "0" means October (10).
- Towns: all digits in the matric map to towns per Table 1.
"""

import csv
import re
from pathlib import Path

# Table 1 from spec: digit -> town name
DIGIT_TO_TOWN = {
    0: "BEDOK",
    1: "BUKIT PANJANG",
    2: "CLEMENTI",
    3: "CHOA CHU KANG",
    4: "HOUGANG",
    5: "JURONG WEST",
    6: "PASIR RIS",
    7: "TAMPINES",
    8: "WOODLANDS",
    9: "YISHUN",
}


def get_digits(matric_str: str) -> list[int]:
    """Extract all digits from matriculation number (e.g. A5656567B -> [5,6,5,6,5,6,7])."""
    return [int(c) for c in matric_str if c.isdigit()]


def target_year_from_matric(matric_str: str) -> int:
    """
    Last digit of target year matches last digit of matric.
    ​2025 is not used as target year (spec: "data for 2025 is provided only for query, not as the target year").
    So: 0->2020, 1->2021, ..., 4->2024, 5->2015, 6->2016, 7->2017, 8->2018, 9->2019.
    """
    digits = get_digits(matric_str)
    if not digits:
        raise ValueError("Matriculation number has no digits")
    last = digits[-1]
    if last <= 4:
        return 2020 + last  # 2020, 2021, 2022, 2023, 2024
    return 2010 + last  # 2015, 2016, 2017, 2018, 2019


def start_month_from_matric(matric_str: str) -> int:
    """Second-last digit of matric; 0 means October (10)."""
    digits = get_digits(matric_str)
    if len(digits) < 2:
        raise ValueError("Matriculation number must have at least two digits")
    d = digits[-2]
    return 10 if d == 0 else d


def town_names_from_matric(matric_str: str) -> set[str]:
    """Set of town names corresponding to all digits in the matric (Table 1)."""
    digits = get_digits(matric_str)
    return {DIGIT_TO_TOWN[d] for d in digits if d in DIGIT_TO_TOWN}


def load_town_name_to_id(colstore_path: Path) -> dict[str, int]:
    """Load dict_town.csv and return mapping town name -> id."""
    path = colstore_path / "dict_town.csv"
    name_to_id = {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name_to_id[row["value"].strip()] = int(row["id"])
    return name_to_id


def get_query_params(matric_str: str, colstore_path: Path) -> tuple[int, int, set[int]]:
    """
    Returns (target_year, start_month, town_ids).
    town_ids are the integer IDs used in the column store (from dict_town.csv).
    """
    target_year = target_year_from_matric(matric_str)
    start_month = start_month_from_matric(matric_str)
    town_names = town_names_from_matric(matric_str)
    name_to_id = load_town_name_to_id(colstore_path)
    town_ids = set()
    for name in town_names:
        if name in name_to_id:
            town_ids.add(name_to_id[name])
        # else: town not in dataset (should not happen for Table 1 towns)
    return (target_year, start_month, town_ids)


def get_month_range(start_month: int, x: int) -> tuple[int, int]:
    """
    For a given x (number of months), return (start_month, end_month) inclusive.
    end_month is capped at 12 (same calendar year only).
    """
    end_month = min(12, start_month + x - 1)
    return (start_month, end_month)
