from csv import DictWriter

from constants import PROJECT_ROOT
from query import QueryEngine


def export_results(query_engine: QueryEngine) -> None:
    """
    Export the query results into ScanResult_<matric_str>.csv file.
    """
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
    result_dir = PROJECT_ROOT / "result"
    result_dir.mkdir(parents=True, exist_ok=True)
    output_path = result_dir / f"ScanResult_{query_engine.query.matric_str}.csv"
    with output_path.open("w", newline="") as csvfile:
        writer = DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for (x, y), data in query_engine.results.items():
            if not data:
                continue

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


def export_query_statistics_csv(query_engines: dict[str, QueryEngine]) -> None:
    """
    Export the query statistics into QueryStatistics.csv file.
    """
    stats = []
    for store_name, query_engine in query_engines.items():
        column_store = query_engine.colstore
        total_block_count = 0
        total_block_read_count = 0
        query_stats = {
            "column_store": store_name,
            "initialisation_time": column_store.initialisation_time,
            "execution_time": column_store.query_execution_time,
            "total_time_taken": column_store.initialisation_time
            + column_store.query_execution_time,
        }
        for column in column_store.columns.values():
            block_count = column_store.get_block_count(column)
            query_stats[f"{column.name}_block_count"] = block_count
            total_block_count += block_count

        query_stats["total_block_count"] = total_block_count
        for column in column_store.columns.values():
            read_count = column_store.get_block_read_count(column)
            query_stats[f"{column.name}_block_read_count"] = read_count
            total_block_read_count += read_count

        query_stats["total_block_read_count"] = total_block_read_count
        stats.append(query_stats)

    result_dir = PROJECT_ROOT / "result"
    result_dir.mkdir(parents=True, exist_ok=True)
    output_path = result_dir / "QueryStatistics.csv"
    with open(output_path, "w", newline="") as csvfile:
        writer = DictWriter(csvfile, fieldnames=list(stats[0].keys()))
        writer.writeheader()
        writer.writerows(stats)

    print(f"Query statistics exported to {output_path.relative_to(PROJECT_ROOT)}")


def build_store_summary_lines(query_engine: QueryEngine) -> list[str]:
    """
    Build summary lines.
    """
    column_store = query_engine.colstore
    total_block = 0
    total_read = 0
    lines = [
        f"{' Column Store Summary ':{'='}^40}",
        f"{'Compression:':<15}{'On' if 'compressed' in column_store.types else 'Off'}",
        f"{'Zone Maps:':<15}{'On' if 'zone map' in column_store.types else 'Off'}",
        f"{'Indexed:':<15}{'(year, month, town)' if 'indexed' in column_store.types else 'Off'}\n",
        f"{'Phase':<20}{'Time (s)':>20}",
        f"{'-' * 40}",
        f"{'Initialisation':<20}{column_store.initialisation_time:>20.3f}",
        f"{'Query Execution':<20}{column_store.query_execution_time:>20.3f}",
        f"{'-' * 40}",
        f"{'Total':<20}{column_store.initialisation_time + column_store.query_execution_time:>20.3f}\n",
        f"{'Column':<20}{'Blocks':>10}{'Read':>10}",
        f"{'-' * 40}",
    ]

    for column in column_store.columns.values():
        path = column_store.colstore_path / column.filename
        if not path.exists():
            continue

        block_count = column_store.get_block_count(column)
        read_count = column_store.get_block_read_count(column)
        lines.append(f"{column.name:<20}{block_count:>10}{read_count:>10}")
        total_block += block_count
        total_read += read_count

    lines.extend(
        [
            f"{'-' * 40}",
            f"{'Total':<20}{total_block:>10}{total_read:>10}",
            f"{'=' * 40}",
        ]
    )

    return lines


def export_query_statistics_txt(query_engines: dict[str, QueryEngine]) -> None:
    """
    Export the query statistics into QueryStatistics.txt file.
    """
    result_dir = PROJECT_ROOT / "result"
    result_dir.mkdir(parents=True, exist_ok=True)
    output_path = result_dir / "QueryStatistics.txt"

    output_lines: list[str] = []
    for query_engine in query_engines.values():
        output_lines.extend(build_store_summary_lines(query_engine))
        output_lines.append("")

    with output_path.open("w", encoding="utf-8", newline="") as txtfile:
        txtfile.write("\n".join(output_lines).rstrip() + "\n")

    print(f"Query statistics exported to {output_path.relative_to(PROJECT_ROOT)}")


def export_query_statistics(query_engines: dict[str, QueryEngine]) -> None:
    """
    Export the query statistics into both QueryStatistics.txt and QueryStatistics.csv files.
    """
    export_query_statistics_txt(query_engines)
    export_query_statistics_csv(query_engines)
