from csv import DictReader, writer
from pathlib import Path


def map_loader(file_path: Path, column_name: str) -> dict[int, str]:
    """
    Load <column_name>_map.csv; return mapping of id -> string.
    """
    path = file_path / f"{column_name}_map.csv"
    if not path.exists():
        return {}

    with open(path, newline="") as file:
        reader = DictReader(file)
        return {int(r["id"]): r["value"] for r in reader}


def map_writer(file_path: Path, column_name: str, mapping: dict[str, int]) -> None:
    """
    Write mapping of id -> string to <column_name>_map.csv.
    """
    file_path.mkdir(parents=True, exist_ok=True)
    path = file_path / f"{column_name}_map.csv"
    with open(path, "w", newline="") as file:
        w = writer(file)
        w.writerow(["id", "value"])
        for value, id in sorted(mapping.items(), key=lambda x: x[1]):
            w.writerow([id, value])
